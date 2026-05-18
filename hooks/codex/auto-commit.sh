#!/bin/bash
# Auto-commit hook: atomic commits per agent session.
#
# Scope rule:
# - Prefer explicit CODEX_AUTO_COMMIT_PATHS / AGENT_AUTO_COMMIT_PATHS.
# - Otherwise use the current agent-do coord focus paths.
# - Never treat "." or repo-root focus as a safe auto-commit scope.
# - If there is no safe scope, commit already staged files only; otherwise skip.

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || exit 0)
cd "$REPO_ROOT"

if git diff --quiet && git diff --cached --quiet && [[ -z "$(git ls-files --others --exclude-standard)" ]]; then
    exit 0
fi

if [[ -n "${CODEX_THREAD_ID:-}" ]]; then
    AGENT_ID="${CODEX_THREAD_ID//-/}"
    AGENT_ID="${AGENT_ID:0:8}"
elif [[ -n "${CLAUDE_SESSION_ID:-}" ]]; then
    AGENT_ID="${CLAUDE_SESSION_ID:0:8}"
elif [[ -n "${OPENCODE_SESSION_ID:-}" ]]; then
    AGENT_ID="${OPENCODE_SESSION_ID:0:8}"
elif [[ -n "${WARP_SESSION_ID:-}" ]]; then
    AGENT_ID="${WARP_SESSION_ID:0:8}"
else
    AGENT_ID=$(date +%s | shasum | head -c 8)
fi

TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

normalized_scope_paths() {
    local source="${CODEX_AUTO_COMMIT_PATHS:-${AGENT_AUTO_COMMIT_PATHS:-}}"

    if [[ -n "$source" ]]; then
        AUTO_COMMIT_SCOPE_RAW="$source" python3 - "$REPO_ROOT" <<'PY'
import os
import re
import sys

repo = os.path.realpath(sys.argv[1])
raw = os.environ.get("AUTO_COMMIT_SCOPE_RAW", "")
items = re.split(r"[\n:]+", raw)
seen = set()
for item in items:
    path = item.strip()
    if not path:
        continue
    path = os.path.expanduser(path)
    if os.path.isabs(path):
        real = os.path.realpath(path)
        try:
            if os.path.commonpath([repo, real]) != repo:
                continue
        except ValueError:
            continue
        rel = os.path.relpath(real, repo)
    else:
        rel = os.path.normpath(path)

    if rel in ("", ".", os.curdir, ".git") or rel.startswith(("..", ".git/")):
        continue
    if rel not in seen:
        print(rel)
        seen.add(rel)
PY
        return 0
    fi

    if command -v agent-do >/dev/null 2>&1; then
        agent-do coord focus show --json 2>/dev/null | python3 - "$REPO_ROOT" <<'PY'
import json
import os
import sys

repo = os.path.realpath(sys.argv[1])
try:
    data = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)

paths = ((data.get("focus") or {}).get("paths") or [])
seen = set()
for item in paths:
    if not isinstance(item, str):
        continue
    path = os.path.expanduser(item.strip())
    if not path:
        continue

    if os.path.isabs(path):
        real = os.path.realpath(path)
        try:
            if os.path.commonpath([repo, real]) != repo:
                continue
        except ValueError:
            continue
        rel = os.path.relpath(real, repo)
    else:
        rel = os.path.normpath(path)

    # A repo-wide focus is a coordination signal, not a commit allowlist.
    if rel in ("", ".", os.curdir, ".git") or rel.startswith(("..", ".git/")):
        continue
    if rel not in seen:
        print(rel)
        seen.add(rel)
PY
    fi
}

RAW_SCOPE_SOURCE="none"
if [[ -n "${CODEX_AUTO_COMMIT_PATHS:-${AGENT_AUTO_COMMIT_PATHS:-}}" ]]; then
    RAW_SCOPE_SOURCE="env"
elif command -v agent-do >/dev/null 2>&1; then
    RAW_SCOPE_SOURCE="coord"
fi

