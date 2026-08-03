#!/usr/bin/env python3
"""Regression coverage for the per-turn `now` stamp hook.

Everything runs against a scratch AGENT_DO_HOME and a scratch repo, and every
elapsed-time assertion is made by writing the state file's timestamps rather
than by waiting: a test that sleeps for a day is not a test.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "claude" / "agent-do-now-stamp.py"

MAX_STAMP_CHARS = 120
STAMP_RE = re.compile(
    r"^NOW \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2} \([A-Z][a-z]+day\)"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(
    payload: object,
    home: Path,
    cwd: Path | None = None,
    env_extra: dict[str, str] | None = None,
    raw: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENT_DO_HOME"] = str(home)
    env.pop("AGENT_DO_NOW", None)
    env.update(env_extra or {})
    return subprocess.run(
        ["python3", str(HOOK)],
        input=raw if raw is not None else json.dumps(payload),
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def context(result: subprocess.CompletedProcess[str]) -> str:
    require(result.returncode == 0, f"hook exited {result.returncode}: {result.stderr}")
    payload = json.loads(result.stdout)
    emitted = payload["hookSpecificOutput"]
    require(
        emitted["hookEventName"] == "UserPromptSubmit",
        f"wrong hook event: {emitted}",
    )
    line = emitted["additionalContext"]
    require("\n" not in line.strip(), f"stamp must be one line: {line!r}")
    require(len(line) <= MAX_STAMP_CHARS, f"stamp over {MAX_STAMP_CHARS} chars: {line!r}")
    require(bool(STAMP_RE.match(line)), f"stamp does not match pinned shape: {line!r}")
    return line


def state_path(home: Path, session: str) -> Path:
    return home / "now" / f"{session}.json"


def backdate(home: Path, session: str, started_ago: float, last_turn_ago: float) -> None:
    """Move a session's recorded moments into the past, in seconds."""
    now = time.time()
    path = state_path(home, session)
    path.write_text(
        json.dumps({"started_at": now - started_ago, "last_turn_at": now - last_turn_ago})
    )


def test_first_turn_omits_the_last_turn_clause() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        line = context(run({"prompt": "hello", "session_id": "fresh-1"}, home))
        require("last turn" not in line, f"first turn must not claim a previous turn: {line}")
        require("session 0m in" in line, f"first turn should read as session start: {line}")


def test_gaps_render_in_pinned_units() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        session = "gaps-1"
        context(run({"prompt": "first", "session_id": session}, home))

        # Minutes.
        backdate(home, session, started_ago=14 * 60, last_turn_ago=3 * 60)
        line = context(run({"prompt": "second", "session_id": session}, home))
        require("last turn 3m ago" in line, f"minute gap wrong: {line}")
        require("session 14m in" in line, f"minute session wrong: {line}")

        # Hours and minutes.
        backdate(home, session, started_ago=5 * 3600 + 120, last_turn_ago=2 * 3600 + 14 * 60)
        line = context(run({"prompt": "third", "session_id": session}, home))
        require("last turn 2h 14m ago" in line, f"hour gap wrong: {line}")
        require("session 5h 2m in" in line, f"hour session wrong: {line}")

        # Days and hours.
        backdate(home, session, started_ago=12 * 86400 + 5 * 3600, last_turn_ago=3 * 86400 + 4 * 3600)
        line = context(run({"prompt": "fourth", "session_id": session}, home))
        require("last turn 3d 4h ago" in line, f"day gap wrong: {line}")
        require("session 12d 5h in" in line, f"day session wrong: {line}")
        require(len(line) <= MAX_STAMP_CHARS, f"worst-case stamp too long ({len(line)}): {line}")


def test_sub_minute_gap_floors_to_zero_minutes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        context(run({"prompt": "first", "session_id": "quick"}, home))
        line = context(run({"prompt": "second", "session_id": "quick"}, home))
        require("last turn 0m ago" in line, f"back-to-back turns should read 0m: {line}")


def test_clock_skew_never_renders_negative() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        session = "skewed"
        context(run({"prompt": "first", "session_id": session}, home))
        backdate(home, session, started_ago=-3600, last_turn_ago=-600)
        line = context(run({"prompt": "second", "session_id": session}, home))
        require("-" not in line.split(") | ", 1)[1], f"negative gap rendered: {line}")


