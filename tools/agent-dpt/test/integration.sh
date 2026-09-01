#!/usr/bin/env bash
# Live browser-path regressions for DPT. Uses the same agent-do browse and dpt
# commands as production, with an isolated browser session and state root.

set -euo pipefail

DPT_TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DPT_DIR="$(dirname "$DPT_TEST_DIR")"
REPO_ROOT="$(cd "$DPT_DIR/../.." && pwd)"
DPT_TEST_STATE="$(mktemp -d)"
DPT_TEST_SESSION="dpt-test-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:12])')"

cleanup() {
    AGENT_BROWSER_SESSION="$DPT_TEST_SESSION" "$REPO_ROOT/agent-do" browse close >/dev/null 2>&1 || true
    rm -rf "$DPT_TEST_STATE"
}
trap cleanup EXIT

export AGENT_BROWSER_SESSION="$DPT_TEST_SESSION"
export AGENT_DO_HOME="$DPT_TEST_STATE/agent-do"
export PATH="$REPO_ROOT:$PATH"

# dist/ is a generated, ignored runtime artifact. Build it through the same
# public command the production scanner uses so this test works from a clean
# checkout and catches source-to-engine assembly failures.
"$REPO_ROOT/agent-do" dpt build >/dev/null

fixture_url() {
    python3 - "$DPT_TEST_DIR/fixtures/$1" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).resolve().as_uri())
PY
}

OKLCH_JSON="$DPT_TEST_STATE/oklch.json"
CANON_JSON="$DPT_TEST_STATE/canon.json"
GRADIENT_JSON="$DPT_TEST_STATE/gradient.json"
GRADIENT_REPORT="$DPT_TEST_STATE/gradient-report.txt"
VIOLATIONS_JSON="$DPT_TEST_STATE/violations.json"

"$REPO_ROOT/agent-do" browse open "$(fixture_url oklch.html)" >/dev/null
"$REPO_ROOT/agent-do" dpt scan --current --json > "$OKLCH_JSON"

python3 - "$OKLCH_JSON" <<'PY'
import json
import sys

with open(sys.argv[1]) as handle:
    data = json.load(handle)

meta = data["meta"]
assert meta["rule_count"] == 65, meta
assert meta["color_parse"]["unparseable_count"] == 0, meta["color_parse"]
assert data["chromatic_field"]["cf01_text_contrast"]["hard_failures"] >= 1
buttons = data["attention_architecture"]["aa02_button_hierarchy"]
assert buttons["primary"] + buttons["secondary"] + buttons["tertiary"] >= 1, buttons
assert data["synthesis"]["overall_score"] is not None, data["synthesis"]
PY

"$REPO_ROOT/agent-do" browse open "$(fixture_url canon.html)" >/dev/null
"$REPO_ROOT/agent-do" dpt scan --current --json > "$CANON_JSON"

python3 - "$CANON_JSON" <<'PY'
import json
import sys

with open(sys.argv[1]) as handle:
    data = json.load(handle)

meta = data["meta"]
cf = data["chromatic_field"]
ts = data["typographic_skeleton"]
sr = data["spatial_rhythm"]
assert meta["scan_coverage"]["document_height"] > meta["viewport"]["height"], meta
assert meta["scan_coverage"]["bands_scanned"] > 1, meta["scan_coverage"]
assert cf["cf04_interactive_primary"]["non_interactive_leaks"] == 0, cf["cf04_interactive_primary"]
assert ts["ts03_line_length"]["violations"] == 0, ts["ts03_line_length"]
assert ts["ts17_faux_bold_italic"]["faux_bold"] == 0, ts["ts17_faux_bold_italic"]
assert ts["ts17_faux_bold_italic"]["faux_italic"] == 0, ts["ts17_faux_bold_italic"]
assert sr["sr09_body_text_margin"]["inadequate_margin"] == 0, sr["sr09_body_text_margin"]
assert ts["ts18_tabular_numerals"]["numeric_cells"] > 0, ts["ts18_tabular_numerals"]
assert meta["color_parse"]["unparseable_count"] == 0, meta["color_parse"]
PY

