#!/usr/bin/env bash
# lib/common.sh — Shared utilities for agent-context
# Sourced by agent-context entry point. Do not run directly.

CONTEXT_BASE="${AGENT_DO_HOME:-$HOME/.agent-do}"
CONTEXT_HOME="$CONTEXT_BASE/context"
CONTEXT_CACHE_DIR="$CONTEXT_HOME/cache"
CONTEXT_INDEX_DB="$CONTEXT_HOME/index.db"
CONTEXT_LOCK_DIR="$CONTEXT_BASE/context.lock"
CONTEXT_LOCK_TIMEOUT="${AGENT_CONTEXT_LOCK_TIMEOUT:-30}"

die() { echo "Error: $*" >&2; exit 1; }

today() { date +%Y-%m-%d; }
now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

redact_url() {
    python3 - "$1" << 'PYTHON'
import sys
from urllib.parse import parse_qsl, urlencode, urlunparse, urlparse

secret_names = ("token", "key", "secret", "signature", "sig", "password", "passwd", "auth", "credential")
url = sys.argv[1]
parsed = urlparse(url)
if not parsed.scheme:
    print(url)
    raise SystemExit(0)
netloc = parsed.netloc
if "@" in netloc:
    netloc = "[redacted]@" + netloc.rsplit("@", 1)[1]
query = []
for key, value in parse_qsl(parsed.query, keep_blank_values=True):
    if any(secret in key.lower() for secret in secret_names):
        query.append((key, "[redacted]"))
    else:
        query.append((key, value))
print(urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, urlencode(query), parsed.fragment)))
PYTHON
}

with_context_lock() (
    local attempts=0
    local max_attempts
    max_attempts=$((CONTEXT_LOCK_TIMEOUT * 10))
    mkdir -p "$CONTEXT_BASE"

    while ! mkdir "$CONTEXT_LOCK_DIR" 2>/dev/null; do
        if [[ -f "$CONTEXT_LOCK_DIR/pid" ]]; then
            local lock_pid
            lock_pid=$(cat "$CONTEXT_LOCK_DIR/pid" 2>/dev/null || true)
            if [[ "$lock_pid" =~ ^[0-9]+$ ]] && ! kill -0 "$lock_pid" 2>/dev/null; then
                rm -rf "$CONTEXT_LOCK_DIR"
                continue
            fi
        fi

        attempts=$((attempts + 1))
        if [[ "$attempts" -ge "$max_attempts" ]]; then
            die "Timed out waiting for context lock: $CONTEXT_LOCK_DIR"
        fi
        sleep 0.1
    done

    printf '%s\n' "$$" > "$CONTEXT_LOCK_DIR/pid"
    trap 'rm -rf "$CONTEXT_LOCK_DIR" 2>/dev/null || true' EXIT INT TERM
    "$@"
)

ensure_init() {
    [[ -d "$CONTEXT_HOME" ]] || {
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_error "Not initialized. Run 'agent-do context init' first." 1
        else
            echo "Error: Not initialized. Run 'agent-do context init' first." >&2
        fi
        exit 1
    }
    _context_migrate_schema
}

validate_json() {
    echo "$1" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null
}

append_jsonl() {
    local file="$1" line="$2"
    validate_json "$line" || {
        echo "Error: Invalid JSON: $line" >&2
        return 1
    }
    echo "$line" >> "$file"
}

count_lines() {
    local file="$1"
    [[ -f "$file" && -s "$file" ]] && wc -l < "$file" | tr -d ' ' || echo "0"
}

# Approximate token count: words * 1.3
count_tokens() {
    local file="$1"
    if [[ -f "$file" ]]; then
        python3 -c "
import sys
with open(sys.argv[1]) as f:
    words = len(f.read().split())
print(int(words * 1.3))
" "$file"
    else
        echo "0"
    fi
}

# Generate a safe filesystem ID from a URL or name
make_id() {
    python3 -c "
import sys, re
raw = sys.argv[1]
# Strip protocol
raw = re.sub(r'^https?://', '', raw)
# Replace non-alphanumeric with hyphens, collapse
safe = re.sub(r'[^a-zA-Z0-9]+', '-', raw).strip('-').lower()
# Truncate
print(safe[:80])
" "$1"
}