SCOPE_SOURCE="none"
SCOPE_PATHS=()
while IFS= read -r path; do
    [[ -n "$path" ]] && SCOPE_PATHS+=("$path")
done < <(normalized_scope_paths)
if [[ "${#SCOPE_PATHS[@]}" -gt 0 ]]; then
    SCOPE_SOURCE="$RAW_SCOPE_SOURCE"
fi

commit_message() {
    local files_changed=$1
    local files_list=$2
    local suffix="${3:-}"
    cat <<MSG
[agent-$AGENT_ID] Auto-commit: $files_changed files ($files_list)${suffix}

Timestamp: $TIMESTAMP
Agent Session: $AGENT_ID
Tool: codex
Scope Source: $SCOPE_SOURCE

Co-Authored-By: Codex <agent@openai.com>
MSG
}

# Safe commit: respects pre-commit hooks. Tries the commit; if pre-commit
# auto-fixed files in place, re-stages and retries once. If commit still
# fails, leaves the work staged and writes a recovery breadcrumb instead of
# silently bypassing the safety gate.
#
# Args:
#   $1 = "cached" or "scoped"
#   $2 = (only for scoped) array name with scope paths
safe_commit() {
    local mode="$1"
    local pre_commit_output
    local staged_files
    local breadcrumb_dir
    local breadcrumb
    local files_changed files_list total scoped_files

    if [[ "$mode" == "scoped" ]]; then
        shift
        local -a scope_paths=("$@")
        scoped_files=$(git diff --cached --name-only -- "${scope_paths[@]}" || true)
        files_changed=$(printf '%s\n' "$scoped_files" | sed '/^$/d' | wc -l | tr -d ' ')
        files_list=$(printf '%s\n' "$scoped_files" | sed '/^$/d' | head -5 | tr '\n' ', ' | sed 's/,$//')
        if [[ "$files_changed" -gt 5 ]]; then
            files_list="$files_list, ..."
        fi
        # Attempt 1
        if git commit --only -m "$(commit_message "$files_changed" "$files_list")" -- "${scope_paths[@]}" >/dev/null 2>&1; then
            echo "[auto-commit] Agent $AGENT_ID committed $files_changed scoped files ($SCOPE_SOURCE)" >&2
            return 0
        fi
        # Attempt 2: pre-commit may have auto-fixed scope files in place
        local modified
        modified=$(git diff --name-only -- "${scope_paths[@]}" || true)
        if [[ -n "$modified" ]]; then
            git add -u -- "${scope_paths[@]}" 2>/dev/null || true
            scoped_files=$(git diff --cached --name-only -- "${scope_paths[@]}" || true)
            files_changed=$(printf '%s\n' "$scoped_files" | sed '/^$/d' | wc -l | tr -d ' ')
            files_list=$(printf '%s\n' "$scoped_files" | sed '/^$/d' | head -5 | tr '\n' ', ' | sed 's/,$//')
            if [[ "$files_changed" -gt 5 ]]; then
                files_list="$files_list, ..."
            fi
            if git commit --only -m "$(commit_message "$files_changed" "$files_list" " (after pre-commit auto-fix)")" -- "${scope_paths[@]}" >/dev/null 2>&1; then
                echo "[auto-commit] Agent $AGENT_ID committed $files_changed scoped files after pre-commit auto-fix ($SCOPE_SOURCE)" >&2
                return 0
            fi
        fi
        # Capture failure for breadcrumb
        pre_commit_output=$(git commit --only -m "$(commit_message "$files_changed" "$files_list")" -- "${scope_paths[@]}" 2>&1 || true)
        staged_files=$(git diff --cached --name-only -- "${scope_paths[@]}")
    else
        # cached mode
        files_changed=$(git diff --cached --name-only | wc -l | tr -d ' ')
        if [[ "$files_changed" == "0" ]]; then
            return 1
        fi
        files_list=$(git diff --cached --name-only | head -5 | tr '\n' ', ' | sed 's/,$//')
        total=$(git diff --cached --name-only | wc -l | tr -d ' ')
        if [[ "$total" -gt 5 ]]; then
            files_list="$files_list, ..."
        fi
        # Attempt 1
        if git commit -m "$(commit_message "$files_changed" "$files_list")" >/dev/null 2>&1; then
            echo "[auto-commit] Agent $AGENT_ID committed $files_changed staged files" >&2
            return 0
        fi
        # Attempt 2: pre-commit may have auto-fixed
        if [[ -n "$(git diff --name-only)" ]]; then
            git add -u
            files_changed=$(git diff --cached --name-only | wc -l | tr -d ' ')
            files_list=$(git diff --cached --name-only | head -5 | tr '\n' ', ' | sed 's/,$//')
            total=$(git diff --cached --name-only | wc -l | tr -d ' ')
            if [[ "$total" -gt 5 ]]; then
                files_list="$files_list, ..."
            fi
            if git commit -m "$(commit_message "$files_changed" "$files_list" " (after pre-commit auto-fix)")" >/dev/null 2>&1; then
                echo "[auto-commit] Agent $AGENT_ID committed $files_changed staged files after pre-commit auto-fix" >&2
                return 0
            fi
        fi
        pre_commit_output=$(git commit -m "$(commit_message "$files_changed" "$files_list")" 2>&1 || true)
        staged_files=$(git diff --cached --name-only)
    fi

    # Loud failure: leave staged, write breadcrumb, notify.
    breadcrumb_dir="$REPO_ROOT/.handoff"
    mkdir -p "$breadcrumb_dir"
    breadcrumb="$breadcrumb_dir/auto-commit-blocked-$AGENT_ID.md"

    cat > "$breadcrumb" <<EOF
# Auto-commit blocked — session $AGENT_ID

**Timestamp:** $TIMESTAMP
**Repo:** $REPO_ROOT
**Mode:** $mode
**Scope Source:** $SCOPE_SOURCE
**Reason:** pre-commit hooks refused this commit. Work is staged but uncommitted.

## Pre-commit output

\`\`\`
$pre_commit_output
\`\`\`

## Staged files

\`\`\`
$staged_files
\`\`\`

## Recover

1. Review the pre-commit failure above.
2. Fix the violations, or accept any in-place auto-fixes that landed.
3. \`git commit -m "<your message>"\` to commit manually.
4. Delete this file once resolved.
EOF

    if command -v osascript >/dev/null 2>&1; then
        osascript -e "display notification \"Auto-commit blocked. See .handoff/auto-commit-blocked-$AGENT_ID.md\" with title \"agent-do auto-commit\" sound name \"Basso\"" 2>/dev/null || true
    fi

    echo "[auto-commit] BLOCKED: pre-commit refused. Breadcrumb: $breadcrumb" >&2
    return 1
}

commit_cached() {
    safe_commit "cached"
}

if [[ "${#SCOPE_PATHS[@]}" -gt 0 ]]; then
    for path in "${SCOPE_PATHS[@]}"; do
        git add -A -- "$path" 2>/dev/null || true
    done

    SCOPED_FILES=$(git diff --cached --name-only -- "${SCOPE_PATHS[@]}" || true)
    if [[ -z "$SCOPED_FILES" ]]; then
        echo "[auto-commit] Agent $AGENT_ID skipped: no changes under scoped paths ($SCOPE_SOURCE)" >&2
        exit 0
    fi

    safe_commit "scoped" "${SCOPE_PATHS[@]}" || true
    exit 0
fi

if ! git diff --cached --quiet; then
    SCOPE_SOURCE="staged"
    commit_cached || true
    exit 0
fi

if [[ "${AUTO_COMMIT_ALLOW_ALL:-}" == "1" ]]; then
    SCOPE_SOURCE="allow-all"
    git add -A
    commit_cached || true
    exit 0
fi

DIRTY_COUNT=$(git status --porcelain | wc -l | tr -d ' ')
echo "[auto-commit] Agent $AGENT_ID skipped: no safe scope; leaving $DIRTY_COUNT dirty paths uncommitted" >&2
exit 0
