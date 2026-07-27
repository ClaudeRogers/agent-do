#!/usr/bin/env bash
# lib/counsel.sh — Clean-context second opinion: a fresh model that sees the
# receipts and nothing else.
# Sourced by agent-zpc. Do not run directly.

ZPC_COUNSEL_TIMEOUT_DEFAULT=300

_counsel_help() {
    cat << 'EOF'
Usage: agent-zpc counsel --brief <file> [--question "<q>"] [--position <id>]

Spawns a fresh model whose entire input is your brief plus your question.
It sees no conversation, no .zpc memory, no repository, and no prior verdict:
an agent that has been arguing a position for an hour cannot un-see that hour,
so this instantiates a judge who never saw it.

  --brief <file>       Required. Receipts only, by convention (see below).
  --question "<q>"     What you want ruled on. Defaults to a plain verdict.
  --position <id>      Print your stored position beside the fresh verdict.
  --timeout <seconds>  Give up on the subprocess (default 300).

BRIEF FORMAT (convention, not enforced): fenced blocks of raw evidence —
command output, file quotes with paths, error text, diffs. No summaries of
what you think it means, no "obviously", no naming who believes what. A
characterization in the brief is the framing you were trying to escape.

RESIDUAL RISK, unsolved and worth stating: this cleans the *context*, not the
*sample*. Which receipts you paste is itself a judgment, and a brief built
from evidence you selected can smuggle the framing back in through omission.
The fresh verdict is a second sample, not an oracle. If it matters, put the
receipts in that you expect to weaken your own case.

Isolation: the subprocess runs with project and user customization disabled,
with all tools disabled (it cannot read a file you did not paste), with no
session persistence, and from a scratch directory. The model is unpinned; it
inherits the CLI default.

Examples:
  agent-zpc counsel --brief .dev/proxy-receipts.md \
      --question "Does the payload survive the hop unchanged?"
  agent-zpc counsel --brief /tmp/brief.md --position pos-1a2b3c
EOF
}

_counsel_system_prompt() {
    cat << 'EOF'
You are a clean-context second opinion. You have no history with this problem,
no relationship with whoever wrote the brief, and no stake in any prior verdict.

You are given a BRIEF made of receipts (command output, file quotes, error
text) and a QUESTION. Reason only from that material.

Answer in four parts:
1. VERDICT — one committed sentence. If it genuinely depends, say what on.
2. CONFIDENCE — low, med, or high, and why that level and not the next one.
3. FALSIFIER — the specific evidence that would change your verdict.
4. MISSING — any receipt you needed and did not get. Name it plainly instead
   of filling the gap with assumption.

Do not infer what the asker hopes to hear, and do not manufacture disagreement
to look independent. If the receipts settle the question, say so and stop.
EOF
}

cmd_counsel() {
    local brief="" question="" position_id="" timeout="$ZPC_COUNSEL_TIMEOUT_DEFAULT"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --brief|-b) brief="${2:-}"; shift 2 ;;
            --question|-q) question="${2:-}"; shift 2 ;;
            --position|-p) position_id="${2:-}"; shift 2 ;;
            --timeout) timeout="${2:-}"; shift 2 ;;
            --help|-h) _counsel_help; return 0 ;;
            *) shift ;;
        esac
    done

    ensure_zpc

    [[ -n "$brief" ]] || die "Usage: agent-zpc counsel --brief <file> [--question \"...\"] [--position <id>]"
    [[ -f "$brief" ]] || die "Brief not found: $brief"
    [[ -s "$brief" ]] || die "Brief is empty: $brief — counsel with no receipts is just a guess."
    [[ "$timeout" =~ ^[0-9]+$ ]] || die "--timeout takes seconds (got: $timeout)"
    command -v claude >/dev/null 2>&1 || die "counsel needs the 'claude' CLI on PATH."

    # Existence check only, so a mistyped id costs nothing instead of a model
    # call whose verdict then has nowhere to go. The row stays unread until
    # after the verdict is in hand.
    if [[ -n "$position_id" ]]; then
        _position_lookup "$(_position_file)" "$position_id" >/dev/null \
            || die "No position with id '$position_id'. Run 'agent-zpc position list'."
    fi

    log_access "counsel"

    [[ -n "$question" ]] || question="What is your verdict on the material above?"

    # Everything the subprocess will ever see, assembled before we leave this
    # directory. Nothing else is read on this path — not .zpc, not the repo.
    local prompt
    prompt="--- BRIEF (receipts) ---
