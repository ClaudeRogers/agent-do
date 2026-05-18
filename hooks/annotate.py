#!/usr/bin/env python3
"""Claude Code UserPromptSubmit hook: capture #tag:word and #note annotations."""
import json, sys, re
from datetime import datetime, timezone
from pathlib import Path

ANNOTATIONS_DIR = Path.home() / ".local/share/agent-sessions/annotations"
TAG_RE = re.compile(r'#tag:([\w-]+)')
NOTE_RE = re.compile(r'#note\s+(.*?)(?=\s*#tag:|\s*$)', re.DOTALL)

def parse_annotations(prompt):
    annotations = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for m in TAG_RE.finditer(prompt):
        annotations.append({"ts": ts, "type": "tag", "value": m.group(1)})
    for m in NOTE_RE.finditer(prompt):
        text = m.group(1).strip()
        if text:
            annotations.append({"ts": ts, "type": "note", "value": text})
    return annotations

def strip_annotations(prompt):
    result = TAG_RE.sub('', prompt)
    result = NOTE_RE.sub('', result)
    result = re.sub(r'#note\s*$', '', result)
    return result.strip()

def save_annotations(session_id, annotations):
    ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)
    fpath = ANNOTATIONS_DIR / f"{session_id}.json"
    data = {"session_id": session_id, "annotations": []}
    if fpath.exists():
        try:
            data = json.loads(fpath.read_text())
        except (json.JSONDecodeError, KeyError):
            pass
    data.setdefault("annotations", []).extend(annotations)
    fpath.write_text(json.dumps(data, indent=2) + "\n")

def summarize(annotations):
    parts = []
    for a in annotations:
        if a["type"] == "tag":
            parts.append(f"tag:{a['value']}")
        else:
            parts.append("note")
    return ", ".join(parts)

def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    prompt = payload.get("prompt", "")
    session_id = payload.get("session_id", "unknown")
    annotations = parse_annotations(prompt)
    if not annotations:
        return
    save_annotations(session_id, annotations)
    remaining = strip_annotations(prompt)
    context = (
        "The user's message contains #tag and #note markup for bookmarking purposes. "
        f"Saved: {summarize(annotations)}. "
    )
    if not remaining:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context + "The prompt contains no separate task; acknowledge briefly and do not invent work."
            }
        }
    else:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context + "Ignore that markup and respond only to the actual content."
            }
        }
    json.dump(output, sys.stdout)

if __name__ == "__main__":
    main()
