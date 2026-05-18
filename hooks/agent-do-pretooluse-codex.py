#!/usr/bin/env python3
"""Codex-compatible PreToolUse wrapper.

Codex currently ignores Claude-style PreToolUse additionalContext payloads.
Run the shared checker in Codex mode so telemetry and safety decisions stay on
the same code path while unsupported nudge output remains suppressed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    script = Path(__file__).with_name("agent-do-pretooluse-check.py")
    env = os.environ.copy()
    env["AGENT_DO_HOOK_RUNTIME"] = "codex"
    result = subprocess.run(
        [sys.executable, str(script)],
        input=sys.stdin.read(),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.stdout:
        # Defensive: the shared checker should suppress Codex additionalContext.
        # If it ever emits another supported payload, pass it through.
        print(result.stdout, end="")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
