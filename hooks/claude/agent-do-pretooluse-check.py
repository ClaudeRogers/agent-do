#!/usr/bin/env python3
"""
PreToolUse hook: NUDGE about agent-do when raw CLI commands are detected.
Non-blocking — adds context reminder but lets the command through.
Part of the agent-do hook trinity (nudge mode).

To switch to BLOCKING mode, change the output from:
    "additionalContext": nudge
to:
    "permissionDecision": "deny",
    "reason": nudge
"""

import json
import os
import sys
import re
from pathlib import Path
from urllib.parse import urlparse

# File lives at <repo>/hooks/claude/agent-do-pretooluse-check.py, so the repo
# root is two parents up and lib/ is its sibling.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

try:
    from registry import load_registry, find_raw_cli_equivalent, get_tool_readiness
except ModuleNotFoundError:
    load_registry = None
    find_raw_cli_equivalent = None
    get_tool_readiness = None

try:
    from telemetry import record_hook_decision, record_nudge_event
except ModuleNotFoundError:
    record_hook_decision = None
    record_nudge_event = None

# Patterns that have agent-do equivalents — grouped by tool
AGENT_DO_PATTERNS = {
    # === Vercel ===
    r'\bvercel\b': ('vercel', 'agent-do vercel'),
    r'\bnpx\s+vercel\b': ('vercel', 'agent-do vercel'),
    r'\bcurl\b.*\bapi\.vercel\.com\b': ('vercel', 'agent-do vercel'),

    # === Render ===
    r'\brender\s+(services|deploys|deploy)\b': ('render', 'agent-do render'),
    r'\bcurl\b.*\bapi\.render\.com\b': ('render', 'agent-do render'),

    # === Supabase ===
    r'\bsupabase\b': ('supabase', 'agent-do supabase'),
    r'\bnpx\s+supabase\b': ('supabase', 'agent-do supabase'),
    r'\bcurl\b.*\bsupabase\.(co|com|io)\b': ('supabase', 'agent-do supabase'),

    # === Browser automation ===
    r'\bnpx\s+playwright\b': ('browse', 'agent-do browse'),
    r'\bplaywright\s+(test|codegen|install|show-report)\b': ('browse', 'agent-do browse'),
    r'\bpuppeteer\b': ('browse', 'agent-do browse'),
    r'\bselenium\b': ('browse', 'agent-do browse'),

    # === iOS Simulator ===
    r'\bxcrun\s+simctl\b': ('ios', 'agent-do ios'),
    r'\bsimctl\b': ('ios', 'agent-do ios'),

    # === Android Emulator ===
    r'\badb\s+(shell|install|uninstall|push|pull|logcat|devices)': ('android', 'agent-do android'),
    r'\bemulator\s': ('android', 'agent-do android'),

    # === Desktop GUI ===
    r'\bosascript\b': ('macos', 'agent-do macos'),
    r'\bautomator\b': ('macos', 'agent-do macos'),

    # === Google Cloud ===
    r'\bgcloud\s+(auth|projects|iam|secrets|run|functions|compute)\b': ('gcp', 'agent-do gcp'),
    r'\bcurl\b.*\bgoogleapis\.com\b': ('gcp', 'agent-do gcp'),

    # === Docker ===
    r'\bdocker\s+(ps|logs|exec|run|start|stop|compose)\b': ('docker', 'agent-do docker'),

    # === Kubernetes ===
    r'\bkubectl\s': ('k8s', 'agent-do k8s'),

    # === SSH ===
    r'\bssh\s+\S+@': ('ssh', 'agent-do ssh'),
    r'\bscp\s': ('ssh', 'agent-do ssh'),

    # === Database ===
    r'\bpsql\s': ('db', 'agent-do db'),
    r'\bmysql\s': ('db', 'agent-do db'),

    # === Cloud ===
    r'\baws\s+(s3|ec2|lambda|iam)\b': ('cloud', 'agent-do cloud'),
    r'\baz\s+(vm|storage|webapp)\b': ('cloud', 'agent-do cloud'),

    # === Image ===
    r'\b(convert|mogrify|identify)\s.*\.(png|jpg|jpeg|gif|webp)': ('image', 'agent-do image'),
    r'\bffmpeg\b.*\.(png|jpg|jpeg|gif)': ('image', 'agent-do image'),

    # === Video ===
    r'\bffmpeg\b.*\.(mp4|mkv|avi|mov|webm)': ('video', 'agent-do video'),

    # === Audio ===
    r'\bffmpeg\b.*\.(mp3|wav|ogg|flac|m4a)': ('audio', 'agent-do audio'),
    r'\bwhisper\b': ('audio', 'agent-do audio'),
}

