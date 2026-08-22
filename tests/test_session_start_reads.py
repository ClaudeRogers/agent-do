#!/usr/bin/env python3
"""What the session-start hook does with the JSON it reads.

The hook parses every envelope it reads with `jq` rather than a `python3 -c`
program, because an interpreter start costs ~190ms here and a session hook pays
that once per parse. Speed is only worth having if the answers are the same, so
this pins both halves of that:

  * well-formed input renders the same blocks, down to peer ordering, the
    read-only detail, the hidden-session tail, and the [new] interrupt prefix;
  * malformed, empty, and failed reads degrade to the same silence — no
    section, no crash, and nothing on stderr (an empty count reaching
    `[ "$x" -gt 0 ]` is an error message, not a comparison).

It also pins the coord collapse: the two coord reads overlap rather than run in
turn, and they go straight at the tool when it sits beside the resolved
dispatcher.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLAUDE_HOOK = REPO / "hooks" / "claude" / "agent-do-session-start.sh"
CURSOR_HOOK = REPO / "hooks" / "cursor" / "agent-do-session-start.py"

FAILURES: list[str] = []

STUB = r"""#!/bin/bash
# Test double for the agent-do dispatcher and for tools/agent-coord.
# Invoked as agent-coord, it answers the same verbs with the leading
# "coord" word stripped by the caller, so both call shapes land here.
self=$(basename "$0")
if [ "$self" = "agent-coord" ]; then
    set -- coord "$@"
fi
tool="$1"
shift

if [ "$tool" = "coord" ]; then
    echo "start coord $1 ($self)" >> "$AGENT_DO_STUB_LOG"
    sleep 0.2
fi

case "${AGENT_DO_STUB_MODE:-valid}" in
    garbage)
        [ "$tool" = "coord" ] && echo "end coord $1" >> "$AGENT_DO_STUB_LOG"
        printf '%s' '{"needs_bootstrap": tr'
        exit 0
        ;;
    silent)
        [ "$tool" = "coord" ] && echo "end coord $1" >> "$AGENT_DO_STUB_LOG"
        exit 1
        ;;
esac

case "$tool" in
    bootstrap)
        cat "$AGENT_DO_STUB_FIXTURES/bootstrap.json"
        ;;
    coord)
        case "$1" in
            touch) cat "$AGENT_DO_STUB_FIXTURES/coord-touch.json" ;;
            interrupts) cat "$AGENT_DO_STUB_FIXTURES/coord-interrupts.json" ;;
            *) exit 1 ;;
        esac
        echo "end coord $1" >> "$AGENT_DO_STUB_LOG"
        ;;
    manna)
        cat "$AGENT_DO_STUB_FIXTURES/manna.json"
        ;;
    *)
        exit 1
        ;;
