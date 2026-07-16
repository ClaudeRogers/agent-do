#!/usr/bin/env python3
"""ci_triage.py - classify a failed GitHub Actions run and draft a triage summary.

Phase 0 of the CI triage unit (invoked by `agent-ci triage`). Deterministic
classification only: known failure classes render from facts extracted out of
run metadata and failed-step logs; anything unrecognized is reported honestly
as unknown/low-confidence rather than guessed at. No model calls, no posting -
dry-run output on stdout. Posting (--post) arrives with the Phase 1 watcher,
gated on the replay harness passing.

Classes:
  C1-dependabot-pr       CI failed on a dependabot/** branch (a human/PR loop exists)
  C2-dependabot-updater  The Dependabot Updates workflow itself failed (unwatched)
  C3-trunk-release       push/schedule/dispatch-event failure (trunk or release; unwatched)
  C4-gate-authoring      expected red on a ci/** gate-authoring branch
  C5-unknown             unrecognized - facts only, low confidence
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys

GH_TIMEOUT = 60
RUN_FIELDS = "databaseId,workflowName,displayTitle,event,headBranch,headSha,conclusion,createdAt,url,jobs"
LOG_TAIL_LINES = 400
GATE_AUTHORS = {"ctyrrell-versova"}


def sh(args):
    """Run a command; return (rc, stdout, stderr). Never raises on nonzero exit."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=GH_TIMEOUT)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout after %ss: %s" % (GH_TIMEOUT, " ".join(args))
    except FileNotFoundError:
        return 127, "", "command not found: %s" % args[0]


# --- redaction ---------------------------------------------------------------
# Logs are an untrusted surface and GitHub only masks *registered* secrets.
# Before any log excerpt leaves this process (stdout, JSON, or a future model
# call), strip common credential shapes. Patterns with 2 groups keep the key
# name and redact the value.
REDACT_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"rnd_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)\b(authorization)([=:]\s*(?:(?:bearer|basic)\s+)?)\S+"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password)([=:]\s*)\S+"),
]

ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


def redact(text):
    for pat in REDACT_PATTERNS:
        if pat.groups >= 2:
            text = pat.sub(lambda m: m.group(1) + m.group(2) + "[REDACTED]", text)
        else:
            text = pat.sub("[REDACTED]", text)
    text = ANSI_ESCAPE.sub("", text)
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


def markdown_inline(value):
    """Render GitHub-controlled metadata without allowing Markdown/HTML injection."""
    text = redact(str(value or "")).replace("\r", " ").replace("\n", " ")
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("`", "\\`"))


# --- fetch -------------------------------------------------------------------
def fetch_run(repo, run_id):
    rc, out, err = sh(["gh", "run", "view", str(run_id), "-R", repo, "--json", RUN_FIELDS])
    if rc != 0:
        fail("gh run view failed: %s" % (err.strip() or out.strip()))
    try:
        run = json.loads(out)
    except ValueError:
        fail("gh run view returned non-JSON output")

    rc, out, _err = sh(["gh", "api", "repos/%s/actions/runs/%s" % (repo, run_id)])
    if rc == 0:
        try:
            api_run = json.loads(out)
            run["actor"] = (api_run.get("actor") or {}).get("login") or ""
        except ValueError:
            pass

    rc, out, _err = sh(["gh", "api", "repos/%s" % repo, "--jq", ".default_branch"])
    if rc == 0:
        run["defaultBranch"] = out.strip()
    return run


def fetch_failed_log(repo, run_id):
    """Return a failed-log tail, or None when GitHub cannot provide logs."""
    rc, out, _err = sh(["gh", "run", "view", str(run_id), "-R", repo, "--log-failed"])
    if rc != 0:
        return None
    lines = out.splitlines()
    return "\n".join(lines[-LOG_TAIL_LINES:])


def failed_steps(run):
    out = []
    for job in run.get("jobs") or []:
        if job.get("conclusion") == "failure":
            steps = [s.get("name", "?") for s in job.get("steps") or []
                     if s.get("conclusion") == "failure"]
            out.append({"job": job.get("name", "?"), "steps": steps})
    return out


