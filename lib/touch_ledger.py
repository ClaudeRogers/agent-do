"""Touch ledger: which files THIS agent's edit tools touched, per session.

The failure this exists for: a Stop-time quality gate that infers "the agent
did design work" from `git status`. Worktree drift is not agent action — it
includes another lane's edits, a file the human dropped in, and anything
untracked that was already there. Every one of those produced a false
"UI files changed without a browser session" advisory, with advice that could
not be followed because there was no app to open.

The honest condition is: this agent actually edited a design-classified file.
A PostToolUse hook knows exactly that — tool name and file path, per call —
so it appends a line here, keyed by session. The Stop gate reads the ledger
for its own session and consumes it, so the nag means "you changed this file
THIS TURN and have not looked at it", and it says so once.

Shared by hooks/claude/agent-do-touch-ledger.py (writer, both runtimes) and
hooks/codex/stop-quality-gate.py (reader). Imports nothing from the repo.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

AGENT_DO_HOME = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))
LEDGER_DIR = AGENT_DO_HOME / "hooks" / "touched"

# Ledgers are consumed at Stop on runtimes that have a gate; on runtimes that
# do not, a session's file outlives its session and nothing tells this module
# the session ended. A week is longer than any session that could still be
# writing to the same ledger, so older files are dead and swept on write.
SWEEP_AFTER_SECONDS = 7 * 24 * 3600

# The session key becomes a filename component. POSIX NAME_MAX is 255 bytes
# and the longest real id this sees is a 36-char UUID or an opaque Codex thread
# id of similar size; 64 holds any of them with the ".jsonl" suffix to spare
# while guaranteeing the component never approaches the filesystem limit.
KEY_MAX_CHARS = 64

# When no session id exists the key degrades to a digest of the working
# directory. 16 hex characters is 64 bits — collisions among one user's
# working directories are not a realistic concern, and the key stays short.
CWD_DIGEST_HEX_CHARS = 16

# Tool names that edit a file and carry its path directly in tool_input.
_PATH_TOOLS = {
    "edit", "write", "multiedit", "notebookedit",
    "str_replace_editor", "str_replace_based_edit_tool",
    "create_file", "write_file", "edit_file", "write_to_file",
}
_PATH_KEYS = ("file_path", "path", "notebook_path", "filename", "filePath", "target_file")

# Codex edits through apply_patch; the patch text names its files.
_PATCH_TOOLS = {"apply_patch", "applypatch", "apply-patch"}
_PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$", re.M)
_PATCH_MOVE_RE = re.compile(r"^\*\*\* Move to: (.+?)\s*$", re.M)

# Shell writes: `> path`, `>> path`, `tee path`, `tee -a path`. Heuristic and
# bounded — only redirect targets that look like files (an extension or a
# slash) count, so `2>&1` and `> /dev/null` never do.
_SHELL_TOOLS = {"bash", "shell", "exec", "run_terminal_cmd", "terminal", "execute_command", "local_shell"}
_REDIRECT_RE = re.compile(r"(?:>>?|\btee\b(?:\s+-a)?)\s*(['\"]?)([^\s'\"|;&<>]+)\1")
_FILE_LIKE_RE = re.compile(r"(?:/|\.[A-Za-z0-9]{1,8}$)")


def _sanitize(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return cleaned[:KEY_MAX_CHARS] or "unknown"


def session_key(payload: dict) -> tuple[str, str]:
    """Return (key, scope). scope is 'session' when a real session id was
    found, 'cwd' when the key degraded to the working directory — both the
    writer and the reader degrade the same way, so they still agree."""
    for field in ("session_id", "thread_id", "conversation_id"):
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            return _sanitize(value), "session"
    for env in ("CLAUDE_SESSION_ID", "CODEX_THREAD_ID", "AGENT_DO_COORD_SESSION"):
        value = os.environ.get(env)
        if value and value.strip():
            return _sanitize(value), "session"
    cwd = payload.get("cwd") or os.getcwd()
    digest = hashlib.sha1(str(cwd).encode("utf-8")).hexdigest()[:CWD_DIGEST_HEX_CHARS]
    return f"cwd-{digest}", "cwd"


def ledger_path(key: str) -> Path:
    return LEDGER_DIR / f"{key}.jsonl"


def _as_text(tool_input) -> str:
    if isinstance(tool_input, str):
        return tool_input
    if isinstance(tool_input, dict):
        for field in ("patch", "input", "content", "command", "cmd"):
            value = tool_input.get(field)
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                return " ".join(str(part) for part in value)
        return json.dumps(tool_input)
    if isinstance(tool_input, list):
        return " ".join(str(part) for part in tool_input)
    return str(tool_input or "")


def extract_paths(tool_name: str, tool_input) -> list[str]:
    """Paths an edit tool call touched, as written (may be relative)."""
    name = (tool_name or "").strip().lower()
    paths: list[str] = []
    if name in _PATH_TOOLS and isinstance(tool_input, dict):
        for field in _PATH_KEYS:
            value = tool_input.get(field)
            if isinstance(value, str) and value.strip():
                paths.append(value.strip())
                break
    elif name in _PATCH_TOOLS:
        text = _as_text(tool_input)
        paths.extend(m.group(1) for m in _PATCH_FILE_RE.finditer(text))
        paths.extend(m.group(1) for m in _PATCH_MOVE_RE.finditer(text))
    elif name in _SHELL_TOOLS:
        text = _as_text(tool_input)
        for match in _REDIRECT_RE.finditer(text):
            target = match.group(2)
            if target.startswith("&") or target.startswith("/dev/"):
                continue
            if _FILE_LIKE_RE.search(target):
                paths.append(target)
    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def _sweep_stale() -> None:
    try:
        now = time.time()
        for entry in LEDGER_DIR.iterdir():
            if entry.suffix == ".jsonl" and now - entry.stat().st_mtime > SWEEP_AFTER_SECONDS:
                entry.unlink()
    except OSError:
        pass


def record(payload: dict, runtime: str = "") -> list[str]:
    """Append the files this tool call touched. Returns the absolute paths
    recorded (empty when the tool was not an edit)."""
    tool_name = payload.get("tool_name") or payload.get("tool") or ""
    tool_input = payload.get("tool_input")
    if tool_input is None:
        tool_input = payload.get("input") or payload.get("arguments") or {}
    raw_paths = extract_paths(tool_name, tool_input)
    if not raw_paths:
        return []
    cwd = payload.get("cwd") or os.getcwd()
    key, scope = session_key(payload)
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    _sweep_stale()
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    recorded: list[str] = []
    with ledger_path(key).open("a", encoding="utf-8") as handle:
        for raw in raw_paths:
            absolute = str(Path(cwd, os.path.expanduser(raw)).resolve()) if not os.path.isabs(raw) else str(Path(raw).resolve())
            recorded.append(absolute)
            handle.write(json.dumps({
                "ts": stamp,
                "runtime": runtime or os.environ.get("AGENT_DO_HOOK_RUNTIME", ""),
                "tool": tool_name,
                "path": absolute,
                "cwd": str(cwd),
                "scope": scope,
            }) + "\n")
    return recorded


def read_and_consume(key: str) -> list[dict]:
    """Return every entry for the session, then truncate the ledger so the
    next Stop only sees what was touched after this one."""
    path = ledger_path(key)
    if not path.exists():
        return []
    entries: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        path.write_text("", encoding="utf-8")
    except OSError:
        return entries
    return entries


def hook_registered(runtime: str) -> bool:
    """Whether the touch-ledger hook is registered for this runtime — the
    difference between 'no edits this turn' and 'nobody is writing ledgers'.
    The reader must know which, because only the second justifies falling
    back to worktree drift."""
    candidates = {
        "codex": [Path.home() / ".codex" / "hooks.json"],
        "claude": [Path(os.environ.get("CLAUDE_SETTINGS_PATH", Path.home() / ".claude" / "settings.json"))],
        "cursor": [Path.home() / ".cursor" / "hooks.json"],
    }.get(runtime, [])
    for candidate in candidates:
        try:
            if "agent-do-touch-ledger" in candidate.read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False
