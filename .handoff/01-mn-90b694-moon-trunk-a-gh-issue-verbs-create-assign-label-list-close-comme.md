---
workflow: 2
manna: mn-90b694
track: mn-b7a0cc
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'Moon trunk A: gh issue verbs (create/assign/label/list/close/comment) + pr create --declare'
inputs: []
binding: sha256:3d1b649e41a3fb4eec411dc8ca9d3e76cbbe20dd932d258c4af4b2c24624e644
---

# Handoff: Moon trunk A: gh issue verbs (create/assign/label/list/close/comment) + pr create --declare

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-90b694
```

## Scope

Moon trunk A: gh issue verbs (create/assign/label/list/close/comment) + pr create --declare

## Inputs

- None declared.

## Work order

Claim mechanism needs issue verbs; gh tool is PR-only today. House pattern: registry+contracts+tests+docs.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-90b694`.
4. Commit with `Manna: mn-90b694` and run `agent-do manna done mn-90b694` only after the work is verified.
