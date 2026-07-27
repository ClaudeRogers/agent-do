#!/usr/bin/env python3
"""Regression coverage for automatic counsel: auto-brief, the flip-triggered
second opinion, and the compact inject blob.

The model call is stubbed, not skipped. A fake `claude` on PATH records the
flags and the exact stdin it was handed, which is what makes the frozen
guarantees testable rather than merely stated: the judge is spawned with
isolation flags intact, and the standing position never reaches its prompt.

The one thing a stub cannot fake is a verdict's quality, so nothing here
asserts on the content of the answer — only on who was asked, with what, and
what was written down afterward.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"

CANARY_CLAIM = "CANARY-CLAIM-THE-JUDGE-MUST-NEVER-SEE"
CANARY_VERDICT = "CANARY-VERDICT-THE-JUDGE-MUST-NEVER-SEE"
FALSIFIER = "a byte-identical body on both sides of the hop"

STUB_VERDICT = "VERDICT: stubbed. CONFIDENCE: high. FALSIFIER: none. MISSING: nothing."

# Long enough that a refusal which waited for it could not possibly look fast,
# short enough that the suite still finishes.
STUB_SLEEP_SECONDS = 3

# Mirrors ZPC_AUTOCOUNSEL_DEBOUNCE_MIN in lib/position.sh.
ZPC_DEBOUNCE_MINUTES = 10

STUB = """#!/usr/bin/env bash
# Stands in for the `claude` CLI: records how it was called, then answers.
printf '%s\\n' "$@" > "$ZPC_STUB_ARGS"
cat > "$ZPC_STUB_STDIN"
[[ -n "${ZPC_STUB_SLEEP:-}" ]] && sleep "$ZPC_STUB_SLEEP"
printf '%s\\n' "$ZPC_STUB_VERDICT"
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(project: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(AGENT_DO), "zpc", *args],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def checked(project: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    result = run(project, env, *args)
    require(result.returncode == 0, f"zpc {' '.join(args)} failed: {result.stderr or result.stdout}")
    return result


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(project: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=project, check=True, capture_output=True)


def counsel_dir(project: Path) -> Path:
    return project / ".zpc" / ".state" / "counsel"


def artifacts(project: Path, position_id: str) -> list[Path]:
    directory = counsel_dir(project)
    if not directory.exists():
        return []
    return sorted(directory.glob(f"{position_id}-*.md"))


def settle(path: Path, timeout: float = 40.0) -> str:
    """Wait for the detached writer to replace the pending stub."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = path.read_text()
        if "status: pending" not in text:
            return text
        time.sleep(0.25)
    raise AssertionError(f"counsel artifact never settled within {timeout}s: {path.read_text()[:400]}")


def build_project(tmp: Path, env: dict[str, str]) -> Path:
    project = tmp / "project"
    project.mkdir()
    # Resolved, because macOS hands out /var/folders paths whose real name is
    # /private/var/... — the tool reports the physical path, and a substring
    # check between the two passes for the wrong reason.
    project = project.resolve()
    checked(project, env, "init", "--platform", "generic")

    git(project, "init", "-q")
    git(project, "config", "user.email", "test@example.invalid")
    git(project, "config", "user.name", "test")
    (project / "work.txt").write_text("committed baseline\n")
    git(project, "add", "work.txt")
    git(project, "commit", "-qm", "baseline")
    # Uncommitted work, so `git diff HEAD` has something real to carry.
    (project / "work.txt").write_text("committed baseline\nUNSTAGED-WORK-MARKER\n")
    return project


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)

        stub_dir = tmp / "stub-bin"
        stub_dir.mkdir()
        stub = stub_dir / "claude"
        stub.write_text(STUB)
        stub.chmod(0o755)

        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(tmp / "agent-home")
        env["PATH"] = f"{stub_dir}{os.pathsep}{env['PATH']}"
        env["ZPC_STUB_ARGS"] = str(tmp / "stub-args.txt")
        env["ZPC_STUB_STDIN"] = str(tmp / "stub-stdin.txt")
        env["ZPC_STUB_VERDICT"] = STUB_VERDICT
        env.pop("ZPC_STUB_SLEEP", None)

        project = build_project(tmp, env)

        # ---- counsel --auto-brief: assembled mechanically, bounded honestly --

        extra = tmp / "extra-receipt.txt"
        extra.write_text("EXPLICIT-RECEIPT-MARKER\n")

        auto = checked(
            project, env,
            "counsel", "--auto-brief", "--receipt", str(extra),
            "--question", "Is this work finished?",
        )
        require(STUB_VERDICT in auto.stdout, f"the verdict must reach stdout: {auto.stdout}")

        briefs = sorted(counsel_dir(project).glob("brief-*.md"))
        require(len(briefs) == 1, f"--auto-brief must leave exactly one brief: {briefs}")
        brief_text = briefs[0].read_text()
        require("git diff HEAD" in brief_text, "the brief must carry the diff receipt")
        require("git status --porcelain" in brief_text, "the brief must carry the status receipt")
        require("UNSTAGED-WORK-MARKER" in brief_text, f"the diff must be the real one: {brief_text[:400]}")
        require("EXPLICIT-RECEIPT-MARKER" in brief_text, "--receipt files must land verbatim")
        require("```diff" in brief_text, "the diff must be fenced as a diff")

        # Isolation, pinned at the wire: the flags that disable project
        # customization, tools and session persistence must all be present.
        flags = (tmp / "stub-args.txt").read_text().splitlines()
        for flag in ("--safe-mode", "--tools", "--no-session-persistence", "-p"):
            require(flag in flags, f"counsel must keep {flag} on the subprocess: {flags}")

        sent = (tmp / "stub-stdin.txt").read_text()
        require("--- BRIEF (receipts) ---" in sent, f"the judge is sent the brief: {sent[:200]}")
        require("Is this work finished?" in sent, "the judge is sent the question")
        require("UNSTAGED-WORK-MARKER" in sent, "the judge is sent the assembled receipts")

        # --receipt is meaningless without something to attach it to.
        stray = run(project, env, "counsel", "--receipt", str(extra), "--brief", str(extra))
        require(stray.returncode != 0, "--receipt without --auto-brief must be refused")

        both = run(project, env, "counsel", "--auto-brief", "--brief", str(extra))
        require(both.returncode != 0, "two briefs is ambiguous and must be refused")

        missing = run(project, env, "counsel", "--auto-brief", "--receipt", str(tmp / "nope.txt"))
        require(missing.returncode != 0, "a missing --receipt must fail before the model call")

        # ---- bounds: every cut says it is a cut ---------------------------

        big = "\n".join(f"line {i}: padding that overflows the diff bound" for i in range(600))
        (project / "big.txt").write_text(big)
        git(project, "add", "big.txt")
        git(project, "commit", "-qm", "big")
        (project / "big.txt").write_text(big.replace("line", "CHANGED"))

        logs = project / "tmp" / "logs" / "session"
        logs.mkdir(parents=True)
        (logs / "combined.log").write_text(
            "\n".join(f"log line {i}" for i in range(2000)) + "\nLAST-LOG-LINE-MARKER\n"
        )
        (project / "tmp" / "logs" / "latest").symlink_to("session")

        checked(project, env, "counsel", "--auto-brief")
        newest = sorted(counsel_dir(project).glob("brief-*.md"))[-1]
        bounded = newest.read_text()

        diff_block = bounded.split("--- RECEIPT: git diff HEAD")[1].split("--- RECEIPT:")[0]
        require("[receipt truncated]" in diff_block, "an overflowing diff must be marked as cut")
        require(len(diff_block) < 12600, f"the diff bound must hold: {len(diff_block)} chars")

        log_block = bounded.split("combined.log ---")[1]
        require("[receipt truncated]" in log_block, "an overflowing log must be marked as cut")
        require("LAST-LOG-LINE-MARKER" in log_block, "a log is cut from the front: the failure is at the end")

        # ---- the ledger never rides along in its own evidence -------------

        checked(
            project, env,
            "position", "add", CANARY_CLAIM,
            "--verdict", CANARY_VERDICT, "--confidence", "med", "--falsifier", FALSIFIER,
        )
        ledger = project / ".zpc" / "memory" / "positions.jsonl"
        position_id = json.loads(ledger.read_text().splitlines()[0])["id"]

        # Worst case: a project that tracks its own memory store in git.
        git(project, "add", "-f", ".zpc/memory/positions.jsonl")
        git(project, "commit", "-qm", "track the ledger")
        with ledger.open("a") as handle:
            handle.write(json.dumps({"id": "pos-000001", "claim": CANARY_CLAIM}) + "\n")

        checked(project, env, "counsel", "--auto-brief")
        leaked = sorted(counsel_dir(project).glob("brief-*.md"))[-1].read_text()
        require(CANARY_CLAIM not in leaked, "a tracked ledger must not reach the brief through the diff")
        require(CANARY_VERDICT not in leaked, "a tracked ledger must not reach the brief through the diff")

        # ---- the refused flip fires the second opinion --------------------

        env["ZPC_STUB_SLEEP"] = str(STUB_SLEEP_SECONDS)
        before = digest(ledger)

        refused = run(project, env, "position", "flip", position_id)
        require(refused.returncode == 2, f"the refusal keeps exit 2: {refused.returncode}")
        require(FALSIFIER in refused.stderr, f"the refusal still quotes the falsifier: {refused.stderr}")
        require(digest(ledger) == before, "a refused flip must still write nothing to the ledger")

        spawned = artifacts(project, position_id)
        require(len(spawned) == 1, f"the refusal must leave exactly one artifact: {spawned}")
        require(str(spawned[0]) in refused.stderr, f"the refusal must name the artifact: {refused.stderr}")

        # The load-bearing assertion, and it is causal rather than clocked: the
        # refusal returned while the judge was still reading. A refusal that
        # waited could not observe its own artifact still pending.
        require(
            "status: pending" in spawned[0].read_text(),
            "the refusal must return before the second opinion does — it is detached, not awaited",
        )

        settled = settle(spawned[0])
        require("status: complete" in settled, f"the detached run must record its outcome: {settled[:300]}")
        require(STUB_VERDICT in settled, f"the verdict must land in the artifact: {settled[:300]}")
        require(digest(ledger) == before, "the detached run must not touch the ledger either")

        # Isolation again, on the automatic path: the judge is handed receipts,
        # never the verdict it is being asked to second-guess.
        auto_sent = (tmp / "stub-stdin.txt").read_text()
        require(CANARY_CLAIM not in auto_sent, f"auto-counsel must not send the claim: {auto_sent[:300]}")
        require(CANARY_VERDICT not in auto_sent, f"auto-counsel must not send the verdict: {auto_sent[:300]}")
        require(FALSIFIER not in auto_sent, "auto-counsel must not send the falsifier either")

        leftovers = [p.name for p in counsel_dir(project).iterdir() if p.suffix in {".partial", ".err"}]
        require(not leftovers, f"the writer must clean up after itself: {leftovers}")

        # ---- debounce: minutes, not keystrokes ----------------------------

        again = run(project, env, "position", "flip", position_id)
        require(again.returncode == 2, "the refusal is unchanged by debouncing")
        require(len(artifacts(project, position_id)) == 1, "a second refusal must reuse the recent verdict")
        require(str(spawned[0]) in again.stderr, f"the refusal must point at the existing verdict: {again.stderr}")

        # ---- position show surfaces what was written ----------------------

        shown = checked(project, env, "position", "show", position_id)
        require(str(spawned[0]) in shown.stdout, f"show must surface the verdict path: {shown.stdout}")
        require(STUB_VERDICT in shown.stdout, f"show must surface the verdict itself: {shown.stdout}")

        shown_json = checked(project, env, "position", "show", position_id, "--json")
        payload = json.loads(shown_json.stdout)
        payload = payload.get("result", payload)
        require(payload["id"] == position_id, f"the stored row keeps its shape: {payload}")
        require(payload["counsel"]["path"] == str(spawned[0]), f"the pointer is additive: {payload}")
        require(payload["counsel"]["status"] == "complete", f"the pointer carries the state: {payload}")

        # ---- the kill switch, told apart from the debounce -----------------

        # Backdate past the window, so anything that does not spawn now is not
        # spawning because it was told not to.
        old = time.time() - (ZPC_DEBOUNCE_MINUTES + 1) * 60
        os.utime(spawned[0], (old, old))

        off = env.copy()
        off["AGENT_DO_ZPC_AUTOCOUNSEL"] = "0"
        silent = run(project, off, "position", "flip", position_id)
        require(silent.returncode == 2, "the kill switch changes nothing about the refusal")
        require(FALSIFIER in silent.stderr, "the refusal is the pre-change one, falsifier and all")
        require("Second opinion" not in silent.stderr, f"no second opinion is offered: {silent.stderr}")
        require(len(artifacts(project, position_id)) == 1, "the kill switch must spawn nothing")

        # The control: same conditions, switch back on, and it does spawn. The
        # silence above was the switch, not the debounce.
        respawn = run(project, env, "position", "flip", position_id)
        require(respawn.returncode == 2, "the refusal is unchanged either way")
        fresh = artifacts(project, position_id)
        require(len(fresh) == 2, f"past the window, a refusal spawns again: {fresh}")
        settle(fresh[-1])

        # ---- inject --compact ---------------------------------------------

        newest_lesson = 11
        for index in range(newest_lesson + 1):
            checked(
                project, env, "learn",
                f"context {index}", f"problem {index}", f"solution {index}",
                f"takeaway number {index} " + "padding " * 12,
                "--tags", "compact,test",
            )
        patterns = project / ".zpc" / "memory" / "patterns.md"
        patterns.write_text("# Established Patterns\n\n" + ("- a pattern line worth following\n" * 80))

        compact = checked(project, env, "inject", "--compact")
        blob = compact.stdout.rstrip("\n")
        require(len(blob) <= 2000, f"the compact blob must stay within 2000 chars: {len(blob)}")
        require("[zpc inject truncated]" in blob, "an overflowing compact blob must admit the cut")
        require("a pattern line worth following" in blob, f"patterns must survive the budget: {blob[:200]}")
        require(f"takeaway number {newest_lesson} " in blob, f"the newest lesson must survive the budget: {blob[-400:]}")
        require("takeaway number 0 " not in blob, "the oldest lessons are what the cut takes")

        compact_json = checked(project, env, "inject", "--compact", "--json")
        parsed = json.loads(compact_json.stdout)
        require(set(parsed) == {"additionalContext"}, f"json mode keeps the hook contract: {parsed.keys()}")
        require(len(parsed["additionalContext"]) <= 2000, "the bound holds in json mode too")

        full = checked(project, env, "inject")
        require(len(full.stdout) > 2000, "the full blob is unbounded and must stay that way")
        require("ZPC Agent Protocol" in full.stdout, "the full blob is unchanged by --compact")

        access = project / ".zpc" / ".state" / "access-log.jsonl"
        rows = [json.loads(line) for line in access.read_text().splitlines() if line.strip()]
        injects = [row for row in rows if row.get("cmd") == "inject"]
        require(len(injects) >= 3, f"every inject leaves a receipt, compact included: {len(injects)}")
        require(
            all(set(row) == {"ts", "cmd", "source", "project"} for row in injects),
            f"the access schema is frozen: {injects[:2]}",
        )
        counsels = [row for row in rows if row.get("cmd") == "counsel"]
        require(counsels, "counsel runs leave receipts too")

    print("zpc auto-counsel: briefs assemble mechanically, refusals detach, compact stays bounded")


if __name__ == "__main__":
    main()
