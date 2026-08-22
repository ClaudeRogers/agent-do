---
workflow: 2
manna: mn-2521d5
track: mn-b7a0cc
source: null
base_commit: c116c72c91fa06ae45aa25d98e54857d11a6cacb
scope: 'DPT: fix false-positive generators and honesty defects'
inputs: []
binding: sha256:74c665c36dc61f48a1c6b8aed7eaa63cf34f5234a2d6bb953c840eca653902af
---

# Handoff: DPT: fix false-positive generators and honesty defects

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-2521d5
```

## Scope

DPT: fix false-positive generators and honesty defects

## Inputs

- None declared.

## Work order

From .handoff/dpt-audit-2026-08-22.md R2: session-scoped baseline (not /tmp global); violations sorted by real impact + include cf01 hard contrast failures; drop unscored checks from fix list or score them; ts17 variable-font/font-synthesis logic; sr09 effective side-space; ts03 per-font char width; cf04 lightness-aware saturation; parse oklch()/color() or fail loudly (never silent perfection); full-page scanning beyond viewport; correct 72/70+ rule-count claims to counted 65; delete dpt-report hardcoded sidebar line; redeploy hook as thin wrapper + only score when the open page matches the edited project

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-2521d5`.
4. Commit with `Manna: mn-2521d5` and run `agent-do manna done mn-2521d5` only after the work is verified.
