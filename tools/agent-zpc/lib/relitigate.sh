#!/usr/bin/env bash
# lib/relitigate.sh — Periodic re-trial of the claims memory repeats most.
# Sourced by agent-zpc. Do not run directly.
#
# Wrong lessons do not announce themselves. They are falsifiable only when
# somebody asks the right question, and an agent reading its own birth context
# is the last party who will think to ask. So the asking is mechanical: the
# claims being injected most, aged and doubted, get handed to a judge that never
# saw them believed, along with receipts collected from the code as it is today.
#
# The pass files challenges and never retracts. A model that read a diff is not
# authority to delete somebody's lesson — it is authority to say "look at this
# again", which is exactly what a challenge means.

# The gate: a store too small has no exposure worth auditing, and a pass too
# recent is spending model calls on claims nothing has changed under.
ZPC_RELIT_MIN_LESSONS=20
ZPC_RELIT_MAX_AGE_DAYS=14
ZPC_RELIT_TOP_N=3

# Per-claim ceilings. A re-litigation brief is small by construction, so the
# 300s counsel default would only ever be a hang budget.
ZPC_RELIT_TIMEOUT=180
ZPC_RELIT_TERMS=3
ZPC_RELIT_GREP_LINES=40

# SIGKILL takes no traps, so a killed pass cannot release its own lock. Counsel
# runs are minutes, not seconds; anything older than this was abandoned.
ZPC_RELIT_LOCK_STALE_MIN=60

_relit_log_file() {
    printf '%s' "$ZPC_STATE_DIR/relitigation-log.jsonl"
}

# True when a pass is overdue: no re-litigation for ZPC_RELIT_MAX_AGE_DAYS and
# a store big enough for exposure to mean something. Anything unreadable answers
# "not due" — inject never surprises its caller.
_relit_is_due() {
    local lessons_file="$ZPC_MEMORY_DIR/lessons.jsonl"
    [[ -f "$lessons_file" && -s "$lessons_file" ]] || return 1

    local verdict
    verdict=$(python3 << 'PYTHON' - "$ZPC_LIB_DIR" "$lessons_file" "$(_relit_log_file)" \
        "$ZPC_RELIT_MIN_LESSONS" "$ZPC_RELIT_MAX_AGE_DAYS" 2>/dev/null
import json, os, sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, sys.argv[1])
import epistemics

lessons_path, log_path = sys.argv[2], sys.argv[3]
min_lessons, max_age_days = int(sys.argv[4]), int(sys.argv[5])

live = [
    record
    for record in epistemics.analyze(lessons_path, "les-")["claims"]
    if record["retraction"] is None
]
if len(live) < min_lessons:
    print("fresh")
    sys.exit(0)

last = ""
if os.path.exists(log_path):
    with open(log_path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                stamp = json.loads(line).get("ts", "")
            except json.JSONDecodeError:
                continue
            if stamp > last:
                last = stamp

if not last:
    print("due")
    sys.exit(0)

try:
    when = datetime.fromisoformat(last.replace("Z", "+00:00"))
except ValueError:
    print("fresh")
    sys.exit(0)

aged = datetime.now(timezone.utc) - when >= timedelta(days=max_age_days)
print("due" if aged else "fresh")
PYTHON
    ) || return 1

    [[ "$verdict" == "due" ]]
}

# The claim's own words decide what gets grepped. A sweep for terms somebody
# picked would be curation; a sweep for the claim's longest words is just the
# claim, asked of the working tree.
_relit_term_receipt() {
    local claim="$1" out="$2" root="$3"

    local terms
    terms="$(_epistemics terms "$claim" "$ZPC_RELIT_TERMS" 2>/dev/null)" || terms="[]"

    {
        printf 'Term sweep of the working tree for the claim under test.\n'
        printf 'Terms are the claim own longest words; nothing here was chosen by hand.\n\n'
        python3 -c 'import json,sys; print("\n".join(json.loads(sys.argv[1])))' "$terms" \
        | while IFS= read -r term; do
            [[ -n "$term" ]] || continue
            printf -- '--- git grep -n -i -- %s ---\n' "$term"
            local hits=""
            hits="$( ( cd "$root" && git grep -n -i -- "$term" ) 2>/dev/null | head -n "$ZPC_RELIT_GREP_LINES" )" || true
            if [[ -n "$hits" ]]; then
                printf '%s\n\n' "$hits"
            else
                printf 'no match in the tracked tree\n\n'
            fi
        done
    } > "$out" 2>/dev/null || true
}

# Subtraction-shaped, and deliberately not asking whether the claim is nice.
# The judge is told the claim only because the claim is the subject; everything
# else it sees is a receipt collected without reference to it.
_relit_question() {
    local date="$1" claim="$2"
    cat << EOF
A claim recorded in this project's memory on ${date} says:

  "${claim}"

Reason only from the receipts above, as if you were meeting this claim for the
first time. Was it ever true of this codebase, and does anything in the receipts
still support it today? What would break if it were removed?

Begin your VERDICT sentence with exactly one of these words: SUPPORTED,
CONTRADICTED, or UNSUPPORTED (nothing in the receipts speaks to it). Then the
sentence.
EOF
}

