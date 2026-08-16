#!/usr/bin/env python3
"""Mine the corrections already typed into past sessions.

Guessing what a user wants next is classification. Reading what he already told
you is evidence, and every time he stopped an agent to say "not that" the
evidence was written down: a user turn, in a transcript, right after the turn
that earned it. This module walks those transcripts and turns each correction
into a lesson the global layer can inject.

Nothing here paraphrases. A mined lesson carries the sentence he actually typed,
the day he typed it, one line naming what the assistant had just done, and the
session it happened in. A candidate missing any of those is dropped rather than
filled in, because a preference the agent invented is worse than one it never
learned.

Two sources, because one is not enough. The agent-sessions index is the long
memory (every harness, back to the beginning) and it lags: it is rebuilt on a
schedule, so today's correction is not in it yet. Live Claude Code transcripts
cover exactly that gap, read only past the index's own watermark so the two
sources never mine the same turn twice.

Ids are derived from row content by lib/epistemics, which is what makes a second
run write nothing: the same correction hashes to the same id, and an id already
in the store is a correction already mined.

Called by lib/intelligence.sh (`zpc harvest --corrections`); prints JSON.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import epistemics

# How many lessons one run may add. The window is the newest candidates, so
# repeated runs are a no-op until new corrections happen — and what falls
# outside it is reported rather than silently dropped.
MINE_CAP = 20

# A correction is an aside, not a specification. The long user turns are the
# ones that hand over requirements, and the markers below appear inside them
# constantly ("what's wrong with this test") without correcting anything.
MAX_CORRECTION_CHARS = 600

# What the assistant had just done, and how much of the quote the rendered
# takeaway carries. The full quote is stored verbatim regardless.
ASSISTANT_PREVIEW_CHARS = 180
QUOTE_RENDER_CHARS = 240

MINED_TAGS = ["preference", "mined"]

# ── the correction lexicon ───────────────────────────────────────────────────
# One place, on purpose: this is the whole definition of what counts as a
# correction, and it is meant to be read and argued with.
#
# `pattern` is matched case-insensitively against the user's typed text.
# `deny` (optional) takes it back — the same words used to mean something else.
# The single word "wrong" is anchored to second person: unanchored it matched
# 876 messages, nearly all of them Erik asking what was wrong with some code.
MARKERS = (
    {"name": "too wordy", "pattern": r"too wordy"},
    {"name": "not what i asked", "pattern": r"not what i (?:asked|wanted|said)"},
    {"name": "that's not it", "pattern": r"that'?s not it"},
    {
        "name": "try again",
        "pattern": r"\btry again\b",
        # Planning to retry later is not a correction of anything.
        "deny": r"(?:i|we|you|they)\s*(?:'ll|ll|will|can|could|should|would|might|may)\s+try again"
                r"|\blet'?s try again\b"
                r"|\btry again (?:later|tomorrow|tonight|in a bit|next)\b",
    },
    {
        "name": "not quite",
        "pattern": r"\bnot quite\b",
        # Hedging about his own knowledge, not a verdict on the answer.
        "deny": r"\bnot quite (?:sure|certain|clear on)\b",
    },
    {"name": "stop using", "pattern": r"\bstop using\b"},
    {"name": "get to the point", "pattern": r"get to the point"},
    {
        "name": "wrong",
        "pattern": r"(?:that'?s|thats|this is|you'?re|you are|it'?s|its)\s+wrong"
                   r"|\bwrong again\b|\bjust wrong\b|\bflat(?:ly)? wrong\b",
    },
    {"name": "re-explain", "pattern": r"re-?explain"},
)

_COMPILED = tuple(
    {
        "name": entry["name"],
        "pattern": re.compile(entry["pattern"], re.IGNORECASE),
        "deny": re.compile(entry["deny"], re.IGNORECASE) if entry.get("deny") else None,
    }
    for entry in MARKERS
)

# Harness scaffolding that arrives inside a "user" turn without a user typing
# it. Mining these would learn preferences from the tooling's own boilerplate.
_ENVELOPES = (
    re.compile(r"<system-reminder>.*?</system-reminder>", re.S),
    re.compile(r"<command-name>.*?</command-(?:message|args|stdout)>", re.S),
    re.compile(r"<local-command-stdout>.*?</local-command-stdout>", re.S),
    re.compile(r"<user-prompt-submit-hook>.*?</user-prompt-submit-hook>", re.S),
)


def collapse(text: str) -> str:
    """Strip harness envelopes and flatten whitespace, keeping the words exact."""
    for envelope in _ENVELOPES:
        text = envelope.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def markers_of(text: str):
    """Every lexicon entry this text trips, in lexicon order.

    All of them, not the first: "stop using your fancy prose, get to the point"
    is one sentence tripping two markers, and recording only the earliest one
    throws away half the receipt for why the line was selected.
    """
    hit = []
    for entry in _COMPILED:
        if entry["deny"] and entry["deny"].search(text):
            continue
        if entry["pattern"].search(text):
            hit.append(entry["name"])
    return hit


def _epoch(value, fallback=0) -> int:
    """Message timestamps come as epoch ints, ISO strings, or nothing.

    The index carries all three shapes in one column, so anything that sorts or
    compares them has to normalize first: SQLite orders TEXT above INTEGER, and
    a max() over the mixed column reports a row six months older than the newest.
    """
    if isinstance(value, (int, float)) and value:
        return int(value)
    if isinstance(value, str) and value:
        try:
            return int(
                datetime.fromisoformat(value.replace("Z", "+00:00"))
                .astimezone(timezone.utc)
                .timestamp()
            )
        except ValueError:
            return fallback
    return fallback


def _day(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d")


def _preview(text: str) -> str:
    text = collapse(text)
    if len(text) <= ASSISTANT_PREVIEW_CHARS:
        return text
    return text[:ASSISTANT_PREVIEW_CHARS].rstrip() + "…"


def _candidate(*, epoch, session, harness, project, markers, quote, preceded_by) -> dict:
    return {
        "ts": epoch,
        "date": _day(epoch),
        "session": session,
        "harness": harness or "unknown",
        "project": project or "unknown",
        "markers": markers,
        "marker": ", ".join(markers),
        "quote": quote,
        "preceded_by": preceded_by,
    }


# ── source 1: the agent-sessions index ───────────────────────────────────────


def index_watermark(db_path: str) -> int:
    """The newest moment the index knows about, as epoch seconds.

    Read from sessions rather than messages: session timestamps are uniformly
    integers, and this number decides where the live scan starts.
    """
    if not os.path.exists(db_path):
        return 0
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
            row = con.execute("SELECT max(timestamp) FROM sessions").fetchone()
    except sqlite3.Error:
        return 0
    return _epoch(row[0] if row else 0)


def from_index(db_path: str, since_epoch: int):
    """Corrections the index already holds.

    Child sessions are excluded: a subagent transcript's "user" turns were
    written by an orchestrating agent, not by a person, and mining them would
    teach the machine its own prompts.
    """
    if not os.path.exists(db_path):
        return []

    query = """
        SELECT m.session_id, m.sequence, m.role, m.content, m.timestamp,
               s.harness, s.project_name, s.timestamp AS session_ts
        FROM messages m
        JOIN sessions s ON s.id = m.session_id
        WHERE COALESCE(s.is_child, 0) = 0
        ORDER BY m.session_id, m.sequence
    """
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(query).fetchall()
    except sqlite3.Error:
        return []

    found = []
    previous_assistant = {}
    for row in rows:
        session = row["session_id"]
        content = row["content"] or ""
        if row["role"] == "assistant":
            if content.strip():
                previous_assistant[session] = content
            continue
        if row["role"] != "user":
            continue

        epoch = _epoch(row["timestamp"], _epoch(row["session_ts"]))
        if not epoch or epoch < since_epoch:
            continue
        text = collapse(content)
        if not text or len(text) > MAX_CORRECTION_CHARS:
            continue
        markers = markers_of(text)
        if not markers:
            continue
        # No preceding assistant turn means nothing to have corrected.
        prior = previous_assistant.get(session)
        if not prior:
            continue

        found.append(_candidate(
            epoch=epoch,
            session=session,
            harness=row["harness"],
            project=row["project_name"],
            markers=markers,
            quote=text,
            preceded_by=_preview(prior),
        ))
    return found


# ── source 2: live Claude Code transcripts ───────────────────────────────────


def _blocks(message) -> tuple:
    """(typed text, tools called) out of one Claude Code message body."""
    content = message.get("content")
    if isinstance(content, str):
        return content, []
    if not isinstance(content, list):
        return "", []
    text, tools = [], []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text.append(block.get("text") or "")
        elif block.get("type") == "tool_use":
            tools.append(block.get("name") or "?")
        elif block.get("type") == "tool_result":
            # A tool result wears the user role without a user behind it.
            return "", []
    return "".join(text), tools


def from_live(root: str, after_epoch: int, since_epoch: int):
    """Corrections newer than the index watermark, read from transcripts on disk.

    The index is rebuilt on a schedule, so the most recent corrections — the
    ones a preference miner most wants — are exactly the ones it is missing.
    Only turns strictly newer than the watermark are taken, which is what keeps
    the two sources from mining the same correction twice.
    """
    if not root or not os.path.isdir(root):
        return [], 0

    floor = max(after_epoch, since_epoch)
    found, scanned = [], 0
    for directory, _, filenames in os.walk(root):
        # Subagent transcripts: same reason child sessions are skipped above.
        if "subagents" in directory.split(os.sep):
            continue
        for filename in sorted(filenames):
            if not filename.endswith(".jsonl"):
                continue
            path = os.path.join(directory, filename)
            try:
                if os.path.getmtime(path) <= after_epoch:
                    continue
                handle = open(path, encoding="utf-8", errors="replace")
            except OSError:
                continue
            scanned += 1
            with handle:
                found.extend(_scan_transcript(handle, path, floor))
    return found, scanned


def _scan_transcript(handle, path: str, floor: int):
    session = os.path.splitext(os.path.basename(path))[0]
    found, prior = [], ""
    for line in handle:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or row.get("isSidechain"):
            continue

        kind = row.get("type")
        if kind == "assistant":
            text, tools = _blocks(row.get("message") or {})
            if text.strip():
                prior = text
            elif tools:
                prior = "ran tools: " + ", ".join(dict.fromkeys(tools))
            continue
        if kind != "user" or row.get("isMeta"):
            continue

        epoch = _epoch(row.get("timestamp"))
        if not epoch or epoch <= floor:
            continue
        text, _ = _blocks(row.get("message") or {})
        text = collapse(text)
        if not text or len(text) > MAX_CORRECTION_CHARS:
            continue
        markers = markers_of(text)
        if not markers or not prior:
            continue

        found.append(_candidate(
            epoch=epoch,
            session=row.get("sessionId") or session,
            harness="claude-code",
            project=os.path.basename(os.path.dirname(path)),
            markers=markers,
            quote=text,
            preceded_by=_preview(prior),
        ))
    return found


# ── candidate → lesson ───────────────────────────────────────────────────────


def to_row(candidate: dict) -> dict:
    """The lesson a correction becomes. Deterministic: the id depends on it.

    Nothing derived from the moment of mining goes in — no run timestamp, no
    sequence number — because the id is a hash of this body, and a body that
    changes between runs is a duplicate waiting to be written.
    """
    quote = candidate["quote"]
    rendered = quote if len(quote) <= QUOTE_RENDER_CHARS else quote[:QUOTE_RENDER_CHARS].rstrip() + "…"

    body = {
        "date": candidate["date"],
        "context": f"{candidate['harness']} session {candidate['session'][:8]} ({candidate['project']})",
        "problem": f"Assistant had just: {candidate['preceded_by']}",
        "solution": f"The next user turn was a correction (markers: {candidate['marker']}).",
        # His words, not a summary of them. A paraphrased preference is a
        # preference the machine made up.
        "takeaway": f"Correction from Erik: \"{rendered}\"",
        "tags": list(MINED_TAGS),
        # A preference is a claim about what to do, which re-litigation against
        # the code cannot check and should not queue.
        "kind": "technique",
        "quote": quote,
        "markers": list(candidate["markers"]),
        "session": candidate["session"],
        "source": f"{candidate['harness']}:{candidate['session']}",
    }
    body["id"] = epistemics.derive("les-", epistemics.canonical(body), 0)
    return body


def mine(db_path: str, transcript_root: str, store: str, since: str):
    since_epoch = 0
    if since:
        try:
            since_epoch = int(
                datetime.strptime(since[:10], "%Y-%m-%d")
                .replace(tzinfo=timezone.utc)
                .timestamp()
            )
        except ValueError:
            raise SystemExit(f"--since expects YYYY-MM-DD, got '{since}'")

    watermark = index_watermark(db_path)
    candidates = from_index(db_path, since_epoch)
    live, scanned = from_live(transcript_root, watermark, since_epoch)
    candidates.extend(live)

    # Newest first: a preference from last week outranks one from last year,
    # and the cap should take the old ones. Ties break on content so two runs
    # over the same corpus select the same rows.
    candidates.sort(key=lambda item: (-item["ts"], item["session"], item["quote"]))

    # One sentence in one session is one correction, however many turns it was
    # replayed across. A retried request records the same words twice with a
    # different assistant turn in front of them; both are the same lesson.
    seen, unique = set(), []
    for candidate in candidates:
        key = (candidate["session"], candidate["quote"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    candidates = unique

    # Cap before dedup, not after. Deduping first would let each run reach
    # deeper into history, and "run it again" would keep writing rows instead
    # of doing nothing.
    selected = candidates[:MINE_CAP]

    known = {record["id"] for record in epistemics.analyze(store, "les-")["claims"]}
    rows, fresh = [], []
    for candidate in selected:
        row = to_row(candidate)
        if row["id"] in known:
            rows.append({**candidate, "id": row["id"], "status": "already-mined"})
            continue
        known.add(row["id"])
        rows.append({**candidate, "id": row["id"], "status": "new"})
        fresh.append(row)

    return {
        "candidates": len(candidates),
        "cap": MINE_CAP,
        "selected": len(selected),
        "beyond_cap": max(0, len(candidates) - MINE_CAP),
        "already_mined": len(selected) - len(fresh),
        "index": {
            "path": db_path,
            "present": os.path.exists(db_path),
            "watermark": _day(watermark) if watermark else "",
        },
        "live": {"root": transcript_root, "files_scanned": scanned},
        "found": rows,
        "rows": fresh,
    }


def main(argv) -> int:
    if len(argv) < 4:
        sys.stderr.write("usage: corrections.py <db> <transcript-root> <store> <since> [--dry-run]\n")
        return 2
    db_path, transcript_root, store, since = argv[0], argv[1], argv[2], argv[3]
    dry_run = "--dry-run" in argv[4:]

    report = mine(db_path, transcript_root, store, since)
    rows = report.pop("rows")

    written = 0
    if not dry_run and rows:
        directory = os.path.dirname(store)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(store, "a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                written += 1

    report["dry_run"] = dry_run
    report["written"] = written
    report["store"] = store
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
