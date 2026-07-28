#!/usr/bin/env bash
# Integration tests for manna
# Usage: ./test/integration.sh

set -euo pipefail

# ============================================================================
# Setup
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANNA="$SCRIPT_DIR/../agent-manna"
TEST_DIR=$(mktemp -d)
PASSED=0
FAILED=0

# Build the Rust binary so this test validates the current source tree.
if ! cargo build --release --quiet --manifest-path "$SCRIPT_DIR/../Cargo.toml"; then
    echo "ERROR: cargo build --release failed"
    exit 2
fi

MANNA_CORE="$SCRIPT_DIR/../target/release/manna-core"
if [[ ! -x "$MANNA_CORE" ]]; then
    echo "ERROR: expected Rust binary not found at $MANNA_CORE"
    exit 2
fi

if [[ ! -x "$MANNA" ]]; then
    echo "ERROR: manna wrapper not executable at $MANNA"
    exit 2
fi

cleanup() {
    rm -rf "$TEST_DIR"
}
trap cleanup EXIT

cd "$TEST_DIR"

# Set unique session ID for tests
export MANNA_SESSION_ID="ses_test_$$"

# ============================================================================
# Test Helpers
# ============================================================================

pass() {
    echo "  ✓ $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo "  ✗ $1"
    echo "    $2"
    FAILED=$((FAILED + 1))
}

# Check YAML output starts with expected prefix
check_yaml() {
    local output="$1"
    local expected="$2"
    local desc="$3"
    
    if [[ "$output" == *"$expected"* ]]; then
        pass "$desc"
    else
        fail "$desc" "Expected '$expected' in output, got: $output"
    fi
}

# Check exit code is expected
check_exit() {
    local expected="$1"
    local actual="$2"
    local desc="$3"
    
    if [[ "$actual" -eq "$expected" ]]; then
        pass "$desc"
    else
        fail "$desc" "Expected exit code $expected, got $actual"
    fi
}

# Extract ID from YAML output (id: mn-xxxxxx)
extract_id() {
    local output="$1"
    echo "$output" | grep -o 'id: mn-[a-f0-9]*' | head -1 | awk '{print $2}'
}

# ============================================================================
# Test Suite
# ============================================================================

echo "=== Manna Integration Tests ==="
echo "Test directory: $TEST_DIR"
echo "Session ID: $MANNA_SESSION_ID"
echo ""

# ----------------------------------------------------------------------------
# Test 1: Init
# ----------------------------------------------------------------------------
echo "Test 1: init"
output=$("$MANNA" init 2>&1) || true
check_yaml "$output" "success: true" "init returns success"
[[ -d .manna ]] && pass ".manna directory created" || fail ".manna directory created" "Directory not found"
[[ -f .manna/issues.jsonl ]] && pass "issues.jsonl created" || fail "issues.jsonl created" "File not found"

# ----------------------------------------------------------------------------
# Test 2: Create issues
# ----------------------------------------------------------------------------
echo ""
echo "Test 2: create"
output=$("$MANNA" create "First issue" "Description for first issue" 2>&1) || true
check_yaml "$output" "success: true" "create returns success"
ID1=$(extract_id "$output")
[[ -n "$ID1" ]] && pass "ID extracted: $ID1" || fail "ID extraction" "Could not extract ID from output"

output=$("$MANNA" create "Second issue" 2>&1) || true
check_yaml "$output" "success: true" "create second issue"
ID2=$(extract_id "$output")
[[ -n "$ID2" ]] && pass "ID extracted: $ID2" || fail "ID extraction" "Could not extract ID"

output=$("$MANNA" create "Third issue for blocking" 2>&1) || true
ID3=$(extract_id "$output")
[[ -n "$ID3" ]] && pass "ID extracted: $ID3" || fail "ID extraction" "Could not extract ID"

