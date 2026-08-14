#!/usr/bin/env python3
"""The public launcher must enforce and propagate GNU Bash 4.4+."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"
SYSTEM_BASH = Path("/bin/bash")
SPARSE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def bash_is_supported(path: Path) -> bool:
    result = subprocess.run(
        [
            str(path),
            "-c",
            "(( BASH_VERSINFO[0] > 4 || "
            "(BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] >= 4) ))",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    runtime_temp = tempfile.TemporaryDirectory()
    sparse_env = os.environ.copy()
    sparse_env.pop("AGENT_DO_BASH", None)
    sparse_env["AGENT_DO_HOME"] = str(Path(runtime_temp.name) / "home")
    sparse_env["PATH"] = SPARSE_PATH
    sparse_env["AGENT_DO_RUNTIME_TEST_KEY"] = "present"

    recovered = subprocess.run(
        [str(AGENT_DO), "creds", "check", "AGENT_DO_RUNTIME_TEST_KEY"],
        cwd=ROOT,
        env=sparse_env,
        text=True,
        capture_output=True,
        check=False,
    )
    require(
        recovered.returncode == 0,
        "sparse-PATH launch did not recover a supported Bash:\n"
        f"stdout={recovered.stdout}\nstderr={recovered.stderr}",
    )
    require("status   ready" in recovered.stdout, f"unexpected credential result: {recovered.stdout}")
    require("invalid option" not in recovered.stderr, f"child tool used an old Bash: {recovered.stderr}")
    require("unbound variable" not in recovered.stderr, f"child tool used an old Bash: {recovered.stderr}")
    runtime_bin = Path(sparse_env["AGENT_DO_HOME"]) / "runtime" / "bin"
    require(
        [entry.name for entry in runtime_bin.iterdir()] == ["bash"],
        f"runtime shim must contain only bash: {list(runtime_bin.iterdir())}",
    )
    require((runtime_bin / "bash").is_symlink(), "runtime bash entry must be a symlink")
    initial_shim_target = os.readlink(runtime_bin / "bash")

    nested_env = sparse_env.copy()
    nested_env.pop("AGENT_DO_BASH", None)
    nested_env["PATH"] = f"{runtime_bin}:{SPARSE_PATH}"
    nested = subprocess.run(
        [str(AGENT_DO), "--help"],
        cwd=ROOT,
        env=nested_env,
        text=True,
        capture_output=True,
        check=False,
    )
    require(nested.returncode == 0, f"launch through runtime shim failed: {nested.stderr}")
    require(
        os.readlink(runtime_bin / "bash") == initial_shim_target,
        "launch through runtime shim rewrote it to a recursive target",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        fake_bin = Path(tmpdir) / "bin"
        fake_bin.mkdir()
        fake_python = fake_bin / "python3"
        fake_python.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  */bin/suggest) printf 'fixture-python\\n' ;;\n"
            "esac\n"
            "exit 0\n"
        )
        fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

        precedence_env = sparse_env.copy()
        precedence_env["PATH"] = f"{fake_bin}:{SPARSE_PATH}"
        precedence = subprocess.run(
            [str(AGENT_DO), "find", "runtime"],
            cwd=ROOT,
            env=precedence_env,
            text=True,
            capture_output=True,
            check=False,
        )
        require(precedence.returncode == 0, f"PATH precedence fixture failed: {precedence.stderr}")
        require(
            precedence.stdout.strip() == "fixture-python",
            f"runtime selection shadowed the caller's Python shim: {precedence.stdout}",
        )

    if SYSTEM_BASH.is_file() and not bash_is_supported(SYSTEM_BASH):
        invalid_env = sparse_env.copy()
        invalid_env["AGENT_DO_BASH"] = str(SYSTEM_BASH)
        rejected = subprocess.run(
            [str(SYSTEM_BASH), str(AGENT_DO), "--help"],
            cwd=ROOT,
            env=invalid_env,
            text=True,
            capture_output=True,
            check=False,
        )
        require(rejected.returncode != 0, "unsupported AGENT_DO_BASH override should fail closed")
        require(
            "requires GNU Bash 4.4 or newer" in rejected.stderr,
            f"missing actionable runtime error: {rejected.stderr}",
        )

    runtime_temp.cleanup()
    print("bash runtime tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
