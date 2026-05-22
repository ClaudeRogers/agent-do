#!/usr/bin/env python3

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_gh import cli


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_pr_create_dispatch_and_args() -> None:
    calls: list[tuple[list[str], str | None]] = []

    def fake_run_gh(args: list[str], *, input_text: str | None = None, timeout: int = 60) -> str:  # noqa: ARG001
        calls.append((args, input_text))
        return "https://github.com/ovachiever/agent-do/pull/99\n"

    with patch("agent_gh.groups.pr.run_gh", side_effect=fake_run_gh):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main([
                "pr",
                "create",
                "--title",
                "Fix bug",
                "--body",
                "Body text",
                "--base",
                "main",
                "--head",
                "feature/fix-bug",
                "--draft",
                "--label",
                "bug",
                "--assignee",
                "alice",
                "--reviewer",
                "bob",
                "--project",
                "Roadmap",
                "--milestone",
                "v1",
            ])

    require(rc == 0, f"expected exit 0, got {rc}")
    require(len(calls) == 1, f"expected one gh invocation, got {calls}")
    require(
        calls[0][0] == [
            "pr",
            "create",
            "--title",
            "Fix bug",
            "--body",
            "Body text",
            "--base",
            "main",
            "--head",
            "feature/fix-bug",
            "--draft",
            "--label",
            "bug",
            "--assignee",
            "alice",
            "--reviewer",
            "bob",
            "--project",
            "Roadmap",
            "--milestone",
            "v1",
        ],
        f"unexpected gh args: {calls[0][0]}",
    )
    require("Created PR:" in buf.getvalue(), f"unexpected stdout: {buf.getvalue()!r}")
    require("pull/99" in buf.getvalue(), f"unexpected stdout: {buf.getvalue()!r}")


def test_pr_create_dry_run_skips_gh() -> None:
    with patch("agent_gh.groups.pr.run_gh") as run_mock:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(["pr", "create", "--title", "Preview only", "--dry-run"])

    require(rc == 0, f"expected exit 0, got {rc}")
    require(run_mock.call_count == 0, f"dry-run should not call gh: {run_mock.call_args_list}")
    require("[dry-run] would run: gh pr create --title Preview only" in buf.getvalue(), buf.getvalue())


def test_pr_checkout_dry_run_skips_gh() -> None:
    with patch("agent_gh.groups.pr.run_gh") as run_mock:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(["checkout", "ovachiever/agent-do#42", "--dry-run"])

    require(rc == 0, f"expected exit 0, got {rc}")
    require(run_mock.call_count == 0, f"dry-run should not call gh: {run_mock.call_args_list}")
    require(
        "[dry-run] would run: gh pr checkout 42 --repo ovachiever/agent-do" in buf.getvalue(),
        buf.getvalue(),
    )


def test_pr_create_json_envelope() -> None:
    with patch("agent_gh.groups.pr.run_gh", return_value="https://github.com/ovachiever/agent-do/pull/100\n"):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(["pr", "create", "--title", "JSON output", "--json"])

    require(rc == 0, f"expected exit 0, got {rc}")
    text = buf.getvalue()
    require('"tool": "gh"' in text, f"missing tool field: {text!r}")
    require('"command": "pr create"' in text, f"missing command field: {text!r}")
    require('"url": "https://github.com/ovachiever/agent-do/pull/100"' in text, f"missing url: {text!r}")


def main() -> int:
    tests = [
        test_pr_create_dispatch_and_args,
        test_pr_create_dry_run_skips_gh,
        test_pr_checkout_dry_run_skips_gh,
        test_pr_create_json_envelope,
    ]
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
    print(f"pr create unit tests passed ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
