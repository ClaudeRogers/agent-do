#!/usr/bin/env bash
# lib/integration.sh — Inject, Init, Status, Profile commands
# Sourced by agent-zpc. Do not run directly.

ZPC_HARVEST_MAX_AGE_DAYS=7
ZPC_HARVEST_MIN_NEW_LESSONS=5

# True when consolidation is overdue: no harvest for ZPC_HARVEST_MAX_AGE_DAYS
# and at least ZPC_HARVEST_MIN_NEW_LESSONS lessons added since the last one.
# Anything unreadable answers "not stale" — inject never surprises its caller.
_harvest_is_stale() {
    local harvest_log="$ZPC_STATE_DIR/harvest-log.jsonl"
    local lessons_file="$ZPC_MEMORY_DIR/lessons.jsonl"

    [[ -f "$lessons_file" && -s "$lessons_file" ]] || return 1

    local verdict
    verdict=$(python3 << 'PYTHON' - "$harvest_log" "$lessons_file" "$ZPC_HARVEST_MAX_AGE_DAYS" "$ZPC_HARVEST_MIN_NEW_LESSONS" 2>/dev/null
import json, os, sys
from datetime import datetime, timedelta

harvest_log, lessons_file = sys.argv[1], sys.argv[2]
max_age_days, min_new_lessons = int(sys.argv[3]), int(sys.argv[4])

# Corrections share the file with the claims they correct, and a store where
# five lessons were retracted has not gained five lessons to consolidate.
lesson_count = 0
with open(lessons_file) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "retracts" in row or "challenges" in row:
            continue
        lesson_count += 1

last = None
if os.path.exists(harvest_log):
    with open(harvest_log) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line)
            except json.JSONDecodeError:
                pass

# Never harvested: every lesson on disk is unconsolidated.
if last is None:
    print("stale" if lesson_count >= min_new_lessons else "fresh")
    sys.exit(0)

stamp = last.get("timestamp") or last.get("date") or ""
try:
    when = datetime.fromisoformat(stamp)
except (TypeError, ValueError):
    print("fresh")
    sys.exit(0)
if when.tzinfo is not None:
    when = when.astimezone().replace(tzinfo=None)

try:
    new_lessons = lesson_count - int(last.get("lesson_count", 0))
except (TypeError, ValueError):
    new_lessons = lesson_count

aged = datetime.now() - when >= timedelta(days=max_age_days)
print("stale" if aged and new_lessons >= min_new_lessons else "fresh")
PYTHON
    ) || return 1

    [[ "$verdict" == "stale" ]]
}

# Fire the overdue harvest without putting it on inject's critical path.
# The session-start hook runs inject under a 3s process-group SIGKILL, so a
# harvest running inside inject would be killed mid-write, leave the harvest
# log un-advanced, and be retried and killed again at every session start.
# Detached, the harvest outlives that kill and inject's wall time stays flat.
_maybe_auto_harvest() {
    _harvest_is_stale || return 0

    local lock="$ZPC_STATE_DIR/harvest.lock"

    # SIGKILL takes no traps, so a killed harvest cannot release its own lock.
    # Anything this old is abandoned, not running.
    if [[ -d "$lock" && -n "$(find "$lock" -maxdepth 0 -mmin +10 2>/dev/null)" ]]; then
        rmdir "$lock" 2>/dev/null || true
    fi

    # mkdir is the atomic test-and-set. Parallel session starts in one project
    # yield to a single harvest instead of racing to append the same patterns.
    mkdir "$lock" 2>/dev/null || return 0

    # set -m gives the job its own process group, so a kill aimed at inject
    # does not reach it. The redirections are load-bearing too: an inherited
    # stdout would hold the caller's command substitution open until harvest
    # finished, which is the very wait this detachment exists to avoid.
    (
        set -m
        { cmd_harvest --auto; rmdir "$lock"; } >/dev/null 2>&1 &
    ) >/dev/null 2>&1 || true

    return 0
}

# The tie-breaker, verbatim in every blob that carries memory. Delivery is the
# whole fight: a claim rendered as law gets obeyed, and an agent that obeys a
# stale lesson while the code says otherwise has been anchored by its own birth
# context. Rendering the same claim with its date and its escape hatch turns the
# contradiction from a dissonance to rationalize into a finding to file.
ZPC_INJECT_TIEBREAKER='These are recorded claims, each true as of its date. Live observation outranks memory: when the code in front of you contradicts a lesson, the code wins, and filing the contradiction (zpc retract --candidate <id> --evidence "<receipt>") is worth more than complying with the lesson.'

# How many claims the full blob carries, and how long a correction stays news.
# A retraction is worth reading while the belief it corrects may still be in
# someone's head; after a month it is history, and history lives in the file.
ZPC_INJECT_LESSON_WINDOW=20
ZPC_INJECT_CORRECTION_DAYS=30

# The machine-wide slice is smaller than the project's: it is context from other
# projects, and it rides in every blob this machine emits.
ZPC_INJECT_GLOBAL_WINDOW=10

# The rendered claims section: retracted claims are gone, challenged claims are
# marked, and every line carries its date, its kind, and the id you would need to
# argue with it. Raw JSON rows used to go here — unreadable, undated, and
# unaddressable, which is how a lesson comes to read like a rule.
_inject_lessons() {
    local lessons_file="$1"

    python3 << 'PYTHON' - "$ZPC_LIB_DIR" "$lessons_file" "$ZPC_INJECT_LESSON_WINDOW" \
        "$ZPC_INJECT_CORRECTION_DAYS" "$ZPC_STATE_DIR/relitigation-log.jsonl"
import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, sys.argv[1])
import epistemics

lessons_path = sys.argv[2]
window, correction_days = int(sys.argv[3]), int(sys.argv[4])
relit_log = sys.argv[5]

state = epistemics.analyze(lessons_path, "les-")
claims = state["claims"]

# When a claim was last tried against current reality, if it ever was. A claim
# checked yesterday and a claim last examined the day it was written are not
# equally trustworthy, and only one of them says so on its own line.
checked = epistemics.last_checked(relit_log)

