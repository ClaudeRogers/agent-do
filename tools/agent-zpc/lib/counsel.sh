#!/usr/bin/env bash
# lib/counsel.sh — Clean-context second opinion: a fresh model that sees the
# receipts and nothing else.
# Sourced by agent-zpc. Do not run directly.

ZPC_COUNSEL_TIMEOUT_DEFAULT=300

# The receipt bound. A brief that overflows the judge's window is not a brief,
# and a silent overflow is worse than a marked cut.
#
# There used to be three numbers here — 12000 for a diff, 6000 for a log, 6000
# for a supplied receipt — and no reason recorded for any of them being what it
# was. A brief is one delivery into a fresh model's window, so it gets what
# lib/delivery.py derives for one delivery, and a receipt that gets cut says by
# how much. Resolved once per brief and passed down, because the authority is
# read from disk and a brief assembles several receipts.
_counsel_budget() {
    python3 - "$ZPC_LIB_DIR" "$ZPC_AUTHORITY_LIB" << 'PYTHON' 2>/dev/null || true
import sys
sys.path.insert(0, sys.argv[1])
import delivery
resolved = delivery.budget(sys.argv[2])
print(resolved["tokens"] if resolved else "")
PYTHON
}

# Keeps the memory store out of the receipts it supplies. See _counsel_auto_brief.
ZPC_COUNSEL_EXCLUDE=':(exclude).zpc'

_counsel_help() {
    cat << 'EOF'
Usage: agent-zpc counsel --brief <file> [--question "<q>"] [--position <id>]
       agent-zpc counsel --auto-brief [--receipt <file>]... [--question "<q>"]

Spawns a fresh model whose entire input is your brief plus your question.
It sees no conversation, no .zpc memory, no repository, and no prior verdict:
an agent that has been arguing a position for an hour cannot un-see that hour,
so this instantiates a judge who never saw it.

  --brief <file>       Receipts only, by convention (see below).
  --auto-brief         Assemble the brief mechanically instead: git status,
                       the full `git diff HEAD`, and the newest agent-tail log.
                       Nothing is chosen, which is the point (see below).
  --receipt <file>     Add a file to the auto-brief verbatim. Repeatable.
  --question "<q>"     What you want ruled on. Defaults to a plain verdict.
  --position <id>      Print your stored position beside the fresh verdict.
  --timeout <seconds>  Give up on the subprocess (default 300).

BRIEF FORMAT (convention, not enforced): fenced blocks of raw evidence —
command output, file quotes with paths, error text, diffs. No summaries of
what you think it means, no "obviously", no naming who believes what. A
characterization in the brief is the framing you were trying to escape.

WHY --auto-brief: the residual risk below is that you pick the receipts. A
mechanical brief takes that hand off the scale — the whole diff and the whole
log go in, including the parts that weaken your case, because nothing is
selecting for your case. It is the weaker brief and the more honest sample.
It is written to .zpc/.state/counsel/brief-<epoch>.md so you can read exactly
what the judge read.

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
  agent-zpc counsel --auto-brief --receipt /tmp/curl-trace.txt \
      --question "Does the working tree do what the commit message claims?"
EOF
}

# Where assembled briefs and auto-counsel verdicts live. Own state, per project.
_counsel_state_dir() {
    printf '%s' "$ZPC_STATE_DIR/counsel"
}

