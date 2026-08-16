#!/usr/bin/env bash
# lib/epistemics.sh — Lesson identity and the retraction that corrects it.
# Sourced by agent-zpc. Do not run directly.

# Exit code for a correction that named no evidence. Same number and same
# meaning as the position ledger's refused flip: "you were refused", not "you
# asked wrong". A caller can tell the two apart without reading the message.
ZPC_RETRACT_REFUSED=2

ZPC_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZPC_EPISTEMICS_PY="$ZPC_LIB_DIR/epistemics.py"

_epistemics() {
    python3 "$ZPC_EPISTEMICS_PY" "$@"
}

# Claim rows only. Corrections live in the same file as their targets, so every
# count that means "how much memory is there" has to step over them.
_zpc_claim_count() {
    local file="$1"
    [[ -f "$file" && -s "$file" ]] || { printf '0'; return 0; }
    _epistemics count "$file" 2>/dev/null || count_lines "$file"
}

# Which file holds this claim. A les- id can name a project lesson or a
# machine-wide one — promoted and mined rows carry the same prefix — so the id
# alone does not say, and the answer is whichever store actually resolves it.
# Project first: that is the store the command is standing in. An id found in
# neither reports against the project store, where the "no such claim" message
# belongs.
_zpc_store_file() {
    local id="$1" project global
    case "$id" in
        les-*)
            project="$ZPC_MEMORY_DIR/lessons.jsonl"
            global="$ZPC_GLOBAL_DIR/global-lessons.jsonl"
            if _epistemics resolve "$project" "les-" "$id" >/dev/null 2>&1; then
                printf '%s' "$project"
            elif [[ -f "$global" ]] && _epistemics resolve "$global" "les-" "$id" >/dev/null 2>&1; then
                printf '%s' "$global"
            else
                printf '%s' "$project"
            fi
            ;;
        dec-*) printf '%s' "$ZPC_MEMORY_DIR/decisions.jsonl" ;;
        *) return 1 ;;
    esac
}

_zpc_store_prefix() {
    case "$1" in
        les-*) printf 'les-' ;;
        dec-*) printf 'dec-' ;;
        *) return 1 ;;
    esac
}

# Materialize derived ids into a store. Idempotent: the ids written here are the
# ones every reader already derives, so running it twice changes nothing and
# skipping it changes nothing either. Silent failure is deliberate — an id is a
# convenience for the next reader, never a reason for this write to fail.
_zpc_backfill() {
    local file="$1" prefix="$2"
    [[ -f "$file" ]] || return 0
    _epistemics backfill "$file" "$prefix" 2>/dev/null || true
}

_zpc_backfill_stores() {
    _zpc_backfill "$ZPC_MEMORY_DIR/lessons.jsonl" "les-" >/dev/null
    _zpc_backfill "$ZPC_MEMORY_DIR/decisions.jsonl" "dec-" >/dev/null
}

_zpc_resolve() {
    local id="$1" file prefix
    file="$(_zpc_store_file "$id")" || return 1
    prefix="$(_zpc_store_prefix "$id")" || return 1
    _epistemics resolve "$file" "$prefix" "$id"
}

_retract_help() {
    cat << 'EOF'
Usage: agent-zpc retract <id> --evidence "<receipt>" [--takeaway "<the corrected claim>"]
       agent-zpc retract --candidate <id> --evidence "<what looked wrong>"
       agent-zpc retract --backfill

You do not delete a wrong lesson. You file the correction with evidence, and
both stay on disk: the claim, and the receipt that broke it. Injection stops
rendering a retracted claim and renders the correction in its place.

  retract <id> --evidence "<receipt>"
      Files a tombstone against a lesson (les-...) or decision (dec-...).
      Without --evidence this exits 2 and writes nothing: a retraction with no
      receipt is the same anchoring problem pointed the other way.
      --takeaway records what is true instead; it is what inject shows under
      Corrections while the retraction is recent.

  retract --candidate <id> --evidence "<what looked wrong>"
      Cheap doubt. Files a challenge instead of a tombstone — you are not
      required to win the argument, only to say what you saw. The claim keeps
      rendering, now marked [challenged: n], and jumps the re-litigation queue.

  retract --backfill
      Give every id-less row in this project's stores its derived id. Happens
      on its own at the next write; this is for when you want the ids now.

Ids are derived from row content, so the id you read in an inject blob is the
id on disk. Find one with: agent-do zpc query --text "<some words>"

Examples:
  agent-zpc retract les-1a2b3c \
      --evidence "src/api.ts:44 sets Retry-After on every 429 (read 2026-07-27)" \
      --takeaway "the API does send Retry-After; the client was ignoring it"
  agent-zpc retract --candidate les-1a2b3c --evidence "grep finds no such handler in src/"
EOF
}

