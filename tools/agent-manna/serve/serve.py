#!/usr/bin/env python3
"""`agent-do manna serve`: the human window onto every manna board.

One read-only daemon on a fixed local port. `/` indexes every registered
board across the estate; `/<slug>` renders one project. Running `serve`
inside a project registers that board, starts the daemon if it is not up,
and always prints the project's URL, so any agent asked "show me the board"
runs this and hands the link over.

Agents do not read from this server. The page is a rendering of
`manna context|list|show`, never a source; the only file it writes is its
own registry under $AGENT_DO_HOME/manna/serve/.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

SERVE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVE_DIR))
import board as board_lib  # noqa: E402

STATIC_DIR = SERVE_DIR / "static"
AGENT_DO = SERVE_DIR.parents[2] / "agent-do"

# 7777 is a name, not a bound: Erik's pick (2026-08-24) for a port anyone on
# the estate can remember. Override with --port or MANNA_SERVE_PORT.
DEFAULT_PORT = 7777
DEFAULT_HOST = "127.0.0.1"
SERVER_NAME = "manna-serve"

# The page reads as live when a change lands within the flow-of-thought
# limit (Nielsen, Usability Engineering 1993: 1.0s). Polling file mtimes
# once a second is far under that once render time is added, and costs a
# handful of stat calls per client per second.
POLL_INTERVAL_SECONDS = 1.0

# Boards on this estate nest at most <root>/<project>/<sub>/.manna
# (aldebaran-group/dm-ephemeris/.manna is the deepest today), so a scan
# walks three directory levels below the root it is given.
SCAN_DEPTH = 3
SCAN_SKIP = {".git", "node_modules", "target", ".venv", "venv", "__pycache__", ".manna", ".handoff"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def serve_home() -> Path:
    home = Path(os.environ.get("AGENT_DO_HOME", str(Path.home() / ".agent-do")))
    path = home / "manna" / "serve"
    path.mkdir(parents=True, exist_ok=True)
    return path


def registry_path() -> Path:
    return serve_home() / "boards.json"


def daemon_path() -> Path:
    return serve_home() / "daemon.json"


def log_path() -> Path:
    return serve_home() / "daemon.log"


# ---------------------------------------------------------------- registry


def load_registry() -> dict[str, dict[str, Any]]:
    path = registry_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    boards = data.get("boards") if isinstance(data, dict) else None
    return boards if isinstance(boards, dict) else {}


def save_registry(boards: dict[str, dict[str, Any]]) -> None:
    path = registry_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"version": 1, "boards": boards}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def slug_for(root: Path, boards: dict[str, dict[str, Any]]) -> str:
    """Directory name, or parent--name when another board already owns it."""
    for slug, entry in boards.items():
        if entry.get("path") == str(root):
            return slug
    base = root.name or "root"
    if base not in boards:
        return base
    return f"{root.parent.name}--{base}"


def register_board(root: Path) -> tuple[str, bool]:
    root = root.resolve()
    boards = load_registry()
    slug = slug_for(root, boards)
    fresh = slug not in boards
    boards[slug] = {"path": str(root), "registered_at": boards.get(slug, {}).get("registered_at") or utc_now_iso()}
    save_registry(boards)
    return slug, fresh


def scan_boards(scan_root: Path) -> list[Path]:
    found: list[Path] = []

    def walk(directory: Path, depth: int) -> None:
        if (directory / ".manna").is_dir():
            found.append(directory)
        if depth >= SCAN_DEPTH:
            return
        try:
            children = sorted(p for p in directory.iterdir() if p.is_dir() and not p.is_symlink())
        except OSError:
            return
        for child in children:
            if child.name in SCAN_SKIP or child.name.startswith("."):
                continue
            walk(child, depth + 1)

    walk(scan_root, 0)
    return found


# ---------------------------------------------------------------- daemon state


def read_daemon() -> dict[str, Any] | None:
    path = daemon_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def health(host: str, port: int) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("server") == SERVER_NAME else {"foreign": True}


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ---------------------------------------------------------------- HTTP


class BoardCache:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.states: dict[str, tuple[str, dict[str, Any]]] = {}
        self.gitdirs: dict[str, Path | None] = {}

    def gitdir(self, root: Path) -> Path | None:
        key = str(root)
        if key not in self.gitdirs:
            self.gitdirs[key] = board_lib.git_dir(root)
        return self.gitdirs[key]

    def signature(self, root: Path) -> str:
        return board_lib.signature(root, self.gitdir(root))

    def state(self, slug: str, root: Path) -> tuple[str, dict[str, Any]]:
        sig = self.signature(root)
        with self.lock:
            cached = self.states.get(slug)
            if cached and cached[0] == sig:
                return cached
        state = board_lib.derive(root, AGENT_DO)
        state["slug"] = slug
        with self.lock:
            self.states[slug] = (sig, state)
        return sig, state


CACHE = BoardCache()


def boards_index() -> dict[str, Any]:
    boards = load_registry()
    rows = []
    for slug, entry in sorted(boards.items()):
        root = Path(entry.get("path", ""))
        if root.is_dir() and (root / ".manna").is_dir():
            row = board_lib.summary(root)
        else:
            row = {"name": root.name, "root": str(root), "exists": False, "total": 0, "status_counts": {}, "dreams": 0, "decisions": 0, "drift_count": 0, "drift_generated_at": None, "latest_update": None, "issues_modified_at": None}
        row["slug"] = slug
        row["url"] = f"/{urllib.parse.quote(slug)}"
        rows.append(row)
    rows.sort(key=lambda r: (not r["exists"], r.get("latest_update") or ""), reverse=False)
    rows.sort(key=lambda r: r.get("latest_update") or "", reverse=True)
    rows.sort(key=lambda r: not r["exists"])
    return {"generated_at": utc_now_iso(), "boards": rows, "count": len(rows), "registry": str(registry_path())}


def index_signature() -> str:
    parts = []
    try:
        st = registry_path().stat()
        parts.append(f"registry:{st.st_mtime_ns}:{st.st_size}")
    except OSError:
        parts.append("registry:missing")
    for slug, entry in sorted(load_registry().items()):
        root = Path(entry.get("path", ""))
        parts.append(slug + "=" + CACHE.signature(root))
    return "|".join(parts)


class Handler(SimpleHTTPRequestHandler):
    server_version = f"{SERVER_NAME}/1.0"
    protocol_version = "HTTP/1.1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write(f"[{self.log_date_time_string()}] {fmt % args}\n")
        sys.stdout.flush()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    # -- helpers

    def send_bytes(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_bytes(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), "application/json; charset=utf-8", status)

    def send_page(self, name: str) -> None:
        path = STATIC_DIR / name
        self.send_bytes(path.read_bytes(), "text/html; charset=utf-8")

    def resolve_board(self, slug: str) -> Path | None:
        entry = load_registry().get(slug)
        if not entry:
            return None
        root = Path(entry.get("path", ""))
        return root if (root / ".manna").is_dir() else None

    # -- routing

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        parts = [urllib.parse.unquote(p) for p in parsed.path.split("/") if p]

        if not parts:
            return self.send_page("index.html")
        if parts[0] == "api":
            return self.route_api(parts[1:], parsed.query)
        if parts[0] == "static":
            self.path = "/" + "/".join(parts[1:])
            return super().do_GET()

        slug = parts[0]
        root = self.resolve_board(slug)
        if root is None:
            return self.send_json({"error": f"no registered board named {slug!r}; run `agent-do manna serve` inside the project"}, HTTPStatus.NOT_FOUND)
        rest = parts[1:]
        if not rest:
            return self.send_page("board.html")
        if rest == ["api", "state"]:
            _, state = CACHE.state(slug, root)
            return self.send_json(state)
        if rest == ["api", "events"]:
            return self.stream(lambda: CACHE.signature(root), lambda: CACHE.state(slug, root)[1])
        if rest == ["handoff"]:
            return self.send_handoff(root, parsed.query)
        return self.send_json({"error": "unknown path"}, HTTPStatus.NOT_FOUND)

    def route_api(self, parts: list[str], query: str) -> None:
        if parts == ["health"]:
            return self.send_json({"server": SERVER_NAME, "pid": os.getpid(), "port": self.server.server_address[1], "boards": len(load_registry()), "started_at": getattr(self.server, "started_at", None)})
        if parts == ["boards"]:
            return self.send_json(boards_index())
        if parts == ["events"]:
            return self.stream(index_signature, boards_index)
        return self.send_json({"error": "unknown api path"}, HTTPStatus.NOT_FOUND)

    def stream(self, signature_fn, payload_fn) -> None:
        """Server-sent events: a fresh payload whenever the signature moves."""
        self.close_connection = True
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        previous = None
        try:
            while not getattr(self.server, "stopping", False):
                sig = signature_fn()
                if sig != previous:
                    payload = json.dumps(payload_fn(), ensure_ascii=False, separators=(",", ":"))
                    self.wfile.write(f"event: state\ndata: {payload}\n\n".encode("utf-8"))
                    previous = sig
                else:
                    self.wfile.write(b": hb\n\n")
                self.wfile.flush()
                time.sleep(POLL_INTERVAL_SECONDS)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def send_handoff(self, root: Path, query: str) -> None:
        requested = urllib.parse.parse_qs(query).get("path", [""])[0]
        root = root.resolve()  # macOS: /var is /private/var; compare like with like
        state_dir = root / ".manna"
        handoff_dir_name = board_lib.read_yaml(state_dir / "workflow.yaml").get("handoff_dir") or ".handoff"
        allowed_root = (root / handoff_dir_name).resolve()
        candidate = (root / requested).resolve()
        inside = candidate == allowed_root or allowed_root in candidate.parents
        if not requested or not inside or not candidate.is_file() or candidate.suffix.lower() not in {".md", ".txt", ".source"}:
            return self.send_bytes(b"handoff is missing or outside the board's handoff root", "text/plain; charset=utf-8", HTTPStatus.NOT_FOUND)
        content = candidate.read_text(encoding="utf-8", errors="replace")
        title = html.escape(str(candidate.relative_to(root)))
        body = (
            "<!doctype html><meta charset='utf-8'><meta name='color-scheme' content='dark'>"
            f"<title>{title}</title><link rel='stylesheet' href='/static/styles.css'>"
            f"<main class='handoff'><header class='handoff-head'>{title}</header><pre>{html.escape(content)}</pre></main>"
        ).encode("utf-8")
        self.send_bytes(body, "text/html; charset=utf-8")


def run_server(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.started_at = utc_now_iso()
    server.stopping = False
    bound_port = server.server_address[1]
    daemon_path().write_text(
        json.dumps({"pid": os.getpid(), "host": host, "port": bound_port, "started_at": server.started_at, "log": str(log_path())}, indent=2) + "\n",
        encoding="utf-8",
    )

    def stop(*_: Any) -> None:
        server.stopping = True
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f"{SERVER_NAME}: http://{host}:{bound_port}/  (read-only; boards register via `agent-do manna serve`)")
    sys.stdout.flush()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        try:
            current = read_daemon()
            if current and current.get("pid") == os.getpid():
                daemon_path().unlink()
        except OSError:
            pass


# ---------------------------------------------------------------- CLI


def ensure_daemon(host: str, port: int) -> dict[str, Any]:
    """Return {'status': running|started, 'port': N, 'pid': P} or raise RuntimeError."""
    existing = read_daemon()
    if existing and pid_alive(int(existing.get("pid", 0))):
        live = health(existing.get("host", host), int(existing.get("port", port)))
        if live and not live.get("foreign"):
            return {"status": "running", "port": int(existing["port"]), "pid": int(existing["pid"]), "host": existing.get("host", host)}
    probe = health(host, port)
    if probe and not probe.get("foreign"):
        return {"status": "running", "port": port, "pid": probe.get("pid"), "host": host}
    if probe and probe.get("foreign"):
        raise RuntimeError(f"port {port} is held by something that is not {SERVER_NAME}; pick another with --port")

    log = log_path().open("ab")
    child = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--foreground", "--host", host, "--port", str(port)],
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        cwd=str(serve_home()),
    )
    # Wait for the child's own health answer or its exit: no timeout literal,
    # the child's fate is the clock.
    while child.poll() is None:
        current = read_daemon()
        if current and current.get("pid") == child.pid:
            live = health(host, int(current["port"]))
            if live and not live.get("foreign"):
                return {"status": "started", "port": int(current["port"]), "pid": child.pid, "host": host}
        time.sleep(POLL_INTERVAL_SECONDS / 10)
    raise RuntimeError(f"daemon exited with code {child.returncode}; see {log_path()}")


def stop_daemon() -> dict[str, Any]:
    current = read_daemon()
    if not current or not pid_alive(int(current.get("pid", 0))):
        if current:
            try:
                daemon_path().unlink()
            except OSError:
                pass
        return {"status": "not_running"}
    pid = int(current["pid"])
    os.kill(pid, signal.SIGTERM)
    while pid_alive(pid):
        time.sleep(POLL_INTERVAL_SECONDS / 10)
    try:
        daemon_path().unlink()
    except OSError:
        pass
    return {"status": "stopped", "pid": pid}


def emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2))
        return
    if "url" in payload:
        print(payload["url"])
    for key in ("daemon", "slug", "board", "index"):
        if key in payload and key != "url":
            print(f"  {key}: {payload[key]}")
    if payload.get("note"):
        print(f"  {payload['note']}")


HELP = """Usage: agent-do manna serve [--open] [--json] [--port N] [--host H]
       agent-do manna serve --status | --stop | --scan <dir> | --foreground

