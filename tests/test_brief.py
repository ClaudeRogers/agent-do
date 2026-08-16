#!/usr/bin/env python3
"""Tests for agent-brief — the estate briefing engine.

Everything runs against fixtures (AGENT_BRIEF_FIXTURES): no network, no live
tools, no writes outside a temp AGENT_DO_HOME. The joins, the contract shape,
the honesty covenant (degraded sources annotated, model voice absent), the
store verbs, and the self-clearing snooze are all exercised.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "agent-brief"

CLAIM_UUID = "aaaabbbb-cccc-4d47-ac03-d3fbe68158bf"
COORD_AGENT = "session-aaaabbbbcccc"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_fixtures(fixtures: Path, *, mn_def_title: str = "def: second item, unclaimed") -> None:
    fixtures.mkdir(parents=True, exist_ok=True)
    (fixtures / "github.json").write_text(json.dumps({
        "count": 2,
        "items": [
            {
                "ref": "owner/repo#5",
                "repo": "owner/repo",
                "number": 5,
                "title": "feat: engine trunk (mn-abc123)",
                "author": "someone",
                "state": "open",
                "draft": False,
                "reasons": ["review_requested"],
                "updated_at": "2026-08-11T12:00:00Z",
                "url": "https://github.com/owner/repo/pull/5",
            },
            {
                "ref": "owner/other#7",
                "repo": "owner/other",
                "number": 7,
                "title": "fix: unrelated standalone",
                "author": "someone",
                "state": "open",
                "draft": False,
                "reasons": ["maintainer_review_stale"],
                "updated_at": "2026-08-10T12:00:00Z",
                "url": "https://github.com/owner/other/pull/7",
            },
        ],
    }))
    (fixtures / "manna.json").write_text(json.dumps({
        "issues": [
            {
                "id": "mn-abc123",
                "title": "engine trunk",
                "status": "in_progress",
                "type": "item",
                "claimed_by": CLAIM_UUID,
                "created_at": "2026-08-11T10:00:00Z",
                "updated_at": "2026-08-11T11:00:00Z",
                "blocked_by": [],
            },
            {
                "id": "mn-def456",
                "title": mn_def_title,
                "status": "open",
                "type": "item",
                "created_at": "2026-08-11T09:00:00Z",
                "updated_at": "2026-08-11T09:30:00Z",
                "blocked_by": [],
            },
            {
                "id": "mn-057357",
                "title": "a parked dream",
                "status": "open",
                "type": "dream",
                "created_at": "2026-06-01T00:00:00Z",
                "updated_at": "2026-06-01T00:00:00Z",
                "blocked_by": [],
            },
            {
                "id": "mn-90d0ee",
                "title": "already done, excluded",
                "status": "done",
                "type": "item",
                "created_at": "2026-08-01T00:00:00Z",
                "updated_at": "2026-08-02T00:00:00Z",
                "blocked_by": [],
            },
        ],
    }))
    (fixtures / "reconcile.json").write_text(json.dumps({
        "success": True,
        "findings": [
            {
                "kind": "landed_open",
                "issue_id": "mn-abc123",
                "detail": "referenced by landed commit trailer but status is open",
                "evidence": "deadbeefcafe",
                "proposed_fix": "review the commits; if the work landed, claim and done mn-abc123",
            },
            {
                "kind": "stale_dream",
                "issue_id": "mn-057357",
                "detail": "open dream older than 14 days",
                "evidence": "created_at 2026-06-01",
                "proposed_fix": "promote to an item on a track, or close it",
            },
            {
                "kind": "landed_open",
                "issue_id": "mn-bad; rm -rf ~",
                "detail": "a poisoned finding",
                "evidence": "hostile board text",
                "proposed_fix": "should never become a command",
            },
            {
                "kind": "landed_open",
                "issue_id": "mn-def456",
                "detail": "referenced by landed commit trailer but status is open",
                "evidence": "0a4dc0ffee00",
                "proposed_fix": "review the commits; if the work landed, claim and done mn-def456",
            },
        ],
    }))
    (fixtures / "coord.json").write_text(json.dumps({
        "success": True,
        "peers": [
            {
                "agent_id": COORD_AGENT,
                "status": "active",
                "last_seen": "2026-08-11T12:30:00Z",
                "focus": {"goal": "build the engine trunk (mn-abc123)", "phase": "building"},
            }
        ],
    }))
    (fixtures / "sessions.json").write_text(json.dumps({"success": True, "result": []}))
    (fixtures / "git.json").write_text(json.dumps({
        "commits": [
            {
                "hash": "deadbeefcafe0000000000000000000000000000",
                "date": "2026-08-11T11:30:00Z",
                "subject": "feat(engine): trunk lands",
                "manna": ["mn-abc123"],
                "files": ["src/engine.py", "tests/test_engine.py"],
            },
            {
                "hash": "0a4dc0ffee000000000000000000000000000000",
                "date": "2026-08-11T10:30:00Z",
                "subject": "chore(manna): stage mn-def456 on the board",
                "manna": ["mn-def456"],
                "files": [".manna/issues.jsonl"],
            },
        ],
    }))
    (fixtures / "ask_sessions.json").write_text(json.dumps({"success": True, "result": []}))
    (fixtures / "ask_zpc.json").write_text(json.dumps({
        "success": True,
        "result": {"count": 1, "results": [{"id": "les-aaaaaa", "takeaway": "engines want receipts"}]},
    }))
    (fixtures / "ask_git.json").write_text(json.dumps({"commits": []}))


def run_brief(
    home: Path, fixtures: Path, *argv: str,
    ai: str | None = "off", drop_model_keys: bool = False,
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["AGENT_DO_HOME"] = str(home)
    env["AGENT_BRIEF_FIXTURES"] = str(fixtures)
    if ai is None:
        env.pop("AGENT_BRIEF_AI", None)
    else:
        env["AGENT_BRIEF_AI"] = ai
    if drop_model_keys:
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("OPENAI_API_KEY", None)
    return subprocess.run(
        [str(TOOL), *argv], capture_output=True, text=True, env=env, cwd=str(home)
    )


def load_brief_module():
    """Import the extensionless agent-brief tool for unit-level tests."""
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader("agent_brief", str(TOOL))
    spec = importlib.util.spec_from_loader("agent_brief", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent_brief"] = module
    loader.exec_module(module)
    return module


def holy(home: Path, fixtures: Path, *argv: str) -> dict:
    proc = run_brief(home, fixtures, "holy", "--focused-repo", str(home), *argv)
    require(proc.returncode == 0, f"holy failed: {proc.stderr}")
    return json.loads(proc.stdout)


def test_help() -> None:
    proc = run_brief(Path("/tmp"), Path("/nonexistent"), "--help")
    require(proc.returncode == 0, f"--help exited {proc.returncode}")
    for verb in ("now", "threads", "ask", "holy", "pin", "snooze", "observe", "state"):
        require(verb in proc.stdout, f"--help missing verb {verb}")


def test_contract_shape_and_joins(home: Path, fixtures: Path) -> None:
    payload = holy(home, fixtures, "--peek")
    require(payload["contract"] == 1, "contract version must be 1")
    # The consumer PINNED contract v1 from live output: these fourteen keys
    # and the suggestion key set are load-bearing. A shape change here means
    # bumping CONTRACT_VERSION, never mutating v1 silently.
    require(set(payload) == {
        "contract", "generated_at", "caller", "paragraph", "threads",
        "threads_total", "delta", "suggestions", "suggestions_total",
        "ranking", "read_state", "annotations", "receipts", "sources",
    }, f"contract v1 top-level shape drifted: {sorted(payload)}")
    for suggestion in payload["suggestions"]:
        require(set(suggestion) == {"id", "kind", "issue_id", "label", "command", "argv", "receipts"},
                f"suggestion shape drifted under v1: {sorted(suggestion)}")

    by_id = {t["id"]: t for t in payload["threads"]}
    require("mn-abc123" in by_id, "mn-abc123 thread missing")
    trunk = by_id["mn-abc123"]
    require(trunk["pr"] is not None and trunk["pr"]["ref"] == "owner/repo#5",
            f"PR did not join to mn-abc123 via title: {trunk['pr']}")
    require(trunk["manna"] is not None, "manna edge missing on trunk thread")
    require(trunk["session"] is not None and trunk["session"]["agent_id"] == COORD_AGENT,
            f"coord session did not join via focus goal: {trunk['session']}")
    require(trunk["last_commit"] is not None and trunk["last_commit"]["hash"].startswith("deadbeef"),
            "git trailer commit did not join")
    require(trunk["needs_me"], "review-requested PR must mark the thread needs_me")
    require(len(trunk["receipts"]) >= 4, f"trunk thread should cite pr+mn+coord+commit: {trunk['receipts']}")
    for rid in trunk["receipts"]:
        require(rid in payload["receipts"], f"thread cites unissued receipt {rid}")

    require("owner/other#7" in by_id, "standalone PR must become its own thread")
    require(by_id["mn-def456"]["claimable"] and not by_id["mn-def456"]["needs_me"],
            "unclaimed unblocked item is claimable inventory, not needs_me")
    require(not by_id["mn-057357"]["claimable"], "a dream is never claimable")
    require("mn-90d0ee" not in by_id, "done issues must not become threads")

    by_issue = {s["issue_id"]: s for s in payload["suggestions"] if s["issue_id"]}
    require(by_issue["mn-abc123"]["command"] == "agent-do manna done mn-abc123",
            f"landed_open one-tap wrong: {by_issue['mn-abc123']}")
    require(by_issue["mn-abc123"]["argv"] == ["agent-do", "manna", "done", "mn-abc123"],
            "suggestion must carry execv-style argv, never only a shell string")
    require(by_issue["mn-057357"]["command"] == "agent-do manna update mn-057357 --type item",
            f"stale_dream one-tap wrong: {by_issue['mn-057357']}")
    poisoned = [s for s in payload["suggestions"] if s["issue_id"] is None]
    require(len(poisoned) == 1 and poisoned[0]["command"] is None and poisoned[0]["argv"] is None,
            f"a malformed issue id must never become a command: {poisoned}")
    require("malformed" in poisoned[0]["label"], "the poisoned finding must say why it lost its command")
    # Trailer != landed: mn-def456's only evidence commit touches .manna/
    # alone (board staging), so the one-tap must inspect, never close.
    landed = [s for s in payload["suggestions"] if s["kind"] == "landed_open" and s["issue_id"] == "mn-def456"]
    require(len(landed) == 1, f"expected one landed_open finding for mn-def456: {payload['suggestions']}")
    require(landed[0]["argv"] == ["agent-do", "manna", "show", "mn-def456"],
            f"board-only landing must downgrade to inspect: {landed[0]}")
    require("board staging" in landed[0]["label"], f"downgrade must say why: {landed[0]['label']}")
    for suggestion in payload["suggestions"]:
        for rid in suggestion["receipts"]:
            require(rid in payload["receipts"], f"suggestion cites unissued receipt {rid}")

    require(payload["paragraph"]["mode"] == "deterministic", "no model configured: voice must be deterministic")
    require(any(a["kind"] == "voice" for a in payload["annotations"]),
            "deterministic voice must be annotated, not silent")
    # Round 3: deterministic mode must still write human prose.
    text = payload["paragraph"]["text"]
    require("(s)" not in text, f"machine-speak pluralization reached the paragraph: {text}")
    require(not re.search(r"\d{4}-\d{2}-\d{2}T", text), f"raw ISO timestamp reached the paragraph: {text}")
    require("Two threads need you — one board item and one pull request." in text,
            f"needs-you sentence must count in words: {text}")
    require("Four one-tap suggestions are waiting." in text,
            f"suggestions sentence must count in words: {text}")
    require("One item sits claimable for any lane." in text,
            f"claimable sentence must count in words: {text}")
    require(payload["sources"]["github"]["origin"] == "fixture", "fixture origin must be reported")
    require(payload["ranking"]["mode"] == "heuristic" and payload["ranking"]["journal_observations"] == 0,
            f"empty journal must report heuristic: {payload['ranking']}")
    top = payload["threads"][0]
    require(top["rank"]["reasons"], "ranked thread must explain itself")


def test_read_state_and_delta(home: Path, fixtures: Path) -> None:
    state_file = home / "brief" / "state.json"
    require(not state_file.exists() or not json.loads(state_file.read_text()).get("callers"),
            "peek runs must not have advanced read-state")
    first = holy(home, fixtures)
    require(first["delta"]["mode"] == "first_look", f"fresh store must be first_look: {first['delta']}")
    second = holy(home, fixtures)
    require(second["delta"]["mode"] == "read_state", f"second look must use read-state: {second['delta']}")
    require(second["delta"]["count"] == 0, f"nothing changed between looks: {second['delta']}")
    explicit = holy(home, fixtures, "--since", "2026-08-11T11:45:00Z", "--peek")
    changed = set(explicit["delta"]["thread_ids"])
    require("mn-abc123" in changed, "coord last_seen 12:30 must land mn-abc123 in the delta")
    require("mn-def456" not in changed, "mn-def456 (09:30) must sit below the 11:45 seam")


def test_pin_snooze_observe(home: Path, fixtures: Path) -> None:
    proc = run_brief(home, fixtures, "pin", "mn-def456")
    require(proc.returncode == 0, f"pin failed: {proc.stderr}")
    payload = holy(home, fixtures, "--peek")
    pinned = next(t for t in payload["threads"] if t["id"] == "mn-def456")
    require(pinned["pinned"], "pin must surface on the thread")
    require(any("pinned" in r for r in pinned["rank"]["reasons"]), "pin must explain its rank boost")

    proc = run_brief(home, fixtures, "snooze", "mn-def456")
    require(proc.returncode == 2, "unbounded snooze must refuse with exit 2")
    proc = run_brief(home, fixtures, "snooze", "mn-def456", "--until-changed",
                     "--focused-repo", str(home))
    require(proc.returncode == 0, f"snooze --until-changed failed: {proc.stderr or proc.stdout}")
    payload = holy(home, fixtures, "--peek")
    snoozed = next(t for t in payload["threads"] if t["id"] == "mn-def456")
    require(snoozed["snoozed"], "snooze must surface on the thread")

    # The thread changes -> the snooze clears itself.
    write_fixtures(fixtures, mn_def_title="def: second item, retitled")
    payload = holy(home, fixtures, "--peek")
    cleared = next(t for t in payload["threads"] if t["id"] == "mn-def456")
    require(not cleared["snoozed"], "until-changed snooze must self-clear when the thread changes")

    proc = run_brief(home, fixtures, "observe", "mn-def456", "nonsense")
    require(proc.returncode == 2, "unknown observe action must refuse with exit 2")
    proc = run_brief(home, fixtures, "observe", "mn-def456", "acted", "--note", "picked it up")
    require(proc.returncode == 0, f"observe failed: {proc.stderr}")
    # One acted and one snoozed cancel to a zero shift, which honestly stays
    # "heuristic"; a second acted makes the journal actually move a score.
    proc = run_brief(home, fixtures, "observe", "mn-abc123", "acted")
    require(proc.returncode == 0, f"observe failed: {proc.stderr}")
    payload = holy(home, fixtures, "--peek")
    require(payload["ranking"]["mode"] == "learned",
            f"journal with observations must report learned: {payload['ranking']}")
    require(payload["ranking"]["journal_observations"] >= 1, "journal count missing")

    proc = run_brief(home, fixtures, "unpin", "mn-def456")
    require(proc.returncode == 0, "unpin failed")
    proc = run_brief(home, fixtures, "unpin", "mn-def456")
    require(proc.returncode == 1, "unpinning an unpinned thread must fail")


def test_fail_closed(home: Path, fixtures: Path) -> None:
    (fixtures / "github.json").write_text("{not json at all")
    payload = holy(home, fixtures, "--peek")
    github = payload["sources"]["github"]
    require(github["status"] == "degraded", f"broken source must degrade: {github}")
    require("unreadable" in github.get("reason", ""), f"degradation must carry the full reason: {github}")
    require(any(a.get("source") == "github" for a in payload["annotations"]),
            "degraded source must be an annotation")
    require(any(t["id"] == "mn-abc123" for t in payload["threads"]),
            "other sources must survive one broken source")
    require("GitHub is unreadable right now." in payload["paragraph"]["text"],
            f"degradation must read as plain consequence: {payload['paragraph']['text']}")
    write_fixtures(fixtures, mn_def_title="def: second item, retitled")


def test_ask(home: Path, fixtures: Path) -> None:
    proc = run_brief(home, fixtures, "ask", "engine", "--json", "--focused-repo", str(home))
    require(proc.returncode == 0, f"ask failed: {proc.stderr}")
    payload = json.loads(proc.stdout)
    require(payload["contract"] == 1, "ask carries the contract version")
    require(payload["answer"]["mode"] == "deterministic", "no model: deterministic answer")
    sources = {h["source"] for h in payload["hits"]}
    require("manna" in sources, f"board hit missing for 'engine': {sources}")
    require("zpc" in sources, f"zpc fixture hit missing: {sources}")
    for hit in payload["hits"]:
        require(hit["receipt"] in payload["receipts"], f"hit cites unissued receipt {hit}")
    require(payload["hits_total"] == len(payload["hits"]), "totals must match the data")


def test_voice_reason(home: Path, fixtures: Path) -> None:
    proc = run_brief(home, fixtures, "holy", "--focused-repo", str(home), "--peek",
                     ai=None, drop_model_keys=True)
    require(proc.returncode == 0, f"holy failed: {proc.stderr}")
    payload = json.loads(proc.stdout)
    voice = [a for a in payload["annotations"] if a["kind"] == "voice"]
    require(len(voice) == 1, f"voice skip must be annotated exactly once: {voice}")
    reason = voice[0]["reason"]
    require("ANTHROPIC_API_KEY" in reason,
            f"the annotation must name what the voice path is missing: {reason}")
    require("creds store" in reason,
            f"the annotation must say how to supply it in a subprocess environment: {reason}")


def test_board_resolution_and_budget() -> None:
    brief = load_brief_module()
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        board = repo / ".manna"
        board.mkdir()
        (board / "issues.jsonl").write_text("")
        # Liberal inputs: repo root, the .manna dir itself, the ledger file.
        for value in (str(repo), str(board), str(board / "issues.jsonl")):
            resolved, _ = brief.resolve_board(value, repo)
            require(resolved == board.resolve(), f"board must resolve from {value}: got {resolved}")
        # An explicit nonexistent value must fail loudly, not fall back.
        try:
            brief.resolve_board(str(repo / "nowhere"), repo)
            require(False, "nonexistent --focused-board must raise SystemExit(2)")
        except SystemExit as exc:
            require(exc.code == 2, f"loud failure must exit 2, got {exc.code}")
        try:
            brief.resolve_repo(str(repo / "nowhere"))
            require(False, "nonexistent --focused-repo must raise SystemExit(2)")
        except SystemExit as exc:
            require(exc.code == 2, f"loud failure must exit 2, got {exc.code}")
        # A default-path miss stays honest and names its search in the reason.
        os.environ.pop("AGENT_BRIEF_FIXTURES", None)
        missing = repo / "empty" / ".manna"
        source = brief.gather_manna(missing, [str(missing)])
        require(source["status"] == "absent" and "looked at" in source["reason"],
                f"false board-absent must name its search: {source}")

    probe = float(brief.READ_PROBE_TIMEOUT_SECONDS)
    require(brief.github_budget(99.0, {}) == 99.0, "explicit --timeout must win")
    require(brief.github_budget(None, {}) == 2.0 * probe,
            "uncalibrated sweep bootstraps at twice the probe budget")
    calibrated = {"calibration": {"github": {"last_ok_seconds": 40.0}}}
    require(brief.github_budget(None, calibrated) == 80.0,
            "calibrated sweep budgets at twice its last observed duration")
    fast = {"calibration": {"github": {"last_ok_seconds": 2.0}}}
    require(brief.github_budget(None, fast) == probe,
            "a fast sweep still gets at least the probe budget")


def test_no_verdict_under_impairment(tmp: Path) -> None:
    """The covenant's core case: degraded is not empty — no clean bill over
    dead sources (consumer round 2, finding 1)."""
    home = tmp / "quiet-home"
    home.mkdir()
    fixtures = tmp / "quiet-fixtures"
    fixtures.mkdir()
    (fixtures / "github.json").write_text("{broken")
    (fixtures / "manna.json").write_text(json.dumps({"issues": []}))
    (fixtures / "reconcile.json").write_text(json.dumps({"success": True, "findings": []}))
    (fixtures / "coord.json").write_text(json.dumps({"success": True, "peers": []}))
    (fixtures / "sessions.json").write_text(json.dumps({"success": True, "result": []}))
    (fixtures / "git.json").write_text(json.dumps({"commits": []}))
    payload = holy(home, fixtures, "--peek")
    text = payload["paragraph"]["text"]
    require("Nothing needs you." not in text,
            f"a clean bill over an unreadable source breaks the covenant: {text}")
    require("no verdict" in text, f"impaired quiet must say no-verdict: {text}")
    require("One of six sources is unreadable" in text,
            f"the no-verdict sentence counts its blind spots in words: {text}")
    # All healthy and quiet -> the proudest state, plainly.
    (fixtures / "github.json").write_text(json.dumps({"count": 0, "items": []}))
    payload = holy(home, fixtures, "--peek")
    require("Nothing needs you." in payload["paragraph"]["text"],
            f"healthy quiet must say so plainly: {payload['paragraph']['text']}")

    proc = run_brief(home, fixtures, "holy", "--focused-repo", str(home / "nowhere"))
    require(proc.returncode == 2, f"nonexistent --focused-repo must exit 2: {proc.returncode}")
    require("--focused-repo" in proc.stdout, f"loud failure must name the flag: {proc.stdout}")
    proc = run_brief(home, fixtures, "holy", "--focused-repo", str(home),
                     "--focused-board", str(home / "nowhere"))
    require(proc.returncode == 2, f"nonexistent --focused-board must exit 2: {proc.returncode}")


def main() -> int:
    test_help()
    test_board_resolution_and_budget()
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        home.mkdir()
        fixtures = Path(tmp) / "fixtures"
        write_fixtures(fixtures)
        test_contract_shape_and_joins(home, fixtures)
        test_read_state_and_delta(home, fixtures)
        test_pin_snooze_observe(home, fixtures)
        test_fail_closed(home, fixtures)
        test_ask(home, fixtures)
        test_voice_reason(home, fixtures)
        test_no_verdict_under_impairment(Path(tmp))
    print("agent-brief: all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