"$REPO_ROOT/agent-do" browse open "$(fixture_url gradient.html)" >/dev/null
"$REPO_ROOT/agent-do" dpt scan --current --json > "$GRADIENT_JSON"

python3 - "$GRADIENT_JSON" <<'PY'
import json
import sys

with open(sys.argv[1]) as handle:
    data = json.load(handle)

diagnostics = data["meta"]["color_parse"]
assert diagnostics["unparseable_count"] > 0, diagnostics
assert any("background-image:" in sample for sample in diagnostics["samples"]), diagnostics
assert data["synthesis"]["overall_score"] is None, data["synthesis"]
assert data["synthesis"]["overall_grade"] == "INCOMPLETE", data["synthesis"]
PY

"$DPT_DIR/bin/dpt-report" "$GRADIENT_JSON" > "$GRADIENT_REPORT"
grep -q "score withheld" "$GRADIENT_REPORT"

"$REPO_ROOT/agent-do" dpt violations "$(fixture_url broken.html)" --json > "$VIOLATIONS_JSON"

python3 - "$VIOLATIONS_JSON" <<'PY'
import json
import sys

with open(sys.argv[1]) as handle:
    data = json.load(handle)

violations = data["violations"]
assert violations and violations[0]["check"] == "cf01_text_contrast", violations[:3]
impacts = [item["impact"] for item in violations]
assert impacts == sorted(impacts, reverse=True), impacts
unscored = {
    "ts10_caps_letter_spacing", "ts11_caps_word_count", "ts12_centered_body_text",
    "ts15_straight_quotes", "ts16_double_hyphens", "ts18_tabular_numerals",
    "ts20_paragraph_separation", "sr10_shadow_color_temperature", "aa05_link_affordance_body",
}
assert not ({item["check"] for item in violations} & unscored), violations
hard = violations[0]["violations"]
assert hard and all(item.get("severity") == "hard" for item in hard), hard
PY

# A baseline explicitly associates this browser session and page origin with the
# current project. The hook may score this project, but must skip an unrelated
# edited project even while the same page remains open.
"$REPO_ROOT/agent-do" browse open "$(fixture_url canon.html)" >/dev/null
"$REPO_ROOT/agent-do" dpt baseline --current >/dev/null

FOREIGN_PROJECT="$DPT_TEST_STATE/foreign-project"
mkdir -p "$FOREIGN_PROJECT"
git -C "$FOREIGN_PROJECT" init --quiet
touch "$FOREIGN_PROJECT/page.tsx"

FOREIGN_HOOK_OUTPUT="$DPT_TEST_STATE/foreign-hook.json"
LOCAL_HOOK_OUTPUT="$DPT_TEST_STATE/local-hook.json"

python3 - "$FOREIGN_PROJECT/page.tsx" <<'PY' |
import json
import sys
print(json.dumps({"tool_input": {"file_path": sys.argv[1]}}))
PY
    DPT_HOOK_HMR_WAIT=0 "$DPT_DIR/hooks/dpt-post-edit.sh" > "$FOREIGN_HOOK_OUTPUT"

python3 - "$DPT_TEST_DIR/fixtures/canon.html" <<'PY' |
import json
import sys
print(json.dumps({"tool_input": {"file_path": sys.argv[1]}}))
PY
    DPT_HOOK_HMR_WAIT=0 "$DPT_DIR/hooks/dpt-post-edit.sh" > "$LOCAL_HOOK_OUTPUT"

python3 - "$FOREIGN_HOOK_OUTPUT" "$LOCAL_HOOK_OUTPUT" <<'PY'
import json
import sys

with open(sys.argv[1]) as handle:
    foreign = json.load(handle)
with open(sys.argv[2]) as handle:
    local = json.load(handle)

foreign_context = foreign["hookSpecificOutput"]["additionalContext"]
local_context = local["hookSpecificOutput"]["additionalContext"]
assert foreign_context.startswith("DPT skipped:"), foreign_context
assert local_context.startswith("DPT:"), local_context
PY

printf '%s\n' "dpt browser integration tests passed"
