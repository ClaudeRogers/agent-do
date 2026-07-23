#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_gh.transport import GhError
from agent_gh.triage import release_notes as notes_mod


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_notes_between_filters_merged_prs_since_tag() -> None:
    repo = "ovachiever/agent-do"
    since_tag = "v1.0.0"
    pr_old = {
        "number": 1,
        "title": "Old bug fix",
        "labels": [{"name": "bug"}],
        "mergedAt": "2026-01-09T12:00:00Z",
        "url": "https://github.com/ovachiever/agent-do/pull/1",
    }
    pr_new = {
        "number": 2,
        "title": "Fresh bug fix",
        "labels": [{"name": "bug"}],
        "mergedAt": "2026-01-11T12:00:00Z",
        "url": "https://github.com/ovachiever/agent-do/pull/2",
    }

    def fake_gh_json(args: list[str], *, input_text: str | None = None):  # noqa: ARG001
        if "releases/generate-notes" in " ".join(args):
            raise GhError("generate-notes failed")
        if args[:2] == ["api", f"/repos/{repo}/git/ref/tags/{since_tag}"]:
            return {"object": {"type": "commit", "sha": "tag-sha"}}
        if args[:2] == ["api", f"/repos/{repo}/git/commits/tag-sha"]:
            return {"committer": {"date": "2026-01-10T00:00:00Z"}}
        if args[:2] == ["api", f"/repos/{repo}"]:
            return {"default_branch": "trunk"}
        if args[:2] == ["search", "prs"]:
            require("--base" in args and "trunk" in args, f"default branch not used: {args}")
            return [pr_old, pr_new]
        raise AssertionError(f"unexpected gh_json call: {args}")

    with patch("agent_gh.triage.release_notes.gh_json", side_effect=fake_gh_json):
        result = notes_mod.notes_between(repo, since_tag)

    data = result["data"]
    require(data["source"] == "pr-label-grouping", f"unexpected source: {data}")
    require(data["sections"]["Bug Fixes"] == ["Fresh bug fix (#2)"], f"unexpected sections: {data}")

def test_notes_between_refuses_unbounded_fallback() -> None:
    repo = "ovachiever/agent-do"

    def fake_gh_json(args: list[str], *, input_text: str | None = None):  # noqa: ARG001
        if "releases/generate-notes" in " ".join(args):
            raise GhError("generate-notes failed")
        if args[:2] == ["api", f"/repos/{repo}"]:
            return {"default_branch": "main"}
        if args[:2] == ["search", "prs"]:
            return [{"number": 1, "title": "Unbounded", "labels": [], "mergedAt": "2026-01-11T00:00:00Z"}]
        if args[:2] == ["api", f"/repos/{repo}/git/ref/tags/v-missing"]:
            raise GhError("tag lookup failed")
        raise AssertionError(f"unexpected gh_json call: {args}")

    with patch("agent_gh.triage.release_notes.gh_json", side_effect=fake_gh_json):
        try:
            notes_mod.notes_between(repo, "v-missing")
        except GhError as exc:
            require("refusing to return unbounded release notes" in str(exc), f"bad error: {exc}")
        else:
            raise AssertionError("expected GhError for unbounded fallback")


def main() -> int:
    tests = [
        test_notes_between_filters_merged_prs_since_tag,
        test_notes_between_refuses_unbounded_fallback,
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
    print(f"release notes unit tests passed ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
