#!/bin/bash
# PostToolUse hook (matcher: ExitPlanMode): a plan was just approved, so the
# bet it rests on is nameable right now.
#
# Every plan has one load-bearing claim — the thing that, if false, wastes the
# whole plan. `zpc position add` is the ledger for exactly that: verdict,
# confidence, falsifier. The moment of approval is the only moment the claim is
# still explicit; by the first commit it has dissolved into the diff.
#
# Delivery here is genuinely non-blocking, unlike the Stop-event write nudge:
# PostToolUse honors hookSpecificOutput.additionalContext, which the docs place
# "next to the tool result" for Claude to read on the next model request. The
# tool has already run; nothing is gated on this hook.
#
# AGENT_DO_ZPC_POSITION_NUDGE=0 disables it. AGENT_DO_ZPC_WRITE_NUDGE=0 also
# disables it: a position is a write, so the master write-side switch silences
# the whole write side.
#
# Never blocks, never exits nonzero. Every failure path is a silent exit 0.

[ "${AGENT_DO_ZPC_POSITION_NUDGE:-1}" = "0" ] && exit 0
[ "${AGENT_DO_ZPC_WRITE_NUDGE:-1}" = "0" ] && exit 0

command -v jq >/dev/null 2>&1 || exit 0

INPUT=$(cat 2>/dev/null || true)
CWD=$(echo "$INPUT" | jq -r '.cwd // ""' 2>/dev/null)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null)

# The registered matcher should already scope this, but a hook registered
# without one would otherwise fire on every tool call in the session.
[ "$TOOL_NAME" = "ExitPlanMode" ] || exit 0

[ -n "$CWD" ] || CWD="$PWD"
cd "$CWD" 2>/dev/null || exit 0

# No ledger, nothing to write to. `zpc position add` requires .zpc/.
[ -d .zpc ] || exit 0

# Stated as facts rather than as instructions to the model: the hooks docs warn
# that out-of-band imperatives trip Claude's prompt-injection defenses and get
# surfaced to the user as suspicious text instead of read as context.
# All four arguments below are required by `position add` — it refuses a row
# without a falsifier, on the grounds that a verdict without one is a mood.
MSG="This plan was approved and the project has a .zpc position ledger. A plan rests on one load-bearing claim: the thing that, if it turns out false, wastes the plan. Recording it now is what makes a later reversal legible as evidence rather than as drift.

  agent-do zpc position add \"<the claim this plan rests on>\" --verdict \"<what you believe is true>\" --confidence low|med|high --falsifier \"<the observation that would change the verdict>\"

All four are required; there is no row without a falsifier. When evidence later contradicts it: agent-do zpc position flip <id> --evidence \"<what changed and where it came from>\". A plan that rests on no contestable claim needs no row. AGENT_DO_ZPC_POSITION_NUDGE=0 turns this off."

jq -nc --arg m "$MSG" \
    '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $m}}' 2>/dev/null

exit 0
