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
CONCURRENT_DIR=$(mktemp -d)
cd "$CONCURRENT_DIR"
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

# Exactly one session may win a claim, and only that session may mutate it.
output=$("$MANNA" create "Atomic claim target" 2>&1)
RACE_ID=$(extract_id "$output")
for i in {1..10}; do
    (
        set +e
        MANNA_SESSION_ID="ses_racer_$i" "$MANNA" claim "$RACE_ID" >"claim.$i.out" 2>&1
        echo $? >"claim.$i.rc"
        exit 0
    ) &
done
wait
claim_winners=0
for i in {1..10}; do
    if [[ "$(cat "claim.$i.rc")" -eq 0 ]]; then
        claim_winners=$((claim_winners + 1))
    fi
done
check_exit 1 "$claim_winners" "concurrent claim has exactly one winner"
output=$("$MANNA" show "$RACE_ID" 2>&1)
RACE_OWNER=$(echo "$output" | awk '/claimed_by:/ {print $2; exit}')
intruder_exit=0
MANNA_SESSION_ID="ses_intruder" "$MANNA" done "$RACE_ID" >/dev/null 2>&1 || intruder_exit=$?
check_exit 1 "$intruder_exit" "non-owner cannot complete claimed work"
intruder_exit=0
MANNA_SESSION_ID="ses_intruder" "$MANNA" abandon "$RACE_ID" >/dev/null 2>&1 || intruder_exit=$?
check_exit 1 "$intruder_exit" "non-owner cannot abandon claimed work"
status_exit=0
MANNA_SESSION_ID="$RACE_OWNER" "$MANNA" update "$RACE_ID" --status done >/dev/null 2>&1 || status_exit=$?
check_exit 1 "$status_exit" "update --status cannot bypass lifecycle verbs"
MANNA_SESSION_ID="$RACE_OWNER" "$MANNA" abandon "$RACE_ID" >/dev/null 2>&1

cd "$TEST_DIR"
rm -rf "$CONCURRENT_DIR"

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
# Test G7: strict workflow pairing, claim gate, sprawl detection, legacy compatibility
# ----------------------------------------------------------------------------
echo ""
echo "Test G7: strict Manna and handoff workflow"
PAIR_DIR=$(mktemp -d)
cd "$PAIR_DIR"
git init -q
printf '.handoff/\n.manna/\n' > .gitignore
output=$("$MANNA" init 2>&1) || true
check_yaml "$output" "workflow: strict" "new board enables the strict workflow"
check_yaml "$output" "gitignore_updated: true" "init repairs a local .handoff ignore rule"
[[ -f .manna/workflow.yaml ]] && pass "init creates .manna/workflow.yaml" || fail "init creates .manna/workflow.yaml" "File not found"
[[ -f .manna/board.yaml ]] && pass "init pins strict board identity separately" || fail "init pins strict board identity separately" "File not found"
[[ -f .handoff/README.md ]] && pass "init creates .handoff/README.md" || fail "init creates .handoff/README.md" "File not found"
ignore_exit=0
git check-ignore --quiet -- .handoff/README.md || ignore_exit=$?
check_exit 1 "$ignore_exit" ".handoff is durable Git-visible state"
ignore_exit=0
git check-ignore --quiet -- .manna/workflow.yaml || ignore_exit=$?
check_exit 1 "$ignore_exit" ".manna is durable Git-visible state"
ignore_exit=0
git check-ignore --quiet -- .manna/issues.jsonl || ignore_exit=$?
check_exit 1 "$ignore_exit" "issues.jsonl is durable Git-visible state"

output=$("$MANNA" create "Paired work" 2>&1) || true
check_yaml "$output" "success: true" "create generates a paired item"
PAIR_ID=$(extract_id "$output")
PROMPT_A=".handoff/$PAIR_ID-paired-work.md"

output=$("$MANNA" show "$PAIR_ID" 2>&1) || true
check_yaml "$output" "prompt: $PROMPT_A" "show displays the prompt pointer"
[[ -f "$PROMPT_A" ]] && pass "create writes the canonical handoff" || fail "create writes the canonical handoff" "File not found"
claim_count=$(grep -c "agent-do manna claim $PAIR_ID" "$PROMPT_A" || true)
check_exit 1 "$claim_count" "handoff carries exactly one claim command"
check_yaml "$(sed -n '1,14p' "$PROMPT_A")" "base_commit:" "handoff binds its base commit"
check_yaml "$(sed -n '1,14p' "$PROMPT_A")" "binding: sha256:" "handoff carries its content binding"

