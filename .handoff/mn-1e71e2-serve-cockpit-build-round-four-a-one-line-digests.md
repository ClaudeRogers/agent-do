---
workflow: 2
manna: mn-1e71e2
track: mn-b7a0cc
source: Erik's rulings across layout rounds 1–4, 2026-08-24
base_commit: 69171d0c3299e84f46bc09e45fed9bca502a8221
scope: 'serve: cockpit build (round-four A) + one-line digests'
inputs:
- Erik's rulings across layout rounds 1–4, 2026-08-24
binding: sha256:55e6e3d86f919349966c0f0e71c7a67e091cc9e15db0ffb828d108ae328b8e95
---

# Handoff: serve: cockpit build (round-four A) + one-line digests

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-1e71e2
```

## Scope

serve: cockpit build (round-four A) + one-line digests

## Inputs

- Erik's rulings across layout rounds 1–4, 2026-08-24

## Work order

Build the ratified layout from layout rounds 1–4 (artifacts 0d5d4ceb, 99b4de34, 9853704b, 8d17eefb; Erik's notes in each page): breadcrumb estate › project; three tabs inbox · board · coordination badged by what needs you; grep; ⌘K jump palette; board opens on now/next/waiting with chips live · +done · dreams · track and a list | timeline switch; inspector on the right (item, or peer in coordination); status strip at the bottom carrying drift and daemon health, opening a debug sheet. Finish A: 10px ledger density, one-line rows with ellipsis, zebra, severity stripe lead, outlined pills, rounded chips, prompt headers ($ manna next), raised-row selection with blue inset, never inverse video. Inbox rows are uniform: who/what · the ask · the verb you perform (grant, rule, split, close, read, launch). Rows show a one-line digest instead of the raw title, generated the way agent-sessions titles sessions (fast model, hash-keyed cache under ~/.agent-do/manna/serve/, outside the board, regenerated only when title/description change, byte-bounded batches against the authority's input window, title as fallback); the manna title and description live in the inspector. dpt floors run on the built page. Read-only stays.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-1e71e2`.
4. Commit with `Manna: mn-1e71e2` and run `agent-do manna done mn-1e71e2` only after the work is verified.
