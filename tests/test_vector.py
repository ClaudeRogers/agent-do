#!/usr/bin/env python3
"""Focused coverage for agent-vector."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    help_result = subprocess.run(
        ["./agent-do", "vector", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    require(help_result.returncode == 0, help_result.stderr)
    require("agent-vector" in help_result.stdout, help_result.stdout)
    require("snapshot <slug>" in help_result.stdout, help_result.stdout)

    with tempfile.TemporaryDirectory() as tmp:
        fake_curl = Path(tmp) / "curl"
        fake_curl.write_text(
            """#!/usr/bin/env bash
printf '%s\n' '[{"slug":"vms-io","name":"VMS.io","phase":"build","pulse":"hot","owner":"efritsch@versova.com"}]'
""",
        )
        fake_curl.chmod(fake_curl.stat().st_mode | stat.S_IXUSR)
        env = {
            **os.environ,
            "PATH": f"{tmp}:{os.environ['PATH']}",
            "VECTOR_SUPABASE_URL": "https://example.supabase.co",
            "VECTOR_SUPABASE_SERVICE_KEY": "service-key",
        }
        result = subprocess.run(
            ["./agent-do", "vector", "ls"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        require(result.returncode == 0, result.stderr)
        require("vms-io" in result.stdout, result.stdout)
        require("VMS.io" in result.stdout, result.stdout)

    print("vector tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
