---
workflow: 2
manna: mn-613088
track: mn-b7a0cc
source: Approved by Erik 2026-08-24; prototype aldebaran-group/moon-two/control-room
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'Moon trunk F: policy board render + notify rules (claim_conflict/unblocked/floor_violation)'
inputs:
- Approved by Erik 2026-08-24; prototype aldebaran-group/moon-two/control-room
binding: sha256:e2895a60984fdf1bf14a719ae0768d1b94cedec06322e5c0a207edd8cbe6b8ee
---

# Handoff: Moon trunk F: policy board render + notify rules (claim_conflict/unblocked/floor_violation)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-613088
```

## Scope

Moon trunk F: policy board render + notify rules (claim_conflict/unblocked/floor_violation)

## Inputs

- None declared.

## Work order

The Linear face: items x claims x floors x blockers x live sessions x evidence. Text+JSON first.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-613088`.
4. Commit with `Manna: mn-613088` and run `agent-do manna done mn-613088` only after the work is verified.
