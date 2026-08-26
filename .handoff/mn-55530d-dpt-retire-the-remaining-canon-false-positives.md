---
workflow: 2
manna: mn-55530d
track: mn-b7a0cc
source: null
base_commit: 7e43f285241ee687a4c42e0f62638e3748c3fc3a
scope: 'DPT: retire the remaining canon false-positives'
inputs: []
binding: sha256:af96c7d78d6f21fb51cdcc493e444be61c9c4ce0b8d777a9c564ebf05b464b73
---

# Handoff: DPT: retire the remaining canon false-positives

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-55530d
```

## Scope

DPT: retire the remaining canon false-positives

## Inputs

- None declared.

## Work order

Rescan on the fixed engine (2026-08-22, post mn-2521d5) shows these audit false positives still firing on the ratified canon Dossier: sr02 44px touch rule on inline evidence links and nav (STILL a critical - adopt WCAG 2.5.8: 24px desktop target with inline-link exemption; the Advance button misses by 1px); ts01 counting small sans data/UI text as body (violations inflated 5 to 24 under full-page scan - needs role classification, floor stays 12px); ts09 hard 2.0-3.0 hero ratio failing editorial display scale (3.72 ratified); cf12 flagging the deliberate colorblind-safe verdict luminance spread; cf04 flagging ratified verdict chips as leaks (needs status-chip allowance); aa10 sticky-decision-bar tab-order artifact. Baseline: canon-dossier 80 with 1 false critical, canon-today 81 clean, broken 30, barf honestly INCOMPLETE, oklch 68 with planted violation caught

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-55530d`.
4. Commit with `Manna: mn-55530d` and run `agent-do manna done mn-55530d` only after the work is verified.