# The pass itself. Runs detached, past the point where inject has returned, so
# every cost in here is off the caller's clock.
_relit_run() {
    local run_dir="$1" run_id="$2" mode="$3"
    local root log_file
    root="$(dirname "$ZPC_DIR")"
    log_file="$(_relit_log_file)"

    mkdir -p "$run_dir" 2>/dev/null || return 0

    local candidates
    candidates="$(_epistemics relit-rank \
        "$ZPC_MEMORY_DIR/lessons.jsonl" "les-" \
        "$ZPC_INJECT_LESSON_WINDOW" "$ZPC_RELIT_TOP_N" \
        "$log_file" "$ZPC_RELIT_MAX_AGE_DAYS" 2>/dev/null)" || candidates="[]"

    printf '%s\n' "$candidates" > "$run_dir/candidates.json" 2>/dev/null || true

    local count
    count="$(printf '%s' "$candidates" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))' 2>/dev/null)" || count=0

    local index=0
    while [[ "$index" -lt "$count" ]]; do
        local claim_json id claim date
        claim_json="$(printf '%s' "$candidates" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)[int(sys.argv[1])]))' "$index" 2>/dev/null)" || break
        id="$(printf '%s' "$claim_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
        claim="$(printf '%s' "$claim_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["claim"])')"
        date="$(printf '%s' "$claim_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["date"])')"

        local outcome="planned" line="" artifact=""
        if [[ "$mode" == "run" ]]; then
            local sweep brief verdict_file
            sweep="$run_dir/sweep-$id.txt"
            brief="$run_dir/brief-$id.md"
            verdict_file="$run_dir/verdict-$id.md"

            _relit_term_receipt "$claim" "$sweep" "$root"
            _counsel_auto_brief "$brief" "$sweep" 2>/dev/null || true

            local status=0
            ( OUTPUT_FORMAT=text cmd_counsel --brief "$brief" \
                --question "$(_relit_question "$date" "$claim")" \
                --timeout "$ZPC_RELIT_TIMEOUT" ) > "$verdict_file" 2>"$verdict_file.err" || status=$?

            artifact="$verdict_file"
            if [[ "$status" -ne 0 ]]; then
                outcome="failed"
                line="counsel exited $status"
            else
                local classified
                classified="$(_epistemics relit-classify "$verdict_file" 2>/dev/null)" || classified='{}'
                outcome="$(printf '%s' "$classified" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("outcome","unreadable"))' 2>/dev/null)" || outcome="unreadable"
                line="$(printf '%s' "$classified" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("line",""))' 2>/dev/null)" || line=""

                # Divergence files doubt, never a tombstone. A verdict read off
                # a diff is a reason to look again, not permission to delete
                # what somebody learned the hard way.
                if [[ "$outcome" == "contradicted" ]]; then
                    ( OUTPUT_FORMAT=text cmd_retract --candidate "$id" \
                        --evidence "re-litigation $run_id: a clean-context read of current receipts returned CONTRADICTED — ${line:0:220} (artifact: $verdict_file)" \
                    ) >> "$run_dir/challenges.log" 2>&1 || true
                fi
            fi
            rm -f "$verdict_file.err" 2>/dev/null || true
        fi

        python3 - "$log_file" "$run_id" "$id" "$outcome" "$line" "$artifact" "$claim_json" << 'PYTHON' 2>/dev/null || true
import json, sys
from datetime import datetime, timezone

log_path, run_id, lesson, outcome, line, artifact, claim_json = sys.argv[1:8]
claim = json.loads(claim_json)
row = {
    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "run": run_id,
    "lesson": lesson,
    "score": claim.get("score"),
    "challenges": claim.get("challenges"),
    "outcome": outcome,
}
if line:
    row["verdict"] = line[:400]
if artifact:
    row["artifact"] = artifact
with open(log_path, "a") as handle:
    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
PYTHON

        index=$((index + 1))
    done

    # The pass row is what the next gate reads. Without it a pass that found no
    # candidate would look like no pass at all and re-fire at every inject.
    python3 - "$log_file" "$run_id" "$count" "$mode" << 'PYTHON' 2>/dev/null || true
import json, sys
from datetime import datetime, timezone

log_path, run_id, count, mode = sys.argv[1:5]
row = {
    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "run": run_id,
    "event": "pass",
    "mode": mode,
    "candidates": int(count),
}
with open(log_path, "a") as handle:
    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
PYTHON

    rm -f "$run_dir"/*.err 2>/dev/null || true
}

# Fire an overdue pass without putting it on inject's critical path. Same detach
# shape as the auto-harvest: own process group, every descriptor closed, so the
# session-start hook's 3s kill lands on inject and never on the judge.
#
# AGENT_DO_ZPC_RELITIGATE: 1 (default) runs it, 0 disables it entirely, and
# "plan" ranks the candidates and records the pass without spending a model.
_maybe_relitigate() {
    local force="${1:-false}"

    local switch="${AGENT_DO_ZPC_RELITIGATE:-1}"
    [[ "$switch" != "0" ]] || return 0

    local mode="run"
    [[ "$switch" == "plan" ]] && mode="plan"

    if [[ "$mode" == "run" ]]; then
        command -v claude >/dev/null 2>&1 || return 0
    fi

    if [[ "$force" != "true" ]]; then
        _relit_is_due || return 0
    fi

    local lock="$ZPC_STATE_DIR/relit.lock"
    mkdir -p "$ZPC_STATE_DIR" 2>/dev/null || return 0
    if [[ -d "$lock" && -n "$(find "$lock" -maxdepth 0 -mmin "+$ZPC_RELIT_LOCK_STALE_MIN" 2>/dev/null)" ]]; then
        rmdir "$lock" 2>/dev/null || true
    fi
    mkdir "$lock" 2>/dev/null || return 0

    local epoch run_id run_dir
    epoch="$(date +%s)"
    run_id="relit-$epoch"
    run_dir="$ZPC_STATE_DIR/counsel/$run_id"

    (
        set -m
        { _relit_run "$run_dir" "$run_id" "$mode"; rmdir "$lock"; } >/dev/null 2>&1 &
    ) >/dev/null 2>&1 || true

    return 0
}
