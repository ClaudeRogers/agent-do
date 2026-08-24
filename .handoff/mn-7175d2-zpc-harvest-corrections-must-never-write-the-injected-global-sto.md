---
workflow: 2
manna: mn-7175d2
track: mn-455a88
source: holy-session audit of the global zpc layer, 2026-08-24
base_commit: 7e43f285241ee687a4c42e0f62638e3748c3fc3a
scope: 'zpc: remove harvest --corrections (transcript-mined quotes are not lessons)'
inputs:
- holy-session audit of the global zpc layer, 2026-08-24
binding: sha256:cf8cba0db679f8aa1d7d3478565d8eb353b49753f26ca06d55474334e643e422
---

# Handoff: zpc: harvest --corrections must never write the injected global store

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-7175d2
```

## Scope

zpc: harvest --corrections must never write the injected global store

## Inputs

- holy-session audit of the global zpc layer, 2026-08-24

## Work order

The miner appended verbatim correction quotes to the global lessons file that inject renders as rulings (20 of 27 rows). Fix: write correction-candidates.jsonl instead, never re-queue ids the global store already holds, promote only by hand via learn + promote. Follow-up: one-time retract of the 21 polluted rows, Erik's call; commands in .dev/zpc-global-prune-2026-08-24.sh

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-7175d2`.
4. Commit with `Manna: mn-7175d2` and run `agent-do manna done mn-7175d2` only after the work is verified.
