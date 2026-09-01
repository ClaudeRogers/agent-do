---
workflow: 2
manna: mn-3dd0f8
track: mn-b7a0cc
source: Erik, 2026-08-24, coordination discussion after mn-613088
base_commit: 9c99f092658d72d9c7d9f9baa5d33fc16a38db7f
scope: 'serve: pulse in NOW rows + live drift'
inputs:
- Erik, 2026-08-24, coordination discussion after mn-613088
binding: sha256:606f657b9c034f79d7dcf1a7225cbb58d08da030e4e2f1f90cda53b7cd86e64f
---

# Handoff: serve: pulse in NOW rows + live drift

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-3dd0f8
```

## Scope

serve: pulse in NOW rows + live drift

## Inputs

- Erik, 2026-08-24, coordination discussion after mn-613088

## Work order

Two better-updates for the human board page. (a) NOW rows absorb coord pulse: each claimant's pulse.status (working / needs-user / finished / failed), current tool (activity), latest_prompt, and todo progress, read from the pulse object that coord peers --json already returns; no new source, no new storage, display only (pulse is telemetry, never custody: zpc pos-3c49ff). needs-user rows sort first. (b) DRIFT goes live: on a board-signature change the daemon runs manna reconcile --json (read-only; only --write-drift writes) and renders current findings, showing drift.yaml's age beside them. Approved by Erik 2026-08-24, including the reconcile-on-change decision (~1s git walk per change accepted). Page stays read-only.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-3dd0f8`.
4. Commit with `Manna: mn-3dd0f8` and run `agent-do manna done mn-3dd0f8` only after the work is verified.
