---
workflow: 2
manna: mn-6b8255
track: mn-b7a0cc
source: residual from mn-ba8db6 close, 2026-08-21
base_commit: 434f3310c17a647c666fc0206c9601097538d8dc
scope: 'Manna: migrate the Cursor hook to derived identity (parity with mn-ba8db6)'
inputs:
- residual from mn-ba8db6 close, 2026-08-21
binding: sha256:8c0bf26ad2ccbd7472f5e0f15c2a3af74db8d09a44dfa407eb27ce4b7e955acb
---

# Handoff: Manna: migrate the Cursor hook to derived identity (parity with mn-ba8db6)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-6b8255
```

## Scope

Manna: migrate the Cursor hook to derived identity (parity with mn-ba8db6)

## Inputs

- residual from mn-ba8db6 close, 2026-08-21

## Work order

The Cursor SessionStart hook still mints a random MANNA_SESSION_TOKEN, so Cursor lanes keep the restart-wedge the Claude hook just shed. Mirror the mn-ba8db6 change: stop minting, export the conversation id for machine-key derivation, neutralize stale half-pins, and update the Cursor branch of tests/test_session_start_reads.py to the derived contract. Small: the Claude-side commit a1676fb is the template.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-6b8255`.
4. Commit with `Manna: mn-6b8255` and run `agent-do manna done mn-6b8255` only after the work is verified.
