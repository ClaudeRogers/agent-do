#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_gh.transport import GhError, run_gh


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_run_gh_wraps_oserror() -> None:
    with (
        patch("agent_gh.transport.gh_bin", return_value="gh"),
        patch("agent_gh.transport.subprocess.run", side_effect=OSError("missing gh binary")),
    ):
        raised = False
        try:
            run_gh(["version"])
        except GhError as exc:
            raised = "failed to start" in str(exc)
        require(raised, "expected GhError when gh cannot start")


def main() -> int:
    tests = [test_run_gh_wraps_oserror]
    failures = []
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failures.append(f"  FAIL {t.__name__}: {exc}")
        except Exception as exc:
            failures.append(f"  ERROR {t.__name__}: {type(exc).__name__}: {exc}")
    if failures:
        for f in failures:
            print(f)
        return 1
    print(f"transport unit tests passed ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
