#!/usr/bin/env python3
"""Cursor sessionStart hook adapter for agent-do."""

from __future__ import annotations

import json
import os
import sys
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

    # Cursor can persist environment returned by sessionStart. Use the stable
    # conversation id as the same host-owned derivation input Claude uses, so
    # manna re-derives the private proof under the machine-local key after a
    # process restart. A random bearer token died with the old process and
    # wedged its live claims (mn-ba8db6). Explicit id + token pins still win.
    env = cursor_output.setdefault("env", {})
    inherited_id = os.environ.get("MANNA_SESSION_ID")
    inherited_token = os.environ.get("MANNA_SESSION_TOKEN")
    identity_is_complete = bool(inherited_id and inherited_token)
    host_session = raw.get("conversation_id") or raw.get("session_id")
    if not isinstance(host_session, str) or not host_session.strip():
        host_session = None

    coord_session = os.environ.get("AGENT_DO_COORD_SESSION") or (
        inherited_id if identity_is_complete else host_session
    )
    if coord_session:
        env["AGENT_DO_COORD_SESSION"] = str(coord_session)

    if identity_is_complete:
        env["MANNA_SESSION_ID"] = inherited_id
        env["MANNA_SESSION_TOKEN"] = inherited_token
    else:
        # Empty values neutralize either half of a stale explicit pair. Manna
        # treats empty as unset and falls through to the derived host identity.
        if inherited_id is not None:
            env["MANNA_SESSION_ID"] = ""
        if inherited_token is not None:
            env["MANNA_SESSION_TOKEN"] = ""
        if host_session:
            env["CLAUDE_SESSION_ID"] = host_session

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
