#!/usr/bin/env python3
"""Regression coverage for the ZPC position ledger.

The refusals are the feature, so they are what is pinned here: a position with
no falsifier is never written, and a flip with no named evidence exits 2 and
leaves the file byte-identical. `counsel` is deliberately absent — it spawns a
model, so its cost and non-determinism belong in manual verification, not in
the suite gate.
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


def run(project: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(AGENT_DO), "zpc", *args],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def checked(project: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    result = run(project, env, *args)
    require(result.returncode == 0, f"zpc {' '.join(args)} failed: {result.stderr or result.stdout}")
    return result


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


FALSIFIER = "a byte-identical body on both sides of the hop"


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(tmp / "agent-home")

        project = tmp / "project"
        project.mkdir()
        checked(project, env, "init", "--platform", "generic")

        ledger = project / ".zpc" / "memory" / "positions.jsonl"

        # A verdict without a falsifier is a mood: refused, and nothing on disk.
        no_falsifier = run(
            project, env,
            "position", "add", "the proxy corrupts the payload",
            "--verdict", "content-encoding is double-applied",
            "--confidence", "med",
        )
        require(no_falsifier.returncode != 0, "add without --falsifier must fail")
        require("falsifier" in no_falsifier.stderr, f"refusal must name the missing falsifier: {no_falsifier.stderr}")
        require(not ledger.exists(), "refused add must write no ledger file")

        # Confidence is a three-level vocabulary, not a number.
        bad_confidence = run(
            project, env,
            "position", "add", "claim", "--verdict", "v",
            "--confidence", "0.8", "--falsifier", FALSIFIER,
        )
        require(bad_confidence.returncode != 0, "numeric confidence must be rejected")
        require(not ledger.exists(), "rejected add must write no ledger file")

        checked(
            project, env,
            "position", "add", "the proxy corrupts the payload",
            "--verdict", "content-encoding is double-applied",
            "--confidence", "med",
            "--falsifier", FALSIFIER,
        )
        stored = rows(ledger)
        require(len(stored) == 1, f"one position expected: {stored}")
        entry = stored[0]
        require(entry["id"].startswith("pos-"), f"id must be pos-prefixed: {entry}")
        require(entry["confidence"] == "med", f"confidence must round-trip: {entry}")
        require(entry["falsifier"] == FALSIFIER, f"falsifier must round-trip: {entry}")
        require(entry["flips"] == [], f"a fresh position has no flips: {entry}")
        require(entry["ts"].endswith("Z"), f"timestamp must be UTC ISO8601: {entry}")

        position_id = entry["id"]
        before = digest(ledger)

        # The refusal that the ledger exists for: exit 2, the stored falsifier
        # quoted back, and not one byte changed.
        refused = run(project, env, "position", "flip", position_id)
        require(refused.returncode == 2, f"evidence-free flip must exit 2, got {refused.returncode}")
        require(FALSIFIER in refused.stderr, f"refusal must quote the stored falsifier: {refused.stderr}")
        require(digest(ledger) == before, "refused flip must not mutate the ledger")

        empty_evidence = run(project, env, "position", "flip", position_id, "--evidence", "")
        require(empty_evidence.returncode == 2, f"empty --evidence must exit 2, got {empty_evidence.returncode}")
        require(digest(ledger) == before, "refused flip must not mutate the ledger")

        # A new verdict is a new opinion and needs its own falsifier.
        unfalsified_verdict = run(
            project, env,
            "position", "flip", position_id,
            "--evidence", "second run agrees",
            "--verdict", "the client decompresses twice",
        )
        require(unfalsified_verdict.returncode != 0, "new verdict without its falsifier must fail")
        require(digest(ledger) == before, "rejected flip must not mutate the ledger")

        # Named evidence: the flip lands, with its reason attached.
        evidence = "curl --raw shows byte-identical bodies on both sides (run 2026-07-27)"
        checked(project, env, "position", "flip", position_id, "--evidence", evidence)
        flipped = rows(ledger)[0]
        require(len(flipped["flips"]) == 1, f"flip must be recorded: {flipped}")
        require(flipped["flips"][0]["evidence"] == evidence, f"evidence must be stored verbatim: {flipped}")
        require(flipped["verdict"] == "withdrawn", f"a flip with no replacement withdraws the verdict: {flipped}")

        replacement = "the client decompresses twice"
        replacement_falsifier = "a client trace showing a single decompression pass"
        checked(
            project, env,
            "position", "flip", position_id,
            "--evidence", "tcpdump shows one Content-Encoding header",
            "--verdict", replacement,
            "--falsifier", replacement_falsifier,
        )
        replaced = rows(ledger)[0]
        require(replaced["verdict"] == replacement, f"stated verdict must replace the old one: {replaced}")
        require(replaced["falsifier"] == replacement_falsifier, f"new falsifier must replace the old one: {replaced}")
        require(len(replaced["flips"]) == 2, f"both flips must be kept: {replaced}")

        # Reads leave receipts, same schema as every other zpc read.
        access_log = project / ".zpc" / ".state" / "access-log.jsonl"
        checked(project, env, "position", "list")
        checked(project, env, "position", "show", position_id)
        logged = [json.loads(line) for line in access_log.read_text().splitlines() if line.strip()]
        reads = [row for row in logged if row.get("cmd") == "position"]
        require(len(reads) >= 2, f"list and show must each log a read: {logged}")
        require(all(set(row) == {"ts", "cmd", "source", "project"} for row in reads), f"access rows keep their schema: {reads}")

        missing = run(project, env, "position", "show", "pos-000000")
        require(missing.returncode != 0, "show of an unknown id must fail")

        listed = checked(project, env, "position", "list", "--json")
        payload = json.loads(listed.stdout)
        payload = payload.get("result", payload)
        require(payload["count"] == 1, f"json list must report the ledger: {payload}")

    print("zpc position ledger: refusals hold, flips record their evidence")


if __name__ == "__main__":
    main()