cmd_retract() {
    ensure_zpc

    local target="" evidence="" takeaway="" candidate=false backfill_only=false
    local positionals=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --evidence|-e) evidence="${2:-}"; shift 2 ;;
            --takeaway) takeaway="${2:-}"; shift 2 ;;
            --candidate)
                candidate=true
                # Reads as a flag when the id came in positionally, and as a
                # flag with a value when it did not. Both spellings are in use.
                if [[ -n "${2:-}" && "${2:-}" != -* ]]; then
                    target="$2"; shift 2
                else
                    shift
                fi
                ;;
            --backfill) backfill_only=true; shift ;;
            --help|-h) _retract_help; return 0 ;;
            *) positionals+=("$1"); shift ;;
        esac
    done

    if [[ "$backfill_only" == true ]]; then
        local lessons_report decisions_report
        lessons_report="$(_zpc_backfill "$ZPC_MEMORY_DIR/lessons.jsonl" "les-")"
        decisions_report="$(_zpc_backfill "$ZPC_MEMORY_DIR/decisions.jsonl" "dec-")"
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            python3 -c '
import json, sys
lessons = json.loads(sys.argv[1] or "{}")
decisions = json.loads(sys.argv[2] or "{}")
print(json.dumps({"success": True, "result": {"lessons": lessons, "decisions": decisions}}))
' "$lessons_report" "$decisions_report"
        else
            python3 -c '
import json, sys
for label, raw in (("lessons", sys.argv[1]), ("decisions", sys.argv[2])):
    data = json.loads(raw or "{}")
    assigned, total = data.get("assigned", 0), data.get("claims", 0)
    print("  %-10s %d id(s) assigned, %d claim(s) total" % (label, assigned, total))