live = [record for record in claims if record["retraction"] is None]
lines = []
for record in live[-window:]:
    row = record["row"]
    tags = epistemics.tags_of(row)
    suffix = f"  [tags: {','.join(tags)}]" if tags else ""
    if record["challenges"]:
        suffix += f"  [challenged: {len(record['challenges'])}]"
    when = checked.get(record["id"])
    if when:
        suffix += f"  [checked: {when}]"
    text = epistemics.claim_text(row) or "(no takeaway recorded)"
    kind = epistemics.kind_of(row)
    lines.append(f"[{row.get('date', '?')}] {record['id']} ({kind}) {text}{suffix}")

print("\n".join(lines) if lines else "(none)")

# A retraction with no replacement claim is bookkeeping: the row stops
# rendering and there is nothing to put in its place. One that names what is
# true instead is the correction worth carrying into the next session.
now = datetime.now(timezone.utc)
corrections = []
for record in claims:
    tombstone = record["retraction"]
    if not tombstone or not tombstone.get("takeaway"):
        continue
    stamp = tombstone.get("ts", "")
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        continue
    if (now - when).days > correction_days:
        continue
    # The withdrawn wording is deliberately not quoted here. A correction that
    # repeats the wrong sentence re-injects it, and a skimmer takes the text and
    # leaves the frame. The id is the pointer for anyone who needs the original:
    # agent-do zpc query --text "<id>".
    corrections.append(
        f"[{stamp[:10]}] {record['id']} corrected to: {tombstone['takeaway']}"
    )

if corrections:
    print()
    print("## Corrections (recent)")
    print("\n".join(corrections))
PYTHON
}

# The machine-wide slice, rendered the same way the project's own claims are.
# Raw JSON rows used to go here, which had two costs: a reader could not name a
# row to argue with it, and a retracted row kept rendering forever because a
# tail knows nothing about corrections. Mined corrections land in this store, so
# it is exactly the section that most needs an escape hatch.
_inject_global() {
    local global_file="$1" limit="$2"

    python3 << 'PYTHON' - "$ZPC_LIB_DIR" "$global_file" "$limit"
import sys

sys.path.insert(0, sys.argv[1])
import epistemics

limit = int(sys.argv[3])

live = [
    record
    for record in epistemics.analyze(sys.argv[2], "les-")["claims"]
    if record["retraction"] is None
]

lines = []
for record in live[-limit:]:
    row = record["row"]
    tags = epistemics.tags_of(row)
    suffix = f"  [tags: {','.join(tags)}]" if tags else ""
    if record["challenges"]:
        suffix += f"  [challenged: {len(record['challenges'])}]"
    text = epistemics.claim_text(row) or "(no takeaway recorded)"
    lines.append(f"[{row.get('date', '?')}] {record['id']} ({epistemics.kind_of(row)}) {text}{suffix}")

print("\n".join(lines) if lines else "(none)")
PYTHON
}

# Patterns rendered as dated claims. The work is in epistemics.render_patterns
# so the compact blob below renders them the same way.
_inject_patterns() {
    local patterns_file="$1" lessons_file="$2"

    python3 << 'PYTHON' - "$ZPC_LIB_DIR" "$patterns_file" "$lessons_file"
import sys

sys.path.insert(0, sys.argv[1])
import epistemics

print(epistemics.render_patterns(sys.argv[2], sys.argv[3]))
PYTHON
}

# The compact blob's ceiling, and the literal marker that admits the cut.
# 2000 chars is a paste, not a payload: it goes in a lane prompt beside the
# lane's own instructions, where an unbounded memory dump would crowd out the
# work it is supposed to inform.
ZPC_INJECT_COMPACT_MAX=2000
ZPC_INJECT_TRUNCATED='[zpc inject truncated]'

# Patterns are consolidated truth and lessons are raw, so patterns get first
# call on the budget — but a fixed share, never all of it, so a long
# patterns.md can never starve the lessons section out of existence.
ZPC_INJECT_COMPACT_PATTERNS_SHARE=60