DOCS_FETCH_PATTERN = re.compile(
    r"\bcurl\b.*\b(llms(?:-full)?\.txt|docs?|documentation|reference|raw\.githubusercontent\.com|github\.com/.+/(?:blob|raw)/)",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+")

# Skip these entirely — no nudge needed
SKIP_PATTERNS = [
    r'(^|/)agent-do\b',
    r'(^|/)agent-(browse|browser|tui|ios|android|macos|manna|render|vercel|supabase|gcp|zpc)',
    r'^(ls|cat|head|tail|wc|grep|rg|find|which|pwd|cd|echo|printf)\b',
    r'^(mkdir|rm|cp|mv|touch|chmod|chown|ln|stat|file|diff)\b',
    r'^(git|npm|yarn|pnpm|pip|python|node|ruby|cargo|go|make|cmake|just)\b',
    r'^(brew|apt|yum|dnf|pacman)\b',
    r'^(jq|yq|sed|awk|sort|uniq|tee|xargs|tr|cut|paste)\b',
    r'^(curl\s.*localhost|curl\s.*127\.0\.0\.1|curl\s.*\[::1\])',
    r'--help\s*$',
    r'--version\s*$',
]


# Codex now supports `hookSpecificOutput.additionalContext` on PreToolUse
# (May 2026 hooks release). Previous versions of this hook suppressed output
# when AGENT_DO_HOOK_RUNTIME=codex because Codex rejected the field; that
# suppression is now obsolete. The hook emits the nudge regardless of
# runtime. The `is_codex_runtime` helper is preserved for any downstream
# callers that still want to branch on runtime for other reasons.
def is_codex_runtime() -> bool:
    runtime = os.environ.get("AGENT_DO_HOOK_RUNTIME", "").strip().lower()
    if runtime == "codex":
        return True
    if runtime in {"claude", "test"}:
        return False
    return any(
        os.environ.get(key)
        for key in (
            "CODEX_CI",
            "CODEX_THREAD_ID",
            "CODEX_MANAGED_BY_NPM",
        )
    )


def emit_context(nudge: str) -> None:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": nudge,
        }
    }
    print(json.dumps(output))


# ---------------------------------------------------------------------------
# Session-aware nudge state
# ---------------------------------------------------------------------------
# Three behaviors layered on top of the raw pattern matchers:
#   1. Demonstration suppression — once `agent-do <tool>` (or `agent-<tool>`)
#      has been invoked in this session, suppress further nudges for that
#      tool. The agent has demonstrated it knows the tool exists; repeating
#      the hard nudge is noise.
#   2. Frequency degradation — even without a demonstration, the same tool
#      family won't get the full hard nudge over and over: first occurrence
#      is HARD, second is a FRIENDLY one-liner, third+ is silent. Per session.
#   3. Gap detection — if `agent-do <tool>` was used recently and the agent
#      now ran the raw equivalent, log a gap event. Over time these gaps are
#      the to-do list for what `agent-do <tool>` should add.
#
# State lives at ~/.agent-do/nudges/session-<sid>.json, keyed off the
# session_id from hook input. Old session files are TTL-cleaned best-effort.

import time

NUDGE_STATE_DIR = Path.home() / ".agent-do" / "nudges"
NUDGE_STATE_TTL_DAYS = 7
NUDGE_FRIENDLY_AFTER = 1   # after N hard nudges for a tool, degrade to friendly
NUDGE_SILENT_AFTER = 3     # after N total nudges for a tool, suppress entirely
GAP_WINDOW_SECONDS = 300   # raw CLI within this many seconds of agent-do = gap


def _resolve_session_id(input_data: dict) -> str:
    return (
        input_data.get("session_id")
        or os.environ.get("CLAUDE_SESSION_ID")
        or os.environ.get("CODEX_THREAD_ID")
        or "default"
    )


def _session_state_path(session_id: str) -> Path:
    NUDGE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id)[:64]
    return NUDGE_STATE_DIR / f"session-{safe}.json"


def _empty_state() -> dict:
    return {"demonstrated": {}, "nudge_counts": {}, "last_agent_do_tool": None, "gap_events": []}


def _load_session_state(session_id: str) -> dict:
    path = _session_state_path(session_id)
    if not path.exists():
        return _empty_state()
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return _empty_state()
    for key, default in _empty_state().items():
        data.setdefault(key, default)
    return data


