---
workflow: 2
manna: mn-3086f2
track: mn-455a88
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'docs: estate-wide refresh to as-is state — README/INTEGRATION/ARCHITECTURE sweep; Cursor registration (post-#24) folds in; #25 closed into this'
inputs: []
binding: sha256:18f5f8b3a12fe461baedfc4e8f22f04850af5e5932f461301f0d00f992cb68dc
---

# Handoff: docs: estate-wide refresh to as-is state — README/INTEGRATION/ARCHITECTURE sweep; Cursor registration (post-#24) folds in; #25 closed into this

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-3086f2
```

## Scope

docs: estate-wide refresh to as-is state — README/INTEGRATION/ARCHITECTURE sweep; Cursor registration (post-#24) folds in; #25 closed into this

## Inputs

- None declared.

## Work order

Author-led docs run across the board. Includes: Cursor adapter registration docs (INTEGRATION.md + README) written against merged #24 reality — the installer registers hooks in settings.json after prompting (--register-hooks writes, --print-only never does), the exact correction CodeRabbit flagged on closed PR #25. hooks/cursor/README.md covers setup until then.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-3086f2`.
4. Commit with `Manna: mn-3086f2` and run `agent-do manna done mn-3086f2` only after the work is verified.
