#!/usr/bin/env python3
"""Regression tests for installed global hooks that must stay advisory-only.

These tests are intentionally tolerant for public checkouts: if the user's
global hook files are not installed, the test exits successfully.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


HOME = Path.home()
ROOT = Path(__file__).resolve().parents[1]
CODEX_STOP = HOME / ".codex" / "hooks" / "stop-quality-gate.py"
CODEX_PROMPT_ROUTER = HOME / ".codex" / "hooks" / "agent-do-prompt-router.py"
CLAUDE_PROMPT_ROUTER = HOME / ".claude" / "hooks" / "agent-do-prompt-router.py"
PRETOOL_HOOK = ROOT / "hooks" / "claude" / "agent-do-pretooluse-check.py"
TOUCH_LEDGER = ROOT / "hooks" / "claude" / "agent-do-touch-ledger.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_hook(path: Path, payload: dict, cwd: Path | None = None, home: Path | None = None,
             env_extra: dict[str, str] | None = None) -> dict:
    env = os.environ.copy()
    if home is not None:
        env["HOME"] = str(home)
    env["AGENT_DO_REPO"] = str(ROOT)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        ["python3", str(path)],
        cwd=str(cwd) if cwd else None,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    require(proc.returncode == 0, f"{path} failed: {proc.stderr}")
    if not proc.stdout.strip():
        return {}
    return json.loads(proc.stdout)


def assert_not_blocking(payload: dict, label: str) -> None:
    require(payload.get("decision") != "block", f"{label} emitted decision:block: {payload}")
    require(payload.get("continue") is not False, f"{label} emitted continue:false: {payload}")


def ledger_hook_registered() -> bool:
    try:
        return "agent-do-touch-ledger" in (HOME / ".codex" / "hooks.json").read_text()
    except OSError:
        return False


def test_codex_stop_is_advisory() -> None:
    """The Stop gate advises, never blocks — and it attributes UI work to the
    agent's own edits (the touch ledger), not to worktree drift."""
    if not CODEX_STOP.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
        ui_file = repo / "app" / "page.tsx"
        ui_file.parent.mkdir(parents=True)
        ui_file.write_text("export default function Page() { return <main>Hello</main>; }\n")
        # Isolate the ledger under a temp AGENT_DO_HOME and make sure no live
        # browser session answers, so the advisory path is deterministic.
        extra = {"AGENT_DO_HOME": str(Path(tmp) / "home"), "AGENT_BROWSER_SESSION": "no-such-session-for-test"}
        session = {"cwd": str(repo), "session_id": "stop-gate-advisory-test"}

        if ledger_hook_registered():
            # Worktree drift alone is not evidence: no ledger entry, no advisory.
            drift = run_hook(CODEX_STOP, session, cwd=repo, env_extra=extra)
            assert_not_blocking(drift, "codex stop hook (drift)")
            require("systemMessage" not in drift, f"un-ledgered worktree drift must not raise a UI advisory: {drift}")

        # The agent's own edit, recorded by the touch ledger, is evidence.
        run_hook(TOUCH_LEDGER, {**session, "tool_name": "Write",
                                "tool_input": {"file_path": "app/page.tsx", "content": "x"}},
                 cwd=repo, env_extra=extra)
        payload = run_hook(CODEX_STOP, session, cwd=repo, env_extra=extra)
        assert_not_blocking(payload, "codex stop hook")
        require(payload.get("continue") is True, f"codex stop hook should continue: {payload}")
        require("systemMessage" in payload, f"codex stop hook should emit advisory context: {payload}")


def test_prompt_router_hooks_are_advisory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        for label, hook in (
            ("codex prompt router", CODEX_PROMPT_ROUTER),
            ("claude prompt router", CLAUDE_PROMPT_ROUTER),
        ):
            if not hook.exists():
                continue
            payload = run_hook(hook, {"prompt": "continue", "session_id": "test-session"}, home=home)
            assert_not_blocking(payload, label)
            require("hookSpecificOutput" in payload, f"{label} should emit context: {payload}")


def test_pretool_safety_headsup_for_destructive_agent_do() -> None:
    """An agent-do call resolving to a destructive/sensitive verb gets an
    advisory safety heads-up — never a block."""
    if not PRETOOL_HOOK.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        # manna delete is destructive; the hook should surface that, advisory-only.
        payload = run_hook(
            PRETOOL_HOOK,
            {"tool_name": "Bash", "tool_input": {"command": "agent-do manna delete mn-abc123"},
             "session_id": "safety-test"},
            home=home,
        )
        assert_not_blocking(payload, "pretool safety heads-up")
        ctx = json.dumps(payload).lower()
        require("destructive" in ctx, f"destructive agent-do call must surface safety: {payload}")

        # A read verb gets no safety heads-up (nothing to warn about).
        read_payload = run_hook(
            PRETOOL_HOOK,
            {"tool_name": "Bash", "tool_input": {"command": "agent-do manna list"},
             "session_id": "safety-test-2"},
            home=home,
        )
        assert_not_blocking(read_payload, "pretool read no-warn")
        require(
            "destructive" not in json.dumps(read_payload).lower(),
            f"read verb must not raise a destructive warning: {read_payload}",
        )


def main() -> int:
    test_codex_stop_is_advisory()
    test_prompt_router_hooks_are_advisory()
    test_pretool_safety_headsup_for_destructive_agent_do()
    print("global hook nonblocking tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
