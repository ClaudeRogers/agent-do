#!/usr/bin/env python3
"""Isolated regression coverage for `zpc harvest --corrections`.

Mining reads two transcript sources and writes preference lessons to the
machine-wide store. Everything here runs against fixtures — a scratch
agent-sessions index and a scratch transcript tree — so the suite never depends
on what happens to be in this machine's real session history.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
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


def mined(project: Path, env: dict[str, str], *extra: str) -> dict:
    payload = json.loads(checked(project, env, "harvest", "--corrections", "--json", *extra).stdout)
    return payload.get("result", payload)


def transcript(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def assistant(stamp: str, text: str) -> dict:
    return {"type": "assistant", "timestamp": stamp,
            "message": {"content": [{"type": "text", "text": text}]}}


def user(stamp: str, session: str, text: str) -> dict:
    return {"type": "user", "timestamp": stamp, "sessionId": session,
            "message": {"content": text}}


def build_index(path: Path, sessions: list[dict], messages: list[dict]) -> None:
    """A scratch database in the agent-sessions shape, read-only from here on."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE sessions (id TEXT PRIMARY KEY, harness TEXT, project_name TEXT,
                               timestamp INTEGER, is_child INTEGER DEFAULT 0);
        CREATE TABLE messages (id TEXT PRIMARY KEY, session_id TEXT, role TEXT,
                               content TEXT, timestamp INTEGER, sequence INTEGER);
        """
    )
    con.executemany(
        "INSERT INTO sessions VALUES (:id, :harness, :project, :ts, :child)", sessions
    )
    con.executemany(
        "INSERT INTO messages VALUES (:id, :session, :role, :content, :ts, :seq)", messages
    )
    con.commit()
    con.close()


def lesson_rows(store: Path) -> list[dict]:
    if not store.exists():
        return []
    rows = [json.loads(line) for line in store.read_text().splitlines() if line.strip()]
    return [row for row in rows if "retracts" not in row and "challenges" not in row]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        home = tmp / "agent-home"
        transcripts = tmp / "transcripts"
        index = tmp / "index" / "sessions.db"

        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(home)
        env["AGENT_SESSIONS_DB"] = str(index)
        env["AGENT_ZPC_TRANSCRIPT_ROOT"] = str(transcripts)
        store = home / "zpc" / "global-lessons.jsonl"

        project = tmp / "project"
        project.mkdir()
        checked(project, env, "init", "--platform", "generic")

        # ── the live source, with the lexicon's edges around it ──────────────
        transcript(transcripts / "agent-do" / "sess-live0001.jsonl", [
            assistant("2026-07-25T10:00:00.000Z",
                      "A five-part architectural tour of the caching layer, beginning with invalidation philosophy."),
            user("2026-07-25T10:01:00.000Z", "sess-live0001", "too wordy, get to the point"),
            assistant("2026-07-25T10:02:00.000Z", "Rewritten in three lines."),
            # Not corrections: the words appear, the correction does not.
            user("2026-07-25T10:03:00.000Z", "sess-live0001", "what is wrong with the retry test?"),
            user("2026-07-25T10:04:00.000Z", "sess-live0001", "the box is unplugged, I will try again later"),
            user("2026-07-25T10:05:00.000Z", "sess-live0001", "I am not quite sure where the daemon writes its logs"),
        ])

        report = mined(project, env, "--dry-run")
        require(report["dry_run"] is True, f"--dry-run must report itself: {report}")
        require(report["written"] == 0, f"--dry-run wrote lessons: {report}")
        require(not store.exists() or not lesson_rows(store),
                "--dry-run touched the store")
        require(report["candidates"] == 1,
                f"lexicon precision: expected the one real correction, got {report['candidates']}")
        require(report["found"][0]["markers"] == ["too wordy", "get to the point"],
                f"every tripped marker must be recorded: {report['found'][0]}")

        # ── the receipt every mined lesson has to carry ──────────────────────
        report = mined(project, env)
        require(report["written"] == 1, f"first real run must write: {report}")
        rows = lesson_rows(store)
        require(len(rows) == 1, f"store should hold one mined lesson: {rows}")
        row = rows[0]
        require(row["quote"] == "too wordy, get to the point", f"quote must be verbatim: {row}")
        require(row["date"] == "2026-07-25", f"date must come from the transcript: {row}")
        require(row["session"] == "sess-live0001", f"session identifier missing: {row}")
        require("caching layer" in row["problem"],
                f"the preceding assistant turn must be named: {row}")
        require(row["tags"] == ["preference", "mined"], f"mined tags missing: {row}")
        require(row["quote"] in row["takeaway"], f"takeaway must carry his words: {row}")
        require(row["id"].startswith("les-"), f"mined lesson needs a claim id: {row}")

        # ── running it again is a no-op ──────────────────────────────────────
        again = mined(project, env)
        require(again["written"] == 0, f"second run must write nothing: {again}")
        require(again["already_mined"] == 1, f"second run must recognize its own row: {again}")
        require(len(lesson_rows(store)) == 1, "second run duplicated a lesson")

        # ── delivery: the mined claim reaches inject, dated and addressable ──
        injected = checked(project, env, "inject").stdout
        require("--- Global Lessons (machine-wide) ---" in injected, "global section missing")
        require(row["id"] in injected, f"mined lesson must be addressable in inject: {injected}")
        require("2026-07-25" in injected, "mined lesson must render with its date")
        require("too wordy, get to the point" in injected, "mined quote missing from inject")

        # ── it is a claim, so it can be doubted and it can be withdrawn ──────
        challenge = run(project, env, "retract", "--candidate", row["id"],
                        "--evidence", "the wordiness complaint was about one report, not all prose")
        require(challenge.returncode == 0, f"challenging a mined lesson failed: {challenge.stderr}")
        require("[challenged: 1]" in checked(project, env, "inject").stdout,
                "a challenged mined lesson must render its doubt")

        refused = run(project, env, "retract", row["id"])
        require(refused.returncode == 2, f"evidence-free retraction must be refused: {refused.returncode}")

        tombstone = run(project, env, "retract", row["id"],
                        "--evidence", "he asked for the long version in the next session")
        require(tombstone.returncode == 0, f"retracting a mined lesson failed: {tombstone.stderr}")
        after = checked(project, env, "inject").stdout
        require("too wordy, get to the point" not in after,
                f"a retracted mined lesson kept rendering: {after}")

        # A withdrawn claim stays withdrawn: mining must not resurrect it.
        revived = mined(project, env)
        require(revived["written"] == 0, f"mining resurrected a retracted lesson: {revived}")

        # ── the index source, its watermark, and child sessions ──────────────
        home_two = tmp / "agent-home-2"
        env_two = env.copy()
        env_two["AGENT_DO_HOME"] = str(home_two)
        store_two = home_two / "zpc" / "global-lessons.jsonl"

        base = int(datetime(2026, 7, 2, tzinfo=timezone.utc).timestamp())
        build_index(
            index,
            [
                {"id": "sess-index01", "harness": "opencode", "project": "atlas",
                 "ts": base, "child": 0},
                {"id": "sess-child01", "harness": "claude-code", "project": "atlas",
                 "ts": base, "child": 1},
            ],
            [
                {"id": "m1", "session": "sess-index01", "role": "assistant", "seq": 0,
                 "content": "I rewrote the loader to prefetch every shard on boot.", "ts": base},
                {"id": "m2", "session": "sess-index01", "role": "user", "seq": 1,
                 "content": "that's not it, prefetching on boot is the bug", "ts": base + 60},
                # A subagent's "user" turn is an orchestrator's prompt, not his.
                {"id": "m3", "session": "sess-child01", "role": "assistant", "seq": 0,
                 "content": "Draft written.", "ts": base},
                {"id": "m4", "session": "sess-child01", "role": "user", "seq": 1,
                 "content": "not quite, try again with the other framing", "ts": base + 60},
            ],
        )

        report = mined(project, env_two, "--dry-run")
        require(report["index"]["present"] is True, f"index not seen: {report}")
        require(report["index"]["watermark"] == "2026-07-02", f"watermark misread: {report['index']}")
        sessions = {item["session"] for item in report["found"]}
        # Both sources in one run: the index reaches back, the live pass covers
        # what the index has not caught up to.
        require(sessions == {"sess-index01", "sess-live0001"},
                f"expected one correction from each source, got {sessions}")
        require("sess-child01" not in sessions,
                f"child-session turns must not be mined: {report['found']}")

        require(mined(project, env_two)["written"] == 2, "both sources should have written")
        require(len(lesson_rows(store_two)) == 2, f"unexpected store contents: {lesson_rows(store_two)}")

        # An index that already covers the live transcripts leaves the live pass
        # nothing to do: that overlap is what would otherwise mine a correction
        # twice, once out of each source.
        env_ahead = env.copy()
        env_ahead["AGENT_DO_HOME"] = str(tmp / "agent-home-ahead")
        ahead = tmp / "index-ahead" / "sessions.db"
        env_ahead["AGENT_SESSIONS_DB"] = str(ahead)
        build_index(
            ahead,
            [{"id": "sess-ahead01", "harness": "codex", "project": "atlas",
              "ts": int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp()), "child": 0}],
            [{"id": "a1", "session": "sess-ahead01", "role": "assistant", "seq": 0,
              "content": "Nothing to correct here.",
              "ts": int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp())}],
        )
        suppressed = mined(project, env_ahead, "--dry-run")
        require(suppressed["candidates"] == 0,
                f"live turns behind the watermark must not be re-mined: {suppressed}")

        # ── --since narrows, and the cap is bounded and honest ───────────────
        narrowed = mined(project, env_two, "--dry-run", "--since", "2026-07-10")
        require([item["session"] for item in narrowed["found"]] == ["sess-live0001"],
                f"--since must drop everything older than its floor: {narrowed['found']}")

        bad = run(project, env_two, "harvest", "--corrections", "--since", "last")
        require(bad.returncode != 0, "--since must reject a non-date")

        home_cap = tmp / "agent-home-cap"
        env_cap = env.copy()
        env_cap["AGENT_DO_HOME"] = str(home_cap)
        env_cap["AGENT_SESSIONS_DB"] = str(tmp / "absent.db")
        env_cap["AGENT_ZPC_TRANSCRIPT_ROOT"] = str(tmp / "many")
        rows = []
        for index_number in range(25):
            stamp = f"2026-06-{index_number + 1:02d}T09:0{index_number % 10}:00.000Z"
            rows.append(assistant(stamp, f"A long answer number {index_number}."))
            rows.append(user(stamp, "sess-cap00001", f"not quite, fix item {index_number}"))
        transcript(tmp / "many" / "agent-do" / "sess-cap00001.jsonl", rows)

        capped = mined(project, env_cap)
        require(capped["candidates"] == 25, f"fixture should yield 25 candidates: {capped}")
        require(capped["written"] == 20, f"cap must bound one run to 20: {capped}")
        require(capped["beyond_cap"] == 5, f"the cap must report what it left: {capped}")
        require(mined(project, env_cap)["written"] == 0, "capped run was not idempotent")

    print("zpc correction mining tests passed")


if __name__ == "__main__":
    main()