# ----------------------------------------------------------------------------
# Test 3: List issues
# ----------------------------------------------------------------------------
echo ""
echo "Test 3: list"
output=$("$MANNA" list 2>&1) || true
check_yaml "$output" "success: true" "list returns success"
check_yaml "$output" "issues:" "list contains issues array"
check_yaml "$output" "$ID1" "list contains first issue"
check_yaml "$output" "$ID2" "list contains second issue"

# Test list with status filter
output=$("$MANNA" list --status open 2>&1) || true
check_yaml "$output" "success: true" "list --status open returns success"
check_yaml "$output" "status: open" "list shows open issues"

# ----------------------------------------------------------------------------
# Test 4: Show issue
# ----------------------------------------------------------------------------
echo ""
echo "Test 4: show"
output=$("$MANNA" show "$ID1" 2>&1) || true
check_yaml "$output" "success: true" "show returns success"
check_yaml "$output" "$ID1" "show contains correct ID"
check_yaml "$output" "First issue" "show contains title"
check_yaml "$output" "Description for first issue" "show contains description"

# ----------------------------------------------------------------------------
# Test 5: Claim issue
# ----------------------------------------------------------------------------
echo ""
echo "Test 5: claim"
output=$("$MANNA" claim "$ID1" 2>&1) || true
check_yaml "$output" "success: true" "claim returns success"
check_yaml "$output" "status: in_progress" "claim sets status to in_progress"
check_yaml "$output" "$MANNA_SESSION_ID" "claim sets claimed_by to session"

# ----------------------------------------------------------------------------
# Test 6: Status
# ----------------------------------------------------------------------------
echo ""
echo "Test 6: status"
output=$("$MANNA" status 2>&1) || true
check_yaml "$output" "success: true" "status returns success"
check_yaml "$output" "$MANNA_SESSION_ID" "status shows session ID"
check_yaml "$output" "$ID1" "status shows claimed issue"

# ----------------------------------------------------------------------------
# Test 7: Block
# ----------------------------------------------------------------------------
echo ""
echo "Test 7: block"
output=$("$MANNA" block "$ID2" "$ID3" 2>&1) || true
check_yaml "$output" "success: true" "block returns success"
check_yaml "$output" "status: blocked" "block sets status to blocked"
check_yaml "$output" "$ID3" "block shows blocker ID"

# Verify blocked issue shows in list
output=$("$MANNA" list --status blocked 2>&1) || true
check_yaml "$output" "$ID2" "blocked issue appears in filtered list"

# ----------------------------------------------------------------------------
# Test 8: Unblock
# ----------------------------------------------------------------------------
echo ""
echo "Test 8: unblock"
output=$("$MANNA" unblock "$ID2" "$ID3" 2>&1) || true
check_yaml "$output" "success: true" "unblock returns success"
check_yaml "$output" "status: open" "unblock reverts status to open"

# ----------------------------------------------------------------------------
# Test 9: Done
# ----------------------------------------------------------------------------
echo ""
echo "Test 9: done"
output=$("$MANNA" done "$ID1" 2>&1) || true
check_yaml "$output" "success: true" "done returns success"
check_yaml "$output" "status: done" "done sets status to done"

# Verify done issue shows in list
output=$("$MANNA" list --status done 2>&1) || true
check_yaml "$output" "$ID1" "done issue appears in filtered list"

# ----------------------------------------------------------------------------
# Test 10: Abandon
# ----------------------------------------------------------------------------
echo ""
echo "Test 10: abandon"
# First claim ID2
"$MANNA" claim "$ID2" >/dev/null 2>&1 || true
output=$("$MANNA" abandon "$ID2" 2>&1) || true
check_yaml "$output" "success: true" "abandon returns success"
check_yaml "$output" "status: open" "abandon reverts status to open"

# ----------------------------------------------------------------------------
# Test 11: Context
# ----------------------------------------------------------------------------
echo ""
echo "Test 11: context"
output=$("$MANNA" context 2>&1) || true
check_yaml "$output" "success: true" "context returns success"
check_yaml "$output" "context:" "context contains context field"
check_yaml "$output" "Manna Context" "context contains header"