esac
exit 0
"""

BOOTSTRAP = {
    "needs_bootstrap": True,
    "ask_prompt": "Bootstrap agent-do for this project?",
    "project_root": "/stub/project",
    "commands": ["agent-do zpc init", "agent-do manna init"],
    "legacy_board": False,
}

TOUCH = {
    "focus": None,
    "active_peers": [
        {
            "agent_id": "peer-audit",
            "mode": "read-only",
            "role": "auditor",
            "phase": "watching",
            "age": "4m ago",
            "focus": {"goal": "reading hooks"},
        },
        {
            "agent_id": "peer-build",
            "alias": "builder-a",
            "phase": "building",
            "age": "1m ago",
            "focus": {"goal": "lane 31"},
        },
    ],
    "peer_counts": {"active": 2, "idle": 0, "stopped": 1, "dead": 2, "stale": 3},
}

INTERRUPTS_NONE: dict = {"interrupts": []}

INTERRUPTS_SOME = {
    "interrupts": [
        {"kind": "contention", "summary": "hooks/claude overlaps builder-a", "new": True},
        {"kind": "notice", "summary": "auditor reading your paths", "new": False},
    ]
}

MANNA = {"context": "# Manna Context\n\n## Open Issues (1)\n- mn-000001: stub issue"}


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok: {label}")
    else:
        FAILURES.append(f"{label}{f' — {detail}' if detail else ''}")
        print(f"  FAIL: {label}{f' — {detail}' if detail else ''}")


def build_stub(root: Path, *, direct_coord: bool, interrupts: dict) -> tuple[Path, Path, Path]:
    """A fake dispatcher on PATH, optionally with tools/agent-coord beside it."""
    bindir = root / "bin"
    fixtures = root / "fixtures"
    bindir.mkdir(parents=True, exist_ok=True)
    fixtures.mkdir(parents=True, exist_ok=True)

    (fixtures / "bootstrap.json").write_text(json.dumps(BOOTSTRAP), encoding="utf-8")
    (fixtures / "coord-touch.json").write_text(json.dumps(TOUCH), encoding="utf-8")
    (fixtures / "coord-interrupts.json").write_text(json.dumps(interrupts), encoding="utf-8")
    (fixtures / "manna.json").write_text(json.dumps(MANNA), encoding="utf-8")

    dispatcher = bindir / "agent-do"
    dispatcher.write_text(STUB, encoding="utf-8")
    dispatcher.chmod(0o755)

    if direct_coord:
        tools = bindir / "tools"
        tools.mkdir(exist_ok=True)
        coord = tools / "agent-coord"
        coord.write_text(STUB, encoding="utf-8")
        coord.chmod(0o755)

    return bindir, fixtures, root / "stub.log"


def run_hook(
    root: Path,
    bindir: Path,
    fixtures: Path,
    log: Path,
    mode: str,
    env_file: Path | None = None,
    identity_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    project = root / "project"
    (project / ".manna").mkdir(parents=True, exist_ok=True)
    home = root / "home"
    home.mkdir(exist_ok=True)

    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{bindir}:{env.get('PATH', '')}",
            "HOME": str(home),
            "AGENT_DO_HOME": str(root / "agent-do-home"),
            "AGENT_DO_STUB_MODE": mode,
            "AGENT_DO_STUB_FIXTURES": str(fixtures),
            "AGENT_DO_STUB_LOG": str(log),
            "AGENT_DO_BOOTSTRAP_PROMPT_MODE": "context",
            # The store walk and inject are pinned by their own tests; keeping
            # them out keeps this one about the reads it is named for.
            "AGENT_DO_ZPC_INJECT": "0",
            "AGENT_DO_ZPC_AUTOINIT": "0",
        }
    )
    for variable in (
        "AGENT_DO_COORD_SESSION",
        "MANNA_SESSION_ID",
        "MANNA_SESSION_TOKEN",
        "CLAUDE_SESSION_ID",
    ):
        env.pop(variable, None)
    env.update(identity_env or {})
    if env_file is None:
        env.pop("CLAUDE_ENV_FILE", None)
    else:
        env["CLAUDE_ENV_FILE"] = str(env_file)

    return subprocess.run(
        ["bash", str(CLAUDE_HOOK)],
        input=json.dumps({"cwd": str(project), "session_id": "stub-session"}),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_session_identity_exports_are_complete_and_private() -> None:
    print("session identity exports:")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bindir, fixtures, log = build_stub(root, direct_coord=True, interrupts=INTERRUPTS_NONE)
        env_file = root / "session.env"
        env_file.write_text("", encoding="utf-8")
        proc = run_hook(root, bindir, fixtures, log, "valid", env_file)

        check("identity hook exits 0", proc.returncode == 0, proc.stderr)
        exports = env_file.read_text(encoding="utf-8")
        check(
            "coord identity is pinned",
            'export AGENT_DO_COORD_SESSION="stub-session"' in exports,
            exports,
        )
        claude_lines = [
            line for line in exports.splitlines() if line.startswith("export CLAUDE_SESSION_ID=")
        ]
        check(
            "Manna rides the derived identity, pinned exactly once",
            len(claude_lines) == 1 and 'export CLAUDE_SESSION_ID="stub-session"' in exports,
            exports,
        )
        check(
            "no mortal token is minted (proofs derive under the machine key)",
            "MANNA_SESSION_TOKEN" not in exports and "MANNA_SESSION_ID" not in exports,
            exports,
        )

        partial_file = root / "partial.env"
        partial_file.write_text("", encoding="utf-8")
        run_hook(
            root,
            bindir,
            fixtures,
            log,
            "valid",
            partial_file,
            {"MANNA_SESSION_ID": "stale-partial-owner"},
        )
        partial_exports = partial_file.read_text(encoding="utf-8")
        check(
            "incomplete inherited identity is neutralized for derivation",
            'export MANNA_SESSION_ID=""' in partial_exports
            and 'export CLAUDE_SESSION_ID="stub-session"' in partial_exports
            and "stale-partial-owner" not in partial_exports,
            partial_exports,
        )

        complete_file = root / "complete.env"
        complete_file.write_text("", encoding="utf-8")
        run_hook(
            root,
            bindir,
            fixtures,
            log,
            "valid",
            complete_file,
            {
                "MANNA_SESSION_ID": "pinned-lane",
                "MANNA_SESSION_TOKEN": "a" * 64,
            },
        )
        complete_exports = complete_file.read_text(encoding="utf-8")
        check(
            "complete inherited identity pair is preserved untouched",
            "MANNA_SESSION_ID" not in complete_exports
            and "MANNA_SESSION_TOKEN" not in complete_exports
            and "CLAUDE_SESSION_ID" not in complete_exports,
            complete_exports,
        )


def test_legacy_board_migration_is_discoverable() -> None:
    print("legacy board migration discovery:")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project = root / "project"
        board = project / ".manna"
        board.mkdir(parents=True)
        (project / "CLAUDE.md").write_text("Use `agent-do manna` here.\n", encoding="utf-8")
        (board / "issues.jsonl").write_text(
            '{"id":"mn-a10001","title":"Legacy row","status":"open",'
            '"created_at":"2026-01-01T00:00:00Z",'
            '"updated_at":"2026-01-01T00:00:00Z","blocked_by":[]}\n',
            encoding="utf-8",
        )
        (board / "sessions.jsonl").write_text("", encoding="utf-8")
        env = dict(os.environ)
        env["AGENT_DO_HOME"] = str(root / "agent-do-home")
        proc = subprocess.run(
            [
                "bash",
                str(REPO / "bin" / "bootstrap"),
                "--recommend",
                "--json",
                "--cwd",
                str(project),
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        check("legacy bootstrap recommendation exits 0", proc.returncode == 0, proc.stderr)
        try:
            recommendation = json.loads(proc.stdout)
        except Exception as exc:  # noqa: BLE001
            check("legacy bootstrap recommendation is JSON", False, f"{exc}: {proc.stdout!r}")
            return
        check("legacy bootstrap recommendation is JSON", True)
        check(
            "bootstrap classifies legacy migration before a write",
            recommendation.get("legacy_board") is True
            and recommendation.get("pending_actions") == ["manna_migrate"]
            and recommendation.get("commands") == ["agent-do manna migrate"],
            repr(recommendation),
        )
        check(
            "bootstrap names the one-command remedy",
            "legacy board: run agent-do manna migrate" in recommendation.get("ask_prompt", ""),
            repr(recommendation),
        )

        transactions = board / "transactions"
        transactions.mkdir()
        (transactions / "board-init.yaml").write_text("pending: true\n", encoding="utf-8")
        recovery_proc = subprocess.run(
            [
                "bash",
                str(REPO / "bin" / "bootstrap"),
                "--recommend",
                "--json",
                "--cwd",
                str(project),
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        recovery = json.loads(recovery_proc.stdout)
        check(
            "pending atomic init stays on its authenticated recovery path",
            recovery_proc.returncode == 0
            and recovery.get("legacy_board") is False
            and recovery.get("pending_actions") == ["manna_init"]
            and recovery.get("commands") == ["agent-do manna init"],
            repr(recovery),
        )
        (transactions / "board-init.yaml").unlink()

        bindir, fixtures, log = build_stub(
            root, direct_coord=True, interrupts=INTERRUPTS_NONE
        )
        (fixtures / "bootstrap.json").write_text(
            json.dumps(recommendation), encoding="utf-8"
        )
        hook = run_hook(root, bindir, fixtures, log, "valid")
        check("legacy SessionStart exits 0", hook.returncode == 0, hook.stderr)
        context = context_of(hook)
        check(
            "SessionStart surfaces legacy migration before board writes",
            "legacy board: run agent-do manna migrate" in context
            and "agent-do manna migrate" in context,
            context,
        )


def test_cursor_session_identity_is_restart_durable() -> None:
    print("Cursor session identity exports:")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project = root / "project"
        project.mkdir()

        def run_cursor(identity_env: dict[str, str] | None = None) -> dict[str, str]:
            env = dict(os.environ)
            env.update(
                {
                    "AGENT_DO_REPO": str(REPO),
                    "AGENT_DO_HOME": str(root / "agent-do-home"),
                    "HOME": str(root / "home"),
                    "AGENT_DO_BOOTSTRAP_PROMPT_MODE": "disabled",
                    "AGENT_DO_ZPC_INJECT": "0",
                    "AGENT_DO_ZPC_AUTOINIT": "0",
                }
            )
            for variable in (
                "AGENT_DO_COORD_SESSION",
                "MANNA_SESSION_ID",
                "MANNA_SESSION_TOKEN",
                "CLAUDE_SESSION_ID",
            ):
                env.pop(variable, None)
            env.update(identity_env or {})
            proc = subprocess.run(
                ["python3", str(CURSOR_HOOK)],
                input=json.dumps(
                    {
                        "cwd": str(project),
                        "conversation_id": "cursor-conversation-123",
                    }
                ),
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            check("Cursor identity hook exits 0", proc.returncode == 0, proc.stderr)
            try:
                payload = json.loads(proc.stdout)
                exports = payload["env"]
            except Exception as exc:  # noqa: BLE001
                check("Cursor identity hook emits environment", False, f"{exc}: {proc.stdout!r}")
                return {}
            check("Cursor identity hook emits environment", True)
            return exports

        exports = run_cursor()
        check(
            "Cursor coord identity is pinned",
            exports.get("AGENT_DO_COORD_SESSION") == "cursor-conversation-123",
            repr(exports),
        )
        check(
            "Cursor Manna identity uses the conversation id for derivation",
            exports.get("CLAUDE_SESSION_ID") == "cursor-conversation-123",
            repr(exports),
        )
        check(
            "Cursor does not mint a mortal Manna identity pair",
            "MANNA_SESSION_ID" not in exports and "MANNA_SESSION_TOKEN" not in exports,
            repr(exports),
        )
        check(
            "Cursor restart returns the same derivation input",
            run_cursor() == exports,
            repr(exports),
        )

        stale_id = run_cursor({"MANNA_SESSION_ID": "stale-owner"})
        check(
            "Cursor neutralizes an id-only stale pin",
            stale_id.get("MANNA_SESSION_ID") == ""
            and stale_id.get("CLAUDE_SESSION_ID") == "cursor-conversation-123"
            and "MANNA_SESSION_TOKEN" not in stale_id,
            repr(stale_id),
        )

        stale_token = run_cursor({"MANNA_SESSION_TOKEN": "b" * 64})
        check(
            "Cursor neutralizes a token-only stale pin",
            stale_token.get("MANNA_SESSION_TOKEN") == ""
            and stale_token.get("CLAUDE_SESSION_ID") == "cursor-conversation-123"
            and "MANNA_SESSION_ID" not in stale_token,
            repr(stale_token),
        )

        complete = run_cursor(
            {
                "MANNA_SESSION_ID": "pinned-lane",
                "MANNA_SESSION_TOKEN": "c" * 64,
            }
        )
        check(
            "Cursor preserves a complete explicit identity pair",
            complete.get("MANNA_SESSION_ID") == "pinned-lane"
            and complete.get("MANNA_SESSION_TOKEN") == "c" * 64
            and "CLAUDE_SESSION_ID" not in complete,
            repr(complete),
        )


def context_of(proc: subprocess.CompletedProcess) -> str:
    payload = json.loads(proc.stdout)
    return payload["hookSpecificOutput"]["additionalContext"]


def test_wellformed_reads_render_identically() -> None:
    print("well-formed reads:")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bindir, fixtures, log = build_stub(root, direct_coord=True, interrupts=INTERRUPTS_NONE)
        proc = run_hook(root, bindir, fixtures, log, "valid")

        check("hook exits 0", proc.returncode == 0, proc.stderr)
        check("hook writes nothing to stderr", proc.stderr == "", repr(proc.stderr))
        context = context_of(proc)

        check(
            "bootstrap ask prompt rendered",
            '"Bootstrap agent-do for this project?"' in context,
            context,
        )
        check("bootstrap project root rendered", "/stub/project" in context, context)
        check(
            "bootstrap commands rendered, one per line",
            "agent-do zpc init\nagent-do manna init" in context,
            context,
        )

        expected_peers = (
            "- builder-a (phase:building, 1m ago) goal: lane 31\n"
            "- peer-audit (auditor, read-only, phase:watching, 4m ago) goal: reading hooks\n"
            "- (6 dead/stopped/stale sessions on the board, not shown)"
        )
        check("coord focus reminder rendered", "## Coord Focus Reminder" in context, context)
        check(
            "peers render writers first, with details and the hidden tail",
            expected_peers in context,
            context,
        )
        check("no interrupts section when there are none", "## Coord Interrupts" not in context, context)
        check("manna board context rendered", "- mn-000001: stub issue" in context, context)

        coord_calls = [line for line in log.read_text(encoding="utf-8").splitlines() if "coord" in line]
        check(
            "both coord reads go straight at the tool",
            len([line for line in coord_calls if "(agent-coord)" in line]) == 2,
            "\n".join(coord_calls),
        )
        check(
            "the two coord reads overlap rather than run in turn",
            len(coord_calls) >= 2 and all(line.startswith("start ") for line in coord_calls[:2]),
            "\n".join(coord_calls),
        )


def test_interrupts_take_precedence() -> None:
    print("interrupts:")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bindir, fixtures, log = build_stub(root, direct_coord=False, interrupts=INTERRUPTS_SOME)
        proc = run_hook(root, bindir, fixtures, log, "valid")

        check("hook exits 0", proc.returncode == 0, proc.stderr)
        context = context_of(proc)
        check("interrupts section rendered", "## Coord Interrupts" in context, context)
        check(
            "interrupt lines carry kind, summary, and the new marker",
            "- [new] contention: hooks/claude overlaps builder-a\n"
            "- notice: auditor reading your paths" in context,
            context,
        )
        check(
            "focus reminder yields to interrupts",
            "## Coord Focus Reminder" not in context,
            context,
        )

        coord_calls = [line for line in log.read_text(encoding="utf-8").splitlines() if "coord" in line]
        check(
            "no tools/ beside the dispatcher falls back to the dispatched form",
            len([line for line in coord_calls if "(agent-do)" in line]) == 2,
            "\n".join(coord_calls),
        )


def test_unreadable_answers_degrade_quietly() -> None:
    for mode, label in (("garbage", "malformed JSON"), ("silent", "failed read")):
        print(f"{label}:")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bindir, fixtures, log = build_stub(root, direct_coord=True, interrupts=INTERRUPTS_NONE)
            proc = run_hook(root, bindir, fixtures, log, mode)

            check(f"{label}: hook exits 0", proc.returncode == 0, proc.stderr)
            check(f"{label}: nothing on stderr", proc.stderr == "", repr(proc.stderr))

            try:
                context = context_of(proc)
            except Exception as exc:  # noqa: BLE001
                check(f"{label}: stdout is a valid hook envelope", False, f"{exc}: {proc.stdout!r}")
                continue
            check(f"{label}: stdout is a valid hook envelope", True)

            check(f"{label}: tooling reminder survives", "TOOLING REMINDER" in context, context)
            for section in (
                "Bootstrap Opportunity",
                "Coord Interrupts",
                "Coord Focus Reminder",
                "Manna Board",
            ):
                check(f"{label}: no {section} section", section not in context, context)


def main() -> int:
    test_wellformed_reads_render_identically()
    test_interrupts_take_precedence()
    test_unreadable_answers_degrade_quietly()
    test_legacy_board_migration_is_discoverable()
    test_session_identity_exports_are_complete_and_private()
    test_cursor_session_identity_is_restart_durable()

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}):")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("session-start read tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
