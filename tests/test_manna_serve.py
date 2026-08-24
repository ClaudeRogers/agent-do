#!/usr/bin/env python3
"""manna serve: derivation, registry, HTTP surface, and CLI lifecycle.

The board on disk is the only input; every section on the page must fall out
of it. These tests build a small strict-shaped board in a throwaway git
repository and check what the page would show.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVE_DIR = REPO / "tools" / "agent-manna" / "serve"
sys.path.insert(0, str(SERVE_DIR))

import board as board_lib  # noqa: E402
import serve as serve_lib  # noqa: E402

ISSUES = [
    {"id": "mn-track1", "title": "TRACK: Program", "status": "open", "type": "track", "blocked_by": [], "created_at": "2026-08-01T00:00:00Z", "updated_at": "2026-08-01T00:00:00Z"},
    {"id": "mn-aaaaaa", "title": "First ready thing", "status": "open", "blocked_by": [], "track": "mn-track1", "prompt": ".handoff/01-mn-aaaaaa-first.md", "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-10T00:00:00Z"},
    {"id": "mn-bbbbbb", "title": "Second ready thing", "status": "open", "blocked_by": [], "track": "mn-track1", "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-11T00:00:00Z"},
    {"id": "mn-cccccc", "title": "Claimed thing", "status": "in_progress", "blocked_by": [], "track": "mn-track1", "claimed_by": "claude-deadbeefdead0000", "claimed_at": "2026-08-12T00:00:00Z", "claim_token_hash": "sha256:" + "0" * 64, "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-12T00:00:00Z"},
    {"id": "mn-cccc22", "title": "Second claimed thing", "status": "in_progress", "blocked_by": [], "track": "mn-track1", "claimed_by": "claude-0000aaaa1111ffff", "claimed_at": "2026-08-12T00:00:00Z", "claim_token_hash": "sha256:" + "1" * 64, "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-13T00:00:00Z"},
    {"id": "mn-dddddd", "title": "Waits on aaaaaa", "status": "blocked", "blocked_by": ["mn-aaaaaa"], "track": "mn-track1", "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-03T00:00:00Z"},
    {"id": "mn-eeeeee", "title": "Waits on dddddd", "status": "blocked", "blocked_by": ["mn-dddddd"], "track": "mn-track1", "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-03T00:00:00Z"},
    {"id": "mn-ffffff", "title": "[DECISION] Ratify the thing", "status": "open", "blocked_by": [], "track": "mn-track1", "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-04T00:00:00Z"},
    {"id": "mn-999999", "title": "Open but graph says blocked", "status": "open", "blocked_by": ["mn-bbbbbb"], "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-04T00:00:00Z"},
    {"id": "mn-mentio", "title": "Retire the [DECISION] title convention", "status": "open", "blocked_by": [], "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-04T00:00:00Z"},
    {"id": "mn-second", "title": "[P1-K] [human] Rule on the second thing", "status": "open", "blocked_by": [], "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-04T00:00:00Z"},
    {"id": "mn-dream1", "title": "A spark", "status": "open", "type": "dream", "blocked_by": [], "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-05T00:00:00Z"},
    {"id": "mn-done00", "title": "Shipped thing", "status": "done", "blocked_by": [], "track": "mn-track1", "legacy_migration": {"version": 1}, "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-06T00:00:00Z"},
    {"id": "mn-cycle1", "title": "Cycle A", "status": "blocked", "blocked_by": ["mn-cycle2"], "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-03T00:00:00Z"},
    {"id": "mn-cycle2", "title": "Cycle B", "status": "blocked", "blocked_by": ["mn-cycle1"], "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-03T00:00:00Z"},
]


STUB_PEERS = {
    "success": True,
    "peers": [
        {"agent_id": "session-deadbeefdead", "status": "active", "age": "3s ago", "age_seconds": 3, "runtime": "claude", "focus": {"goal": "building the thing"},
         "pulse": {"status": "needs-user", "activity": "Bash", "latest_prompt": "please fix it", "updated_at": "2026-08-24T00:00:00Z", "turns": 4, "todo": {"done": 1, "total": 3, "current": "fix unicode"}}},
        {"agent_id": "session-0000aaaa1111", "status": "active", "age": "9s ago", "age_seconds": 9, "runtime": "claude", "focus": {"goal": "reading"},
         "pulse": {"status": "working", "activity": "Read", "latest_prompt": "look around", "updated_at": "2026-08-24T00:00:00Z", "turns": 1}},
        {"agent_id": "codex-feedfacefeedface", "status": "idle", "age": "40m ago", "age_seconds": 2400, "runtime": "codex", "focus": {}},
        {"agent_id": "session-dead00000000", "status": "dead", "age": "3h ago", "age_seconds": 10800, "runtime": "claude", "focus": {}},
    ],
}
STUB_RECONCILE = {"success": True, "findings": [
    {"kind": "landed_open", "issue_id": "mn-aaaaaa", "detail": "live finding", "evidence": "abc123", "proposed_fix": "claim and done"},
    {"kind": "stale_dream", "issue_id": "mn-dream1", "detail": "old dream", "evidence": "created 2026-08-02", "proposed_fix": "convert or close"},
]}


def make_stub_agent_do(directory: Path) -> Path:
    """A stand-in `agent-do` that answers the two verbs serve consumes."""
    import shlex
    script = directory / "agent-do"
    script.write_text(
        "#!/usr/bin/env python3\nimport json, sys\n"
        f"PEERS = {STUB_PEERS!r}\nRECON = {STUB_RECONCILE!r}\n"
        "a = sys.argv[1:]\n"
        "if a[:3] == ['coord', 'peers', '--json']: print(json.dumps(PEERS)); sys.exit(0)\n"
        "if a[:3] == ['manna', 'reconcile', '--json']: print(json.dumps(RECON)); sys.exit(1)\n"
        "sys.exit(2)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout.strip()


def make_board(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    board = root / ".manna"
    board.mkdir()
    (board / "issues.jsonl").write_text("".join(json.dumps(i) + "\n" for i in ISSUES), encoding="utf-8")
    (board / "handoff-order.yaml").write_text("version: 1\nitems:\n- mn-bbbbbb\n- mn-aaaaaa\n- mn-dddddd\n", encoding="utf-8")
    (board / "workflow.yaml").write_text("version: 2\nhandoff_dir: .handoff\n", encoding="utf-8")
    (board / "board.yaml").write_text("version: 1\nworkflow: strict\n", encoding="utf-8")
    (board / "drift.yaml").write_text(
        "generated_at: \"2026-08-20T00:00:00Z\"\nfindings:\n- kind: landed_open\n  issue_id: mn-aaaaaa\n  detail: referenced by landed commit trailer but status is open\n  evidence: abc123\n  proposed_fix: claim and done it\n",
        encoding="utf-8",
    )
    handoff = root / ".handoff"
    handoff.mkdir()
    (handoff / "01-mn-aaaaaa-first.md").write_text("# First\n\nwork order body\n", encoding="utf-8")
    (root / "secret.md").write_text("not a handoff\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "feat: advance the first thing\n\nManna: mn-aaaaaa\nCo-Authored-By: t <t@example.com>")
    git(root, "commit", "-q", "--allow-empty", "-m", "chore: unrelated")
    return root


class DerivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = make_board(Path(cls.tmp.name) / "proj")
        cls.state = board_lib.derive(cls.root, agent_do=None)
        cls.by_id = {r["id"]: r for r in cls.state["all"]}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_private_fields_never_leave_the_board(self) -> None:
        payload = json.dumps(self.state)
        self.assertNotIn("claim_token_hash", payload)
        self.assertNotIn("legacy_migration", payload)

    def test_next_follows_handoff_order_then_unordered(self) -> None:
        self.assertEqual([r["id"] for r in self.state["next"]], ["mn-bbbbbb", "mn-aaaaaa", "mn-mentio"])

    def test_now_carries_claimant_with_unseen_liveness_without_coord(self) -> None:
        now = self.state["now"]
        self.assertEqual(sorted(r["id"] for r in now), ["mn-cccc22", "mn-cccccc"])
        first = next(r for r in now if r["id"] == "mn-cccccc")
        self.assertEqual(first["claimant"]["label"], "claude-deadbeefdead0000")
        self.assertEqual(first["claimant"]["liveness"], "unseen")
        self.assertIsNone(first["claimant"]["pulse"])
        self.assertEqual(self.state["drift"]["source"], "file")

    def test_decisions_come_from_title_markers(self) -> None:
        self.assertEqual(sorted(r["id"] for r in self.state["decisions"]), ["mn-ffffff", "mn-second"])
        self.assertEqual(self.by_id["mn-mentio"]["effective"], "ready")
        self.assertEqual(self.by_id["mn-ffffff"]["effective"], "decision")
        self.assertEqual(self.by_id["mn-ffffff"]["title_plain"], "Ratify the thing")

    def test_graph_outranks_status_field(self) -> None:
        self.assertEqual(self.by_id["mn-999999"]["effective"], "waiting")
        self.assertEqual(self.by_id["mn-999999"]["blockers"][0]["id"], "mn-bbbbbb")

    def test_waves_are_topological_layers(self) -> None:
        waves = {w["wave"]: [r["id"] for r in w["items"]] for w in self.state["waves"]}
        self.assertEqual(waves[1], ["mn-dddddd", "mn-999999"])
        self.assertEqual(waves[2], ["mn-eeeeee"])
        self.assertEqual(sorted(r["id"] for r in self.state["unlayered"]), ["mn-cycle1", "mn-cycle2"])

    def test_handoff_existence_is_reported_per_row(self) -> None:
        self.assertTrue(self.by_id["mn-aaaaaa"]["handoff_exists"])
        self.assertIsNone(self.by_id["mn-bbbbbb"]["handoff_exists"])

    def test_dependents_are_reverse_edges(self) -> None:
        self.assertEqual(self.by_id["mn-aaaaaa"]["dependents"], ["mn-dddddd"])

    def test_trailer_commits_index_by_id(self) -> None:
        commits = self.by_id["mn-aaaaaa"]["commits"]
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0]["subject"], "feat: advance the first thing")
        self.assertEqual(self.by_id["mn-bbbbbb"]["commits"], [])

    def test_dreams_tracks_drift_counts(self) -> None:
        self.assertEqual([r["id"] for r in self.state["dreams"]], ["mn-dream1"])
        self.assertEqual(self.state["tracks"][0]["id"], "mn-track1")
        self.assertEqual(self.state["tracks"][-1]["title"], "(no track)")
        self.assertEqual(self.state["drift"]["count"], 1)
        self.assertEqual(self.state["drift"]["kinds"], {"landed_open": 1})
        self.assertEqual(self.state["counts"]["ready"], 3)
        self.assertEqual(self.state["git"]["branch"], "main")

    def test_summary_matches_derivation(self) -> None:
        summary = board_lib.summary(self.root)
        self.assertEqual(summary["decisions"], 2)
        self.assertEqual(summary["dreams"], 1)
        self.assertEqual(summary["status_counts"]["done"], 1)
        self.assertEqual(summary["drift_count"], 1)

    def test_signature_moves_when_the_board_moves(self) -> None:
        gitdir = board_lib.git_dir(self.root)
        before = board_lib.signature(self.root, gitdir)
        path = self.root / ".manna" / "issues.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        os.utime(path, (1, 1))
        self.assertNotEqual(before, board_lib.signature(self.root, gitdir))

    def test_peer_matching_across_identity_forms(self) -> None:
        peers = [{"agent_id": "session-3c15edbd4860", "status": "active"}, {"agent_id": "codex-01a02afe94d27b52", "status": "idle"}]
        self.assertEqual(board_lib.match_peer("claude-3c15edbd486045ef", peers)["status"], "active")
        self.assertEqual(board_lib.match_peer("codex-01a02afe94d27b52", peers)["status"], "idle")
        self.assertIsNone(board_lib.match_peer("claude-ffffffffffffffff", peers))
        self.assertIsNone(board_lib.match_peer(None, peers))


class LiveDerivationTests(unittest.TestCase):
    """With coord and reconcile answering (stubbed), pulse rides the rows and drift is live."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = make_board(Path(cls.tmp.name) / "proj")
        cls.stub = make_stub_agent_do(Path(cls.tmp.name))
        cls.state = board_lib.derive(cls.root, agent_do=cls.stub, live=True)
        cls.by_id = {r["id"]: r for r in cls.state["all"]}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_now_sorts_needs_user_first_and_carries_pulse(self) -> None:
        now = self.state["now"]
        self.assertEqual([r["id"] for r in now], ["mn-cccccc", "mn-cccc22"])
        c = now[0]["claimant"]
        self.assertEqual(c["attention"], "needs-user")
        self.assertEqual(c["pulse"]["activity"], "Bash")
        self.assertEqual(c["pulse"]["todo"], {"done": 1, "total": 3, "current": "fix unicode"})
        self.assertEqual(now[1]["claimant"]["attention"], "working")

    def test_peers_attention_first_and_counted(self) -> None:
        self.assertEqual([p["attention"] for p in self.state["peers"]], ["needs-user", "working", "idle", "gone"])
        self.assertEqual(self.state["attention"]["needs-user"], 1)
        self.assertEqual(self.state["attention"]["gone"], 1)

    def test_drift_is_live_with_file_age_beside_it(self) -> None:
        d = self.state["drift"]
        self.assertEqual(d["source"], "reconcile")
        self.assertEqual(d["count"], 2)
        self.assertEqual(d["kinds"], {"landed_open": 1, "stale_dream": 1})
        self.assertEqual(d["file"]["count"], 1)
        self.assertEqual(d["file"]["generated_at"], "2026-08-20T00:00:00Z")
        self.assertFalse((self.root / ".manna" / "drift.yaml").read_text().count("live finding"), "the page never writes drift")

    def test_nonzero_exit_reconcile_still_counts(self) -> None:
        # the stub exits 1 with findings, as reconcile does
        self.assertIsNotNone(board_lib.live_drift(self.root, self.stub))


class RegistryAndHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        os.environ["AGENT_DO_HOME"] = str(self.home)
        self.root = make_board(Path(self.tmp.name) / "proj")

    def tearDown(self) -> None:
        os.environ.pop("AGENT_DO_HOME", None)
        self.tmp.cleanup()

    def test_slug_collisions_take_the_parent_name(self) -> None:
        slug, fresh = serve_lib.register_board(self.root)
        self.assertEqual((slug, fresh), ("proj", True))
        other = Path(self.tmp.name) / "elsewhere" / "proj"
        other.mkdir(parents=True)
        slug2, fresh2 = serve_lib.register_board(other)
        self.assertEqual((slug2, fresh2), ("elsewhere--proj", True))
        self.assertEqual(serve_lib.register_board(self.root), ("proj", False))

    def test_machine_added_marker_is_honored_and_never_in_code(self) -> None:
        self.assertNotIn("[ADA]", board_lib.DECISION_MARKERS)
        (self.root / ".manna" / "issues.jsonl").open("a", encoding="utf-8").write(
            json.dumps({"id": "mn-named1", "title": "[Ada] Rule on the named thing", "status": "open", "blocked_by": [], "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-04T00:00:00Z"}) + "\n"
        )
        before = board_lib.summary(self.root, serve_lib.decision_markers())["decisions"]
        with self.assertRaises(ValueError):
            serve_lib.add_decision_marker("ADA")
        serve_lib.add_decision_marker("[ADA]")
        serve_lib.add_decision_marker("[ada]")
        self.assertEqual(serve_lib.load_registry_file()["decision_markers"], ["[ADA]"])
        self.assertEqual(board_lib.summary(self.root, serve_lib.decision_markers())["decisions"], before + 1)
        serve_lib.register_board(self.root)
        self.assertEqual(serve_lib.load_registry_file()["decision_markers"], ["[ADA]"], "registering a board keeps the markers")

    def test_scan_finds_nested_boards_and_skips_noise(self) -> None:
        base = Path(self.tmp.name) / "estate"
        (base / "a" / ".manna").mkdir(parents=True)
        (base / "a" / "sub" / ".manna").mkdir(parents=True)
        (base / "node_modules" / "x" / ".manna").mkdir(parents=True)
        (base / "deep" / "1" / "2" / "3" / ".manna").mkdir(parents=True)
        found = {p.relative_to(base).as_posix() for p in serve_lib.scan_boards(base)}
        self.assertEqual(found, {"a", "a/sub"})

    def test_http_surface(self) -> None:
        serve_lib.register_board(self.root)
        server = ThreadingHTTPServer(("127.0.0.1", 0), serve_lib.Handler)
        server.daemon_threads = True
        server.stopping = False
        server.started_at = "test"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def get(path: str) -> tuple[int, bytes, str]:
            try:
                with urllib.request.urlopen(base + path, timeout=5) as resp:
                    return resp.status, resp.read(), resp.headers.get("Content-Type", "")
            except urllib.error.HTTPError as err:
                return err.code, err.read(), err.headers.get("Content-Type", "")

        try:
            status, body, _ = get("/api/health")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["server"], "manna-serve")

            status, body, _ = get("/api/boards")
            index = json.loads(body)
            self.assertEqual([b["slug"] for b in index["boards"]], ["proj"])
            self.assertEqual(index["boards"][0]["decisions"], 2)

            status, body, ctype = get("/proj")
            self.assertEqual(status, 200)
            self.assertIn("text/html", ctype)
            self.assertIn(b'id="now-list"', body)

            status, body, _ = get("/proj/api/state")
            state = json.loads(body)
            self.assertEqual(state["slug"], "proj")
            self.assertNotIn("claim_token_hash", body.decode())

            # No document viewer: the page hands out the handoff path, never the file.
            status, _, _ = get("/proj/handoff?path=.handoff/01-mn-aaaaaa-first.md")
            self.assertEqual(status, 404)
            self.assertNotIn("work order body", body.decode())

            status, _, _ = get("/nope")
            self.assertEqual(status, 404)

            # DNS rebinding: a foreign Host header is refused everywhere
            for host in ("evil.example", "evil.example:80", "127.0.0.1.evil.example"):
                req = urllib.request.Request(base + "/api/boards", headers={"Host": host})
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        self.fail(f"{host} was served: {resp.status}")
                except urllib.error.HTTPError as err:
                    self.assertEqual(err.code, 403, host)
            req = urllib.request.Request(base + "/api/boards", headers={"Origin": "http://evil.example"})
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(caught.exception.code, 403)
            req = urllib.request.Request(base + "/api/health", headers={"Origin": base})
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
            for host in ("localhost", f"localhost:{server.server_address[1]}", "[::1]:1", "127.0.0.1"):
                req = urllib.request.Request(base + "/api/health", headers={"Host": host})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    self.assertEqual(resp.status, 200, host)
            status, _, ctype = get("/static/app.js")
            self.assertEqual(status, 200)
            self.assertIn("javascript", ctype)
        finally:
            server.stopping = True
            server.shutdown()
            server.server_close()