' "$lessons_report" "$decisions_report"
        fi
        return 0
    fi

    [[ -n "$target" ]] || target="${positionals[0]:-}"
    [[ -n "$target" ]] || die "Usage: agent-zpc retract <id> --evidence \"<receipt>\" (or --candidate <id> for a challenge)"

    local file prefix
    file="$(_zpc_store_file "$target")" \
        || die "Ids look like les-1a2b3c (a lesson) or dec-1a2b3c (a decision); got '$target'."
    prefix="$(_zpc_store_prefix "$target")"

    local row
    row="$(_zpc_resolve "$target")" \
        || die "No claim with id '$target'. Find one with: agent-do zpc query --text \"<words>\" (ids are shown by inject)."

    # The refusal, before anything is written — including before the id backfill
    # below, so "writes nothing" means the file is byte-identical afterwards.
    if [[ -z "$evidence" ]]; then
        local refusal
        refusal=$(python3 << 'PYTHON' - "$row" "$candidate"
import json, sys

record = json.loads(sys.argv[1])
candidate = sys.argv[2] == "true"
verb = "challenge" if candidate else "retraction"
flag = "--candidate " if candidate else ""

print(
    f"Refused: a {verb} needs named evidence.\n\n"
    f"  {record['id']} [{record.get('date', '?')}] {record.get('claim', '')}\n"
    f"  kind: {record.get('kind', '')}, challenges so far: {record.get('challenges', 0)}\n\n"
    "Nothing was written. Name what you observed, and where:\n"
    f"  agent-zpc retract {flag}{record['id']} --evidence \"<file:line, command output, or run>\"\n\n"
    "A claim is not wrong because it is inconvenient, and a retraction with no\n"
    "receipt is the same anchoring problem pointed the other way."
)
PYTHON
        )

        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_error "$refusal" "$ZPC_RETRACT_REFUSED" || true
        else
            printf '%s\n' "$refusal" >&2
        fi
        exit "$ZPC_RETRACT_REFUSED"
    fi

    # The ids readers derive become ids the file carries, so the row this
    # correction points at can be found by grep and not only by derivation.
    _zpc_backfill "$file" "$prefix" >/dev/null

    local verb="retract"
    [[ "$candidate" == true ]] && verb="challenge"

    local correction
    correction="$(_epistemics correction "$verb" "$target" "$evidence" "$takeaway")" \
        || die "Could not build the correction row; nothing was written."
    append_jsonl "$file" "$correction" || return 1

    log_access "retract"

    local blast='{"lessons":[],"decisions":[],"patterns":[]}'
    if [[ "$candidate" == false ]]; then
        blast="$(_epistemics blast-radius \
            "$ZPC_MEMORY_DIR/lessons.jsonl" \
            "$ZPC_MEMORY_DIR/decisions.jsonl" \
            "$ZPC_MEMORY_DIR/patterns.md" \
            "$prefix" "$target" 2>/dev/null)" || blast='{"lessons":[],"decisions":[],"patterns":[]}'
    fi

    local updated
    updated="$(_zpc_resolve "$target")" || updated="$row"

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        python3 << 'PYTHON' - "$correction" "$updated" "$blast" "$candidate"
import json, sys

payload = {
    "correction": json.loads(sys.argv[1]),
    "target": json.loads(sys.argv[2]),
    "blast_radius": json.loads(sys.argv[3]),
    "kind": "challenge" if sys.argv[4] == "true" else "retraction",
}
print(json.dumps({"success": True, "result": payload}, ensure_ascii=False))
PYTHON
    else
        python3 << 'PYTHON' - "$correction" "$updated" "$blast" "$candidate"
import json, sys

correction = json.loads(sys.argv[1])
record = json.loads(sys.argv[2])
blast = json.loads(sys.argv[3])
candidate = sys.argv[4] == "true"

claim = record.get("claim", "")
if candidate:
    print(f"Challenged {record['id']} [{record.get('date', '?')}]: {claim}")
    print(f"  evidence: {correction['evidence']}")
    print(f"  challenges on this claim: {record.get('challenges', 0)}")
    print()
    print("The claim keeps rendering, now marked [challenged]. You did not have to")
    print("win the argument to file this; re-litigation reaches challenged claims first.")
else:
    print(f"Retracted {record['id']} [{record.get('date', '?')}]: {claim}")
    print(f"  evidence: {correction['evidence']}")
    if correction.get("takeaway"):
        print(f"  instead:  {correction['takeaway']}")
    print()
    print("Nothing was deleted. The claim stays on disk with the receipt beside it;")
    print("inject stops rendering it and shows the correction for the next 30 days.")

    lessons = blast.get("lessons", [])
    decisions = blast.get("decisions", [])
    patterns = blast.get("patterns", [])
    if lessons or decisions or patterns:
        print()
        print("Blast radius — these co-refer and were never examined:")
        for hit in lessons:
            tags = ",".join(hit.get("shared_tags", []))
            marker = f"  [tags: {tags}]" if tags else ""
            print(f"  {hit['id']} [{hit.get('date', '?')}]{marker} {hit.get('claim', '')}")
        for hit in decisions:
            print(f"  {hit['id']} [{hit.get('date', '?')}] (decision) {hit.get('claim', '')}")
        for hit in patterns:
            print(f"  patterns.md ## {hit['section']} — {hit['line']}")
        print()
        print("Nothing above was changed. Read them; retract the ones that fell with it.")
PYTHON
    fi
}
