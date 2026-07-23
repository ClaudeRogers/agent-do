#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


def make_exec(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run(cmd: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, env=env, text=True, capture_output=True, check=False)


def fake_env(tmp: Path) -> dict[str, str]:
    fake_bin = tmp / "bin"
    fake_bin.mkdir()
    make_exec(
        fake_bin / "gh",
        """#!/usr/bin/env python3
import json
import sys

args = sys.argv[1:]
if args[:2] == ["pr", "list"]:
    print(json.dumps([{
        "number": 7,
        "title": "Feature",
        "headRefName": "feature",
        "baseRefName": "main",
        "url": "https://github.com/owner/repo/pull/7",
        "headRepositoryOwner": {"login": "owner"},
        "headRepository": {"name": "repo"},
        "mergeStateStatus": "BEHIND",
    }]))
    sys.exit(0)
if args[:2] == ["pr", "update-branch"]:
    sys.exit(0)
print("unexpected gh args: " + " ".join(args), file=sys.stderr)
sys.exit(2)
""",
    )
    home = tmp / "home"
    home.mkdir()
    return {
        **os.environ,
        "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
        "AGENT_DO_HOME": str(home),
        "HOME": str(home),
    }


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_sync_requires_live() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        env = fake_env(Path(tmpdir))
        result = run([str(AGENT_DO), "gh", "sync", "--author", "owner"], env=env)
        require(result.returncode == 1, f"expected live denial, got {result.returncode}: {result.stdout} {result.stderr}")
        payload = json.loads(result.stdout)
        require(payload["action_required"] == "LIVE_APPROVAL_REQUIRED", f"bad payload: {payload}")
        require(payload["required_scope"] == "any", f"bad scope: {payload}")
        require(payload["app"] == "GitHub", f"bad app: {payload}")
        require(payload["reason"] == "gh:sync", f"bad reason: {payload}")


def test_sync_dry_run_does_not_require_live() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        env = fake_env(Path(tmpdir))
        result = run([str(AGENT_DO), "gh", "sync", "--author", "owner", "--dry-run"], env=env)
        require(result.returncode == 0, f"dry-run should pass without live: {result.stdout} {result.stderr}")
        require("dry-run" in result.stdout, f"expected dry-run output: {result.stdout}")


def main() -> int:
    tests = [test_sync_requires_live, test_sync_dry_run_does_not_require_live]
    failures = []
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failures.append(f"  FAIL {test.__name__}: {exc}")
        except Exception as exc:
            failures.append(f"  ERROR {test.__name__}: {type(exc).__name__}: {exc}")
    if failures:
        for failure in failures:
            print(failure)
        return 1
    print(f"gh sync tests passed ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
