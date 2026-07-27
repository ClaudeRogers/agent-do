#!/usr/bin/env bash
# lib/position.sh — The position ledger: verdict, confidence, falsifier, and
# the flip that must name its evidence.
# Sourced by agent-zpc. Do not run directly.

# Exit code for a flip that named no evidence. Distinct from 1 (usage/lookup)
# so a caller can tell "you asked wrong" from "you were refused".
ZPC_POSITION_REFUSED=2

_position_help() {
    cat << 'EOF'
Usage: agent-zpc position <add|flip|list|show> [args]

An epistemic ledger. A position is a verdict you are willing to be wrong
about in a named way: without a falsifier it is a mood, and a verdict that
moves without named evidence is capitulation, not judgment. The ledger
refuses both.

  position add "<claim>" --verdict "<v>" --confidence low|med|high \
      --falsifier "<what would change the verdict>"
      All four are required. No --falsifier, no row.

  position flip <id> --evidence "<what changed, and where it came from>" \
      [--verdict "<new verdict>" --falsifier "<its falsifier>"]
      Records the reversal with its reason. Without --evidence this exits 2,
      quotes the falsifier you wrote, and writes nothing.
      Omit --verdict and the position is withdrawn: the evidence broke the
      old verdict and no replacement was offered. Supply --verdict and you
      must supply the new verdict's --falsifier with it.

  position list                 One line per position, newest last.
  position show <id>            Full row including flip history.

Storage: .zpc/memory/positions.jsonl (append-only rows, in-place flips).

Examples:
  agent-zpc position add "the proxy corrupts the payload" \
      --verdict "content-encoding is double-applied" --confidence med \
      --falsifier "a byte-identical body across the hop"
  agent-zpc position flip pos-1a2b3c \
      --evidence "curl --raw shows identical bytes both sides (run 2026-07-27)"
EOF
}

# Normalize the confidence vocabulary. Three levels, no numbers: a decimal
# confidence invites false precision on a judgment that has none.
_position_confidence() {
    case "$1" in
        low) printf 'low' ;;
        med|medium) printf 'med' ;;
        high) printf 'high' ;;
        *) return 1 ;;
    esac
}

_position_file() {
    printf '%s' "$ZPC_MEMORY_DIR/positions.jsonl"
}

# Print the stored row for an id, or fail if there is none.
_position_lookup() {
    local file="$1" id="$2"
    [[ -f "$file" && -s "$file" ]] || return 1
    python3 << 'PYTHON' - "$file" "$id"
import json, sys

path, pid = sys.argv[1], sys.argv[2]
with open(path) as handle:
    for line in handle:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("id") == pid:
            print(json.dumps(obj, ensure_ascii=False))
            sys.exit(0)
sys.exit(1)
PYTHON
}