# Cut a receipt to the brief's budget, by whole lines, marking the cut in place
# with its magnitude so a trimmed receipt can never be mistaken for a complete
# one. `tail` keeps the end (a log fails at the bottom); `head` keeps the start
# (a diff names its files at the top). An empty limit means the authority could
# not answer, so nothing is cut: a receipt trimmed against an invented ceiling
# is evidence a judge cannot audit.
#
# The receipt arrives on stdin, so the program cannot: `python3 -c` rather than a
# heredoc, or the script itself would eat the evidence it was meant to trim.
_counsel_bound() {
    local limit="$1" keep="${2:-head}"
    python3 -c '
import sys

sys.path.insert(0, sys.argv[1])
import delivery

limit, keep = sys.argv[2], sys.argv[3]
text = sys.stdin.read()
if not limit or delivery.measured(text) <= int(limit):
    sys.stdout.write(text)
    raise SystemExit(0)

budget, lines = int(limit), text.splitlines()
kept, spent = [], 0
for line in (lines if keep == "head" else reversed(lines)):
    step = delivery.measured(line) + 1
    if spent + step > budget:
        break
    kept.append(line)
    spent += step
note = "[receipt truncated: %d of %d lines shown]" % (len(kept), len(lines))
body = "\n".join(kept if keep == "head" else list(reversed(kept)))
sys.stdout.write(body + "\n" + note + "\n" if keep == "head" else note + "\n" + body + "\n")
' "$ZPC_LIB_DIR" "$limit" "$keep"
}

# Resolve a path through every symlink, or fail if it does not exist. macOS
# ships BSD realpath, which has no -e, so this uses python3 — already required
# by every zpc command — and tests existence itself.
_counsel_realpath() {
    [[ -e "$1" ]] || return 1
    python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$1" 2>/dev/null
}