# --- C2: parse Dependabot's structured error table -----------------------------
# The updater prints an ASCII table:
#   | Dependency | Error Type | Error Details |
# gh --log-failed prefixes every line with "Job\tStep\t<timestamp> "; strip both
# before matching. Cell 2 is snake_case (e.g. dependency_file_not_resolvable),
# which conveniently excludes the header row.
DEP_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([a-z][a-z_]+)\s*\|")
TRANSIENT_HINTS = ("ERR_PNPM_BROKEN_METADATA_JSON", "ETIMEDOUT", "ECONNRESET", "429")
STRUCTURAL_HINTS = ("No solution found", "unsatisfiable", "requirements are unsatisfiable")


def _log_content(line):
    part = line.split("\t")[-1]
    return re.sub(r"^\d{4}-\d{2}-\d{2}T[0-9:.]+Z\s?", "", part)


def parse_updater_errors(log):
    errors, hints = [], set()
    for line in log.splitlines():
        content = _log_content(line).strip()
        m = DEP_ROW.match(content)
        if m:
            errors.append({"dependency": m.group(1), "error_type": m.group(2)})
        for h in TRANSIENT_HINTS:
            if h in content:
                hints.add("transient:" + h)
        for h in STRUCTURAL_HINTS:
            if h in content:
                hints.add("structural:" + h)
    return errors, sorted(hints)


# --- classification ------------------------------------------------------------
DEP_BRANCH = re.compile(r"^dependabot/([^/]+)/(?:.+/)?(.+?)-([0-9][^/]*)$")


def classify(repo, run, run_id, log_fetcher=None):
    """Classify one failed run. `log_fetcher(repo, run_id) -> str | None` is injectable
    so tests run offline against fixture logs."""
    if log_fetcher is None:
        log_fetcher = fetch_failed_log
    wf = run.get("workflowName") or ""
    branch = run.get("headBranch") or ""
    event = run.get("event") or ""
    facts = {
        "workflow": wf,
        "branch": branch,
        "event": event,
        "title": run.get("displayTitle") or "",
        "failed": failed_steps(run),
        "url": run.get("url") or "",
        "actor": run.get("actor") or "",
        "default_branch": run.get("defaultBranch") or "",
    }

    if wf == "Dependabot Updates":
        raw_log = log_fetcher(repo, run_id)
        facts["log_available"] = raw_log is not None
        errors, hints = parse_updater_errors(raw_log or "")
        facts["updater_errors"] = errors
        facts["hints"] = hints
        return "C2-dependabot-updater", facts, "high" if errors or hints else "low"

    if branch.startswith("ci/") and facts["actor"] in GATE_AUTHORS:
        return "C4-gate-authoring", facts, "high"

    if branch.startswith("dependabot/"):
        m = DEP_BRANCH.match(branch)
        if m:
            facts["ecosystem"], facts["dependency"], facts["version"] = m.groups()
        return "C1-dependabot-pr", facts, "high"

    if event in ("schedule", "release"):
        return "C3-trunk-release", facts, "medium-high"

    if event in ("push", "workflow_dispatch") and facts["default_branch"] and branch == facts["default_branch"]:
        return "C3-trunk-release", facts, "medium-high"

    raw_log = log_fetcher(repo, run_id)
    facts["log_available"] = raw_log is not None
    facts["log_tail"] = redact("\n".join((raw_log or "").splitlines()[-40:]))
    return "C5-unknown", facts, "low"


def signature(repo, facts):
    """Stable dedupe key: identical recurring failures share a signature."""
    fs = facts.get("failed") or []
    job = fs[0]["job"] if fs else ""
    step = fs[0]["steps"][0] if fs and fs[0].get("steps") else ""
    dep = facts.get("dependency", "")
    updater = json.dumps({
        "errors": facts.get("updater_errors") or [],
        "hints": facts.get("hints") or [],
    }, sort_keys=True, separators=(",", ":"))
    key = "|".join([
        repo, facts.get("workflow", ""), job, step,
        dep or facts.get("branch", ""), updater,
    ])
    return hashlib.sha256(key.encode()).hexdigest()[:12]