# Test with max-tokens
output=$("$MANNA" context --max-tokens 100 2>&1) || true
check_yaml "$output" "success: true" "context with max-tokens returns success"

# ============================================================================
# Edge Case Tests
# ============================================================================

echo ""
echo "=== Edge Case Tests ==="

# ----------------------------------------------------------------------------
# Test E1: Claim already-claimed issue
# ----------------------------------------------------------------------------
echo ""
echo "Test E1: claim already-claimed issue"
"$MANNA" claim "$ID3" >/dev/null 2>&1 || true  # First claim

# Try to claim from different session
export MANNA_SESSION_ID="ses_other_$$"
output=$("$MANNA" claim "$ID3" 2>&1) || exit_code=$?
if [[ "$output" == *"success: false"* ]]; then
    pass "re-claim returns error"
else
    fail "re-claim returns error" "Expected success: false, got: $output"
fi
export MANNA_SESSION_ID="ses_test_$$"  # Restore

# ----------------------------------------------------------------------------
# Test E2: Done on non-existent ID
# ----------------------------------------------------------------------------
echo ""
echo "Test E2: done on non-existent ID"
output=$("$MANNA" done "mn-nonexistent" 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "done non-existent returns error"
check_yaml "$output" "not found" "error mentions not found"

# ----------------------------------------------------------------------------
# Test E3: Show non-existent ID
# ----------------------------------------------------------------------------
echo ""
echo "Test E3: show non-existent ID"
output=$("$MANNA" show "mn-nonexistent" 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "show non-existent returns error"

# ----------------------------------------------------------------------------
# Test E4: Invalid status filter
# ----------------------------------------------------------------------------
echo ""
echo "Test E4: invalid status filter"
output=$("$MANNA" list --status invalid 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "invalid status returns error"
check_yaml "$output" "Invalid status" "error mentions invalid status"

# ----------------------------------------------------------------------------
# Test E5: Empty title
# ----------------------------------------------------------------------------
echo ""
echo "Test E5: empty title"
output=$("$MANNA" create "" 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "empty title returns error"

# ----------------------------------------------------------------------------
# Test E6: Concurrent creates
# ----------------------------------------------------------------------------
echo ""
echo "Test E6: concurrent creates (10 parallel)"
cd "$TEST_DIR"
rm -rf .manna
"$MANNA" init >/dev/null 2>&1

# Spawn 10 parallel creates (suppress output)
for i in {1..10}; do
    "$MANNA" create "Concurrent issue $i" >/dev/null 2>&1 &
done
wait

# Verify all 10 issues were created (no corruption)
output=$("$MANNA" list 2>&1)
count=$(echo "$output" | grep -c "mn-" || true)
if [[ "$count" -eq 10 ]]; then
    pass "all 10 concurrent creates succeeded"
else
    fail "all 10 concurrent creates succeeded" "Expected 10 issues, got $count"
fi

# Verify JSONL file is valid (no partial lines)
lines=$(wc -l < .manna/issues.jsonl | tr -d ' ')
if [[ "$lines" -eq 10 ]]; then
    pass "JSONL file has correct line count"
else
    fail "JSONL file has correct line count" "Expected 10 lines, got $lines"
fi

# ----------------------------------------------------------------------------
# Test E7: Block with non-existent blocker
# ----------------------------------------------------------------------------
echo ""
echo "Test E7: block with non-existent blocker"
output=$("$MANNA" list 2>&1)
first_id=$(extract_id "$output")
output=$("$MANNA" block "$first_id" "mn-nonexistent" 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "block with non-existent blocker returns error"

# ----------------------------------------------------------------------------
# Test E8: Double init
# ----------------------------------------------------------------------------
echo ""
echo "Test E8: double init (should be idempotent)"
"$MANNA" init >/dev/null 2>&1
output=$("$MANNA" init 2>&1) || true
check_yaml "$output" "success: true" "second init succeeds"

# ============================================================================
# YAML Validation
# ============================================================================

echo ""
echo "=== YAML Validation ==="

# Check if yq is available for proper YAML validation
if command -v yq &>/dev/null; then
    output=$("$MANNA" list 2>&1)
    if echo "$output" | yq eval '.' - >/dev/null 2>&1; then
        pass "list output is valid YAML (yq)"
    else
        fail "list output is valid YAML (yq)" "yq parsing failed"
    fi
    
    output=$("$MANNA" context 2>&1)
    if echo "$output" | yq eval '.' - >/dev/null 2>&1; then
        pass "context output is valid YAML (yq)"
    else
        fail "context output is valid YAML (yq)" "yq parsing failed"
    fi
else
    # Basic validation: check YAML-like structure
    output=$("$MANNA" list 2>&1)
    if [[ "$output" =~ ^success: ]] && [[ "$output" =~ issues: ]]; then
        pass "list output has YAML structure (basic check)"
    else
        fail "list output has YAML structure (basic check)" "Missing expected fields"
    fi
    
    output=$("$MANNA" context 2>&1)
    if [[ "$output" =~ ^success: ]] && [[ "$output" =~ context: ]]; then
        pass "context output has YAML structure (basic check)"
    else
        fail "context output has YAML structure (basic check)" "Missing expected fields"
    fi
fi

# ============================================================================
# Board Grammar Tests (types, tracks, dream, lint, reconcile)
# ============================================================================

echo ""
echo "=== Board Grammar Tests ==="

GRAMMAR_DIR=$(mktemp -d)
GRAMMAR_PHYS=$(cd "$GRAMMAR_DIR" && pwd -P)
cd "$GRAMMAR_DIR"
"$MANNA" init >/dev/null 2>&1

# ----------------------------------------------------------------------------
# Test G1: types and track edges
# ----------------------------------------------------------------------------
echo ""
echo "Test G1: types and track edges"
output=$("$MANNA" create "Umbrella track" --type track 2>&1) || true
check_yaml "$output" "success: true" "create --type track succeeds"
check_yaml "$output" "type: track" "created issue carries type track"
TRACK_ID=$(extract_id "$output")

output=$("$MANNA" create "Tracked item" --track "$TRACK_ID" --source "test/integration.sh" 2>&1) || true
check_yaml "$output" "success: true" "create --track succeeds"
check_yaml "$output" "track: $TRACK_ID" "created item carries track edge"
check_yaml "$output" "source: test/integration.sh" "created item carries source"
ITEM_ID=$(extract_id "$output")

output=$("$MANNA" create "Bad edge" --track "$ITEM_ID" 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "--track to a non-track errors"
check_yaml "$output" "not a track" "error names the non-track target"

output=$("$MANNA" create "Ghost edge" --track "mn-404404" 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "--track to a missing id errors"

output=$("$MANNA" create "Nested track" --type track --track "$TRACK_ID" 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "tracks don't nest on create"

output=$("$MANNA" update "$ITEM_ID" --type track 2>&1) || exit_code=$?
check_yaml "$output" "success: false" "update --type track with a track edge errors"

output=$("$MANNA" list --type track 2>&1) || true
check_yaml "$output" "$TRACK_ID" "list --type track finds the track"
if [[ "$output" != *"$ITEM_ID"* ]]; then
    pass "list --type track excludes items"
else
    fail "list --type track excludes items" "item leaked into track filter: $output"
fi

output=$("$MANNA" list --track "$TRACK_ID" 2>&1) || true
check_yaml "$output" "$ITEM_ID" "list --track finds track members"

# ----------------------------------------------------------------------------
# Test G2: dream walks up to the nearest board
# ----------------------------------------------------------------------------
echo ""
echo "Test G2: dream on local board"
mkdir -p "$GRAMMAR_DIR/sub/dir"
cd "$GRAMMAR_DIR/sub/dir"
output=$("$MANNA" dream "A spark from below" --source "shower" 2>&1) || true
check_yaml "$output" "success: true" "dream succeeds from a subdirectory"
check_yaml "$output" "type: dream" "dream carries type dream"
check_yaml "$output" "board: $GRAMMAR_PHYS" "dream walked up to the nearest board"
DREAM_ID=$(extract_id "$output")
cd "$GRAMMAR_DIR"
output=$("$MANNA" show "$DREAM_ID" 2>&1) || true
check_yaml "$output" "A spark from below" "dream landed on the walk-up board"

# ----------------------------------------------------------------------------
# Test G3: dream global inbox fallback
# ----------------------------------------------------------------------------
echo ""
echo "Test G3: dream global inbox fallback"
INBOX_HOME=$(mktemp -d)
NOBOARD_DIR=$(mktemp -d)
cd "$NOBOARD_DIR"
output=$(AGENT_DO_HOME="$INBOX_HOME" "$MANNA" dream "Homeless spark" 2>&1) || true
check_yaml "$output" "success: true" "dream succeeds with no board in sight"
check_yaml "$output" "filed to global inbox" "dream reports the inbox fallback"
if [[ -f "$INBOX_HOME/inbox/.manna/issues.jsonl" ]]; then
    pass "inbox board auto-initialized"
else
    fail "inbox board auto-initialized" "no issues.jsonl under $INBOX_HOME/inbox/.manna"
fi
cd "$GRAMMAR_DIR"
rm -rf "$INBOX_HOME" "$NOBOARD_DIR"

# ----------------------------------------------------------------------------
# Test G4: lint gate
# ----------------------------------------------------------------------------
echo ""
echo "Test G4: lint"
# Board so far: track + tracked item + open dream (untracked dreams are fine)
lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 0 "$lint_exit" "lint exits 0 on a clean board"
check_yaml "$output" "clean: true" "lint reports clean"

output=$("$MANNA" create "Loose item" 2>&1) || true
LOOSE_ID=$(extract_id "$output")
lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 1 "$lint_exit" "lint exits 1 with findings"
check_yaml "$output" "untracked_item" "lint names the untracked_item rule"
check_yaml "$output" "$LOOSE_ID" "lint names the loose item"

"$MANNA" update "$LOOSE_ID" --track "$TRACK_ID" >/dev/null 2>&1 || true
lint_exit=0
output=$("$MANNA" lint --json 2>&1) || lint_exit=$?
check_exit 0 "$lint_exit" "lint exits 0 after attaching the item"
check_yaml "$output" '"clean":true' "lint --json reports clean"

# ----------------------------------------------------------------------------
# Test G5: reconcile
# ----------------------------------------------------------------------------
echo ""
echo "Test G5: reconcile"
# Manufacture a blocker desync: A blocks B, A completes, B stays blocked.
output=$("$MANNA" create "Blocker work" --track "$TRACK_ID" 2>&1) || true
A_ID=$(extract_id "$output")
output=$("$MANNA" create "Dependent work" --track "$TRACK_ID" 2>&1) || true
B_ID=$(extract_id "$output")
"$MANNA" block "$B_ID" "$A_ID" >/dev/null 2>&1
"$MANNA" claim "$A_ID" >/dev/null 2>&1
"$MANNA" done "$A_ID" >/dev/null 2>&1

rec_exit=0
output=$("$MANNA" reconcile 2>&1) || rec_exit=$?
check_exit 0 "$rec_exit" "reconcile exits 0 (advisory)"
check_yaml "$output" "blocker_desync" "reconcile detects the blocker desync"
check_yaml "$output" "$B_ID" "reconcile names the desynced issue"

output=$("$MANNA" show "$B_ID" 2>&1) || true
check_yaml "$output" "status: blocked" "reconcile without --fix mutates nothing"

rec_exit=0
output=$("$MANNA" reconcile --write-drift 2>&1) || rec_exit=$?
check_exit 0 "$rec_exit" "reconcile --write-drift exits 0"
if [[ -f .manna/drift.yaml ]]; then
    pass "drift.yaml written"
else
    fail "drift.yaml written" "missing .manna/drift.yaml"
fi
if command -v yq &>/dev/null; then
    if yq eval '.' .manna/drift.yaml >/dev/null 2>&1; then
        pass "drift.yaml is valid YAML (yq)"
    else
        fail "drift.yaml is valid YAML (yq)" "yq parsing failed"
    fi
fi
if grep -q "generated_at:" .manna/drift.yaml && grep -q "findings:" .manna/drift.yaml; then
    pass "drift.yaml has the pinned shape"
else
    fail "drift.yaml has the pinned shape" "missing generated_at/findings keys"
fi
if grep -q "kind: blocker_desync" .manna/drift.yaml; then
    pass "drift.yaml carries the finding"
else
    fail "drift.yaml carries the finding" "no blocker_desync entry"
fi

rec_exit=0
output=$("$MANNA" reconcile --fix 2>&1) || rec_exit=$?
check_exit 0 "$rec_exit" "reconcile --fix exits 0"
output=$("$MANNA" show "$B_ID" 2>&1) || true
check_yaml "$output" "status: open" "reconcile --fix unblocked the dependent"

output=$("$MANNA" reconcile --dream-age-days 0 --json 2>&1) || true
check_yaml "$output" "stale_dream" "reconcile --dream-age-days 0 flags the fresh dream"

# ----------------------------------------------------------------------------
# Test G6: context renders the track tree (and stays v1 without tracks)
# ----------------------------------------------------------------------------
echo ""
echo "Test G6: context track tree"
output=$("$MANNA" context 2>&1) || true
check_yaml "$output" "## Umbrella track ($TRACK_ID)" "context groups items under the track"
check_yaml "$output" "## Dreams" "context renders a Dreams section"
check_yaml "$output" "$DREAM_ID" "context lists the dream"
if [[ "$output" != *"$A_ID"* ]]; then
    pass "context still excludes done issues"
else
    fail "context still excludes done issues" "done issue leaked: $output"
fi
if [[ "$output" != *"## Open Issues"* ]]; then
    pass "track tree replaces the by-status sections"
else
    fail "track tree replaces the by-status sections" "v1 sections leaked into grouped render"
fi

UNTYPED_DIR=$(mktemp -d)
cd "$UNTYPED_DIR"
"$MANNA" init >/dev/null 2>&1
"$MANNA" create "Plain issue" >/dev/null 2>&1
output=$("$MANNA" context 2>&1) || true
check_yaml "$output" "## Open Issues (1)" "untyped board keeps the v1 render"
if [[ "$output" != *"## Untracked"* && "$output" != *"## Dreams"* ]]; then
    pass "untyped board has no tree sections"
else
    fail "untyped board has no tree sections" "tree sections leaked: $output"
fi
cd "$GRAMMAR_DIR"
rm -rf "$UNTYPED_DIR"

cd "$TEST_DIR"
rm -rf "$GRAMMAR_DIR"

# ----------------------------------------------------------------------------
# Test G7: prompt pairing (--prompt field, lint existence, reconcile pairing)
# ----------------------------------------------------------------------------
echo ""
echo "Test G7: prompt pairing"
PAIR_DIR=$(mktemp -d)
PAIR_PHYS=$(cd "$PAIR_DIR" && pwd -P)
cd "$PAIR_DIR"
"$MANNA" init >/dev/null 2>&1
mkdir -p .dev/session-prompts
PROMPT_A="$PAIR_PHYS/.dev/session-prompts/lane-a.md"
PROMPT_B="$PAIR_PHYS/.dev/session-prompts/lane-b.md"

output=$("$MANNA" create "Paired work" --prompt "$PROMPT_A" 2>&1) || true
check_yaml "$output" "success: true" "create --prompt succeeds before the file exists"
PAIR_ID=$(extract_id "$output")

output=$("$MANNA" show "$PAIR_ID" 2>&1) || true
check_yaml "$output" "prompt: $PROMPT_A" "show displays the prompt pointer"

lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 1 "$lint_exit" "lint exits 1 on a missing prompt file"
check_yaml "$output" "prompt_file" "lint names the prompt_file rule"
check_yaml "$output" "$PAIR_ID" "lint names the pointing issue"

printf '# Lane A work order (%s)\nClaim first: agent-do manna claim %s\n' "$PAIR_ID" "$PAIR_ID" > "$PROMPT_A"
lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 0 "$lint_exit" "lint exits 0 once the prompt file exists"

rec_exit=0
output=$("$MANNA" reconcile --json 2>&1) || rec_exit=$?
check_exit 0 "$rec_exit" "reconcile exits 0 on a paired board"
if [[ "$output" != *"prompt_pairing"* ]]; then
    pass "correctly paired board reports no prompt_pairing finding"
else
    fail "correctly paired board reports no prompt_pairing finding" "unexpected finding: $output"
fi

output=$("$MANNA" create "Pointerless work" 2>&1) || true
LONE_ID=$(extract_id "$output")
# A bare id mention is data, not a pairing promise: no finding without a claim command.
printf '# Lane B notes: relates to %s\n' "$LONE_ID" > "$PROMPT_B"
output=$("$MANNA" reconcile --json 2>&1) || true
if [[ "$output" != *"prompt_pairing"* ]]; then
    pass "bare id mention without a claim command produces no finding"
else
    fail "bare id mention without a claim command produces no finding" "unexpected finding: $output"
fi

printf 'Claim: agent-do manna claim %s\n' "$LONE_ID" >> "$PROMPT_B"
output=$("$MANNA" reconcile --json 2>&1) || true
check_yaml "$output" "prompt_pairing" "reconcile flags a claim command whose issue lacks a pointer"
check_yaml "$output" "$LONE_ID" "reconcile names the pointerless issue"

output=$("$MANNA" update "$LONE_ID" --prompt "$PROMPT_B" 2>&1) || true
check_yaml "$output" "success: true" "update --prompt succeeds"
output=$("$MANNA" reconcile --json 2>&1) || true
if [[ "$output" != *"prompt_pairing"* ]]; then
    pass "pointer repair clears the pairing finding"
else
    fail "pointer repair clears the pairing finding" "finding persisted: $output"
fi

cd "$TEST_DIR"
rm -rf "$PAIR_DIR"

# ----------------------------------------------------------------------------
# Test G8: dreams are visible and inert until converted
# ----------------------------------------------------------------------------
echo ""
echo "Test G8: dream claim gate"
GATE_DIR=$(mktemp -d)
cd "$GATE_DIR"
"$MANNA" init >/dev/null 2>&1
output=$("$MANNA" create "Umbrella track" --type track 2>&1) || true
G_TRACK=$(extract_id "$output")
output=$("$MANNA" create "Real work" --track "$G_TRACK" 2>&1) || true
G_ITEM=$(extract_id "$output")
output=$("$MANNA" dream "A parked spark" 2>&1) || true
G_DREAM=$(extract_id "$output")

# The refusal must not touch the board: hash the file on both sides.
if command -v md5 &>/dev/null; then
    hash_cmd() { md5 -q "$1"; }
else
    hash_cmd() { md5sum "$1" | awk '{print $1}'; }
fi
before_hash=$(hash_cmd .manna/issues.jsonl)
claim_exit=0
output=$("$MANNA" claim "$G_DREAM" 2>&1) || claim_exit=$?
after_hash=$(hash_cmd .manna/issues.jsonl)

check_exit 2 "$claim_exit" "claim on a dream exits 2"
check_yaml "$output" "success: false" "claim on a dream refuses"
check_yaml "$output" "$G_DREAM" "refusal names the dream id"
check_yaml "$output" "not claimable work" "refusal says a dream is not claimable work"
check_yaml "$output" "update $G_DREAM --type item" "refusal gives the exact conversion command"
check_yaml "$output" "Erik" "refusal names who authorizes"
if [[ "$before_hash" == "$after_hash" ]]; then
    pass "refused claim wrote nothing (board byte-identical)"
else
    fail "refused claim wrote nothing (board byte-identical)" "issues.jsonl changed: $before_hash -> $after_hash"
fi
output=$("$MANNA" show "$G_DREAM" 2>&1) || true
check_yaml "$output" "status: open" "refused dream is still open"
check_yaml "$output" "type: dream" "refused dream is still a dream"
if [[ "$output" != *"claimed_by"* ]]; then
    pass "refused dream carries no claim"
else
    fail "refused dream carries no claim" "claimed_by present: $output"
fi

# Visibility is the ruling: the dream stays in every list, marked inert.
output=$("$MANNA" list 2>&1) || true
check_yaml "$output" "$G_DREAM" "list still shows the dream"
check_yaml "$output" "not claimable, needs conversion" "list marks the dream inert"
output=$("$MANNA" list --json 2>&1) || true
check_yaml "$output" '"gate":"[DREAM: not claimable, needs conversion]"' "list --json carries the gate marker"
output=$("$MANNA" context 2>&1) || true
check_yaml "$output" "$G_DREAM" "context still shows the dream"
check_yaml "$output" "$G_DREAM: A parked spark [open] [DREAM: not claimable, needs conversion]" \
    "context marks the dream row inert"
check_yaml "$output" "update <id> --type item" "context spells out the conversion command"

# Items are untouched by the gate.
claim_exit=0
output=$("$MANNA" claim "$G_ITEM" 2>&1) || claim_exit=$?
check_exit 0 "$claim_exit" "claim on an item still succeeds"
check_yaml "$output" "status: in_progress" "claimed item goes in_progress"
"$MANNA" abandon "$G_ITEM" >/dev/null 2>&1

# Conversion is the authorization act.
output=$("$MANNA" update "$G_DREAM" --type item 2>&1) || true
check_yaml "$output" "AUTHORIZED" "conversion prints an authorization line"
check_yaml "$output" "now claimable work" "authorization line says the row is claimable"
claim_exit=0
output=$("$MANNA" claim "$G_DREAM" 2>&1) || claim_exit=$?
check_exit 0 "$claim_exit" "claim succeeds after conversion"
check_yaml "$output" "status: in_progress" "converted dream claims like any item"

# And back: parking an item prints the inverse and restores the gate.
"$MANNA" abandon "$G_DREAM" >/dev/null 2>&1
output=$("$MANNA" update "$G_DREAM" --type dream 2>&1) || true
check_yaml "$output" "PARKED" "parking prints the inverse line"
check_yaml "$output" "no longer claimable" "inverse line says the row is not claimable"
claim_exit=0
"$MANNA" claim "$G_DREAM" >/dev/null 2>&1 || claim_exit=$?
check_exit 2 "$claim_exit" "re-parked dream refuses claim again"

# A non-crossing edit stays silent.
output=$("$MANNA" update "$G_ITEM" --title "Real work, renamed" 2>&1) || true
if [[ "$output" != *"authorization"* ]]; then
    pass "non-crossing update prints no authorization line"
else
    fail "non-crossing update prints no authorization line" "unexpected line: $output"
fi

cd "$TEST_DIR"
rm -rf "$GATE_DIR"

# ============================================================================
# Summary
# ============================================================================

echo ""
echo "============================================"
echo "Test Summary: $PASSED passed, $FAILED failed"
echo "============================================"

if [[ "$FAILED" -gt 0 ]]; then
    echo ""
    echo "FAILED: Some tests did not pass"
    exit 1
else
    echo ""
    echo "All tests passed!"
    exit 0
fi
