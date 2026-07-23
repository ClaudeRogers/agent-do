#!/usr/bin/env python3
"""Notion team operating layer for agent-do.

The shell entrypoint owns help text. This module owns the contract-real Notion
surface: modern data-source APIs, credential-aware doctor/snapshot, recursive
reads, verified writes, local cache, team schema mapping, webhook ingestion, and
optional semantic indexing over the cache.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import hmac
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable


NOTION_VERSION = "2025-09-03"
NEEDS_CLARIFICATION = 2
PAGE_SIZE = 100
UUID_RE = re.compile(r"(?i)\b([0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b")
URL_ID_RE = re.compile(r"(?i)([0-9a-f]{32})(?:[?#]|$)")


class NotionError(Exception):
    def __init__(self, message: str, code: int = 1, **payload: Any) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.payload = payload


class Runtime:
    def __init__(self, json_mode: bool = False) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        home = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))
        workspace = os.environ.get("AGENT_NOTION_WORKSPACE_ID", "default")
        self.repo_root = repo_root
        self.tool_dir = Path(__file__).resolve().parent
        self.json_mode = json_mode
        self.workspace_id = safe_slug(workspace)
        self.root = home / "notion" / "workspaces" / self.workspace_id
        self.cache_db = self.root / "index.db"
        self.schema_path = self.root / "schema.yaml"
        self.webhook_dir = self.root / "webhooks"
        self.request_script = self.tool_dir / "request.sh"
        self.mock_file = os.environ.get("AGENT_NOTION_MOCK_FILE")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return cleaned or "default"


def emit(payload: Any, json_mode: bool = True) -> None:
    if json_mode:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print_human(payload)


def print_human(payload: Any) -> None:
    if isinstance(payload, dict):
        if "items" in payload and isinstance(payload["items"], list):
            for item in payload["items"]:
                if isinstance(item, dict):
                    label = item.get("title") or item.get("name") or item.get("id") or item
                    suffix = f" ({item.get('id')})" if item.get("id") else ""
                    print(f"{label}{suffix}")
                else:
                    print(item)
            return
        if "text" in payload:
            print(payload["text"])
            return
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def normalize_uuid(value: str) -> str:
    compact = value.replace("-", "").lower()
    if not re.fullmatch(r"[0-9a-f]{32}", compact):
        raise ValueError(value)
    return f"{compact[0:8]}-{compact[8:12]}-{compact[12:16]}-{compact[16:20]}-{compact[20:32]}"


def extract_id(value: str) -> str | None:
    value = value.strip()
    direct = UUID_RE.search(value)
    if direct:
        return normalize_uuid(direct.group(1))
    url_id = URL_ID_RE.search(value)
    if url_id:
        return normalize_uuid(url_id.group(1))
    return None


def rich_text_plain(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    return "".join(str(item.get("plain_text") or item.get("text", {}).get("content") or "") for item in items)


def title_from_object(obj: dict[str, Any]) -> str:
    for key in ("title", "name"):
        value = obj.get(key)
        if isinstance(value, list):
            text = rich_text_plain(value)
            if text:
                return text
        if isinstance(value, str) and value:
            return value
    props = obj.get("properties") or {}
    for prop in props.values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            text = rich_text_plain(prop.get("title"))
            if text:
                return text
    return "Untitled"


def text_from_block(block: dict[str, Any]) -> str:
    btype = block.get("type", "")
    content = block.get(btype) if isinstance(block.get(btype), dict) else {}
    parts: list[str] = []
    if isinstance(content, dict):
        if btype in {"child_page", "child_database"} and content.get("title"):
            parts.append(str(content.get("title") or ""))
        parts.append(rich_text_plain(content.get("rich_text")))
        if content.get("caption"):
            parts.append(rich_text_plain(content.get("caption")))
    return " ".join(part for part in parts if part).strip()


def blocks_from_text(content: str) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", content.strip()) if part.strip()]
    for paragraph in paragraphs:
        if paragraph.startswith("# "):
            children.append(text_block("heading_1", paragraph[2:].strip()))
        elif paragraph.startswith("## "):
            children.append(text_block("heading_2", paragraph[3:].strip()))
        elif paragraph.startswith("- [ ] "):
            children.append(to_do_block(paragraph[6:].strip(), checked=False))
        elif paragraph.startswith("- [x] ") or paragraph.startswith("- [X] "):
            children.append(to_do_block(paragraph[6:].strip(), checked=True))
        elif paragraph.startswith("- "):
            for line in paragraph.splitlines():
                text = line[2:].strip() if line.startswith("- ") else line.strip()
                if text:
                    children.append(text_block("bulleted_list_item", text))
        else:
            children.append(text_block("paragraph", paragraph))
    return children or [text_block("paragraph", content.strip())]


def rich_text_chunks(text: str, limit: int = 1900) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    remaining = text or ""
    while remaining:
        chunk = remaining[:limit]
        chunks.append({"type": "text", "text": {"content": chunk}})
        remaining = remaining[limit:]
    return chunks or [{"type": "text", "text": {"content": ""}}]


def text_block(kind: str, text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": kind,
        kind: {"rich_text": rich_text_chunks(text)},
    }


def to_do_block(text: str, checked: bool = False) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "to_do",
        "to_do": {
            "rich_text": rich_text_chunks(text),
            "checked": checked,
        },
    }


def credential_source(rt: Runtime, key: str) -> str | None:
    if os.environ.get(key):
        return "env"
    script = f"source {sh_quote(str(rt.repo_root / 'lib' / 'creds-helper.sh'))}; creds_get_source {sh_quote(key)}"
    proc = subprocess.run(["bash", "-lc", script], cwd=rt.repo_root, text=True, capture_output=True, check=False)
    if proc.returncode == 0:
        return proc.stdout.strip() or "store"
    return None


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


class NotionClient:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self._mock_cache: dict[str, Any] | None = None

    def request(self, method: str, endpoint: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        method = method.upper()
        if self.rt.mock_file:
            return self._mock_request(method, endpoint, body)

        body_path = ""
        with contextlib.ExitStack() as stack:
            if body is not None:
                tmp = stack.enter_context(tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False))
                body_path = tmp.name
                json.dump(body, tmp)
                tmp.close()
                stack.callback(lambda: Path(body_path).unlink(missing_ok=True))
            proc = subprocess.run(
                ["bash", str(self.rt.request_script), method, endpoint, body_path],
                cwd=self.rt.repo_root,
                text=True,
                capture_output=True,
                check=False,
            )
        raw = proc.stdout.strip()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise NotionError("notion api returned non-json response", stdout=raw[:1000], stderr=proc.stderr, code=1) from exc
        if proc.returncode != 0 or payload.get("object") == "error":
            raise NotionError(
                payload.get("message") or "notion api request failed",
                code=1 if proc.returncode != NEEDS_CLARIFICATION else NEEDS_CLARIFICATION,
                status=payload.get("status"),
                notion_code=payload.get("code"),
                endpoint=endpoint,
            )
        return payload

    def _mock_request(self, method: str, endpoint: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._mock_cache is None:
            self._mock_cache = json.loads(Path(self.rt.mock_file or "").read_text(encoding="utf-8"))
        key = f"{method} {endpoint}"
        short_key = f"{method} {endpoint.split('?', 1)[0]}"
        value = self._mock_cache.get(key, self._mock_cache.get(short_key))
        if value is None:
            raise NotionError("mock response missing", endpoint=endpoint, method=method, body=body or {})
        record = os.environ.get("AGENT_NOTION_MOCK_RECORD")
        if record:
            with Path(record).open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"method": method, "endpoint": endpoint, "body": body or {}}) + "\n")
        if isinstance(value, dict) and value.get("object") == "error":
            raise NotionError(value.get("message", "mock error"), notion_code=value.get("code"), endpoint=endpoint)
        return value

    def paginate(self, method: str, endpoint: str, body: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page_body = dict(body or {})
            page_endpoint = endpoint
            if method.upper() == "GET":
                params = {"page_size": str(PAGE_SIZE)}
                if cursor:
                    params["start_cursor"] = cursor
                sep = "&" if "?" in page_endpoint else "?"
                page_endpoint = page_endpoint + sep + urllib.parse.urlencode(params)
                response = self.request(method, page_endpoint)
            else:
                page_body.setdefault("page_size", PAGE_SIZE)
                if cursor:
                    page_body["start_cursor"] = cursor
                response = self.request(method, endpoint, page_body)
            results.extend(response.get("results") or [])
            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")
            if not cursor:
                break
        return results


def ensure_storage(rt: Runtime) -> None:
    rt.root.mkdir(parents=True, exist_ok=True)
    rt.webhook_dir.mkdir(parents=True, exist_ok=True)
    with db_connect(rt) as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS pages (
              id TEXT PRIMARY KEY,
              title TEXT,
              url TEXT,
              created_time TEXT,
              last_edited_time TEXT,
              parent_type TEXT,
              parent_id TEXT,
              archived INTEGER DEFAULT 0,
              raw_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS blocks (
              id TEXT PRIMARY KEY,
              page_id TEXT,
              parent_id TEXT,
              type TEXT,
              text TEXT,
              has_children INTEGER DEFAULT 0,
              raw_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
              id TEXT PRIMARY KEY,
              name TEXT,
              type TEXT,
              raw_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS data_sources (
              id TEXT PRIMARY KEY,
              title TEXT,
              url TEXT,
              parent_id TEXT,
              raw_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS comments (
              id TEXT PRIMARY KEY,
              parent_id TEXT,
              discussion_id TEXT,
              text TEXT,
              created_time TEXT,
              raw_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS embeddings (
              item_id TEXT,
              item_kind TEXT,
              provider TEXT,
              model TEXT,
              text_hash TEXT,
              vector_json TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY (item_id, provider, model)
            );
            CREATE TABLE IF NOT EXISTS sync_state (
              key TEXT PRIMARY KEY,
              value TEXT,
              updated_at TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS notion_fts USING fts5(
              kind, item_id UNINDEXED, title, text, url UNINDEXED, last_edited_time UNINDEXED
            );
            """
        )


