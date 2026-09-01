#!/usr/bin/env python3
"""Focused coverage for agent-render logs."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_bash(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-lc", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    help_result = subprocess.run(
        ["./agent-do", "render", "logs", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    require(help_result.returncode == 0, f"render logs --help failed: {help_result.stderr}")
    require("Usage: agent-render logs <service> [options]" in help_result.stdout, f"unexpected render logs help: {help_result.stdout}")
    require("--since <time>" in help_result.stdout, f"expected logs help flags: {help_result.stdout}")

    temp_dir = tempfile.TemporaryDirectory()
    query_path = Path(temp_dir.name) / "render-queries.txt"
    render_script = f"""
set -euo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-render'}")
resolve_service() {{
  echo "srv-test"
}}
normalize_log_time() {{
  if [[ "$1" == "60" ]]; then
    echo "2026-04-19T12:00:00Z"
  else
    echo "$1"
  fi
}}
render_request_checked() {{
  local method="$1"
  local endpoint="$2"
  if [[ "$endpoint" == "/services/srv-test" ]]; then
    printf '%s\\n' '{{"id":"srv-test","ownerId":"tea-test-owner"}}'
    return 0
  fi
  if [[ "$endpoint" == /logs\\?* ]]; then
    printf '%s\\n' "$endpoint" >> "{query_path}"
    printf '%s\\n' '{{"hasMore":true,"nextStartTime":"2026-04-19T11:00:00Z","nextEndTime":"2026-04-19T12:00:00Z","logs":[{{"timestamp":"2026-04-19T12:30:00Z","labels":[{{"name":"type","value":"app"}},{{"name":"level","value":"info"}}],"message":"\\u001b[0;32mhello\\u001b[0m"}}]}}'
    return 0
  fi
  echo "unexpected endpoint: $endpoint" >&2
  return 1
}}
render_request() {{
  render_request_checked "$@"
}}
cmd_logs my-render-service --since 60 --limit 5 --type app --level info --text error --host api.example.com --method GET --status 500 --path /billing
cmd_logs my-render-service --limit 5
"""

    result = run_bash(render_script)
    require(result.returncode == 0, f"render logs command failed: {result.stderr}")
    require(query_path.exists(), "expected query capture file to exist")
    queries = query_path.read_text().splitlines()
    require(len(queries) == 2, f"expected filtered and unfiltered queries, got: {queries}")
    query = queries[0]
    require(query.startswith("/logs?"), f"expected /logs endpoint, got: {query}")
    require("ownerId=tea-test-owner" in query, f"missing ownerId in query: {query}")
    require("resource=srv-test" in query, f"missing resource filter in query: {query}")
    require("startTime=2026-04-19T12%3A00%3A00Z" in query, f"missing startTime in query: {query}")
    require("limit=5" in query, f"missing limit in query: {query}")
    require("type=app" in query, f"missing type filter in query: {query}")
    require("level=info" in query, f"missing level filter in query: {query}")
    require("text=error" in query, f"missing text filter in query: {query}")
    require("host=api.example.com" in query, f"missing host filter in query: {query}")
    require("method=GET" in query, f"missing method filter in query: {query}")
    require("statusCode=500" in query, f"missing status code filter in query: {query}")
    require("path=%2Fbilling" in query, f"missing path filter in query: {query}")
    unfiltered_query = queries[1]
    require("ownerId=tea-test-owner" in unfiltered_query, f"missing ownerId: {unfiltered_query}")
    require("resource=srv-test" in unfiltered_query, f"missing resource: {unfiltered_query}")
    for unexpected in ("type=", "level=", "text=", "host=", "method=", "statusCode=", "path="):
        require(unexpected not in unfiltered_query, f"unexpected filter {unexpected}: {unfiltered_query}")

    require(result.stdout.count("[app/info] hello") == 2, f"unexpected render log output: {result.stdout}")
    require(result.stderr.count("More logs available.") == 2, f"expected pagination hints: {result.stderr}")
    temp_dir.cleanup()

    print("render tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
