#!/usr/bin/env python3
"""Machine-wide lessons: what may enter, and when one fires.

A global lesson rides into every session on the machine, so the bar for one is
the bar for interrupting every future piece of work. Before this module the bar
was nothing: `promote --to global` copied any row, and a transcript miner wrote
"try again" into the store as a ruling. After the prune of 2026-08-24 the store
held two lessons, and Erik's ruling was that global lessons must earn their
weight in gold and saffron.

Three things a global lesson has to carry, or `promote` refuses and writes
nothing (exit 2, the same refusal `position add` makes without a falsifier):

  rule   what to do, stated as an instruction a session can follow
  why    the reason, which is what lets a session tell when the rule does
         not apply
  when   the situation that summons it — words in a prompt, a command about
         to run, a file being edited — or `always` for the rare rule that
         belongs in every session's opening context

plus a receipt that it is really cross-project: seen in two or more projects,
or about this machine or this user rather than any codebase. A row a machine
generated (mined, auto-captured) is never eligible.

Delivery follows from `when`. Session start carries only the `always` rows and
a count; everything else waits for its trigger and is injected by the hook
that fires at that moment (`zpc inject --trigger <kind> <value>`), so the rule
arrives beside the situation it is about instead of an hour before it.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import epistemics  # noqa: E402

# The trigger grammar. `kind:match` on the command line; a list of
# {"kind", "match"} on the row. The moments are the ones agent-do already has
# hooks for — nothing here invents a new place to fire from.
KINDS = ("prompt", "command", "path", "always")
TRIGGERED_KINDS = tuple(kind for kind in KINDS if kind != "always")

SCOPES = ("machine", "user")

# Rows nothing typed by a person. Tags the auto-capture and the (retired)
# transcript miner used, and the auto-lesson's own boilerplate takeaway.
MACHINE_TAGS = {"mined", "auto", "auto-captured"}
AUTO_TAKEAWAY_PREFIX = "Error resolved (review and enrich this auto-lesson)"

# How many projects a lesson has to have bitten in before "global" is a
# description and not a hope. One project is a project lesson.
CROSS_PROJECT_MINIMUM = 2


class TriggerError(ValueError):
    pass


def parse_when(spec: str) -> dict:
    """`prompt:<regex>` | `command:<regex>` | `path:<glob>` | `always`."""
    spec = (spec or "").strip()
    if spec == "always":
        return {"kind": "always", "match": ""}
    kind, sep, match = spec.partition(":")
    kind = kind.strip()
    if not sep or kind not in TRIGGERED_KINDS:
        raise TriggerError(
            f"a trigger is one of {', '.join(f'{k}:<match>' for k in TRIGGERED_KINDS)} or always; got '{spec}'"
        )
    match = match.strip()
    if not match:
        raise TriggerError(f"'{kind}:' needs something to match")
    if kind in ("prompt", "command"):
        try:
            re.compile(match, re.IGNORECASE)
        except re.error as exc:
            raise TriggerError(f"'{kind}:{match}' is not a valid regex: {exc}") from exc
    return {"kind": kind, "match": match}


def is_machine_generated(row: dict) -> bool:
    tags = {tag for tag in epistemics.tags_of(row) if isinstance(tag, str)}
    if tags & MACHINE_TAGS:
        return True
    takeaway = row.get("takeaway") or ""
    return isinstance(takeaway, str) and takeaway.startswith(AUTO_TAKEAWAY_PREFIX)


def gate(row: dict, *, rule: str, why: str, whens: list, seen_in: list, scope: str) -> list:
    """What a row is still missing before it may go machine-wide.

    Empty list means it passes. Each entry is one sentence a refusal prints.
    """
    missing = []
    if is_machine_generated(row):
        missing.append(
            "this row was written by a machine (mined or auto-captured); a global "
            "lesson is written by a person who can say why"
        )
    if not (rule or "").strip():
        missing.append("--rule: what to do, as an instruction a session can follow")
    if not (why or "").strip():
        missing.append("--why: the reason, so a session can tell when the rule does not apply")
    if not whens:
        missing.append(
            "--when: the situation that summons it "
            f"({', '.join(f'{k}:<match>' for k in TRIGGERED_KINDS)}, or always)"
        )
    projects = [p for p in seen_in if p]
    if scope and scope not in SCOPES:
        missing.append(f"--scope must be one of {', '.join(SCOPES)}; got '{scope}'")
    elif not scope and len(projects) < CROSS_PROJECT_MINIMUM:
        missing.append(
            f"a cross-project receipt: --seen-in with at least {CROSS_PROJECT_MINIMUM} "
            "project names, or --scope machine|user when it is about this machine or "
            "this user rather than any codebase"
        )
    return missing


def stamp(row: dict, *, rule: str, why: str, whens: list, seen_in: list, scope: str,
          promoted_from: str) -> dict:
    """The global copy: the project row plus the fields the gate demanded."""
    out = dict(row)
    out["rule"] = rule.strip()
    out["why"] = why.strip()
    out["when"] = list(whens)
    if scope:
        out["scope"] = scope
        out.pop("seen_in", None)
    else:
        out["seen_in"] = [p for p in seen_in if p]
        out.pop("scope", None)
    out["promoted_from"] = promoted_from
    out["promoted_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return out


def whens_of(row: dict) -> list:
    raw = row.get("when")
    if not isinstance(raw, list):
        return []
    return [w for w in raw if isinstance(w, dict) and w.get("kind") in KINDS]


def fires_at_startup(row: dict) -> bool:
    """`always` rows, and rows promoted before triggers existed (no `when`)."""
    whens = whens_of(row)
    return not whens or any(w["kind"] == "always" for w in whens)


def split_startup(records) -> tuple[list, list]:
    """(records for session start, records that wait for a trigger)."""
    startup, waiting = [], []
    for record in records:
        (startup if fires_at_startup(record["row"]) else waiting).append(record)
    return startup, waiting


def _matches(when: dict, kind: str, value: str) -> bool:
    if when.get("kind") != kind:
        return False
    match = when.get("match") or ""
    if kind in ("prompt", "command"):
        try:
            return re.search(match, value, re.IGNORECASE) is not None
        except re.error:
            return False
    if kind == "path":
        return fnmatch.fnmatch(value, match) or fnmatch.fnmatch(os.path.basename(value), match)
    return False


def matching(records, kind: str, value: str) -> list:
    """Live global records whose `when` fires for this moment."""
    if kind not in TRIGGERED_KINDS or not value:
        return []
    hits = []
    for record in records:
        if any(_matches(when, kind, value) for when in whens_of(record["row"])):
            hits.append(record)
    return hits


def render_fired(records, kind: str, value: str) -> str:
    """The lesson beside the situation: rule first, then why, then the handle.

    The takeaway is not repeated — the rule is the instruction form of it, and
    two sentences saying one thing is how a reader skims both.
    """
    lines = [f"--- ZPC lesson fires now ({kind}) ---"]
    for record in records:
        row = record["row"]
        note = f"  [challenged: {len(record['challenges'])}]" if record["challenges"] else ""
        lines.append(f"- {row.get('rule') or epistemics.claim_text(row)}{note}")
        if row.get("why"):
            lines.append(f"    why: {row['why']}")
        lines.append(
            f"    {record['id']} [{epistemics.dated(row.get('date'))}]"
            f" — retract with evidence if the code in front of you says otherwise"
        )
    return "\n".join(lines)


def startup_note(waiting_count: int) -> str:
    if waiting_count <= 0:
        return ""
    noun = "lesson carries a trigger and arrives" if waiting_count == 1 else "lessons carry triggers and arrive"
    return (
        f"({waiting_count} more machine-wide {noun} when the situation does: "
        "a matching prompt, command, or file.)"
    )


# ── CLI, for the shell wrappers ──────────────────────────────────────────────


def _load_live(path: str):
    if not path or not os.path.isfile(path) or os.path.getsize(path) == 0:
        return []
    return [r for r in epistemics.analyze(path, "les-")["claims"] if r["retraction"] is None]


def cmd_match(argv) -> int:
    """match <global-file> <kind> <value> → JSON {fired, text}."""
    if len(argv) < 3:
        sys.stderr.write("usage: triggers.py match <global-file> <kind> <value>\n")
        return 2
    path, kind, value = argv[0], argv[1], argv[2]
    hits = matching(_load_live(path), kind, value)
    print(json.dumps({
        "kind": kind,
        "fired": [r["id"] for r in hits],
        "text": render_fired(hits, kind, value) if hits else "",
    }, ensure_ascii=False))
    return 0


def cmd_counts(argv) -> int:
    """counts <global-file> → JSON {live, startup, waiting}."""
    if len(argv) < 1:
        sys.stderr.write("usage: triggers.py counts <global-file>\n")
        return 2
    live = _load_live(argv[0])
    startup, waiting = split_startup(live)
    print(json.dumps({"live": len(live), "startup": len(startup), "waiting": len(waiting)}))
    return 0


def main(argv) -> int:
    if not argv:
        sys.stderr.write("usage: triggers.py match|counts ...\n")
        return 2
    verb, rest = argv[0], argv[1:]
    if verb == "match":
        return cmd_match(rest)
    if verb == "counts":
        return cmd_counts(rest)
    sys.stderr.write(f"unknown verb {verb}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
