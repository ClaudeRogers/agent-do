#!/usr/bin/env python3
"""Regression coverage for the write-time quantity check hook.

Everything runs against a scratch AGENT_DO_HOME and scratch files, so the
suite never reads or writes the real hook state, and never touches a live
settings.json.

The load-bearing case is the last one people think of: a model the authority
has no record for. The hook has to say the literal is unverified and name
nothing — a guessed ceiling would be the same defect the hook exists to catch.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "claude" / "agent-do-quantity-check.py"

TIME_BUDGET_MS = 300


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(
    payload: object,
    home: Path,
    hook: Path | None = None,
    env_extra: dict[str, str] | None = None,
    raw: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENT_DO_HOME"] = str(home)
    env["AGENT_DO_REPO"] = str(ROOT)
    env.pop("AGENT_DO_QUANTITY_CHECK", None)
    env.update(env_extra or {})
    return subprocess.run(
        ["python3", str(hook or HOOK)],
        input=raw if raw is not None else json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def write_payload(path: Path, content: str, session: str = "s1", cwd: Path | None = None) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {
        "session_id": session,
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "cwd": str(cwd or path.parent),
        "tool_input": {"file_path": str(path), "content": content},
    }


def context(result: subprocess.CompletedProcess[str], label: str) -> str:
    require(result.returncode == 0, f"{label}: exited {result.returncode}: {result.stderr}")
    require(bool(result.stdout.strip()), f"{label}: expected a nudge, got silence")
    payload = json.loads(result.stdout)
    require(
        payload.get("hookSpecificOutput", {}).get("hookEventName") == "PostToolUse",
        f"{label}: wrong hook event: {payload}",
    )
    # Nudge only: nothing in the emitted shape may gate the turn.
    blob = json.dumps(payload)
    for forbidden in ("decision", "permissionDecision", "continue"):
        require(forbidden not in blob, f"{label}: emitted a gating key ({forbidden}): {payload}")
    return payload["hookSpecificOutput"]["additionalContext"]


def assert_silent(result: subprocess.CompletedProcess[str], label: str) -> None:
    require(result.returncode == 0, f"{label}: exited {result.returncode}: {result.stderr}")
    require(not result.stdout.strip(), f"{label}: expected silence, got {result.stdout!r}")


def receipts(home: Path) -> list[dict]:
    path = home / "quantity" / "write-checks.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


KNOWN_MODEL_SOURCE = """import anthropic

client = anthropic.Anthropic()


