---
workflow: 2
manna: mn-79291c
track: mn-b7a0cc
source: estate sweep 2026-08-21, receipts in session
base_commit: 69f70a671fc685c6abc31e4df5c9a52c065ef0f8
scope: 'Manna: migrate convergence gaps round 2 — strict-lookalike handoffs and cross-project pointers'
inputs:
- estate sweep 2026-08-21, receipts in session
binding: sha256:4380e6bfb4b21b2c5cf6c8220b211e223b58552e7f6a6c0411178dd549f254a7
---

# Handoff: Manna: migrate convergence gaps round 2 — strict-lookalike handoffs and cross-project pointers

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-79291c
```

## Scope

Manna: migrate convergence gaps round 2 — strict-lookalike handoffs and cross-project pointers

## Inputs

- estate sweep 2026-08-21, receipts in session

## Work order

Found by the 2026-08-21 estate sweep (17 of 21 boards converged; these gaps block 3 of the 4 remainders).

GAP A — strict-lookalike handoffs (scale-mechanics, palingenesis): pre-adoption .handoff/ files carry partial frontmatter (manna/track/source, no binding, no base_commit, no Scope/Inputs/Completion sections). migrate classifies them as strict pairs and refuses with 'handoff Claim section must contain exactly ...' even when that line is present, because full strict validation runs on them. Proposal: a frontmatter-carrying file with NO binding field is legacy content — wrap it into a canonical sealed handoff preserving the body, exactly as handwritten Markdown is wrapped today.

GAP B — cross-project absolute pointers (holy-ghostty): 7 rows point at /Users/erik/Custom-Coding/agent-sessions/.dev/session-prompts/*.md (a different repo), 7 more at absolute in-project .dev paths; several rows open or in_progress. migrate refuses 'legacy handoff pointer is outside the project'. Proposal: at migration, ingest the pointed file's content into the canonical handoff with a provenance note recording the original path; normalize absolute in-project pointers to repo-relative. Content survives, sprawl dies.

ALSO IN THE WAY, no code needed: holy-ghostty .gitignore:40 and palingenesis .gitignore:59 ignore /.handoff/ — lift as part of each board's migration (migrate already refuses with the exact filename). aldebaran-group was skipped for 2 live peer sessions — plain rerun when quiet. egora converged but has no git repository, so its board is not yet durable (Erik's call whether to git init).

Backups of every swept board: sweep-20260821/backup in the 2026-08-21 session scratchpad.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-79291c`.
4. Commit with `Manna: mn-79291c` and run `agent-do manna done mn-79291c` only after the work is verified.
