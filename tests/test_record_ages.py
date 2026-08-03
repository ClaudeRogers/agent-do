#!/usr/bin/env python3
"""Every dated record the system hands an agent says how old it is.

Models copy phrases reliably and compute date deltas unreliably, so the
delta is computed once, here, by the tools that own the records. Two
properties are pinned throughout: the age is derived at render time (nothing
stored is ever rewritten), and it is appended rather than substituted (the
exact date stays recoverable from the same line).

Ages are asserted against fixtures with known offsets — one day, eight days,
ninety days — and the expected phrase is computed from the fixture rather than
pinned, because the age of a fixed date changes every midnight.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"
ZPC_LIB = ROOT / "tools" / "agent-zpc" / "lib"

# The bounds already in force, restated here because age strings are the most
# likely thing to push a blob past one.
COMPACT_MAX = 2000
PREFERENCES_MAX = 2000
SESSION_START_MAX = 6000
TRUNCATION_MARKER = "[zpc inject truncated]"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def day(offset: int) -> str:
    return str(date.today() - timedelta(days=offset))


def expected_age(offset: int) -> str:
    return "today" if offset == 0 else f"{offset}d ago"


def run(args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(AGENT_DO), *args], cwd=cwd, env=env, text=True, capture_output=True, check=False
    )
    require(
        result.returncode == 0,
        f"{' '.join(args)} failed ({result.returncode}): {result.stderr or result.stdout}",
    )
    return result


# ── the vocabulary itself ────────────────────────────────────────────────────

def test_age_vocabulary_matches_coord() -> None:
    sys.path.insert(0, str(ZPC_LIB))
    import epistemics

    now = datetime.now(timezone.utc)

    def stamp(**delta) -> str:
        return (now - timedelta(**delta)).isoformat().replace("+00:00", "Z")

    require(epistemics.age_of(stamp(seconds=5)) == "5s ago", "seconds render as seconds")
    require(epistemics.age_of(stamp(minutes=3)) == "3m ago", "minutes render as minutes")
    require(epistemics.age_of(stamp(hours=4)) == "4h ago", "hours render as hours")
    require(epistemics.age_of(stamp(days=7, hours=1)) == "7d ago", "days render as days")

    # A bare date can only be answered at day resolution, and its zero is a
    # word rather than a number: `today` cannot be misread, `0d ago` can.
    require(epistemics.age_of(day(0)) == "today", "a date recorded today reads as today")
    for offset in (1, 8, 90):
        require(
            epistemics.age_of(day(offset)) == expected_age(offset),
            f"a {offset}-day-old date must read {expected_age(offset)}",
        )

    # Nothing knowable, nothing claimed.
    for junk in ("", "   ", "not a date", None, 17):
        require(epistemics.age_of(junk) is None, f"unparseable input must claim no age: {junk!r}")

    # Clock skew between machines is real; a record from the future is not.
    require(
        epistemics.age_of((now + timedelta(hours=3)).isoformat().replace("+00:00", "Z")) == "0s ago",
        "a future timestamp must never render negative",
    )


def test_dated_appends_and_never_replaces() -> None:
    sys.path.insert(0, str(ZPC_LIB))
    import epistemics

    require(
        epistemics.dated(day(8)) == f"{day(8)} (8d ago)",
        "the date comes first and the age is appended in parentheses",
    )
    require(epistemics.dated("not a date") == "not a date", "an unreadable value renders as itself")
    require(epistemics.dated("") == "?", "an absent value renders the caller's fallback")
    require(epistemics.dated("", fallback="") == "", "the fallback is the caller's to choose")


# ── zpc ──────────────────────────────────────────────────────────────────────

def zpc_project(tmp: Path) -> tuple[Path, dict[str, str]]:
    env = os.environ.copy()
    env["AGENT_DO_HOME"] = str(tmp / "agent-home")
    project = tmp / "project"
    project.mkdir()
    run(["zpc", "init", "--platform", "generic"], project, env)
    return project, env


def test_zpc_inject_ages_every_claim() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        project, env = zpc_project(tmp)
        memory = project / ".zpc" / "memory"

        lessons = memory / "lessons.jsonl"
        rows = [
            {"date": day(offset), "context": "c", "problem": "p", "solution": "s",
             "takeaway": f"claim aged {offset}", "tags": ["proxy"]}
            for offset in (0, 1, 8, 90)
        ]
        lessons.write_text("".join(json.dumps(row) + "\n" for row in rows))
        (memory / "patterns.md").write_text("# Patterns\n\n## proxy\n- consolidated\n")
        before = lessons.read_bytes()

        blob = run(["zpc", "inject"], project, env).stdout
        for offset in (0, 1, 8, 90):
            expected = f"[{day(offset)} ({expected_age(offset)})]"
            require(expected in blob, f"a claim must render {expected}:\n{blob}")

        # A consolidated section is aged by its newest claim: staleness is
        # about the last addition, not the first.
        require(
            f"## proxy  [4 claim(s), {day(90)}..{day(0)} (today)]" in blob,
            f"a pattern section is aged by its newest claim:\n{blob}",
        )

        require(lessons.read_bytes() == before, "rendering an age must not rewrite the store")


def test_zpc_decisions_carry_their_age() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        project, env = zpc_project(tmp)
        decisions = project / ".zpc" / "memory" / "decisions.jsonl"
        decisions.write_text(json.dumps({
            "date": day(8), "problem": "which store", "options": ["a", "b"],
            "chosen": "a", "rationale": "it was already there",
        }) + "\n")

        blob = run(["zpc", "inject"], project, env).stdout
        require(
            f"[{day(8)} (8d ago)]" in blob,
            f"a settled decision must say how long it has been settled:\n{blob}",
        )


def test_zpc_corrections_carry_their_age() -> None:
    """A correction is only useful while the belief it corrects may still be
    in someone's head, which is a question about how long ago it was made."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        project, env = zpc_project(tmp)
        lessons = project / ".zpc" / "memory" / "lessons.jsonl"

        lessons.write_text(json.dumps({
            "date": day(20), "context": "c", "problem": "p", "solution": "s",
            "takeaway": "the old belief", "tags": ["x"],
        }) + "\n")

        # The retraction has to name the row it withdraws, and ids are derived
        # from content, so the id is read back out of the render.
        first = run(["zpc", "inject"], project, env).stdout
        target = re.search(r"les-[0-9a-f]+", first)
        require(target is not None, f"the fixture claim must render an id:\n{first}")

        stamp = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with lessons.open("a") as handle:
            handle.write(json.dumps({
                "retracts": target.group(0), "ts": stamp,
                "takeaway": "the corrected belief", "evidence": "receipt",
            }) + "\n")

        blob = run(["zpc", "inject"], project, env).stdout
        require(
            f"[{day(3)} (3d ago)] {target.group(0)} corrected to:" in blob,
            f"a correction must say how long ago it was made:\n{blob}",
        )