_inject_compact() {
    local patterns_file="$ZPC_MEMORY_DIR/patterns.md"
    local lessons_file="$ZPC_MEMORY_DIR/lessons.jsonl"

    python3 << 'PYTHON' - "$patterns_file" "$lessons_file" "$ZPC_INJECT_COMPACT_MAX" \
        "$ZPC_INJECT_TRUNCATED" "$ZPC_INJECT_COMPACT_PATTERNS_SHARE" "${OUTPUT_FORMAT:-text}" \
        "$ZPC_LIB_DIR" "$ZPC_INJECT_TIEBREAKER"
import json, os, sys

patterns_path, lessons_path = sys.argv[1], sys.argv[2]
limit, marker, share, fmt = int(sys.argv[3]), sys.argv[4], int(sys.argv[5]), sys.argv[6]

sys.path.insert(0, sys.argv[7])
import epistemics

# The tie-breaker costs a sixth of the budget and buys the frame the rest is
# read in. A subagent handed this blob has no other context: it is the surface
# where memory is most likely to be mistaken for instruction, so it is the last
# place the law should be trimmed to make room for more claims.
TIEBREAKER = sys.argv[8]
HEADER = "--- ZPC compact (this project's memory) ---"
PATTERNS_LABEL = "Recorded patterns (claims, dated):"
LESSONS_LABEL = "Recent lessons (newest first):"


def cut(text, budget):
    """Trim to budget, spending part of it on the admission that we trimmed."""
    if budget <= 0:
        return marker
    if len(text) <= budget:
        return text
    keep = max(0, budget - len(marker) - 1)
    return text[:keep].rstrip() + "\n" + marker


patterns = epistemics.render_patterns(patterns_path, lessons_path).strip() or "(none yet)"

# Retracted claims are absent from every rendering, this one included: a bounded
# blob is exactly where a withdrawn claim would be least likely to be questioned.
records = [
    record
    for record in epistemics.analyze(lessons_path, "les-")["claims"]
    if record["retraction"] is None
]

# Newest first, so the cut always takes the oldest — the one worth losing.
# Identical takeaways collapse to their newest instance: auto-captured lessons
# repeat verbatim, and five copies of one line spend a budget that five
# different lines were the point of.
rendered = []
seen = set()
for record in reversed(records):
    row = record["row"]
    takeaway = epistemics.claim_text(row)
    if not takeaway or takeaway in seen:
        continue
    seen.add(takeaway)
    tags = epistemics.tags_of(row)
    suffix = f"  [{','.join(tags)}]" if tags else ""
    if record["challenges"]:
        suffix += f"  [challenged: {len(record['challenges'])}]"
    # Dated and kinded here too: the compact blob is shorter, not softer.
    rendered.append(
        f"- [{row.get('date', '?')}] {record['id']} ({epistemics.kind_of(row)}) {takeaway}{suffix}"
    )
lessons_text = "\n".join(rendered) or "(none yet)"

scaffold = len(HEADER) + len(TIEBREAKER) + len(PATTERNS_LABEL) + len(LESSONS_LABEL) + 8
budget = max(0, limit - scaffold)

patterns_text = cut(patterns, budget * share // 100)
lessons_text = cut(lessons_text, budget - len(patterns_text))

blob = "\n".join(
    [HEADER, TIEBREAKER, "", PATTERNS_LABEL, patterns_text, "", LESSONS_LABEL, lessons_text]
)
if len(blob) > limit:
    blob = cut(blob, limit)

if fmt == "json":
    print(json.dumps({"additionalContext": blob}))
else:
    print(blob)
PYTHON
}

# The preference slice's ceiling, the same 2000 characters the compact blob
# spends and for the same reason: this is a paste into somebody else's prompt.
ZPC_INJECT_PREFERENCES_MAX=2000

# The tag that says a claim is about how this user wants to be worked with,
# rather than about how some codebase behaves. Correction mining writes it.
ZPC_INJECT_PREFERENCES_TAG='preference'

# A receipt for a read that happened outside any project store. log_access
# writes into .zpc/.state, which is exactly what this path does not have, so the
# same row shape goes to the machine-wide log instead. Append-only and silent:
# an unwritable receipt is never a reason for the read it describes to fail.
_log_global_access() {
    local cmd="$1"

    local ts source line
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)" || return 0
    source="${AGENT_DO_ZPC_SOURCE:-cli}"

    printf -v line '{"ts":"%s","cmd":"%s","source":"%s","project":"%s"}' \
        "$(_json_escape "$ts")" \
        "$(_json_escape "$cmd")" \
        "$(_json_escape "$source")" \
        "$(_json_escape "$PWD")"

    {
        mkdir -p "$ZPC_GLOBAL_DIR" &&
        printf '%s\n' "$line" >> "$ZPC_GLOBAL_DIR/access-log.jsonl"
    } 2>/dev/null || true

    return 0
}

# The machine-wide slice on its own: what this user has already said about how
# to work, carried into a directory that was never asked to have memory. A
# preference does not belong to a project, so requiring a project store to read
# one is how the same correction gets typed a fourth time.
_inject_preferences() {
    local global_file="$ZPC_GLOBAL_DIR/global-lessons.jsonl"

    # Nothing recorded is nothing to say. An empty section would be a claim in
    # itself — that the store was consulted and found wanting — and the caller
    # is pasting this straight into a prompt.
    if [[ ! -f "$global_file" || ! -s "$global_file" ]]; then
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            printf '{"additionalContext": ""}\n'
        fi
        return 0
    fi

    # Failure exits 0 with nothing said, stderr intact: a directory with no
    # memory and a directory whose memory would not parse are the same answer to
    # the caller, and neither is worth failing a session start over.
    python3 << 'PYTHON' - "$global_file" "$ZPC_INJECT_PREFERENCES_MAX" "$ZPC_INJECT_TRUNCATED" \
        "${OUTPUT_FORMAT:-text}" "$ZPC_LIB_DIR" "$ZPC_INJECT_TIEBREAKER" \
        "$ZPC_INJECT_PREFERENCES_TAG" || return 0
import json, sys

global_path = sys.argv[1]
limit, marker, fmt = int(sys.argv[2]), sys.argv[3], sys.argv[4]

sys.path.insert(0, sys.argv[5])
import epistemics

TIEBREAKER = sys.argv[6]
PREFERENCE_TAG = sys.argv[7]
HEADER = "--- ZPC preferences (machine-wide, this user) ---"
LABEL = "Recorded preferences (newest first):"


def joined(lines):
    return "\n".join(lines)


def fit(lines, budget):
    """Trim to budget by whole claims, spending part of it on admitting the cut.

    Character-granular trimming is wrong here in a way it is not elsewhere: half
    a preference is still a sentence, and "never do X unless Y" cut at the comma
    is a claim the user never made. A dropped claim is merely missing.
    """
    kept = []
    for line in lines:
        if len(joined(kept + [line])) > budget:
            break
        kept.append(line)
    if len(kept) == len(lines):
        return joined(kept)
    while kept and len(joined(kept + [marker])) > budget:
        kept.pop()
    return joined(kept + [marker]) if kept else marker


def render(record):
    row = record["row"]
    tags = epistemics.tags_of(row)
    suffix = f"  [tags: {','.join(tags)}]" if tags else ""
    if record["challenges"]:
        suffix += f"  [challenged: {len(record['challenges'])}]"
    text = epistemics.claim_text(row) or "(no takeaway recorded)"
    return f"- [{row.get('date', '?')}] {record['id']} ({epistemics.kind_of(row)}) {text}{suffix}"


# Retracted claims are absent here as they are everywhere else. A withdrawn
# preference is the one most likely to be obeyed on reflex, since nobody
# re-reads a rule they think they already know.
live = [
    record
    for record in epistemics.analyze(global_path, "les-")["claims"]
    if record["retraction"] is None
]

# Dated order, not file order: promotions and mining append at different times
# than the days they describe, and "newest first" has to mean the claim's day.
live.sort(key=lambda record: record["row"].get("date", ""), reverse=True)

# Preferences first, then the rest of the technique claims. The cut takes from
# the end, so the budget is spent on how this user works before it is spent on
# how some other project did.
preferred, technique = [], []
for record in live:
    if PREFERENCE_TAG in epistemics.tags_of(record["row"]):
        preferred.append(record)
    elif epistemics.kind_of(record["row"]) == "technique":
        technique.append(record)

# Mined corrections repeat verbatim across sessions — "try again" is typed a
# hundred times — and five copies of one line spend a budget that five different
# lines were the point of.
lines, seen = [], set()
for record in preferred + technique:
    text = epistemics.claim_text(record["row"])
    if not text or text in seen:
        continue
    seen.add(text)
    lines.append(render(record))

if not lines:
    if fmt == "json":
        print(json.dumps({"additionalContext": ""}))
    sys.exit(0)

scaffold = len(HEADER) + len(TIEBREAKER) + len(LABEL) + 4
body = fit(lines, max(0, limit - scaffold))

blob = "\n".join([HEADER, TIEBREAKER, "", LABEL, body])
if len(blob) > limit:
    blob = blob[: max(0, limit - len(marker) - 1)].rstrip() + "\n" + marker

if fmt == "json":
    print(json.dumps({"additionalContext": blob}))
else:
    print(blob)
PYTHON
}

