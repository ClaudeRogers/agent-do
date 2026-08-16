"""How much memory one blob may carry, and what gets cut first.

Every number in the delivery path used to be somebody's guess, and the guesses
compounded: a top-20 window inside inject, then a 6000-character cut in the
session-start hook, so a store holding 197 rows delivered none of them and said
so with the four words `[zpc inject truncated]`. This module holds the two
answers that replace all of it — where the budget comes from, and what a cut
takes — in one place, so a future guess has nowhere to hide.

THE BUDGET, derived and not chosen
    `max_tokens` is the authority's published size of ONE DELIVERY: the most
    text a model may hand over in a single response. A memory blob is one
    delivery of text into a session, so it gets one delivery's worth. The
    minimum over every record is taken because a session-start hook cannot know
    which model it is feeding, and a bound that holds only on the roomiest model
    is not a bound.

    It is read at call time through agent-do's own resolver (`lib/quantities.py`)
    rather than copied here, so no literal in this repo can go stale against it.
    When the authority cannot be reached there is no ceiling, and none is
    applied: a fallback constant is the exact defect this module exists to end,
    and an oversized blob is a visible fault where a silent cut is not.

THE UNIT, and the chars-vs-tokens problem stated honestly
    The budget arrives in tokens. Text is trimmed in bytes. Nothing converts
    between them, because the authority publishes no bytes-per-token figure and
    a folk constant is a guess wearing a citation.

    What is used instead is a proven inequality. Every token of a byte-level BPE
    tokenizer decodes to at least one byte, so a text of B bytes is at most B
    tokens. Holding the blob to `bytes <= budget_tokens` therefore guarantees
    `tokens <= budget_tokens` for any text, in any encoding, under any such
    tokenizer — no measurement, no constant, no assumption about the language
    the memory happens to be written in.

    The cost is that the bound is conservative: real prose runs several bytes to
    the token, so a blob is held to roughly a quarter of the tokens it was
    allowed. That is the correct direction of error for a ceiling, and it is
    still an order of magnitude more than the 6000 characters it replaces.

THE CUT, ordered by value
    Sections claim the budget in value order and a cut takes whole records from
    the end of a section, never a byte offset. The old cut landed wherever 6000
    characters ran out — inside the boilerplate header, before a single claim —
    which is the worst available ordering: it kept the frame and deleted
    everything the frame was there to introduce.
"""

from __future__ import annotations

import sys
from typing import Any, Iterable


def budget(authority_lib: str) -> dict[str, Any] | None:
    """The smallest single delivery the authority publishes, with its record.

    Returns None when the authority cannot answer — an absent ceiling, never a
    substitute one.
    """
    if not authority_lib:
        return None
    if authority_lib not in sys.path:
        sys.path.insert(0, authority_lib)
    try:
        from quantities import authority_entries
    except Exception:  # noqa: BLE001 - no resolver, no ceiling
        return None
    try:
        entries = [
            entry
            for entry in authority_entries()
            if entry.get("key", "").endswith(".max_tokens")
            and isinstance(entry.get("value"), (int, float))
        ]
    except Exception:  # noqa: BLE001 - unreadable authority, no ceiling
        return None
    if not entries:
        return None
    tightest = min(entries, key=lambda entry: entry["value"])
    return {
        "tokens": int(tightest["value"]),
        "key": tightest["key"],
        "why": (
            "the smallest single delivery published in models.yaml; a blob has to "
            "fit whichever model the session is running on"
        ),
    }


def measured(text: str) -> int:
    """Bytes, which is the unit a token count can be bounded by without a constant."""
    return len(text.encode("utf-8", "surrogatepass"))


# ── rendering claims ──────────────────────────────────────────────────────
#
# One renderer for every blob, so "shorter" can never quietly become "softer".
# Each line carries its date, its age, its kind, and the id you would need to
# argue with it, because a claim delivered as a bare assertion is a claim an
# agent has no handle on.


def render_claim(record, *, bullet: bool = False, tag_label: bool = True,
                 checked: dict | None = None, copies: int = 1) -> str:
    import epistemics

    row = record["row"]
    tags = epistemics.tags_of(row)
    if tags:
        suffix = f"  [tags: {','.join(tags)}]" if tag_label else f"  [{','.join(tags)}]"
    else:
        suffix = ""
    if copies > 1:
        suffix += f"  [x{copies} identical]"
    if record["challenges"]:
        suffix += f"  [challenged: {len(record['challenges'])}]"
    if checked:
        when = checked.get(record["id"])
        if when:
            suffix += f"  [checked: {epistemics.dated(when)}]"
    text = epistemics.claim_text(row) or "(no takeaway recorded)"
    lead = "- " if bullet else ""
    return (
        f"{lead}[{epistemics.dated(row.get('date'))}] {record['id']} "
        f"({epistemics.kind_of(row)}) {text}{suffix}"
    )