rm -f .manna/workflow.yaml
claim_exit=0
output=$("$MANNA" claim "$PAIR_ID" 2>&1) || claim_exit=$?
check_exit 2 "$claim_exit" "deleting workflow.yaml cannot downgrade a strict board"
check_yaml "$output" "strict Manna board identity exists" "claim names the missing strict config"
output=$("$MANNA" init 2>&1) || true
check_yaml "$output" "restored_config: true" "init restores the independently pinned strict config"
[[ -f .manna/workflow.yaml ]] && pass "restored strict config exists" || fail "restored strict config exists" "File not found"

printf '.manna/issues.jsonl\n' >> .gitignore
claim_exit=0
output=$("$MANNA" claim "$PAIR_ID" 2>&1) || claim_exit=$?
check_exit 2 "$claim_exit" "claim fails when issues.jsonl is hidden from Git"
check_yaml "$output" "issues.jsonl is ignored" "claim names the hidden board file"
printf '!.manna/issues.jsonl\n' >> .gitignore

OUTSIDE_HANDOFF=$(mktemp -d)
ln -s "$OUTSIDE_HANDOFF" .handoff/escape
create_exit=0
output=$("$MANNA" create "Symlink escape" --prompt .handoff/escape/work.md 2>&1) || create_exit=$?
check_exit 1 "$create_exit" "strict create rejects a symlink escape"
check_yaml "$output" "crosses a symlink" "symlink refusal names the filesystem boundary"
rm -f .handoff/escape
rm -rf "$OUTSIDE_HANDOFF"

printf '\nSealed continuation context.\n' >> "$PROMPT_A"
claim_exit=0
"$MANNA" claim "$PAIR_ID" >/dev/null 2>&1 || claim_exit=$?
check_exit 2 "$claim_exit" "unsealed handoff edits block claim"
output=$("$MANNA" handoff seal "$PAIR_ID" 2>&1) || true
check_yaml "$output" "success: true" "handoff seal binds an intentional edit"
claim_exit=0
"$MANNA" claim "$PAIR_ID" >/dev/null 2>&1 || claim_exit=$?
check_exit 0 "$claim_exit" "sealed handoff becomes claimable"
"$MANNA" abandon "$PAIR_ID" >/dev/null 2>&1

before_rows=$(wc -l < .manna/issues.jsonl | tr -d ' ')
before_handoffs=$(find .handoff -name 'mn-*.md' -type f | wc -l | tr -d ' ')
printf '.handoff/mn-*.md\n' >> .gitignore
create_exit=0
output=$("$MANNA" create "Ignored handoff" 2>&1) || create_exit=$?
check_exit 2 "$create_exit" "create fails when a generated handoff would be ignored"
after_rows=$(wc -l < .manna/issues.jsonl | tr -d ' ')
after_handoffs=$(find .handoff -name 'mn-*.md' -type f | wc -l | tr -d ' ')
if [[ "$before_rows" == "$after_rows" && "$before_handoffs" == "$after_handoffs" ]]; then
    pass "failed create rolls back both sides of the pair"
else
    fail "failed create rolls back both sides of the pair" "rows $before_rows->$after_rows, handoffs $before_handoffs->$after_handoffs"
fi
printf '!.handoff/mn-*.md\n' >> .gitignore

lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 0 "$lint_exit" "lint accepts the generated pair"

rec_exit=0
output=$("$MANNA" reconcile --json 2>&1) || rec_exit=$?
check_exit 0 "$rec_exit" "reconcile remains advisory on a paired board"
if [[ "$output" != *"prompt_pairing"* && "$output" != *"workflow_sprawl"* ]]; then
    pass "generated pair reports no linkage or sprawl drift"
else
    fail "generated pair reports no linkage or sprawl drift" "unexpected finding: $output"
fi

create_exit=0
output=$("$MANNA" create "Wrong root" --prompt .handoffs/wrong.md 2>&1) || create_exit=$?
check_exit 1 "$create_exit" "strict create rejects a parallel handoff root"

