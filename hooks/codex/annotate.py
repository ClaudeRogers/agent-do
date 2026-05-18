#!/usr/bin/env python3
"""Codex UserPromptSubmit hook: capture #tag:word and #note annotations."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ANNOTATIONS_DIR = Path.home() / ".local/share/agent-sessions/annotations"
TAG_RE = re.compile(r"#tag:([\w-]+)")
NOTE_RE = re.compile(r"#note\s+(.*?)(?=\s*#tag:|\s*$)", re.DOTALL)


def parse_annotations(prompt: str) -> list[dict[str, str]]:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    annotations: list[dict[str, str]] = []
    for match in TAG_RE.finditer(prompt):
        annotations.append({"ts": ts, "type": "tag", "value": match.group(1)})
    for match in NOTE_RE.finditer(prompt):
        text = match.group(1).strip()
        if text:
            annotations.append({"ts": ts, "type": "note", "value": text})
    return annotations


def strip_annotations(prompt: str) -> str:
    result = TAG_RE.sub("", prompt)
    result = NOTE_RE.sub("", result)
    result = re.sub(r"#note\s*$", "", result)
    return result.strip()


def save_annotations(session_id: str, annotations: list[dict[str, str]]) -> None:
    ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = ANNOTATIONS_DIR / f"{session_id}.json"
    data = {"session_id": session_id, "annotations": []}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except Exception:
            pass
    data.setdefault("annotations", []).extend(annotations)
    path.write_text(json.dumps(data, indent=2) + "\n")


def summarize(annotations: list[dict[str, str]]) -> str:
    return ", ".join(
        f"tag:{item['value']}" if item["type"] == "tag" else "note"
        for item in annotations
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    prompt = payload.get("prompt") or ""
    annotations = parse_annotations(prompt)
    if not annotations:
        return
    save_annotations(payload.get("session_id") or "unknown", annotations)
    context = (
        "The user's prompt included #tag/#note annotation markup. "
        f"Saved: {summarize(annotations)}. "
    )
    if not strip_annotations(prompt):
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context
                    + "The prompt contains no separate task; acknowledge briefly and do not invent work.",
                }
            },
            sys.stdout,
        )
        return
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context + "Ignore the annotation markup and respond only to the actual content.",
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
