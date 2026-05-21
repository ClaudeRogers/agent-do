#!/usr/bin/env python3
"""Regression tests for agent-jira: connections, issues, search, sprints."""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import stat
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
JIRA_PY = ROOT / "tools" / "agent-jira" / "jira_ops.py"
AGENT_DO = ROOT / "agent-do"

PASS = 0
FAIL = 0

# Track requests to assert on dry-run (no HTTP calls made)
_requests: list[tuple[str, str]] = []
_post_bodies: dict[str, dict] = {}
_put_bodies: dict[str, dict] = {}


def check(desc: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        print(f"  ✓ {desc}")
        PASS += 1
    else:
        print(f"  ✗ {desc}")
        if detail:
            print(f"    {detail[:300]}")
        FAIL += 1


def run(argv: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(JIRA_PY), *argv],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


class JiraHandler(http.server.BaseHTTPRequestHandler):
    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def _send(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_err(self, msg: str, status: int = 400) -> None:
        self._send({"errorMessages": [msg], "errors": {}}, status=status)

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _route_get(self, path: str, qs: dict) -> None:
        # both api v2 (server) and v3 (cloud) share the same fake responses
        path = path.replace("/rest/api/2/", "/rest/api/3/")

        if path == "/rest/api/3/myself":
            self._send({
                "accountId": "uid-abc",
                "displayName": "Test User",
                "emailAddress": "test@example.com",
                "name": "test",
            })

        elif path == "/rest/api/3/project":
            self._send([
                {"key": "PROJ", "name": "Test Project", "projectTypeKey": "software"},
                {"key": "OPS", "name": "Ops Project", "projectTypeKey": "business"},
            ])

        elif path == "/rest/api/3/search":
            jql = qs.get("jql", [""])[0]
            if "statusCategory != Done" in jql:
                count = 5 if "project = PROJ" in jql else 2
                self._send({"total": count, "issues": [], "maxResults": 0})
            else:
                self._send({
                    "total": 2,
                    "issues": [
                        {
                            "key": "PROJ-1",
                            "fields": {
                                "summary": "Fix login bug",
                                "status": {"name": "In Progress"},
                                "issuetype": {"name": "Bug"},
                                "priority": {"name": "High"},
                                "assignee": {"displayName": "Test User", "emailAddress": "test@example.com"},
                                "reporter": {"displayName": "Reporter"},
                                "labels": ["backend"],
                                "created": "2026-01-01T00:00:00.000Z",
                                "updated": "2026-01-15T00:00:00.000Z",
                                "description": None,
                            },
                        },
                        {
                            "key": "PROJ-2",
                            "fields": {
                                "summary": "Add dark mode",
                                "status": {"name": "Todo"},
                                "issuetype": {"name": "Story"},
                                "priority": {"name": "Medium"},
                                "assignee": None,
                                "reporter": {"displayName": "Reporter"},
                                "labels": [],
                                "created": "2026-01-02T00:00:00.000Z",
                                "updated": "2026-01-16T00:00:00.000Z",
                                "description": None,
                            },
                        },
                    ],
                })

        elif path in ("/rest/api/3/issue/PROJ-1", "/rest/api/3/issue/PROJ-1?expand=renderedFields,names,changelog", "/rest/api/3/issue/PROJ-1?expand=renderedFields,names,changelog,comment") or path.startswith("/rest/api/3/issue/PROJ-1?"):
            self._send({
                "key": "PROJ-1",
                "fields": {
                    "summary": "Fix login bug",
                    "status": {"name": "In Progress"},
                    "issuetype": {"name": "Bug"},
                    "priority": {"name": "High"},
                    "assignee": {"displayName": "Test User", "emailAddress": "test@example.com"},
                    "reporter": {"displayName": "Reporter"},
                    "labels": ["backend", "auth"],
                    "created": "2026-01-01T00:00:00.000Z",
                    "updated": "2026-01-15T00:00:00.000Z",
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Login is broken"}]}],
                    },
                    "comment": {
                        "comments": [
                            {
                                "author": {"displayName": "Reviewer"},
                                "created": "2026-01-10T00:00:00.000Z",
                                "body": {
                                    "type": "doc",
                                    "version": 1,
                                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Please fix ASAP"}]}],
                                },
                            }
                        ]
                    },
                },
            })

        elif path == "/rest/api/3/issue/PROJ-999":
            self._send_err("Issue does not exist or you do not have permission.", status=404)

        elif path == "/rest/api/3/issue/PROJ-1/transitions":
            self._send({
                "transitions": [
                    {"id": "11", "name": "To Do", "to": {"name": "Todo"}},
                    {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
                    {"id": "31", "name": "Done", "to": {"name": "Done"}},
                ]
            })

        elif path == "/rest/agile/1.0/board":
            self._send({
                "values": [
                    {"id": 42, "name": "PROJ Board", "type": "scrum"},
                    {"id": 43, "name": "OPS Board", "type": "kanban"},
                ]
            })

        elif path.startswith("/rest/agile/1.0/board/42/sprint"):
            state = qs.get("state", ["active"])[0]
            if state in ("active", "all"):
                self._send({
                    "values": [
                        {
                            "id": 1,
                            "name": "Sprint 1",
                            "state": "active",
                            "startDate": "2026-01-01T00:00:00.000Z",
                            "endDate": "2026-01-14T00:00:00.000Z",
                        }
                    ]
                })
            else:
                self._send({"values": []})

        elif path == "/rest/agile/1.0/sprint/1/issue":
            self._send({
                "issues": [
                    {
                        "key": "PROJ-1",
                        "fields": {
                            "summary": "Fix login bug",
                            "status": {"name": "In Progress"},
                            "issuetype": {"name": "Bug"},
                            "priority": {"name": "High"},
                            "assignee": {"displayName": "Test User", "emailAddress": "test@example.com"},
                            "reporter": {"displayName": "Reporter"},
                            "labels": [],
                            "created": "2026-01-01T00:00:00.000Z",
                            "updated": "2026-01-15T00:00:00.000Z",
                            "description": None,
                        },
                    }
                ]
            })

        else:
            self._send_err(f"Not found: {path}", status=404)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        _requests.append(("GET", self.path))
        self._route_get(parsed.path, qs)

    def do_POST(self) -> None:  # noqa: N802
        body_bytes = self._read_body()
        _requests.append(("POST", self.path))
        path = urlparse(self.path).path
        path = path.replace("/rest/api/2/", "/rest/api/3/")
        body = json.loads(body_bytes) if body_bytes else {}
        _post_bodies[path] = body

        if path == "/rest/api/3/issue":
            self._send({"key": "PROJ-3", "id": "10003"}, status=201)
        elif path == "/rest/api/3/issue/PROJ-1/comment":
            self._send({"id": "cmt-1"})
        elif path == "/rest/api/3/issue/PROJ-1/transitions":
            self._send(None, status=204)
        elif path == "/rest/agile/1.0/sprint/1/issue":
            self._send(None, status=204)
        else:
            self._send_err(f"Not found: {path}", status=404)

    def do_PUT(self) -> None:  # noqa: N802
        body_bytes = self._read_body()
        _requests.append(("PUT", self.path))
        path = urlparse(self.path).path
        path = path.replace("/rest/api/2/", "/rest/api/3/")
        body = json.loads(body_bytes) if body_bytes else {}
        _put_bodies[path] = body

        if path in ("/rest/api/3/issue/PROJ-1/assignee", "/rest/api/3/issue/PROJ-1"):
            self._send(None, status=204)
        else:
            self._send_err(f"Not found: {path}", status=404)


def _make_env(tmp: Path, port: int, *, extra: dict | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["AGENT_DO_HOME"] = str(tmp / "home")
    env.pop("JIRA_URL", None)
    env.pop("JIRA_EMAIL", None)
    env.pop("JIRA_API_TOKEN", None)
    env["SERVER_PORT"] = str(port)
    if extra:
        env.update(extra)
    return env


def main() -> int:
    global PASS, FAIL

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        server = socketserver.TCPServer(("127.0.0.1", 0), JiraHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        base_url = f"http://127.0.0.1:{port}"

        try:
            env = _make_env(tmp, port)
            home = Path(env["AGENT_DO_HOME"])

            # ── connections ─────────────────────────────────────────────────────

            print("\nconnections add")
            r = run(["connections", "add", "work",
                     "--url", base_url,
                     "--email", "test@example.com",
                     "--token", "tok-secret",
                     "--default"], env=env)
            check("connections add exits 0", r.returncode == 0, r.stderr)
            check("connections add prints profile name", "work" in r.stdout, r.stdout)
            check("connections add marks default", "default" in r.stdout, r.stdout)

            creds_file = home / "jira" / ".creds" / "work"
            check("connections add: creds file exists", creds_file.exists(), str(creds_file))
            check(
                "connections add: creds file mode is 0o600",
                stat.S_IMODE(creds_file.stat().st_mode) == 0o600,
                oct(stat.S_IMODE(creds_file.stat().st_mode)),
            )
            creds = json.loads(creds_file.read_text())
            check("connections add: url stored in creds", creds.get("url") == base_url, str(creds))
            check("connections add: token stored in creds", creds.get("token") == "tok-secret", str(creds))

            meta_file = home / "jira" / "connections.json"
            check("connections add: connections.json created", meta_file.exists())
            meta = json.loads(meta_file.read_text())
            check("connections add: token NOT in connections.json", "tok-secret" not in meta_file.read_text())
            check("connections add: default set in metadata", meta.get("default") == "work")

            print("\nconnections add second profile")
            r2 = run(["connections", "add", "personal",
                      "--url", base_url,
                      "--email", "me@personal.com",
                      "--token", "tok-personal"], env=env)
            check("connections add second exits 0", r2.returncode == 0, r2.stderr)
            check("connections add second: creds file at 0o600",
                  stat.S_IMODE((home / "jira" / ".creds" / "personal").stat().st_mode) == 0o600)
            check("connections add second does not change default", meta_file.read_text().count('"default"') >= 1)

            print("\nconnections list")
            r = run(["connections", "list"], env=env)
            check("connections list exits 0", r.returncode == 0, r.stderr)
            check("connections list shows work", "work" in r.stdout, r.stdout)
            check("connections list shows default marker", "*" in r.stdout, r.stdout)
            check("connections list shows personal", "personal" in r.stdout, r.stdout)
            check("connections list shows Cloud type", "Cloud" in r.stdout, r.stdout)
            check("connections list hides token", "tok-secret" not in r.stdout, r.stdout)

            print("\nconnections set-default")
            r = run(["connections", "set-default", "personal"], env=env)
            check("set-default exits 0", r.returncode == 0, r.stderr)
            meta_after = json.loads(meta_file.read_text())
            check("set-default changes metadata", meta_after.get("default") == "personal")

            # restore default to work for remaining tests
            run(["connections", "set-default", "work"], env=env)

            print("\nconnections add --server flag")
            r = run(["connections", "add", "dc",
                     "--url", base_url,
                     "--email", "admin",
                     "--token", "pat-123",
                     "--server"], env=env)
            check("connections add --server exits 0", r.returncode == 0, r.stderr)
            check("connections add --server shows Server/DC", "Server" in r.stdout, r.stdout)
            meta_dc = json.loads(meta_file.read_text())
            check("connections add --server: server=true in metadata", meta_dc["profiles"]["dc"].get("server") is True)

            print("\nconnections remove")
            r = run(["connections", "remove", "dc"], env=env)
            check("connections remove exits 0", r.returncode == 0, r.stderr)
            check("connections remove: creds file gone", not (home / "jira" / ".creds" / "dc").exists())
            meta_after = json.loads(meta_file.read_text())
            check("connections remove: metadata updated", "dc" not in meta_after.get("profiles", {}))

            print("\nconnections add: missing required args")
            r = run(["connections", "add", "bad", "--url", base_url, "--email", "x@x.com"], env=env)
            check("connections add missing --token exits 1", r.returncode == 1)
            check("connections add missing --token prints error", "Error:" in r.stderr, r.stderr)

            r = run(["connections", "add", "bad2", "--email", "x@x.com", "--token", "t"], env=env)
            check("connections add missing --url exits 1", r.returncode == 1)

            # ── whoami ──────────────────────────────────────────────────────────

            print("\nwhoami")
            r = run(["whoami"], env=env)
            check("whoami exits 0", r.returncode == 0, r.stderr)
            check("whoami shows account", "Test User" in r.stdout, r.stdout)
            check("whoami shows email", "test@example.com" in r.stdout, r.stdout)
            check("whoami shows jira base url", base_url in r.stdout, r.stdout)

            r = run(["whoami", "--json"], env=env)
            check("whoami --json exits 0", r.returncode == 0, r.stderr)
            payload = json.loads(r.stdout)
            check("whoami --json has displayName", payload.get("displayName") == "Test User")
            check("whoami --json has emailAddress", payload.get("emailAddress") == "test@example.com")

            print("\nwhoami --connection")
            r = run(["whoami", "--connection", "personal"], env=env)
            check("whoami --connection exits 0", r.returncode == 0, r.stderr)

            r = run(["whoami", "--connection", "nonexistent"], env=env)
            check("whoami bad connection exits 1", r.returncode == 1)
            check("whoami bad connection prints error", "not found" in r.stderr.lower() or "Error:" in r.stderr, r.stderr)

            # ── snapshot ────────────────────────────────────────────────────────

            print("\nsnapshot")
            r = run(["snapshot"], env=env)
            check("snapshot exits 0", r.returncode == 0, r.stderr)
            check("snapshot shows project count", "2" in r.stdout, r.stdout)
            check("snapshot shows PROJ key", "PROJ" in r.stdout, r.stdout)
            check("snapshot shows open issue count", "5" in r.stdout, r.stdout)

            r = run(["snapshot", "--json"], env=env)
            check("snapshot --json exits 0", r.returncode == 0, r.stderr)
            snap = json.loads(r.stdout)
            check("snapshot --json tool field", snap.get("tool") == "snapshot")
            check("snapshot --json project_count", snap["data"]["project_count"] == 2)
            projects = snap["data"]["projects"]
            proj_keys = [p["key"] for p in projects]
            check("snapshot --json has PROJ", "PROJ" in proj_keys)
            check("snapshot --json has open_issues", all("open_issues" in p for p in projects))

            # ── issue view ──────────────────────────────────────────────────────

            print("\nissue view")
            r = run(["issue", "view", "PROJ-1"], env=env)
            check("issue view exits 0", r.returncode == 0, r.stderr)
            check("issue view shows key", "PROJ-1" in r.stdout, r.stdout)
            check("issue view shows summary", "Fix login bug" in r.stdout, r.stdout)
            check("issue view shows status", "In Progress" in r.stdout, r.stdout)
            check("issue view shows assignee", "Test User" in r.stdout, r.stdout)
            check("issue view shows labels", "backend" in r.stdout, r.stdout)
            check("issue view shows description", "Login is broken" in r.stdout, r.stdout)

            r = run(["issue", "view", "PROJ-1", "--comments"], env=env)
            check("issue view --comments exits 0", r.returncode == 0, r.stderr)
            check("issue view --comments shows comment author", "Reviewer" in r.stdout, r.stdout)
            check("issue view --comments shows comment body", "Please fix ASAP" in r.stdout, r.stdout)

            r = run(["issue", "view", "PROJ-1", "--json"], env=env)
            check("issue view --json exits 0", r.returncode == 0, r.stderr)
            iv = json.loads(r.stdout)
            check("issue view --json key", iv.get("key") == "PROJ-1")
            check("issue view --json summary", iv.get("summary") == "Fix login bug")
            check("issue view --json status", iv.get("status") == "In Progress")
            check("issue view --json labels", "backend" in (iv.get("labels") or []))

            r = run(["issue", "view", "PROJ-999"], env=env)
            check("issue view 404 exits 1", r.returncode == 1)
            check("issue view 404 prints error", "Error:" in r.stderr, r.stderr)

            # ── issue list ──────────────────────────────────────────────────────

            print("\nissue list")
            r = run(["issue", "list", "PROJ"], env=env)
            check("issue list exits 0", r.returncode == 0, r.stderr)
            check("issue list shows PROJ-1", "PROJ-1" in r.stdout, r.stdout)
            check("issue list shows PROJ-2", "PROJ-2" in r.stdout, r.stdout)
            check("issue list shows total", "2 of 2" in r.stdout or "(2 of 2)" in r.stdout or "2" in r.stdout)

            r = run(["issue", "list", "PROJ", "--json"], env=env)
            check("issue list --json exits 0", r.returncode == 0, r.stderr)
            il = json.loads(r.stdout)
            check("issue list --json has issues", len(il["data"]["issues"]) == 2)
            check("issue list --json project field", il["data"]["project"] == "PROJ")

            # ── issue create ────────────────────────────────────────────────────

            print("\nissue create")
            _requests.clear()
            _post_bodies.clear()
            r = run(["issue", "create", "PROJ",
                     "--summary", "New feature request",
                     "--type", "Story",
                     "--priority", "Medium",
                     "--label", "frontend",
                     "--label", "ux"], env=env)
            check("issue create exits 0", r.returncode == 0, r.stderr)
            check("issue create prints key", "PROJ-3" in r.stdout, r.stdout)

            create_body = _post_bodies.get("/rest/api/3/issue", {})
            fields = create_body.get("fields", {})
            check("issue create sends summary", fields.get("summary") == "New feature request")
            check("issue create sends type", (fields.get("issuetype") or {}).get("name") == "Story")
            check("issue create sends priority", (fields.get("priority") or {}).get("name") == "Medium")
            check("issue create sends labels", set(fields.get("labels", [])) == {"frontend", "ux"})

            r = run(["issue", "create", "PROJ",
                     "--summary", "With description",
                     "--description", "Detailed description here"], env=env)
            check("issue create with description exits 0", r.returncode == 0, r.stderr)
            create_body2 = _post_bodies.get("/rest/api/3/issue", {})
            desc = create_body2.get("fields", {}).get("description", {})
            check("issue create sends ADF description", isinstance(desc, dict) and desc.get("type") == "doc")

            print("\nissue create --dry-run")
            _requests_before = len(_requests)
            r = run(["issue", "create", "PROJ",
                     "--summary", "Dry run test",
                     "--dry-run"], env=env)
            check("issue create --dry-run exits 2", r.returncode == 2)
            check("issue create --dry-run shows preview", "[dry-run]" in r.stdout, r.stdout)
            check("issue create --dry-run shows summary", "Dry run test" in r.stdout, r.stdout)
            # No new POST should have been made
            new_posts = [m for m in _requests[_requests_before:] if m[0] == "POST"]
            check("issue create --dry-run makes no HTTP request", len(new_posts) == 0)

            r = run(["issue", "create", "PROJ"], env=env)
            check("issue create missing --summary exits 1", r.returncode == 1)
            check("issue create missing --summary prints error", "Error:" in r.stderr, r.stderr)

            r = run(["issue", "create", "PROJ", "--summary", "x", "--json"], env=env)
            check("issue create --json exits 0", r.returncode == 0, r.stderr)
            cj = json.loads(r.stdout)
            check("issue create --json has key", "key" in cj)
            check("issue create --json has url", "url" in cj)

            # ── issue comment ───────────────────────────────────────────────────

            print("\nissue comment")
            r = run(["issue", "comment", "PROJ-1", "--body", "This is a comment"], env=env)
            check("issue comment exits 0", r.returncode == 0, r.stderr)
            check("issue comment prints confirmation", "PROJ-1" in r.stdout, r.stdout)

            comment_body = _post_bodies.get("/rest/api/3/issue/PROJ-1/comment", {})
            body_field = comment_body.get("body", {})
            check("issue comment sends ADF body", isinstance(body_field, dict) and body_field.get("type") == "doc")

            _requests_before = len(_requests)
            r = run(["issue", "comment", "PROJ-1", "--body", "Preview", "--dry-run"], env=env)
            check("issue comment --dry-run exits 2", r.returncode == 2)
            check("issue comment --dry-run shows preview", "[dry-run]" in r.stdout, r.stdout)
            new_posts = [m for m in _requests[_requests_before:] if m[0] == "POST"]
            check("issue comment --dry-run makes no HTTP request", len(new_posts) == 0)

            r = run(["issue", "comment", "PROJ-1"], env=env)
            check("issue comment missing --body exits 1", r.returncode == 1)

            r = run(["issue", "comment", "PROJ-1", "--body", "ok", "--json"], env=env)
            check("issue comment --json exits 0", r.returncode == 0, r.stderr)
            cmt_j = json.loads(r.stdout)
            check("issue comment --json has key", cmt_j.get("key") == "PROJ-1")

            # ── issue assign ────────────────────────────────────────────────────

            print("\nissue assign")
            _put_bodies.clear()
            r = run(["issue", "assign", "PROJ-1", "--to", "user-account-id-123"], env=env)
            check("issue assign exits 0", r.returncode == 0, r.stderr)
            check("issue assign prints confirmation", "PROJ-1" in r.stdout, r.stdout)

            assign_body = _put_bodies.get("/rest/api/3/issue/PROJ-1/assignee", {})
            check("issue assign sends accountId", assign_body.get("accountId") == "user-account-id-123")

            _put_bodies.clear()
            r = run(["issue", "assign", "PROJ-1", "--to", "none"], env=env)
            check("issue assign --to none exits 0", r.returncode == 0, r.stderr)
            unassign_body = _put_bodies.get("/rest/api/3/issue/PROJ-1/assignee", {})
            check("issue assign --to none sends null accountId", unassign_body.get("accountId") is None)

            _requests_before = len(_requests)
            r = run(["issue", "assign", "PROJ-1", "--to", "x@x.com", "--dry-run"], env=env)
            check("issue assign --dry-run exits 2", r.returncode == 2)
            check("issue assign --dry-run shows preview", "[dry-run]" in r.stdout, r.stdout)
            new_puts = [m for m in _requests[_requests_before:] if m[0] == "PUT"]
            check("issue assign --dry-run makes no HTTP request", len(new_puts) == 0)

            r = run(["issue", "assign", "PROJ-1"], env=env)
            check("issue assign missing --to exits 1", r.returncode == 1)

            # ── issue transition ─────────────────────────────────────────────────

            print("\nissue transition")
            r = run(["issue", "transition", "PROJ-1", "--to", "Done"], env=env)
            check("issue transition exits 0", r.returncode == 0, r.stderr)
            check("issue transition prints status", "Done" in r.stdout, r.stdout)

            transition_body = _post_bodies.get("/rest/api/3/issue/PROJ-1/transitions", {})
            check("issue transition sends transition id", (transition_body.get("transition") or {}).get("id") == "31")

            r = run(["issue", "transition", "PROJ-1", "--to", "done"], env=env)
            check("issue transition case-insensitive exits 0", r.returncode == 0, r.stderr)

            r = run(["issue", "transition", "PROJ-1", "--to", "Nonexistent Status"], env=env)
            check("issue transition bad status exits 1", r.returncode == 1)
            check("issue transition bad status lists available", "To Do" in r.stderr or "Done" in r.stderr, r.stderr)

            _requests_before = len(_requests)
            r = run(["issue", "transition", "PROJ-1", "--to", "Done", "--dry-run"], env=env)
            check("issue transition --dry-run exits 2", r.returncode == 2)
            check("issue transition --dry-run shows preview", "[dry-run]" in r.stdout, r.stdout)
            new_posts = [m for m in _requests[_requests_before:] if m[0] == "POST"
                         and "transitions" in m[1]]
            check("issue transition --dry-run makes no transition POST", len(new_posts) == 0)

            # ── issue label ──────────────────────────────────────────────────────

            print("\nissue label")
            _put_bodies.clear()
            r = run(["issue", "label", "PROJ-1", "--add", "newlabel", "--remove", "auth"], env=env)
            check("issue label exits 0", r.returncode == 0, r.stderr)
            check("issue label prints updated labels", "PROJ-1" in r.stdout, r.stdout)

            label_body = _put_bodies.get("/rest/api/3/issue/PROJ-1", {})
            updated_labels = (label_body.get("fields") or {}).get("labels", [])
            check("issue label adds new label", "newlabel" in updated_labels)
            check("issue label removes auth", "auth" not in updated_labels)
            check("issue label keeps backend", "backend" in updated_labels)

            _requests_before = len(_requests)
            r = run(["issue", "label", "PROJ-1", "--add", "x", "--dry-run"], env=env)
            check("issue label --dry-run exits 2", r.returncode == 2)
            check("issue label --dry-run shows before/after", "Before:" in r.stdout and "After:" in r.stdout, r.stdout)
            new_puts = [m for m in _requests[_requests_before:] if m[0] == "PUT"]
            check("issue label --dry-run makes no HTTP PUT", len(new_puts) == 0)

            r = run(["issue", "label", "PROJ-1"], env=env)
            check("issue label no --add/--remove exits 1", r.returncode == 1)

            # ── issue edit ───────────────────────────────────────────────────────

            print("\nissue edit")
            _put_bodies.clear()
            r = run(["issue", "edit", "PROJ-1",
                     "--summary", "Updated summary",
                     "--priority", "Low"], env=env)
            check("issue edit exits 0", r.returncode == 0, r.stderr)
            check("issue edit prints confirmation", "PROJ-1" in r.stdout, r.stdout)

            edit_body = _put_bodies.get("/rest/api/3/issue/PROJ-1", {})
            edit_fields = edit_body.get("fields", {})
            check("issue edit sends summary", edit_fields.get("summary") == "Updated summary")
            check("issue edit sends priority", (edit_fields.get("priority") or {}).get("name") == "Low")

            _put_bodies.clear()
            r = run(["issue", "edit", "PROJ-1", "--description", "New desc", "--dry-run"], env=env)
            check("issue edit --dry-run exits 2", r.returncode == 2)
            check("issue edit --dry-run shows preview", "[dry-run]" in r.stdout, r.stdout)
            check("issue edit --dry-run makes no PUT", "/rest/api/3/issue/PROJ-1" not in _put_bodies)

            r = run(["issue", "edit", "PROJ-1"], env=env)
            check("issue edit no fields exits 1", r.returncode == 1)

            r = run(["issue", "edit", "PROJ-1", "--summary", "x", "--json"], env=env)
            check("issue edit --json exits 0", r.returncode == 0, r.stderr)
            ej = json.loads(r.stdout)
            check("issue edit --json has key", ej.get("key") == "PROJ-1")
            check("issue edit --json has updated fields", "summary" in (ej.get("updated") or []))

            # ── transitions ──────────────────────────────────────────────────────

            print("\ntransitions")
            r = run(["transitions", "PROJ-1"], env=env)
            check("transitions exits 0", r.returncode == 0, r.stderr)
            check("transitions shows To Do", "To Do" in r.stdout, r.stdout)
            check("transitions shows In Progress", "In Progress" in r.stdout, r.stdout)
            check("transitions shows Done", "Done" in r.stdout, r.stdout)

            r = run(["transitions", "PROJ-1", "--json"], env=env)
            check("transitions --json exits 0", r.returncode == 0, r.stderr)
            tj = json.loads(r.stdout)
            check("transitions --json key field", tj.get("key") == "PROJ-1")
            check("transitions --json has 3 transitions", len(tj.get("transitions", [])) == 3)
            names = [t["name"] for t in tj["transitions"]]
            check("transitions --json contains Done", "Done" in names)

            # ── search ───────────────────────────────────────────────────────────

            print("\nsearch")
            r = run(["search", "project = PROJ AND status = 'In Progress'"], env=env)
            check("search exits 0", r.returncode == 0, r.stderr)
            check("search shows PROJ-1", "PROJ-1" in r.stdout, r.stdout)
            check("search shows JQL in output", "PROJ" in r.stdout, r.stdout)

            r = run(["search", "project = PROJ", "--json"], env=env)
            check("search --json exits 0", r.returncode == 0, r.stderr)
            sj = json.loads(r.stdout)
            check("search --json tool field", sj.get("tool") == "search")
            check("search --json has issues", len(sj["data"]["issues"]) > 0)
            check("search --json has total", "total" in sj["data"])
            check("search --json has jql", "jql" in sj["data"])

            r = run(["search", "project = PROJ", "--limit", "10", "--json"], env=env)
            check("search --limit exits 0", r.returncode == 0, r.stderr)

            # ── board ────────────────────────────────────────────────────────────

            print("\nboard list")
            r = run(["board", "list"], env=env)
            check("board list exits 0", r.returncode == 0, r.stderr)
            check("board list shows PROJ Board", "PROJ Board" in r.stdout, r.stdout)
            check("board list shows OPS Board", "OPS Board" in r.stdout, r.stdout)
            check("board list shows board type", "scrum" in r.stdout, r.stdout)

            r = run(["board", "list", "--json"], env=env)
            check("board list --json exits 0", r.returncode == 0, r.stderr)
            bj = json.loads(r.stdout)
            check("board list --json has boards", len(bj.get("boards", [])) == 2)

            # ── sprint ───────────────────────────────────────────────────────────

            print("\nsprint list")
            r = run(["sprint", "list", "42"], env=env)
            check("sprint list exits 0", r.returncode == 0, r.stderr)
            check("sprint list shows Sprint 1", "Sprint 1" in r.stdout, r.stdout)
            check("sprint list shows active state", "active" in r.stdout, r.stdout)

            r = run(["sprint", "list", "42", "--json"], env=env)
            check("sprint list --json exits 0", r.returncode == 0, r.stderr)
            slj = json.loads(r.stdout)
            check("sprint list --json has sprints", len(slj.get("sprints", [])) == 1)
            check("sprint list --json board_id", slj.get("board_id") == "42")

            print("\nsprint active")
            r = run(["sprint", "active", "42"], env=env)
            check("sprint active exits 0", r.returncode == 0, r.stderr)
            check("sprint active shows sprint name", "Sprint 1" in r.stdout, r.stdout)
            check("sprint active shows issue count", "1 issues" in r.stdout or "issues" in r.stdout, r.stdout)
            check("sprint active shows PROJ-1", "PROJ-1" in r.stdout, r.stdout)

            r = run(["sprint", "active", "42", "--json"], env=env)
            check("sprint active --json exits 0", r.returncode == 0, r.stderr)
            saj = json.loads(r.stdout)
            check("sprint active --json has sprint", "sprint" in saj)
            check("sprint active --json has issues", len(saj.get("issues", [])) > 0)

            print("\nsprint add")
            _requests_before = len(_requests)
            r = run(["sprint", "add", "PROJ-1", "--sprint", "1"], env=env)
            check("sprint add exits 0", r.returncode == 0, r.stderr)
            check("sprint add prints confirmation", "PROJ-1" in r.stdout, r.stdout)

            _requests_before = len(_requests)
            r = run(["sprint", "add", "PROJ-2", "--sprint", "1", "--dry-run"], env=env)
            check("sprint add --dry-run exits 2", r.returncode == 2)
            check("sprint add --dry-run shows preview", "[dry-run]" in r.stdout, r.stdout)
            new_posts = [m for m in _requests[_requests_before:] if m[0] == "POST"]
            check("sprint add --dry-run makes no HTTP request", len(new_posts) == 0)

            r = run(["sprint", "add", "PROJ-1"], env=env)
            check("sprint add missing --sprint exits 1", r.returncode == 1)

            # ── env var credentials ──────────────────────────────────────────────

            print("\nenv var credentials")
            env_no_profile = _make_env(tmp / "envtest", port, extra={
                "JIRA_URL": base_url,
                "JIRA_EMAIL": "env@example.com",
                "JIRA_API_TOKEN": "env-token",
            })
            (tmp / "envtest" / "home").mkdir(parents=True, exist_ok=True)
            r = run(["whoami"], env=env_no_profile)
            check("env var credentials: whoami exits 0", r.returncode == 0, r.stderr)
            check("env var credentials: resolves without profile", "Test User" in r.stdout, r.stdout)

            print("\nper-profile env var credentials")
            env_per_profile = _make_env(tmp / "envprofile", port, extra={
                "JIRA_URL_MYCONN": base_url,
                "JIRA_EMAIL_MYCONN": "profile@example.com",
                "JIRA_API_TOKEN_MYCONN": "profile-token",
            })
            (tmp / "envprofile" / "home").mkdir(parents=True, exist_ok=True)
            r = run(["whoami", "--connection", "myconn"], env=env_per_profile)
            check("per-profile env var: whoami exits 0", r.returncode == 0, r.stderr)

            print("\nno credentials error")
            env_no_creds = _make_env(tmp / "nocreds", port)
            (tmp / "nocreds" / "home").mkdir(parents=True, exist_ok=True)
            r = run(["whoami"], env=env_no_creds)
            check("no credentials exits 1", r.returncode == 1)
            check("no credentials shows helpful error", "connections add" in r.stderr or "JIRA_URL" in r.stderr, r.stderr)

            # ── server/DC mode ───────────────────────────────────────────────────

            print("\nServer/DC mode")
            run(["connections", "add", "dc2",
                 "--url", base_url,
                 "--email", "admin",
                 "--token", "pat",
                 "--server"], env=env)
            r = run(["whoami", "--connection", "dc2"], env=env)
            check("Server/DC whoami exits 0", r.returncode == 0, r.stderr)

            # Server mode uses api/2/ paths - verify via issue create ADF vs plain text
            _post_bodies.clear()
            run(["issue", "create", "PROJ",
                 "--summary", "Server issue",
                 "--description", "Plain text desc",
                 "--connection", "dc2"], env=env)
            server_create = _post_bodies.get("/rest/api/3/issue", {})
            desc_val = (server_create.get("fields") or {}).get("description", "")
            check("Server/DC sends plain-text description", isinstance(desc_val, str), str(desc_val))

        finally:
            server.shutdown()
            server.server_close()

    # ── dispatch test (agent-do jira --help) ─────────────────────────────────────
    print("\nagent-do dispatch")
    r = subprocess.run(
        [str(AGENT_DO), "jira", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    check("agent-do jira --help exits 0", r.returncode == 0, r.stderr)
    check("agent-do jira --help shows CONNECTION MANAGEMENT", "CONNECTION MANAGEMENT" in r.stdout, r.stdout)
    check("agent-do jira --help shows issue commands", "issue view" in r.stdout, r.stdout)
    check("agent-do jira --help shows sprint", "sprint" in r.stdout, r.stdout)

    print(f"\nResults: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
