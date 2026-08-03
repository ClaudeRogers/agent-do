#!/usr/bin/env python3
"""
UserPromptSubmit hook: stamp `now` on every turn.

A model reads the clock once at session start and then does date arithmetic
against that reading for the rest of the session. The arithmetic is where it
goes wrong: on 2026-08-03 this repo's orchestrator wrote `2026-07-28` into
issues and lane prompts it created that same day, six days off, in the hour it
proposed this hook. It had a date in context, the date was stale, and nothing
forced a fresh reading.

So force one. Every turn opens with a single line the model can copy instead of
compute: the absolute local timestamp with its offset and weekday, the gap
since the previous turn, and how long the session has been running.

    NOW 2026-08-03T12:34:56-07:00 (Monday) | last turn 14m ago | session 2h 6m in

The elapsed clauses are what make the absolute one legible: a stamp alone tells
you when it is, a stamp plus gaps tells you how much of the context above you
was written a while ago.

Stdlib only, no subprocesses: this runs on every prompt, so it must cost
milliseconds and it must never be the reason a turn fails. Every error path
exits 0 in silence — a missing stamp is a missing convenience, while a raised
exception is the user's turn.
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# The pinned shape. The line is a header, not a paragraph: it buys its place in
# every turn's context by staying under a tweet's worth of characters.
MAX_STAMP_CHARS = 120

# Session id -> one file. One file per session rather than one shared map
# because parallel agents write their turns concurrently, and a shared map is a
# lost update waiting to happen.
AGENT_DO_HOME = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))
STATE_DIR = AGENT_DO_HOME / "now"

# State lives under AGENT_DO_HOME and never in a repository: a per-machine
# turn clock is not project history, and writing it into a checkout would put
# machine state under version control.
#
# A session's file stops being interesting the moment the session ends, but
# nothing tells this hook that a session ended. The bound is time: files
# untouched for a week are swept on the next run. A week is longer than any
# session that could still care about its own last-turn gap, and short enough
# that the directory stays a handful of files.
SWEEP_AFTER_SECONDS = 7 * 24 * 3600


def disabled() -> bool:
    return os.environ.get("AGENT_DO_NOW", "").strip() == "0"


def session_key(raw: object) -> str | None:
    """Filesystem-safe key for a session id, or None when there is no id.

    No id means no state: two unrelated agents sharing a fallback key would
    read each other's turns as their own, and a wrong gap is worse than no gap.
    """
    if not isinstance(raw, str):
        return None
    key = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-.")[:64]
    return key or None


def format_gap(seconds: float) -> str:
    """Elapsed time in the stamp's pinned units: `Nm`, `Nh Nm`, or `Nd Nh`.

    Minutes are the floor. Below a minute the honest reading is `0m`: the turn
    is continuous with the last one, which is exactly what the model needs to
    know.
    """
    total = max(0, int(seconds))
    minutes = total // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h {minutes % 60}m"
    return f"{hours // 24}d {hours % 24}h"


def read_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_state(path: Path, started_at: float, last_turn_at: float) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"started_at": started_at, "last_turn_at": last_turn_at}),
            encoding="utf-8",
        )
    except Exception:
        pass


def sweep(now: float) -> None:
    """Drop session files no live session could still be reading."""
    try:
        with os.scandir(STATE_DIR) as entries:
            for entry in entries:
                if not entry.name.endswith(".json"):
                    continue
                try:
                    if now - entry.stat().st_mtime > SWEEP_AFTER_SECONDS:
                        os.unlink(entry.path)
                except OSError:
                    continue
    except OSError:
        pass


def timestamp(moment: datetime) -> str:
    return f"NOW {moment.isoformat(timespec='seconds')} ({moment:%A})"


def build_stamp(now: float, started_at: float | None, last_turn_at: float | None) -> str:
    """Assemble the pinned line, absolute clause first.

    The first turn of a session omits the `last turn` clause rather than
    printing a zero: there is no previous turn, and `0m ago` would claim there
    was one.
    """
    parts = [timestamp(datetime.fromtimestamp(now).astimezone())]
    if last_turn_at is not None:
        parts.append(f"last turn {format_gap(now - last_turn_at)} ago")
    if started_at is not None:
        parts.append(f"session {format_gap(now - started_at)} in")

    line = " | ".join(parts)
    if len(line) > MAX_STAMP_CHARS:
        # The absolute reading is the part that cannot be recomputed from
        # anything else in context, so it is the part that survives.
        line = parts[0][:MAX_STAMP_CHARS]
    return line


def main() -> None:
    if disabled():
        sys.exit(0)

    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if not isinstance(input_data, dict):
        sys.exit(0)

    now = time.time()
    key = session_key(input_data.get("session_id"))

    if key is None:
        # Nothing to measure against, so state the one thing that is knowable.
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": timestamp(datetime.fromtimestamp(now).astimezone()),
                    }
                }
            )
        )
        sys.exit(0)

    path = STATE_DIR / f"{key}.json"
    state = read_state(path)

    def moment(field: str) -> float | None:
        value = state.get(field)
        return float(value) if isinstance(value, (int, float)) else None

    last_turn_at = moment("last_turn_at")
    started_at = moment("started_at")
    if started_at is None:
        started_at = now
        last_turn_at = None

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": build_stamp(now, started_at, last_turn_at),
                }
            }
        )
    )

    write_state(path, started_at, now)
    sweep(now)
    sys.exit(0)


if __name__ == "__main__":
    main()
