#!/usr/bin/env python3
"""Cursor sessionStart hook adapter for agent-do."""

from __future__ import annotations

import json
import os
import secrets
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cursor_compat import (  # noqa: E402
    claude_to_cursor_output,
    normalize_cwd,
    resolve_agent_do_dir,
    resolve_repo,
    run_canonical_hook,
)


def main() -> None:
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)
    if not isinstance(raw, dict):
        sys.exit(0)

    repo = resolve_repo()
    if repo is None:
        sys.exit(0)

    payload = dict(raw)
    payload["cwd"] = normalize_cwd(raw)

    claude_output = run_canonical_hook(repo, "hooks/claude/agent-do-session-start.sh", payload)
    cursor_output = claude_to_cursor_output(claude_output)

    # Cursor can persist environment returned by sessionStart. Pin both the
    # public owner label and an independent bearer token so separate shell
    # invocations share one identity without making the label forgeable.
    env = cursor_output.setdefault("env", {})
    inherited_id = os.environ.get("MANNA_SESSION_ID")
    inherited_token = os.environ.get("MANNA_SESSION_TOKEN")
    identity_is_complete = bool(inherited_id and inherited_token)
    session_id = (
        inherited_id
        if identity_is_complete
        else raw.get("session_id") or raw.get("conversation_id") or f"cursor-{uuid.uuid4()}"
    )
    env["AGENT_DO_COORD_SESSION"] = os.environ.get("AGENT_DO_COORD_SESSION") or str(session_id)
    env["MANNA_SESSION_ID"] = str(session_id)
    env["MANNA_SESSION_TOKEN"] = inherited_token if identity_is_complete else secrets.token_hex(32)

    agent_do_dir = resolve_agent_do_dir()
    if agent_do_dir:
        current_path = os.environ.get("PATH", "")
        if agent_do_dir not in current_path.split(os.pathsep):
            env["PATH"] = f"{agent_do_dir}{os.pathsep}{current_path}"

    if cursor_output:
        print(json.dumps(cursor_output))

    sys.exit(0)


if __name__ == "__main__":
    main()
