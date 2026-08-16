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


def run_hook(root: Path, bindir: Path, fixtures: Path, log: Path, mode: str) -> subprocess.CompletedProcess:
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
    env.pop("CLAUDE_ENV_FILE", None)

    return subprocess.run(
        ["bash", str(CLAUDE_HOOK)],
        input=json.dumps({"cwd": str(project), "session_id": "stub-session"}),
        capture_output=True,
        text=True,
        check=False,
        env=env,
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
