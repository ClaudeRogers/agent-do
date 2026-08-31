#!/usr/bin/env python3
"""Offline tests for lib/ci_triage.py - classification, parsing, redaction.

Fixture-based: no network, no gh. Fixtures mirror real failures observed on
the Versova fleet 2026-07-01..14 (the same runs the classifier was derived
from), so these are regression tests for the deterministic handlers.
"""

from __future__ import annotations

import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from ci_triage import (  # noqa: E402
    DEP_BRANCH,
    classify,
    parse_updater_errors,
    redact,
    render_markdown,
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

    cls, facts, conf = classify("o/r", run, "1", log_fetcher=lambda r, i: None)
    require(cls == "C2-dependabot-updater" and conf == "low", "missing logs stayed confident")
    require(facts["log_available"] is False, "missing logs not represented")


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


def test_c3_staging_push():
    """A failed staging push is trunk-class, not silent C5.

    Fleets that promote through a staging branch need staging breaks to
    page; before this change they classified C5-unknown (facts-only)."""
    cls, facts, conf = classify("o/r", run_fixture(event="push", headBranch="staging",
                                                    defaultBranch="main"),
                                "1", log_fetcher=NO_LOG)
    require(cls == "C3-trunk-release", "staging push stayed silent: got %s" % cls)
    require(facts.get("trunk") == "staging",
            "staging trunk marker missing: %r" % facts.get("trunk"))
    require(conf == "medium-high", "staging push confidence drifted: %s" % conf)
    cls, facts, _ = classify("o/r", run_fixture(event="push", headBranch="main",
                                                 defaultBranch="main"), "1", log_fetcher=NO_LOG)
    require(cls == "C3-trunk-release", "default-branch push regressed: %s" % cls)
    require("trunk" not in facts,
            "default-branch push grew a trunk marker: %r" % facts.get("trunk"))


def test_c3_c4():
    cls, _, _ = classify("o/r", run_fixture(workflowName="iOS App Store Build", event="push",
                                             headBranch="main", defaultBranch="main"),
                         "1", log_fetcher=NO_LOG)
    require(cls == "C3-trunk-release", "push event: got %s" % cls)
    # GATE_AUTHORS is env-configured (AGENT_DO_CI_GATE_AUTHORS) and empty by
    # default; patch the module set to exercise the C4 path.
    import ci_triage as _ct
    _saved = _ct.GATE_AUTHORS
    try:
        _ct.GATE_AUTHORS = {"gate-author"}
        cls, _, _ = classify("o/r", run_fixture(headBranch="ci/lint-delta-gate",
                                                 actor="gate-author"), "1", log_fetcher=NO_LOG)
        require(cls == "C4-gate-authoring", "ci/ branch: got %s" % cls)
        cls, _, _ = classify("o/r", run_fixture(headBranch="ci/not-a-gate", actor="someone-else"),
                             "1", log_fetcher=NO_LOG)
        require(cls == "C5-unknown", "untrusted ci/ actor was suppressed: %s" % cls)
    finally:
        _ct.GATE_AUTHORS = _saved
    # Default (no env var): ci/** branches classify as C5, never C4.
    cls, _, _ = classify("o/r", run_fixture(headBranch="ci/lint-delta-gate",
                                             actor="gate-author"), "1", log_fetcher=NO_LOG)
    require(cls == "C5-unknown", "empty GATE_AUTHORS still produced C4: %s" % cls)
    cls, _, _ = classify("o/r", run_fixture(event="push", headBranch="feature/x",
                                             defaultBranch="main"), "1", log_fetcher=NO_LOG)
    require(cls == "C5-unknown", "feature push misclassified as trunk: %s" % cls)


def test_c5_low_confidence_and_redaction():
    leaky = "\n".join([
        "Build\tstep\t2026-07-14T00:00:00.0Z export GITHUB_TOKEN=ghp_" + "a" * 30,
        "Build\tstep\t2026-07-14T00:00:00.0Z api_key: super-secret-value",
        "Build\tstep\t2026-07-14T00:00:00.0Z Authorization: Bearer opaque-service-token",
        "Build\tstep\t2026-07-14T00:00:00.0Z jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        "Build\tstep\t2026-07-14T00:00:00.0Z \x1b]0;unsafe\x07 ``` </details>",
    ])
    cls, facts, conf = classify("o/r", run_fixture(headBranch="feat/thing"), "1",
                                log_fetcher=lambda r, i: leaky)
    require(cls == "C5-unknown" and conf == "low", "got %s/%s" % (cls, conf))
    tail = facts["log_tail"]
    require("ghp_" not in tail, "GitHub token leaked")
    require("super-secret-value" not in tail, "api_key value leaked")
    require("opaque-service-token" not in tail, "Bearer token leaked")
    require("eyJhbGciOiJIUzI1NiJ9" not in tail, "JWT leaked")
    require("\x1b" not in tail and "\x07" not in tail, "terminal control sequence leaked")
    require("[REDACTED]" in tail, "redaction marker absent")
    rendered = render_markdown("o/r", "1", cls, facts, conf, signature("o/r", facts))
    require("````\n" in rendered, "log-controlled fence was not lengthened")
    hostile_facts = dict(facts, workflow="CI\n</details> `unsafe`", failed=[{
        "job": "</details>", "steps": ["``` injected"],
    }])
    hostile = render_markdown("o/r", "1", cls, hostile_facts, conf, signature("o/r", hostile_facts))
    require("CI &lt;/details&gt; \\`unsafe\\`" in hostile, "workflow metadata injected Markdown")
    require("**Failed:** &lt;/details&gt; -> \\`\\`\\` injected" in hostile,
            "job/step metadata injected Markdown")


def test_signature_stability():
    _, facts, _ = classify("o/r", run_fixture(headBranch="dependabot/npm_and_yarn/main/zod-4.4.3"),
                           "1", log_fetcher=NO_LOG)
    a, b = signature("o/r", facts), signature("o/r", facts)
    require(a == b and len(a) == 12, "signature unstable or wrong length: %s/%s" % (a, b))
    facts2 = dict(facts, dependency="tiptap")
    require(signature("o/r", facts2) != a, "signature ignores dependency")

    c2a = dict(facts, dependency="", branch="main",
               updater_errors=[{"dependency": "a", "error_type": "unknown_error"}], hints=[])
    c2b = dict(c2a, updater_errors=[{"dependency": "b", "error_type": "unknown_error"}])
    require(signature("o/r", c2a) != signature("o/r", c2b),
            "signature ignores C2 updater errors")


def test_cli_post_gate():
    proc = subprocess.run(
        [str(ROOT / "tools" / "agent-ci"), "triage", "123", "--repo", "o/r", "--post"],
        capture_output=True, text=True,
    )
    require(proc.returncode != 0, "--post unexpectedly succeeded")
    require("--post is not implemented in Phase 0" in proc.stdout,
            "wrapper did not forward explicit post gate: %r/%r" % (proc.stdout, proc.stderr))


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
