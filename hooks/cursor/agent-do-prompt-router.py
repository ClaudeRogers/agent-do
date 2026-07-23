#!/usr/bin/env python3
"""Cursor beforeSubmitPrompt hook adapter for agent-do."""

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

    prompt = raw.get("prompt") or raw.get("message") or ""
    if not isinstance(prompt, str) or not prompt.strip():
        sys.exit(0)

    repo = resolve_repo()
    if repo is None:
        sys.exit(0)

    payload = {
        "prompt": prompt,
        "cwd": normalize_cwd(raw),
    }

    claude_output = run_canonical_hook(repo, "hooks/claude/agent-do-prompt-router.py", payload)
    cursor_output = claude_to_cursor_output(claude_output, continue_prompt=True)
    if not cursor_output:
        sys.exit(0)

    if "continue" not in cursor_output:
        cursor_output["continue"] = True

    print(json.dumps(cursor_output))
    sys.exit(0)


if __name__ == "__main__":
    main()
