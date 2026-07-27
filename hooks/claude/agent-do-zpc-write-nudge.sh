#!/bin/bash
# Stop hook: notice when a .zpc project's code moved but its memory did not.
#
# The read side of project memory closed mechanically (SessionStart embeds
# `zpc inject`). The write side still depends on the model choosing to run
# `zpc learn` / `zpc decide` / `zpc position add`. This hook supplies the
# missing machine-detected condition: tracked files changed during this
# session, nothing was appended under .zpc/memory/, so say so once.
#
# DELIVERY, and why the default targets the user and not the model:
#   Claude Code's Stop event has no non-blocking way to show text to the model.
#   Per the hooks docs, hookSpecificOutput.additionalContext on Stop "keeps the
#   conversation going through the same loop protections as decision: block"
#   (the 8-continuation cap and the stop_hook_active flag); it differs from
#   block only in how the transcript labels it. Once a turn ends there is no
#   next model request in which to read a reminder, so model-visible and
#   turn-ending are mutually exclusive here.
#   `systemMessage` is the one Stop output that is visible and truly changes
#   nothing: the user sees it, the turn ends. It is available here as the
#   opt-out, not the default.
#
#   The default spends the continuation. That cost is accepted deliberately:
#   a reminder the model never reads does not close the write side, it only
#   moves the obligation to the human. The guards below bound the cost to at
#   most one extra turn per session.
#
# AGENT_DO_ZPC_WRITE_NUDGE:
#   unset | continue | 1   hookSpecificOutput.additionalContext — the model
#                          sees the nudge and spends its one guarded
#                          continuation writing the record (default). `1` and
#                          `continue` are kept as aliases so settings written
#                          against the earlier semantics keep working.
#   user                   systemMessage — the user sees the nudge, the turn
#                          ends, nothing is gated. The opt-out for anyone who
#                          wants the signal without the continuation.
#   0                      off entirely
#
#   Any unrecognized value falls through to the default rather than going
#   silent: a typo should not quietly disable the write side.
#
# Never blocks, never emits decision:"block", never exits nonzero. Every
# failure path is a silent exit 0.

MODE="${AGENT_DO_ZPC_WRITE_NUDGE:-continue}"
[ "$MODE" = "0" ] && exit 0

command -v jq >/dev/null 2>&1 || exit 0
command -v git >/dev/null 2>&1 || exit 0

INPUT=$(cat 2>/dev/null || true)
CWD=$(echo "$INPUT" | jq -r '.cwd // ""' 2>/dev/null)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""' 2>/dev/null)
STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)

# Re-entrancy: in continue mode this hook's own nudge brings us back here.
# The cooldown marker already covers it; this is the documented second guard.
[ "$STOP_ACTIVE" = "true" ] && exit 0

[ -n "$CWD" ] || CWD="$PWD"
cd "$CWD" 2>/dev/null || exit 0
[ -d .zpc ] || exit 0

# .zpc/ is gitignored (except team/), so markers here never dirty the tree.
STATE_DIR=".zpc/.state"
mkdir -p "$STATE_DIR" 2>/dev/null || exit 0

# A session id is a UUID, but it arrives from outside: never let it name a path.
SAFE_ID=$(printf '%s' "${SESSION_ID:-unknown}" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-64)
BASELINE="$STATE_DIR/session-$SAFE_ID.baseline"
COOLDOWN="$STATE_DIR/write-nudge-$SAFE_ID.done"

# One nudge per session, checked before any work.
[ -e "$COOLDOWN" ] && exit 0