# --- rendering -------------------------------------------------------------------
ACTIONS = {
    "C1-dependabot-pr": (
        "If this bump is a deliberately-deferred major, recommend "
        "`@dependabot ignore this major version` and close; if the repo's manifests are "
        "upstream-owned, close per the no-drift policy; otherwise a minor/patch broke a "
        "real check - inspect the failed step below before merging anything."
    ),
    "C2-dependabot-updater": (
        "The updater itself failed - nobody is watching these. Explicit transient hints "
        "(broken registry metadata, timeouts, connection resets, or rate limits) may clear on the next scheduled "
        "run; structural hints (unsatisfiable resolution on upstream-owned manifests) "
        "will recur every run until the ecosystem is silenced in dependabot.yml or the "
        "conflict is fixed upstream."
    ),
    "C3-trunk-release": (
        "Trunk/release failure with no PR author in the loop - highest triage priority. "
        "Inspect the failed step; if this is an upload/notarize step, check for the "
        "known fleet-wide Apple PLA 403 block before debugging code."
    ),
    "C4-gate-authoring": (
        "Expected red: gate-authoring self-test on a ci/** branch. No action."
    ),
    "C5-unknown": (
        "Unrecognized failure class - low confidence, no proposed fix (a wrong guess "
        "is worse than none). Redacted log tail attached; triage by hand and consider "
        "adding a deterministic handler for this shape."
    ),
}


def render_markdown(repo, run_id, cls, facts, confidence, sig):
    lines = []
    lines.append("## CI triage: %s run %s" % (repo, run_id))
    lines.append("")
    lines.append("**Class:** %s · **Confidence:** %s · **Signature:** `%s`" % (cls, confidence, sig))
    lines.append("**Workflow:** %s · **Event:** %s · **Branch:** `%s`" % (
        markdown_inline(facts.get("workflow")), markdown_inline(facts.get("event")),
        markdown_inline(facts.get("branch"))))
    for f in facts.get("failed") or []:
        steps = ", ".join(markdown_inline(step) for step in (f.get("steps") or [])) \
            or "(no step-level failure recorded)"
        lines.append("**Failed:** %s -> %s" % (markdown_inline(f.get("job")), steps))
    if facts.get("dependency"):
        lines.append("**Dependency:** %s %s (%s)" % (
            markdown_inline(facts.get("dependency")), markdown_inline(facts.get("version", "?")),
            markdown_inline(facts.get("ecosystem", "?"))))
    if facts.get("updater_errors"):
        lines.append("")
        lines.append("**Updater errors:**")
        for e in facts["updater_errors"]:
            lines.append("- `%s` - %s" % (
                markdown_inline(e["dependency"]), markdown_inline(e["error_type"])))
    if facts.get("hints"):
        lines.append("**Hints:** " + ", ".join(markdown_inline(h) for h in facts["hints"]))
    lines.append("")
    lines.append("**Proposed action:** " + ACTIONS[cls])
    if facts.get("log_tail"):
        lines.append("")
        lines.append("<details><summary>Redacted log tail</summary>")
        lines.append("")
        longest = max((len(m.group(0)) for m in re.finditer(r"`+", facts["log_tail"])), default=0)
        fence = "`" * max(3, longest + 1)
        lines.append(fence)
        lines.append(facts["log_tail"])
        lines.append(fence)
        lines.append("</details>")
    lines.append("")
    lines.append("Run: %s" % facts.get("url", ""))
    return "\n".join(lines)


def fail(message):
    print(json.dumps({"success": False, "error": message}, indent=2))
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Classify a failed GitHub Actions run (dry-run triage).")
    ap.add_argument("run_id")
    ap.add_argument("--repo", required=True, help="owner/repo")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--post", action="store_true",
                    help="not implemented in Phase 0 (gated on the replay harness)")
    args = ap.parse_args()

    if args.post:
        fail("--post is not implemented in Phase 0; posting arrives with the Phase 1 "
             "watcher, gated on the replay harness passing")

    run = fetch_run(args.repo, args.run_id)
    if run.get("conclusion") != "failure":
        fail("run %s conclusion is %r, not failure - nothing to triage" %
             (args.run_id, run.get("conclusion")))

    cls, facts, confidence = classify(args.repo, run, args.run_id)
    sig = signature(args.repo, facts)
    summary = render_markdown(args.repo, args.run_id, cls, facts, confidence, sig)

    if args.as_json:
        print(json.dumps({
            "success": True,
            "repo": args.repo,
            "run_id": str(args.run_id),
            "class": cls,
            "confidence": confidence,
            "signature": sig,
            "facts": facts,
            "proposed_action": ACTIONS[cls],
            "summary": summary,
        }, indent=2))
    else:
        print(summary)


if __name__ == "__main__":
    main()