Human window onto the board. Read-only. Agents keep `manna context|list|show`.

Running inside a project registers its board with the estate daemon, starts
the daemon if needed, and prints the project URL:
  http://127.0.0.1:7777/<project>      this board
  http://127.0.0.1:7777/               every registered board

Options:
  --open           open the project page in the default browser
  --json           machine-readable result
  --port N         daemon port (default 7777, or MANNA_SERVE_PORT)
  --host H         bind address (default 127.0.0.1; keep it local)
  --status         is the daemon up, which boards are registered
  --stop           stop the daemon
  --scan <dir>     register every board found up to three levels below <dir>
  --foreground     run the daemon in this process (what the daemon itself runs)
"""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="agent-do manna serve", add_help=False)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MANNA_SERVE_PORT", DEFAULT_PORT)))
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--scan", metavar="DIR")
    parser.add_argument("--foreground", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    args = parser.parse_args(argv)

    if args.help:
        print(HELP, end="")
        return 0
    if args.foreground:
        run_server(args.host, args.port)
        return 0
    if args.stop:
        emit(stop_daemon(), args.json)
        return 0
    if args.status:
        current = read_daemon()
        live = None
        if current and pid_alive(int(current.get("pid", 0))):
            live = health(current.get("host", args.host), int(current.get("port", args.port)))
        boards = load_registry()
        payload = {
            "running": bool(live and not live.get("foreign")),
            "daemon": current if live else None,
            "index": f"http://{current.get('host', args.host)}:{current.get('port')}/" if live and current else None,
            "boards": {slug: entry.get("path") for slug, entry in sorted(boards.items())},
            "count": len(boards),
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print("running:", payload["running"], "" if not payload["index"] else payload["index"])
            for slug, path in payload["boards"].items():
                print(f"  /{slug}  {path}")
        return 0

    if args.scan:
        found = scan_boards(Path(args.scan))
        added = []
        for root in found:
            slug, fresh = register_board(root)
            added.append({"slug": slug, "path": str(root), "new": fresh})
        payload = {"scanned": str(Path(args.scan).resolve()), "found": len(found), "registered": added}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"found {len(found)} boards under {payload['scanned']}")
            for row in added:
                print(f"  {'+' if row['new'] else '='} /{row['slug']}  {row['path']}")
        if not found:
            return 0

    root = board_lib.find_board_root(Path.cwd())
    if root is None and not args.scan:
        message = "no .manna/ here or above; run inside a project with a board (or `agent-do manna init`)"
        if args.json:
            print(json.dumps({"success": False, "error": message}))
        else:
            print(message, file=sys.stderr)
        return 2

    try:
        daemon = ensure_daemon(args.host, args.port)
    except RuntimeError as error:
        if args.json:
            print(json.dumps({"success": False, "error": str(error)}))
        else:
            print(f"error: {error}", file=sys.stderr)
        return 1

    base = f"http://{daemon['host']}:{daemon['port']}"
    payload: dict[str, Any] = {"success": True, "daemon": daemon["status"], "pid": daemon["pid"], "port": daemon["port"], "index": f"{base}/"}
    if root is not None:
        slug, _ = register_board(root)
        payload.update({"slug": slug, "board": str(root), "url": f"{base}/{urllib.parse.quote(slug)}"})
        if args.open:
            webbrowser.open(payload["url"])
    else:
        payload["url"] = payload["index"]
        if args.open:
            webbrowser.open(payload["index"])
    payload["note"] = "read-only human view; agents use `agent-do manna context`"
    emit(payload, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