cmd_inject() {
    local compact=false relitigate=false preferences=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --compact) compact=true; shift ;;
            --relitigate) relitigate=true; shift ;;
            --preferences) preferences=true; shift ;;
            *) shift ;;
        esac
    done

    # The preference slice answers before a project store exists, so it runs
    # before the check that would demand one. Everything below this point —
    # ensure_zpc, the overdue harvest, re-litigation — is project work.
    if [[ "$preferences" == true ]]; then
        if init_zpc_dirs 2>/dev/null; then
            log_access "inject --preferences"
        else
            _log_global_access "inject --preferences"
        fi
        _inject_preferences
        return 0
    fi

    ensure_zpc
    log_access "inject"
    _maybe_auto_harvest

    # Both of these are detached and both are allowed to fail: what inject owes
    # its caller is the blob, on time. Re-litigation rides here because inject is
    # the moment exposure is measurable — these are the claims about to be
    # repeated into somebody's context again.
    _maybe_relitigate "$relitigate" 2>/dev/null || true

    if [[ "$compact" == true ]]; then
        _inject_compact
        return 0
    fi

    local lessons_file="$ZPC_MEMORY_DIR/lessons.jsonl"
    local decisions_file="$ZPC_MEMORY_DIR/decisions.jsonl"
    local patterns_file="$ZPC_MEMORY_DIR/patterns.md"
    local profile_file="$ZPC_MEMORY_DIR/profile.md"
    local global_lessons_file="$ZPC_GLOBAL_DIR/global-lessons.jsonl"

    # Claims, not lines: corrections share the file with what they correct.
    local lesson_count decision_count
    lesson_count=$(_zpc_claim_count "$lessons_file")
    decision_count=$(_zpc_claim_count "$decisions_file")

    local context=""

    # Section 1: Protocol
    context+="--- ZPC Agent Protocol (MANDATORY) ---\n"
    context+="${ZPC_INJECT_TIEBREAKER}\n"
    context+="BEFORE writing code: read the Recorded Patterns below and note which the code still supports.\n"
    context+="DURING work: use 'agent-do zpc learn' to capture lessons.\n"
    context+="  EXACT format is handled by the tool. Usage:\n"
    context+="  agent-do zpc learn \"context\" \"problem\" \"solution\" \"takeaway\" --tags \"tag1,tag2\"\n"
    context+="BEFORE reporting completion:\n"
    context+="  Log EVERY error-resolution pair as a lesson.\n"
    context+="  Include in completion message: \"Lessons logged: N (new) | Decisions logged: N (new)\"\n"
    context+="\n"

    # Section 2: Profile
    if [[ -f "$profile_file" && -s "$profile_file" ]]; then
        context+="--- Project Profile ---\n"
        context+="$(cat "$profile_file")\n\n"
    fi

    # Section 3: Patterns
    if [[ -f "$patterns_file" && -s "$patterns_file" ]]; then
        context+="--- Recorded Patterns (claims, dated) ---\n"
        context+="$(_inject_patterns "$patterns_file" "$lessons_file")\n\n"
    fi

    # Section 4: Machine-wide lessons (bounded; omit the section when empty)
    if [[ -f "$global_lessons_file" && -s "$global_lessons_file" ]]; then
        context+="--- Global Lessons (machine-wide) ---\n"
        context+="$(_inject_global "$global_lessons_file" "$ZPC_INJECT_GLOBAL_WINDOW")\n\n"
    fi

    # Section 5: Recent project lessons
    context+="--- Recent Lessons (newest last) ---\n"
    if [[ -f "$lessons_file" && -s "$lessons_file" ]]; then
        context+="$(_inject_lessons "$lessons_file")\n"
    else
        context+="(none)\n"
    fi
    context+="\n"

    # Section 6: Decisions
    context+="--- Settled Decisions (do not re-derive; retract with evidence to re-open) ---\n"
    if [[ -f "$decisions_file" && -s "$decisions_file" ]]; then
        context+="$(python3 << 'PYTHON' - "$decisions_file" "$ZPC_LIB_DIR"
import json, sys, os

sys.path.insert(0, sys.argv[2])
import epistemics

# A decision binds until someone re-opens it, which is the difference between a
# decision and a lesson — but it binds under its own id, so re-opening it is a
# command and not an argument.
for record in epistemics.analyze(sys.argv[1], "dec-")["claims"]:
    if record["retraction"] is not None:
        continue
    row = record["row"]
    marker = f"  [challenged: {len(record['challenges'])}]" if record["challenges"] else ""
    print(f"[{row.get('date', '?')}] {record['id']} {row.get('chosen', '?')}: {row.get('rationale', '')}{marker}")
PYTHON
)\n"
    else
        context+="(none)\n"
    fi
    context+="\n"

    # Section 7: Baseline counts
    context+="--- Baseline Counts (your starting point) ---\n"
    context+="lessons.jsonl: ${lesson_count} entries | decisions.jsonl: ${decision_count} entries\n"
    context+="Only count entries YOU append as 'new'. Do not count pre-existing entries.\n"

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        # Claude Code additionalContext format
        python3 << 'PYTHON' - "$context"
import json, sys
ctx = sys.argv[1]
print(json.dumps({"additionalContext": ctx}))
PYTHON
    else
        printf '%b' "$context"
    fi
}

