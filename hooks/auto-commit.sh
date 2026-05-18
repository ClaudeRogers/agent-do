#!/bin/bash
# Auto-commit hook (Stop event): atomic commits per agent session.
#
# Philosophy: each agent's work should be its own commit, tagged by session,
# so git history stays clean and bisectable. With many agents, you don't want
# Agent A's work in Agent B's commit.
#
# Safety: this hook RESPECTS pre-commit hooks. It does NOT use --no-verify.
# Pre-commit hooks exist to catch real things (secrets, formatting, lint
# violations); silently bypassing them is exactly the worst kind of automation
# failure (invisible until a leaked key ships to GitHub).
#
# Flow:
#   1. Try a clean commit. If it succeeds, done.
#   2. If pre-commit auto-fixed files in place (black/ruff/prettier style
#      hooks that modify and then fail the commit), re-stage and retry once.
#   3. If commit still fails, leave the work staged, write a recovery
#      breadcrumb at .handoff/auto-commit-blocked-<session>.md, fire a macOS
#      notification, and exit non-zero. Work is recoverable; nothing is
#      silently bypassed.
#
# Codex users: a companion script at hooks/codex/auto-commit.sh exists with
# the same safety pattern plus per-path scoping driven by coord focus or
# CODEX_AUTO_COMMIT_PATHS / AGENT_AUTO_COMMIT_PATHS env vars.

set -e

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || exit 0)
cd "$REPO_ROOT"

if git diff --quiet && git diff --cached --quiet; then
    exit 0  # nothing to commit
fi

if [[ -n "$CLAUDE_SESSION_ID" ]]; then
    AGENT_ID="${CLAUDE_SESSION_ID:0:8}"
elif [[ -n "$OPENCODE_SESSION_ID" ]]; then
    AGENT_ID="${OPENCODE_SESSION_ID:0:8}"
elif [[ -n "$WARP_SESSION_ID" ]]; then
    AGENT_ID="${WARP_SESSION_ID:0:8}"
else
    AGENT_ID=$(date +%s | shasum | head -c 8)
fi

TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

git add -A

FILES_CHANGED=$(git diff --cached --name-only | wc -l | tr -d ' ')
FILES_LIST=$(git diff --cached --name-only | head -5 | tr '\n' ', ' | sed 's/,$//')
if [[ $(git diff --cached --name-only | wc -l) -gt 5 ]]; then
    FILES_LIST="$FILES_LIST, ..."
fi

build_message() {
    local suffix="${1:-}"
    cat <<MSG
[agent-$AGENT_ID] Auto-commit: $FILES_CHANGED files ($FILES_LIST)${suffix}

Timestamp: $TIMESTAMP
Agent Session: $AGENT_ID
Tool: ${CLAUDE_TOOL:-${OPENCODE_TOOL:-claude}}

Co-Authored-By: agent-do auto-commit <noreply@agent-do>
MSG
}

# Attempt 1: clean commit with pre-commit hooks active.
if git commit -m "$(build_message)" >/dev/null 2>&1; then
    echo "[auto-commit] Agent $AGENT_ID committed $FILES_CHANGED files" >&2
    exit 0
fi

# Attempt 2: did pre-commit auto-fix files in place? Re-stage and retry once.
if [[ -n "$(git diff --name-only)" ]]; then
    git add -u
    FILES_CHANGED=$(git diff --cached --name-only | wc -l | tr -d ' ')
    FILES_LIST=$(git diff --cached --name-only | head -5 | tr '\n' ', ' | sed 's/,$//')
    if [[ $(git diff --cached --name-only | wc -l) -gt 5 ]]; then
        FILES_LIST="$FILES_LIST, ..."
    fi
    if git commit -m "$(build_message ' (after pre-commit auto-fix)')" >/dev/null 2>&1; then
        echo "[auto-commit] Agent $AGENT_ID committed $FILES_CHANGED files after pre-commit auto-fix" >&2
        exit 0
    fi
fi

# Pre-commit really blocked. Capture details, leave staged, notify loudly.
PRE_COMMIT_OUTPUT=$(git commit -m "$(build_message)" 2>&1 || true)
STAGED_FILES=$(git diff --cached --name-only)

BREADCRUMB_DIR="$REPO_ROOT/.handoff"
mkdir -p "$BREADCRUMB_DIR"
BREADCRUMB="$BREADCRUMB_DIR/auto-commit-blocked-$AGENT_ID.md"

cat > "$BREADCRUMB" <<EOF
# Auto-commit blocked — session $AGENT_ID

**Timestamp:** $TIMESTAMP
**Repo:** $REPO_ROOT
**Reason:** pre-commit hooks refused this commit. Work is staged but uncommitted.

## Pre-commit output

\`\`\`
$PRE_COMMIT_OUTPUT
\`\`\`

## Staged files ($FILES_CHANGED)

\`\`\`
$STAGED_FILES
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

echo "[auto-commit] BLOCKED: pre-commit refused. Breadcrumb: $BREADCRUMB" >&2
exit 1