def live_claims(path: str, prefix: str = "les-") -> list:
    """Every claim that has not been retracted, oldest first.

    Retracted claims are absent from every rendering. A bounded blob is exactly
    where a withdrawn claim would be least likely to be questioned.
    """
    import epistemics

    return [
        record
        for record in epistemics.analyze(path, prefix)["claims"]
        if record["retraction"] is None
    ]


def render_claims(records, **kwargs) -> tuple[str, dict[str, int]]:
    """Claims newest first, one line each, identical takeaways collapsed.

    Newest first is what makes the cut take the oldest record rather than the
    newest, and it is the whole reason a bound can be applied at all without
    losing the thing worth keeping.

    Collapsing identical takeaways is not cosmetic either. Auto-captured lessons
    repeat verbatim — one real store holds 168 copies of `Error resolved (review
    and enrich this auto-lesson)` against 29 distinct claims — so without the
    collapse a budget is spent almost entirely on one sentence, and the rows
    count is a measure of write volume rather than of knowledge.

    A collapse is a cut like any other, so it carries its magnitude (`[x168
    identical]`). A challenged claim is never collapsed at all — into a twin or
    from one. The challenge was filed against that row under that id, and it is
    the id `zpc retract` takes; merging it into an identical-looking sibling
    would hide the doubt behind the wording it was filed about.
    """
    import epistemics

    rows = list(records)
    lines, index = [], {}
    for record in reversed(rows):
        text = epistemics.claim_text(record["row"])
        if not text:
            continue
        key = (text, record["id"]) if record["challenges"] else text
        if key in index:
            index[key]["copies"] += 1
            continue
        index[key] = {
            "record": record,
            "copies": 1,
            "position": len(index),
        }
    for group in sorted(index.values(), key=lambda item: item["position"]):
        lines.append(render_claim(group["record"], copies=group["copies"], **kwargs))
    return "\n".join(lines), {"rows": len(rows), "distinct": len(lines)}


def render_corrections(records, correction_days: int) -> str:
    """Retractions that name what is true instead, while they are still news.

    The withdrawn wording is deliberately never quoted: a correction that
    repeats the wrong sentence re-injects it, and a skimmer takes the text and
    leaves the frame. The id is the pointer for anyone who needs the original.
    """
    import epistemics
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    lines = []
    for record in records:
        tombstone = record["retraction"]
        if not tombstone or not tombstone.get("takeaway"):
            continue
        stamp = tombstone.get("ts", "")
        try:
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if (now - when).days > correction_days:
            continue
        lines.append(
            f"[{epistemics.dated(stamp[:10])}] {record['id']} corrected to: {tombstone['takeaway']}"
        )
    return "\n".join(lines)


def render_decisions(path: str) -> str:
    """Settled decisions, newest first, each under the id that re-opens it.

    A decision binds until someone re-opens it, which is the difference between
    a decision and a lesson — but it binds under its own id, so re-opening it is
    a command and not an argument.
    """
    import epistemics

    lines = []
    for record in reversed(live_claims(path, "dec-")):
        row = record["row"]
        note = f"  [challenged: {len(record['challenges'])}]" if record["challenges"] else ""
        lines.append(
            f"[{epistemics.dated(row.get('date'))}] {record['id']} "
            f"{row.get('chosen', '?')}: {row.get('rationale', '')}{note}"
        )
    return "\n".join(lines)


def marker(kept: int, total: int, unit: str) -> str:
    """A cut that says how big it was.

    The fact of a cut without its magnitude is a half-receipt: it tells a reader
    something is missing and leaves them no way to ask how much, which reads to
    an agent as completeness with a footnote.
    """
    return f"[truncated: {kept} of {total} {unit} shown]"


def budget_receipt(tokens: int, origin: str) -> str:
    """Where the ceiling that just cut something came from.

    It reports the budget actually applied, never the one that would have been:
    a caller who passes --max-tokens and reads the authority's figure back has
    been handed a receipt for a cut that did not happen that way.
    """
    return (
        f"[budget: {tokens} tokens from {origin}, "
        f"held in bytes because no token is shorter than one byte]"
    )


def resolve(authority_lib: str, override: str) -> tuple[int | None, str]:
    """The budget in force, and what to credit it to."""
    if override:
        return int(override), "--max-tokens"
    found = budget(authority_lib)
    return (found["tokens"], found["key"]) if found else (None, "")


def receipt_reserve(tokens: int | None, origin: str) -> int:
    """Room the blob owes its own receipt, charged before anything is laid out."""
    if not tokens:
        return 0
    return measured(budget_receipt(tokens, origin)) + 2


