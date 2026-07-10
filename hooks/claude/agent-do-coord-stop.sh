#!/bin/bash
# SessionEnd hook: retire this session's coord presence cleanly.
# Advisory and silent — never blocks, never creates a board where none exists.

INPUT=$(cat 2>/dev/null || true)
CWD=$(echo "$INPUT" | jq -r '.cwd // ""' 2>/dev/null)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""' 2>/dev/null)
[ -n "$CWD" ] || CWD="$PWD"
cd "$CWD" 2>/dev/null || exit 0

# Only retire in projects that already use coord.
GIT_DIR=$(git rev-parse --git-dir 2>/dev/null) || exit 0
[ -d "$GIT_DIR/agent-do/coord" ] || exit 0

# Resolve agent-do (same chain as agent-do-session-start.sh, condensed).
AGENT_DO=""
if command -v agent-do &>/dev/null; then
    AGENT_DO="agent-do"
fi
if [ -z "$AGENT_DO" ] && [ -f "$HOME/.agent-do/install-path" ]; then
    REPO=$(cat "$HOME/.agent-do/install-path" 2>/dev/null)
    [ -n "$REPO" ] && [ -x "$REPO/agent-do" ] && AGENT_DO="$REPO/agent-do"
fi
if [ -z "$AGENT_DO" ]; then
    SCRIPT_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)"
    [ -n "$SCRIPT_REPO" ] && [ -x "$SCRIPT_REPO/agent-do" ] && AGENT_DO="$SCRIPT_REPO/agent-do"
fi
[ -n "$AGENT_DO" ] || exit 0

# Retire the same identity the session used (session-start pinned it via
# AGENT_DO_COORD_SESSION in CLAUDE_ENV_FILE from the same session_id).
[ -n "$SESSION_ID" ] && export AGENT_DO_COORD_SESSION="$SESSION_ID"

"$AGENT_DO" coord stop --note "session ended" >/dev/null 2>&1
exit 0