$(cat "$brief")

--- QUESTION ---
$question"

    local work_dir
    work_dir="$(mktemp -d)" || die "Could not create a scratch directory for the subprocess."

    printf '%s\n' "$prompt" > "$work_dir/prompt.txt"

    local previous_dir="$PWD"
    cd "$work_dir" || die "Could not enter scratch directory $work_dir"

    # --safe-mode drops CLAUDE.md, skills, hooks, plugins and MCP; --tools ""
    # leaves the judge no way to read anything the brief did not contain;
    # --no-session-persistence keeps this run from becoming anyone's history.
    # The model stays unpinned on purpose: counsel inherits the CLI default.
    claude -p --safe-mode --tools "" --no-session-persistence \
        --system-prompt "$(_counsel_system_prompt)" \
        < "$work_dir/prompt.txt" > "$work_dir/verdict.txt" 2> "$work_dir/stderr.txt" &
    local counsel_pid=$!

    (
        sleep "$timeout"
        kill -TERM "$counsel_pid" 2>/dev/null && touch "$work_dir/timed-out"
    ) >/dev/null 2>&1 &
    local watchdog_pid=$!

    local status=0
    wait "$counsel_pid" || status=$?
    kill "$watchdog_pid" 2>/dev/null || true
    wait "$watchdog_pid" 2>/dev/null || true

    cd "$previous_dir" || true

    if [[ -f "$work_dir/timed-out" ]]; then
        rm -rf "$work_dir"
        die "counsel timed out after ${timeout}s. Raise it with --timeout or shorten the brief."
    fi

    local verdict stderr_text
    verdict="$(cat "$work_dir/verdict.txt" 2>/dev/null || true)"
    stderr_text="$(cat "$work_dir/stderr.txt" 2>/dev/null || true)"
    rm -rf "$work_dir"

    if [[ "$status" -ne 0 || -z "$verdict" ]]; then
        die "counsel subprocess failed (exit $status): ${stderr_text:-no output}"
    fi

    # The stored position is read only here, after the verdict is in hand, and
    # never enters the prompt above. That ordering is what makes the fresh
    # verdict independent rather than a mirror of the one it is compared to.
    local position_row=""
    if [[ -n "$position_id" ]]; then
        position_row=$(_position_lookup "$(_position_file)" "$position_id") \
            || die "Position '$position_id' vanished mid-run. The verdict above still stands on its own."
    fi

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        python3 << 'PYTHON' - "$verdict" "$brief" "$question" "$position_row"
import json, sys

verdict, brief, question, position_raw = sys.argv[1:5]
payload = {
    "verdict": verdict,
    "brief": brief,
    "question": question,
    "position": json.loads(position_raw) if position_raw else None,
}
print(json.dumps({"success": True, "result": payload}, ensure_ascii=False, indent=2))
PYTHON
        return 0
    fi

    echo "--- Fresh verdict (context: this brief and this question only) ---"
    printf '%s\n' "$verdict"

    if [[ -n "$position_row" ]]; then
        echo
        echo "--- Divergence check ---"
        python3 << 'PYTHON' - "$position_row"
import json, sys

p = json.loads(sys.argv[1])
print(f"Your standing position {p.get('id', '?')} (confidence: {p.get('confidence', '')})")
print(f"  claim:     {p.get('claim', '')}")
print(f"  verdict:   {p.get('verdict', '')}")
print(f"  falsifier: {p.get('falsifier', '')}")
print()
print("The verdict above never saw this position, and nothing here scores the")
print("agreement for you. If they diverge, the flip needs named evidence:")
print(f"  agent-zpc position flip {p.get('id', '?')} --evidence \"<what changed>\"")
PYTHON
    fi
}
