---
workflow: 2
manna: mn-3a58e4
track: mn-b7a0cc
source: Erik, 2026-08-24, coordination discussion
base_commit: 9c99f092658d72d9c7d9f9baa5d33fc16a38db7f
scope: 'serve: coordination section per board'
inputs:
- Erik, 2026-08-24, coordination discussion
binding: sha256:8f7e5656c95117f5f41e8bc869605c04d515738cad3bfdfe5f0027d1343ada39
---

# Handoff: serve: coordination section per board

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-3a58e4
```

## Scope

serve: coordination section per board

## Inputs

- Erik, 2026-08-24, coordination discussion

## Work order

A COORDINATION section on each board page, read-only, all data already in coord: NEEDS YOU first (pulse needs-user / failed), then peers attention-first (identity, runtime, liveness+age, pulse status, current tool, latest prompt, todo, focus goal, the manna item they hold via the identity-hex join serve already does), then claims by path so overlapping writers are visible, then open drops (--for-me / any) and contention or dependency interrupts. Sources: coord peers --json, claims, drops, interrupts, need list. Depends on the pulse merge in the NOW rows landing first.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-3a58e4`.
4. Commit with `Manna: mn-3a58e4` and run `agent-do manna done mn-3a58e4` only after the work is verified.