sed -i.bak "s/agent-do manna claim $PAIR_ID/agent-do manna claim mn-dead00/" "$PROMPT_A"
rm -f "$PROMPT_A.bak"
claim_exit=0
output=$("$MANNA" claim "$PAIR_ID" 2>&1) || claim_exit=$?
check_exit 2 "$claim_exit" "claim fails closed on a broken handoff link"
check_yaml "$output" "Refusing claim" "claim explains the broken handoff contract"
lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 1 "$lint_exit" "lint fails on a mismatched claim command"
check_yaml "$output" "handoff_contract" "lint names the handoff contract"
sed -i.bak "s/agent-do manna claim mn-dead00/agent-do manna claim $PAIR_ID/" "$PROMPT_A"
rm -f "$PROMPT_A.bak"
"$MANNA" handoff seal "$PAIR_ID" >/dev/null 2>&1

mkdir -p .handoffs
printf 'agent-do manna claim %s\n' "$PAIR_ID" > .handoffs/shadow.md
output=$("$MANNA" reconcile --json 2>&1) || true
check_yaml "$output" "workflow_sprawl" "reconcile detects a shadow handoff root"
check_yaml "$output" ".handoffs" "sprawl finding names the shadow root"
sprawl_exit=0
"$MANNA" reconcile --json >/dev/null 2>&1 || sprawl_exit=$?
check_exit 1 "$sprawl_exit" "shadow handoff roots make reconcile fail"

DEEP_SHADOW=.dev/one/two/three/four/five/six/seven/eight/nine/ten/eleven/twelve
mkdir -p "$DEEP_SHADOW"
cp "$PROMPT_A" "$DEEP_SHADOW/deep-shadow.md"
output=$("$MANNA" reconcile --json 2>&1) || true
check_yaml "$output" "deep-shadow.md" "sprawl scan has no nesting ceiling"

LINK_TARGET=$(mktemp)
cp "$PROMPT_A" "$LINK_TARGET"
mkdir -p .dev/linked
ln -s "$LINK_TARGET" .dev/linked/shadow.md
output=$("$MANNA" reconcile --json 2>&1) || true
check_yaml "$output" ".dev/linked/shadow.md" "sprawl scan reads symlinked work-order content"
rm -f "$LINK_TARGET"

LEGACY_DIR=$(mktemp -d)
LEGACY_PHYS=$(cd "$LEGACY_DIR" && pwd -P)
cd "$LEGACY_DIR"
mkdir -p .manna
touch .manna/sessions.jsonl
printf '%s\n' '{"id":"mn-a1b2c3","title":"Existing legacy row","status":"open","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z","blocked_by":[]}' > .manna/issues.jsonl
output=$("$MANNA" init 2>&1) || true
check_yaml "$output" "workflow: legacy" "init classifies a real pre-workflow board explicitly"
check_yaml "$(cat .manna/board.yaml)" "workflow: legacy" "legacy mode is pinned instead of inferred"
mkdir -p .dev/session-prompts
LEGACY_PROMPT="$LEGACY_PHYS/.dev/session-prompts/lane-a.md"
output=$("$MANNA" create "Legacy paired work" --prompt "$LEGACY_PROMPT" 2>&1) || true
check_yaml "$output" "success: true" "existing legacy boards retain explicit prompt pointers"
LEGACY_ID=$(extract_id "$output")
printf 'agent-do manna claim %s\n' "$LEGACY_ID" > "$LEGACY_PROMPT"
lint_exit=0
output=$("$MANNA" lint 2>&1) || lint_exit=$?
check_exit 0 "$lint_exit" "legacy prompt pairing remains valid"

cd "$TEST_DIR"
rm -rf "$PAIR_DIR"
rm -rf "$LEGACY_DIR"

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
# Every context row carries when it last moved, so the inert marker is pinned
# around the age rather than against a stamp that changes every second.
check_yaml "$output" "$G_DREAM: A parked spark [open] updated $(date -u +%Y-%m-%d) (" \
    "context dates and ages the dream row"
check_yaml "$output" "ago) [DREAM: not claimable, needs conversion]" \
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
output=$("$MANNA" done "$G_DREAM" 2>&1) || true
check_yaml "$output" "status: done" "done explicitly closes an unclaimed dream"

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
