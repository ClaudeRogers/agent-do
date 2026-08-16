#!/usr/bin/env python3
"""Regression coverage for lesson identity and the retract verb.

Three properties carry the feature and are pinned here: ids are derived from
content, so assigning them twice is a no-op and a reader can name a row the
writer never labelled; a correction with no evidence exits 2 and leaves the
store byte-identical; and nothing is ever edited or deleted — a retracted claim
stays on disk while inject stops rendering it.

`counsel` is absent on purpose (it spawns a model), as it is in the position
suite: cost and non-determinism belong in manual verification, not the gate.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(project: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(AGENT_DO), "zpc", *args],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def checked(project: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    result = run(project, env, *args)
    require(result.returncode == 0, f"zpc {' '.join(args)} failed: {result.stderr or result.stdout}")
    return result


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def claims(path: Path) -> list:
    return [row for row in rows(path) if "retracts" not in row and "challenges" not in row]


def learn(project: Path, env: dict, takeaway: str, tags: str = "api") -> str:
    result = checked(
        project, env, "learn",
        f"context for {takeaway}", f"problem for {takeaway}", f"solution for {takeaway}",
        takeaway, "--tags", tags,
    )
    require("[les-" in result.stdout, f"learn must report the id it wrote: {result.stdout}")
    return result.stdout.split("[", 1)[1].split("]", 1)[0]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(tmp / "agent-home")

        project = tmp / "project"
        project.mkdir()
        checked(project, env, "init", "--platform", "generic")

        lessons = project / ".zpc" / "memory" / "lessons.jsonl"
        decisions = project / ".zpc" / "memory" / "decisions.jsonl"

        # ── ids are content-derived, and assigning them twice changes nothing ──
        legacy = [
            {"date": "2026-01-04", "context": "proxy", "problem": "502s",
             "solution": "raised the timeout", "takeaway": "the gateway times out at 30s",
             "tags": ["proxy", "api"]},
            {"date": "2026-01-05", "context": "retry", "problem": "hot loop",
             "solution": "added backoff", "takeaway": "always back off before retrying",
             "tags": ["api"]},
            # Byte-identical to the row above: two claims, not one, so two ids.
            {"date": "2026-01-05", "context": "retry", "problem": "hot loop",
             "solution": "added backoff", "takeaway": "always back off before retrying",
             "tags": ["api"]},
        ]
        with lessons.open("w") as handle:
            for row in legacy:
                handle.write(json.dumps(row) + "\n")

        checked(project, env, "retract", "--backfill")
        first_pass = digest(lessons)
        ids = [row["id"] for row in claims(lessons)]
        require(len(ids) == 3, f"every legacy row gets an id: {ids}")
        require(all(i.startswith("les-") and len(i) == 10 for i in ids), f"id shape: {ids}")
        require(len(set(ids)) == 3, f"duplicate content must not collapse to one id: {ids}")

        checked(project, env, "retract", "--backfill")
        require(digest(lessons) == first_pass, "backfill must be idempotent, byte for byte")

        # A fresh store built from the same content derives the same ids: the id
        # is a function of the row, not of when it was assigned.
        mirror = tmp / "mirror"
        (mirror / ".zpc" / "memory").mkdir(parents=True)
        checked(mirror, env, "init", "--platform", "generic")
        with (mirror / ".zpc" / "memory" / "lessons.jsonl").open("w") as handle:
            for row in legacy:
                handle.write(json.dumps(row) + "\n")
        checked(mirror, env, "retract", "--backfill")
        require(
            [row["id"] for row in claims(mirror / ".zpc" / "memory" / "lessons.jsonl")] == ids,
            "ids must be derived from content, not from the store that holds it",
        )

        target = ids[0]

        # ── refusal: no evidence, exit 2, not one byte written ──
        before = digest(lessons)
        refused = run(project, env, "retract", target)
        require(refused.returncode == 2, f"evidence-free retraction must exit 2, got {refused.returncode}")
        require("evidence" in refused.stderr, f"refusal must say what is missing: {refused.stderr}")
        require(target in refused.stderr, f"refusal must quote the claim's id: {refused.stderr}")
        require(digest(lessons) == before, "refused retraction must not touch the store")

        empty = run(project, env, "retract", target, "--evidence", "")
        require(empty.returncode == 2, f"empty --evidence must exit 2, got {empty.returncode}")
        require(digest(lessons) == before, "refused retraction must not touch the store")

        refused_candidate = run(project, env, "retract", "--candidate", target)
        require(refused_candidate.returncode == 2, "a challenge also needs its receipt")
        require(digest(lessons) == before, "refused challenge must not touch the store")

        unknown = run(project, env, "retract", "les-000000", "--evidence", "anything")
        require(unknown.returncode == 1, f"unknown id is a usage error, not a refusal: {unknown.returncode}")
        malformed = run(project, env, "retract", "nonsense", "--evidence", "anything")
        require(malformed.returncode == 1, "an id that is not les-/dec- shaped is rejected")
        require(digest(lessons) == before, "neither lookup failure writes anything")

        # ── the retraction lands as a row beside its target, which survives ──
        evidence = "src/gateway.ts:88 sets the timeout to 120s (read 2026-07-27)"
        correction = "the gateway times out at 120s"
        filed = checked(
            project, env, "retract", target,
            "--evidence", evidence, "--takeaway", correction,
        )
        require("Blast radius" in filed.stdout, f"retraction must surface co-referring claims: {filed.stdout}")

        stored = rows(lessons)
        tombstones = [row for row in stored if "retracts" in row]
        require(len(tombstones) == 1, f"exactly one tombstone: {tombstones}")
        tombstone = tombstones[0]
        require(set(tombstone) == {"retracts", "ts", "evidence", "takeaway"}, f"tombstone shape: {tombstone}")
        require(tombstone["retracts"] == target, f"tombstone names its target: {tombstone}")
        require(tombstone["evidence"] == evidence, f"evidence is stored verbatim: {tombstone}")
        original = [row for row in stored if row.get("id") == target]
        require(len(original) == 1, "the retracted claim is still on disk")
        require(original[0]["takeaway"] == "the gateway times out at 30s", "the claim is never edited")

        # ── a challenge marks the claim without withdrawing it ──
        challenged_id = ids[1]
        checked(project, env, "retract", "--candidate", challenged_id, "--evidence", "grep finds no backoff in src/")
        challenges = [row for row in rows(lessons) if "challenges" in row]
        require(len(challenges) == 1, f"exactly one challenge: {challenges}")
        require(set(challenges[0]) == {"challenges", "ts", "evidence"}, f"challenge shape: {challenges[0]}")

        # ── inject: the retracted claim is gone, the correction is there ──
        injected = checked(project, env, "inject").stdout
        require("the gateway times out at 30s" not in injected, "a retracted claim must not render")
        require("## Corrections (recent)" in injected, f"corrections section must render: {injected}")
        require(correction in injected, "the correction takes the retracted claim's place")
        require(f"[challenged: 1]" in injected, f"a challenged claim renders its marker: {injected}")
        require(challenged_id in injected, "claims render with the id you would retract them by")

        # Identical takeaways collapse to one line so a store of repeats cannot
        # spend a whole budget on one sentence — but a challenged row is never
        # collapsed, into a twin or from one. The doubt was filed against that
        # id, and merging it away would hide it behind wording it shares.
        twin = [i for i in ids if i not in (target, challenged_id)][0]
        require(twin in injected, f"the challenged row's identical twin still renders: {injected}")

        compact = checked(project, env, "inject", "--compact").stdout
        require("the gateway times out at 30s" not in compact, "compact must drop retracted claims too")

        # ── counts and health read claims, never corrections ──
        status = checked(project, env, "status", "--json").stdout
        snapshot = json.loads(status)
        snapshot = snapshot.get("result", snapshot)
        require(snapshot["lessons"] == 3, f"three claims, two corrections, count is 3: {snapshot}")
        require(snapshot["format_issues"] == 0, f"corrections are not malformed lessons: {snapshot}")

        # ── query still finds a retracted claim, and finds it by id ──
        found = checked(project, env, "query", "--text", target).stdout
        require("RETRACTED" in found, f"query must mark the retraction: {found}")
        by_id = checked(project, env, "query", "--text", challenged_id, "--json").stdout
        payload = json.loads(by_id)
        payload = payload.get("result", payload)
        require(payload["count"] == 1, f"an id is searchable text: {payload}")

        # ── decisions carry the same identity, and the same correction path ──
        checked(
            project, env, "decide", "Which retry budget?",
            "--options", "fixed,exponential", "--chosen", "exponential",
            "--rationale", "bounded tail latency",
        )
        decision_ids = [row["id"] for row in claims(decisions)]
        require(len(decision_ids) == 1 and decision_ids[0].startswith("dec-"), f"decision id: {decision_ids}")
        checked(project, env, "retract", decision_ids[0], "--evidence", "the budget was never implemented")
        require(
            any("retracts" in row for row in rows(decisions)),
            "a decision's tombstone lands in the decisions store",
        )

        # ── the receipt for a write is logged with the frozen schema ──
        access_log = project / ".zpc" / ".state" / "access-log.jsonl"
        logged = [json.loads(line) for line in access_log.read_text().splitlines() if line.strip()]
        retract_rows = [row for row in logged if row.get("cmd") == "retract"]
        require(len(retract_rows) >= 3, f"every filed correction logs one row: {logged}")
        require(
            all(set(row) == {"ts", "cmd", "source", "project"} for row in retract_rows),
            f"access rows keep their schema: {retract_rows}",
        )

        # ── harvest consolidates the living corpus, and rebuilds what it wrote ──
        harvest_project = tmp / "harvest"
        harvest_project.mkdir()
        checked(harvest_project, env, "init", "--platform", "generic")
        doomed = learn(harvest_project, env, "the cache never expires", "cache")
        for n in range(4):
            learn(harvest_project, env, f"cache claim {n}", "cache")
        checked(harvest_project, env, "harvest", "--auto")
        patterns = harvest_project / ".zpc" / "memory" / "patterns.md"
        require("the cache never expires" in patterns.read_text(), "harvest consolidates the tag")

        checked(harvest_project, env, "retract", doomed, "--evidence", "src/cache.ts:9 sets a 60s TTL")
        checked(harvest_project, env, "harvest", "--auto")
        require(
            "the cache never expires" not in patterns.read_text(),
            f"a retracted claim must wash out of its pattern: {patterns.read_text()}",
        )
        require("cache claim 0" in patterns.read_text(), "the surviving claims stay consolidated")

    print("zpc epistemics: ids derive from content, corrections append, retractions never delete")


if __name__ == "__main__":
    main()