def ask(prompt):
    return client.messages.create(
        model="claude-sonnet-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
"""

UNKNOWN_MODEL_SOURCE = """from anthropic import Anthropic


def ask(client: Anthropic, prompt: str):
    return client.messages.create(
        model="claude-opus-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
"""

DERIVED_CONSTANT_SOURCE = """import anthropic

# anthropic.claude-sonnet-5.max_tokens, read from the quantity authority
MAX_TOKENS = 128000


def ask(client, prompt):
    return client.messages.create(
        model="claude-sonnet-5",
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
"""

NO_BOUNDS_SOURCE = """import anthropic


def ask(client, prompt):
    return client.messages.create(model="claude-sonnet-5", messages=prompt)
"""


def test_known_ceiling_is_named_and_receipted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home, repo = Path(tmp) / "home", Path(tmp) / "repo"
        target = repo / "client.py"
        payload = write_payload(target, KNOWN_MODEL_SOURCE, session="known", cwd=repo)

        started = time.perf_counter()
        result = run(payload, home)
        elapsed_ms = (time.perf_counter() - started) * 1000

        message = context(result, "known ceiling")
        require("max_tokens=4096" in message, f"literal not surfaced: {message}")
        require(
            "anthropic.claude-sonnet-5.max_tokens is 128000" in message,
            f"published ceiling not named: {message}",
        )
        require("line 9" in message, f"line number not resolved: {message}")
        require("omit the parameter entirely" in message, f"remediation ladder missing: {message}")
        require(
            message.index("omit the parameter") < message.index("reference a capability constant")
            < message.index("named constant"),
            f"remediation ladder out of order: {message}",
        )
        require(
            elapsed_ms < TIME_BUDGET_MS,
            f"hook took {elapsed_ms:.0f}ms, over the {TIME_BUDGET_MS}ms budget",
        )

        rows = receipts(home)
        require(len(rows) == 1, f"expected one receipt row, got {rows}")
        row = rows[0]
        require(row["file"] == target.as_posix(), f"receipt names the wrong file: {row}")
        require(row["mode"] == "nudge", f"receipt should record nudge mode: {row}")
        finding = row["findings"][0]
        require(finding["ceiling_status"] == "known", f"ceiling status wrong: {finding}")
        require(finding["ceiling_value"] == 128000, f"ceiling value wrong: {finding}")


def test_missing_record_degrades_without_inventing_a_ceiling() -> None:
    """A real, current model the authority has never heard of."""
    with tempfile.TemporaryDirectory() as tmp:
        home, repo = Path(tmp) / "home", Path(tmp) / "repo"
        payload = write_payload(repo / "opus.py", UNKNOWN_MODEL_SOURCE, session="gap", cwd=repo)
        message = context(run(payload, home), "missing record")

        require("max_tokens=4096" in message, f"literal not surfaced: {message}")
        require(
            "no record for anthropic.claude-opus-5.max_tokens" in message,
            f"the gap is not named as a gap: {message}",
        )
        require("unverified" in message, f"the unverified state is not stated: {message}")
        # No ceiling may be asserted for a key with no record. The only numbers
        # allowed in the finding line are the literal and the line number.
        finding_line = next(line for line in message.splitlines() if "max_tokens=4096" in line)
        numbers = set(re.findall(r"\d+", finding_line)) - {"4096", "5"}
        require(
            numbers <= {str(n) for n in range(1, 100)},
            f"a ceiling was invented for a key with no record: {finding_line}",
        )
        require("128000" not in message, f"another model's ceiling leaked in: {message}")

        finding = receipts(home)[0]["findings"][0]
        require(finding["ceiling_status"] == "no_record", f"receipt status wrong: {finding}")
        require(finding.get("ceiling_value") is None, f"receipt carries a guessed ceiling: {finding}")


def test_derived_constant_and_reference_pass() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home, repo = Path(tmp) / "home", Path(tmp) / "repo"
        payload = write_payload(repo / "derived.py", DERIVED_CONSTANT_SOURCE, session="ok", cwd=repo)
        assert_silent(run(payload, home), "derived constant")
        require(not receipts(home), "a silent run must leave no receipt")


def test_file_without_bounds_is_silent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home, repo = Path(tmp) / "home", Path(tmp) / "repo"
        payload = write_payload(repo / "plain.py", NO_BOUNDS_SOURCE, session="plain", cwd=repo)
        assert_silent(run(payload, home), "no bounding literals")


def test_one_nudge_per_file_per_session() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home, repo = Path(tmp) / "home", Path(tmp) / "repo"
        target = repo / "client.py"
        payload = write_payload(target, KNOWN_MODEL_SOURCE, session="cooldown", cwd=repo)
        context(run(payload, home), "first write")
        assert_silent(run(payload, home), "second write, same session")

        # The cooldown silences the message, not the measurement.
        rows = receipts(home)
        require(len(rows) == 2, f"the suppressed write left no receipt: {rows}")
        require(
            [row["mode"] for row in rows] == ["nudge", "suppressed"],
            f"receipt modes wrong: {[row['mode'] for row in rows]}",
        )

        # A different session sees the same file fresh; a different file in the
        # same session is its own budget.
        other = dict(payload, session_id="cooldown-2")
        context(run(other, home), "same file, new session")
        second_file = write_payload(repo / "other.py", KNOWN_MODEL_SOURCE, session="cooldown", cwd=repo)
        context(run(second_file, home), "new file, same session")


def test_edit_fragment_reports_the_files_own_line() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home, repo = Path(tmp) / "home", Path(tmp) / "repo"
        target = repo / "client.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(KNOWN_MODEL_SOURCE, encoding="utf-8")
        payload = {
            "session_id": "edit",
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "cwd": str(repo),
            "tool_input": {
                "file_path": str(target),
                "old_string": "        max_tokens=2048,",
                "new_string": "        max_tokens=4096,",
            },
        }
        message = context(run(payload, home), "edit fragment")
        require("line 9" in message, f"fragment line not resolved against the file: {message}")


def test_out_of_scope_paths_are_silent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home, repo = Path(tmp) / "home", Path(tmp) / "repo"
        for name in ("README.md", "test_client.py", "tests/client.py", "node_modules/pkg/index.js"):
            payload = write_payload(repo / name, KNOWN_MODEL_SOURCE, session=f"scope-{name}", cwd=repo)
            assert_silent(run(payload, home), f"out of scope: {name}")


def test_the_check_passes_its_own_source() -> None:
    """The hook holds itself to the ladder it hands out.

    Its own truncations are named constants carrying their derivations, so a
    scan of this file finds nothing. A checker that would nudge about itself is
    a checker whose author did not believe the remediation was practical.
    """
    with tempfile.TemporaryDirectory() as tmp:
        home, repo = Path(tmp) / "home", Path(tmp) / "repo"
        payload = write_payload(
            repo / "quantity-check.py", HOOK.read_text(encoding="utf-8"), session="self", cwd=repo
        )
        assert_silent(run(payload, home), "the hook's own source")


def test_the_authority_record_is_out_of_scope() -> None:
    """models.yaml is where a published ceiling belongs as a number."""
    with tempfile.TemporaryDirectory() as tmp:
        home, repo = Path(tmp) / "home", Path(tmp) / "repo"
        record = "models:\n  claude-sonnet-5:\n    provider: anthropic\n    max_tokens: 128000\n"
        payload = write_payload(repo / "models.yaml", record, session="authority", cwd=repo)
        assert_silent(run(payload, home), "the authority's own record")


def test_anonymous_bounds_respect_the_floor() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home, repo = Path(tmp) / "home", Path(tmp) / "repo"
        structural = write_payload(
            repo / "small.py", "first = rows[:2]\nlead = names[:1]\n", session="floor-low", cwd=repo
        )
        assert_silent(run(structural, home), "structural slice")

        capped = write_payload(
            repo / "capped.py", "shown = sorted(models)[:40]\n", session="floor-high", cwd=repo
        )
        message = context(run(capped, home), "capped slice")
        require("slice=40" in message, f"slice cap not surfaced: {message}")


def test_kill_switch_and_malformed_input_are_silent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home, repo = Path(tmp) / "home", Path(tmp) / "repo"
        payload = write_payload(repo / "client.py", KNOWN_MODEL_SOURCE, session="off", cwd=repo)
        assert_silent(
            run(payload, home, env_extra={"AGENT_DO_QUANTITY_CHECK": "0"}), "kill switch"
        )
        for label, raw in (
            ("empty stdin", ""),
            ("not json", "{not json at all"),
            ("json array", "[1, 2, 3]"),
            ("json scalar", '"hello"'),
            ("missing tool_input", json.dumps({"tool_name": "Write"})),
            ("tool_input not an object", json.dumps({"tool_name": "Write", "tool_input": 7})),
            ("no file_path", json.dumps({"tool_name": "Write", "tool_input": {"content": "x"}})),
            ("other tool", json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})),
        ):
            assert_silent(run(None, home, raw=raw), label)


def test_authority_unavailable_still_never_crashes_or_guesses() -> None:
    """No resolver reachable: the literal is still flagged, no ceiling claimed."""
    with tempfile.TemporaryDirectory() as tmp:
        home, repo = Path(tmp) / "home", Path(tmp) / "repo"
        # A copy at a path whose repo-root walk finds no lib/quantities.py, with
        # no AGENT_DO_REPO and no breadcrumb under the scratch AGENT_DO_HOME.
        island = Path(tmp) / "island" / "hooks" / "claude"
        island.mkdir(parents=True)
        stray = island / HOOK.name
        shutil.copy2(HOOK, stray)

        payload = write_payload(repo / "client.py", KNOWN_MODEL_SOURCE, session="noauth", cwd=repo)
        env = {"AGENT_DO_REPO": ""}
        result = run(payload, home, hook=stray, env_extra=env)
        message = context(result, "authority unavailable")
        require("max_tokens=4096" in message, f"literal not surfaced: {message}")
        require("128000" not in message, f"a ceiling was claimed without an authority: {message}")
        require(
            "could not be read" in message,
            f"the unavailable authority is not stated: {message}",
        )
        finding = receipts(home)[0]["findings"][0]
        require(
            finding["ceiling_status"] == "authority_unavailable",
            f"receipt status wrong: {finding}",
        )


def test_receipts_stay_out_of_the_repository() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home, repo = Path(tmp) / "home", Path(tmp) / "repo"
        payload = write_payload(repo / "client.py", KNOWN_MODEL_SOURCE, session="receipt", cwd=repo)
        context(run(payload, home), "receipt path")
        require((home / "quantity" / "write-checks.jsonl").is_file(), "receipt not written under AGENT_DO_HOME")
        strays = [path for path in repo.rglob("*") if path.suffix == ".jsonl"]
        require(not strays, f"receipts leaked into the repository: {strays}")


def main() -> int:
    for test in (
        test_known_ceiling_is_named_and_receipted,
        test_missing_record_degrades_without_inventing_a_ceiling,
        test_derived_constant_and_reference_pass,
        test_file_without_bounds_is_silent,
        test_one_nudge_per_file_per_session,
        test_edit_fragment_reports_the_files_own_line,
        test_out_of_scope_paths_are_silent,
        test_the_check_passes_its_own_source,
        test_the_authority_record_is_out_of_scope,
        test_anonymous_bounds_respect_the_floor,
        test_kill_switch_and_malformed_input_are_silent,
        test_authority_unavailable_still_never_crashes_or_guesses,
        test_receipts_stay_out_of_the_repository,
    ):
        test()
    print("quantity write-check hook tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