def fit(sections: Iterable[dict[str, Any]], budget_bytes: int | None,
        reserve: int = 0) -> dict[str, Any]:
    """Fit sections to a budget, cutting whole records from the least valuable end.

    `sections` are dicts of `key`, `header`, `body`, `unit`, and `protected`,
    listed in value order.

    Protected sections are charged whole and never trimmed: the tie-breaker law
    and the baseline counts are the frame a reader judges everything else
    through, so spending them to fit another claim inverts the point.

    THE ALLOCATION, and why it is not a priority queue. Strict priority hands the
    first section everything it wants before the second gets a byte, which is the
    original bug in miniature: a project profile of "(not yet documented)"
    headings ahead of the claims consumed the whole budget and delivered no
    memory at all. Round-robin instead — one record per section per turn, in
    value order — so no section can starve another, and each section still loses
    its own least valuable records first because each is ordered before it gets
    here. It also needs no ratio: the 60/40 patterns-versus-lessons split this
    replaced was doing real work holding starvation off, and it was still a
    number nobody derived.

    `reserve` is room held back for text the assembled blob will carry but this
    function does not lay out — the budget receipt. A ceiling that does not
    charge for its own receipt is a ceiling the blob quietly exceeds.

    A budget of None means the authority could not answer, so nothing is cut.
    """
    prepared = []
    for section in sections:
        body = str(section.get("body") or "")
        prepared.append({
            "key": str(section.get("key") or section.get("header") or ""),
            "header": str(section.get("header") or ""),
            "unit": str(section.get("unit") or "lines"),
            "protected": bool(section.get("protected")),
            "lines": body.splitlines(),
            "kept": [],
        })

    if budget_bytes is None:
        for item in prepared:
            item["kept"] = list(item["lines"])
        return _blocks(prepared, False, None)

    remaining = budget_bytes - reserve
    for item in prepared:
        if item["protected"]:
            item["kept"] = list(item["lines"])
            remaining -= _cost(item["header"], item["lines"])

    competing = [item for item in prepared if not item["protected"]]
    # A section that will show anything needs its header, and a section that
    # shows nothing still needs one to hang its marker from.
    for item in competing:
        remaining -= measured(item["header"]) + 2

    # A section that cannot fit its next record is retired rather than skipped
    # past. Each section therefore keeps a contiguous prefix of its own ordered
    # records, which is what makes "the cut took the oldest" true and the
    # marker's `kept of total` mean what it says. Skipping one long record to
    # squeeze in a shorter one behind it would leave a hole nothing discloses.
    active = [item for item in competing if item["lines"]]
    while active:
        placed = False
        for item in list(active):
            index = len(item["kept"])
            if index >= len(item["lines"]):
                active.remove(item)
                continue
            step = measured(item["lines"][index]) + 1
            if step > remaining:
                active.remove(item)
                continue
            item["kept"].append(item["lines"][index])
            remaining -= step
            placed = True
        if not placed:
            break

    # The marker costs bytes too, and a marker that overflows would be a cut
    # with no receipt. It is paid for out of the section that is being cut.
    for item in competing:
        if len(item["kept"]) == len(item["lines"]):
            continue
        note = marker(len(item["kept"]), len(item["lines"]), item["unit"])
        remaining -= measured(note) + 1
        while remaining < 0 and item["kept"]:
            remaining += measured(item["kept"].pop()) + 1
            remaining += measured(note) + 1
            note = marker(len(item["kept"]), len(item["lines"]), item["unit"])
            remaining -= measured(note) + 1
        item["marker"] = note

    return _blocks(prepared, True, remaining)


def _cost(header: str, lines: list[str]) -> int:
    return measured(header) + 2 + sum(measured(line) + 1 for line in lines)


def _blocks(prepared: list[dict[str, Any]], bounded: bool, remaining: int | None) -> dict[str, Any]:
    blocks = []
    for item in prepared:
        cut = bounded and not item["protected"] and len(item["kept"]) < len(item["lines"])
        body = list(item["kept"])
        if cut:
            body.append(item["marker"])
        blocks.append({
            "key": item["key"],
            "header": item["header"],
            "body": "\n".join(body),
            "kept": len(item["kept"]),
            "total": len(item["lines"]),
            "unit": item["unit"],
            "cut": cut,
        })
    return {
        "blocks": blocks,
        "cut": any(block["cut"] for block in blocks),
        "remaining": remaining,
    }


def assemble(fitted: dict[str, Any], order: list[str],
             budget_tokens: int | None, origin: str) -> str:
    """Render fitted blocks in reading order, with the budget's receipt if it bit.

    Value order and reading order are different questions. The budget is spent in
    value order so a cut takes the least valuable records; the blob is read in
    the order that makes it legible. Keying the blocks lets both be true at once.
    """
    by_key = {block["key"]: block for block in fitted["blocks"]}
    parts: list[str] = []
    for key in order:
        block = by_key.get(key)
        if block is None or not block["body"].strip():
            continue
        parts.append(f"{block['header']}\n{block['body']}" if block["header"] else block["body"])
    text = "\n\n".join(parts)
    if fitted["cut"] and budget_tokens:
        text = f"{text}\n\n{budget_receipt(budget_tokens, origin)}"
    return text
