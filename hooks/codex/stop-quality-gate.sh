#!/bin/bash
# Stop hook: advisory quality report + auto-commit + notification when Codex finishes
#
# Normal workflow hooks must not block. Missing verification is surfaced as
# context; auto-commit and notification should still run.

set -euo pipefail

INPUT=$(cat)
RESULT=$(printf '%s' "$INPUT" | python3 ~/.codex/hooks/stop-quality-gate.py)

~/.codex/hooks/auto-commit.sh 2>/dev/null || true

printf '%s\n' "$RESULT"

exit 0
