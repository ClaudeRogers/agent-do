---
workflow: 2
manna: mn-86a41b
track: mn-b7a0cc
source: 'Erik ratified design 2026-08-31 (Holy: One Ledger, Two Faces — track mn-9a97cc on holy-ghostty''s board). Consumer: Holy native board/attention surfaces. Filed by the holy-ghostty design session; agent-do worker builds it.'
base_commit: 7f7ac1c639dd3a56ad6ddcc98672416c36999270
scope: 'coord pulse: accept an explicit verdict write from a non-hook caller'
inputs:
- 'Erik ratified design 2026-08-31 (Holy: One Ledger, Two Faces — track mn-9a97cc on holy-ghostty''s board). Consumer: Holy native board/attention surfaces. Filed by the holy-ghostty design session; agent-do worker builds it.'
binding: sha256:9e24b13873b37db99fc9e5a2185c51071b7a9c383ee3766f888b0fa522abff57
---

# Handoff: coord pulse: accept an explicit verdict write from a non-hook caller

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-86a41b
```

## Scope

coord pulse: accept an explicit verdict write from a non-hook caller

## Inputs

- Erik ratified design 2026-08-31 (Holy: One Ledger, Two Faces — track mn-9a97cc on holy-ghostty's board). Consumer: Holy native board/attention surfaces. Filed by the holy-ghostty design session; agent-do worker builds it.

## Work order

coord pulse record currently ingests only --from-hook harness payloads. Deliver a documented write path for an external supervisor (Holy) to record a session's attention verdict under its session key: status (the six-state vocabulary incl. needs-user/failed/working/idle/finished), optional activity note, updated_at — same store, same liveness semantics, so board.py peers/attention render it identically to hook-fed rows. Contract must be idempotent and safe under concurrent hook writes (last-writer-wins per field or documented merge). Consumer: Holy writes its pane-evidence verdict back so the board's needs-you and Holy's roster orb read one record. House pattern registry+contracts+tests+docs.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-86a41b`.
4. Commit with `Manna: mn-86a41b` and run `agent-do manna done mn-86a41b` only after the work is verified.
