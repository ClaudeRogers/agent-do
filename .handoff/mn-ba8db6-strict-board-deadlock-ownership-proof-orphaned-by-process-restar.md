---
workflow: 2
manna: mn-ba8db6
track: mn-b7a0cc
source: null
base_commit: 5eb1c5f17bdc4d0c81fda01362ebb64db147c5c8
scope: 'Strict-board deadlock: ownership proof orphaned by process restart within one logical session'
inputs: []
binding: sha256:6c65e07def9d4a8afddb428a94c9c99f24f65fa873e30470f356baa7aa076588
---

# Handoff: Strict-board deadlock: ownership proof orphaned by process restart within one logical session

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-ba8db6
```

## Scope

Strict-board deadlock: ownership proof orphaned by process restart within one logical session

## Inputs

- None declared.

## Work order

Repro on holy-ghostty board 2026-08-21: session 6e040306 claimed mn-7c1e31 (accepted), the session's PROCESS restarted (same conversation, same visible session id), then done/seal/abandon all refuse with 'ownership proof does not match session 6e040306...; the visible owner label is not sufficient authority'. reconcile classifies the issue landed_open and prescribes 'claim and done' — but claim refuses (status in_progress) and done refuses (proof mismatch), a closed loop with no sanctioned exit. reconcile --fix cannot help: its dead-claim detection keys on session liveness and this session is alive; only the proof secret was lost. Gap: the enforced-handoff workflow needs either proof re-derivation for a live session presenting the same session identity, or a reconcile remedy for landed_open+proof-orphan (verify commit trailers landed, then re-mint or release). Until then any mid-work process restart permanently wedges the item.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-ba8db6`.
4. Commit with `Manna: mn-ba8db6` and run `agent-do manna done mn-ba8db6` only after the work is verified.
