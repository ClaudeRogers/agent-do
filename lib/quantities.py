"""The quantity authority — looked-up ceilings and measured totals.

Agents invent numbers because measuring costs a tool call and guessing costs
nothing. This module inverts that trade: one place to read a published number
from, one place to measure a present one, so typing a literal is the more
expensive option rather than the cheaper one.

Two kinds of quantity, and the distinction is load-bearing:

  LOOKED_UP  a static, versioned ceiling somebody else published — a model's
             max_tokens, an API's page limit. Answered out of models.yaml
             together with the record it came from, so a caller can cite it.
  MEASURED   how many exist right now — lines in a file, entries in a
             directory, rows behind a read command. Computed on demand and
             never cached into a literal, because it is true only now.

Both refuse rather than approximate. An unknown key names itself and fails; a
census that cannot count exactly says why and fails. There is no default, no
fallback zero, and no silent estimate anywhere in this module.

KEY GRAMMAR
    <namespace>.<subject>.<quantity>          anthropic.claude-sonnet-5.max_tokens

Keys are parsed from the ends, never by splitting on every dot: subjects carry
dots of their own (openai.gpt-5.6-sol.max_tokens), while namespace and quantity
never do. First segment is the namespace, last is the quantity, everything
between is the subject.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from difflib import get_close_matches
from pathlib import Path
from typing import Any

from models import load_config, models_file

# One bounded read probe. Reuses the budget `agent-do harness contracts audit`
# already applies to a single declared read verb rather than inventing a second
# timeout policy for the same shape of call; both read it from here.
READ_PROBE_TIMEOUT_SECONDS = 15

# Payload keys that mean "this response is one page of a larger set". A census
# over any of them cannot be exact, so it refuses. Sourced from the pagination
# vocabularies actually in play across agent-do's surfaces: Anthropic and the
# Files/Models APIs return `has_more`; the Managed Agents endpoints return
# `next_page`; cursor APIs (GitHub, Notion, Slack) return a next-cursor token.
TRUNCATION_MARKERS_TRUE = ("has_more", "truncated", "is_truncated")
TRUNCATION_MARKERS_PRESENT = ("next_page", "next_cursor", "next_page_token", "next_offset")


class QuantityError(RuntimeError):
    """A caller error: unknown key, unreadable target, unusable command."""


class CensusRefusal(RuntimeError):
    """The count cannot be made exactly, so no count is returned.

    Distinct from QuantityError because the caller did nothing wrong — the
    world is simply not countable through this path right now. Consumers map
    it to a different exit code so "refused" never reads as "crashed".
    """

    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


# ── looked-up quantities ──────────────────────────────────────────────────


def parse_key(key: str) -> tuple[str, str, str]:
    """Split a dotted authority key into (namespace, subject, quantity)."""
    text = (key or "").strip()
    if not text:
        raise QuantityError("quantity key cannot be empty")
    parts = text.split(".")
    if len(parts) < 3:
        raise QuantityError(
            f"malformed quantity key: {text}\n"
            "  expected <namespace>.<subject>.<quantity>, e.g. anthropic.claude-sonnet-5.max_tokens"
        )
    return parts[0], ".".join(parts[1:-1]), parts[-1]


def _is_number(value: Any) -> bool:
    # bool is a subclass of int; a flag is not a quantity.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _model_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Every numeric field on every model record, as addressable entries.

    Model records are rewritten wholesale by `agent-do models doctor`, so they
    carry no per-field provenance of their own; the record itself is the
    citation and the doctor is the maintainer.
    """
    records = config.get("models")
    if not isinstance(records, dict):
        return []
    entries: list[dict[str, Any]] = []
    for record_key, record in sorted(records.items()):
        if not isinstance(record, dict):
            continue
        namespace = str(record.get("provider") or "").strip()
        subject = str(record_key)
        if "/" in record_key:
            prefix, _, remainder = record_key.partition("/")
            subject = remainder
            namespace = namespace or prefix
        if not namespace:
            # Unaddressable rather than guessed: without a provider there is no
            # namespace, and inventing one would make the key a lie.
            continue
        for field, value in sorted(record.items()):
            if not _is_number(value):
                continue
            entries.append(
                {
                    "key": f"{namespace}.{subject}.{field}",
                    "value": value,
                    "unit": "tokens" if field.endswith("_tokens") else None,
                    "kind": "looked_up",
                    "provenance": {
                        "file": _models_file_label(),
                        "record": f"models.{record_key}",
                        "field": field,
                        "maintained_by": "agent-do models doctor (refreshed from the provider's /v1/models response)",
                    },
                }
            )
    return entries


