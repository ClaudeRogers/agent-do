#!/bin/bash
# SessionStart hook: Add agent-do to PATH, inject tooling reminder,
# load always-active skills, detect frontend projects
#
# Auto-detects agent-do location (no hardcoded paths):
#   1. `which agent-do` (already in PATH)
#   2. ~/.local/bin/agent-do symlink (install.sh creates this)
#   3. ~/.agent-do/install-path breadcrumb file

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // ""')

# --- Resolve agent-do location ---
AGENT_DO_DIR=""

# 1. Already in PATH?
if command -v agent-do &>/dev/null; then
    RESOLVED=$(readlink "$(command -v agent-do)" 2>/dev/null || command -v agent-do)
    AGENT_DO_DIR="$(cd "$(dirname "$RESOLVED")" 2>/dev/null && pwd)"
fi

# 2. Check ~/.local/bin symlink
if [ -z "$AGENT_DO_DIR" ] && [ -L "$HOME/.local/bin/agent-do" ]; then
    RESOLVED=$(readlink "$HOME/.local/bin/agent-do" 2>/dev/null)
    if [ -n "$RESOLVED" ] && [ -x "$RESOLVED" ]; then
        AGENT_DO_DIR="$(cd "$(dirname "$RESOLVED")" 2>/dev/null && pwd)"
    fi
fi

# 3. Check breadcrumb file
if [ -z "$AGENT_DO_DIR" ] && [ -f "$HOME/.agent-do/install-path" ]; then
    BREADCRUMB=$(cat "$HOME/.agent-do/install-path" 2>/dev/null)
    if [ -n "$BREADCRUMB" ] && [ -x "$BREADCRUMB/agent-do" ]; then
        AGENT_DO_DIR="$BREADCRUMB"
    fi
fi

# 4. Script-relative fallback: this hook lives at <repo>/hooks/claude/, so a
#    bare checkout (fresh contributor, CI) resolves its own dispatcher without
#    any install artifacts.
if [ -z "$AGENT_DO_DIR" ]; then
    SCRIPT_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)"
    if [ -n "$SCRIPT_REPO" ] && [ -x "$SCRIPT_REPO/agent-do" ]; then
        AGENT_DO_DIR="$SCRIPT_REPO"
    fi
fi

