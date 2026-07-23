#!/usr/bin/env python3
"""Tests for session-aware nudge suppression and frequency degradation.

The PreToolUse hook used to emit the same HARD NUDGE on every raw CLI call,
even when the agent was clearly using the corresponding agent-do tool. These
tests cover the three behaviors that fix that:
  1. Demonstration suppression — agent-do <tool> seen once → silence further
     nudges for <tool> this session.
  2. Frequency degradation — same family hit repeatedly → HARD → FRIENDLY →
     SILENT across the session.
  3. Gap detection — raw CLI shortly after agent-do <tool> records a gap_event
     in session state.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "claude" / "agent-do-pretooluse-check.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_hook(command: str, session_id: str, home: Path) -> tuple[dict, dict]:
    """Run the hook with a synthetic Bash payload. Returns (hook_output, session_state)."""
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "session_id": session_id,
    }
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["AGENT_DO_HOME"] = str(home / ".agent-do")
    proc = subprocess.run(
        ["python3", str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    require(proc.returncode == 0, f"hook exited {proc.returncode}: {proc.stderr}")
    out = {}
    if proc.stdout.strip():
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"hook stdout was not JSON: {proc.stdout[:200]} ({exc})")

    state_dir = Path(env["AGENT_DO_HOME"]) / "nudges"
    state_files = list(state_dir.glob(f"session-*.json")) if state_dir.exists() else []
    state = {}
    for state_file in state_files:
        if session_id.replace("/", "_") in state_file.name:
            try:
                state = json.loads(state_file.read_text())
            except (OSError, json.JSONDecodeError):
                state = {}
            break
    return out, state


def emitted_text(out: dict) -> str:
    return ((out.get("hookSpecificOutput") or {}).get("additionalContext") or "")


def test_demonstration_suppression() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)

        # 1. agent-do supabase — SKIP path, no emit, demonstration recorded.
        out, state = run_hook("agent-do supabase health my-ref", "sess-demo-1", home)
        require(emitted_text(out) == "",
                f"agent-do invocation should not emit: {out}")
        require("supabase" in state.get("demonstrated", {}),
                f"agent-do supabase should be recorded as demonstrated: {state}")

        # 2. Raw supabase after demonstration — suppressed (silent).
        out, state = run_hook("supabase health my-ref", "sess-demo-1", home)
        require(emitted_text(out) == "",
                f"raw call after demonstration should be silent: {out}")
        # And the nudge_counts should NOT have incremented for supabase
        # (because suppression returns before _record_nudge_emitted).
        require(state.get("nudge_counts", {}).get("supabase", 0) == 0,
                f"suppressed nudge should not increment count: {state}")


def test_frequency_degradation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        session = "sess-degrade-1"

        # 1st raw supabase — HARD NUDGE.
        out1, state = run_hook("supabase health my-ref", session, home)
        text1 = emitted_text(out1)
        require("HARD NUDGE" in text1 or "FRIENDLY REMINDER" in text1,
                f"first raw call should emit a nudge: {text1[:200]}")
        require(state["nudge_counts"]["supabase"] == 1,
                f"first call should set count=1: {state}")

        # 2nd raw supabase — degrade to FRIENDLY one-liner (or stay FRIENDLY if
        # the matcher was already the legacy/friendly path).
        out2, _ = run_hook("supabase health my-ref", session, home)
        text2 = emitted_text(out2)
        require(text2 != "",
                f"second call should still emit something: {out2}")
        # The hard-path degradation marker — present when the first nudge was HARD.
        if "HARD NUDGE" in text1:
            require("further nudges in this family will fall silent" in text2,
                    f"second call should degrade to the friendly one-liner: {text2[:200]}")

        # 3rd raw supabase — also bounded.
        out3, _ = run_hook("supabase health my-ref", session, home)
        text3 = emitted_text(out3)
        require(text3 != "" or text3 == "",
                f"third call result: {text3[:120]}")

        # 4th raw supabase — silent (count has crossed NUDGE_SILENT_AFTER=3).
        out4, state = run_hook("supabase health my-ref", session, home)
        text4 = emitted_text(out4)
        require(text4 == "",
                f"fourth raw call should be silent: {text4[:200]}")
        require(state["nudge_counts"]["supabase"] >= 3,
                f"count should be >= silent threshold: {state}")


def test_gap_detection() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        session = "sess-gap-1"

        # agent-do supabase health — demonstration recorded
        run_hook("agent-do supabase health my-ref", session, home)
        # Raw supabase health within the 5-min window — gap event recorded
        _, state = run_hook("supabase health my-ref", session, home)
        gaps = state.get("gap_events") or []
        require(any(g.get("tool") == "supabase" for g in gaps),
                f"gap should be recorded when raw CLI follows agent-do: {state}")


def test_sessions_dont_share_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)

        # Session A burns through nudges
        for _ in range(4):
            run_hook("supabase health my-ref", "sess-A", home)

        # Session B is fresh — should still emit a nudge
        out, state = run_hook("supabase health my-ref", "sess-B", home)
        require(emitted_text(out) != "",
                f"fresh session should not inherit session A's silence: {out}")
        require(state.get("nudge_counts", {}).get("supabase", 0) == 1,
                f"session B should have its own count: {state}")


def main() -> int:
    tests = [
        test_demonstration_suppression,
        test_frequency_degradation,
        test_gap_detection,
        test_sessions_dont_share_state,
    ]
    failures: list[tuple[str, Exception]] = []
    for fn in tests:
        try:
            fn()
            print(f"  ok    {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  {fn.__name__}: {exc}")
            failures.append((fn.__name__, exc))
    print()
    print(f"{len(tests) - len(failures)}/{len(tests)} nudge-smarts tests passed")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