def _limit_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Hand-entered ceilings that are not per-model (API page limits, quotas).

    Unlike model records these are never machine-rewritten, so each one carries
    its own `source` and `verified` date in data — not in a comment, because
    `models doctor --fix` round-trips the file through a YAML dumper and
    comments do not survive that.
    """
    records = config.get("limits")
    if not isinstance(records, dict):
        return []
    entries: list[dict[str, Any]] = []
    for record_key, record in sorted(records.items()):
        if not isinstance(record, dict):
            continue
        namespace = str(record.get("provider") or "").strip()
        subject = str(record_key)
        if "/" in record_key:
            prefix, _, remainder = record_key.partition("/")
            subject = remainder
            namespace = namespace or prefix
        if not namespace:
            continue
        for field, declared in sorted(record.items()):
            if not isinstance(declared, dict) or "value" not in declared:
                continue
            value = declared["value"]
            if not _is_number(value):
                raise QuantityError(
                    f"limits.{record_key}.{field}.value is not a number: {value!r}"
                )
            provenance = {
                "file": _models_file_label(),
                "record": f"limits.{record_key}",
                "field": field,
                "maintained_by": "hand-entered",
            }
            for extra in ("source", "verified"):
                if declared.get(extra):
                    provenance[extra] = str(declared[extra])
            entries.append(
                {
                    "key": f"{namespace}.{subject}.{field}",
                    "value": value,
                    "unit": str(declared["unit"]) if declared.get("unit") else None,
                    "kind": "looked_up",
                    "provenance": provenance,
                }
            )
    return entries


def _models_file_label() -> str:
    path = models_file()
    try:
        return path.relative_to(Path(__file__).resolve().parent.parent).as_posix()
    except ValueError:
        return str(path)


def authority_entries(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every addressable quantity, sorted by key."""
    config = config if config is not None else load_config()
    entries = _model_entries(config) + _limit_entries(config)
    return sorted(entries, key=lambda item: item["key"])