def test_zpc_bounds_still_bind_with_ages_in_the_blob() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        project, env = zpc_project(tmp)
        memory = project / ".zpc" / "memory"

        # Far more store than any bound can carry, so the cut is exercised.
        with (memory / "lessons.jsonl").open("w") as handle:
            for n in range(150):
                handle.write(json.dumps({
                    "date": day(n % 120), "context": "bulk", "problem": f"p{n}",
                    "solution": f"s{n}", "takeaway": f"bulk takeaway {n} " + "x" * 70,
                    "tags": ["bulk"],
                }) + "\n")
        (memory / "patterns.md").write_text("# Patterns\n\n" + ("- a long pattern line\n" * 200))

        compact = run(["zpc", "inject", "--compact"], project, env).stdout
        require(len(compact) <= COMPACT_MAX, f"compact blew its ceiling: {len(compact)} chars")
        require(TRUNCATION_MARKER in compact, "a cut blob still admits the cut")

        global_lessons = Path(env["AGENT_DO_HOME"]) / "zpc" / "global-lessons.jsonl"
        global_lessons.parent.mkdir(parents=True, exist_ok=True)
        with global_lessons.open("w") as handle:
            for n in range(80):
                handle.write(json.dumps({
                    "date": day(n % 60), "context": "c", "problem": "p", "solution": "s",
                    "takeaway": f"preference {n} " + "y" * 70, "tags": ["preference"],
                }) + "\n")

        preferences = run(["zpc", "inject", "--preferences"], project, env).stdout
        require(
            len(preferences) <= PREFERENCES_MAX,
            f"the preference slice blew its ceiling: {len(preferences)} chars",
        )
        require(TRUNCATION_MARKER in preferences, "a cut preference slice admits the cut")

        # The full blob has no ceiling of its own; the session-start hook cuts
        # it at 6000 and backs up to a whole line. That arithmetic is what the
        # ages must survive, so it is exercised on real oversized output.
        full = run(["zpc", "inject"], project, env).stdout
        require(len(full) > SESSION_START_MAX, "fixture must be big enough to exercise the cut")
        cut = full[:SESSION_START_MAX]
        cut = cut[: cut.rfind("\n")] + f"\n{TRUNCATION_MARKER}"
        require(len(cut) <= SESSION_START_MAX, f"the session-start cut must hold: {len(cut)}")
        require(cut.endswith(TRUNCATION_MARKER), "the cut blob keeps its marker")


