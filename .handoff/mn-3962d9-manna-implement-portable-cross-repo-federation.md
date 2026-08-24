---
workflow: 2
manna: mn-3962d9
track: mn-b7a0cc
source: Erik approval 2026-08-24; .handoff/mn-e40d9a-manna-research-if-how-cross-repo-board-linkage-should-exist.md
base_commit: c69860b2158aca1c1a90e1afff17af3cf40a018a
scope: 'Manna: implement portable cross-repo federation'
inputs:
- Erik approval 2026-08-24; .handoff/mn-e40d9a-manna-research-if-how-cross-repo-board-linkage-should-exist.md
binding: sha256:c914bfd3bea5b99f6b9d2c93784007f3c254d94521ed094094a5209d0154d160
---

# Handoff: Manna: implement portable cross-repo federation

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-3962d9
```

## Scope

Manna: implement portable cross-repo federation

## Inputs

- Erik approval 2026-08-24; .handoff/mn-e40d9a-manna-research-if-how-cross-repo-board-linkage-should-exist.md

## Work order

Implement the Erik-approved mn-e40d9a federation v1 specification in full: tracked .manna/federation.yaml identity and relation authority, typed board-qualified relations, authenticated journaled mutations, local-only lint and reconcile rules, registry-backed resolved/unavailable/missing/ambiguous reads, counterpart reciprocity, serve rendering, registry contracts, documentation, and the complete hermetic test matrix. Preserve local ownership, blocker, done, pairing, handoff, and landed-evidence invariants. Do not add relation fields to Issue, couple local lifecycle to remote state, auto-migrate prose, or choose divergent replicas.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-3962d9`.
4. Commit with `Manna: mn-3962d9` and run `agent-do manna done mn-3962d9` only after the work is verified.