class CliLifecycleTests(unittest.TestCase):
    def test_serve_registers_starts_prints_url_and_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            root = make_board(Path(tmp) / "proj")
            env = {**os.environ, "AGENT_DO_HOME": str(home)}
            wrapper = REPO / "tools" / "agent-manna" / "agent-manna"
            try:
                first = subprocess.run([str(wrapper), "serve", "--json", "--port", "0"], cwd=root, env=env, capture_output=True, text=True, timeout=60)
                self.assertEqual(first.returncode, 0, first.stderr)
                payload = json.loads(first.stdout)
                self.assertEqual(payload["daemon"], "started")
                self.assertEqual(payload["slug"], "proj")
                self.assertTrue(payload["url"].endswith("/proj"))
                port = payload["port"]

                second = subprocess.run([str(wrapper), "serve", "--json", "--port", "0"], cwd=root, env=env, capture_output=True, text=True, timeout=60)
                again = json.loads(second.stdout)
                self.assertEqual(again["daemon"], "running")
                self.assertEqual(again["port"], port)

                with urllib.request.urlopen(f"http://127.0.0.1:{port}/proj/api/state", timeout=5) as resp:
                    self.assertEqual(json.loads(resp.read())["name"], "proj")

                outside = subprocess.run([str(wrapper), "serve", "--json"], cwd=tmp, env=env, capture_output=True, text=True, timeout=60)
                self.assertEqual(outside.returncode, 2)
                self.assertIn("no .manna", json.loads(outside.stdout)["error"])

                status = subprocess.run([str(wrapper), "serve", "--status", "--json"], cwd=root, env=env, capture_output=True, text=True, timeout=60)
                self.assertTrue(json.loads(status.stdout)["running"])

                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as resp:
                    self.assertEqual(json.loads(resp.read())["source"], serve_lib.SOURCE_HASH)
            finally:
                stopped = subprocess.run([str(wrapper), "serve", "--stop", "--json"], cwd=root, env=env, capture_output=True, text=True, timeout=60)
            self.assertIn(json.loads(stopped.stdout)["status"], {"stopped", "not_running"})
            status = subprocess.run([str(wrapper), "serve", "--status", "--json"], cwd=root, env=env, capture_output=True, text=True, timeout=60)
            self.assertFalse(json.loads(status.stdout)["running"])

    def test_help_lists_serve_for_the_drift_gate(self) -> None:
        wrapper = REPO / "tools" / "agent-manna" / "agent-manna"
        out = subprocess.run([str(wrapper), "--help"], capture_output=True, text=True, timeout=30).stdout
        self.assertRegex(out, r"\n  serve\s{2,}", msg=out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