_position_add() {
    ensure_zpc

    local claim="" verdict="" confidence="" falsifier=""
    local positionals=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --verdict|-v) verdict="${2:-}"; shift 2 ;;
            --confidence) confidence="${2:-}"; shift 2 ;;
            --falsifier|-f) falsifier="${2:-}"; shift 2 ;;
            --help|-h) _position_help; return 0 ;;
            *) positionals+=("$1"); shift ;;
        esac
    done

    claim="${positionals[0]:-}"

    [[ -n "$claim" ]] || die "Usage: agent-zpc position add \"<claim>\" --verdict \"<v>\" --confidence low|med|high --falsifier \"<what would change it>\""
    [[ -n "$verdict" ]] || die "A position needs a verdict. Add --verdict \"<your call on the claim>\"."
    [[ -n "$confidence" ]] || die "A position needs a confidence. Add --confidence low|med|high."

    local level
    level="$(_position_confidence "$confidence")" || die "Confidence must be low, med, or high (got: $confidence)."

    # The refusal this ledger exists for. Nothing is written.
    [[ -n "$falsifier" ]] || die "An opinion without a falsifier is a mood. Add --falsifier \"<the evidence that would change this verdict>\" — nothing was written."

    local file
    file="$(_position_file)"
    mkdir -p "$ZPC_MEMORY_DIR"

    local json_line
    json_line=$(python3 << 'PYTHON' - "$file" "$claim" "$verdict" "$level" "$falsifier"
import json, os, secrets, sys
from datetime import datetime, timezone

path, claim, verdict, confidence, falsifier = sys.argv[1:6]

taken = set()
if os.path.exists(path):
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                taken.add(json.loads(line).get("id"))
            except json.JSONDecodeError:
                pass

while True:
    pid = "pos-" + secrets.token_hex(3)
    if pid not in taken:
        break

entry = {
    "id": pid,
    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "claim": claim,
    "verdict": verdict,
    "confidence": confidence,
    "falsifier": falsifier,
    "flips": [],
}
with open(path, "a") as handle:
    handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
print(json.dumps(entry, ensure_ascii=False))
PYTHON
    ) || die "Could not write to $file"

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$json_line"
    else
        local pid
        pid=$(printf '%s' "$json_line" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
        echo "Position $pid recorded: $verdict (confidence: $level)"
        echo "  falsifier: $falsifier"
    fi
}

_position_flip() {
    ensure_zpc

    local id="" evidence="" verdict="" falsifier=""
    local positionals=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --evidence|-e) evidence="${2:-}"; shift 2 ;;
            --verdict|-v) verdict="${2:-}"; shift 2 ;;
            --falsifier|-f) falsifier="${2:-}"; shift 2 ;;
            --help|-h) _position_help; return 0 ;;
            *) positionals+=("$1"); shift ;;
        esac
    done

    id="${positionals[0]:-}"
    [[ -n "$id" ]] || die "Usage: agent-zpc position flip <id> --evidence \"<what changed, and where it came from>\""

    local file row
    file="$(_position_file)"
    row=$(_position_lookup "$file" "$id") || die "No position with id '$id'. Run 'agent-zpc position list'."

    # The refusal. Read the row first so the message can quote the falsifier
    # the author wrote for themselves; nothing is mutated on this path.
    if [[ -z "$evidence" ]]; then
        local refusal
        refusal=$(python3 << 'PYTHON' - "$row"
import json, sys

p = json.loads(sys.argv[1])
print(
    "Refused: a flip needs named evidence.\n\n"
    f"  Position {p['id']}: {p.get('claim', '')}\n"
    f"  Standing verdict: {p.get('verdict', '')} (confidence: {p.get('confidence', '')})\n"
    f"  Your falsifier:   {p.get('falsifier', '')}\n\n"
    "Nothing was written. Name the evidence that met that falsifier:\n"
    f"  agent-zpc position flip {p['id']} --evidence \"<what changed, and where it came from>\"\n\n"
    "Pushback is not evidence. A verdict that moves without one is capitulation."
)
PYTHON
        )
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_error "$refusal" "$ZPC_POSITION_REFUSED" || true
        else
            printf '%s\n' "$refusal" >&2
        fi
        exit "$ZPC_POSITION_REFUSED"
    fi

    # A new verdict is a new opinion, and it needs its own falsifier for the
    # same reason the first one did.
    if [[ -n "$verdict" && -z "$falsifier" ]]; then
        die "A new verdict needs its own falsifier. Add --falsifier \"<what would change this one>\" — nothing was written."
    fi

    local updated
    updated=$(python3 << 'PYTHON' - "$file" "$id" "$evidence" "$verdict" "$falsifier"
import json, os, sys, tempfile
from datetime import datetime, timezone

path, pid, evidence, new_verdict, new_falsifier = sys.argv[1:6]
stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

rows = []
flipped = None
with open(path) as handle:
    for line in handle:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            rows.append(line)
            continue
        if obj.get("id") == pid and flipped is None:
            # No stated replacement withdraws the verdict: the evidence broke
            # it and nothing was offered in its place.
            verdict = new_verdict or "withdrawn"
            obj.setdefault("flips", []).append(
                {"ts": stamp, "evidence": evidence, "new_verdict": verdict}
            )
            obj["verdict"] = verdict
            if new_falsifier:
                obj["falsifier"] = new_falsifier
            flipped = obj
        rows.append(json.dumps(obj, ensure_ascii=False))

if flipped is None:
    sys.exit(1)

directory = os.path.dirname(path) or "."
handle_fd, temp_path = tempfile.mkstemp(dir=directory)
with os.fdopen(handle_fd, "w") as handle:
    handle.write("\n".join(rows) + "\n")
os.replace(temp_path, path)
print(json.dumps(flipped, ensure_ascii=False))
PYTHON
    ) || die "Flip failed to write; position '$id' is unchanged."

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$updated"
    else
        local new_verdict
        new_verdict=$(printf '%s' "$updated" | python3 -c 'import json,sys; print(json.load(sys.stdin)["verdict"])')
        echo "Position $id flipped: $new_verdict"
        echo "  evidence: $evidence"
    fi
}

