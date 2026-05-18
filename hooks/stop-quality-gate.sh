#!/bin/bash
# Stop hook: Auto-commit + notifications when agent finishes
#
# With 42+ agents, each agent's work becomes its own atomic commit.
# No mixing of work across agents.

# --- AUTO-COMMIT: Atomic commits per agent session ---
~/.claude/hooks/auto-commit.sh 2>/dev/null || true

# --- DESKTOP NOTIFICATION ---
if command -v osascript &>/dev/null; then
    osascript -e 'display notification "Claude has finished responding" with title "Claude Code" sound name "Glass"' 2>/dev/null &
fi

exit 0
