#!/usr/bin/env python3
"""
PostToolUse hook (matcher: Edit|Write|MultiEdit|NotebookEdit on Claude; every
tool on Codex, filtered here): record which files THIS agent just edited.

One line per touched file, keyed by session, under
~/.agent-do/hooks/touched/. The Stop-time quality gate reads its own session's
ledger instead of `git status`, so "UI files changed without a browser
session" can only ever mean: this agent edited that file, this turn. Worktree
drift — another lane's edits, a dropped-in source document, pre-existing
untracked files — never reaches the gate through this path.

Runtime-agnostic: reads stdin, writes under AGENT_DO_HOME, imports only
lib/touch_ledger.py resolved relative to this file. Silent exit 0 on any
error; never blocks, never emits output.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    repo_lib = Path(__file__).resolve().parents[2] / "lib"
    sys.path.insert(0, str(repo_lib))
    try:
        import touch_ledger  # type: ignore
    except Exception:
        return
    # The runtime label is provenance, so it is stated or inferred, never
    # defaulted: the env var when a shim set it (hooks/codex/ does), else the
    # identity each runtime exports to its hook subprocesses, else left empty.
    runtime = os.environ.get("AGENT_DO_HOOK_RUNTIME", "")
    if not runtime:
        if os.environ.get("CODEX_THREAD_ID"):
            runtime = "codex"
        elif os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("CLAUDECODE"):
            runtime = "claude"
        elif os.environ.get("CURSOR_TRACE_ID") or os.environ.get("CURSOR_SESSION_ID"):
            runtime = "cursor"
    try:
        touch_ledger.record(payload, runtime=runtime)
    except Exception:
        return


if __name__ == "__main__":
    main()
