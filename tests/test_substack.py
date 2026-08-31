#!/usr/bin/env python3
"""Focused tests for agent-do substack: converter units + full offline API loop."""

from __future__ import annotations

import http.server
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "agent-substack"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module():
    loader = importlib.machinery.SourceFileLoader("agent_substack", str(TOOL))
    spec = importlib.util.spec_from_loader("agent_substack", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Converter units
# ---------------------------------------------------------------------------

def test_converter(mod) -> None:
    md = (
        "# My Title\n\n"
        "Intro with **bold**, *em*, `code`, and a [link](https://x.test).\n\n"
        "## Section\n\n"
        "> quoted line one\n> quoted line two\n\n"
        "- alpha\n- beta with **bold**\n\n"
        "1. one\n2. two\n\n"
        "```python\nprint('hi')\n```\n\n"
        "---\n\n"
        "![alt text](https://x.test/pic.png)\n\n"
        "Closing.\n"
    )
    title, body = mod.extract_title(md)
    require(title == "My Title", f"extract_title got {title!r}")
    require("# My Title" not in body, "H1 must be removed from body")

    doc = mod.markdown_to_doc(body)
    types = [node["type"] for node in doc["content"]]
    require(types == [
        "paragraph", "heading", "blockquote", "bullet_list", "ordered_list",
        "code_block", "horizontal_rule", "captionedImage", "paragraph",
    ], f"block sequence wrong: {types}")

    intro = doc["content"][0]["content"]
    marks = {frozenset(m["type"] for m in n.get("marks", [])) for n in intro}
    require(frozenset({"strong"}) in marks, "missing strong mark")
    require(frozenset({"em"}) in marks, "missing em mark")
    require(frozenset({"code"}) in marks, "missing code mark")
    link_nodes = [n for n in intro for m in n.get("marks", []) if m["type"] == "link"]
    require(bool(link_nodes) and link_nodes[0]["text"] == "link", "missing link node")

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "text":
                require(bool(node.get("text")), "empty text node emitted")
            for child in node.get("content", []) or []:
                walk(child)

    walk(doc)

    heading = doc["content"][1]
    require(heading["attrs"]["level"] == 2, "heading level wrong")
    code_block = doc["content"][5]
    require(code_block["attrs"]["language"] == "python", "code language lost")
    require(code_block["content"][0]["text"] == "print('hi')", "code text lost")
    image = doc["content"][7]
    require(image["content"][0]["attrs"]["src"] == "https://x.test/pic.png", "image src lost")

    text = mod.doc_plain_text(doc)
    require("alpha" in text and "Closing." in text, "plain text extraction incomplete")
    require(mod.doc_plain_text(json.dumps(doc)) == text, "string-form doc must extract identically")


def test_normalize(mod) -> None:
    n = mod.normalize_publication
    require(n("foo") == "https://foo.substack.com", "bare subdomain")
    require(n("foo.substack.com") == "https://foo.substack.com", "domain form")
    require(n("https://foo.substack.com/") == "https://foo.substack.com", "url form")
    require(n("https://essays.example.com") == "https://essays.example.com", "custom domain")


# ---------------------------------------------------------------------------
# Offline API loop against a fixture server
# ---------------------------------------------------------------------------

class FakeSubstack(http.server.BaseHTTPRequestHandler):
    drafts: dict = {}
    next_id = 111
    seen_cookies: list = []
    published: list = []

    def _send(self, payload, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:  # noqa: N802
        FakeSubstack.seen_cookies.append(self.headers.get("Cookie") or "")
        path = self.path.split("?")[0]
        if path == "/api/v1/drafts":
            self._send(list(FakeSubstack.drafts.values()))
        elif path == "/api/v1/subscription":
            self._send({"user_id": 42})
        elif path == "/api/v1/archive":
            self._send([{"id": 9, "title": "older post", "post_date": "2026-08-01", "canonical_url": "https://pub.test/p/older"}])
        elif path.startswith("/api/v1/drafts/") and path.endswith("/prepublish"):
            self._send({})
        elif path.startswith("/api/v1/drafts/"):
            draft_id = path.rsplit("/", 1)[1]
            draft = FakeSubstack.drafts.get(draft_id)
            self._send(draft if draft else {"error": "not found"}, 200 if draft else 404)
        else:
            self._send({"error": f"unexpected GET {path}"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        FakeSubstack.seen_cookies.append(self.headers.get("Cookie") or "")
        path = self.path.split("?")[0]
        if path == "/api/v1/drafts":
            payload = self._body()
            draft_id = FakeSubstack.next_id
            FakeSubstack.next_id += 1
            record = {"id": draft_id, **payload}
            FakeSubstack.drafts[str(draft_id)] = record
            self._send(record)
        elif path.endswith("/publish"):
            draft_id = path.split("/")[-2]
            FakeSubstack.published.append({"id": draft_id, "send": self._body().get("send")})
            self._send({"id": draft_id, "canonical_url": f"https://pub.test/p/post-{draft_id}"})
        else:
            self._send({"error": f"unexpected POST {path}"}, 404)

    def do_PUT(self) -> None:  # noqa: N802
        FakeSubstack.seen_cookies.append(self.headers.get("Cookie") or "")
        path = self.path.split("?")[0]
        draft_id = path.rsplit("/", 1)[1]
        payload = self._body()
        record = {"id": int(draft_id), **payload}
        FakeSubstack.drafts[draft_id] = record
        self._send(record)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - quiet
        del format, args


def run_cli(env: dict, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *argv],
        capture_output=True, text=True, env=env, timeout=60,
    )


def test_api_loop() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeSubstack)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions = tmp_path / "sessions" / "substack"
            sessions.mkdir(parents=True)
            (sessions / "storage.json").write_text(json.dumps({
                "cookies": [
                    {"name": "substack.sid", "value": "test-sid", "domain": ".substack.com"},
                    {"name": "other", "value": "x", "domain": "example.com"},
                ]
            }))
            md = tmp_path / "essay.md"
            md.write_text("# Essay Title\n\nBody paragraph with **bold**.\n")

            env = {
                **os.environ,
                "AGENT_DO_HOME": str(tmp_path / "home"),
                "AGENT_BROWSE_SESSIONS_DIR": str(tmp_path / "sessions"),
                "AGENT_SUBSTACK_API_BASE": f"http://127.0.0.1:{port}",
                "AGENT_SUBSTACK_ACCOUNT_BASE": f"http://127.0.0.1:{port}",
            }

            # not connected yet -> actionable refusal
            result = run_cli(env, "drafts")
            require(result.returncode != 0, "drafts before connect must fail")
            require("connect" in result.stderr, f"refusal must name the fix: {result.stderr}")

            # connect
            result = run_cli(env, "connect", "--publication", "pub", "--json")
            require(result.returncode == 0, f"connect failed: {result.stderr}")
            connected = json.loads(result.stdout)
            require(connected["user_id"] == 42, f"user_id not resolved: {connected}")
            require(connected["base_url"] == "https://pub.substack.com", "config must keep the real base_url")

            # draft
            result = run_cli(env, "draft", str(md), "--json")
            require(result.returncode == 0, f"draft failed: {result.stderr}")
            created = json.loads(result.stdout)
            draft_id = str(created["draft_id"])
            require(created["title"] == "Essay Title", "H1 must become the title")
            stored = FakeSubstack.drafts[draft_id]
            require(stored["draft_bylines"] == [{"id": 42, "is_guest": False}], "byline must ride the resolved user id")
            body_doc = json.loads(stored["draft_body"])
            require(body_doc["type"] == "doc", "draft_body must be a serialized ProseMirror doc")

            # verify via receipt
            result = run_cli(env, "verify", draft_id, "--json")
            require(result.returncode == 0, f"verify failed: {result.stderr}")
            verdict = json.loads(result.stdout)
            require(verdict["body_match"] is True, f"receipt hash must match remote: {verdict}")

            # verify via file
            result = run_cli(env, "verify", draft_id, "--file", str(md), "--json")
            verdict = json.loads(result.stdout)
            require(verdict["text_match"] is True, f"file text must match remote: {verdict}")
            require(verdict["title_match"] is True, f"title must match: {verdict}")

            # update
            md.write_text("# Essay Title\n\nRevised paragraph.\n")
            result = run_cli(env, "update", draft_id, str(md), "--json")
            require(result.returncode == 0, f"update failed: {result.stderr}")
            require("Revised paragraph." in FakeSubstack.drafts[draft_id]["draft_body"], "update must replace body")

            # publish without --email must not send
            result = run_cli(env, "publish", draft_id, "--json")
            require(result.returncode == 0, f"publish failed: {result.stderr}")
            published = json.loads(result.stdout)
            require(published["email_sent"] is False, "email must default to NOT sent")
            require(FakeSubstack.published[-1]["send"] is False, "publish body must carry send=false")
            require(published["post_url"] == f"https://pub.test/p/post-{draft_id}", "post url must surface")

            # snapshot carries totals
            result = run_cli(env, "snapshot", "--json")
            snap = json.loads(result.stdout)
            require(snap["drafts_total"] == len(FakeSubstack.drafts), "snapshot must carry draft totals")
            require(snap["recent_posts_total"] == 1, "snapshot must carry post totals")

            # receipts recorded every write
            result = run_cli(env, "receipts", "--json")
            receipts = json.loads(result.stdout)
            actions = [r["action"] for r in receipts["receipts"]]
            require(actions == ["draft", "update", "publish"], f"receipt trail wrong: {actions}")
            require(receipts["total"] == 3, "receipts must carry totals")

            # image resolver refuses exfiltration shapes: absolute paths,
            # traversal out of the essay dir, and non-image files
            secret = tmp_path / "secret.txt"
            secret.write_text("not an image")
            for bad_src, label in (
                (str(secret), "absolute path"),
                ("../secret.txt", "path traversal"),
            ):
                essay_dir = tmp_path / "essays"
                essay_dir.mkdir(exist_ok=True)
                bad_md = essay_dir / "bad.md"
                bad_md.write_text(f"# T\n\n![x]({bad_src})\n")
                result = run_cli(env, "draft", str(bad_md))
                require(result.returncode != 0, f"{label} must be refused")
                require("image path" in result.stderr, f"{label} refusal must name the path problem: {result.stderr}")
            not_image = tmp_path / "essays" / "notes.txt"
            not_image.write_text("plain text")
            bad_md = tmp_path / "essays" / "bad.md"
            bad_md.write_text("# T\n\n![x](notes.txt)\n")
            result = run_cli(env, "draft", str(bad_md))
            require(result.returncode != 0, "non-image upload must be refused")
            require("not an image" in result.stderr, f"mime refusal must say so: {result.stderr}")

            # cookies rode every request, filtered to substack domains
            require(all("substack.sid=test-sid" in c for c in FakeSubstack.seen_cookies), "cookie must ride every request")
            require(all("other=x" not in c for c in FakeSubstack.seen_cookies), "non-substack cookies must not leak")
    finally:
        server.shutdown()


def main() -> int:
    mod = load_module()
    test_converter(mod)
    test_normalize(mod)
    test_api_loop()
    print("agent-substack tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
