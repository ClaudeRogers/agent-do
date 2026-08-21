---
workflow: 2
manna: mn-898c08
track: mn-b7a0cc
source: estate scan 2026-08-21; three independent discovery costs
base_commit: 2bde3b6a5165c909ed53d6e0a84baad976e1efd4
scope: 'Manna: legacy-board discoverability — misrouted error text + bootstrap/SessionStart migrate detection'
inputs:
- estate scan 2026-08-21; three independent discovery costs
binding: sha256:8d377eb7ae5ce348b6618c06ef6573969a6ac81b711ce62606591f7a69d466cc
---

# Handoff: Manna: legacy-board discoverability — misrouted error text + bootstrap/SessionStart migrate detection

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-898c08
```

## Scope

Manna: legacy-board discoverability — misrouted error text + bootstrap/SessionStart migrate detection

## Inputs

- estate scan 2026-08-21; three independent discovery costs

## Work order

Sessions in three projects (agent-do, vms.io, versova-supply-intelligence) each independently dug to discover that manna migrate was the remedy for a legacy board. Two fixes: (1) the identityless-board error says 'run agent-do manna init' — on a nonempty legacy board it must name migrate instead; (2) bootstrap --recommend and the SessionStart hook should detect a .manna/ lacking workflow.yaml and surface 'legacy board: run agent-do manna migrate' before any session trips on it. Also surface untracked durable board files (git-tracked=no) as a finding — orphaned claims from dead sessions were the lane-32 root hazard.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-898c08`.
4. Commit with `Manna: mn-898c08` and run `agent-do manna done mn-898c08` only after the work is verified.