# Total recorded rows across every memory stream. Counting the whole directory
# rather than naming lessons.jsonl and decisions.jsonl means positions.jsonl —
# and anything zpc adds later — counts as a write without touching this hook.
zpc_line_count() {
    local total=0 n f
    for f in .zpc/memory/*.jsonl; do
        [ -f "$f" ] || continue
        n=$(wc -l < "$f" 2>/dev/null | tr -d '[:space:]')
        case "$n" in
            ''|*[!0-9]*) continue ;;
        esac
        total=$((total + n))
    done
    printf '%s' "$total"
}

HEAD_NOW=$(git rev-parse HEAD 2>/dev/null || printf '')

# First Stop of a session with no baseline (hook installed mid-session, or a
# SessionStart that predates it): record the mark and stay silent. A nudge
# without a baseline would be a guess, and the file's own mtime is the clock
# every later comparison reads.
if [ ! -f "$BASELINE" ]; then
    {
        printf 'head=%s\n' "$HEAD_NOW"
        printf 'zpc_lines=%s\n' "$(zpc_line_count)"
    } > "$BASELINE" 2>/dev/null || exit 0
    exit 0
fi

BASE_HEAD=$(sed -n 's/^head=//p' "$BASELINE" 2>/dev/null | head -1)
BASE_LINES=$(sed -n 's/^zpc_lines=//p' "$BASELINE" 2>/dev/null | head -1)
case "$BASE_LINES" in
    ''|*[!0-9]*) exit 0 ;;
esac

# Memory grew: the loop is closed, nothing to say.
NOW_LINES=$(zpc_line_count)
[ "$NOW_LINES" -gt "$BASE_LINES" ] 2>/dev/null && exit 0

# Did this session move code? Two independent signals, either one counts:
#   1. HEAD moved — work was committed, so the tree may read clean now.
#   2. A tracked file differs from HEAD *and* was touched after the baseline
#      file was written. The mtime test is what separates this session's work
#      from dirt that was already sitting in the tree at session start, and
#      comparing against the baseline file itself keeps it to a POSIX -nt with
#      no unportable stat(1) formats.
CHANGED=0
CHANGED_SAMPLE=""

if [ -n "$HEAD_NOW" ] && [ -n "$BASE_HEAD" ] && [ "$HEAD_NOW" != "$BASE_HEAD" ]; then
    CHANGED=1
    CHANGED_SAMPLE="committed work"
fi

if [ "$CHANGED" -eq 0 ]; then
    while IFS= read -r -d '' path; do
        [ -n "$path" ] || continue
        # Bookkeeping surfaces are not the source this nudge is about.
        case "$path" in
            .zpc/*|.manna/*|.handoff/*|.dev/*) continue ;;
        esac
        [ -e "$path" ] || continue
        if [ "$path" -nt "$BASELINE" ]; then
            CHANGED=1
            CHANGED_SAMPLE="$path"
            break
        fi
    done < <(git diff --name-only -z --no-renames HEAD 2>/dev/null)
fi

[ "$CHANGED" -eq 1 ] || exit 0

# Claim the cooldown before emitting: if anything below fails, the session has
# still had its one shot and cannot loop.
: > "$COOLDOWN" 2>/dev/null || exit 0

# Stated as facts, not as instructions to the model. The hooks docs warn that
# text framed as out-of-band system commands trips Claude's prompt-injection
# defenses, which surfaces the nudge to the user as suspicious text instead of
# reading it as context. Every command below is real; every flag is required.
READ_MSG="This session changed tracked files (${CHANGED_SAMPLE}) and appended nothing to .zpc/memory — no lesson, no decision, no position. The write side of project memory:
  agent-do zpc learn \"<context>\" \"<problem>\" \"<solution>\" \"<takeaway>\" --tags \"t1,t2\"
  agent-do zpc decide \"<problem>\" --options \"a,b\" --chosen a --rationale \"why\"
  agent-do zpc position add \"<claim>\" --verdict \"<v>\" --confidence low|med|high --falsifier \"<what would change it>\"
A session with nothing worth recording is a real outcome. This fires once per session; AGENT_DO_ZPC_WRITE_NUDGE=0 turns it off."

if [ "$MODE" = "user" ]; then
    jq -nc --arg m "zpc: $READ_MSG" '{systemMessage: $m}' 2>/dev/null
else
    jq -nc --arg m "$READ_MSG" \
        '{hookSpecificOutput: {hookEventName: "Stop", additionalContext: $m}}' 2>/dev/null
fi

exit 0
