#!/usr/bin/env python3
"""Regression coverage for `zpc inject --preferences`.

A preference does not belong to a project. What the user has already said about
how to work has to reach the session standing in an empty directory, which is
exactly the session that has no `.zpc/` to read from — so the store requirement
is what this slice drops, and the ceiling, the tie-breaker, and the retraction
filter are what it keeps.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"

TIEBREAKER = (
    'These are recorded claims, each true as of its date. Live observation '
    'outranks memory: when the code in front of you contradicts a lesson, the '
    'code wins, and filing the contradiction (zpc retract --candidate <id> '
    '--evidence "<receipt>") is worth more than complying with the lesson.'
)
# The caller's squeeze, passed in with --max-tokens. The slice's own budget
# is derived from the quantity authority; nothing in this path ships a
# ceiling for a test to pin.
SQUEEZE = 2000


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def aged(day: str) -> str:
    """`2026-07-20 (14d ago)` — the fixture's date the way inject renders it.

    Computed rather than pinned: the expected age of a fixed date changes
    every midnight, and an age that is merely present proves nothing.
    """
    when = datetime.strptime(day, "%Y-%m-%d").date()
    days = (datetime.now().date() - when).days
    return f"{day} (today)" if days == 0 else f"{day} ({days}d ago)"


def run(cwd: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(AGENT_DO), "zpc", *args],
        cwd=cwd, env=env, text=True, capture_output=True, check=False,
    )


def checked(cwd: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    result = run(cwd, env, *args)
    require(result.returncode == 0, f"zpc {' '.join(args)} failed: {result.stderr or result.stdout}")
    return result


def write_global(home: Path, rows: list[dict]) -> Path:
    store = home / "zpc" / "global-lessons.jsonl"
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return store


def receipts(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


FIXTURE = [
    {"id": "les-aaa001", "date": "2026-07-20", "context": "session",
     "problem": "assistant padded the answer", "solution": "the user corrected it",
     "takeaway": "Correction from Erik: \"just say the thing\"",
     "tags": ["preference", "mined"], "kind": "technique"},
    {"id": "les-aaa002", "date": "2026-07-18", "context": "session",
     "problem": "assistant hedged", "solution": "the user corrected it",
     "takeaway": "Correction from Erik: \"stop hedging\"",
     "tags": ["preference", "mined"], "kind": "technique"},
    {"id": "les-aaa003", "date": "2026-07-19", "context": "session",
     "problem": "assistant guessed", "solution": "the user corrected it",
     "takeaway": "Correction from Erik: \"this one was withdrawn\"",
     "tags": ["preference", "mined"], "kind": "technique"},
    {"id": "les-aaa004", "date": "2026-07-22", "context": "other project",
     "problem": "flaky suite", "solution": "pinned the seed",
     "takeaway": "Always pin the random seed before blaming the test.",
     "tags": ["testing"], "kind": "technique"},
    {"id": "les-aaa005", "date": "2026-07-23", "context": "other project",
     "problem": "gateway 502s", "solution": "raised the timeout",
     "takeaway": "the gateway times out at 30s", "tags": ["proxy"], "kind": "world-state"},
    {"retracts": "les-aaa003", "ts": "2026-07-24T09:00:00Z",
     "evidence": "the session it was mined from was a different user"},
    {"challenges": "les-aaa002", "ts": "2026-07-25T09:00:00Z",
     "evidence": "the next turn asked for more hedging, not less"},
]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        home = tmp / "agent-home"
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(home)

        # A directory with no memory of its own: no .zpc, and nothing above it.
        loose = tmp / "loose"
        loose.mkdir()

        write_global(home, FIXTURE)
        blob = checked(loose, env, "inject", "--preferences").stdout

        require(TIEBREAKER in blob, f"the preference slice carries the law verbatim:\n{blob}")
        require("just say the thing" in blob, f"preference claims must render:\n{blob}")
        require("stop hedging" in blob, "every live preference renders")
        require("this one was withdrawn" not in blob, f"a retracted preference kept rendering:\n{blob}")
        require("[challenged: 1]" in blob, f"a challenged claim renders its marker:\n{blob}")
        require("les-aaa001" in blob, "a claim renders the id you would retract it by")
        require(
            f"[{aged('2026-07-20')}]" in blob and f"[{aged('2026-07-18')}]" in blob,
            f"every claim is dated and says how old that date is:\n{blob}",
        )
        require("the gateway times out at 30s" not in blob, "world-state claims are not preferences")

        # Preferences before the rest, newest first inside each tier: the cut
        # takes from the end, so the order is what decides who survives it.
        require(
            blob.index("just say the thing") < blob.index("stop hedging"),
            f"preferences render newest first:\n{blob}",
        )
        require(
            blob.index("stop hedging") < blob.index("Always pin the random seed"),
            f"preference-tagged claims outrank other techniques:\n{blob}",
        )
        require("truncated" not in blob, "a slice that fits does not claim to have been cut")

        # The receipt for a read that happened outside any store.
        global_log = home / "zpc" / "access-log.jsonl"
        rows = receipts(global_log)
        require(len(rows) == 1, f"one storeless read, one receipt: {rows}")
        require(
            sorted(rows[0]) == ["cmd", "project", "source", "ts"],
            f"the storeless receipt keeps the access-log row shape: {rows[0]}",
        )
        require(rows[0]["cmd"] == "inject --preferences", f"the receipt names the read: {rows[0]}")
        require(
            Path(rows[0]["project"]).resolve() == loose.resolve(),
            f"the receipt names where it was read: {rows[0]}",
        )

        # Nothing recorded is nothing to say, and it is still an answer.
        empty_env = env.copy()
        empty_home = tmp / "empty-home"
        empty_env["AGENT_DO_HOME"] = str(empty_home)
        missing = run(loose, empty_env, "inject", "--preferences")
        require(missing.returncode == 0, f"a missing global store is not an error: {missing.stderr}")
        require(missing.stdout == "", f"a missing global store says nothing: {missing.stdout!r}")

        write_global(empty_home, [])
        blank = run(loose, empty_env, "inject", "--preferences")
        require(blank.returncode == 0, f"an empty global store is not an error: {blank.stderr}")
        require(blank.stdout == "", f"an empty global store says nothing: {blank.stdout!r}")

        # A store holding only corrections has no claims left to render.
        write_global(empty_home, [FIXTURE[2], FIXTURE[5]])
        gone = run(loose, empty_env, "inject", "--preferences")
        require(gone.returncode == 0, f"an all-retracted store is not an error: {gone.stderr}")
        require(gone.stdout == "", f"an all-retracted store says nothing: {gone.stdout!r}")

        # The ceiling holds against a store far too big for it, and it holds by
        # dropping whole claims: half a preference is a sentence the user never
        # wrote.
        fat_env = env.copy()
        fat_home = tmp / "fat-home"
        fat_env["AGENT_DO_HOME"] = str(fat_home)
        write_global(fat_home, [
            {"id": f"les-bbb{index:03d}", "date": f"2026-06-{index % 28 + 1:02d}",
             "context": "bulk", "problem": f"p{index}", "solution": f"s{index}",
             "takeaway": f"Correction from Erik: \"bulk preference {index} " + "x" * 200 + "\"",
             "tags": ["preference", "mined"], "kind": "technique"}
            for index in range(60)
        ])
        crowded = checked(loose, fat_env, "inject", "--preferences",
                          "--max-tokens", str(SQUEEZE)).stdout
        require(len(crowded.encode()) <= SQUEEZE,
                f"the caller's budget holds when crowded: {len(crowded)}")
        require(TIEBREAKER in crowded, f"the law is not what gets trimmed:\n{crowded}")
        cuts = [line for line in crowded.splitlines() if "truncated" in line]
        require(cuts, "a cut slice admits the cut")
        require(all(re.search(r"\b\d+ of \d+\b", line) for line in cuts),
                f"every truncation marker carries its magnitude: {cuts}")
        for line in crowded.splitlines():
            require(
                not line.startswith("- ") or line.rstrip().endswith('"  [tags: preference,mined]'),
                f"a claim was cut mid-sentence:\n{line}",
            )

        # Inside a store the receipt goes where receipts go, and the slice is
        # still the machine-wide one.
        project = tmp / "project"
        project.mkdir()
        checked(project, env, "init", "--platform", "generic")
        checked(project, env, "learn", "local", "local problem", "local fix",
                "a project claim that is not a preference", "--tags", "local")

        in_store = checked(project, env, "inject", "--preferences").stdout
        require("just say the thing" in in_store, "the slice is machine-wide from inside a store too")
        require("a project claim that is not a preference" not in in_store,
                f"the preference slice carries no project claims:\n{in_store}")
        require(len(receipts(global_log)) == 1, "a read inside a store does not write the global log")
        project_log = receipts(project / ".zpc" / ".state" / "access-log.jsonl")
        require(
            any(row.get("cmd") == "inject --preferences" for row in project_log),
            f"a read inside a store leaves its receipt there: {project_log}",
        )

        # The neighbours are untouched: plain inject still carries the project's
        # own memory, and --compact still bounds it.
        full = checked(project, env, "inject").stdout
        require("--- ZPC Agent Protocol (MANDATORY) ---" in full, "plain inject changed shape")
        require("a project claim that is not a preference" in full, "plain inject lost project claims")
        require("--- Global Lessons (machine-wide) ---" in full, "plain inject lost the global section")
        compact = checked(project, env, "inject", "--compact",
                          "--max-tokens", str(SQUEEZE)).stdout
        require("--- ZPC compact (this project's memory) ---" in compact, "--compact changed shape")
        require(len(compact.encode()) <= SQUEEZE, f"--compact honours the caller: {len(compact)}")

        # A store that cannot be read is a directory with no memory, not a
        # failure the caller has to handle.
        broken_env = env.copy()
        broken_home = tmp / "broken-home"
        broken_env["AGENT_DO_HOME"] = str(broken_home)
        store = broken_home / "zpc" / "global-lessons.jsonl"
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text("{not json at all\n", encoding="utf-8")
        broken = run(loose, broken_env, "inject", "--preferences")
        require(broken.returncode == 0, f"an unreadable store is not an error: {broken.stderr}")

    print("zpc preferences: the user's own corrections travel without a store")


if __name__ == "__main__":
    main()