# Extract YAML frontmatter from a markdown file
extract_frontmatter() {
    local file="$1"
    python3 - "$file" << 'PYTHON'
import sys, json

path = sys.argv[1]
with open(path) as f:
    content = f.read()

# Check for YAML frontmatter
if not content.startswith('---'):
    print('{}')
    sys.exit(0)

parts = content.split('---', 2)
if len(parts) < 3:
    print('{}')
    sys.exit(0)

try:
    import yaml
    meta = yaml.safe_load(parts[1])
    print(json.dumps(meta or {}, ensure_ascii=False))
except ImportError:
    # Fallback: parse simple key: value pairs, including YAML block scalars.
    meta = {}
    lines = parts[1].split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith('#') or ':' not in line:
            i += 1
            continue
        k, v = line.split(':', 1)
        key = k.strip()
        value = v.strip()
        if value in {'|', '>'}:
            block = []
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if nxt and not nxt.startswith((' ', '\t')) and ':' in nxt:
                    break
                if nxt.strip():
                    block.append(nxt.strip())
                i += 1
            meta[key] = '\n'.join(block).strip()
            continue
        meta[key] = value.strip('"').strip("'")
        i += 1
    print(json.dumps(meta, ensure_ascii=False))
except Exception:
    print('{}')
PYTHON
}

# Strip YAML frontmatter, return body only
strip_frontmatter() {
    local file="$1"
    python3 -c "
import sys
with open(sys.argv[1]) as f:
    content = f.read()
if content.startswith('---'):
    parts = content.split('---', 2)
    if len(parts) >= 3:
        print(parts[2].strip())
    else:
        print(content)
else:
    print(content)
" "$file"
}

# Write meta.json for a cached package
write_meta() {
    local dir="$1" name="$2" type="$3" description="$4" source_url="$5" token_count="$6"
    local trust="${7:-community}" tags="${8:-}"
    python3 - "$dir" "$name" "$type" "$description" "$source_url" "$token_count" "$trust" "$tags" << 'PYTHON'
import json, sys
from datetime import datetime, timezone

meta = {
    "name": sys.argv[2],
    "type": sys.argv[3],
    "description": sys.argv[4],
    "source": sys.argv[5],
    "token_count": int(sys.argv[6]),
    "trust": sys.argv[7],
    "tags": [t.strip() for t in sys.argv[8].split(",") if t.strip()],
    "fetched_at": datetime.now(timezone.utc).isoformat(),
}
with open(f"{sys.argv[1]}/meta.json", "w") as f:
    json.dump(meta, f, indent=2, ensure_ascii=False)
PYTHON
}

