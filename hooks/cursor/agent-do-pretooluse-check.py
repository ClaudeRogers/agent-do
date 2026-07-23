#!/usr/bin/env python3
"""Cursor preToolUse hook adapter for agent-do shell nudges."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cursor_compat import (  # noqa: E402
    claude_to_cursor_output,
    normalize_cwd,
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

    tool_name = raw.get("tool_name")
    if tool_name not in {"Shell", "Bash"}:
        sys.exit(0)

    tool_input = raw.get("tool_input")
    if not isinstance(tool_input, dict):
        sys.exit(0)

    command = tool_input.get("command", "")
    if not isinstance(command, str) or not command.strip():
        sys.exit(0)

    repo = resolve_repo()
    if repo is None:
        sys.exit(0)

    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": normalize_cwd(raw),
    }

    claude_output = run_canonical_hook(repo, "hooks/claude/agent-do-pretooluse-check.py", payload)
    cursor_output = claude_to_cursor_output(claude_output)
    if not cursor_output:
        sys.exit(0)

    print(json.dumps(cursor_output))
    sys.exit(0)


if __name__ == "__main__":
    main()
