# Skills Consolidation Task List - 2026-05-07

This is the working progress tracker for consolidating `~/.skills/` into `agent-do`.
Use this file to mark progress. The ledger remains the evidence table; this file is
the task board.

Related files:

- `~/.skills/AUDIT.md` - corrected strategy document
- `.handoff/skills-migration-ledger-2026-05-07.md` - verified per-skill ledger
- `.handoff/SESSION-HANDOFF-2026-05-07.md` - running handoff

Rules:

- No hard deletion without explicit user approval.
- Archive before cleanup.
- Do not archive a source skill after context/tool migration until retrieval or replacement behavior is verified.
- `artful-*`, `save-to-obsidian`, and `pdf-*` are protected unless explicitly reopened by the user.

## Status Legend

- `[x]` done
- `[>]` in progress
- `[ ]` not started
- `[!]` blocked or requires explicit approval

## Current Milestone

Goal: prove one safe migration pattern end to end before scaling to the rest of the skill library.

## Completed

- [x] Read repo guide and handoff.
- [x] Correct `~/.skills/AUDIT.md` so the bad `DELETE_REDUNDANT` rows are no longer deletion guidance.
- [x] Correct the session handoff so it no longer says `reactome-database` is empty or `torch-geometric` is an empty shell.
- [x] Re-read and reclassify `n8n-*` and `tanstack-*` deletion candidates from actual skill contents.
- [x] Generate `.handoff/skills-migration-ledger-2026-05-07.md` from filesystem truth.
- [x] Patch `agent-context` so `scan-skills` can index bundled support files.
- [x] Run TanStack context pilot for `tanstack-query`, `tanstack-router`, and `tanstack-table`.
- [x] Verify TanStack context retrieval for references/templates.
- [x] Verify targeted TanStack context search.
- [x] Run `bash tools/agent-context/test/integration.sh` - 34 passed.
- [x] Run `./test.sh` - 50 passed.

## Next Required

- [ ] Decide whether to keep the `agent-context` code changes as a commit-worthy repo change.
  - Status: ready for user decision.
  - Evidence: tests passed; diff touches only `tools/agent-context/*`.
  - Recommendation: keep. This is the production path needed for safe context migration.

- [ ] Use TanStack context in normal work before archiving the source skills.
  - Status: not started.
  - Exit condition: at least one real task successfully uses `agent-do context get/search` for TanStack without needing prompt-time skill loading.
  - Do not archive `tanstack-query`, `tanstack-router`, or `tanstack-table` before this.

- [ ] Repair `reactome-database` packaging.
  - Status: not started.
  - Current path: `~/.skills/reactome-database/reactome-database/SKILL.md`.
  - Decision needed: repackage as a normal skill layout or classify directly into future `agent-bio`.
  - Safe action: copy/move into a normal layout only with archive backup.

## Approval-Only Archive Candidates

These are plausible cleanup candidates, but no action should happen without explicit user approval.

- [!] Archive `~/.skills/obsidian/`.
  - Reason: smaller skeleton; `save-to-obsidian` is canonical and active.
  - Proposed destination: `~/.skills/.archive/2026-05-07/obsidian/`.

- [!] Archive `~/.skills/openai-assistants/`.
  - Reason: disabled and upstream-deprecated; may still hold migration reference value.
  - Proposed destination: `~/.skills/.archive/2026-05-07/openai-assistants/`.

- [!] Archive `~/.skills/torch-geometric/`.
  - Reason: disabled twin of active `torch_geometric`; not empty.
  - Proposed destination: `~/.skills/.archive/2026-05-07/torch-geometric/`.

## Next Migration Batches

- [ ] Batch 2: n8n context migration.
  - Skills: `n8n-code-javascript`, `n8n-code-python`, `n8n-expression-syntax`, `n8n-mcp-tools-expert`, `n8n-node-configuration`, `n8n-validation-expert`, `n8n-workflow-patterns`.
  - Precondition: keep `agent-context` bundled-file indexing.
  - Work: run named `scan-skills`, verify `get --file` for references, run 3-5 targeted searches.
  - Source skills remain in place until verified by real usage.

- [ ] Batch 3: disabled `.off` review policy.
  - Count: 50 disabled skill directories.
  - Work: choose policy: leave parked, archive all with dated backup, or review by family.
  - Constraint: archive, do not hard-delete.

- [ ] Batch 4: broad context migration.
  - Count in ledger: 151 `later-context` plus completed TanStack pilot and n8n batch after it runs.
  - Work: migrate by family, verify search and `get --file`, then decide when prompt-time skill can be removed.

- [ ] Batch 5: tool migration planning.
  - Count in ledger: 82 `TOOL_MIGRATION`.
  - First proposed tool family: `agent-bio`.
  - Start with 3-5 high-traffic databases only, not all 28 at once.

## Open Questions

- Should the `agent-context` changes be committed before more migration work?
- Should archive candidates move to `~/.skills/.archive/2026-05-07/` or a different ignored archive path?
- Should `reactome-database` be repaired as a skill now, or folded directly into the future `agent-bio` design?