# Keep the store out of git without touching a file the repo would commit.
# .git/info/exclude is per-checkout and never tracked, which is the property an
# unattended caller needs: the leak protection survives, and what the repo tells
# the world to ignore stays the repo's business. Silent throughout — a store
# that could not be excluded is still a store, and the caller may be a hook.
_zpc_exclude_store() {
    local project_dir="$1"

    # Already ignored, by this repo's rules or a parent's, is already done.
    git -C "$project_dir" check-ignore -q .zpc 2>/dev/null && return 0

    local git_dir exclude
    git_dir="$(git -C "$project_dir" rev-parse --git-dir 2>/dev/null)" || return 0
    [[ -n "$git_dir" ]] || return 0
    case "$git_dir" in
        /*) ;;
        *) git_dir="$project_dir/$git_dir" ;;
    esac

    exclude="$git_dir/info/exclude"
    grep -qF '.zpc/' "$exclude" 2>/dev/null && return 0

    {
        mkdir -p "$git_dir/info" &&
        printf '\n# ZPC memory (local, untracked)\n.zpc/\n!.zpc/team/\n' >> "$exclude"
    } 2>/dev/null || true

    return 0
}

cmd_init() {
    local platform="" force=false store_only=false
    local positionals=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --platform|-p) platform="$2"; shift 2 ;;
            --force|-f) force=true; shift ;;
            --store-only) store_only=true; shift ;;
            --help|-h)
                cat << 'EOF'
Usage: agent-zpc init [--platform claude|cursor|codex|generic] [--force]
       agent-zpc init --store-only

  --platform    Which agent instruction file to write (auto-detected by default)
  --force       Rewrite profile.md and the instruction file if they exist
  --store-only  Create .zpc/ and nothing else: no .gitignore append, no agent
                instruction file, no import line added to one that exists. The
                store is kept out of git through .git/info/exclude, which is
                machine-local and untracked. This is the mode an unattended
                caller runs in a repo it does not own.
EOF
                return 0
                ;;
            *) positionals+=("$1"); shift ;;
        esac
    done

    local project_dir="$PWD"

    # A checkout bound to another's store already has its memory: the binding is
    # the store. Initializing over it builds a local store that resolution will
    # still pass over while the binding stands, and — without --store-only —
    # dirties the worktree's tracked .gitignore for nothing.
    local bound=""
    bound="$(_zpc_binding_for "$project_dir" 2>/dev/null || true)"
    if [[ -n "$bound" && "$force" != true ]]; then
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            BOUND="$bound" PROJECT="$project_dir" python3 -c '
import json, os
print(json.dumps({
    "success": True,
    "result": {"created": [], "bound_to": os.environ["BOUND"], "project": os.environ["PROJECT"]},
}))
'
        else
            echo "Already bound: $project_dir keeps its memory in $bound"
            echo "  (binding lives in ${ZPC_BINDINGS_FILE}; pass --force for a local store here)"
        fi
        return 0
    fi

    # Create directories
    mkdir -p "$project_dir/.zpc/memory"
    mkdir -p "$project_dir/.zpc/team"
    mkdir -p "$project_dir/.zpc/.state"

    local created=()

    # Create data files (skip if exists to preserve memory)
    for f in lessons.jsonl decisions.jsonl; do
        if [[ ! -f "$project_dir/.zpc/memory/$f" ]]; then
            touch "$project_dir/.zpc/memory/$f"
            created+=("$f")
        fi
    done

    # Default patterns.md
    if [[ ! -f "$project_dir/.zpc/memory/patterns.md" ]]; then
        printf '# Patterns\n\nNo patterns yet. Run `agent-do zpc harvest` after accumulating 3+ lessons with shared tags.\n' \
            > "$project_dir/.zpc/memory/patterns.md"
        created+=("patterns.md")
    fi

    # Auto-detect stack and write profile
    if [[ ! -f "$project_dir/.zpc/memory/profile.md" ]] || [[ "$force" == "true" ]]; then
        local stack
        stack=$(_detect_stack "$project_dir")
        printf '# Project Profile\n\n## Stack\n%s\n\n## Architecture\n(not yet documented)\n\n## Testing\n(not yet documented)\n\n## Conventions\n(not yet documented)\n' \
            "$stack" > "$project_dir/.zpc/memory/profile.md"
        created+=("profile.md")
    fi

    # A tracked file belongs to the repo, not to us. The store-only path keeps
    # the one side effect worth keeping — the store stays out of commits — and
    # drops the two that write files the repo would ship.
    if [[ "$store_only" == true ]]; then
        _zpc_exclude_store "$project_dir"
    else
        # Add .zpc/ to .gitignore (but NOT .zpc/team/)
        if [[ -f "$project_dir/.gitignore" ]]; then
            if ! grep -qF ".zpc/" "$project_dir/.gitignore" 2>/dev/null; then
                printf '\n# ZPC memory (local, git-ignored)\n.zpc/\n!.zpc/team/\n' >> "$project_dir/.gitignore"
            fi
        else
            printf '# ZPC memory (local, git-ignored)\n.zpc/\n!.zpc/team/\n' > "$project_dir/.gitignore"
        fi
    fi

    # Auto-detect platform if not specified
    if [[ "$store_only" != true && -z "$platform" ]]; then
        if [[ -d "$project_dir/.claude" ]]; then
            platform="claude"
        elif [[ -f "$project_dir/.cursorrules" ]]; then
            platform="cursor"
        elif [[ -f "$project_dir/AGENTS.md" ]]; then
            platform="codex"
        else
            platform="generic"
        fi
    fi

    # Generate platform instruction file
    local template_dir="$SCRIPT_DIR/templates"
    local instruction_file="" template_file=""

    case "$platform" in
        claude)   instruction_file="CLAUDE.md";          template_file="$template_dir/claude.md.tmpl" ;;
        cursor)   instruction_file=".cursorrules";       template_file="$template_dir/cursor.rules.tmpl" ;;
        codex)    instruction_file="AGENTS.md";          template_file="$template_dir/agents.md.tmpl" ;;
        generic)  instruction_file="ZPC-INSTRUCTIONS.md"; template_file="$template_dir/generic.md.tmpl" ;;
    esac

    if [[ "$store_only" != true && -n "$template_file" && -f "$template_file" ]]; then
        local stack_info
        stack_info=$(_detect_stack "$project_dir")

        if [[ ! -f "$project_dir/$instruction_file" ]] || [[ "$force" == "true" ]]; then
            sed -e "s|{{PROJECT_PATH}}|$project_dir|g" \
                -e "s|{{STACK}}|$stack_info|g" \
                "$template_file" > "$project_dir/$instruction_file"
            created+=("$instruction_file")
        elif ! grep -qiF "zpc" "$project_dir/$instruction_file" 2>/dev/null; then
            # Existing file without ZPC — add import
            mkdir -p "$project_dir/.zpc"
            sed -e "s|{{PROJECT_PATH}}|$project_dir|g" \
                -e "s|{{STACK}}|$stack_info|g" \
                "$template_file" > "$project_dir/.zpc/zpc-brain.md"
            printf '\n@.zpc/zpc-brain.md\n' >> "$project_dir/$instruction_file"
            created+=("zpc-brain.md (imported)")
        fi
    fi

    # Update global project index
    ZPC_GLOBAL_DIR="${AGENT_DO_HOME:-$HOME/.agent-do}/zpc"
    ensure_global
    python3 << 'PYTHON' - "$ZPC_GLOBAL_DIR/project-index.jsonl" "$project_dir"
import json, sys, os
from datetime import datetime
index_file, project = sys.argv[1], sys.argv[2]
entry = {"project": project, "initialized": datetime.now().strftime("%Y-%m-%d"), "last_activity": datetime.now().strftime("%Y-%m-%d")}
lines = []
if os.path.exists(index_file):
    with open(index_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("project") != project:
                    lines.append(line)
            except:
                lines.append(line)
lines.append(json.dumps(entry))
with open(index_file, "w") as f:
    f.write("\n".join(lines) + "\n")
PYTHON

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        # The platform came in through argv, not through the heredoc: a quoted
        # heredoc expands nothing, so the old inline "$platform" reached Python
        # as source text and made every --json init a SyntaxError.
        python3 << 'PYTHON' - "${created[*]}" "$platform" "$store_only"
import json, sys
files = sys.argv[1].split()
platform, store_only = sys.argv[2], sys.argv[3] == "true"
print(json.dumps({
    "success": True,
    "result": {
        "created": files,
        "platform": platform or None,
        "store_only": store_only,
    },
}))
PYTHON
    else
        echo "ZPC initialized in $project_dir"
        if [[ "$store_only" == true ]]; then
            echo "  Store only: no .gitignore or instruction file written"
        else
            echo "  Platform: $platform"
        fi
        if [[ ${#created[@]} -gt 0 ]]; then
            echo "  Created: ${created[*]}"
        fi
        echo ""
        echo "Start capturing lessons: agent-do zpc learn ..."
    fi
}

_detect_stack() {
    local dir="$1"
    local stack=""

    if [[ -f "$dir/package.json" ]]; then
        stack="Node.js"
        [[ -f "$dir/tsconfig.json" ]] && stack="TypeScript / Node.js"
        grep -q '"react"' "$dir/package.json" 2>/dev/null && stack="$stack + React"
        grep -q '"next"' "$dir/package.json" 2>/dev/null && stack="$stack (Next.js)"
        grep -q '"vue"' "$dir/package.json" 2>/dev/null && stack="$stack + Vue"
    elif [[ -f "$dir/tsconfig.json" ]]; then
        stack="TypeScript"
    elif [[ -f "$dir/pyproject.toml" ]]; then
        stack="Python"
        grep -q "fastapi" "$dir/pyproject.toml" 2>/dev/null && stack="$stack + FastAPI"
        grep -q "django" "$dir/pyproject.toml" 2>/dev/null && stack="$stack + Django"
        grep -q "flask" "$dir/pyproject.toml" 2>/dev/null && stack="$stack + Flask"
    elif [[ -f "$dir/requirements.txt" ]]; then
        stack="Python"
    elif [[ -f "$dir/Cargo.toml" ]]; then
        stack="Rust"
    elif [[ -f "$dir/go.mod" ]]; then
        stack="Go"
    elif [[ -f "$dir/pubspec.yaml" ]]; then
        stack="Flutter / Dart"
    elif [[ -f "$dir/Gemfile" ]]; then
        stack="Ruby"
    else
        stack="Unknown stack"
    fi

    echo "$stack"
}

cmd_status() {
    ensure_zpc

    local lessons_file="$ZPC_MEMORY_DIR/lessons.jsonl"
    local decisions_file="$ZPC_MEMORY_DIR/decisions.jsonl"
    local patterns_file="$ZPC_MEMORY_DIR/patterns.md"
    local harvest_log="$ZPC_STATE_DIR/harvest-log.jsonl"
    local team_lessons="$ZPC_TEAM_DIR/shared-lessons.jsonl"
    local global_lessons="$ZPC_GLOBAL_DIR/global-lessons.jsonl"

    local project_path
    project_path="$(dirname "$ZPC_DIR")"
    local lesson_count decision_count pattern_count team_count global_count
    lesson_count=$(_zpc_claim_count "$lessons_file")
    decision_count=$(_zpc_claim_count "$decisions_file")
    pattern_count=$(grep -c "^## " "$patterns_file" 2>/dev/null) || pattern_count=0
    team_count=$(count_lines "$team_lessons")
    global_count=$(count_lines "$global_lessons")

    # Format issues + consolidation gaps via python
    local health
    health=$(python3 << 'PYTHON' - "$lessons_file" "$patterns_file"
import json, sys, os, re
from collections import Counter

lessons_file, patterns_file = sys.argv[1], sys.argv[2]


def is_correction(obj):
    """Retractions and challenges are commentary on rows, not rows to validate."""
    return "retracts" in obj or "challenges" in obj


# Format issues
issues = 0
if os.path.exists(lessons_file):
    with open(lessons_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if is_correction(obj):
                    continue
                required = ["date", "context", "problem", "solution", "takeaway", "tags"]
                if any(k not in obj for k in required) or not isinstance(obj.get("tags"), list):
                    issues += 1
            except:
                issues += 1

# Consolidation gaps
pattern_tags = set()
if os.path.exists(patterns_file):
    with open(patterns_file) as f:
        for line in f:
            m = re.match(r"^## (.+)$", line.strip())
            if m:
                pattern_tags.add(m.group(1).strip())

tag_counter = Counter()
if os.path.exists(lessons_file):
    with open(lessons_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if is_correction(obj):
                    continue
                for tag in obj.get("tags", []):
                    if isinstance(tag, str):
                        tag_counter[tag] += 1
            except:
                pass

gaps = sum(1 for tag, count in tag_counter.items() if count >= 3 and tag not in pattern_tags)

print(json.dumps({"format_issues": issues, "consolidation_gaps": gaps}))
PYTHON
    )

    local format_issues gaps last_harvest global_exists
    format_issues=$(echo "$health" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['format_issues'])")
    gaps=$(echo "$health" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['consolidation_gaps'])")

    last_harvest="never"
    if [[ -f "$harvest_log" && -s "$harvest_log" ]]; then
        last_harvest=$(tail -1 "$harvest_log" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('date','unknown'))" 2>/dev/null || echo "unknown")
    fi

    global_exists="false"
    [[ -d "$ZPC_GLOBAL_DIR" ]] && global_exists="true"

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        snapshot_begin "zpc"
        snapshot_field "project" "$project_path"
        snapshot_num_field "lessons" "$lesson_count"
        snapshot_num_field "decisions" "$decision_count"
        snapshot_num_field "patterns" "$pattern_count"
        snapshot_num_field "team_lessons" "$team_count"
        snapshot_num_field "global_lessons" "$global_count"
        snapshot_num_field "format_issues" "$format_issues"
        snapshot_num_field "consolidation_gaps" "$gaps"
        snapshot_field "last_harvest" "$last_harvest"
        snapshot_bool_field "global_memory" "$global_exists"
        snapshot_end
    else
        echo "ZPC STATUS — $project_path"
        echo "  Lessons:           $lesson_count"
        echo "  Decisions:         $decision_count"
        echo "  Patterns:          $pattern_count"
        echo "  Team lessons:      $team_count"
        echo "  Global lessons:    $global_count"
        echo "  Format issues:     $format_issues"
        echo "  Consolidation gaps: $gaps"
        echo "  Last harvest:      $last_harvest"
    fi
}

cmd_profile() {
    ensure_zpc

    local subcmd="${1:-show}"
    shift 2>/dev/null || true

    local profile_file="$ZPC_MEMORY_DIR/profile.md"

    case "$subcmd" in
        show)
            if [[ ! -f "$profile_file" ]]; then
                echo "No profile found. Run 'agent-do zpc init' first."
                return 0
            fi
            if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
                local content
                content=$(<"$profile_file")
                json_success "$content"
            else
                cat "$profile_file"
            fi
            ;;
        update)
            local section="${1:-}"
            local content="${2:-}"
            if [[ -z "$section" || -z "$content" ]]; then
                die "Usage: agent-zpc profile update <section> <content>"
            fi
            python3 << 'PYTHON' - "$profile_file" "$section" "$content"
import sys, os, re

profile_file, section, new_content = sys.argv[1], sys.argv[2], sys.argv[3]

if not os.path.exists(profile_file):
    with open(profile_file, "w") as f:
        f.write(f"# Project Profile\n\n## {section}\n{new_content}\n")
    print(f"Created profile with section: {section}")
    sys.exit(0)

with open(profile_file) as f:
    lines = f.readlines()

# Find and replace section content
new_lines = []
in_section = False
replaced = False
for line in lines:
    if re.match(rf"^## {re.escape(section)}\s*$", line.strip()):
        new_lines.append(line)
        new_lines.append(new_content + "\n\n")
        in_section = True
        replaced = True
        continue
    if in_section:
        if line.startswith("## "):
            in_section = False
            new_lines.append(line)
        # Skip old content
        continue
    new_lines.append(line)

if not replaced:
    new_lines.append(f"\n## {section}\n{new_content}\n")

with open(profile_file, "w") as f:
    f.writelines(new_lines)

print(f"Updated section: {section}")
PYTHON
            ;;
        detect)
            local project_dir
            project_dir="$(dirname "$ZPC_DIR")"
            local stack
            stack=$(_detect_stack "$project_dir")
            # Update just the Stack section
            cmd_profile update "Stack" "$stack"
            ;;
        *)
            die "Unknown profile subcommand: $subcmd. Use: show, update, detect"
            ;;
    esac
}

cmd_checkpoint() {
    ensure_zpc
    mkdir -p "$ZPC_STATE_DIR"

    local phase="" agents="" verify_compliance=true

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --phase|-p) phase="$2"; shift 2 ;;
            --agents|-a) agents="$2"; shift 2 ;;
            --no-compliance) verify_compliance=false; shift ;;
            --help|-h)
                cat << 'CPHELP'
Usage: agent-zpc checkpoint [--phase "name"] [--agents "a1,a2,a3"]

Run at swarm phase boundaries. Performs:
1. Memory inventory: lesson/decision counts since last checkpoint
2. Agent compliance: which agents logged lessons/decisions (if --agents given)
3. Format health: JSONL validation
4. Consolidation scan: tags at 3+ without patterns
5. Harvest log: records checkpoint state for incremental tracking

Designed for the team lead to run between swarm phases:
  Phase 1 complete → checkpoint → Phase 2 spawn → ... → checkpoint → done

Examples:
  agent-do zpc checkpoint --phase "Phase 1: design tokens"
  agent-do zpc checkpoint --phase "Phase 2: layout + shared" --agents "layout-shell,shared-components"
  agent-do zpc checkpoint --phase "Integration" --agents "overview,innovations,data"
CPHELP
                return 0
                ;;
            *) shift ;;
        esac
    done

    local lessons_file="$ZPC_MEMORY_DIR/lessons.jsonl"
    local decisions_file="$ZPC_MEMORY_DIR/decisions.jsonl"
    local patterns_file="$ZPC_MEMORY_DIR/patterns.md"
    local checkpoint_log="$ZPC_STATE_DIR/checkpoint-log.jsonl"

    # Get previous checkpoint baseline
    local prev_lessons=0 prev_decisions=0
    if [[ -f "$checkpoint_log" && -s "$checkpoint_log" ]]; then
        prev_lessons=$(tail -1 "$checkpoint_log" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('total_lessons',0))" 2>/dev/null || echo 0)
        prev_decisions=$(tail -1 "$checkpoint_log" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('total_decisions',0))" 2>/dev/null || echo 0)
    fi

    local result
    result=$(python3 << 'PYTHON' - "$lessons_file" "$decisions_file" "$patterns_file" "$prev_lessons" "$prev_decisions" "$agents" "$verify_compliance" "$phase"
import json, sys, os, re
from collections import Counter
from datetime import datetime

lessons_file = sys.argv[1]
decisions_file = sys.argv[2]
patterns_file = sys.argv[3]
prev_lessons = int(sys.argv[4])
prev_decisions = int(sys.argv[5])
agents_str = sys.argv[6]
verify_compliance = sys.argv[7] == "true"
phase = sys.argv[8] if sys.argv[8] else f"Checkpoint {datetime.now().strftime('%H:%M')}"

agent_list = [a.strip() for a in agents_str.split(",") if a.strip()] if agents_str else []

# --- Memory inventory ---
lessons = []
format_issues = []
if os.path.exists(lessons_file):
    with open(lessons_file) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                # A retraction or challenge is a claim about a row, not a row:
                # it is neither an entry an agent failed to log nor one with a
                # missing field.
                if "retracts" in obj or "challenges" in obj:
                    continue
                # Numbered by claim, not by line: the baseline below is a count
                # of claims, and comparing it to a line number would read every
                # correction as a lesson somebody logged.
                lessons.append((len(lessons) + 1, obj))
                required = ["date", "context", "problem", "solution", "takeaway", "tags"]
                missing = [k for k in required if k not in obj]
                if missing:
                    format_issues.append({"line": i, "missing": missing})
                elif not isinstance(obj.get("tags"), list):
                    format_issues.append({"line": i, "missing": ["tags (not array)"]})
            except json.JSONDecodeError:
                format_issues.append({"line": i, "missing": ["INVALID JSON"]})

decisions = []
if os.path.exists(decisions_file):
    with open(decisions_file) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if "retracts" in obj or "challenges" in obj:
                    continue
                decisions.append((len(decisions) + 1, obj))
            except:
                pass

total_lessons = len(lessons)
total_decisions = len(decisions)
new_lessons = total_lessons - prev_lessons
new_decisions = total_decisions - prev_decisions

# --- Agent compliance ---
compliance = {}
if agent_list and verify_compliance:
    # Check new lessons/decisions for agent attribution
    # Lessons don't have an "agent" field, but we can check context field
    new_lesson_objs = [obj for i, obj in lessons if i > prev_lessons]
    new_decision_objs = [obj for i, obj in decisions if i > prev_decisions]

    for agent in agent_list:
        agent_lower = agent.lower()
        agent_lessons = sum(1 for obj in new_lesson_objs
                          if agent_lower in json.dumps(obj).lower())
        agent_decisions = sum(1 for obj in new_decision_objs
                            if agent_lower in json.dumps(obj).lower())
        compliance[agent] = {
            "lessons": agent_lessons,
            "decisions": agent_decisions,
            "compliant": agent_lessons > 0 or agent_decisions > 0
        }

# --- Consolidation gaps ---
pattern_tags = set()
pattern_count = 0
if os.path.exists(patterns_file):
    with open(patterns_file) as f:
        for line in f:
            m = re.match(r"^## (.+)$", line.strip())
            if m:
                pattern_count += 1
                pattern_tags.add(m.group(1).strip())

tag_counter = Counter()
for _, obj in lessons:
    for tag in obj.get("tags", []):
        if isinstance(tag, str):
            tag_counter[tag] += 1

gaps = [{"tag": tag, "count": count}
        for tag, count in tag_counter.most_common()
        if count >= 3 and tag not in pattern_tags]

output = {
    "phase": phase,
    "timestamp": datetime.now().isoformat(),
    "total_lessons": total_lessons,
    "total_decisions": total_decisions,
    "new_lessons": new_lessons,
    "new_decisions": new_decisions,
    "pattern_count": pattern_count,
    "format_issues": len(format_issues),
    "format_issue_details": format_issues[:5],
    "consolidation_gaps": gaps,
    "agent_compliance": compliance,
    "agents_checked": len(agent_list),
    "agents_compliant": sum(1 for v in compliance.values() if v["compliant"]),
}

print(json.dumps(output))
PYTHON
    )

    # Log checkpoint
    echo "$result" >> "$checkpoint_log"

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$result"
    else
        python3 << 'PYTHON' - "$result"
import json, sys
data = json.loads(sys.argv[1])

print(f"ZPC CHECKPOINT: {data['phase']}")
print(f"  Lessons:    {data['total_lessons']} total ({data['new_lessons']:+d} since last)")
print(f"  Decisions:  {data['total_decisions']} total ({data['new_decisions']:+d} since last)")
print(f"  Patterns:   {data['pattern_count']}")
print(f"  Format:     {'clean' if data['format_issues'] == 0 else str(data['format_issues']) + ' issues'}")

gaps = data["consolidation_gaps"]
if gaps:
    print(f"  Gaps:       {len(gaps)} tags need patterns")
    for g in gaps:
        print(f"              {g['tag']} ({g['count']} lessons)")
else:
    print(f"  Gaps:       none")

compliance = data["agent_compliance"]
if compliance:
    print(f"\n  Agent Compliance ({data['agents_compliant']}/{data['agents_checked']}):")
    for agent, info in compliance.items():
        status = "OK" if info["compliant"] else "MISSING"
        print(f"    {agent:<25} L:{info['lessons']} D:{info['decisions']}  [{status}]")
    noncompliant = [a for a, v in compliance.items() if not v["compliant"]]
    if noncompliant:
        print(f"\n  WARNING: {len(noncompliant)} agent(s) logged nothing: {', '.join(noncompliant)}")
        print(f"  Review their git diffs and extract lessons manually.")
PYTHON
    fi
}