def db_connect(rt: Runtime) -> sqlite3.Connection:
    conn = sqlite3.connect(rt.cache_db, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def cache_counts(rt: Runtime) -> dict[str, int | None]:
    if not rt.cache_db.exists():
        return {key: 0 for key in ("pages", "blocks", "users", "data_sources", "comments", "embeddings")}
    with db_connect(rt) as conn:
        out: dict[str, int | None] = {}
        for table in ("pages", "blocks", "users", "data_sources", "comments", "embeddings"):
            out[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return out


def cache_last_sync(rt: Runtime) -> str | None:
    if not rt.cache_db.exists():
        return None
    with db_connect(rt) as conn:
        row = conn.execute("SELECT value FROM sync_state WHERE key='last_sync'").fetchone()
        return row[0] if row else None


def load_schema(rt: Runtime) -> dict[str, Any]:
    if not rt.schema_path.exists():
        return {"roles": {}}
    text = rt.schema_path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # The writer uses JSON-compatible YAML. Return empty on hand-edited parse
        # failures so commands fail with clarification instead of crashing.
        return {"roles": {}}


def save_schema(rt: Runtime, schema: dict[str, Any]) -> None:
    rt.root.mkdir(parents=True, exist_ok=True)
    rt.schema_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def credential_contract(rt: Runtime) -> dict[str, Any]:
    return {
        "NOTION_TOKEN": {
            "present": credential_source(rt, "NOTION_TOKEN") is not None or bool(rt.mock_file),
            "source": "mock" if rt.mock_file else credential_source(rt, "NOTION_TOKEN"),
            "roles": ["notion_api"],
            "required": True,
        },
        "VOYAGE_API_KEY": {
            "present": credential_source(rt, "VOYAGE_API_KEY") is not None,
            "source": credential_source(rt, "VOYAGE_API_KEY"),
            "roles": ["semantic_cache"],
            "required": False,
        },
        "OPENAI_API_KEY": {
            "present": credential_source(rt, "OPENAI_API_KEY") is not None,
            "source": credential_source(rt, "OPENAI_API_KEY"),
            "roles": ["semantic_cache_fallback"],
            "required": False,
        },
    }


def cmd_doctor(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_storage(rt)
    client = NotionClient(rt)
    creds = credential_contract(rt)
    payload: dict[str, Any] = {
        "ok": False,
        "tool": "notion",
        "api_version": NOTION_VERSION,
        "credentials": creds,
        "cache": {"path": str(rt.cache_db), "last_sync": cache_last_sync(rt), **cache_counts(rt)},
        "schema": {"path": str(rt.schema_path), "exists": rt.schema_path.exists()},
        "features": {
            "read": {"ready": creds["NOTION_TOKEN"]["present"], "requires": ["NOTION_TOKEN"]},
            "write": {"ready": creds["NOTION_TOKEN"]["present"], "requires": ["NOTION_TOKEN", "shared pages/data sources"]},
            "cache": {"ready": rt.cache_db.exists(), "requires": ["sync"]},
            "webhooks": {"ready": webhook_store_ready(rt) and bool(os.environ.get("NOTION_WEBHOOK_VERIFICATION_TOKEN")), "requires": ["public HTTPS receiver", "Notion subscription"]},
            "semantic": {
                "ready": bool(creds["VOYAGE_API_KEY"]["present"] or creds["OPENAI_API_KEY"]["present"]),
                "requires_any": ["VOYAGE_API_KEY", "OPENAI_API_KEY"],
            },
        },
    }
    if not creds["NOTION_TOKEN"]["present"]:
        payload["recommendation"] = "run: agent-do creds store NOTION_TOKEN --stdin, then share pages/data sources with the integration"
        emit(payload, rt.json_mode)
        return 1
    try:
        me = client.request("GET", "/users/me")
        payload["bot"] = simplify_user(me)
        payload["ok"] = True
    except NotionError as exc:
        payload["error"] = error_payload(exc)
        payload["recommendation"] = "verify NOTION_TOKEN and that the integration has workspace access"
        emit(payload, rt.json_mode)
        return exc.code
    emit(payload, rt.json_mode)
    return 0


def simplify_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user.get("id"),
        "name": user.get("name"),
        "type": user.get("type"),
        "bot": user.get("bot") if user.get("type") == "bot" else None,
    }


def error_payload(exc: NotionError) -> dict[str, Any]:
    payload = {"message": exc.message, **exc.payload}
    return {k: v for k, v in payload.items() if v is not None}


def cmd_auth_status(rt: Runtime, args: argparse.Namespace) -> int:
    return cmd_doctor(rt, args)


def cmd_snapshot(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_storage(rt)
    client = NotionClient(rt)
    payload: dict[str, Any] = {
        "tool": "notion",
        "ok": False,
        "api_version": NOTION_VERSION,
        "workspace_id": rt.workspace_id,
        "cache": {"path": str(rt.cache_db), "last_sync": cache_last_sync(rt), **cache_counts(rt)},
        "schema": load_schema(rt),
    }
    if not credential_contract(rt)["NOTION_TOKEN"]["present"]:
        payload["recommendation"] = "set NOTION_TOKEN and share target pages/data sources with the integration"
        emit(payload, True)
        return 1
    try:
        payload["bot"] = simplify_user(client.request("GET", "/users/me"))
        payload["recent"] = simplify_search_results(client.request("POST", "/search", {"page_size": 10}).get("results") or [])
        payload["ok"] = True
    except NotionError as exc:
        payload["error"] = error_payload(exc)
        emit(payload, True)
        return exc.code
    emit(payload, True)
    return 0


def simplify_search_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [simplify_object(item) for item in results]


def simplify_object(item: dict[str, Any]) -> dict[str, Any]:
    obj = item.get("object")
    return {
        "object": obj,
        "id": item.get("id"),
        "title": title_from_object(item),
        "url": item.get("url"),
        "last_edited_time": item.get("last_edited_time"),
    }


def cmd_workspace(rt: Runtime, args: argparse.Namespace) -> int:
    client = NotionClient(rt)
    payload = {
        "bot": simplify_user(client.request("GET", "/users/me")),
        "users": cmd_users_payload(client),
        "data_sources": list_data_sources(client),
        "schema": load_schema(rt),
    }
    emit(payload, rt.json_mode)
    return 0


def cmd_users_payload(client: NotionClient) -> list[dict[str, Any]]:
    return [simplify_user(user) for user in client.paginate("GET", "/users")]


def cmd_users(rt: Runtime, args: argparse.Namespace) -> int:
    emit({"items": cmd_users_payload(NotionClient(rt))}, rt.json_mode)
    return 0


def cmd_search(rt: Runtime, args: argparse.Namespace) -> int:
    query = " ".join(args.query).strip()
    if not query:
        raise NotionError("search query required", code=NEEDS_CLARIFICATION)
    body: dict[str, Any] = {"query": query, "page_size": args.limit}
    results = NotionClient(rt).request("POST", "/search", body).get("results") or []
    emit({"query": query, "items": simplify_search_results(results)}, rt.json_mode)
    return 0


def resolve_object(client: NotionClient, value: str, expected: str | None = None) -> dict[str, Any]:
    found_id = extract_id(value)
    if found_id:
        if expected == "data_source":
            obj = client.request("GET", f"/data_sources/{found_id}")
        elif expected == "database":
            obj = client.request("GET", f"/databases/{found_id}")
        else:
            obj = client.request("GET", f"/pages/{found_id}")
        return obj
    results = client.request("POST", "/search", {"query": value, "page_size": 10}).get("results") or []
    if expected:
        results = [item for item in results if item.get("object") == expected or (expected == "data_source" and item.get("object") == "database")]
    if not results:
        raise NotionError("notion object not found", code=1, query=value, expected=expected)
    if len(results) > 1:
        raise NotionError("ambiguous notion object", code=NEEDS_CLARIFICATION, query=value, matches=simplify_search_results(results))
    return results[0]


def read_blocks_recursive(client: NotionClient, block_id: str, page_id: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    children = client.paginate("GET", f"/blocks/{block_id}/children")
    for child in children:
        item = dict(child)
        item["_plain_text"] = text_from_block(item)
        item["_page_id"] = page_id or block_id
        out.append(item)
        # Child pages/databases are separate Notion objects and are already
        # discoverable through search. Recursing through them from a parent page
        # can explode a sync into hundreds of page walks for workspace hubs.
        if item.get("has_children") and item.get("type") not in {"child_page", "child_database"}:
            out.extend(read_blocks_recursive(client, item["id"], page_id=page_id or block_id))
    return out


def cmd_blocks(rt: Runtime, args: argparse.Namespace) -> int:
    client = NotionClient(rt)
    page = resolve_object(client, args.page, expected=None)
    page_id = page.get("id") or extract_id(args.page)
    if not page_id:
        raise NotionError("page id required", code=NEEDS_CLARIFICATION)
    blocks = read_blocks_recursive(client, page_id, page_id=page_id)
    emit({"page": simplify_object(page), "blocks": [simplify_block(b) for b in blocks]}, rt.json_mode)
    return 0


def simplify_block(block: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": block.get("id"),
        "type": block.get("type"),
        "text": block.get("_plain_text") or text_from_block(block),
        "has_children": bool(block.get("has_children")),
    }


def cmd_read(rt: Runtime, args: argparse.Namespace) -> int:
    client = NotionClient(rt)
    page = resolve_object(client, args.page)
    page_id = page.get("id")
    blocks = read_blocks_recursive(client, page_id, page_id=page_id)
    text = "\n".join(filter(None, [text_from_block(block) for block in blocks]))
    payload = {
        "page": simplify_object(page),
        "text": text,
        "blocks": [simplify_block(block) for block in blocks],
    }
    emit(payload, rt.json_mode)
    return 0


def list_data_sources(client: NotionClient) -> list[dict[str, Any]]:
    response = client.request(
        "POST",
        "/search",
        {"filter": {"property": "object", "value": "data_source"}, "page_size": PAGE_SIZE},
    )
    results = [item for item in (response.get("results") or []) if item.get("object") == "data_source"]
    if not results:
        response = client.request(
            "POST",
            "/search",
            {"filter": {"property": "object", "value": "database"}, "page_size": PAGE_SIZE},
        )
        results = [item for item in (response.get("results") or []) if item.get("object") == "database"]
    return [simplify_object(item) for item in results]


def cmd_data_sources(rt: Runtime, args: argparse.Namespace) -> int:
    client = NotionClient(rt)
    if args.ds_command == "list":
        emit({"items": list_data_sources(client)}, rt.json_mode)
        return 0
    target = resolve_object(client, args.target, expected="data_source")
    ds_id = target["id"]
    if target.get("object") != "data_source":
        # Compatibility for older workspaces/search results.
        ds_ids = target.get("data_sources") or target.get("data_source_ids") or []
        if ds_ids:
            ds_id = ds_ids[0].get("id") if isinstance(ds_ids[0], dict) else ds_ids[0]
    if args.ds_command == "schema":
        schema = client.request("GET", f"/data_sources/{ds_id}")
        emit({"data_source": simplify_object(schema), "properties": schema.get("properties") or {}}, rt.json_mode)
        return 0
    if args.ds_command == "query":
        body: dict[str, Any] = {"page_size": args.limit}
        response = client.request("POST", f"/data_sources/{ds_id}/query", body)
        emit({"data_source": simplify_object(target), "items": simplify_search_results(response.get("results") or [])}, rt.json_mode)
        return 0
    raise NotionError("unknown data-sources command", code=NEEDS_CLARIFICATION)


def title_property_name(data_source: dict[str, Any] | None) -> str:
    props = (data_source or {}).get("properties") or {}
    for name, prop in props.items():
        if isinstance(prop, dict) and prop.get("type") == "title":
            return name
    return "Name"


def target_for_role(rt: Runtime, role: str | None = None) -> dict[str, str | None]:
    role = role or "note"
    schema = load_schema(rt)
    roles = schema.get("roles") or {}
    mapped = roles.get(role) or {}
    return {
        "data_source_id": mapped.get("data_source_id") or os.environ.get("NOTION_DATA_SOURCE_ID"),
        "parent_page_id": mapped.get("parent_page_id") or os.environ.get("NOTION_PARENT_PAGE_ID"),
        "title_property": mapped.get("title_property") or "Name",
    }


def create_page(
    client: NotionClient,
    *,
    title: str,
    content: str,
    data_source_id: str | None = None,
    parent_page_id: str | None = None,
    title_property: str = "Name",
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not data_source_id and not parent_page_id:
        raise NotionError(
            "save target required",
            code=NEEDS_CLARIFICATION,
            recommendation="pass --data-source, set NOTION_DATA_SOURCE_ID, pass --parent-page, or run bootstrap-team",
        )
    body: dict[str, Any] = {
        "children": blocks_from_text(content),
    }
    if data_source_id:
        body["parent"] = {"data_source_id": data_source_id}
        body["properties"] = {title_property: {"title": [{"text": {"content": title[:2000]}}]}}
    else:
        body["parent"] = {"page_id": parent_page_id}
        body["properties"] = {"title": [{"text": {"content": title[:2000]}}]}
    if metadata:
        meta_lines = "\n".join(f"{key}: {value}" for key, value in metadata.items() if value)
        if meta_lines:
            body["children"].insert(0, text_block("paragraph", meta_lines))
    return client.request("POST", "/pages", body)


def cmd_save(rt: Runtime, args: argparse.Namespace) -> int:
    title = args.title or infer_title(args.content)
    content = args.content or ""
    client = NotionClient(rt)
    role = args.type or "note"
    target = target_for_role(rt, role)
    data_source_id = resolve_target_data_source(client, args.data_source) if args.data_source else target["data_source_id"]
    parent_page_id = extract_id(args.parent_page) if args.parent_page else target["parent_page_id"]
    title_property = target["title_property"] or "Name"
    if data_source_id:
        title_property = title_property_name(client.request("GET", f"/data_sources/{data_source_id}"))
    page = create_page(
        client,
        title=title,
        content=content,
        data_source_id=data_source_id,
        parent_page_id=parent_page_id,
        title_property=title_property,
        metadata={"type": role, "scope": args.scope},
    )
    verified = verify_page(client, page["id"])
    emit({"created": simplify_object(page), "verified": verified}, rt.json_mode)
    return 0


def infer_title(content: str) -> str:
    for line in content.splitlines():
        clean = line.strip().lstrip("#").strip()
        if clean:
            return clean[:80]
    return f"Notion note {now_iso()}"


def resolve_target_data_source(client: NotionClient, value: str) -> str:
    found = extract_id(value)
    if found:
        return found
    obj = resolve_object(client, value, expected="data_source")
    return obj["id"]


def verify_page(client: NotionClient, page_id: str) -> dict[str, Any]:
    page = client.request("GET", f"/pages/{page_id}")
    return {"ok": bool(page.get("id")), "page": simplify_object(page)}


def cmd_verify(rt: Runtime, args: argparse.Namespace) -> int:
    client = NotionClient(rt)
    page = resolve_object(client, args.page)
    emit(verify_page(client, page["id"]), rt.json_mode)
    return 0


def cmd_save_group(rt: Runtime, args: argparse.Namespace) -> int:
    client = NotionClient(rt)
    target = target_for_role(rt, args.type or "handoff")
    data_source_id = resolve_target_data_source(client, args.data_source) if args.data_source else target["data_source_id"]
    parent_page_id = extract_id(args.parent_page) if args.parent_page else target["parent_page_id"]
    title_property = target["title_property"] or "Name"
    if data_source_id:
        title_property = title_property_name(client.request("GET", f"/data_sources/{data_source_id}"))
    hub = create_page(
        client,
        title=args.title,
        content=args.content or f"# {args.title}",
        data_source_id=data_source_id,
        parent_page_id=parent_page_id,
        title_property=title_property,
        metadata={"type": args.type or "handoff", "scope": args.scope},
    )
    children: list[dict[str, Any]] = []
    for child in args.child or []:
        if ":" not in child:
            raise NotionError("--child must be name:body", code=NEEDS_CLARIFICATION, child=child)
        name, body = child.split(":", 1)
        child_page = create_page(client, title=name.strip(), content=body.strip(), parent_page_id=hub["id"])
        children.append(simplify_object(child_page))
    emit({"hub": simplify_object(hub), "children": children, "verified": verify_page(client, hub["id"])}, rt.json_mode)
    return 0


def cmd_task(rt: Runtime, args: argparse.Namespace) -> int:
    if args.task_command != "add":
        raise NotionError("unknown task command", code=NEEDS_CLARIFICATION)
    content = args.content or ""
    details = []
    if args.owner:
        details.append(f"owner: {args.owner}")
    if args.due:
        details.append(f"due: {args.due}")
    if args.status:
        details.append(f"status: {args.status}")
    if details:
        content = "\n".join(details + ["", content]).strip()
    args.type = "task"
    args.content = content or args.title
    return cmd_save(rt, args)


def cmd_decision(rt: Runtime, args: argparse.Namespace) -> int:
    if args.decision_command != "record":
        raise NotionError("unknown decision command", code=NEEDS_CLARIFICATION)
    args.type = "decision"
    return cmd_save(rt, args)


def cmd_handoff(rt: Runtime, args: argparse.Namespace) -> int:
    if args.handoff_command != "create":
        raise NotionError("unknown handoff command", code=NEEDS_CLARIFICATION)
    args.type = "handoff"
    return cmd_save(rt, args)


def cmd_comment(rt: Runtime, args: argparse.Namespace) -> int:
    if args.comment_command != "add":
        raise NotionError("unknown comment command", code=NEEDS_CLARIFICATION)
    client = NotionClient(rt)
    target = resolve_object(client, args.page)
    rich_text: list[dict[str, Any]] = []
    if args.mention_user:
        rich_text.append({"type": "mention", "mention": {"type": "user", "user": {"id": args.mention_user}}})
        rich_text.append({"type": "text", "text": {"content": " "}})
    rich_text.append({"type": "text", "text": {"content": args.text}})
    body = {"parent": {"page_id": target["id"]}, "rich_text": rich_text}
    comment = client.request("POST", "/comments", body)
    emit({"comment": simplify_comment(comment), "verified_parent": simplify_object(target)}, rt.json_mode)
    return 0


def simplify_comment(comment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": comment.get("id"),
        "discussion_id": comment.get("discussion_id"),
        "created_time": comment.get("created_time"),
        "text": rich_text_plain(comment.get("rich_text")),
    }


def cmd_sync(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_storage(rt)
    client = NotionClient(rt)
    users = cmd_users_payload(client)
    data_sources = list_data_sources(client)
    pages = [
        item
        for item in (client.request("POST", "/search", {"filter": {"property": "object", "value": "page"}, "page_size": args.limit}).get("results") or [])
        if item.get("object") == "page"
    ]
    synced_blocks = 0
    with db_connect(rt) as conn:
        for user in users:
            conn.execute(
                "INSERT OR REPLACE INTO users(id,name,type,raw_json) VALUES(?,?,?,?)",
                (user.get("id"), user.get("name"), user.get("type"), json.dumps(user)),
            )
        for ds in data_sources:
            conn.execute(
                "INSERT OR REPLACE INTO data_sources(id,title,url,parent_id,raw_json) VALUES(?,?,?,?,?)",
                (ds.get("id"), ds.get("title"), ds.get("url"), None, json.dumps(ds)),
            )
        for page in pages[: args.limit]:
            page_id = page["id"]
            title = title_from_object(page)
            parent = page.get("parent") or {}
            conn.execute(
                """
                INSERT OR REPLACE INTO pages(id,title,url,created_time,last_edited_time,parent_type,parent_id,archived,raw_json)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    page_id,
                    title,
                    page.get("url"),
                    page.get("created_time"),
                    page.get("last_edited_time"),
                    parent.get("type"),
                    parent.get(parent.get("type", ""), None) if isinstance(parent, dict) else None,
                    1 if page.get("archived") else 0,
                    json.dumps(page),
                ),
            )
            blocks = read_blocks_recursive(client, page_id, page_id=page_id)
            synced_blocks += len(blocks)
            for block in blocks:
                text = text_from_block(block)
                parent_obj = block.get("parent") or {}
                conn.execute(
                    "INSERT OR REPLACE INTO blocks(id,page_id,parent_id,type,text,has_children,raw_json) VALUES(?,?,?,?,?,?,?)",
                    (
                        block.get("id"),
                        page_id,
                        parent_obj.get(parent_obj.get("type", ""), None) if isinstance(parent_obj, dict) else None,
                        block.get("type"),
                        text,
                        1 if block.get("has_children") else 0,
                        json.dumps(block),
                    ),
                )
        rebuild_fts(conn)
        conn.execute("INSERT OR REPLACE INTO sync_state(key,value,updated_at) VALUES('last_sync',?,?)", (now_iso(), now_iso()))
    emit({"ok": True, "pages": len(pages[: args.limit]), "blocks": synced_blocks, "users": len(users), "data_sources": len(data_sources)}, rt.json_mode)
    return 0


def rebuild_fts(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM notion_fts")
    conn.execute(
        "INSERT INTO notion_fts(kind,item_id,title,text,url,last_edited_time) SELECT 'page',id,title,title,url,last_edited_time FROM pages"
    )
    conn.execute(
        """
        INSERT INTO notion_fts(kind,item_id,title,text,url,last_edited_time)
        SELECT 'block', blocks.id, pages.title, blocks.text, pages.url, pages.last_edited_time
        FROM blocks LEFT JOIN pages ON pages.id=blocks.page_id
        WHERE blocks.text IS NOT NULL AND blocks.text != ''
        """
    )
    conn.execute(
        "INSERT INTO notion_fts(kind,item_id,title,text,url,last_edited_time) SELECT 'data_source',id,title,title,url,NULL FROM data_sources"
    )


def cmd_cache(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_storage(rt)
    if args.cache_command == "status":
        emit({"path": str(rt.cache_db), "last_sync": cache_last_sync(rt), **cache_counts(rt)}, rt.json_mode)
        return 0
    if args.cache_command == "search":
        query = " ".join(args.query).strip()
        if not query:
            raise NotionError("cache search query required", code=NEEDS_CLARIFICATION)
        mode = args.mode
        if mode in ("semantic", "hybrid"):
            semantic = semantic_search(rt, query, args.limit)
            if mode == "semantic":
                emit({"query": query, "mode": mode, "items": semantic}, rt.json_mode)
                return 0
        else:
            semantic = []
        with db_connect(rt) as conn:
            rows = conn.execute(
                """
                SELECT kind,item_id,title,text,url,last_edited_time,
                       snippet(notion_fts, 3, '[', ']', '...', 24) AS snippet
                FROM notion_fts
                WHERE notion_fts MATCH ?
                LIMIT ?
                """,
                (query, args.limit),
            ).fetchall()
        keyword = [
            {
                "kind": row[0],
                "id": row[1],
                "title": row[2],
                "text": row[3],
                "url": row[4],
                "last_edited_time": row[5],
                "snippet": row[6],
            }
            for row in rows
        ]
        items = merge_hybrid(keyword, semantic, args.limit) if mode == "hybrid" else keyword
        emit({"query": query, "mode": mode, "items": items}, rt.json_mode)
        return 0
    raise NotionError("unknown cache command", code=NEEDS_CLARIFICATION)


def cmd_bootstrap_team(rt: Runtime, args: argparse.Namespace) -> int:
    client = NotionClient(rt)
    sources = list_data_sources(client)
    roles = adopt_roles(sources)
    missing = [role for role in ROLE_KEYWORDS if role not in roles]
    schema = {
        "version": 1,
        "workspace_id": rt.workspace_id,
        "updated_at": now_iso(),
        "roles": roles,
        "missing_roles": missing,
        "policy": {
            "creation": "inspect-and-adopt first; creating data sources requires explicit human confirmation",
            "source": "agent-do notion bootstrap-team",
        },
    }
    if args.create_missing and missing:
        raise NotionError(
            "creating missing Notion data sources is intentionally blocked until a live workspace shape is confirmed",
            code=NEEDS_CLARIFICATION,
            missing_roles=missing,
            recommendation="create or share the desired data sources, then rerun bootstrap-team",
        )
    save_schema(rt, schema)
    emit(schema, rt.json_mode)
    return 0


ROLE_KEYWORDS = {
    "tasks": ("task", "todo", "checklist"),
    "decisions": ("decision", "adr"),
    "handoffs": ("handoff", "handoffs"),
    "projects": ("project", "roadmap"),
    "meetings": ("meeting", "standup"),
    "specs": ("spec", "brief", "doc"),
    "sources": ("source", "reference", "research"),
    "people": ("people", "team", "users"),
}


def adopt_roles(data_sources: list[dict[str, Any]]) -> dict[str, Any]:
    roles: dict[str, Any] = {}
    for role, keywords in ROLE_KEYWORDS.items():
        for ds in data_sources:
            title = (ds.get("title") or "").lower()
            if any(keyword in title for keyword in keywords):
                roles[role[:-1] if role.endswith("s") else role] = {
                    "data_source_id": ds.get("id"),
                    "title": ds.get("title"),
                    "title_property": "Name",
                }
                break
    return roles


def cmd_schema(rt: Runtime, args: argparse.Namespace) -> int:
    if args.schema_command != "show":
        raise NotionError("unknown schema command", code=NEEDS_CLARIFICATION)
    emit(load_schema(rt), rt.json_mode)
    return 0


def webhook_store_ready(rt: Runtime) -> bool:
    return rt.webhook_dir.exists()


def cmd_webhooks(rt: Runtime, args: argparse.Namespace) -> int:
    rt.webhook_dir.mkdir(parents=True, exist_ok=True)
    if args.webhook_command == "doctor":
        token_present = bool(os.environ.get("NOTION_WEBHOOK_VERIFICATION_TOKEN"))
        payload = {
            "ok": token_present,
            "store": str(rt.webhook_dir / "events.jsonl"),
            "verification_token_present": token_present,
            "requires": ["public HTTPS receiver", "Notion-side webhook subscription", "signature validation"],
            "recommendation": "deploy a receiver, paste the Notion verification token into NOTION_WEBHOOK_VERIFICATION_TOKEN, then route events to webhooks ingest",
        }
        emit(payload, rt.json_mode)
        return 0 if token_present else 1
    if args.webhook_command == "ingest":
        body = Path(args.body_file).read_bytes()
        token = os.environ.get("NOTION_WEBHOOK_VERIFICATION_TOKEN", "")
        if token and args.signature:
            digest = hmac.new(token.encode(), body, hashlib.sha256).hexdigest()
            expected = args.signature.removeprefix("sha256=")
            if not hmac.compare_digest(digest, expected):
                raise NotionError("webhook signature mismatch", code=1)
        event = json.loads(body.decode("utf-8"))
        event_path = rt.webhook_dir / "events.jsonl"
        with event_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"received_at": now_iso(), "event": event}) + "\n")
        emit({"ok": True, "stored": str(event_path)}, rt.json_mode)
        return 0
    raise NotionError("unknown webhooks command", code=NEEDS_CLARIFICATION)


def cmd_embed(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_storage(rt)
    if args.embed_command == "status":
        counts = cache_counts(rt)
        provider = embedding_provider(rt)
        emit({"embeddings": counts.get("embeddings", 0), "provider": provider}, rt.json_mode)
        return 0
    if args.embed_command == "refresh":
        provider = embedding_provider(rt)
        if not provider:
            raise NotionError("VOYAGE_API_KEY or OPENAI_API_KEY required for semantic cache", code=NEEDS_CLARIFICATION)
        rows = embedding_candidates(rt, args.limit)
        updated = refresh_embeddings(rt, provider, rows)
        emit({"ok": True, "provider": provider["provider"], "model": provider["model"], "updated": updated}, rt.json_mode)
        return 0
    raise NotionError("unknown embed command", code=NEEDS_CLARIFICATION)


def embedding_provider(rt: Runtime) -> dict[str, Any] | None:
    if credential_source(rt, "VOYAGE_API_KEY"):
        return {"provider": "voyage", "model": "voyage-4-large", "key": "VOYAGE_API_KEY", "url": "https://api.voyageai.com/v1/embeddings"}
    if credential_source(rt, "OPENAI_API_KEY"):
        return {"provider": "openai", "model": "text-embedding-3-large", "key": "OPENAI_API_KEY", "url": "https://api.openai.com/v1/embeddings"}
    return None


def embedding_candidates(rt: Runtime, limit: int) -> list[tuple[str, str, str]]:
    with db_connect(rt) as conn:
        rows = conn.execute(
            """
            SELECT item_id, kind, COALESCE(title,'') || '\n' || COALESCE(text,'')
            FROM notion_fts
            WHERE COALESCE(text,'') != ''
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [(row[0], row[1], row[2]) for row in rows]


def get_secret(rt: Runtime, key: str) -> str:
    value = os.environ.get(key)
    if value:
        return value
    script = f"source {sh_quote(str(rt.repo_root / 'lib' / 'creds-helper.sh'))}; creds_get {sh_quote(key)}"
    proc = subprocess.run(["bash", "-lc", script], cwd=rt.repo_root, text=True, capture_output=True, check=False)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise NotionError(f"{key} not available", code=NEEDS_CLARIFICATION)
    return proc.stdout.strip()


def refresh_embeddings(rt: Runtime, provider: dict[str, Any], rows: list[tuple[str, str, str]]) -> int:
    if not rows:
        return 0
    key = get_secret(rt, provider["key"])
    texts = [row[2][:12000] for row in rows]
    vectors = embed_texts(provider, key, texts)
    with db_connect(rt) as conn:
        for (item_id, kind, text), vector in zip(rows, vectors):
            conn.execute(
                "INSERT OR REPLACE INTO embeddings(item_id,item_kind,provider,model,text_hash,vector_json,updated_at) VALUES(?,?,?,?,?,?,?)",
                (
                    item_id,
                    kind,
                    provider["provider"],
                    provider["model"],
                    hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    json.dumps(vector),
                    now_iso(),
                ),
            )
    return len(vectors)


def embed_texts(provider: dict[str, Any], key: str, texts: list[str]) -> list[list[float]]:
    if provider["provider"] == "voyage":
        body = {"model": provider["model"], "input": texts, "input_type": "document"}
    else:
        body = {"model": provider["model"], "input": texts}
    req = urllib.request.Request(
        provider["url"],
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            return [item["embedding"] for item in data.get("data", [])]
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise NotionError("embedding request failed", status=exc.code, code=1) from exc
    return []


def semantic_search(rt: Runtime, query: str, limit: int) -> list[dict[str, Any]]:
    provider = embedding_provider(rt)
    if not provider:
        return []
    key = get_secret(rt, provider["key"])
    query_vector = embed_texts(provider, key, [query])[0]
    with db_connect(rt) as conn:
        rows = conn.execute(
            """
            SELECT embeddings.item_id, embeddings.item_kind, embeddings.vector_json,
                   notion_fts.title, notion_fts.text, notion_fts.url
            FROM embeddings JOIN notion_fts ON notion_fts.item_id=embeddings.item_id
            WHERE embeddings.provider=? AND embeddings.model=?
            """,
            (provider["provider"], provider["model"]),
        ).fetchall()
    scored = []
    for row in rows:
        score = cosine(query_vector, json.loads(row[2]))
        scored.append({"kind": row[1], "id": row[0], "title": row[3], "text": row[4], "url": row[5], "score": score})
    return sorted(scored, key=lambda item: item["score"], reverse=True)[:limit]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def merge_hybrid(keyword: list[dict[str, Any]], semantic: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for rank, item in enumerate(keyword):
        key = item["id"]
        item = dict(item)
        item["score"] = item.get("score", 0.0) + max(0.0, 1.0 - rank * 0.05)
        out[key] = item
    for rank, item in enumerate(semantic):
        key = item["id"]
        existing = out.get(key, dict(item))
        existing["score"] = existing.get("score", 0.0) + max(0.0, 1.0 - rank * 0.03)
        out[key] = existing
    return sorted(out.values(), key=lambda item: item.get("score", 0), reverse=True)[:limit]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-notion", add_help=True)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor").set_defaults(func=cmd_doctor)
    sub.add_parser("snapshot").set_defaults(func=cmd_snapshot)
    auth = sub.add_parser("auth")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    auth_sub.add_parser("status").set_defaults(func=cmd_auth_status)
    sub.add_parser("workspace").set_defaults(func=cmd_workspace)
    sub.add_parser("users").set_defaults(func=cmd_users)
    search = sub.add_parser("search")
    search.add_argument("query", nargs="*")
    search.add_argument("--limit", type=int, default=10)
    search.set_defaults(func=cmd_search)
    read = sub.add_parser("read")
    read.add_argument("page")
    read.set_defaults(func=cmd_read)
    blocks = sub.add_parser("blocks")
    blocks.add_argument("page")
    blocks.set_defaults(func=cmd_blocks)

    ds = sub.add_parser("data-sources")
    ds_sub = ds.add_subparsers(dest="ds_command", required=True)
    ds_sub.add_parser("list").set_defaults(func=cmd_data_sources)
    ds_schema = ds_sub.add_parser("schema")
    ds_schema.add_argument("target")
    ds_schema.set_defaults(func=cmd_data_sources)
    ds_query = ds_sub.add_parser("query")
    ds_query.add_argument("target")
    ds_query.add_argument("--limit", type=int, default=25)
    ds_query.set_defaults(func=cmd_data_sources)

    save = sub.add_parser("save")
    add_save_args(save)
    save.set_defaults(func=cmd_save)
    group = sub.add_parser("save-group")
    add_save_args(group)
    group.add_argument("--child", action="append", default=[])
    group.set_defaults(func=cmd_save_group)
    verify = sub.add_parser("verify")
    verify.add_argument("page")
    verify.set_defaults(func=cmd_verify)

    task = sub.add_parser("task")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    task_add = task_sub.add_parser("add")
    add_save_args(task_add)
    task_add.add_argument("--owner")
    task_add.add_argument("--due")
    task_add.add_argument("--status", default="not started")
    task_add.set_defaults(func=cmd_task)

    decision = sub.add_parser("decision")
    decision_sub = decision.add_subparsers(dest="decision_command", required=True)
    dec_record = decision_sub.add_parser("record")
    add_save_args(dec_record)
    dec_record.set_defaults(func=cmd_decision)

    handoff = sub.add_parser("handoff")
    handoff_sub = handoff.add_subparsers(dest="handoff_command", required=True)
    handoff_create = handoff_sub.add_parser("create")
    add_save_args(handoff_create)
    handoff_create.set_defaults(func=cmd_handoff)

    comment = sub.add_parser("comment")
    comment_sub = comment.add_subparsers(dest="comment_command", required=True)
    comment_add = comment_sub.add_parser("add")
    comment_add.add_argument("page")
    comment_add.add_argument("--text", required=True)
    comment_add.add_argument("--mention-user")
    comment_add.set_defaults(func=cmd_comment)

    sync = sub.add_parser("sync")
    sync.add_argument("--limit", type=int, default=50)
    sync.set_defaults(func=cmd_sync)
    cache = sub.add_parser("cache")
    cache_sub = cache.add_subparsers(dest="cache_command", required=True)
    cache_sub.add_parser("status").set_defaults(func=cmd_cache)
    cache_search = cache_sub.add_parser("search")
    cache_search.add_argument("query", nargs="*")
    cache_search.add_argument("--limit", type=int, default=10)
    cache_search.add_argument("--mode", choices=["keyword", "semantic", "hybrid"], default="keyword")
    cache_search.set_defaults(func=cmd_cache)

    boot = sub.add_parser("bootstrap-team")
    boot.add_argument("--create-missing", action="store_true")
    boot.set_defaults(func=cmd_bootstrap_team)
    schema = sub.add_parser("schema")
    schema_sub = schema.add_subparsers(dest="schema_command", required=True)
    schema_sub.add_parser("show").set_defaults(func=cmd_schema)

    webhooks = sub.add_parser("webhooks")
    webhook_sub = webhooks.add_subparsers(dest="webhook_command", required=True)
    webhook_sub.add_parser("doctor").set_defaults(func=cmd_webhooks)
    ingest = webhook_sub.add_parser("ingest")
    ingest.add_argument("--body-file", required=True)
    ingest.add_argument("--signature")
    ingest.set_defaults(func=cmd_webhooks)

    embed = sub.add_parser("embed")
    embed_sub = embed.add_subparsers(dest="embed_command", required=True)
    embed_sub.add_parser("status").set_defaults(func=cmd_embed)
    embed_refresh = embed_sub.add_parser("refresh")
    embed_refresh.add_argument("--limit", type=int, default=100)
    embed_refresh.set_defaults(func=cmd_embed)

    return parser


def add_save_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title")
    parser.add_argument("--content", default="")
    parser.add_argument("--data-source")
    parser.add_argument("--parent-page")
    parser.add_argument("--type", choices=["note", "task", "decision", "handoff", "spec", "meeting"], default="note")
    parser.add_argument("--scope", choices=["local", "team", "project-public", "public"], default="team")


def main(argv: list[str]) -> int:
    json_mode = "--json" in argv
    cleaned = [arg for arg in argv if arg != "--json"]
    if not cleaned:
        cleaned = ["doctor"]
    rt = Runtime(json_mode=json_mode)
    parser = build_parser()
    try:
        args = parser.parse_args(cleaned)
        return args.func(rt, args)
    except NotionError as exc:
        payload = {"ok": False, "error": exc.message, **exc.payload}
        emit(payload, json_mode)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