def lookup(key: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve one authority key to its value plus the record it came from.

    Raises QuantityError naming the key when it is unknown. It never returns a
    default and never returns zero — an absent number is not the number zero,
    and a caller that gets one instead of an error will ship it.
    """
    parse_key(key)  # reject malformed keys before searching for them
    entries = authority_entries(config)
    by_key = {item["key"]: item for item in entries}
    found = by_key.get(key)
    if found is not None:
        return found

    # Nearest-match hints use difflib's own defaults (n=3, cutoff=0.6). They are
    # stdlib defaults, not thresholds tuned here, and they affect only the help
    # text of a failure — never a returned value.
    suggestions = get_close_matches(key, list(by_key))
    lines = [f"unknown quantity key: {key}"]
    if suggestions:
        lines.append(f"  did you mean: {', '.join(suggestions)}")
    lines.append(f"  {len(by_key)} keys are declared in {_models_file_label()}")
    lines.append("  list them with: agent-do harness quantity keys")
    raise QuantityError("\n".join(lines))


# ── measured quantities ───────────────────────────────────────────────────


def census_lines(target: str) -> dict[str, Any]:
    """Count lines in a file, exactly as `wc -l` does.

    `wc -l` counts newline bytes, so a final line with no terminator is not
    counted. Rather than silently choosing a different definition, this reports
    the same number and flags the unterminated tail as its own field, letting
    the caller add one if their definition of "line" differs.
    """
    path = Path(target).expanduser()
    if not path.exists():
        raise QuantityError(f"cannot count lines: no such path: {target}")
    if path.is_dir():
        raise CensusRefusal(
            "not_a_file",
            f"{target} is a directory; count its entries with `census entries` instead",
        )
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise QuantityError(f"cannot read {target}: {exc}") from exc
    return {
        "target": target,
        "total": data.count(b"\n"),
        "unit": "lines",
        "kind": "measured",
        "exact": True,
        "method": "newline-count",
        "method_detail": (
            "counted 0x0A bytes over the whole file, matching `wc -l`; "
            "a final unterminated line is reported separately, never silently added"
        ),
        "final_line_unterminated": bool(data) and not data.endswith(b"\n"),
        "bytes_scanned": len(data),
    }


def census_entries(target: str, glob: str | None = None, recursive: bool = False) -> dict[str, Any]:
    """Count directory entries, optionally matching a glob."""
    path = Path(target).expanduser()
    if not path.exists():
        raise QuantityError(f"cannot count entries: no such path: {target}")
    if not path.is_dir():
        raise CensusRefusal(
            "not_a_directory",
            f"{target} is not a directory; count its lines with `census lines` instead",
        )
    pattern = glob or "*"
    try:
        matches = list(path.rglob(pattern) if recursive else path.glob(pattern))
    except OSError as exc:
        raise QuantityError(f"cannot scan {target}: {exc}") from exc
    return {
        "target": target,
        "total": len(matches),
        "unit": "entries",
        "kind": "measured",
        "exact": True,
        "method": "dir-scan",
        "method_detail": (
            f"enumerated every entry matching {pattern!r} "
            f"{'recursively' if recursive else 'at the top level only'}; "
            "files and directories both count"
        ),
        "glob": pattern,
        "recursive": recursive,
    }


def _read_only_verb(tool: str, argv: list[str]) -> str:
    """Confirm the target command is a declared read, and return the verb.

    Census is a read-only, parallel-safe verb, so it will not reach a write
    verb to get its count. Safety comes from the contracts already declared in
    the registry rather than from a list maintained here — and an undeclared
    verb is refused, because unknown safety is not the same as safe.
    """
    from registry import get_tool_contracts, load_registry

    tools = load_registry().get("tools") or {}
    info = tools.get(tool)
    if not isinstance(info, dict):
        raise QuantityError(f"unknown tool in --via: {tool}")
    contracts = get_tool_contracts(info)
    if not contracts:
        raise QuantityError(f"{tool} declares no contracts; census cannot confirm it is read-only")

    words = [arg for arg in argv if not arg.startswith("-")]
    # Longest declared verb wins, so "contracts validate" beats "contracts".
    candidates = [" ".join(words[:count]) for count in range(len(words), 0, -1)]
    for candidate in candidates:
        beats = {beat for beat, verbs in contracts.items() if candidate in verbs}
        if not beats:
            continue
        if beats <= {"snapshot", "verify"}:
            return candidate
        raise QuantityError(
            f"refusing to run a write verb: `{tool} {candidate}` declares {sorted(beats)}\n"
            "  census only reads; give it a snapshot or verify verb"
        )
    raise QuantityError(
        f"`{tool} {' '.join(words) or '<no verb>'}` matches no declared contract verb; "
        "census cannot confirm it is read-only"
    )


def _resolve_path(payload: Any, dotted: str) -> Any:
    """Walk an explicit --path. A path that is not there is a caller error.

    The line between the two failure kinds is what the caller asked for: a
    request that could not be executed as written raises QuantityError, while
    a request that ran but yielded no certifiable count raises CensusRefusal.
    """
    current = payload
    for segment in dotted.split("."):
        if not isinstance(current, dict) or segment not in current:
            available = ", ".join(sorted(current)) if isinstance(current, dict) else "(not an object)"
            raise QuantityError(f"no value at --path {dotted}; available here: {available}")
        current = current[segment]
    return current


def _truncation_reason(payload: Any, counted: int) -> tuple[str, str] | None:
    """Detect that the payload is one page of a larger set."""
    if not isinstance(payload, dict):
        return None
    for marker in TRUNCATION_MARKERS_TRUE:
        if payload.get(marker) is True:
            return ("paginated", f"payload declares {marker}=true: more results exist beyond this page")
    for marker in TRUNCATION_MARKERS_PRESENT:
        if payload.get(marker) not in (None, "", False):
            return ("paginated", f"payload carries {marker}: more results exist beyond this page")
    declared_limit = payload.get("limit")
    if _is_number(declared_limit) and counted == declared_limit:
        # At the page boundary an exact count and a capped one are the same
        # number. Refusing here is the whole point: a cap that hides the answer
        # is worse than no count at all.
        return (
            "page_boundary",
            f"payload declares limit={declared_limit} and returned exactly that many rows; "
            "a full page cannot be distinguished from a truncated one",
        )
    return None


def census_rows(
    via: str,
    path: str | None = None,
    timeout: int = READ_PROBE_TIMEOUT_SECONDS,
    runner: Any = None,
) -> dict[str, Any]:
    """Count the rows a read command returns right now.

    `via` is an agent-do invocation without the leading `agent-do`, run through
    argv with no shell, and only after the registry confirms the verb is a
    declared read.
    """
    raw = (via or "").strip()
    if not raw:
        raise QuantityError("--via requires an agent-do command, e.g. --via \"manna list --json\"")
    shell_chars = set("|;&<>$`\n")
    if shell_chars & set(raw):
        raise QuantityError(
            "--via runs through argv, never a shell; remove pipes, redirects, and substitutions"
        )
    try:
        argv = shlex.split(raw)
    except ValueError as exc:
        raise QuantityError(f"cannot parse --via: {exc}") from exc
    if not argv:
        raise QuantityError("--via parsed to no command")

    tool = argv[0]
    verb = _read_only_verb(tool, argv[1:])

    if runner is None:
        runner = _default_runner
    result = runner(argv, timeout)
    stdout = result.get("stdout") or ""
    if result.get("returncode") != 0:
        message = (result.get("stderr") or stdout).strip().splitlines()
        raise CensusRefusal(
            "command_failed",
            f"`agent-do {raw}` exited {result.get('returncode')}: "
            f"{message[0] if message else 'no output'}",
        )
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise CensusRefusal(
            "not_json",
            f"`agent-do {raw}` did not return JSON ({exc}); add its --json flag so rows can be counted",
        ) from exc

    if path:
        rows = _resolve_path(payload, path)
        source = path
    elif isinstance(payload, list):
        rows, source = payload, "$"
    elif isinstance(payload, dict):
        arrays = sorted(key for key, value in payload.items() if isinstance(value, list))
        if not arrays:
            raise CensusRefusal("no_array", "payload contains no array to count; name one with --path")
        if len(arrays) > 1:
            raise CensusRefusal(
                "ambiguous_array",
                f"payload contains {len(arrays)} arrays ({', '.join(arrays)}); name one with --path",
            )
        rows, source = payload[arrays[0]], arrays[0]
    else:
        raise CensusRefusal("no_array", "payload is a scalar; there is nothing to count")

    if not isinstance(rows, list):
        raise QuantityError(f"value at {source} is {type(rows).__name__}, not an array; nothing to count")

    counted = len(rows)
    truncated = _truncation_reason(payload, counted)
    if truncated:
        raise CensusRefusal(truncated[0], truncated[1])

    return {
        "target": f"agent-do {raw}",
        "total": counted,
        "unit": "rows",
        "kind": "measured",
        "exact": True,
        "method": "json-array",
        "method_detail": (
            f"ran the declared read verb `{tool} {verb}` through argv, parsed its JSON, "
            f"and counted every element of {source} after confirming no pagination marker was present"
        ),
        "verb": f"{tool} {verb}",
        "json_path": source,
    }


def _default_runner(argv: list[str], timeout: int) -> dict[str, Any]:
    """Run one declared read verb through argv — no shell, no repo writes.

    Telemetry is suppressed the same way the harness suppresses it for its own
    probes: this invocation is a measurement, not a routing decision the
    suggestion model should learn from.
    """
    repo_root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["AGENT_DO_TELEMETRY_SUPPRESS"] = "1"
    try:
        completed = subprocess.run(
            [str(repo_root / "agent-do"), *argv],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise CensusRefusal(
            "timed_out",
            f"`agent-do {' '.join(argv)}` did not finish within {timeout}s; nothing was counted",
        ) from exc
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