_context_migrate_schema() {
    mkdir -p "$CONTEXT_CACHE_DIR" "$CONTEXT_HOME"

    python3 - "$CONTEXT_INDEX_DB" "$CONTEXT_CACHE_DIR" << 'PYTHON'
import hashlib
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

db_path, cache_dir = sys.argv[1:3]
TEXT_EXTENSIONS = {
    ".md", ".mdx", ".txt", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml",
    ".yml", ".py", ".sh", ".css", ".html", ".sql", ".toml",
}
DEFAULT_TTL_DAYS = 7
SCHEMA_VERSION = "1"


def now():
    return datetime.now(timezone.utc)


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def iso(value):
    return value.replace(microsecond=0).isoformat()


def infer_source_kind(pkg_id, name, ptype, source):
    blob = " ".join(str(item or "").lower() for item in (pkg_id, name, source))
    if ptype == "skill":
        return "local-skill"
    if ptype == "local":
        return "local-project"
    if "llms" in blob:
        return "llms"
    if "github.com" in blob and "/tree/" in blob:
        return "github-dir"
    if "github.com" in blob:
        return "github-file"
    if str(source or "").startswith(("http://", "https://")):
        return "url"
    return "local-project"


def package_status(ptype, source_kind, fetched_at):
    if source_kind.startswith("local") or ptype in {"skill", "local"}:
        return "local", None, "local-mtime"
    fetched = parse_dt(fetched_at)
    expires = (fetched or now()) + timedelta(days=DEFAULT_TTL_DAYS)
    status = "fresh" if fetched and fetched + timedelta(days=DEFAULT_TTL_DAYS) >= now() else "stale"
    return status, iso(expires), "on-use"


def iter_package_files(root):
    if not root or not os.path.isdir(root):
        return []
    rows = []
    for dirpath, _, filenames in os.walk(root):
        for filename in sorted(filenames):
            path = os.path.join(dirpath, filename)
            rel = os.path.relpath(path, root)
            if rel == "meta.json":
                continue
            if os.path.splitext(filename)[1].lower() not in TEXT_EXTENSIONS:
                continue
            try:
                with open(path, "rb") as handle:
                    raw = handle.read()
            except OSError:
                continue
            text = raw.decode("utf-8", errors="replace")
            rows.append({
                "rel_path": rel,
                "hash": hashlib.sha256(raw).hexdigest(),
                "tokens": int(len(text.split()) * 1.3),
            })
    return rows


def package_hash(files):
    hasher = hashlib.sha256()
    for item in files:
        hasher.update(item["rel_path"].encode())
        hasher.update(item["hash"].encode())
    return hasher.hexdigest() if files else ""


conn = sqlite3.connect(db_path)
conn.execute("PRAGMA busy_timeout = 5000")
conn.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS packages USING fts5(
        id, name, description, tags, content_preview,
        source UNINDEXED, trust UNINDEXED, token_count UNINDEXED,
        cache_path UNINDEXED, type UNINDEXED
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS package_meta (
        id TEXT PRIMARY KEY,
        name TEXT,
        type TEXT,
        trust TEXT,
        token_count INTEGER,
        source TEXT,
        cache_path TEXT,
        fetched_at TEXT,
        last_accessed TEXT,
        access_count INTEGER DEFAULT 0
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS context_schema (
        key TEXT PRIMARY KEY,
        value TEXT
    )
""")

existing = {row[1] for row in conn.execute("PRAGMA table_info(package_meta)")}
columns = {
    "tags": "TEXT",
    "source_kind": "TEXT",
    "canonical_url": "TEXT",
    "etag": "TEXT",
    "last_modified": "TEXT",
    "content_hash": "TEXT",
    "checked_at": "TEXT",
    "expires_at": "TEXT",
    "refresh_status": "TEXT",
    "refresh_error": "TEXT",
    "refresh_policy": "TEXT",
}
for name, decl in columns.items():
    if name not in existing:
        conn.execute(f"ALTER TABLE package_meta ADD COLUMN {name} {decl}")

conn.execute("""
    CREATE TABLE IF NOT EXISTS package_files (
        package_id TEXT NOT NULL,
        rel_path TEXT NOT NULL,
        source_url TEXT,
        content_hash TEXT,
        token_count INTEGER DEFAULT 0,
        fetched_at TEXT,
        indexed_at TEXT,
        PRIMARY KEY (package_id, rel_path)
    )
""")

version = conn.execute("SELECT value FROM context_schema WHERE key = 'version'").fetchone()
if not version or version[0] != SCHEMA_VERSION:
    indexed_at = iso(now())
    conn.execute("DELETE FROM package_files")
    rows = conn.execute(
        "SELECT id, name, type, trust, token_count, source, cache_path, fetched_at FROM package_meta"
    ).fetchall()
    for pkg_id, name, ptype, trust, tokens, source, cache_path, fetched_at in rows:
        tags_row = conn.execute("SELECT tags FROM packages WHERE id = ?", (pkg_id,)).fetchone()
        tags = tags_row[0] if tags_row else ""
        source_kind = infer_source_kind(pkg_id, name, ptype, source)
        status, expires_at, policy = package_status(ptype, source_kind, fetched_at)
        files = iter_package_files(cache_path)
        content_hash = package_hash(files)
        checked_at = indexed_at
        conn.execute(
            """
            UPDATE package_meta
            SET tags = COALESCE(tags, ?),
                source_kind = COALESCE(source_kind, ?),
                canonical_url = COALESCE(canonical_url, ?),
                content_hash = COALESCE(content_hash, ?),
                checked_at = COALESCE(checked_at, ?),
                expires_at = COALESCE(expires_at, ?),
                refresh_status = COALESCE(refresh_status, ?),
                refresh_policy = COALESCE(refresh_policy, ?),
                refresh_error = COALESCE(refresh_error, '')
            WHERE id = ?
            """,
            (tags, source_kind, source, content_hash, checked_at, expires_at, status, policy, pkg_id),
        )
        for item in files:
            conn.execute(
                """
                INSERT OR REPLACE INTO package_files
                (package_id, rel_path, source_url, content_hash, token_count, fetched_at, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (pkg_id, item["rel_path"], source, item["hash"], item["tokens"], fetched_at, indexed_at),
            )

    conn.execute(
        "INSERT OR REPLACE INTO context_schema (key, value) VALUES ('version', ?)",
        (SCHEMA_VERSION,),
    )

conn.commit()
conn.close()
PYTHON
}

# Initialize storage
cmd_init() {
    if [[ -d "$CONTEXT_HOME" ]]; then
        _context_migrate_schema
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_success "Already initialized at $CONTEXT_HOME"
        else
            echo "Already initialized at $CONTEXT_HOME"
        fi
        return 0
    fi

    mkdir -p "$CONTEXT_CACHE_DIR"
    mkdir -p "$CONTEXT_HOME"

    # Default config
    cat > "$CONTEXT_HOME/config.yaml" << 'YAML'
# agent-context configuration
sources: []

trust_policy:
  allow: [official, maintainer, community, local]
  prefer: official

defaults:
  max_tokens: 8000
  cache_max_mb: 500
  ttl: 7d
YAML

    # Initialize empty JSONL files
    touch "$CONTEXT_HOME/annotations.jsonl"
    touch "$CONTEXT_HOME/feedback.jsonl"

    # Initialize FTS5 index
    python3 - "$CONTEXT_INDEX_DB" << 'PYTHON'
import sqlite3, sys

conn = sqlite3.connect(sys.argv[1])
conn.execute('PRAGMA busy_timeout = 5000')
conn.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS packages USING fts5(
        id, name, description, tags, content_preview,
        source UNINDEXED, trust UNINDEXED, token_count UNINDEXED,
        cache_path UNINDEXED, type UNINDEXED
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS package_meta (
        id TEXT PRIMARY KEY,
        name TEXT,
        type TEXT,
        trust TEXT,
        token_count INTEGER,
        source TEXT,
        cache_path TEXT,
        fetched_at TEXT,
        last_accessed TEXT,
        access_count INTEGER DEFAULT 0
    )
""")
conn.commit()
conn.close()
PYTHON

    _context_migrate_schema

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_success "Initialized at $CONTEXT_HOME"
    else
        echo "Initialized context store at $CONTEXT_HOME"
        echo "  Config:      $CONTEXT_HOME/config.yaml"
        echo "  Cache:       $CONTEXT_CACHE_DIR/"
        echo "  Index:       $CONTEXT_INDEX_DB"
        echo "  Annotations: $CONTEXT_HOME/annotations.jsonl"
    fi
}

_context_freshness_counts() {
    python3 - "$CONTEXT_INDEX_DB" << 'PYTHON'
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

conn = sqlite3.connect(sys.argv[1])
conn.execute("PRAGMA busy_timeout = 5000")
now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
counts = Counter()
for status, expires_at in conn.execute(
    "SELECT COALESCE(refresh_status, 'unknown'), expires_at FROM package_meta"
):
    resolved = status or "unknown"
    if resolved not in {"local", "failed"} and expires_at and expires_at < now:
        resolved = "stale"
    counts[resolved] += 1
conn.close()
print(
    counts.get("fresh", 0),
    counts.get("stale", 0),
    counts.get("failed", 0),
    counts.get("local", 0),
    counts.get("unknown", 0),
)
PYTHON
}

# Status overview
cmd_status() {
    ensure_init

    local pkg_count cache_size_kb annotations_count feedback_count
    local fresh_count stale_count failed_count local_count unknown_count

    pkg_count=$(python3 -c "
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute('PRAGMA busy_timeout = 5000')
try:
    row = conn.execute('SELECT COUNT(*) FROM package_meta').fetchone()
    print(row[0])
except:
    print(0)
conn.close()
" "$CONTEXT_INDEX_DB" 2>/dev/null || echo "0")

    cache_size_kb=$(du -sk "$CONTEXT_CACHE_DIR" 2>/dev/null | cut -f1 || echo "0")
    annotations_count=$(count_lines "$CONTEXT_HOME/annotations.jsonl")
    feedback_count=$(count_lines "$CONTEXT_HOME/feedback.jsonl")
    read -r fresh_count stale_count failed_count local_count unknown_count < <(_context_freshness_counts)

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        snapshot_begin "context"
        snapshot_num_field "packages" "$pkg_count"
        snapshot_num_field "fresh_packages" "$fresh_count"
        snapshot_num_field "stale_packages" "$stale_count"
        snapshot_num_field "failed_packages" "$failed_count"
        snapshot_num_field "local_packages" "$local_count"
        snapshot_num_field "unknown_packages" "$unknown_count"
        snapshot_num_field "cache_size_kb" "$cache_size_kb"
        snapshot_num_field "annotations" "$annotations_count"
        snapshot_num_field "feedback_ratings" "$feedback_count"
        snapshot_field "home" "$CONTEXT_HOME"
        snapshot_end
    else
        echo "agent-context status"
        echo "  Packages:    $pkg_count indexed"
        echo "  Freshness:   $fresh_count fresh, $stale_count stale, $failed_count failed, $local_count local, $unknown_count unknown"
        echo "  Cache:       ${cache_size_kb}KB"
        echo "  Annotations: $annotations_count"
        echo "  Feedback:    $feedback_count ratings"
        echo "  Home:        $CONTEXT_HOME"
    fi
}

cmd_stale() {
    ensure_init

    python3 - "$CONTEXT_INDEX_DB" "${OUTPUT_FORMAT:-text}" << 'PYTHON'
import json
import sqlite3
import sys
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

db_path, output_format = sys.argv[1:3]
now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
SECRET_NAMES = ("token", "key", "secret", "signature", "sig", "password", "passwd", "auth", "credential")

def redact_url(url):
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.scheme:
        return url
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = "[redacted]@" + netloc.rsplit("@", 1)[1]
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if any(secret in key.lower() for secret in SECRET_NAMES):
            query.append((key, "[redacted]"))
        else:
            query.append((key, value))
    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, urlencode(query), parsed.fragment))

conn = sqlite3.connect(db_path)
conn.execute("PRAGMA busy_timeout = 5000")
rows = conn.execute(
    """
    SELECT id, name, type, source_kind, refresh_status, checked_at, expires_at,
           refresh_error, source
    FROM package_meta
    WHERE COALESCE(refresh_status, 'unknown') IN ('stale', 'failed', 'unknown')
       OR (expires_at IS NOT NULL AND expires_at < ? AND COALESCE(refresh_status, '') != 'local')
    ORDER BY
      CASE COALESCE(refresh_status, 'unknown')
        WHEN 'failed' THEN 0
        WHEN 'stale' THEN 1
        ELSE 2
      END,
      name
    """,
    (now,),
).fetchall()
conn.close()

items = []
for row in rows:
    pkg_id, name, ptype, source_kind, status, checked_at, expires_at, error, source = row
    resolved = status or "unknown"
    if resolved not in {"local", "failed"} and expires_at and expires_at < now:
        resolved = "stale"
    items.append({
        "id": pkg_id,
        "name": name,
        "type": ptype,
        "source_kind": source_kind or "",
        "refresh_status": resolved,
        "checked_at": checked_at or "",
        "expires_at": expires_at or "",
        "refresh_error": redact_url(error or ""),
        "source": redact_url(source or ""),
    })

if output_format == "json":
    print(json.dumps({"success": True, "count": len(items), "packages": items}, indent=2))
else:
    if not items:
        print("No stale packages.")
    else:
        print(f"{len(items)} stale package(s):\n")
        for item in items:
            expires = item["expires_at"] or "no expiry"
            print(f"  {item['refresh_status']:7s} {item['name']} ({item['id']})")
            print(f"          Type: {item['type']}  Source: {item['source_kind']}  Expires: {expires}")
            if item["refresh_error"]:
                print(f"          Error: {item['refresh_error']}")
PYTHON
}
