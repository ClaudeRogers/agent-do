---
workflow: 2
manna: mn-1f446f
track: mn-b7a0cc
source: null
base_commit: 7e43f285241ee687a4c42e0f62638e3748c3fc3a
scope: coord pulse + peers attention upgrade (Warp steal)
inputs: []
binding: sha256:e56703a90eda06f775f2e2e12b316deb845e2dcb2c124a33dda0b465faa1fd7e
---

# Handoff: coord pulse + peers attention upgrade (Warp steal)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-1f446f
```

## Scope

coord pulse + peers attention upgrade (Warp steal)

## Inputs

- None declared.

## Work order

Hook-fed pulse telemetry per session + attention-first peers columns; greenlit by Erik 2026-08-24; full scope in .dev/warp-recon-2026-08-22/03-BUILD-SCOPE.md

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-1f446f`.
4. Commit with `Manna: mn-1f446f` and run `agent-do manna done mn-1f446f` only after the work is verified.
