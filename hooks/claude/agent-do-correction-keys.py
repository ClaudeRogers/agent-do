#!/usr/bin/env python3
"""
UserPromptSubmit hook: one-keystroke correction keys.

Correcting the assistant should cost one keystroke, and every press should
leave a receipt. When the entire prompt is one registered key, this hook
expands it into explicit context for the model and appends a row to
`<AGENT_DO_HOME>/zpc/corrections.jsonl`.

This is an exact command vocabulary, the way vim keys are: the whole prompt
must BE the key (optionally one space and a short note). It never inspects
prose, never matches substrings, and never guesses intent. Anything that is
not an exact key press is not this hook's business, and it exits 0 in silence.

Stdlib only, no subprocesses: a correction must expand in milliseconds, and a
missing repo library must never cost the user their keystroke.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# One map, one place. The key is the whole command; `meaning` states what the
# press asserts about the previous turn, `asks_for` states what the user is
# now asking for. Both are rendered as facts about the user's request, never
# as out-of-band instructions to the model.
CORRECTION_KEYS = {
    "w": {
        "label": "too wordy",
        "meaning": "the previous answer was too wordy",
        "asks_for": (
            "the same answer again, kernel first: the load-bearing claim in the "
            "opening sentence, about five lines total, no preamble and no flourish"
        ),
    },
    "d": {
        "label": "go deeper",
        "meaning": "the previous answer stayed too shallow",
        "asks_for": (
            "the core of that same answer expanded with specifics (mechanism, "
            "numbers, names, file:line evidence), without restating what was "
            "already said"
        ),
    },
    "s": {
        "label": "subtraction form",
        "meaning": "the previous answer would land better inverted",
        "asks_for": (
            "the same answer re-cast in subtraction form: what breaks when the "
            "thing is removed, in the order the breakages arrive"
        ),
    },
}

# A keyed correction is a keystroke plus at most a few words. Longer text after
# the key is prose, not a command, and prose is out of scope by design.
MAX_NOTE_CHARS = 200

AGENT_DO_HOME = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))
RECEIPT_PATH = AGENT_DO_HOME / "zpc" / "corrections.jsonl"


def disabled() -> bool:
    return os.environ.get("AGENT_DO_CORRECTION_KEYS", "").strip() == "0"


def parse_key_press(prompt: str) -> tuple[str, str] | None:
    """Return (key, note) when the prompt is exactly one registered key press.

    Exact means exact: a single-line prompt whose first whitespace-delimited
    token is a registered key, with nothing after it but an optional short
    note. Everything else returns None.
    """
    if not isinstance(prompt, str):
        return None

    text = prompt.strip()
    if not text or "\n" in text or "\r" in text:
        return None
    if text.startswith("/"):
        return None

    key, _, note = text.partition(" ")
    if key not in CORRECTION_KEYS:
        return None

    note = note.strip()
    if len(note) > MAX_NOTE_CHARS:
        return None

    return key, note


def build_context(key: str, note: str) -> str:
    entry = CORRECTION_KEYS[key]
    lines = [
        f"## Correction key: `{key}` ({entry['label']})",
        "",
        f"The user's entire message was `{key}`, a deliberate press from a fixed "
        "correction vocabulary (`w` too wordy, `d` go deeper, `s` subtraction form). "
        "It is a correction of the previous turn, not a new question and not a "
        "message to answer literally.",
        "",
        f"The press says {entry['meaning']}.",
        f"The user is asking for {entry['asks_for']}.",
    ]
    if note:
        lines += ["", f'The user added a note with the key: "{note}".']
    lines += [
        "",
        "Deliver the corrected answer directly. Do not explain the key, do not "
        "acknowledge the correction, and do not ask what was meant.",
    ]
    return "\n".join(lines) + "\n"


def log_receipt(key: str, note: str, cwd: str) -> None:
    """Append the press to the corrections journal. Never blocks the turn.

    Every failure here (unwritable home, read-only file, full disk) is
    swallowed: a lost receipt is a lost data point, while a raised exception
    would cost the user the correction itself.
    """
    row = {
        "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "key": key,
        "note": note,
        "cwd": cwd,
    }
    try:
        RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with RECEIPT_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
    except Exception:
        pass


def main() -> None:
    if disabled():
        sys.exit(0)

    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if not isinstance(input_data, dict):
        sys.exit(0)

    press = parse_key_press(input_data.get("prompt", ""))
    if press is None:
        sys.exit(0)

    key, note = press
    cwd = input_data.get("cwd")
    cwd = cwd if isinstance(cwd, str) else ""

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": build_context(key, note),
                }
            }
        )
    )

    log_receipt(key, note, cwd)
    sys.exit(0)


if __name__ == "__main__":
    main()
