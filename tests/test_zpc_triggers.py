#!/usr/bin/env python3
"""Isolated regression coverage for machine-wide lesson entry and delivery (mn-e209fb).

A global lesson rides into every session on the machine. Entry is gated:
`promote --to global` refuses a row without a rule, a why, a trigger, and a
cross-project receipt, and refuses any row a machine wrote. Delivery follows
the trigger: session start carries only `always` rows and a count, and the
hook that fires at the named moment injects the rest. Everything here runs in
a scratch AGENT_DO_HOME so the machine's real store is never touched.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"
HOOK = ROOT / "hooks" / "claude" / "agent-do-zpc-trigger.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(project: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(AGENT_DO), "zpc", *args], cwd=project, env=env, text=True,
        capture_output=True, check=False,
    )


def checked(project: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    result = run(project, env, *args)
    require(result.returncode == 0, f"zpc {' '.join(args)} failed: {result.stderr or result.stdout}")
    return result


def json_result(result: subprocess.CompletedProcess) -> dict:
    payload = json.loads(result.stdout)
    return payload.get("result", payload)


def rows(store: Path) -> list[dict]:
    if not store.exists():
        return []
    out = [json.loads(line) for line in store.read_text().splitlines() if line.strip()]
    return [r for r in out if "retracts" not in r and "challenges" not in r]


def hook(payload: dict, env: dict, cwd: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [sys_python(), str(HOOK)], input=json.dumps(payload), cwd=cwd, env=env,
        text=True, capture_output=True, check=False,
    )
    require(result.returncode == 0, f"trigger hook must never fail: {result.stderr}")
    return result


def sys_python() -> str:
    import sys
    return sys.executable


def hook_context(result: subprocess.CompletedProcess) -> str:
    if not result.stdout.strip():
        return ""
    payload = json.loads(result.stdout)
    require(payload.get("decision") != "block", f"hook emitted a block decision: {payload}")
    require(payload.get("continue") is not False, f"hook emitted continue:false: {payload}")
    return payload["hookSpecificOutput"]["additionalContext"]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        home = tmp / "agent-home"
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(home)
        env["AGENT_DO_TELEMETRY_SUPPRESS"] = "1"
        env["AGENT_DO_ZPC_RELITIGATE"] = "0"
        env.pop("CLAUDE_SESSION_ID", None)
        env.pop("AGENT_DO_COORD_SESSION", None)
        store = home / "zpc" / "global-lessons.jsonl"
        deliveries = home / "zpc" / "deliveries.jsonl"

        source = tmp / "source"
        source.mkdir()
        checked(source, env, "init", "--platform", "generic")

        # line 1: a real lesson; line 2: a machine-written row; line 3: an always-rule
        checked(source, env, "learn", "writing shell tests", "a test faked its own premise",
                "assert the premise inside the test", "Prove a test's premise before asserting behavior.",
                "--tags", "testing,premise")
        checked(source, env, "learn", "auto", "something", "something",
                "Correction from Erik: \"try again\"", "--tags", "preference,mined")
        checked(source, env, "learn", "how Erik reads", "padded replies go unread",
                "say the thing", "State the point plainly at its natural length.",
                "--tags", "preference,communication")

        # ── the gate refuses, and writes nothing ─────────────────────────────
        bare = run(source, env, "promote", "1", "--to", "global")
        require(bare.returncode == 2, f"a bare promotion to global must be refused with exit 2: {bare.returncode}")
        require("--rule" in bare.stderr and "--when" in bare.stderr and "--why" in bare.stderr,
                f"the refusal must name what is missing: {bare.stderr}")
        require(not rows(store), "a refused promotion wrote to the global store")

        bad_regex = run(source, env, "promote", "1", "--to", "global",
                        "--rule", "r", "--why", "w", "--when", "prompt:(unclosed", "--scope", "user")
        require(bad_regex.returncode == 2 and "regex" in bad_regex.stderr,
                f"an invalid trigger regex must be refused: {bad_regex.stderr}")

        machine = run(source, env, "promote", "2", "--to", "global",
                      "--rule", "r", "--why", "w", "--when", "always", "--scope", "user")
        require(machine.returncode == 2 and "machine" in machine.stderr,
                f"a mined row must never go global: {machine.stderr}")

        one_project = run(source, env, "promote", "1", "--to", "global",
                          "--rule", "r", "--why", "w", "--when", "always", "--seen-in", "only-one")
        require(one_project.returncode == 2 and "cross-project" in one_project.stderr,
                f"one project is a project lesson: {one_project.stderr}")

        batch = run(source, env, "promote", "preference", "--to", "global",
                    "--rule", "r", "--why", "w", "--when", "always", "--scope", "user")
        require(batch.returncode == 2 and "one at a time" in batch.stderr,
                f"global promotion is one row at a time: {batch.stderr}")
        require(not rows(store), "a refusal wrote to the global store")

        # ── a row that earns it ──────────────────────────────────────────────
        promoted = json_result(checked(
            source, env, "promote", "1", "--to", "global", "--json",
            "--rule", "Prove a test's premise inside the test before asserting the behavior",
            "--why", "a test that fakes its own premise can assert nothing and still pass",
            "--when", "path:test_*.py", "--when", "command:pytest|python3 tests/",
            "--when", "prompt:write (a|the) test",
            "--seen-in", "agent-do,holy-ghostty",
        ))
        require(promoted["promoted"] == 1, f"gated promotion must land: {promoted}")
        stored = rows(store)
        require(len(stored) == 1, f"one global row expected: {stored}")
        row = stored[0]
        rule_id = row["id"]
        require(row["rule"].startswith("Prove") and row["why"].startswith("a test"),
                f"rule and why must ride on the global copy: {row}")
        require([w["kind"] for w in row["when"]] == ["path", "command", "prompt"],
                f"triggers must be stored in order: {row['when']}")
        require(row["seen_in"] == ["agent-do", "holy-ghostty"], f"receipt missing: {row}")
        require(row["promoted_from"] == "source", f"promoted_from must name the project: {row}")

        # Re-promoting updates in place, under the same id: how a lesson
        # promoted before triggers existed gets its rule without a reissue.
        updated = json_result(checked(
            source, env, "promote", "1", "--to", "global", "--json",
            "--rule", "Prove the premise first",
            "--why", "a faked premise proves nothing",
            "--when", "path:test_*.py", "--scope", "user",
        ))
        require(updated["updated"] == 1 and updated["promoted"] == 0, f"re-promotion must update: {updated}")
        stored = rows(store)
        require(len(stored) == 1 and stored[0]["id"] == rule_id, f"update must keep the id and the row count: {stored}")
        require(stored[0]["rule"] == "Prove the premise first" and stored[0].get("scope") == "user"
                and "seen_in" not in stored[0], f"update must replace the gate fields: {stored[0]}")

        # Put the full trigger set back for the delivery checks.
        checked(source, env, "promote", "1", "--to", "global",
                "--rule", "Prove a test's premise inside the test before asserting the behavior",
                "--why", "a test that fakes its own premise can assert nothing and still pass",
                "--when", "path:test_*.py", "--when", "command:pytest|python3 tests/",
                "--when", "prompt:write (a|the) test", "--scope", "user")

        # An always-rule, for the session-start slice.
        always = json_result(checked(
            source, env, "promote", "3", "--to", "global", "--json",
            "--rule", "State the point plainly at its natural length",
            "--why", "Erik stops reading padded prose, so a padded answer is an unread answer",
            "--when", "always", "--scope", "user",
        ))
        require(always["promoted"] == 1, f"always-rule must land: {always}")

        # ── delivery: session start carries always rows and a count ─────────
        consumer = tmp / "consumer"
        consumer.mkdir()
        checked(consumer, env, "init", "--platform", "generic")
        opening = checked(consumer, env, "inject").stdout
        require("State the point plainly" in opening, f"an always-rule must open the session: {opening}")
        require("Prove a test's premise" not in opening and rule_id not in opening,
                f"a triggered rule must not open the session: {opening}")
        require("1 more machine-wide lesson carries a trigger" in opening,
                f"session start must count what waits: {opening}")
        prefs = checked(consumer, env, "inject", "--preferences").stdout
        require("Prove a test's premise" not in prefs and "carries a trigger" in prefs,
                f"the preference slice must hold the triggered rule back and count it: {prefs}")

        status = json_result(checked(consumer, env, "status", "--json"))
        require(status["global_lessons"] == 2 and status["global_lessons_triggered"] == 1,
                f"status must count live and triggered: {status}")

        # ── delivery: the trigger fires the rule beside its moment ───────────
        fired = json_result(checked(consumer, env, "inject", "--trigger", "prompt",
                                    "please write a test for the parser", "--json"))
        require(fired["fired"] == [rule_id], f"prompt trigger must fire the rule: {fired}")
        blob = fired["additionalContext"]
        require("Prove a test's premise" in blob and "why: a test that fakes" in blob and rule_id in blob,
                f"a fired lesson carries rule, why and id: {blob}")
        require("State the point plainly" not in blob, f"an always-rule does not fire on a trigger: {blob}")

        quiet = json_result(checked(consumer, env, "inject", "--trigger", "prompt",
                                    "deploy the thing", "--json"))
        require(quiet["fired"] == [] and quiet["additionalContext"] == "",
                f"nothing matched must be nothing said: {quiet}")
        require(checked(consumer, env, "inject", "--trigger", "prompt", "deploy the thing").stdout.strip() == "",
                "text mode must print nothing when nothing fires")

        by_command = json_result(checked(consumer, env, "inject", "--trigger", "command",
                                         "python3 tests/test_zpc_global.py", "--json"))
        require(by_command["fired"] == [rule_id], f"command trigger must fire: {by_command}")
        by_path = json_result(checked(consumer, env, "inject", "--trigger", "path",
                                      "/somewhere/tests/test_widgets.py", "--json"))
        require(by_path["fired"] == [rule_id], f"path glob must match the basename: {by_path}")
        other_path = json_result(checked(consumer, env, "inject", "--trigger", "path",
                                         "/somewhere/src/widgets.py", "--json"))
        require(other_path["fired"] == [], f"a non-matching path must not fire: {other_path}")

        # No project store at all: the hooks fire in every directory.
        bare_dir = tmp / "no-store"
        bare_dir.mkdir()
        no_store = json_result(checked(bare_dir, env, "inject", "--trigger", "prompt",
                                       "write the test now", "--json"))
        require(no_store["fired"] == [rule_id], f"triggers must answer without a .zpc: {no_store}")

        delivered = [json.loads(l) for l in deliveries.read_text().splitlines() if l.strip()]
        require(len(delivered) == 4 and all(d["fired"] == [rule_id] for d in delivered),
                f"every firing leaves a delivery receipt: {delivered}")
        require({d["kind"] for d in delivered} == {"prompt", "command", "path"},
                f"receipts carry the kind: {delivered}")

        # A retracted global rule stops firing.
        checked(consumer, env, "retract", rule_id, "--evidence", "the fixture is done with it")
        gone = json_result(checked(consumer, env, "inject", "--trigger", "prompt",
                                   "write a test", "--json"))
        require(gone["fired"] == [], f"a retracted rule must not fire: {gone}")
        # ...and comes back for the hook checks below.
        checked(source, env, "promote", "1", "--to", "global",
                "--rule", "Prove a test's premise inside the test before asserting the behavior",
                "--why", "a test that fakes its own premise can assert nothing and still pass",
                "--when", "path:test_*.py", "--when", "command:pytest|python3 tests/",
                "--when", "prompt:write (a|the) test", "--scope", "user")
        # The retraction stands on the old id; the re-promotion updated that
        # same row, which stays retracted. A fresh row is the honest fixture.
        checked(source, env, "learn", "writing shell tests", "a second premise",
                "assert it", "Second: prove the premise.", "--tags", "testing")
        fresh = json_result(checked(
            source, env, "promote", "4", "--to", "global", "--json",
            "--rule", "Second: prove the premise before asserting",
            "--why", "same reason", "--when", "prompt:write (a|the) test",
            "--when", "command:git commit", "--when", "path:*.test.js", "--scope", "user",
        ))
        require(fresh["promoted"] == 1, f"fresh rule must land: {fresh}")
        fresh_id = [r for r in rows(store) if r["rule"].startswith("Second")][0]["id"]

        # ── the hook: one delivery per session per kind, never a block ───────
        hook_env = env.copy()
        hook_env["AGENT_DO_REPO"] = str(ROOT)
        session = {"session_id": "sess-trigger-0001", "cwd": str(consumer)}
        first = hook_context(hook({**session, "hook_event_name": "UserPromptSubmit",
                                   "prompt": "write the test for the loader"}, hook_env, consumer))
        require("Second: prove the premise" in first and fresh_id in first,
                f"the prompt hook must deliver the fired rule: {first}")
        second = hook_context(hook({**session, "hook_event_name": "UserPromptSubmit",
                                    "prompt": "write a test again"}, hook_env, consumer))
        require(second == "", f"the same rule must not be delivered twice in one session: {second}")

        by_bash = hook_context(hook({**session, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                                     "tool_input": {"command": "git commit -m 'x'"}}, hook_env, consumer))
        require("Second: prove the premise" in by_bash, f"the command hook must deliver: {by_bash}")
        not_bash = hook_context(hook({**session, "hook_event_name": "PreToolUse", "tool_name": "Read",
                                      "tool_input": {"command": "git commit"}}, hook_env, consumer))
        require(not_bash == "", f"only Bash commands are command triggers: {not_bash}")

        by_edit = hook_context(hook({**session, "hook_event_name": "PostToolUse", "tool_name": "Write",
                                     "tool_input": {"file_path": str(consumer / "widget.test.js")}},
                                    hook_env, consumer))
        require("Second: prove the premise" in by_edit, f"the edit hook must deliver: {by_edit}")

        other_session = hook_context(hook({"session_id": "sess-trigger-0002", "cwd": str(consumer),
                                           "hook_event_name": "UserPromptSubmit",
                                           "prompt": "write the test"}, hook_env, consumer))
        require("Second: prove the premise" in other_session, "a new session gets its own delivery")

        garbage = subprocess.run([sys_python(), str(HOOK)], input="not json", cwd=consumer,
                                 env=hook_env, text=True, capture_output=True, check=False)
        require(garbage.returncode == 0 and garbage.stdout.strip() == "",
                f"garbage input must be silent and exit 0: {garbage}")
        unknown_event = hook({**session, "hook_event_name": "Stop"}, hook_env, consumer)
        require(unknown_event.stdout.strip() == "", "an unregistered event must be silent")

    print("zpc triggers: entry gated on rule+why+when, delivery rides the moment, session start carries the count")


if __name__ == "__main__":
    main()
