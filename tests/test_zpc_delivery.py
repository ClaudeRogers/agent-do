#!/usr/bin/env python3
"""Regression coverage for anti-dogma delivery.

Retraction assumes a noticer, and injection is what suppresses noticing: an
agent handed bare assertions at birth has no reason to argue with them. So the
delivery itself is pinned here — the tie-breaker sentence verbatim in both
blobs, every claim carrying its date and kind, no "follow these" anywhere, and
the compact blob still inside its 2000-character ceiling with all of it.
"""

from __future__ import annotations

import json
import os
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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def aged(day: str) -> str:
    """`2026-01-04 (211d ago)` — the fixture's date the way delivery renders it.

    Computed here rather than pinned, because the expected age of a fixed date
    changes every midnight. A wrong age fails this the same as a missing one.
    """
    when = datetime.strptime(day, "%Y-%m-%d").date()
    days = (datetime.now().date() - when).days
    return f"{day} (today)" if days == 0 else f"{day} ({days}d ago)"


def checked(project: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [str(AGENT_DO), "zpc", *args],
        cwd=project, env=env, text=True, capture_output=True, check=False,
    )
    require(result.returncode == 0, f"zpc {' '.join(args)} failed: {result.stderr or result.stdout}")
    return result


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(tmp / "agent-home")

        project = tmp / "project"
        project.mkdir()
        checked(project, env, "init", "--platform", "generic")

        memory = project / ".zpc" / "memory"
        with (memory / "lessons.jsonl").open("w") as handle:
            for row in [
                {"date": "2026-01-04", "context": "gateway", "problem": "502s",
                 "solution": "raised the timeout", "takeaway": "the gateway times out at 30s",
                 "tags": ["proxy"]},
                {"date": "2026-01-06", "context": "retry", "problem": "hot loop",
                 "solution": "added backoff", "takeaway": "always back off before retrying",
                 "tags": ["proxy"]},
            ]:
                handle.write(json.dumps(row) + "\n")
        (memory / "patterns.md").write_text(
            "# Patterns\n\n## proxy\n<!-- zpc:auto -->\n- always back off before retrying\n"
            "\n## handwritten\n- a section nobody generated\n"
        )
        checked(project, env, "retract", "--backfill")
        ids = [
            json.loads(line)["id"]
            for line in (memory / "lessons.jsonl").read_text().splitlines()
            if line.strip()
        ]

        # Delivery reads the re-litigation log for the one thing a claim cannot
        # say about itself: when it was last tried against current reality.
        state = project / ".zpc" / ".state"
        state.mkdir(exist_ok=True)
        (state / "relitigation-log.jsonl").write_text(
            json.dumps({"ts": "2026-07-20T09:00:00Z", "run": "relit-1",
                        "lesson": ids[0], "outcome": "supported"}) + "\n"
        )

        full = checked(project, env, "inject").stdout
        compact = checked(project, env, "inject", "--compact").stdout

        for label, blob in (("inject", full), ("inject --compact", compact)):
            require(TIEBREAKER in blob, f"{label} must carry the tie-breaker verbatim:\n{blob}")
            require("follow these" not in blob, f"{label} must not frame claims as orders:\n{blob}")
            require("Established Patterns" not in blob, f"{label} keeps no 'Established' framing")
            require("Established patterns" not in blob, f"{label} keeps no 'Established' framing")
            require("<!-- zpc:auto -->" not in blob, f"{label} must strip harvest bookkeeping")
            require("(world-state)" in blob, f"{label} must render claim kind:\n{blob}")
            require("(technique)" in blob, f"{label} must distinguish technique from world-state")
            require(
                aged("2026-01-04") in blob and aged("2026-01-06") in blob,
                f"{label} must date every claim and say how old the date is:\n{blob}",
            )
            require(ids[0] in blob, f"{label} must name the id you would retract by")

        require("Recorded Patterns (claims, dated)" in full, f"full blob renames the section:\n{full}")
        require("Recorded patterns (claims, dated):" in compact, "compact renames the section")
        require(
            f"## proxy  [2 claim(s), 2026-01-04..{aged('2026-01-06')}]" in full,
            f"a consolidated section is dated by the claims behind it, and aged "
            f"by its newest:\n{full}",
        )
        require(
            "## handwritten" in full and "## handwritten  [" not in full,
            "a section with no claims behind it gets no invented dating",
        )
        require(
            f"[checked: {aged('2026-07-20')}]" in full,
            f"a re-litigated claim shows when, and how long ago that was:\n{full}",
        )
        require("[checked:" not in full.split(ids[1])[1].split("\n")[0],
                "an unexamined claim claims no check")

        require(len(compact) <= 2000, f"compact stays bounded: {len(compact)} chars")

        # The ceiling holds when the store is far too big for it, and the law
        # survives the cut that the claims do not.
        with (memory / "lessons.jsonl").open("a") as handle:
            for n in range(120):
                handle.write(json.dumps({
                    "date": "2026-02-01", "context": "bulk", "problem": f"p{n}",
                    "solution": f"s{n}", "takeaway": f"bulk takeaway number {n} " + "x" * 60,
                    "tags": ["bulk"],
                }) + "\n")
        (memory / "patterns.md").write_text("# Patterns\n\n" + ("- a long pattern line\n" * 200))
        crowded = checked(project, env, "inject", "--compact").stdout
        require(len(crowded) <= 2000, f"compact stays bounded when crowded: {len(crowded)} chars")
        require(TIEBREAKER in crowded, f"the law is not what gets trimmed:\n{crowded}")
        require("[zpc inject truncated]" in crowded, "a cut blob still admits the cut")

    print("zpc delivery: claims arrive dated, kinded, and outranked by observation")


if __name__ == "__main__":
    main()