# --- Add to PATH if found ---
if [ -n "$AGENT_DO_DIR" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
    echo "export PATH=\"$AGENT_DO_DIR:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi

# --- Pin coord + manna identity to this Claude session ---
# Every Bash call then derives the same coord agent identity, and the
# SessionEnd hook can retire exactly that identity via the same session_id.
# Manna gets the same anchor: claims made as the session_id survive pid
# recycling, so reconcile can probe them meaningfully instead of always
# finding a dead transient pid.
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""')
if [ -n "$SESSION_ID" ] && [ -z "${AGENT_DO_COORD_SESSION:-}" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
    echo "export AGENT_DO_COORD_SESSION=\"$SESSION_ID\"" >> "$CLAUDE_ENV_FILE"
fi
if [ -n "$SESSION_ID" ] && [ -z "${MANNA_SESSION_ID:-}" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
    echo "export MANNA_SESSION_ID=\"$SESSION_ID\"" >> "$CLAUDE_ENV_FILE"
fi

run_native_bootstrap_prompt() {
    local ask_prompt="$1"
    local project_root="$2"
    local response

    case "${AGENT_DO_BOOTSTRAP_AUTO_RESPONSE:-}" in
        bootstrap)
            response="Bootstrap"
            ;;
        not_now)
            response="Not now"
            ;;
        *)
            if ! command -v osascript >/dev/null 2>&1; then
                return 2
            fi

            response=$(osascript <<EOF 2>/dev/null || true
display dialog "$(printf '%s' "$ask_prompt" | sed 's/\\/\\\\/g; s/"/\\"/g')" with title "agent-do Bootstrap" buttons {"Not now", "Bootstrap"} default button "Bootstrap"
button returned of result
EOF
)
            ;;
    esac

    if [[ "$response" == "Bootstrap" ]]; then
        # Capture output to a log; emit a macOS notification with status; on
        # failure also fire a follow-up dialog with the option to view the log.
        # The session-start hook fires once per session, so it's fine to grab
        # the user's attention briefly when something actually needs them.
        local log_dir log_file run_exit project_label
        log_dir="${HOME}/.agent-do/logs"
        mkdir -p "$log_dir" 2>/dev/null || true
        log_file="$log_dir/bootstrap-$(date +%Y%m%d-%H%M%S)-$$.log"
        project_label="$(basename "$project_root")"

        (
            cd "$project_root"
            echo "agent-do bootstrap --yes" > "$log_file"
            echo "project: $project_root" >> "$log_file"
            echo "started: $(date '+%Y-%m-%d %H:%M:%S')" >> "$log_file"
            echo "---" >> "$log_file"
            "$AGENT_DO_DIR/agent-do" bootstrap --yes >> "$log_file" 2>&1
        )
        run_exit=$?

        if command -v osascript >/dev/null 2>&1; then
            if [[ "$run_exit" -eq 0 ]]; then
                osascript -e "display notification \"Bootstrap completed for $project_label. Log: $log_file\" with title \"agent-do Bootstrap\" sound name \"Glass\"" 2>/dev/null || true
            else
                osascript -e "display notification \"Bootstrap FAILED for $project_label (exit $run_exit). Log: $log_file\" with title \"agent-do Bootstrap\" sound name \"Basso\"" 2>/dev/null || true
                # On failure also offer to open the log right now.
                local choice
                choice=$(osascript <<DLG 2>/dev/null || true
display dialog "agent-do bootstrap failed (exit $run_exit) for $project_label.

Log: $log_file" with title "agent-do Bootstrap failed" buttons {"Dismiss", "Open log"} default button "Open log"
button returned of result
DLG
)
                if [[ "$choice" == "Open log" ]] && command -v open >/dev/null 2>&1; then
                    open "$log_file" 2>/dev/null || true
                fi
            fi
        else
            # Non-macOS / no osascript: echo status to stderr so it lands in
            # whatever the host shell shows.
            if [[ "$run_exit" -eq 0 ]]; then
                echo "[agent-do bootstrap] completed for $project_label. Log: $log_file" >&2
            else
                echo "[agent-do bootstrap] FAILED for $project_label (exit $run_exit). Log: $log_file" >&2
            fi
        fi
    fi

    return 0
}

append_bootstrap_prompt() {
    local bootstrap_json needs_bootstrap ask_prompt project_root commands prompt_mode

    [ -n "$AGENT_DO_DIR" ] || return 0
    [ -n "$CWD" ] || return 0
    [ -x "$AGENT_DO_DIR/agent-do" ] || return 0

    bootstrap_json=$(bounded_run 3 "$AGENT_DO_DIR/agent-do" bootstrap --recommend --json --cwd "$CWD" 2>/dev/null || true)
    [ -n "$bootstrap_json" ] || return 0

    needs_bootstrap=$(echo "$bootstrap_json" | python3 -c "import json,sys; print('true' if json.load(sys.stdin).get('needs_bootstrap') else 'false')" 2>/dev/null || echo "false")
    [ "$needs_bootstrap" = "true" ] || return 0

    ask_prompt=$(echo "$bootstrap_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('ask_prompt',''))" 2>/dev/null || true)
    project_root=$(echo "$bootstrap_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('project_root',''))" 2>/dev/null || true)
    commands=$(echo "$bootstrap_json" | python3 -c "import json,sys; data=json.load(sys.stdin); [print(cmd) for cmd in data.get('commands', [])]" 2>/dev/null || true)

    prompt_mode="${AGENT_DO_BOOTSTRAP_PROMPT_MODE:-}"
    if [ -z "$prompt_mode" ]; then
        if [ "$(uname -s)" = "Darwin" ] && command -v osascript >/dev/null 2>&1; then
            prompt_mode="native"
        else
            prompt_mode="context"
        fi
    fi

    case "$prompt_mode" in
        native)
            run_native_bootstrap_prompt "$ask_prompt" "$project_root" && return 0
            ;;
        disabled)
            return 0
            ;;
    esac

    CONTEXT="$CONTEXT

---

## Bootstrap Opportunity

This project has pending agent-do bootstrap work.

At the start of your first reply in this session, ask exactly one short yes/no question:
\"$ask_prompt\"

