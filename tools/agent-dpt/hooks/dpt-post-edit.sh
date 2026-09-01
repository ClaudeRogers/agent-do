#!/usr/bin/env bash
# DPT PostToolUse hook — design quality feedback after CSS/HTML/JSX edits
# Two modes:
#   1. Browse session active → wait for HMR → inject engine → return score
#   2. No browse session → WARN that design files are being edited blind

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(printf '%s' "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('file_path', ''))
except: print('')
" 2>/dev/null)

[[ -z "$FILE_PATH" ]] && exit 0

# Is this edit design work? Same rules as hooks/codex/stop-quality-gate.py:
#   - tests and tooling configs are never UI, whatever their name contains
#   - a UI extension is UI
#   - otherwise the basename's stem must BE a design-system name (theme,
#     tokens, design-tokens, design-system) or start with one followed by
#     "." or "-". Substring matching was the bug: "*global*" flagged
#     test_global_hooks_nonblocking.py as a design file.
#
# Document/data trees (.handoff/, .dev/, docs/, fixtures/) are tracked
# separately: they suppress the no-session WARNING below — "open the app"
# is unfollowable for an archived text — but never the SCORING path. A
# fixture page open in the live browser with a baseline is being iterated
# on deliberately, and its edits deserve their score.
IS_DESIGN=false
IN_DOC_TREE=false
BASENAME="${FILE_PATH##*/}"
STEM="${BASENAME%.*}"
STEM_HEAD="${STEM%%[.-]*}"
case "$FILE_PATH" in
    */.handoff/*|*/.dev/*|*/docs/*|*/fixtures/*) IN_DOC_TREE=true ;;
esac
case "$BASENAME" in
    test_*|*_test.py|*.test.*|*.spec.*|*.config.*|tailwind.*|postcss.*|vite.*|*.d.ts) ;;
    *.css|*.scss|*.less|*.html|*.htm|*.jsx|*.tsx|*.vue|*.svelte|*.astro) IS_DESIGN=true ;;
    *)
        case "$STEM" in
            theme|tokens|design-tokens|design-system) IS_DESIGN=true ;;
            *)
                case "$STEM_HEAD" in
                    theme|tokens|design-tokens|design-system) IS_DESIGN=true ;;
                esac
                ;;
        esac
        ;;
esac

[[ "$IS_DESIGN" == false ]] && exit 0

# Check the current agent-scoped browse session. Do not grab the first socket on
# disk; that can belong to another agent or a stale daemon.
BROWSE_STATUS="$(agent-do browse status --json 2>/dev/null || true)"
BROWSE_READY="$(python3 -c "
import json, sys
try:
    data = json.loads(sys.argv[1])
    print('1' if data.get('daemon', {}).get('running') and data.get('browser', {}).get('responsive') else '0')
except Exception:
    print('0')
" "$BROWSE_STATUS")"

# === MODE 2: No browse session — WARN LOUDLY ===
if [[ "$BROWSE_READY" != "1" ]]; then
    python3 -c "
import json
msg = 'WARNING: You are editing design files WITHOUT a browser session. '
msg += 'DPT cannot score your changes. You are flying blind. '
msg += 'REQUIRED: Run \`agent-do browse open <dev-url>\` NOW, then \`agent-do dpt baseline\` before making more changes. '
msg += 'Do NOT continue editing design files without visual verification.'
output = {'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': msg}}
print(json.dumps(output))
"
    exit 0
fi

# === MODE 1: Browse session active — score and report ===
# The canonical score command first proves that this browser session has a
# baseline for the edited project and that the open page still matches it. It
# waits for HMR only after that proof, so unrelated pages are neither delayed
# nor misattributed as feedback on this edit.
SCORE_OUTPUT="$(agent-do dpt score --current --quiet --for-file "$FILE_PATH" 2>/dev/null || true)"

if [[ -n "$SCORE_OUTPUT" ]]; then
    python3 -c "
import json, sys
output = {'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': sys.argv[1]}}
print(json.dumps(output))
" "$SCORE_OUTPUT"
fi
