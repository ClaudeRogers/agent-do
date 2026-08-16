#!/usr/bin/env python3
"""Regression coverage for exposure-ranked re-litigation.

The model spawns are out of the gate, as with counsel: what is pinned here is
everything around them — who gets picked and why, when a pass fires at all, that
the kill switch is absolute, that a verdict is read as exactly one of three
words, and that none of it can make inject slow or make inject fail.

`AGENT_DO_ZPC_RELITIGATE=plan` is the seam: it walks the whole trigger, lock,
detach and logging path and stops short of spending a model.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"
EPISTEMICS = ROOT / "tools" / "agent-zpc" / "lib" / "epistemics.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def zpc(project: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(AGENT_DO), "zpc", *args],
        cwd=project, env=env, text=True, capture_output=True, check=False,
    )


def checked(project: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    result = zpc(project, env, *args)
    require(result.returncode == 0, f"zpc {' '.join(args)} failed: {result.stderr or result.stdout}")
    return result


def epistemics(*args: str) -> object:
    result = subprocess.run(
        ["python3", str(EPISTEMICS), *args], text=True, capture_output=True, check=False,
    )
    require(result.returncode == 0, f"epistemics {args[0]} failed: {result.stderr}")
    return json.loads(result.stdout)


def days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def wait_for(predicate, seconds: float = 20.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.2)
    return predicate()


def log_rows(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(tmp / "agent-home")

        project = tmp / "project"
        project.mkdir()
        checked(project, env, "init", "--platform", "generic")
        memory = project / ".zpc" / "memory"
        state = project / ".zpc" / ".state"
        relit_log = state / "relitigation-log.jsonl"
        lessons = memory / "lessons.jsonl"

        # 24 claims: 20 old world-state, two techniques, one recent, one destined
        # to be retracted. Only what inject repeats is eligible.
        rows = []
        for n in range(20):
            rows.append({
                "date": days_ago(200 + n), "context": "api", "problem": f"p{n}",
                "solution": f"s{n}", "takeaway": f"the service returns shape {n}",
                "tags": ["api"],
            })
        rows.append({"date": days_ago(400), "context": "style", "problem": "p",
                     "solution": "s", "takeaway": "always run the formatter first",
                     "tags": ["style"]})
        rows.append({"date": days_ago(1), "context": "api", "problem": "p",
                     "solution": "s", "takeaway": "the newest endpoint is v3",
                     "tags": ["api"]})
        with lessons.open("w") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
        checked(project, env, "retract", "--backfill")
        ids = [json.loads(line)["id"] for line in lessons.read_text().splitlines() if line.strip()]

        # ── ranking: exposure, then age, then doubt ──
        ranked = epistemics(
            "relit-rank", str(lessons), "les-", "20", "3", str(relit_log), "14"
        )
        require(len(ranked) == 3, f"top three, no more: {ranked}")
        require(
            all(item["kind"] == "world-state" for item in ranked),
            f"technique claims do not rot the way world-state does: {ranked}",
        )
        require(
            "always run the formatter first" not in json.dumps(ranked),
            "a technique must never be ranked in",
        )
        oldest = max(item["age_days"] for item in ranked)
        require(ranked[0]["age_days"] == oldest, f"age carries the ranking: {ranked}")

        # A challenge outranks age: someone already looked and doubted.
        youngest_world_state = ids[19]
        checked(project, env, "retract", "--candidate", youngest_world_state,
                "--evidence", "no such shape in the current response")
        challenged_rank = epistemics(
            "relit-rank", str(lessons), "les-", "20", "3", str(relit_log), "14"
        )
        require(
            challenged_rank[0]["id"] == youngest_world_state,
            f"a challenged claim jumps the queue: {challenged_rank}",
        )

        # A claim checked inside the cooling window is left alone, unless doubted.
        state.mkdir(exist_ok=True)
        with relit_log.open("w") as handle:
            for item in challenged_rank[1:]:
                handle.write(json.dumps({
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "run": "relit-0", "lesson": item["id"], "outcome": "supported",
                }) + "\n")
        cooled = epistemics("relit-rank", str(lessons), "les-", "20", "3", str(relit_log), "14")
        cooled_ids = {item["id"] for item in cooled}
        require(
            all(item["id"] not in cooled_ids for item in challenged_rank[1:]),
            f"a freshly checked claim waits its turn: {cooled}",
        )
        require(
            youngest_world_state in cooled_ids,
            "a challenged claim is examined even if it was checked recently",
        )

        # A retracted claim is never re-litigated: it is already withdrawn.
        checked(project, env, "retract", ids[0], "--evidence", "the endpoint was deleted in 2026-03")
        after_retraction = epistemics("relit-rank", str(lessons), "les-", "20", "3", str(relit_log), "14")
        require(
            ids[0] not in {item["id"] for item in after_retraction},
            "a retracted claim is out of the queue",
        )

        # ── the verdict is read as exactly one of three words ──
        verdict = tmp / "verdict.md"
        verdict.write_text("1. VERDICT — CONTRADICTED: src/api.ts returns shape 9, not shape 3.\n")
        parsed = epistemics("relit-classify", str(verdict))
        require(parsed["outcome"] == "contradicted" and parsed["divergent"], f"contradiction: {parsed}")

        verdict.write_text("1. VERDICT — SUPPORTED, the receipts show the same shape.\n")
        require(not epistemics("relit-classify", str(verdict))["divergent"], "agreement files nothing")

        verdict.write_text("1. VERDICT — UNSUPPORTED: no receipt speaks to this claim.\n")
        silent = epistemics("relit-classify", str(verdict))
        require(silent["outcome"] == "unsupported", f"silence is its own outcome: {silent}")
        require(not silent["divergent"], "silence in the receipts is not divergence")

        require(epistemics("relit-classify", str(tmp / "nope.md"))["outcome"] == "unreadable",
                "a missing verdict is unreadable, not agreement")

        # ── the kill switch is absolute ──
        relit_log.unlink(missing_ok=True)
        off = env | {"AGENT_DO_ZPC_RELITIGATE": "0"}
        started = time.time()
        result = zpc(project, off, "inject")
        require(result.returncode == 0, "inject never fails for re-litigation's sake")
        time.sleep(1.0)
        require(not relit_log.exists(), "the kill switch spawns nothing at all")
        require(
            not list((state / "counsel").glob("relit-*")) if (state / "counsel").exists() else True,
            "the kill switch writes no run directory",
        )
        require(time.time() - started < 10, "inject stays on its own clock")

        # ── the trigger, the lock, and the log, without spending a model ──
        planning = env | {"AGENT_DO_ZPC_RELITIGATE": "plan"}
        started = time.time()
        checked(project, planning, "inject")
        elapsed = time.time() - started
        require(elapsed < 10, f"inject returns while the pass runs behind it: {elapsed:.1f}s")

        require(wait_for(lambda: relit_log.exists() and log_rows(relit_log)),
                "an overdue pass fires on inject")
        rows = log_rows(relit_log)
        passes = [row for row in rows if row.get("event") == "pass"]
        require(len(passes) == 1, f"exactly one pass row: {rows}")
        require(passes[0]["candidates"] == 3, f"the pass took the top three: {passes[0]}")
        examined = [row for row in rows if row.get("lesson")]
        require(len(examined) == 3, f"one row per claim examined: {rows}")
        require(all(row["outcome"] == "planned" for row in examined), f"planned, not judged: {examined}")

        run_dirs = sorted((state / "counsel").glob("relit-*"))
        require(len(run_dirs) == 1, f"one artifact directory per pass: {run_dirs}")
        require((run_dirs[0] / "candidates.json").exists(), "the pass records who it picked")
        require(not (state / "relit.lock").exists(), "a finished pass releases its lock")

        # A pass just ran, so the next inject leaves it alone.
        checked(project, planning, "inject")
        time.sleep(1.0)
        require(len(log_rows(relit_log)) == len(rows), f"a recent pass does not re-fire: {log_rows(relit_log)}")

        # ...and --relitigate overrides the gate on purpose.
        checked(project, planning, "inject", "--relitigate")
        require(wait_for(lambda: len([r for r in log_rows(relit_log) if r.get("event") == "pass"]) == 2),
                "an explicit --relitigate runs regardless of the gate")

        # ── a small store is never worth a pass ──
        small = tmp / "small"
        small.mkdir()
        checked(small, env, "init", "--platform", "generic")
        checked(small, env, "learn", "c", "p", "s", "the store is small", "--tags", "x")
        checked(small, planning, "inject")
        time.sleep(1.0)
        require(
            not (small / ".zpc" / ".state" / "relitigation-log.jsonl").exists(),
            "under the exposure floor, nothing fires",
        )

    print("zpc re-litigation: exposure ranks, challenges file, the kill switch holds")


if __name__ == "__main__":
    main()