def _save_session_state(session_id: str, state: dict) -> None:
    try:
        path = _session_state_path(session_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        os.replace(tmp, path)
    except OSError:
        pass


def _cleanup_old_sessions() -> None:
    """Sweep session files older than TTL. Best-effort; cheap to skip."""
    try:
        if not NUDGE_STATE_DIR.exists():
            return
        cutoff = time.time() - NUDGE_STATE_TTL_DAYS * 86400
        for entry in NUDGE_STATE_DIR.glob("session-*.json"):
            try:
                if entry.stat().st_mtime < cutoff:
                    entry.unlink()
            except OSError:
                pass
    except OSError:
        pass


# Match `agent-do <tool>` (dispatcher form) or bare `agent-<tool>` (direct call).
_AGENT_DO_INVOCATION_RE = re.compile(
    r"(?:^|[\s/])agent-do\s+([A-Za-z][A-Za-z0-9_-]+)|"
    r"(?:^|[\s/])agent-([A-Za-z][A-Za-z0-9_-]+)(?=\s|$)"
)


def _extract_agent_do_invocation(command: str) -> tuple[str | None, str]:
    """Return (tool, verb_or_empty) if command is an agent-do invocation."""
    match = _AGENT_DO_INVOCATION_RE.search(command)
    if not match:
        return None, ""
    tool = match.group(1) or match.group(2)
    if not tool or tool == "do":
        return None, ""
    rest = command[match.end():].lstrip()
    verb = rest.split()[0] if rest else ""
    if verb.startswith("-"):
        verb = ""
    return tool, verb


def _record_demonstration(state: dict, tool: str, verb: str) -> None:
    now = int(time.time())
    state["demonstrated"][tool] = now
    state["last_agent_do_tool"] = {"tool": tool, "verb": verb, "ts": now}


def _nudge_decision(state: dict, tool: str) -> str:
    """Return one of: hard | friendly | suppress_demonstrated | suppress_frequency."""
    if tool in state.get("demonstrated", {}):
        return "suppress_demonstrated"
    count = state.get("nudge_counts", {}).get(tool, 0)
    if count >= NUDGE_SILENT_AFTER:
        return "suppress_frequency"
    if count >= NUDGE_FRIENDLY_AFTER:
        return "friendly"
    return "hard"


def _record_nudge_emitted(state: dict, tool: str) -> None:
    state["nudge_counts"][tool] = state.get("nudge_counts", {}).get(tool, 0) + 1


def _detect_gap(state: dict, tool: str) -> bool:
    """If agent-do <tool> was invoked within the gap window, log this raw call as a gap."""
    last = state.get("last_agent_do_tool") or {}
    if last.get("tool") != tool:
        return False
    if int(time.time()) - int(last.get("ts", 0)) > GAP_WINDOW_SECONDS:
        return False
    state.setdefault("gap_events", []).append({
        "tool": tool,
        "ts": int(time.time()),
        "agent_do_verb": last.get("verb", ""),
    })
    return True


def _friendly_one_liner(replacement: str, example: str) -> str:
    return (
        f"Reminder: `{replacement}` exists for this; closest call is `{example}`. "
        "(Second occurrence this session; further nudges in this family will fall silent.)"
    )


def _gated_emit(state: dict, tool: str, *, hard_text: str, friendly_text: str,
                replacement: str, example: str, base_event: str, command: str,
                extra_tools: list[str] | None = None) -> None:
    """Decide and (maybe) emit. Records telemetry for every path."""
    decision = _nudge_decision(state, tool)
    gap = _detect_gap(state, tool)
    event = f"{base_event}_{decision}" + ("_gap" if gap else "")

    if record_hook_decision is not None:
        try:
            record_hook_decision(
                "PreToolUse", "pretool",
                "emit" if decision in ("hard", "friendly") else "suppress",
                tools=extra_tools or [tool],
                commands=[replacement, example],
                reason=event,
            )
        except Exception:
            pass
    if record_nudge_event is not None:
        try:
            record_nudge_event(
                event, "pretool",
                tool=tool,
                tools=extra_tools or [tool],
                commands=[replacement, example],
                replacement=replacement,
                command=command[:240],
            )
        except Exception:
            pass

    if decision in ("suppress_demonstrated", "suppress_frequency"):
        return
    emit_context(friendly_text if decision == "friendly" else hard_text)
    _record_nudge_emitted(state, tool)


def context_fetch_command_for_raw_docs(command: str) -> str:
    match = URL_PATTERN.search(command)
    if not match:
        return "agent-do context fetch <url>"

    url = match.group(0)
    parsed = urlparse(url)
    if re.search(r"/llms(?:-full)?\.txt$", parsed.path, re.IGNORECASE) and parsed.netloc:
        return f"agent-do context fetch-llms {parsed.netloc}"
    return f"agent-do context fetch {url}"


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    if input_data.get("tool_name") != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "").strip()
    if not command:
        sys.exit(0)

    session_id = _resolve_session_id(input_data)
    state = _load_session_state(session_id)
    # Best-effort sweep of old session files (~once per fire is fine)
    _cleanup_old_sessions()

    # Skip known-safe commands. The agent-do invocation case is special: we
    # record it as a demonstration before exiting so future raw nudges in this
    # session can be suppressed.
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            tool, verb = _extract_agent_do_invocation(command)
            if tool:
                _record_demonstration(state, tool, verb)
                _save_session_state(session_id, state)
            if record_hook_decision is not None:
                try:
                    record_hook_decision(
                        "PreToolUse", "pretool", "suppress",
                        reason="skip_pattern_demonstration" if tool else "skip_pattern",
                    )
                except Exception:
                    pass
            sys.exit(0)

    # Docs-fetch nudge — gated.
    if DOCS_FETCH_PATTERN.search(command):
        replacement = context_fetch_command_for_raw_docs(command)
        hard_nudge = (
            "HARD NUDGE: `agent-do context` is the native path for fetching and indexing docs/reference content. "
            f"Closest replacement: `{replacement}`. "
            "It stores provenance and freshness metadata so later agents can use `agent-do context retrieve ... --fresh` instead of ad hoc downloaded files. "
            "Proceeding with your raw command is allowed, but agent-do context should be the default choice here."
        )
        friendly = _friendly_one_liner("agent-do context", replacement)
        _gated_emit(
            state, "context",
            hard_text=hard_nudge,
            friendly_text=friendly,
            replacement="agent-do context",
            example=replacement,
            base_event="pretool_context_fetch_nudge",
            command=command,
        )
        _save_session_state(session_id, state)
        sys.exit(0)

    # Registry-driven hard nudge — gated.
    if load_registry is not None and find_raw_cli_equivalent is not None:
        registry = load_registry()
        shared_match = find_raw_cli_equivalent(registry, command)
        if shared_match:
            readiness = get_tool_readiness(shared_match['info']) if get_tool_readiness else {}
            replacement = shared_match['replacement']
            example = shared_match.get('example') or replacement
            reason = shared_match.get('reason') or "agent-do already exposes this workflow with structured output."
            fix = readiness.get('fix')
            note = readiness.get('note')

            hard_nudge = (
                f"HARD NUDGE: `{replacement}` is the native agent-do path for this command family. "
                f"Closest replacement: `{example}`. "
                f"{reason} "
            )
            if fix and note:
                hard_nudge += f"If setup is missing: `{fix}`. {note} "
            elif note:
                hard_nudge += f"{note} "
            hard_nudge += "Proceeding with your raw command is allowed, but agent-do should be the default choice here."

            friendly = _friendly_one_liner(replacement, example)
            _gated_emit(
                state, shared_match["tool"],
                hard_text=hard_nudge,
                friendly_text=friendly,
                replacement=replacement,
                example=example,
                base_event="pretool_hard_nudge",
                command=command,
            )
            _save_session_state(session_id, state)
            sys.exit(0)

    # Legacy friendly-reminder patterns — already mild; gate on demonstration
    # + frequency but do not degrade further (friendly_text == hard_text).
    for pattern, (tool, hint) in AGENT_DO_PATTERNS.items():
        if re.search(pattern, command, re.IGNORECASE):
            reminder = (
                f"FRIENDLY REMINDER: `{hint}` exists and is purpose-built for this. "
                f"It returns structured, snapshot-based output optimized for AI agents. "
                f"Run `{hint} --help` for commands. "
                f"Proceeding with your command is fine, but next time prefer agent-do."
            )
            _gated_emit(
                state, tool,
                hard_text=reminder,
                friendly_text=reminder,
                replacement=hint,
                example=hint,
                base_event="pretool_legacy_nudge",
                command=command,
            )
            _save_session_state(session_id, state)
            sys.exit(0)

    if record_hook_decision is not None:
        try:
            record_hook_decision("PreToolUse", "pretool", "suppress", reason="no_agent_do_match")
        except Exception:
            pass
    _save_session_state(session_id, state)
    sys.exit(0)

if __name__ == "__main__":
    main()
