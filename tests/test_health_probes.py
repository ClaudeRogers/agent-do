#!/usr/bin/env python3
"""bin/health must never hang on a dead external daemon (docker, kubectl)."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        shim_dir = Path(tmp) / "bin"
        shim_dir.mkdir()
        # A docker whose daemon never answers: `docker info` blocks forever.
        fake_docker = shim_dir / "docker"
        fake_docker.write_text("#!/bin/bash\nif [ \"$1\" = info ]; then sleep 600; fi\nexit 0\n")
        fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{shim_dir}:{env['PATH']}"
        env.setdefault("AGENT_DO_HOME", str(ROOT / ".dev" / "test-home"))

        start = time.monotonic()
        result = subprocess.run(
            ["bash", str(ROOT / "bin" / "health"), "docker"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=120,
        )
        elapsed = time.monotonic() - start
        require(
            elapsed < 60,
            f"health hung on a dead docker daemon for {elapsed:.0f}s — probe timeout missing",
        )
        require(result.returncode == 0, f"health exited nonzero: {result.stderr}")
        require(
            "not responding" in result.stdout or "not running" in result.stdout,
            f"dead daemon should surface as WARN, got: {result.stdout}",
        )
    print("health probe tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
