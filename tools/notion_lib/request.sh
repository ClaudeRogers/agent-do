#!/usr/bin/env bash
# Notion API request helper. All live Notion HTTP calls from agent-notion pass
# through lib/retry.sh so rate limits and transient failures share repo policy.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck source=/dev/null
source "$REPO_ROOT/lib/retry.sh"
# shellcheck source=/dev/null
source "$REPO_ROOT/lib/creds-helper.sh"

method="${1:-}"
endpoint="${2:-}"
body_file="${3:-}"

if [[ -z "$method" || -z "$endpoint" ]]; then
    echo '{"object":"error","code":"invalid_request","message":"method and endpoint required"}' >&2
    exit 2
fi

token="$(creds_get NOTION_TOKEN 2>/dev/null || true)"
if [[ -z "$token" ]]; then
    echo '{"object":"error","code":"missing_credentials","message":"NOTION_TOKEN not set"}'
    exit 1
fi

base="${NOTION_API_BASE:-https://api.notion.com/v1}"
version="${NOTION_VERSION:-2025-09-03}"
url="${base}${endpoint}"

args=(
    -H "Authorization: Bearer $token"
    -H "Content-Type: application/json"
    -H "Notion-Version: $version"
)

if [[ -n "$body_file" ]]; then
    args+=(--data-binary "@$body_file")
fi

api_request "$method" "$url" "${args[@]}"
