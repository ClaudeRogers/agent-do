#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_gh.refs import PrRef
from agent_gh.groups import cr as cr_mod
from agent_gh.groups import pr as pr_mod


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _ref() -> PrRef:
    return PrRef(repo="ovachiever/agent-do", number="14", original="ovachiever/agent-do#14")


def test_coderabbit_feedback_filters_rate_limit_and_trims() -> None:
    payload = {
        "comments": [
            {
                "author": {"login": "coderabbitai"},
                "body": "<!-- This is an auto-generated comment: summarize by coderabbit.ai -->\n"
                "<!-- This is an auto-generated comment: rate limited by coderabbit.ai -->\n\n"
                "> [!WARNING]\n> ## Rate limit exceeded\n> \n> Please wait before requesting another review.\n",
            },
            {
                "author": {"login": "coderabbitai"},
                "body": "Intro text\n\n**Actionable comments posted: 2**\n\n- comment one\n- comment two\n",
                "path": "tools/agent-jira/jira_ops.py",
                "line": 123,
            },
            {"author": {"login": "someoneelse"}, "body": "ignore me"},
        ],
        "reviews": [
            {
                "author": {"login": "coderabbitai"},
                "body": "Preamble\n\n**Actionable comments posted: 1**\n\n- review comment\n",
                "state": "COMMENTED",
            }
        ],
    }

    with patch("agent_gh.groups.cr.gh_json", return_value=payload):
        items = cr_mod._coderabbit_feedback_items(_ref())

    require(len(items) == 2, f"expected 2 feedback items, got {items}")
    require(items[0]["kind"] == "coderabbit_comment", f"bad kind: {items[0]}")
    require(items[0]["body"].startswith("**Actionable comments posted: 2**"), f"bad excerpt: {items[0]['body']}")
    require("Rate limit exceeded" not in items[0]["body"], f"rate-limit noise leaked into body: {items[0]['body']}")
    require(items[1]["kind"] == "coderabbit_review", f"bad kind: {items[1]}")
    require(items[1]["body"].startswith("**Actionable comments posted: 1**"), f"bad review excerpt: {items[1]['body']}")


def test_review_items_combines_threads_and_coderabbit_feedback() -> None:
    thread = {
        "id": "thread-1",
        "resolved": False,
        "path": "tools/agent-gh/agent_gh/groups/cr.py",
        "line": 42,
        "comments": [{"author": "reviewer", "body": "Please handle this edge case."}],
    }
    feedback = [
        {
            "kind": "coderabbit_comment",
            "author": "coderabbitai",
            "body": "**Actionable comments posted: 1**\n\n- handle this edge case\n",
            "path": "tools/agent-gh/agent_gh/groups/cr.py",
            "line": 42,
        }
    ]

    with (
        patch("agent_gh.groups.cr.pr_threads", return_value=[thread]),
        patch("agent_gh.groups.cr._coderabbit_feedback_items", return_value=feedback),
    ):
        items = cr_mod._review_items(_ref())

    require(len(items) == 2, f"expected 2 items, got {items}")
    require(items[0]["kind"] == "thread", f"expected thread first, got {items[0]}")
    require(items[1]["kind"] == "coderabbit_comment", f"expected coderabbit item second, got {items[1]}")
    prompt = cr_mod._format_review_items_for_prompt(items)
    require("CodeRabbit comment" in prompt, f"expected coderabbit label in prompt: {prompt}")
    require("Please handle this edge case." in prompt, f"expected thread body in prompt: {prompt}")


def test_pr_repo_slug_prefers_base_repository() -> None:
    pr = {
        "headRepositoryOwner": {"login": "ClaudeRogers"},
        "headRepository": {"name": "agent-do"},
        "url": "https://github.com/ovachiever/agent-do/pull/9",
    }
    require(cr_mod._pr_repo_slug(pr) == "ovachiever/agent-do", f"expected base repo slug, got {cr_mod._pr_repo_slug(pr)}")


def test_pr_detail_extracts_head_repo_slug() -> None:
    payload = {
        "number": 9,
        "title": "feat(gh): expand agent-gh",
        "state": "OPEN",
        "headRefName": "feat/agent-gh-expand",
        "headRepositoryOwner": {"login": "ClaudeRogers"},
        "headRepository": {"name": "agent-do"},
    }
    detail = pr_mod.normalize_pr_detail(PrRef(repo="ovachiever/agent-do", number="9", original="ovachiever/agent-do#9"), payload)
    require(detail["head_repo"] == "ClaudeRogers/agent-do", f"expected fork repo slug, got {detail['head_repo']}")


def test_claude_invocation_uses_constrained_permissions() -> None:
    with patch("agent_gh.groups.cr.subprocess.run", return_value=CompletedProcess(args=[], returncode=0)) as run:
        ok = cr_mod._address_with_claude(
            "/tmp/repo",
            [{"kind": "thread", "path": "a.py", "line": 1, "comments": [{"author": "erik", "body": "fix"}]}],
            {"title": "PR", "headRefName": "feature", "baseRefName": "main", "url": "https://github.com/o/r/pull/1"},
            "o/r",
            "diff --git a/a.py b/a.py",
            "claude",
            False,
            silent=True,
        )

    require(ok is True, "expected claude invocation to succeed")
    argv = run.call_args.args[0]
    require("--bare" in argv, f"expected --bare: {argv}")
    require("--permission-mode" in argv and "acceptEdits" in argv, f"expected constrained permission mode: {argv}")
    require("--allowedTools" in argv, f"expected allowed tools: {argv}")
    joined = " ".join(argv)
    require("Bash(git push" not in joined, f"nested claude must not be allowed to push: {argv}")


def main() -> int:
    tests = [
        test_coderabbit_feedback_filters_rate_limit_and_trims,
        test_review_items_combines_threads_and_coderabbit_feedback,
        test_pr_repo_slug_prefers_base_repository,
        test_pr_detail_extracts_head_repo_slug,
        test_claude_invocation_uses_constrained_permissions,
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
    print(f"cr unit tests passed ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