_position_list() {
    ensure_zpc

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h) _position_help; return 0 ;;
            *) shift ;;
        esac
    done

    log_access "position"

    local file
    file="$(_position_file)"

    local rendered
    rendered=$(python3 << 'PYTHON' - "$file" "${OUTPUT_FORMAT:-text}"
import json, os, sys

path, fmt = sys.argv[1], sys.argv[2]

rows = []
if os.path.exists(path):
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass

if fmt == "json":
    print(json.dumps({"positions": rows, "count": len(rows)}, ensure_ascii=False))
    sys.exit(0)

if not rows:
    print("No positions recorded. Start one with 'agent-zpc position add'.")
    sys.exit(0)

print(f"{len(rows)} position(s):\n")
for row in rows:
    flips = row.get("flips", []) or []
    print(f"{row.get('id', '?')}  {row.get('confidence', '?'):<4}  {row.get('ts', '')[:10]}  flips:{len(flips)}")
    print(f"  claim:   {row.get('claim', '')}")
    print(f"  verdict: {row.get('verdict', '')}")
PYTHON
    )

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$rendered"
    else
        printf '%s\n' "$rendered"
    fi
}

_position_show() {
    ensure_zpc

    local id=""
    local positionals=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h) _position_help; return 0 ;;
            *) positionals+=("$1"); shift ;;
        esac
    done

    id="${positionals[0]:-}"
    [[ -n "$id" ]] || die "Usage: agent-zpc position show <id>"

    log_access "position"

    local file row
    file="$(_position_file)"
    row=$(_position_lookup "$file" "$id") || die "No position with id '$id'. Run 'agent-zpc position list'."

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$row"
        return 0
    fi

    python3 << 'PYTHON' - "$row"
import json, sys

p = json.loads(sys.argv[1])
print(p.get("id", "?"))
print(f"  recorded:   {p.get('ts', '')}")
print(f"  claim:      {p.get('claim', '')}")
print(f"  verdict:    {p.get('verdict', '')}")
print(f"  confidence: {p.get('confidence', '')}")
print(f"  falsifier:  {p.get('falsifier', '')}")
flips = p.get("flips", []) or []
print(f"  flips:      {len(flips)}")
for flip in flips:
    print(f"    {flip.get('ts', '')}  ->  {flip.get('new_verdict', '')}")
    print(f"      evidence: {flip.get('evidence', '')}")
PYTHON
}

cmd_position() {
    local sub="${1:-list}"
    shift 2>/dev/null || true

    case "$sub" in
        add|record) _position_add "$@" ;;
        flip|reverse) _position_flip "$@" ;;
        list) _position_list "$@" ;;
        show) _position_show "$@" ;;
        help|--help|-h) _position_help ;;
        *) die "Unknown position subcommand: $sub (add|flip|list|show)" ;;
    esac
}
