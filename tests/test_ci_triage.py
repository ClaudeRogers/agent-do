#!/usr/bin/env python3
"""Offline tests for lib/ci_triage.py - classification, parsing, redaction.

Fixture-based: no network, no gh. Fixtures mirror real failures observed on
the Versova fleet 2026-07-01..14 (the same runs the classifier was derived
from), so these are regression tests for the deterministic handlers.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from ci_triage import (  # noqa: E402
    DEP_BRANCH,
    classify,
    parse_updater_errors,
    redact,
    signature,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_fixture(**kw):
    base = {
        "workflowName": "CI",
        "headBranch": "main",
        "event": "pull_request",
        "displayTitle": "t",
        "conclusion": "failure",
        "url": "https://example.invalid/run",
        "jobs": [{
            "name": "Verify",
            "conclusion": "failure",
            "steps": [{"name": "Install dependencies", "conclusion": "failure"}],
        }],
    }
    base.update(kw)
    return base


NO_LOG = lambda repo, run_id: ""  # noqa: E731

# Mirrors `gh run view --log-failed` line shape: Job\tStep\t<ts> <content>.
UPDATER_LOG = "\n".join([
    "Dependabot\tRun Dependabot\t2026-07-13T14:51:34.9569857Z |                Dependencies failed to update                |",
    "Dependabot\tRun Dependabot\t2026-07-13T14:51:34.9571086Z | Dependency     | Error Type                     | Details |",
    "Dependabot\tRun Dependabot\t2026-07-13T14:51:34.9573591Z | @types/node    | unknown_error                  | null    |",
    "Dependabot\tRun Dependabot\t2026-07-13T14:51:34.9574833Z | tailwind-merge | dependency_file_not_resolvable | {       |",
    'Dependabot\tRun Dependabot\t2026-07-13T14:51:34.9576099Z |                |                                |   "message": "Error (ERR_PNPM_BROKEN_METADATA_JSON) while resolving \\"pnpm-lock.yaml\\" file." |',
])


def test_c2_updater_table_parse():
    errors, hints = parse_updater_errors(UPDATER_LOG)
    deps = {(e["dependency"], e["error_type"]) for e in errors}
    require(("@types/node", "unknown_error") in deps, "missing @types/node row: %r" % deps)
    require(("tailwind-merge", "dependency_file_not_resolvable") in deps,
            "missing tailwind-merge row: %r" % deps)
    require(len(errors) == 2, "header/detail rows leaked into errors: %r" % errors)
    require("transient:ERR_PNPM_BROKEN_METADATA_JSON" in hints, "missing pnpm hint: %r" % hints)


def test_c2_classification():
    run = run_fixture(workflowName="Dependabot Updates", event="dynamic",
                      jobs=[{"name": "Dependabot", "conclusion": "failure",
                             "steps": [{"name": "Run Dependabot", "conclusion": "failure"}]}])
    cls, facts, conf = classify("o/r", run, "1", log_fetcher=lambda r, i: UPDATER_LOG)
    require(cls == "C2-dependabot-updater", "got %s" % cls)
    require(conf == "high", "got %s" % conf)
    require(len(facts["updater_errors"]) == 2, "errors not attached")


def test_c1_branch_parse():
    for branch, eco, dep, ver in [
        ("dependabot/npm_and_yarn/web/main/mui/material-9.2.0", "npm_and_yarn", "material", "9.2.0"),
        ("dependabot/npm_and_yarn/main/zod-4.4.3", "npm_and_yarn", "zod", "4.4.3"),
        ("dependabot/github_actions/actions/checkout-7.0.0", "github_actions", "checkout", "7.0.0"),
    ]:
        m = DEP_BRANCH.match(branch)
        require(m is not None, "no match: %s" % branch)
        require(m.groups() == (eco, dep, ver), "%s -> %r" % (branch, m.groups()))
    cls, facts, _ = classify("o/r", run_fixture(headBranch="dependabot/npm_and_yarn/main/zod-4.4.3"),
                             "1", log_fetcher=NO_LOG)
    require(cls == "C1-dependabot-pr", "got %s" % cls)
    require(facts["dependency"] == "zod", "got %r" % facts.get("dependency"))


def test_c3_c4():
    cls, _, _ = classify("o/r", run_fixture(workflowName="iOS App Store Build", event="push"),
                         "1", log_fetcher=NO_LOG)
    require(cls == "C3-trunk-release", "push event: got %s" % cls)
    cls, _, _ = classify("o/r", run_fixture(headBranch="ci/lint-delta-gate"), "1", log_fetcher=NO_LOG)
    require(cls == "C4-gate-authoring", "ci/ branch: got %s" % cls)


def test_c5_low_confidence_and_redaction():
    leaky = "\n".join([
        "Build\tstep\t2026-07-14T00:00:00.0Z export GITHUB_TOKEN=ghp_" + "a" * 30,
        "Build\tstep\t2026-07-14T00:00:00.0Z api_key: super-secret-value",
        "Build\tstep\t2026-07-14T00:00:00.0Z jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    ])
    cls, facts, conf = classify("o/r", run_fixture(headBranch="feat/thing"), "1",
                                log_fetcher=lambda r, i: leaky)
    require(cls == "C5-unknown" and conf == "low", "got %s/%s" % (cls, conf))
    tail = facts["log_tail"]
    require("ghp_" not in tail, "GitHub token leaked")
    require("super-secret-value" not in tail, "api_key value leaked")
    require("eyJhbGciOiJIUzI1NiJ9" not in tail, "JWT leaked")
    require("[REDACTED]" in tail, "redaction marker absent")


def test_signature_stability():
    _, facts, _ = classify("o/r", run_fixture(headBranch="dependabot/npm_and_yarn/main/zod-4.4.3"),
                           "1", log_fetcher=NO_LOG)
    a, b = signature("o/r", facts), signature("o/r", facts)
    require(a == b and len(a) == 12, "signature unstable or wrong length: %s/%s" % (a, b))
    facts2 = dict(facts, dependency="tiptap")
    require(signature("o/r", facts2) != a, "signature ignores dependency")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print("  ok  %s" % t.__name__)
        except AssertionError as e:
            failures += 1
            print("  FAIL %s: %s" % (t.__name__, e))
    print("%d/%d passed" % (len(tests) - failures, len(tests)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
