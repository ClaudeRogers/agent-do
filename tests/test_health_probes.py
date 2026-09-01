#!/usr/bin/env python3
"""Health checks must stay bounded and fail closed on broken prerequisites."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_executable(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        shim_dir = Path(tmp) / "bin"
        shim_dir.mkdir()
        # A docker whose daemon never answers: `docker info` blocks forever.
        fake_docker = shim_dir / "docker"
        write_executable(
            fake_docker,
            "#!/bin/bash\nif [ \"$1\" = info ]; then sleep 600; fi\nexit 0\n",
        )

        env = os.environ.copy()
        env["PATH"] = f"{shim_dir}:{env['PATH']}"
        env["AGENT_DO_HOME"] = str(Path(tmp) / "home")

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

    with tempfile.TemporaryDirectory() as tmp:
        isolated_root = Path(tmp) / "agent-do"
        isolated_bin = isolated_root / "bin"
        isolated_lib = isolated_root / "lib"
        isolated_tools = isolated_root / "tools"
        isolated_bin.mkdir(parents=True)
        isolated_lib.mkdir()
        isolated_tools.mkdir()

        shutil.copy2(ROOT / "bin" / "health", isolated_bin / "health")
        shutil.copy2(ROOT / "lib" / "bash-runtime.sh", isolated_lib / "bash-runtime.sh")
        write_executable(
            isolated_tools / "agent-demo",
            "#!/usr/bin/env bash\n"
            "if [ \"$1\" = \"--help\" ]; then\n"
            "  echo 'agent-demo - health fixture'\n"
            "  exit 0\n"
            "fi\n"
            "exit 0\n",
        )
        write_executable(
            isolated_tools / "agent-creds",
            "#!/usr/bin/env bash\n"
            "echo 'credential backend exploded' >&2\n"
            "exit 70\n",
        )

        isolated_env = os.environ.copy()
        isolated_env["AGENT_DO_HOME"] = str(isolated_root / "state")
        failed_probe = subprocess.run(
            ["bash", str(isolated_bin / "health"), "demo"],
            cwd=isolated_root,
            env=isolated_env,
            text=True,
            capture_output=True,
            check=False,
        )
        require(failed_probe.returncode != 0, "credential probe failure should make health fail")
        require("MISS  demo" in failed_probe.stdout, f"probe failure was not surfaced: {failed_probe.stdout}")
        require(
            "credential probe failed (exit 70; non-JSON output)" in failed_probe.stdout,
            f"missing credential failure detail: {failed_probe.stdout}",
        )

    print("health probe tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
