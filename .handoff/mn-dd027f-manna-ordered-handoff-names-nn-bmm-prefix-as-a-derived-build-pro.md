---
workflow: 2
manna: mn-dd027f
track: mn-b7a0cc
source: vms.io session 2026-08-18; design discussion agent-do 2026-08-20
base_commit: 463dee4551e31a47a589469a16581df5f148deb3
scope: 'Manna: ordered handoff names — NN[bMM] prefix as a derived build product'
inputs:
- vms.io session 2026-08-18; design discussion agent-do 2026-08-20
binding: sha256:1044fbcaced3e9f527a3971a42ca4f90670238d9426a8584de51de189dc0d8bc
---

# Handoff: Manna: ordered handoff names — NN[bMM] prefix as a derived build product

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-dd027f
```

## Scope

Manna: ordered handoff names — NN[bMM] prefix as a derived build product

## Inputs

- vms.io session 2026-08-18; design discussion agent-do 2026-08-20

## Work order

PURPOSE OF THE b-MARKER (Erik, 2026-08-20): a launch gate for parallel sessions. Any file without a b is safe to open in its own parallel session right now; a b means do not launch until the named blocker closes. The fence is per-file, not positional: 01 02 03 04b03 05 = four launchable (01, 02, 03, 05), only 04 held. Corollary filing rule: the number encodes PRIORITY ONLY, never dependency — every real dependency must be a blocked_by edge on the board, or a bare filename will wrongly read as launchable. The sync pass keeps markers live so absence-of-b is always a true launch signal.

DECIDED: A+B — two renderings of one board truth. Numbered filenames for the human glance; generated .handoff/README.md index (number ↔ mn-id ↔ full blocker list ↔ status) for agents and traceability. Both written by the same sync pass; agents read the board, never filenames.

DECIDED, ordering: no gap numbering, no insertion markers (5.inject rejected — records history where names should record current state). Order lives on the board as an ordered list; every sync re-derives dense 01..N and renames whatever moved. The tool owns every rename atomically; git history is the record of how the plan changed.

DECIDED, blocker suffix: exactly one b-marker — the highest still-open blocker. 05b02 even when 05 also waits on 01: 02's own name carries b01, so the chain reads through. Sync re-derives on every change — when the shown blocker closes but another remains, the name re-renders to it; when the last closes, the b vanishes (that bare name IS the launch signal). Edge case (independent blockers, only one shown) is covered by the README's full list.

THE SCHEME (proven by hand in vms.io .handoff/): filename = <NN>[b<MM>]-mn-<id>-<slug>.md. Two-digit priority prefix; a blocked item wears b + its highest still-open blocker's number. Payoff: ls .handoff/ reads as the plan — priority, blockage, and parallel-launch safety at a glance.

DESIGN CONSTRAINT: numbering is a derived build product the tool owns, never hand-maintained — contracts-propose doctrine. Hand-kept copies drift (vms.io's rename pass broke three times in one session). Mechanism: a sync pass (new verb, or reconcile --fix growing rename powers) computes prefixes from board state, renames files, repoints prompt: fields, and regenerates the README index atomically; manna lint flags filename-vs-board drift. Pairing gate already accepts prefixed names (canonical_handoff_path requires only .md under .handoff/); generation at workflow.rs:317 plus sync/lint logic are the changes.

REMAINING WORK, not decisions: ordered-list/rank storage on items, the sync pass, lint wiring. Design settled. Build waits for conversion (--type item) and a clear lane — codex session active when filed. New manna verb/field = taxonomy gate, satisfied by this thread.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-dd027f`.
4. Commit with `Manna: mn-dd027f` and run `agent-do manna done mn-dd027f` only after the work is verified.