def test_missing_session_id_stamps_without_gaps() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        line = context(run({"prompt": "hello"}, home))
        require("|" not in line, f"no session id means no measurable gaps: {line}")
        require(not (home / "now").exists(), "no session id must not write state")


def test_kill_switch_is_silent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        result = run(
            {"prompt": "hello", "session_id": "killed"},
            home,
            env_extra={"AGENT_DO_NOW": "0"},
        )
        require(result.returncode == 0, f"kill switch must exit 0: {result.returncode}")
        require(result.stdout == "", f"kill switch must print nothing: {result.stdout!r}")
        require(not (home / "now").exists(), "kill switch must not write state")


def test_malformed_input_is_silent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        for label, raw in (
            ("not json", "{{{"),
            ("empty", ""),
            ("json list", "[1, 2, 3]"),
            ("json string", '"hello"'),
        ):
            result = run(None, home, raw=raw)
            require(result.returncode == 0, f"{label} must exit 0: {result.returncode}")
            require(result.stdout == "", f"{label} must print nothing: {result.stdout!r}")


def test_unreadable_state_falls_back_to_a_first_turn() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        session = "corrupt"
        context(run({"prompt": "first", "session_id": session}, home))
        state_path(home, session).write_text("not json at all")
        line = context(run({"prompt": "second", "session_id": session}, home))
        require("last turn" not in line, f"corrupt state must not invent a gap: {line}")


def test_state_lands_under_agent_do_home_and_never_in_a_repo() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)

        context(run({"prompt": "hello", "session_id": "placement", "cwd": str(repo)}, home, cwd=repo))

        require(state_path(home, "placement").is_file(), "state must land under AGENT_DO_HOME")
        strays = [p for p in repo.rglob("*") if p.is_file() and ".git/" not in str(p)]
        require(not strays, f"hook wrote into the repo: {strays}")


def test_session_id_cannot_escape_the_state_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        context(run({"prompt": "hello", "session_id": "../../escape"}, home))
        written = list((home / "now").glob("*.json"))
        require(len(written) == 1, f"expected one state file, got {written}")
        require(
            written[0].parent == home / "now",
            f"session id escaped the state directory: {written[0]}",
        )


def test_stale_session_files_are_swept() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        context(run({"prompt": "hello", "session_id": "live"}, home))

        stale = state_path(home, "ancient")
        stale.write_text(json.dumps({"started_at": 0, "last_turn_at": 0}))
        ancient = time.time() - 8 * 24 * 3600
        os.utime(stale, (ancient, ancient))

        context(run({"prompt": "hello again", "session_id": "live"}, home))
        require(not stale.exists(), "a session untouched for a week should be swept")
        require(state_path(home, "live").exists(), "the live session must survive the sweep")


def test_hook_completes_well_under_200ms() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        session = "timed"
        context(run({"prompt": "warm", "session_id": session}, home))

        payload = json.dumps({"prompt": "timed", "session_id": session})
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(home)
        elapsed = []
        for _ in range(5):
            start = time.perf_counter()
            subprocess.run(
                ["python3", str(HOOK)],
                input=payload,
                text=True,
                capture_output=True,
                env=env,
                check=True,
            )
            elapsed.append((time.perf_counter() - start) * 1000)
        worst = max(elapsed)
        require(worst < 200, f"hook took {worst:.0f}ms, over the 200ms budget: {elapsed}")


def main() -> int:
    test_first_turn_omits_the_last_turn_clause()
    test_gaps_render_in_pinned_units()
    test_sub_minute_gap_floors_to_zero_minutes()
    test_clock_skew_never_renders_negative()
    test_missing_session_id_stamps_without_gaps()
    test_kill_switch_is_silent()
    test_malformed_input_is_silent()
    test_unreadable_state_falls_back_to_a_first_turn()
    test_state_lands_under_agent_do_home_and_never_in_a_repo()
    test_session_id_cannot_escape_the_state_directory()
    test_stale_session_files_are_swept()
    test_hook_completes_well_under_200ms()
    print("now stamp hook tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
