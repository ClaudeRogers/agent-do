#!/usr/bin/env python3
"""Identity and corrections for the ZPC memory stores.

A claim you cannot name is a claim you cannot argue with. Lessons and decisions
were written as anonymous rows, which was survivable while memory was something
an agent chose to read and fatal once injection made it automatic: a wrong row
became automated anchoring with no handle to grab it by.

This module supplies the handle. Ids are derived from row content, so the same
store yields the same ids every time it is asked — backfill is idempotent, and
a reader can name a row the writer never labelled. Corrections are appended
rows in the same file as their target: a retraction ({"retracts": id}) says the
claim is wrong and names the receipt, a challenge ({"challenges": id}) says only
that someone doubted it. Nothing is ever edited or deleted, because the record
of having been wrong is worth more than the tidiness of hiding it.

Called by lib/epistemics.sh; every subcommand prints JSON on stdout.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone

# Six hex characters: short enough to type into a retract command from a glance
# at an inject blob, wide enough that the collision loop below almost never runs.
ID_HEX = 6

# Prescriptive language marks a technique — a claim about what to do, which
# stays true as long as the practice does. Everything else is read as
# world-state: a claim about how things are, which rots when things change.
# Deliberately crude and deliberately deterministic: no model call decides how
# a lesson is filed.
_TECHNIQUE_OPENERS = re.compile(
    r"^\W*(always|never|prefer|use|run|avoid|check|add|keep|write|start|stop|"
    r"don'?t|do not|make sure|ensure|remember to|treat|put|set|call|verify)\b",
    re.IGNORECASE,
)

_STOPWORDS = {
    "about", "after", "again", "against", "because", "before", "being", "between",
    "could", "every", "first", "from", "into", "never", "other", "should", "since",
    "start", "still", "than", "that", "their", "them", "then", "there", "these",
    "they", "this", "those", "through", "under", "until", "were", "what", "when",
    "where", "which", "while", "with", "would", "your",
}


def is_correction(row) -> bool:
    """A correction row talks about another row instead of about the world."""
    return isinstance(row, dict) and ("retracts" in row or "challenges" in row)


def load(path: str):
    """Parse a store into (raw_line, parsed_or_None) pairs, in file order.

    Unparseable lines are kept verbatim so a rewrite can put them back exactly
    as found: this module refuses to be the reason a store loses a line it
    merely failed to understand.
    """
    entries = []
    try:
        with open(path) as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    parsed = None
                entries.append((stripped, parsed if isinstance(parsed, dict) else None))
    except OSError:
        return []
    return entries


def canonical(row: dict) -> str:
    """The content an id is derived from: the whole row except the id itself."""
    body = {key: value for key, value in row.items() if key != "id"}
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def derive(prefix: str, base: str, nonce: int) -> str:
    digest = hashlib.sha256(f"{nonce}\x1f{base}".encode("utf-8")).hexdigest()
    return prefix + digest[:ID_HEX]


def assign_ids(entries, prefix: str):
    """Give every claim row an id, deriving it from content in file order.

    Two rows with identical content are two claims, not one, so the second gets
    the next nonce rather than the first row's id. The same loop absorbs a true
    hash collision. Both walks are decided by file content alone, which is what
    makes running this twice a no-op: stored ids are taken as given, and any row
    re-derived lands on the id it already had.
    """
    taken = {
        parsed["id"]
        for _, parsed in entries
        if parsed and isinstance(parsed.get("id"), str) and parsed["id"]
    }

    assigned = 0
    result = []
    for raw, parsed in entries:
        if parsed is None or is_correction(parsed) or parsed.get("id"):
            result.append((raw, parsed))
            continue

        base = canonical(parsed)
        nonce = 0
        while True:
            candidate = derive(prefix, base, nonce)
            if candidate not in taken:
                break
            nonce += 1

        taken.add(candidate)
        assigned += 1
        # Id first, so a human scanning the raw file reads the handle before the
        # prose. The remaining keys keep their written order.
        ordered = {"id": candidate}
        ordered.update({key: value for key, value in parsed.items() if key != "id"})
        result.append((json.dumps(ordered, ensure_ascii=False), ordered))

    return result, assigned


def write_atomic(path: str, entries) -> None:
    directory = os.path.dirname(path) or "."
    handle_fd, temp_path = tempfile.mkstemp(dir=directory)
    with os.fdopen(handle_fd, "w") as handle:
        for raw, _ in entries:
            handle.write(raw + "\n")
    os.replace(temp_path, path)


def analyze(path: str, prefix: str) -> dict:
    """The store as an epistemic object: claims, and what has been said about them.

    Ids are derived here rather than read, so a store that has never been
    written to since this shipped answers exactly as it will after its first
    backfill. Nothing on this path writes.
    """
    entries, _ = assign_ids(load(path), prefix)

    claims = []
    by_id = {}
    for raw, parsed in entries:
        if parsed is None or is_correction(parsed):
            continue
        record = {
            "id": parsed["id"],
            "row": parsed,
            "retraction": None,
            "challenges": [],
        }
        claims.append(record)
        by_id[parsed["id"]] = record

    orphans = []
    for _, parsed in entries:
        if not is_correction(parsed):
            continue
        target = parsed.get("retracts") or parsed.get("challenges")
        record = by_id.get(target)
        if record is None:
            orphans.append(parsed)
            continue
        if "retracts" in parsed:
            # Newest retraction wins the render; the older ones stay on disk.
            record["retraction"] = parsed
        else:
            record["challenges"].append(parsed)

    return {"claims": claims, "by_id": by_id, "orphans": orphans}


def kind_of(row: dict) -> str:
    """world-state or technique. An explicit field always beats the heuristic."""
    declared = row.get("kind")
    if declared in ("world-state", "technique"):
        return declared
    takeaway = (row.get("takeaway") or row.get("solution") or "").strip()
    return "technique" if _TECHNIQUE_OPENERS.match(takeaway) else "world-state"


def claim_text(row: dict) -> str:
    return (row.get("takeaway") or row.get("solution") or row.get("chosen") or "").strip()


def tags_of(row: dict):
    tags = row.get("tags") or []
    if isinstance(tags, str):
        tags = [tag.strip() for tag in tags.split(",")]
    return [tag for tag in tags if isinstance(tag, str) and tag]


def last_checked(relit_log: str) -> dict:
    """id -> the day it was last tried against current reality, if ever.

    Written by re-litigation, read by delivery. A claim's own date says when it
    was believed; this says when it was last put in front of the code again,
    and the gap between them is the honest measure of how much it has earned.
    An unreadable or absent log means "never checked", never an error.
    """
    checked = {}
    try:
        with open(relit_log) as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                target, stamp = row.get("lesson"), row.get("ts", "")
                if not target or not stamp:
                    continue
                day = stamp[:10]
                if day > checked.get(target, ""):
                    checked[target] = day
    except OSError:
        pass
    return checked


def render_patterns(patterns_path: str, lessons_path: str) -> str:
    """Patterns as dated claims rather than standing orders.

    A consolidated section summarizes lessons that each happened on a day, so
    the heading carries that span wherever the tags make it derivable and says
    nothing where they do not. Harvest's machine marker is stripped: it is
    bookkeeping for the rebuild, not context for a reader.
    """
    spans = {}
    for record in analyze(lessons_path, "les-")["claims"]:
        if record["retraction"] is not None:
            continue
        date = record["row"].get("date", "")
        for tag in tags_of(record["row"]):
            first, last, count = spans.get(tag, ("", "", 0))
            spans[tag] = (
                min(first, date) if first else date,
                max(last, date) if last else date,
                count + 1,
            )

    try:
        with open(patterns_path) as handle:
            lines = handle.read().rstrip("\n").split("\n")
    except OSError:
        return ""

    out = []
    for line in lines:
        if line.strip() == "<!-- zpc:auto -->":
            continue
        heading = re.match(r"^## (.+)$", line.strip())
        if heading:
            tag = heading.group(1).strip()
            span = spans.get(tag)
            if span and span[2]:
                first, last, count = span
                window = first if first == last else f"{first}..{last}"
                out.append(f"## {tag}  [{count} claim(s), {window}]")
                continue
        out.append(line)
    return "\n".join(out)


def terms_of(text: str):
    """Salient words: long enough to mean something, common enough to match."""
    return {
        word
        for word in re.findall(r"[a-z0-9_.-]{5,}", text.lower())
        if word not in _STOPWORDS
    }


# ── subcommands ──────────────────────────────────────────────────────────────


def cmd_backfill(argv) -> int:
    """Materialize derived ids into the file. Idempotent by construction."""
    path, prefix = argv[0], argv[1]
    entries = load(path)
    updated, assigned = assign_ids(entries, prefix)
    if assigned:
        write_atomic(path, updated)
    total = sum(1 for _, parsed in updated if parsed and not is_correction(parsed))
    print(json.dumps({"assigned": assigned, "claims": total, "path": path}))
    return 0


def cmd_count(argv) -> int:
    """Claim rows only. Corrections are commentary, not entries."""
    entries = load(argv[0])
    print(sum(1 for _, parsed in entries if parsed is not None and not is_correction(parsed)))
    return 0


def cmd_resolve(argv) -> int:
    """Print one claim by id, with everything already said about it."""
    path, prefix, wanted = argv[0], argv[1], argv[2]
    state = analyze(path, prefix)
    record = state["by_id"].get(wanted)
    if record is None:
        return 1
    row = record["row"]
    print(json.dumps({
        "id": record["id"],
        "row": row,
        "kind": kind_of(row),
        "date": row.get("date", ""),
        "claim": claim_text(row),
        "tags": tags_of(row),
        "retraction": record["retraction"],
        "challenges": len(record["challenges"]),
    }, ensure_ascii=False))
    return 0


def cmd_correction(argv) -> int:
    """Emit a correction row for appending. Shape is fixed; nothing else joins it."""
    verb, target, evidence = argv[0], argv[1], argv[2]
    takeaway = argv[3] if len(argv) > 3 else ""
    key = "retracts" if verb == "retract" else "challenges"
    row = {
        key: target,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evidence": evidence,
    }
    if verb == "retract" and takeaway:
        row["takeaway"] = takeaway
    print(json.dumps(row, ensure_ascii=False))
    return 0


def cmd_blast_radius(argv) -> int:
    """Everything that co-refers with a corrected claim.

    A wrong lesson rarely travelled alone: it was tagged with its neighbours and
    consolidated into a pattern that now repeats it in every inject. Retraction
    names the row; this names the blast radius, and leaves the judgment to a
    reader rather than deleting anything on a keyword match.
    """
    lessons_path, decisions_path, patterns_path, prefix, wanted = argv[:5]
    limit = int(argv[5]) if len(argv) > 5 else 8

    state = analyze(lessons_path, prefix)
    record = state["by_id"].get(wanted)
    if record is None:
        state = analyze(decisions_path, "dec-")
        record = state["by_id"].get(wanted)
    if record is None:
        print(json.dumps({"lessons": [], "decisions": [], "patterns": []}))
        return 0

    target = record["row"]
    target_tags = set(tags_of(target))
    target_terms = terms_of(claim_text(target))

    def related(path: str, row_prefix: str):
        hits = []
        for other in analyze(path, row_prefix)["claims"]:
            if other["id"] == wanted:
                continue
            row = other["row"]
            shared_tags = sorted(target_tags & set(tags_of(row)))
            shared_terms = sorted(target_terms & terms_of(claim_text(row)))
            if not shared_tags and not shared_terms:
                continue
            hits.append({
                "id": other["id"],
                "date": row.get("date", ""),
                "claim": claim_text(row),
                "shared_tags": shared_tags,
                "shared_terms": shared_terms[:4],
                "weight": len(shared_tags) * 2 + len(shared_terms),
            })
        hits.sort(key=lambda hit: (-hit["weight"], hit["date"]))
        return hits[:limit]

    sections = []
    if target_tags and os.path.exists(patterns_path):
        current = None
        try:
            with open(patterns_path) as handle:
                for line in handle:
                    heading = re.match(r"^## (.+)$", line.strip())
                    if heading:
                        current = heading.group(1).strip()
                        continue
                    if current and current in target_tags:
                        text = line.strip().lstrip("- ").strip()
                        if text and target_terms & terms_of(text):
                            sections.append({"section": current, "line": text})
        except OSError:
            pass

    print(json.dumps({
        "lessons": related(lessons_path, "les-"),
        "decisions": related(decisions_path, "dec-"),
        "patterns": sections[:limit],
    }, ensure_ascii=False))
    return 0


def cmd_live_takeaways(argv) -> int:
    """Takeaways for a tag with the retracted ones removed.

    Harvest consolidates lessons into patterns, and a pattern built from a claim
    that has since been retracted keeps injecting the wrongness after the row
    itself stopped rendering. Consolidation reads the living corpus or it
    launders the corpse.
    """
    path, prefix, tag = argv[0], argv[1], argv[2]
    live = []
    for record in analyze(path, prefix)["claims"]:
        if record["retraction"] is not None:
            continue
        if tag not in tags_of(record["row"]):
            continue
        text = claim_text(record["row"])
        if text:
            live.append(text)
    print(json.dumps({"tag": tag, "takeaways": live}, ensure_ascii=False))
    return 0


COMMANDS = {
    "backfill": cmd_backfill,
    "count": cmd_count,
    "resolve": cmd_resolve,
    "correction": cmd_correction,
    "blast-radius": cmd_blast_radius,
    "live-takeaways": cmd_live_takeaways,
}


def main(argv) -> int:
    if not argv or argv[0] not in COMMANDS:
        sys.stderr.write(
            "usage: epistemics.py <%s> [args]\n" % "|".join(sorted(COMMANDS))
        )
        return 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