# True when an already-resolved path sits strictly inside an already-resolved
# root. Equality is not containment: the root is not a file within itself.
_counsel_within_root() {
    [[ "$1" == "$2"/* ]]
}

# The newest agent-tail log, read through that tool's own convention
# (tmp/logs/latest -> session dir). Absent or unreadable is not an error: the
# brief simply says so, rather than inventing a receipt.
#
# Every hop is resolved and confined to the project root, because this symlink
# is a file a repository can commit and the brief it feeds is both written to
# disk and sent to a model. Unconfined, cloning a hostile repo and opening a
# session would be enough to read an arbitrary local file: the session-start
# hook runs `zpc inject`, inject fires the relitigation pass, and that pass
# assembles a brief through this collector. Resolving before reading also
# closes the swap-the-link race, since what gets read is the real path.
# Prints "ok <path>" or "refused <path>", and nothing when there is simply no
# log. A refusal has to travel back to the caller as output, not a global: this
# runs inside a command substitution, and a subshell's variables die with it.
_counsel_latest_log() {
    local root_real refused=""
    root_real="$(_counsel_realpath "$1")" || return 1

    local base
    for base in "$PWD/tmp/logs" "$1/tmp/logs"; do
        [[ -L "$base/latest" ]] || continue

        local session
        session="$(_counsel_realpath "$base/latest")" || continue
        [[ -d "$session" ]] || continue
        if ! _counsel_within_root "$session" "$root_real"; then
            refused="$base/latest"
            continue
        fi

        # The file is checked on its own: a directory inside the root can still
        # hold a symlink that points out of it.
        local candidate resolved
        for candidate in "$session/combined.log" "$(ls -t "$session"/*.log 2>/dev/null | head -1)"; do
            [[ -n "$candidate" && -f "$candidate" && -s "$candidate" ]] || continue
            resolved="$(_counsel_realpath "$candidate")" || continue
            [[ -f "$resolved" ]] || continue
            if ! _counsel_within_root "$resolved" "$root_real"; then
                refused="$candidate"
                continue
            fi
            printf 'ok %s' "$resolved"
            return 0
        done
    done

    [[ -z "$refused" ]] || { printf 'refused %s' "$refused"; return 0; }
    return 1
}

# One fenced receipt block. The heading names the exact source so a reader can
# re-run it; the fence keeps the model from reading structure as instruction.
_counsel_receipt_block() {
    local label="$1" fence="$2"
    printf -- '--- RECEIPT: %s ---\n' "$label"
    printf '```%s\n' "$fence"
    cat
    printf '\n```\n\n'
}

# A receipt that has nothing to report says so in one line. The judge cannot
# cross-check anything it is handed, so a collector's complaint about the world
# must never be dressed as an observation of it: `git diff` outside a repo
# prints its own usage screen, and fenced as a diff that is a hundred lines of
# fabricated evidence.
_counsel_unavailable() {
    printf -- '--- RECEIPT: %s ---\n' "$1"
    printf 'unavailable: %s\n\n' "$2"
}

# The collector ran and the answer was nothing. That is a finding, not a
# failure, and the judge should be able to tell the two apart: "the tree is
# clean" and "I could not look at the tree" support opposite conclusions.
_counsel_nothing() {
    printf -- '--- RECEIPT: %s ---\n' "$1"
    printf 'nothing to report: %s\n\n' "$2"
}

# What the git collectors can honestly say about this root, decided up front.
# Asking the world its state beats parsing the tool's objection to it.
_counsel_git_state() {
    local root="$1"
    ( cd "$root" && git rev-parse --is-inside-work-tree ) >/dev/null 2>&1 || { printf 'none'; return 0; }
    ( cd "$root" && git rev-parse --verify HEAD ) >/dev/null 2>&1 || { printf 'unborn'; return 0; }
    printf 'ready'
}

# Run one collector and emit exactly one of three things: its bounded output as
# a fenced receipt, an honest line saying it produced nothing, or an honest line
# saying it failed. Never its diagnostics as evidence.
# Usage: _counsel_collect <label> <fence> <limit> <keep> <root> <empty-note> <cmd...>
_counsel_collect() {
    local label="$1" fence="$2" limit="$3" keep="$4" root="$5" empty_note="$6"
    shift 6

    local out_file err_file status=0
    out_file="$(mktemp)" || { _counsel_unavailable "$label" "no scratch file available"; return 0; }
    err_file="$(mktemp)" || { rm -f "$out_file"; _counsel_unavailable "$label" "no scratch file available"; return 0; }

    ( cd "$root" && "$@" ) > "$out_file" 2> "$err_file" || status=$?

    if [[ "$status" -ne 0 ]]; then
        # One line of the tool's own words, preferring the line that names the
        # cause over the first line it happened to print.
        local reason=""
        reason="$(grep -m1 -E '^(fatal|error):' "$err_file" 2>/dev/null || true)"
        [[ -n "$reason" ]] || reason="$(grep -m1 -v '^[[:space:]]*$' "$err_file" 2>/dev/null || true)"
        _counsel_unavailable "$label" "${reason:-command failed (exit $status)}"
    elif [[ ! -s "$out_file" ]]; then
        _counsel_nothing "$label" "$empty_note"
    else
        _counsel_bound "$limit" "$keep" < "$out_file" | _counsel_receipt_block "$label" "$fence"
    fi

    rm -f "$out_file" "$err_file" 2>/dev/null || true
}

# Assemble a brief from what the machine can see without asking anyone what
# matters. Mechanical selection is the whole point: no curation step exists
# here to smuggle the framing back in.
_counsel_auto_brief() {
    local out="$1"
    shift
    local receipts=("$@")

    local root
    root="$(dirname "$ZPC_DIR")"

    mkdir -p "$(dirname "$out")" || die "Could not create $(dirname "$out")"

    {
        printf '# Auto-assembled brief\n'
        printf 'assembled: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf 'root: %s\n' "$root"
        printf 'selection: mechanical (nothing here was chosen for its content)\n\n'

        # .zpc is excluded from both, and it is the one exclusion here. A
        # project that tracks its memory store would otherwise ship the
        # standing verdict to the judge inside the diff — the exact prior
        # opinion counsel exists to have never seen. Not curation of the
        # evidence: removal of the ledger from its own trial.
        local status_label="git status --porcelain (excluding .zpc)"
        local diff_label="git diff HEAD (excluding .zpc)"
        local max_tokens
        max_tokens="$(_counsel_budget)"

        case "$(_counsel_git_state "$root")" in
            none)
                _counsel_unavailable "$status_label" "no git repository at $root"
                _counsel_unavailable "$diff_label" "no git repository at $root"
                ;;
            unborn)
                _counsel_collect "$status_label" "" "$max_tokens" head "$root" \
                    "nothing modified and nothing untracked" \
                    git status --porcelain -- . "$ZPC_COUNSEL_EXCLUDE"
                _counsel_unavailable "$diff_label" \
                    "the repository at $root has no commits yet: there is no HEAD to diff against"
                ;;
            *)
                _counsel_collect "$status_label" "" "$max_tokens" head "$root" \
                    "nothing modified and nothing untracked" \
                    git status --porcelain -- . "$ZPC_COUNSEL_EXCLUDE"
                _counsel_collect "$diff_label" "diff" "$max_tokens" head "$root" \
                    "no tracked file differs from HEAD" \
                    git diff HEAD -- . "$ZPC_COUNSEL_EXCLUDE"
                ;;
        esac

        local log_find="" log_state="" log_path=""
        if log_find="$(_counsel_latest_log "$root")"; then
            log_state="${log_find%% *}"
            log_path="${log_find#* }"
        fi

        if [[ "$log_state" == "ok" ]]; then
            # `cat`, not a pre-trimmed tail: _counsel_bound holds the end of the
            # stream and reports how many lines it dropped, and a `tail -c` in
            # front of it would silently discard the very lines the marker is
            # supposed to be counting.
            _counsel_collect "$log_path" "" "$max_tokens" tail "$root" \
                "the log exists but is empty" \
                cat "$log_path"
        elif [[ "$log_state" == "refused" ]]; then
            # A refusal is not an absence. Saying "no log" here would hide the
            # fact that something pointed out of the project and was stopped.
            _counsel_unavailable "latest run log" \
                "$log_path resolves outside $root and was not read"
        else
            # Name where we looked. "None found" and "looked in the wrong
            # place" are different facts, and a brief that conflates them
            # hands the judge a false negative dressed as a receipt.
            printf -- '--- RECEIPT: latest run log ---\n'
            printf 'No log found. Searched (agent-tail convention, latest symlink):\n'
            printf '  %s/tmp/logs/latest\n' "$PWD"
            [[ "$root" == "$PWD" ]] || printf '  %s/tmp/logs/latest\n' "$root"
            printf '\n'
        fi

        local receipt
        for receipt in "${receipts[@]+"${receipts[@]}"}"; do
            _counsel_collect "$receipt" "" "$max_tokens" head "$root" \
                "the file is empty" \
                cat "$receipt"
        done
    } > "$out"
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
    local auto_brief=false
    local receipts=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --brief|-b) brief="${2:-}"; shift 2 ;;
            --auto-brief) auto_brief=true; shift ;;
            --receipt) receipts+=("${2:-}"); shift 2 ;;
            --question|-q) question="${2:-}"; shift 2 ;;
            --position|-p) position_id="${2:-}"; shift 2 ;;
            --timeout) timeout="${2:-}"; shift 2 ;;
            --help|-h) _counsel_help; return 0 ;;
            *) shift ;;
        esac
    done

    ensure_zpc

    if [[ "$auto_brief" == true ]]; then
        [[ -z "$brief" ]] || die "--auto-brief assembles the brief and --brief supplies one; counsel reads exactly one. Pass extra files with --receipt."
        local receipt
        for receipt in "${receipts[@]+"${receipts[@]}"}"; do
            [[ -f "$receipt" ]] || die "Receipt not found: $receipt"
        done
        brief="$(_counsel_state_dir)/brief-$(date +%s).md"
        _counsel_auto_brief "$brief" "${receipts[@]+"${receipts[@]}"}"
        # On stderr, and before the model call: the path is worth having even
        # if the run below times out, and it must not enter the artifact the
        # detached caller captures from stdout.
        echo "Brief assembled (mechanical): $brief" >&2
    elif [[ ${#receipts[@]} -gt 0 ]]; then
        die "--receipt adds files to an assembled brief. Pass --auto-brief with it, or put them in your own --brief."
    fi

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
