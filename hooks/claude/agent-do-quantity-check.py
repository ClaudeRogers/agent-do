#!/usr/bin/env python3
"""
PostToolUse hook (matcher: Edit|Write): a bare literal in a bounding slot.

The failure this exists for: an agent writes a max_tokens of 4096 into a
project, and from then on every request to that model is capped there. The
number reads as deliberate configuration, so review passes over it. Nothing
errors. The only symptom is a response that stops mid-sentence, or JSON that
parses and is missing its tail. The write moment is the last cheap moment —
after it, the cap is code somebody has to notice.

So this reads what was just written, finds numbers typed into bounding slots,
and asks the quantity authority what the real ceiling is. Where the authority
knows, the nudge names it. Where the authority has no record — a real and
current model can be missing — the nudge says the literal is unverified and
names nothing. A guessed ceiling would be the same defect this hook is for.

WHAT PASSES, and why the ladder is shaped this way:
  A reference passes: an identifier, a config lookup, a computed expression.
  A named constant passes when its definition carries a derivation comment —
  the comment is the derivation, and a constant without one is still a number
  somebody typed. A literal at a call site does not pass on a comment, because
  the remediation there is to omit the parameter or reference the constant, not
  to annotate the number in place.

NOISE DISCIPLINE. A check that cries wolf gets trained away, and a dismissed
check is worse than no check. Hence: one nudge per file per session; nothing at
all for a file with no bounding literals; comments, docs, tests, and fixtures
are out of scope; anonymous bounds (slices, LIMIT, head/tail) are only reported
above a floor, because a two-element slice is structure and a forty-element one
is a cap. Comment lines are skipped, but prose inside a string literal is not:
telling the two apart needs a parser, and a parser is not a millisecond.

Nudge only. Never blocks, never exits nonzero, silent exit 0 on malformed
input, a missing authority, or any error at all. AGENT_DO_QUANTITY_CHECK=0
turns it off. The scan/render split below is what lets the same check be
registered as a PreToolUse block later without a rewrite: block mode adds a
permission decision to the same findings, it does not compute different ones.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

AGENT_DO_HOME = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))
STATE_DIR = AGENT_DO_HOME / "quantity"
RECEIPT_PATH = STATE_DIR / "write-checks.jsonl"

# Session cooldown files stop being interesting the moment the session ends, and
# nothing tells this hook that a session ended. A week is longer than any
# session that could still be editing the same file.
SWEEP_AFTER_SECONDS = 7 * 24 * 3600

# Budgets. A hook on every edit pays for itself in milliseconds or not at all.
MAX_SCAN_BYTES = 512 * 1024
MAX_FINDINGS_SCANNED = 200
MAX_FINDINGS_REPORTED = 6

# Truncations this file performs on its own strings, named rather than typed
# inline — the ladder below applies to the hook that preaches it.
#
# LINE_TEXT_CHARS bounds a source line kept for matching and display: long
# enough for any real bounding expression plus its context, short enough that a
# minified line cannot put kilobytes into a nudge or a receipt.
LINE_TEXT_CHARS = 160
# SHA-1 is 40 hex characters; 16 of them is 64 bits of session-plus-path key,
# which is a collision every few billion files rather than every few thousand.
TOKEN_HEX_CHARS = 16
# A session id is a 36-character UUID. 64 leaves room for the longer ids other
# runtimes hand out while keeping the filename inside every filesystem's limit.
SESSION_KEY_CHARS = 64

# An anonymous bound is one with no name to argue with: a slice, a LIMIT, a
# `head -n`. Below this floor they are overwhelmingly structural (`[:1]` is
# "the first one", not a cap), and reporting them is exactly the cry-wolf that
# gets the whole check ignored. Named slots carry no floor: `max_tokens=1` is
# as much a typed ceiling as `max_tokens=4096`.
ANONYMOUS_BOUND_FLOOR = 10

# Bounding slots, normalized (lowercased, separators stripped) so that
# max_tokens, maxTokens, MAX_TOKENS, and --max-tokens are one entry.
#
# TOKEN_SLOTS are the ones the authority may hold a published ceiling for.
# BOUND_SLOTS are bounds with no published ceiling anywhere — the number is
# still unexplained, but no lookup can contradict it.
TOKEN_SLOTS = {
    "maxtokens": ("max_output_tokens", "max_tokens"),
    "maxoutputtokens": ("max_output_tokens", "max_tokens"),
    "maxcompletiontokens": ("max_completion_tokens", "max_tokens"),
    "maxnewtokens": ("max_output_tokens", "max_tokens"),
    "maxresponsetokens": ("max_output_tokens", "max_tokens"),
    "maxlength": ("max_output_tokens", "max_tokens"),
    "maxinputtokens": ("max_input_tokens",),
    "contextwindow": ("max_input_tokens",),
    "maxcontexttokens": ("max_input_tokens",),
    # A thinking budget is bounded by the output ceiling, so that is the
    # published number worth naming next to it.
    "budgettokens": ("max_tokens",),
    "thinkingbudget": ("max_tokens",),
    "thinkingbudgettokens": ("max_tokens",),
    "maxthinkingtokens": ("max_tokens",),
    "tokenbudget": ("max_tokens",),
    "reasoningtokens": ("max_tokens",),
    # No published ceiling, but unmistakably a cap on how much is considered.
    "topk": (),
}

BOUND_SLOTS = {
    "limit",
    "maxresults",
    "pagesize",
    "perpage",
    "batchsize",
    "chunksize",
    "timeout",
    "timeoutms",
    "timeoutsec",
    "timeoutseconds",
    "retries",
    "maxretries",
    "maxattempts",
    "maxiterations",
    "maxsteps",
    "maxturns",
    "maxdepth",
}

# `temperature` and `top_p` are deliberately absent. They are sampling
# parameters, not bounds, and nothing in a line of source distinguishes a
# cap-like use from an ordinary one — so every reading would be a guess, and a
# guess here spends the credibility the real findings need.

_ALNUM = re.compile(r"[^a-z0-9]+")

# name = 4096 | "name": 4096 | name => 4096
ASSIGN_RE = re.compile(
    r"""(?P<quote>["'`]?)(?P<name>[A-Za-z_][A-Za-z0-9_.\-]*)(?P=quote)\s*
        (?::|=>|=)\s*
        (?P<value>\d[\d_]*)(?![\d.\w])""",
    re.VERBOSE,
)
# --max-tokens 4096 | --max-tokens=4096
FLAG_RE = re.compile(r"--(?P<name>[A-Za-z][A-Za-z0-9\-]*)[=\s]+(?P<value>\d[\d_]*)(?![\d.\w])")
# name(4096) — .limit(100), setMaxTokens(4096)
CALL_RE = re.compile(r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\(\s*(?P<value>\d[\d_]*)\s*\)")

ANONYMOUS_RES = (
    ("slice", re.compile(r"\[\s*(?:0\s*)?:\s*(?P<value>\d[\d_]*)\s*\]")),
    ("slice", re.compile(r"\.slice\(\s*(?:0\s*,\s*)?(?P<value>\d[\d_]*)\s*\)")),
    ("slice", re.compile(r"\bislice\([^,)]+,\s*(?P<value>\d[\d_]*)\s*\)")),
    ("sql limit", re.compile(r"\bLIMIT\s+(?P<value>\d[\d_]*)\b", re.IGNORECASE)),
    ("head/tail", re.compile(r"\b(?:head|tail)\s+(?:-n\s*|-)(?P<value>\d[\d_]*)\b")),
)

COMMENT_LINE = re.compile(r"^\s*(?:#|//|/\*|\*|--|<!--)")
TRAILING_COMMENT = re.compile(r"(?:#|//|/\*|--)\s*\S")
CONSTANT_DEF = re.compile(
    r"^\s*(?:(?:export|const|let|var|final|static|public|private|readonly)\s+)*"
    r"(?P<name>[A-Z][A-Z0-9_]*)\s*(?::[^=]+)?=[^=]"
)
# Someone who wrote an authority key on the line already consulted the
# authority; that is the behaviour this hook exists to produce.
AUTHORITY_REFERENCE = re.compile(
    r"harness\s+quantity|\b[a-z][a-z0-9_]*\.[A-Za-z0-9._\-]+\.(?:max_\w+|budget_\w+|page_limit)\b"
)

MODEL_RE = re.compile(
    r"\b(?P<id>(?:claude|gpt|gemini|llama|mistral)-[A-Za-z0-9][A-Za-z0-9.\-]*)",
)
MODEL_NAMESPACES = {
    "claude": "anthropic",
    "gpt": "openai",
    "gemini": "google",
    "llama": "meta",
    "mistral": "mistralai",
}

# Source files only. A cap in a Markdown example is an example; a cap in a
# lockfile is not the agent's writing; a cap in a test is a fixture pinning a
# small number on purpose.
CODE_SUFFIXES = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs",
    ".rb", ".java", ".kt", ".swift", ".php", ".cs", ".scala", ".lua", ".pl",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".m", ".sh", ".bash", ".zsh", ".sql",
    ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".tf", ".hcl", ".gradle",
}
SKIP_PATH_MARKERS = (
    "/test/", "/tests/", "/__tests__/", "/spec/", "/specs/", "/fixtures/",
    "/testdata/", "/node_modules/", "/vendor/", "/dist/", "/build/",
    "/.venv/", "/site-packages/", "/.git/", "/coverage/",
)
SKIP_NAME_PREFIXES = ("test_", "conftest")
SKIP_NAME_MARKERS = (".test.", ".spec.", "_test.", "-test.", ".lock", ".min.")
# The authority's own record is the one file where a published ceiling written
# as a number is the correct form — it is what every other file is supposed to
# reference instead of typing.
SKIP_NAMES = ("models.yaml",)


def disabled() -> bool:
    return os.environ.get("AGENT_DO_QUANTITY_CHECK", "").strip() == "0"


def normalize(name: str) -> str:
    return _ALNUM.sub("", name.lower())


# ── what was written ──────────────────────────────────────────────────────


def written_text(tool_name: str, tool_input: dict) -> str:
    """The text this tool call put into the file, and nothing else.

    Only new text is scanned. Code that was already in the file was not written
    by this call, and nudging about it would make every edit to a legacy file a
    lecture about the whole file.
    """
    if tool_name == "Write":
        content = tool_input.get("content")
        return content if isinstance(content, str) else ""

    parts: list[str] = []
    new_string = tool_input.get("new_string")
    if isinstance(new_string, str):
        parts.append(new_string)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
                parts.append(edit["new_string"])
    return "\n".join(parts)


def in_scope(path: Path) -> bool:
    # Leading slash so the directory markers below match a first segment too:
    # a relative `tests/client.py` is as much a test as an absolute one.
    posix = "/" + path.as_posix().lstrip("/")
    name = path.name.lower()
    if path.suffix.lower() not in CODE_SUFFIXES:
        return False
    if any(marker in posix for marker in SKIP_PATH_MARKERS):
        return False
    if any(name.startswith(prefix) for prefix in SKIP_NAME_PREFIXES):
        return False
    if any(marker in name for marker in SKIP_NAME_MARKERS):
        return False
    if name in SKIP_NAMES:
        return False
    return True


# ── the scan ──────────────────────────────────────────────────────────────


def carries_derivation(lines: list[str], index: int) -> bool:
    """Does this constant definition say where its number came from?

    A comment on the line or immediately above it is the derivation. Blank
    lines between the comment and the definition break the association: a
    comment two paragraphs up is about something else.
    """
    line = lines[index] if 0 <= index < len(lines) else ""
    if TRAILING_COMMENT.search(line):
        return True
    if index - 1 >= 0 and COMMENT_LINE.match(lines[index - 1]):
        return True
    return False


def scan(text: str) -> list[dict]:
    """Every bare literal in a bounding slot, in the order it was written.

    Findings carry the line text rather than a line number: the number is
    resolved later against the file on disk, because an Edit's fragment has no
    line numbering of its own and a wrong line number is worse than none.
    """
    findings: list[dict] = []
    lines = text.splitlines()

    for index, line in enumerate(lines):
        if len(findings) >= MAX_FINDINGS_SCANNED:
            break
        if COMMENT_LINE.match(line):
            continue
        if AUTHORITY_REFERENCE.search(line):
            continue

        constant = CONSTANT_DEF.match(line)
        seen_here: set[tuple[str, str]] = set()

        for pattern in (ASSIGN_RE, FLAG_RE, CALL_RE):
            for match in pattern.finditer(line):
                raw_name = match.group("name")
                # Dots are attribute access, so the slot is the last segment:
                # `self.timeout = 30` and `config.max_tokens: 4096` are the
                # same two slots as their undotted forms.
                key = normalize(raw_name.rsplit(".", 1)[-1])
                if key in TOKEN_SLOTS:
                    tier, fields = "token", TOKEN_SLOTS[key]
                elif key in BOUND_SLOTS:
                    tier, fields = "bound", ()
                else:
                    continue
                value = match.group("value")
                if (raw_name, value) in seen_here:
                    continue
                seen_here.add((raw_name, value))
                # A named constant that documents its derivation is the
                # sanctioned form; flagging it would make the ladder's own top
                # rung unreachable.
                if constant and carries_derivation(lines, index):
                    continue
                findings.append(
                    {
                        "slot": raw_name,
                        "normalized": key,
                        "value": int(value.replace("_", "")),
                        "tier": tier,
                        "fields": list(fields),
                        "line_text": line.strip()[:LINE_TEXT_CHARS],
                        "fragment_line": index,
                        "kind": "constant" if constant else "call-site",
                    }
                )

        for label, pattern in ANONYMOUS_RES:
            for match in pattern.finditer(line):
                value = int(match.group("value").replace("_", ""))
                if value < ANONYMOUS_BOUND_FLOOR:
                    continue
                if (label, str(value)) in seen_here:
                    continue
                seen_here.add((label, str(value)))
                if constant and carries_derivation(lines, index):
                    continue
                findings.append(
                    {
                        "slot": label,
                        "normalized": label,
                        "value": value,
                        "tier": "bound",
                        "fields": [],
                        "line_text": line.strip()[:LINE_TEXT_CHARS],
                        "fragment_line": index,
                        "kind": "anonymous",
                    }
                )

    return findings


def model_mentions(text: str) -> list[tuple[int, str]]:
    """Model ids in the written text, with the line they appear on."""
    found: list[tuple[int, str]] = []
    for index, line in enumerate(text.splitlines()):
        for match in MODEL_RE.finditer(line):
            found.append((index, match.group("id").rstrip(".-")))
    return found


def nearest_model(mentions: list[tuple[int, str]], line: int) -> str | None:
    if not mentions:
        return None
    return min(mentions, key=lambda item: (abs(item[0] - line), item[0]))[1]


def authority_key(model: str, field: str) -> str:
    prefix = model.split("-", 1)[0].lower()
    return f"{MODEL_NAMESPACES.get(prefix, prefix)}.{model}.{field}"


def load_authority():
    """The authority's own resolver, or None.

    This imports `lib/quantities.py` rather than shelling out to
    `agent-do harness quantity lookup`: the CLI costs the better part of a
    second per call, and this hook has 300ms for the whole run. It is the same
    resolver reading the same models.yaml — the number still comes from the
    authority, and no ceiling is ever written down here.
    """
    for candidate in (
        os.environ.get("AGENT_DO_REPO"),
        _breadcrumb_repo(),
        str(Path(__file__).resolve().parents[2]),
    ):
        if not candidate:
            continue
        lib = Path(candidate).expanduser() / "lib"
        if not (lib / "quantities.py").is_file():
            continue
        if str(lib) not in sys.path:
            sys.path.insert(0, str(lib))
        try:
            import quantities  # noqa: PLC0415 — resolved at run time by design

            return quantities
        except Exception:
            return None
    return None


def _breadcrumb_repo() -> str | None:
    try:
        return (AGENT_DO_HOME / "install-path").read_text(encoding="utf-8").strip() or None
    except Exception:
        return None


def resolve_ceilings(findings: list[dict], text: str) -> None:
    """Attach the published ceiling to every token-slot finding that has one.

    Three outcomes, and the difference between them is the whole point:
      known      the authority holds the number, so the nudge cites it
      no_record  the key is well-formed and the authority has never heard of
                 it — said plainly, with no number invented to fill the hole
      no_subject nothing in the file names a model, so no key exists to ask
    """
    token_findings = [item for item in findings if item["tier"] == "token" and item["fields"]]
    if not token_findings:
        return

    mentions = model_mentions(text)
    authority = load_authority()
    if authority is None:
        for item in token_findings:
            item["ceiling_status"] = "authority_unavailable"
        return

    try:
        config = authority.load_config()
    except Exception:
        for item in token_findings:
            item["ceiling_status"] = "authority_unavailable"
        return

    declared_fields: set[str] | None = None

    for item in token_findings:
        model = nearest_model(mentions, item["fragment_line"])
        if not model:
            item["ceiling_status"] = "no_subject"
            continue
        keys = [authority_key(model, field) for field in item["fields"]]
        item["ceiling_key"] = keys[0]
        for key in keys:
            try:
                record = authority.lookup(key, config)
            except Exception:
                continue
            item["ceiling_key"] = key
            item["ceiling_value"] = record.get("value")
            item["ceiling_status"] = "known"
            break
        else:
            # Nothing matched, so the key we name is the one somebody would
            # have to add. Prefer a field the authority already uses for other
            # subjects: naming a field it has never declared would send the
            # reader after a key that would not exist even once the gap closed.
            if declared_fields is None:
                declared_fields = _declared_fields(authority, config)
            for key, field in zip(keys, item["fields"]):
                if field in declared_fields:
                    item["ceiling_key"] = key
                    break
            item["ceiling_status"] = "no_record"


def _declared_fields(authority, config) -> set[str]:
    try:
        return {entry["key"].rsplit(".", 1)[-1] for entry in authority.authority_entries(config)}
    except Exception:
        return set()


# ── line numbers ──────────────────────────────────────────────────────────


def resolve_lines(findings: list[dict], path: Path) -> None:
    """Give each finding the line number it has in the file that shipped.

    Matched by unique line text, because an Edit's `new_string` is a fragment
    with no idea where it landed. Ambiguity yields no number rather than a
    plausible wrong one.
    """
    try:
        if path.stat().st_size > MAX_SCAN_BYTES:
            return
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return

    index: dict[str, list[int]] = {}
    for number, line in enumerate(lines, start=1):
        index.setdefault(line.strip()[:LINE_TEXT_CHARS], []).append(number)

    for item in findings:
        matches = index.get(item["line_text"], [])
        if len(matches) == 1:
            item["line"] = matches[0]


# ── the message ───────────────────────────────────────────────────────────


def rank(item: dict) -> tuple:
    # Token slots first: they are the class that runs on every request and
    # truncates silently. Within a tier, the order they were written.
    return (0 if item["tier"] == "token" else 1, item.get("fragment_line", 0))


def describe(item: dict) -> str:
    where = f"line {item['line']}" if item.get("line") else "written here"
    head = f"  {where}  {item['slot']}={item['value']}"
    status = item.get("ceiling_status")
    if status == "known":
        return f"{head} — {item['ceiling_key']} is {item['ceiling_value']}"
    if status == "no_record":
        return (
            f"{head} — the authority holds no record for {item['ceiling_key']}, "
            "so this ceiling is unverified"
        )
    if status == "no_subject":
        return f"{head} — no model is named nearby, so no published ceiling resolves"
    if status == "authority_unavailable":
        return f"{head} — the quantity authority could not be read, so no ceiling was checked"
    return f"{head} — a bound with no published ceiling and no stated derivation"


def render(display_path: str, findings: list[dict]) -> str:
    ordered = sorted(findings, key=rank)
    shown = ordered[:MAX_FINDINGS_REPORTED]
    lines = [
        f"Bare numeric literals were just written into bounding slots in {display_path}. "
        "A number typed into a bound runs on every call for as long as the code lives, "
        "reads as configuration so review passes over it, and fails by truncating output "
        "rather than by raising.",
        "",
    ]
    lines += [describe(item) for item in shown]
    if len(ordered) > len(shown):
        lines.append(f"  ...and {len(ordered) - len(shown)} more in the same write")
    lines += [
        "",
        "The remediation hierarchy, strictest first: omit the parameter entirely and take "
        "the provider's own default; reference a capability constant; or define a named "
        "constant whose definition carries the real-world constraint that produced the "
        "number. Published ceilings: agent-do harness quantity lookup "
        "<namespace>.<subject>.<quantity>; agent-do harness quantity keys lists what is "
        "declared. A key with no record is a gap in the authority, never a licence to "
        "pick a number.",
        "",
        "This fires once per file per session. AGENT_DO_QUANTITY_CHECK=0 turns it off.",
    ]
    return "\n".join(lines)


# ── session state and receipts ────────────────────────────────────────────


def session_token(session_id: object, path: Path) -> str | None:
    """The cooldown key for this file in this session, or None without an id.

    No id means no cooldown rather than a shared one: two unrelated agents
    falling back to the same key would silence each other's first finding, and
    a missed cap costs more than a repeated nudge.
    """
    if not isinstance(session_id, str) or not session_id.strip():
        return None
    return hashlib.sha1(f"{session_id}\0{path.as_posix()}".encode()).hexdigest()[:TOKEN_HEX_CHARS]


def already_nudged(token: str, session_id: str) -> bool:
    """One nudge per file per session, claimed before the message is emitted.

    Append-only, one file per session: parallel agents write their own files,
    and a short append is atomic enough that two of this hook's own runs cannot
    lose each other's rows.
    """
    key = re.sub(r"[^A-Za-z0-9._-]+", "-", session_id).strip("-.")[:SESSION_KEY_CHARS] or "unknown"
    seen_path = STATE_DIR / f"seen-{key}.txt"
    try:
        if seen_path.is_file() and token in seen_path.read_text(encoding="utf-8").split():
            return True
    except Exception:
        return False
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with seen_path.open("a", encoding="utf-8") as handle:
            handle.write(token + "\n")
    except Exception:
        pass
    return False


def sweep(now: float) -> None:
    try:
        with os.scandir(STATE_DIR) as entries:
            for entry in entries:
                if not entry.name.startswith("seen-"):
                    continue
                try:
                    if now - entry.stat().st_mtime > SWEEP_AFTER_SECONDS:
                        os.unlink(entry.path)
                except OSError:
                    continue
    except OSError:
        pass


def log_receipt(row: dict) -> None:
    """Incidence, measured before anyone argues about block mode.

    Under AGENT_DO_HOME and never inside a repository: a per-machine tally of
    what agents wrote is not project history, and writing it into a checkout
    would put machine state under version control.
    """
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with RECEIPT_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
    except Exception:
        pass


# ── entry point ───────────────────────────────────────────────────────────


def run() -> None:
    started = time.perf_counter()

    try:
        input_data = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(input_data, dict):
        return

    tool_name = input_data.get("tool_name")
    if tool_name not in ("Edit", "Write", "MultiEdit"):
        return
    tool_input = input_data.get("tool_input")
    if not isinstance(tool_input, dict):
        return

    raw_path = tool_input.get("file_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return
    path = Path(raw_path)
    if not in_scope(path):
        return

    text = written_text(tool_name, tool_input)
    if not text or len(text) > MAX_SCAN_BYTES:
        return

    findings = scan(text)
    if not findings:
        return

    session_id = input_data.get("session_id")
    token = session_token(session_id, path)
    # The cooldown silences the message, not the measurement: a literal written
    # into an already-nudged file is still a literal written, and the receipt is
    # what makes incidence arguable before block mode is.
    suppressed = token is not None and already_nudged(token, session_id)

    resolve_lines(findings, path)
    resolve_ceilings(findings, text)

    display_path = path.name
    cwd = input_data.get("cwd")
    if isinstance(cwd, str) and cwd:
        try:
            display_path = path.resolve().relative_to(Path(cwd).resolve()).as_posix()
        except Exception:
            display_path = path.name

    event = input_data.get("hook_event_name")
    if not isinstance(event, str) or not event:
        event = "PostToolUse"

    if not suppressed:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": event,
                        "additionalContext": render(display_path, findings),
                    }
                }
            )
        )

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    log_receipt(
        {
            "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "session": session_id if isinstance(session_id, str) else None,
            "tool": tool_name,
            "file": path.as_posix(),
            "mode": "suppressed" if suppressed else "nudge",
            "elapsed_ms": elapsed_ms,
            "findings": [
                {
                    "slot": item["slot"],
                    "value": item["value"],
                    "tier": item["tier"],
                    "kind": item["kind"],
                    "line": item.get("line"),
                    "ceiling_key": item.get("ceiling_key"),
                    "ceiling_value": item.get("ceiling_value"),
                    "ceiling_status": item.get("ceiling_status"),
                }
                for item in sorted(findings, key=rank)
            ],
        }
    )
    sweep(time.time())


def main() -> None:
    if disabled():
        sys.exit(0)
    try:
        run()
    except Exception:
        # A nudge is a convenience; the edit already happened. Nothing this
        # hook can fail at is worth a nonzero exit.
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