def test_zpc_position_renders_its_age() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        project, env = zpc_project(tmp)

        run([
            "zpc", "position", "add", "the gate is the refusal",
            "--verdict", "yes", "--confidence", "high",
            "--falsifier", "a claim succeeds on a dream",
        ], project, env)

        listed = run(["zpc", "position", "list"], project, env).stdout
        require(
            f"{day(0)} (today)" in listed,
            f"a position must say how long it has stood:\n{listed}",
        )

        rows = (project / ".zpc" / "memory" / "positions.jsonl").read_text().strip().split("\n")
        position_id = json.loads(rows[0])["id"]
        shown = run(["zpc", "position", "show", position_id], project, env).stdout
        recorded = next(line for line in shown.splitlines() if "recorded:" in line)
        # `show` holds the full timestamp, so its age answers at the ladder's
        # own resolution rather than at day resolution.
        require(
            re.search(r"recorded:\s+\S+Z \(\d+[smhd] ago\)$", recorded) is not None,
            f"position show must append an age to the exact timestamp: {recorded!r}",
        )


# ── manna ────────────────────────────────────────────────────────────────────

def manna_board(tmp: Path, offsets: list[int]) -> tuple[Path, dict[str, str]]:
    """A board whose rows were last touched a known number of days ago.

    The timestamps are written directly because there is no way to ask the CLI
    for a row that moved last week, and a fixture is the one place that is
    honest: nothing here manages a real board.
    """
    env = os.environ.copy()
    env["AGENT_DO_HOME"] = str(tmp / "agent-home")
    env["MANNA_SESSION_ID"] = "ages-test"
    board = tmp / "board"
    board.mkdir()
    run(["manna", "init"], board, env)

    for offset in offsets:
        run(["manna", "create", f"row aged {offset}"], board, env)

    path = board / ".manna" / "issues.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    require(len(rows) == len(offsets), f"expected {len(offsets)} rows, got {len(rows)}")
    for row, offset in zip(rows, offsets):
        stamp = (datetime.now(timezone.utc) - timedelta(days=offset, hours=1))
        row["created_at"] = stamp.isoformat().replace("+00:00", "Z")
        row["updated_at"] = row["created_at"]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return board, env


def manna_day(offset: int) -> str:
    return str((datetime.now(timezone.utc) - timedelta(days=offset, hours=1)).date())


def test_manna_list_show_and_context_render_ages() -> None:
    offsets = [1, 8, 90]
    with tempfile.TemporaryDirectory() as tmp_str:
        board, env = manna_board(Path(tmp_str), offsets)
        path = board / ".manna" / "issues.jsonl"
        before = path.read_bytes()

        listed = run(["manna", "list"], board, env).stdout
        for offset in offsets:
            expected = f"updated: {manna_day(offset)} ({offset}d ago)"
            require(expected in listed, f"list must carry '{expected}':\n{listed}")

        blob = run(["manna", "context"], board, env).stdout
        for offset in offsets:
            expected = f"updated {manna_day(offset)} ({offset}d ago)"
            require(expected in blob, f"context must carry '{expected}':\n{blob}")

        first_id = json.loads(path.read_text().splitlines()[0])["id"]
        shown = run(["manna", "show", first_id], board, env).stdout
        require("age:" in shown, f"show must carry an age block:\n{shown}")
        require("created: 1d ago" in shown, f"show must age creation:\n{shown}")
        require("updated: 1d ago" in shown, f"show must age the last move:\n{shown}")
        # The exact stored timestamps stay exactly where a parser expects them.
        require("created_at: " in shown and "updated_at: " in shown, "show keeps its RFC 3339 fields")

        require(path.read_bytes() == before, "rendering an age must not rewrite the board")


def test_manna_json_output_keeps_timestamps_machine_readable() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        board, env = manna_board(Path(tmp_str), [8])
        payload = json.loads(run(["manna", "list", "--json"], board, env).stdout)
        row = payload["issues"][0]
        require(
            row["updated"] == f"{manna_day(8)} (8d ago)",
            f"the rendered field carries date and age: {row}",
        )
        # And the stored row, read back, is still an unmodified RFC 3339 stamp.
        stored = json.loads((board / ".manna" / "issues.jsonl").read_text().splitlines()[0])
        datetime.fromisoformat(stored["updated_at"].replace("Z", "+00:00"))


def main() -> int:
    test_age_vocabulary_matches_coord()
    test_dated_appends_and_never_replaces()
    test_zpc_inject_ages_every_claim()
    test_zpc_decisions_carry_their_age()
    test_zpc_corrections_carry_their_age()
    test_zpc_bounds_still_bind_with_ages_in_the_blob()
    test_zpc_position_renders_its_age()
    test_manna_list_show_and_context_render_ages()
    test_manna_json_output_keeps_timestamps_machine_readable()
    print("record ages: every dated record says how old it is, and stays exactly dated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
