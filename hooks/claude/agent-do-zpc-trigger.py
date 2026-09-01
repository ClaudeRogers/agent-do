#!/usr/bin/env python3
"""Deliver a machine-wide zpc lesson at the moment its trigger names.

Registered three times (install.sh CLAUDE_SETTINGS_SPECS): UserPromptSubmit,
PreToolUse for Bash, PostToolUse for Edit|Write. Each firing is one question
to `agent-do zpc inject --trigger <kind> <value>` — the prompt just typed, the
command about to run, the file just edited — and the answer, when there is
one, is the lesson whose `when` matched, rendered with its rule and its why.
Nothing matched is nothing said: no output, exit 0.

A lesson fires once per session per kind. Context persists inside a session,
and the second delivery of the same rule is the one that teaches an agent to
skim the section. Advisory only: never a decision, never a block.
"""

# Hooks run under whatever python3 the harness resolves, which on macOS is the
# system 3.9 where `X | None` in an annotation raises at import time.
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HOOK_START = time.monotonic()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

try:
    from telemetry import record_hook_decision, record_nudge_event
except ModuleNotFoundError:
    record_hook_decision = None
    record_nudge_event = None

# install.sh registers this hook with a 5-second timeout, after which Claude
# Code kills it and drops its output. The subprocess gets what is left of that
# window minus the time already spent here, and a margin to print in.
REGISTERED_HOOK_TIMEOUT_SECONDS = 5.0
PRINT_MARGIN_SECONDS = 0.3

EVENT_KINDS = {
    "UserPromptSubmit": "prompt",
    "PreToolUse": "command",
    "PostToolUse": "path",
}


def resolve_agent_do_binary() -> str | None:
    env_root = os.environ.get("AGENT_DO_REPO")
    if env_root:
        candidate = Path(env_root).expanduser() / "agent-do"
        if candidate.exists():
            return str(candidate)
    repo_candidate = Path(__file__).resolve().parents[2] / "agent-do"
    if repo_candidate.exists():
        return str(repo_candidate)
    breadcrumb = Path.home() / ".agent-do" / "install-path"
    if breadcrumb.is_file():
        try:
            candidate = Path(breadcrumb.read_text().strip()).expanduser() / "agent-do"
            if candidate.exists():
                return str(candidate)
        except OSError:
            pass
    return None


def value_for(kind: str, input_data: dict) -> str:
    if kind == "prompt":
        return (input_data.get("prompt") or "").strip()
    tool_input = input_data.get("tool_input") or {}
    if kind == "command":
        if input_data.get("tool_name") != "Bash":
            return ""
        return (tool_input.get("command") or "").strip()
    if kind == "path":
        if input_data.get("tool_name") not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            return ""
        return (tool_input.get("file_path") or tool_input.get("notebook_path") or "").strip()
    return ""


def session_key(input_data: dict) -> str:
    return (
        input_data.get("session_id")
        or os.environ.get("CLAUDE_SESSION_ID")
        or os.environ.get("AGENT_DO_COORD_SESSION")
        or "unknown"
    )


def seen_path(session: str) -> Path:
    home = Path(os.environ.get("AGENT_DO_HOME") or (Path.home() / ".agent-do"))
    return home / "zpc" / ".state" / "trigger-seen" / f"{session}.json"


def load_seen(session: str) -> dict:
    path = seen_path(session)
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_seen(session: str, seen: dict) -> None:
    path = seen_path(session)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(seen))
    except OSError:
        pass


def run_bounded(cmd: list[str], cwd: str | None, timeout: float) -> str:
    import signal

    if timeout <= 0:
        return ""
    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except OSError:
        return ""
    try:
        out, _ = proc.communicate(timeout=timeout)
        return out or ""
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        return ""


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)
    if not isinstance(input_data, dict):
        sys.exit(0)

    event = input_data.get("hook_event_name") or ""
    kind = EVENT_KINDS.get(event)
    if not kind:
        sys.exit(0)
    value = value_for(kind, input_data)
    if not value:
        sys.exit(0)

    agent_do = resolve_agent_do_binary()
    if not agent_do:
        sys.exit(0)

    cwd = input_data.get("cwd") or os.getcwd()
    env = dict(os.environ)
    env["AGENT_DO_ZPC_SOURCE"] = "hook"
    budget = REGISTERED_HOOK_TIMEOUT_SECONDS - (time.monotonic() - HOOK_START) - PRINT_MARGIN_SECONDS
    raw = run_bounded(
        [agent_do, "zpc", "inject", "--trigger", kind, value, "--json"], cwd, budget
    )
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    payload = payload.get("result", payload) if isinstance(payload, dict) else {}
    fired = [i for i in (payload.get("fired") or []) if isinstance(i, str)]
    text = payload.get("additionalContext") or ""

    session = session_key(input_data)
    seen = load_seen(session)
    already = set(seen.get(kind) or [])
    fresh = [i for i in fired if i not in already]

    if record_hook_decision is not None:
        try:
            record_hook_decision(
                event, "zpc_trigger", "emit" if fresh else "suppress",
                cwd=cwd, prompt=value, reason=(
                    "lesson_fired" if fresh
                    else ("already_delivered_this_session" if fired else "no_trigger_matched")
                ),
            )
        except Exception:
            pass

    if not fresh or not text:
        sys.exit(0)

    seen[kind] = sorted(already | set(fresh))
    save_seen(session, seen)

    if record_nudge_event is not None:
        try:
            # The trigger value (prompt / command / path) rides along through
            # telemetry's central prompt_fields policy: stable hash plus a
            # redact_text 160-char excerpt. Erik ruled 2026-08-26 that
            # debuggability outranks the residual-leak risk of redacted
            # excerpts in this local log; the earlier omission (a789605 and
            # the later prompt= drop) was agent doctrine he never ratified.
            record_nudge_event(
                f"zpc_lesson_fired_{kind}", "zpc_trigger",
                lessons=fresh, kind=kind, cwd=cwd, prompt=value,
            )
        except Exception:
            pass

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": text,
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # A lesson is a convenience; the prompt, command, or edit already
        # happened or is about to. Nothing here is worth a nonzero exit.
        sys.exit(0)
