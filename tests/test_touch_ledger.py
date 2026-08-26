"""The touch ledger and the Stop gate's use of it.

The contract under test: a Stop-time UI advisory may fire only when THIS
agent's edit tools touched a design-classified file this turn — never because
the worktree drifted (another lane, a dropped-in document, untracked files).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "lib"
HOOK = REPO / "hooks" / "claude" / "agent-do-touch-ledger.py"
GATE = REPO / "hooks" / "codex" / "stop-quality-gate.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DO_HOME", str(tmp_path / "home"))
    for env in ("CLAUDE_SESSION_ID", "CODEX_THREAD_ID", "AGENT_DO_COORD_SESSION"):
        monkeypatch.delenv(env, raising=False)
    sys.modules.pop("touch_ledger", None)
    return _load("touch_ledger", LIB / "touch_ledger.py")


def test_claude_edit_payload_is_recorded(ledger, tmp_path):
    payload = {"session_id": "sess-A", "cwd": str(tmp_path), "tool_name": "Edit",
               "tool_input": {"file_path": str(tmp_path / "src/app/page.tsx"), "old_string": "a", "new_string": "b"}}
    recorded = ledger.record(payload)
    assert recorded == [str((tmp_path / "src/app/page.tsx").resolve())]
    entries = ledger.read_and_consume("sess-A")
    assert [e["path"] for e in entries] == recorded
    assert entries[0]["tool"] == "Edit"
    # Consumed: the next Stop sees nothing.
    assert ledger.read_and_consume("sess-A") == []


def test_codex_apply_patch_paths_are_parsed(ledger, tmp_path):
    patch = ("*** Begin Patch\n*** Update File: components/Hero.tsx\n@@\n-a\n+b\n"
             "*** Add File: styles/tokens.css\n+:root{}\n*** End Patch\n")
    payload = {"session_id": "sess-B", "cwd": str(tmp_path), "tool_name": "apply_patch", "tool_input": {"patch": patch}}
    recorded = ledger.record(payload)
    assert recorded == [str((tmp_path / "components/Hero.tsx").resolve()),
                        str((tmp_path / "styles/tokens.css").resolve())]


def test_shell_redirect_targets_are_recorded_but_devnull_is_not(ledger, tmp_path):
    payload = {"session_id": "sess-C", "cwd": str(tmp_path), "tool_name": "Bash",
               "tool_input": {"command": "cat > index.html <<'EOF'\n<p>x</p>\nEOF\nls > /dev/null 2>&1"}}
    recorded = ledger.record(payload)
    assert recorded == [str((tmp_path / "index.html").resolve())]


def test_non_edit_tools_record_nothing(ledger, tmp_path):
    for tool in ("Read", "Glob", "Grep", "WebFetch"):
        payload = {"session_id": "sess-D", "cwd": str(tmp_path), "tool_name": tool,
                   "tool_input": {"file_path": str(tmp_path / "src/app/page.tsx")}}
        assert ledger.record(payload) == []
    assert not ledger.ledger_path("sess-D").exists()


def test_session_key_degrades_identically_without_ids(ledger, tmp_path):
    writer = ledger.session_key({"cwd": str(tmp_path)})
    reader = ledger.session_key({"cwd": str(tmp_path)})
    assert writer == reader
    assert writer[1] == "cwd"
    assert ledger.session_key({"session_id": "abc/def"}) == ("abc-def", "session")


def test_hook_script_writes_ledger_end_to_end(ledger, tmp_path):
    env = dict(os.environ, AGENT_DO_HOME=str(tmp_path / "home"))
    payload = {"session_id": "sess-E", "cwd": str(tmp_path), "tool_name": "Write",
               "tool_input": {"file_path": "docs/guide.html", "content": "<p>"}}
    proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), text=True,
                          capture_output=True, env=env, timeout=20)
    assert proc.returncode == 0 and proc.stdout == ""
    entries = ledger.read_and_consume("sess-E")
    assert [e["path"] for e in entries] == [str((tmp_path / "docs/guide.html").resolve())]


@pytest.fixture
def gate(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DO_HOME", str(tmp_path / "home"))
    for env in ("CLAUDE_SESSION_ID", "CODEX_THREAD_ID", "AGENT_DO_COORD_SESSION"):
        monkeypatch.delenv(env, raising=False)
    sys.modules.pop("touch_ledger", None)
    sys.path.insert(0, str(LIB))
    module = _load("stop_quality_gate", GATE)
    sys.path.pop(0)
    return module


def _git_repo(path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def test_gate_uses_ledger_not_worktree_drift(gate, tmp_path, monkeypatch):
    repo = _git_repo(tmp_path / "repo")
    # Worktree drift the agent did NOT cause: an untracked document and an untracked UI file.
    (repo / ".handoff").mkdir()
    (repo / ".handoff" / "source.html").write_text("<p>archived text</p>")
    (repo / "index.html").write_text("<p>someone else's page</p>")
    monkeypatch.setattr(gate, "ledger_registered", lambda: True)
    files, evidence = gate.changed_files_for_gate(str(repo), {"session_id": "sess-G", "cwd": str(repo)})
    assert evidence == "ledger"
    assert files == []  # nothing in the ledger → nothing attributed to this agent


def test_gate_fires_only_on_ledgered_ui_files(gate, tmp_path, monkeypatch):
    repo = _git_repo(tmp_path / "repo")
    (repo / "src").mkdir()
    (repo / "src" / "page.tsx").write_text("export default 1")
    monkeypatch.setattr(gate, "ledger_registered", lambda: True)
    gate.touch_ledger.record({"session_id": "sess-H", "cwd": str(repo), "tool_name": "Edit",
                              "tool_input": {"file_path": "src/page.tsx"}})
    files, evidence = gate.changed_files_for_gate(str(repo), {"session_id": "sess-H", "cwd": str(repo)})
    assert evidence == "ledger"
    assert files == ["src/page.tsx"]
    assert gate.ui_files(files) == ["src/page.tsx"]
    # Consumed: the following Stop attributes nothing.
    files2, _ = gate.changed_files_for_gate(str(repo), {"session_id": "sess-H", "cwd": str(repo)})
    assert files2 == []


def test_gate_falls_back_to_worktree_when_ledger_hook_unregistered(gate, tmp_path, monkeypatch):
    repo = _git_repo(tmp_path / "repo")
    (repo / "index.html").write_text("<p>page</p>")
    monkeypatch.setattr(gate, "ledger_registered", lambda: False)
    files, evidence = gate.changed_files_for_gate(str(repo), {"session_id": "sess-I", "cwd": str(repo)})
    assert evidence == "worktree"
    assert files == ["index.html"]