If the user says yes, run:
\`agent-do bootstrap --yes\`

Run it from:
\`$project_root\`

Planned bootstrap:
\`\`\`
$commands
\`\`\`

    If the user says no, continue normally and do not ask again in this session."
}

append_project_tooling() {
    local suggest_json project_root signals tools_block

    [ -n "$AGENT_DO_DIR" ] || return 0
    [ -n "$CWD" ] || return 0
    [ -x "$AGENT_DO_DIR/agent-do" ] || return 0

    suggest_json=$(bounded_run 3 "$AGENT_DO_DIR/agent-do" suggest --project --json --cwd "$CWD" --limit 5 2>/dev/null || true)
    [ -n "$suggest_json" ] || return 0

    project_root=$(echo "$suggest_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('project',''))" 2>/dev/null || true)
    tools_block=$(echo "$suggest_json" | python3 -c "
import json, sys
data = json.load(sys.stdin)
lines = []
for item in data.get('results', []):
    lines.append(f\"- {item.get('tool')}: start with \`{item.get('primary')}\`\")
    readiness = item.get('readiness') or {}
    fix = readiness.get('fix')
    note = readiness.get('note')
    if fix and note:
        lines.append(f\"  setup: \`{fix}\` ({note})\")
print('\\n'.join(lines))
" 2>/dev/null || true)
    signals=$(echo "$suggest_json" | python3 -c "import json,sys; data=json.load(sys.stdin); print(', '.join(data.get('signals', [])))" 2>/dev/null || true)

    [ -n "$tools_block" ] || return 0

    CONTEXT="$CONTEXT

---

## Project-Scoped agent-do Tools

Current project root:
\`$project_root\`

Detected signals:
\`${signals:-general}\`

Top likely agent-do tools for this repo:
$tools_block

Refresh this list any time with:
\`agent-do suggest --project\`"
}

# Run a command with a hard wall-clock bound, SIGKILLing its entire process
# group on expiry so orphaned grandchildren cannot hold pipes open.
bounded_run() {
    perl -e '
        setpgrp(0, 0);
        $SIG{ALRM} = sub { kill KILL => -$$ };
        alarm shift(@ARGV);
        my $pid = fork();
        if (!$pid) { exec @ARGV or exit 127 }
        waitpid($pid, 0);
        exit($? >> 8);
    ' "$@"
}

append_coord_context() {
    local touch_json interrupts_json active_count focus_goal active_block interrupt_count interrupt_block

    [ -n "$AGENT_DO_DIR" ] || return 0
    [ -n "$CWD" ] || return 0
    [ -x "$AGENT_DO_DIR/agent-do" ] || return 0

    # bounded_run kills the whole process group on timeout: a slow or wedged
    # agent-do spawn must degrade to "no coord context", never hold the pipe
    # open and eat the hook's whole timeout budget.
    touch_json=$(cd "$CWD" && bounded_run 2 "$AGENT_DO_DIR/agent-do" coord touch --json 2>/dev/null || true)
    [ -n "$touch_json" ] || return 0

    active_count=$(echo "$touch_json" | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('active_peers', [])))" 2>/dev/null || echo "0")
    focus_goal=$(echo "$touch_json" | python3 -c "import json,sys; data=json.load(sys.stdin); print(((data.get('focus') or {}).get('goal')) or '')" 2>/dev/null || true)

    interrupts_json=$(cd "$CWD" && bounded_run 2 "$AGENT_DO_DIR/agent-do" coord interrupts --json --mark-seen --limit 5 2>/dev/null || true)
    interrupt_count=$(echo "$interrupts_json" | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('interrupts', [])))" 2>/dev/null || echo "0")

    if [ "$interrupt_count" -gt 0 ]; then
        interrupt_block=$(echo "$interrupts_json" | python3 -c "
import json, sys
data = json.load(sys.stdin)
lines = []
for item in data.get('interrupts', []):
    prefix = '[new] ' if item.get('new') else ''
    lines.append(f'- {prefix}{item.get(\"kind\")}: {item.get(\"summary\")}')
print('\n'.join(lines))
" 2>/dev/null || true)

        [ -n "$interrupt_block" ] || return 0

        CONTEXT="$CONTEXT

---

## Coord Interrupts

Relevant coordination interrupts are active in this repo:
$interrupt_block

Use:
\`agent-do coord status\`
\`agent-do coord interrupts\`
\`agent-do coord focus show\`
"
        return 0
    fi

    [ "$active_count" -gt 0 ] || return 0
    [ -z "$focus_goal" ] || return 0

    active_block=$(echo "$touch_json" | python3 -c "
import json, sys
data = json.load(sys.stdin)
peers = data.get('active_peers', [])
peers.sort(key=lambda item: 0 if (item.get('mode') or 'writer') == 'writer' else 1)
lines = []
for peer in peers:
    label = peer.get('alias') or peer.get('agent_id')
    focus = peer.get('focus') or {}
    details = []
    if (peer.get('mode') or 'writer') == 'read-only':
        details.append(f\"{peer.get('role') or 'auditor'}, read-only\")
    if peer.get('phase'):
        details.append(f\"phase:{peer['phase']}\")
    if peer.get('age'):
        details.append(peer['age'])
    suffix = f\" ({', '.join(details)})\" if details else ''
    goal = f\" goal: {focus.get('goal')}\" if focus.get('goal') else ''
    lines.append(f'- {label}{suffix}{goal}')
counts = data.get('peer_counts') or {}
hidden = int(counts.get('dead', 0)) + int(counts.get('stopped', 0)) + int(counts.get('stale', 0))
if hidden:
    lines.append(f'- ({hidden} dead/stopped/stale sessions on the board, not shown)')
print('\n'.join(lines))
" 2>/dev/null || true)

    [ -n "$active_block" ] || return 0

    CONTEXT="$CONTEXT

---

## Coord Focus Reminder

Other active peers exist in this repo, and you have not declared focus yet.

Active peers:
$active_block

Set focus before overlapping work starts:
\`agent-do coord focus set \"<goal>\" --path <path> [--path <path> ...]\`
\`agent-do coord peers\`
\`agent-do coord claim <path>\`
\`agent-do coord interrupts\`
"
}

append_manna_board() {
    local board_json board_block drift_file drift_block

    [ -n "$AGENT_DO_DIR" ] || return 0
    [ -n "$CWD" ] || return 0
    [ -x "$AGENT_DO_DIR/agent-do" ] || return 0
    # Board presence gates everything below: repos without .manna/ take none
    # of this path, so the emitted envelope stays byte-identical to today.
    [ -d "$CWD/.manna" ] || return 0

    board_json=$(cd "$CWD" && bounded_run 2 "$AGENT_DO_DIR/agent-do" manna context --max-tokens 1500 --json 2>/dev/null || true)
    if [ -n "$board_json" ]; then
        board_block=$(echo "$board_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('context',''))" 2>/dev/null || true)
        if [ -n "$board_block" ]; then
            CONTEXT="$CONTEXT

---

## Manna Board

$board_block

Work the board: \`agent-do manna claim <id>\` before starting, \`agent-do manna done <id>\` when verified."
        fi
    fi

    # Drift greeting: the SessionEnd reconcile advisory writes .manna/drift.yaml;
    # read-if-exists, so a hand-written file greets before that ever ships.
    drift_file="$CWD/.manna/drift.yaml"
    [ -f "$drift_file" ] || return 0
    grep -q '^findings:' "$drift_file" 2>/dev/null || return 0
    grep -Eq '^[[:space:]]*-[[:space:]]+kind:' "$drift_file" 2>/dev/null || return 0

    drift_block=$(sed -n '1,30p' "$drift_file" 2>/dev/null)
    [ -n "$drift_block" ] || return 0

    CONTEXT="$CONTEXT

---

## Board drift (unresolved from last session)

\`\`\`yaml
$drift_block
\`\`\`

Reconcile the board against reality before claiming new work, then remove \`.manna/drift.yaml\` once resolved."
}

# At least one recorded line under .zpc/memory/. An initialized-but-empty store
# has nothing worth embedding, so it keeps the advisory.
zpc_has_records() {
    local file
    for file in "$1"/.zpc/memory/*.jsonl; do
        [ -f "$file" ] || continue
        grep -q '[^[:space:]]' "$file" 2>/dev/null && return 0
    done
    return 1
}

# Mark where this session started, for the Stop-event write nudge
# (agent-do-zpc-write-nudge.sh) to measure against. Two facts plus one clock:
# HEAD at the mark, recorded rows at the mark, and the file's own mtime, which
# is what lets the nudge tell this session's edits from dirt that was already
# in the tree. Written here rather than lazily at the first Stop so that work
# done in the opening turn still counts.
zpc_write_session_baseline() {
    local state_dir baseline total n f
    [ -n "$CWD" ] || return 0
    [ -d "$CWD/.zpc" ] || return 0
    [ -n "$SESSION_ID" ] || return 0

    state_dir="$CWD/.zpc/.state"
    mkdir -p "$state_dir" 2>/dev/null || return 0

    # One marker pair per session accumulates forever otherwise. Session-start
    # is the once-per-session place to sweep it.
    find "$state_dir" -maxdepth 1 -type f \
        \( -name 'session-*.baseline' -o -name 'write-nudge-*.done' \) \
        -mtime +7 -delete 2>/dev/null

    baseline="$state_dir/session-$(printf '%s' "$SESSION_ID" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-64).baseline"
    # SessionStart fires again on resume and compact with the same session_id.
    # Keeping the first mark keeps the clock honest.
    [ -f "$baseline" ] && return 0

    total=0
    for f in "$CWD"/.zpc/memory/*.jsonl; do
        [ -f "$f" ] || continue
        n=$(wc -l < "$f" 2>/dev/null | tr -d '[:space:]')
        case "$n" in
            ''|*[!0-9]*) continue ;;
        esac
        total=$((total + n))
    done

    {
        printf 'head=%s\n' "$(cd "$CWD" && git rev-parse HEAD 2>/dev/null || printf '')"
        printf 'zpc_lines=%s\n' "$total"
    } > "$baseline" 2>/dev/null || return 0
}

append_zpc_memory() {
    local inject_out inject_rc

    [ -n "$CWD" ] || return 0
    [ -d "$CWD/.zpc" ] || return 0

    # The advisory below only *asks* the agent to go read the store, and asking
    # is not a mechanism. When there are records to show, put the memory itself
    # in context. Every failure mode (kill-switch, empty store, missing
    # dispatcher, nonzero exit, timeout) falls through to the advisory, so the
    # section degrades instead of disappearing.
    if [ "${AGENT_DO_ZPC_INJECT:-1}" != "0" ] &&
       [ -n "$AGENT_DO_DIR" ] &&
       [ -x "$AGENT_DO_DIR/agent-do" ] &&
       zpc_has_records "$CWD"; then
        # cwd must be inside the project: inject resolves the store from there.
        # AGENT_DO_ZPC_SOURCE tags the access log; the export dies with the
        # subshell so it never leaks into the rest of the hook.
        inject_out=$(cd "$CWD" && export AGENT_DO_ZPC_SOURCE=hook && bounded_run 3 "$AGENT_DO_DIR/agent-do" zpc inject 2>/dev/null)
        inject_rc=$?

        if [ "$inject_rc" -eq 0 ] && [ -n "$inject_out" ]; then
            if [ ${#inject_out} -gt 6000 ]; then
                inject_out="${inject_out:0:6000}"
                # Back up to the last complete line: a cut landing mid-character
                # would hand jq -Rs invalid UTF-8 and cost the whole envelope.
                inject_out="${inject_out%$'\n'*}"
                inject_out="$inject_out
[zpc inject truncated]"
            fi

            CONTEXT="$CONTEXT

---

## ZPC Project Memory

This project's recorded memory, loaded below. Read it before coding; it is already in context, so do not re-run \`agent-do zpc inject\`.

$inject_out

Keep the loop closed: \`agent-do zpc learn\` and \`agent-do zpc decide\` as you work, \`agent-do zpc harvest\` after significant work."
            return 0
        fi
    fi

    CONTEXT="$CONTEXT

---

## ZPC Memory Available

This project has ZPC memory at \`.zpc/\`. At session start:
\`\`\`
agent-do zpc status      # Memory health + counts
agent-do zpc patterns    # Established conventions — read before coding
\`\`\`
Log lessons and decisions as you work. Run \`agent-do zpc harvest\` after significant work."
}

# --- Inject tooling reminder ---
CONTEXT="## TOOLING REMINDER - agent-do

BEFORE using raw commands (xcrun, adb, osascript, curl for APIs, etc.), CHECK if agent-do has a tool:

\`\`\`
agent-do <tool> <command> [args...]
agent-do -n \"natural language description of what you want\"
agent-do --how \"...\"     # Explain without executing
\`\`\`

Discovery: agent-do suggest \"<task>\" | agent-do suggest --project | agent-do find <keyword> | agent-do --list | agent-do <tool> --help

Prefer agent-do over raw CLI commands when a tool exists.
Use agent-do <tool> --help to see available commands."

# --- Load always-active skill: artful-claude ---
SKILL_FILE="$HOME/.claude/skills/artful-claude/SKILL.md"
if [ -f "$SKILL_FILE" ]; then
    SKILL_CONTENT=$(cat "$SKILL_FILE")
    CONTEXT="$CONTEXT

---

## ALWAYS-ACTIVE SKILL: artful-claude (MANDATORY)

The following skill governs ALL output — terminal, files, docs, conversation. Apply on every turn without exception.

$SKILL_CONTENT"
fi

# --- Detect frontend project → inject design toolkit ---
IS_FRONTEND=false

if [ -n "$CWD" ]; then
    # Check root package.json for frontend frameworks
    if [ -f "$CWD/package.json" ]; then
        if grep -qE '"(react|next|vue|nuxt|svelte|astro|angular|remix|gatsby|solid-js)"' "$CWD/package.json" 2>/dev/null; then
            IS_FRONTEND=true
        fi
    fi

    # Check monorepo subdirs (apps/*, packages/*)
    if [ "$IS_FRONTEND" = false ]; then
        for subdir in "$CWD"/apps/*/package.json "$CWD"/packages/*/package.json; do
            [ -f "$subdir" ] || continue
            if grep -qE '"(react|next|vue|nuxt|svelte|astro|angular|remix|gatsby|solid-js)"' "$subdir" 2>/dev/null; then
                IS_FRONTEND=true
                break
            fi
        done
    fi

    # Check for frontend file extensions in src/ or app/
    if [ "$IS_FRONTEND" = false ]; then
        for dir in "$CWD/src" "$CWD/app" "$CWD/apps"; do
            [ -d "$dir" ] || continue
            if find "$dir" -maxdepth 4 -name '*.tsx' -o -name '*.jsx' -o -name '*.vue' -o -name '*.svelte' 2>/dev/null | head -1 | grep -q .; then
                IS_FRONTEND=true
                break
            fi
        done
    fi

    # Check for Flutter/Dart (also has UI)
    if [ "$IS_FRONTEND" = false ] && [ -f "$CWD/pubspec.yaml" ]; then
        if grep -q 'flutter' "$CWD/pubspec.yaml" 2>/dev/null; then
            IS_FRONTEND=true
        fi
    fi
fi

if [ "$IS_FRONTEND" = true ]; then
    CONTEXT="$CONTEXT

---

## FRONTEND PROJECT DETECTED — Design Toolkit Active

This is a frontend project. When doing ANY visual/UI work, you MUST:

### 1. Load Design Skills
Read and apply these skills for all UI work:
- \`~/.claude/skills/artful-ux/SKILL.md\` — layout, hierarchy, interaction, spacing, anti-patterns
- \`~/.claude/skills/artful-colors/SKILL.md\` — color perception, palette, cultural context
- \`~/.claude/skills/artful-typography/SKILL.md\` — typeface selection, hierarchy, responsive type

### 2. Use Browser Verification (MANDATORY)
Never edit UI code without visual verification:
\`\`\`
agent-do browse open <dev-url>
agent-do browse screenshot /tmp/before.png   # visual truth — view with Read tool
agent-do browse snapshot -i                  # structural inventory
\`\`\`

Workflow: baseline screenshot → code → reload → screenshot → Quick-5 → fix → confirm.

### 3. Score with DPT
After visual changes, score the result:
\`\`\`
agent-do dpt score /tmp/after.png            # 0-100 with per-layer breakdown
\`\`\`

Screenshots for evaluation. Snapshots for inventory. Both, in that order."
fi

# --- Detect ZPC project → embed memory (advisory fallback) ---
zpc_write_session_baseline
append_zpc_memory

append_project_tooling
append_bootstrap_prompt
append_coord_context
append_manna_board

ESCAPED=$(echo "$CONTEXT" | jq -Rs .)
echo "{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":$ESCAPED}}"
exit 0
