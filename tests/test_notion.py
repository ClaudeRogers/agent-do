#!/usr/bin/env python3
"""Contract tests for agent-notion.

These tests use AGENT_NOTION_MOCK_FILE so they never hit the live Notion API.
They validate the agent-facing contract: modern API shape, structured JSON,
credential presentation, recursive reads, verified writes, cache sync/search,
schema adoption, and webhook ingestion.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "agent-notion"
sys.path.insert(0, str(ROOT / "tools" / "notion_lib"))
sys.path.insert(0, str(ROOT / "lib"))

from engine import blocks_from_text, extract_id, normalize_uuid, rich_text_plain  # noqa: E402
from registry import load_registry  # noqa: E402


PAGE_ID = "11111111-1111-1111-1111-111111111111"
BLOCK_ID = "22222222-2222-2222-2222-222222222222"
DATA_SOURCE_ID = "33333333-3333-3333-3333-333333333333"
USER_ID = "44444444-4444-4444-4444-444444444444"
COMMENT_ID = "55555555-5555-5555-5555-555555555555"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_tool(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(TOOL), *args], cwd=ROOT, env=env, text=True, capture_output=True, check=False)


def page(title: str = "Agent Do Release Decision", page_id: str = PAGE_ID) -> dict:
    return {
        "object": "page",
        "id": page_id,
        "url": f"https://www.notion.so/{page_id.replace('-', '')}",
        "created_time": "2026-05-20T00:00:00Z",
        "last_edited_time": "2026-05-20T01:00:00Z",
        "parent": {"type": "data_source_id", "data_source_id": DATA_SOURCE_ID},
        "properties": {"Name": {"type": "title", "title": [{"plain_text": title, "text": {"content": title}}]}},
    }


def data_source(title: str = "Team Tasks") -> dict:
    return {
        "object": "data_source",
        "id": DATA_SOURCE_ID,
        "url": f"https://www.notion.so/{DATA_SOURCE_ID.replace('-', '')}",
        "title": [{"plain_text": title, "text": {"content": title}}],
        "properties": {"Project": {"type": "title", "title": {}}},
    }


def user() -> dict:
    return {"object": "user", "id": USER_ID, "type": "person", "name": "Chris Tyrrell"}


def bot() -> dict:
    return {"object": "user", "id": "bot-id", "type": "bot", "name": "agent-do", "bot": {"owner": {"type": "workspace"}}}


def mock_file(tmp: Path) -> Path:
    responses = {
        "GET /users/me": bot(),
        "GET /users": {"object": "list", "results": [user()], "has_more": False},
        "POST /search": {"object": "list", "results": [page(), data_source()], "has_more": False},
        f"GET /pages/{PAGE_ID}": page(),
        f"GET /data_sources/{DATA_SOURCE_ID}": data_source(),
        f"POST /data_sources/{DATA_SOURCE_ID}/query": {"object": "list", "results": [page()], "has_more": False},
        f"GET /blocks/{PAGE_ID}/children": {
            "object": "list",
            "results": [
                {
                    "object": "block",
                    "id": BLOCK_ID,
                    "type": "paragraph",
                    "has_children": False,
                    "parent": {"type": "page_id", "page_id": PAGE_ID},
                    "paragraph": {"rich_text": [{"plain_text": "Use Notion for shared execution.", "text": {"content": "Use Notion for shared execution."}}]},
                },
                {
                    "object": "block",
                    "id": "child-page-block-id",
                    "type": "child_page",
                    "has_children": True,
                    "parent": {"type": "page_id", "page_id": PAGE_ID},
                    "child_page": {"title": "Nested workspace hub"},
                }
            ],
            "has_more": False,
        },
        "POST /pages": page("Created Team Decision"),
        f"GET /pages/{PAGE_ID}?page_size=100": page(),
        "POST /comments": {
            "object": "comment",
            "id": COMMENT_ID,
            "discussion_id": "discussion-id",
            "created_time": "2026-05-20T02:00:00Z",
            "rich_text": [{"plain_text": "Please review", "text": {"content": "Please review"}}],
        },
    }
    path = tmp / "notion-mock.json"
    path.write_text(json.dumps(responses), encoding="utf-8")
    return path


def env_for(tmp: Path) -> tuple[dict[str, str], Path]:
    record = tmp / "requests.jsonl"
    env = os.environ.copy()
    env["AGENT_DO_HOME"] = str(tmp / "home")
    env["AGENT_NOTION_WORKSPACE_ID"] = "test-workspace"
    env["AGENT_NOTION_MOCK_FILE"] = str(mock_file(tmp))
    env["AGENT_NOTION_MOCK_RECORD"] = str(record)
    env["AGENT_DO_CREDS_SERVICE"] = "agent-do-test-notion"
    env["NOTION_TOKEN"] = "test-notion-token"
    env["NOTION_WEBHOOK_VERIFICATION_TOKEN"] = "webhook-secret"
    return env, record


def parse_json(proc: subprocess.CompletedProcess[str]) -> dict:
    require(proc.stdout.strip(), f"expected stdout json, stderr={proc.stderr}")
    return json.loads(proc.stdout)


def test_static_surface() -> None:
    help_out = subprocess.run([str(TOOL), "--help"], cwd=ROOT, text=True, capture_output=True, check=False)
    require(help_out.returncode == 0, help_out.stderr)
    for needle in ("Notion-Version 2025-09-03", "data-sources list", "bootstrap-team", "webhooks ingest", "embed refresh"):
        require(needle in help_out.stdout, f"help missing {needle}")

    registry = load_registry()
    entry = registry["tools"]["notion"]
    require("NOTION_TOKEN" in entry["credentials"]["required"], "notion must require NOTION_TOKEN")
    require("data-sources" in entry["commands"], "notion registry must expose data-sources")
    require("routing" in entry and "notion" in entry["routing"]["discover_keywords"], "notion routing missing")


def test_id_normalization() -> None:
    compact = "11111111111111111111111111111111"
    require(normalize_uuid(compact) == PAGE_ID, "compact uuid normalization failed")
    require(extract_id(f"https://www.notion.so/Foo-{compact}?pvs=4") == PAGE_ID, "notion URL id extraction failed")
    long_text = "x" * 4500
    block = blocks_from_text(long_text)[0]
    require(rich_text_plain(block["paragraph"]["rich_text"]) == long_text, "long text must be chunked, not truncated")


def test_doctor_snapshot_and_read() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        env, _ = env_for(tmp)
        doctor = run_tool("doctor", "--json", env=env)
        require(doctor.returncode == 0, doctor.stderr)
        payload = parse_json(doctor)
        require(payload["ok"] is True, payload)
        require(payload["api_version"] == "2025-09-03", payload)
        require(payload["credentials"]["NOTION_TOKEN"]["source"] == "mock", payload)

        snapshot = run_tool("snapshot", "--json", env=env)
        require(snapshot.returncode == 0, snapshot.stderr)
        snap = parse_json(snapshot)
        require(snap["ok"] is True and snap["recent"], snap)

        read = run_tool("read", PAGE_ID, "--json", env=env)
        require(read.returncode == 0, read.stderr)
        body = parse_json(read)
        require("Use Notion for shared execution" in body["text"], body)


def test_data_sources_save_verify_and_comments() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        env, record = env_for(tmp)

        listed = run_tool("data-sources", "list", "--json", env=env)
        require(listed.returncode == 0, listed.stderr)
        require(parse_json(listed)["items"][0]["title"] == "Team Tasks", listed.stdout)

        schema = run_tool("data-sources", "schema", DATA_SOURCE_ID, "--json", env=env)
        require(schema.returncode == 0, schema.stderr)
        require(parse_json(schema)["data_source"]["id"] == DATA_SOURCE_ID, schema.stdout)

        saved = run_tool("decision", "record", "--title", "Use Notion", "--content", "Decision body", "--data-source", DATA_SOURCE_ID, "--json", env=env)
        require(saved.returncode == 0, saved.stderr)
        save_payload = parse_json(saved)
        require(save_payload["verified"]["ok"] is True, save_payload)
        page_req = next(req for req in record.read_text(encoding="utf-8").splitlines() if '"endpoint": "/pages"' in req)
        page_body = json.loads(page_req)["body"]
        require("Project" in page_body["properties"], page_body)
        require("Name" not in page_body["properties"], page_body)

        commented = run_tool("comment", "add", PAGE_ID, "--text", "Please review", "--mention-user", USER_ID, "--json", env=env)
        require(commented.returncode == 0, commented.stderr)
        require(parse_json(commented)["comment"]["id"] == COMMENT_ID, commented.stdout)

        requests = [json.loads(line) for line in record.read_text(encoding="utf-8").splitlines()]
        require(any(req["method"] == "POST" and req["endpoint"] == "/comments" for req in requests), "comment call was not recorded")
        comment_req = next(req for req in requests if req["method"] == "POST" and req["endpoint"] == "/comments")
        require(comment_req["body"]["rich_text"][0]["type"] == "mention", f"mention object missing: {comment_req}")


def test_sync_cache_bootstrap_and_webhooks() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        env, _ = env_for(tmp)

        synced = run_tool("sync", "--limit", "5", "--json", env=env)
        require(synced.returncode == 0, synced.stderr)
        sync_payload = parse_json(synced)
        require(sync_payload["pages"] >= 1 and sync_payload["blocks"] >= 1, sync_payload)

        cache = run_tool("cache", "search", "shared", "--json", env=env)
        require(cache.returncode == 0, cache.stderr)
        found = parse_json(cache)
        require(found["items"], found)

        boot = run_tool("bootstrap-team", "--json", env=env)
        require(boot.returncode == 0, boot.stderr)
        boot_payload = parse_json(boot)
        require("task" in boot_payload["roles"], boot_payload)

        schema = run_tool("schema", "show", "--json", env=env)
        require(schema.returncode == 0, schema.stderr)
        require(parse_json(schema)["roles"]["task"]["data_source_id"] == DATA_SOURCE_ID, schema.stdout)

        event_body = b'{"type":"page.updated","entity":{"id":"11111111-1111-1111-1111-111111111111"}}'
        event_path = tmp / "event.json"
        event_path.write_bytes(event_body)
        signature = hmac.new(b"webhook-secret", event_body, hashlib.sha256).hexdigest()
        ingest = run_tool("webhooks", "ingest", "--body-file", str(event_path), "--signature", f"sha256={signature}", "--json", env=env)
        require(ingest.returncode == 0, ingest.stderr)
        require(Path(parse_json(ingest)["stored"]).exists(), ingest.stdout)


def test_missing_token_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(Path(tmp_str) / "home")
        env["AGENT_DO_CREDS_SERVICE"] = f"agent-do-test-notion-empty-{Path(tmp_str).name}"
        env.pop("NOTION_TOKEN", None)
        proc = run_tool("doctor", "--json", env=env)
        require(proc.returncode == 1, proc.stdout)
        payload = parse_json(proc)
        require(payload["ok"] is False, payload)
        require("NOTION_TOKEN" in payload["recommendation"], payload)


def main() -> int:
    tests = [
        test_static_surface,
        test_id_normalization,
        test_doctor_snapshot_and_read,
        test_data_sources_save_verify_and_comments,
        test_sync_cache_bootstrap_and_webhooks,
        test_missing_token_contract,
    ]
    for test in tests:
        test()
    print("notion tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
