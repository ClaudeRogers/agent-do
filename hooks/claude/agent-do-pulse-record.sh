#!/bin/bash
# Pulse hook: forward one Claude Code hook payload (stdin JSON) into coord's
# per-session pulse telemetry. Registered on UserPromptSubmit, PreToolUse,
# PostToolUse, Notification, Stop, StopFailure, and SessionEnd.
# Telemetry only and silent by contract: exit 0 always, print nothing, and
# record only in projects that already run coord — this hook never creates a
# board where none exists. (Concept from Warp's hook-fed agent status surface;
# see .dev/warp-recon-2026-08-22 in the agent-do repo.)

INPUT=$(cat 2>/dev/null || true)
[ -n "$INPUT" ] || exit 0

CWD=$(echo "$INPUT" | jq -r '.cwd // ""' 2>/dev/null)
[ -n "$CWD" ] || CWD="$PWD"
cd "$CWD" 2>/dev/null || exit 0

# Only projects that already use coord get pulse rows (same restraint as the
# SessionEnd coord-stop hook). Global-fallback stores stay untouched.
GIT_DIR=$(git rev-parse --git-dir 2>/dev/null || true)
[ -n "$GIT_DIR" ] && [ -d "$GIT_DIR/agent-do/coord" ] || exit 0

# Resolve agent-do (same chain as agent-do-coord-stop.sh, condensed).
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

# Background with a hard bound: a pulse write must never add latency to the
# session's hook chain, and a wedged spawn must never linger. The tool itself
# also guarantees exit 0 with empty output in --from-hook mode.
(
    printf '%s' "$INPUT" | perl -e '
        setpgrp(0, 0);
        $SIG{ALRM} = sub { kill KILL => -$$ };
        alarm shift(@ARGV);
        my $pid = fork();
        if (!$pid) { exec @ARGV or exit 127 }
        waitpid($pid, 0);
        exit($? >> 8);
    ' 5 "$AGENT_DO" coord pulse record --from-hook >/dev/null 2>&1
) &
disown 2>/dev/null || true
exit 0
