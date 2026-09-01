# agent-do — Session Handoff (2026-05-07)

**Outgoing model:** Claude Opus 4.7 (1M context). User moving work to Codex.
**Session type:** Advisory / audit. **No production code or registry changes were made.**
**Primary artifact:** `~/.skills/AUDIT.md` (1041 lines after Codex correction patch) — a triage of 432 skill directories at `~/.skills/` (= `~/.claude/skills/`, symlinked).

---

## 0. TL;DR for the Next Agent

User has 432 skills in `~/.skills/` and wants to consolidate them into `agent-do` so agent-do gets stronger and the skill index gets shorter. They asked for a full triage report. **The report exists and is mostly useful**, but **the `DELETE_REDUNDANT` bucket has confirmed errors** — see Section 9. Trust the strategy/buckets; verify every individual deletion against the actual `SKILL.md` content before acting.

User already corrected two deletion calls in this session:
- **`obsidian` vs `save-to-obsidian`** — audit said delete `save-to-obsidian`. **Wrong.** `save-to-obsidian` is the mature, vault-aware skill (73 lines, globs vault, builds `[[wikilinks]]`, multi-file hub notes). `obsidian` is a 36-line skeleton. **Correct action: delete `obsidian`, keep `save-to-obsidian`.**
- **`pdf-recipe`, `pdf-shoplist`, `pdf-star`, `pdf-versova`** — audit said delete (fold into `pdf`). **Wrong.** These are not styling variants. `pdf-recipe` and `pdf-shoplist` use a different engine (puppeteer vs reportlab) and different inputs. `pdf-star`/`pdf-versova` encode real design systems. **Correct action: keep all four. Do not consolidate.**

Codex follow-up: `n8n-*` (7 skills) and `tanstack-*` (4 skills, including disabled `tanstack-start`) have now been re-read at the `SKILL.md` level. They are not deletion-safe duplicates. Keep active members until a deliberate context/tool migration exists; review disabled `tanstack-start` separately.

Codex also found two handoff-level misses: `reactome-database` is not empty; it contains `reactome-database/reactome-database/SKILL.md` plus references/scripts. `torch-geometric` is not an empty shell; it is a disabled twin of `torch_geometric` with matching references/scripts.

User also confirmed: **`artful-*` skills are sacred. Never touch them.** All are correctly classified as `PERSONA_VOICE` / `KEEP` in the audit.

---

## 1. Architecture Changes

None. No code, registry, or settings changes were made to the agent-do codebase. The session was advisory.

---

## 2. Files Created

| File | Purpose | Lines |
|---|---|---|
| `~/.skills/AUDIT.md` | Full skills triage report — buckets, action recommendations, per-skill table, phasing plan; patched by Codex with corrections | 1041 |
| `.handoff/SESSION-HANDOFF-2026-05-07.md` | This document; patched by Codex with correction follow-up | 309 |
| `.handoff/skills-migration-ledger-2026-05-07.md` | Codex-generated ledger from filesystem truth plus TanStack context pilot results | updated |
| `.handoff/skills-consolidation-task-list-2026-05-07.md` | Working task list for marking consolidation progress | current |
| `/tmp/extract_skills.py` | Walks `~/.skills/`, parses SKILL.md frontmatter, writes `/tmp/skills_data.json` | ~60 |
| `/tmp/extract_skills2.py` | Re-processes `.off` files into a separate `disabled` bucket | ~30 |
| `/tmp/classify_skills.py` | Heuristic classifier — assigns bucket + action + note per skill | ~210 |
| `/tmp/write_audit.py` | Composes the final markdown report from classified data | ~140 |
| `/tmp/skills_data.json` | Raw extracted frontmatter (387 active + 50 disabled + 1 error) | — |
| `/tmp/skills_classified.json` | Classified dataset, source for the report | — |
| `/tmp/agent_do_registry.json` | Snapshot of `registry.yaml` tools for cross-referencing | — |

The `/tmp/*` files will be wiped on reboot. Codex created the durable ledger above so future work no longer depends on those temporary classifier artifacts.

---

## 3. Files Modified

| File | Change | Why |
|---|---|---|
| `.gitignore` | Added `.handoff/` to ignore list | Per handoff skill protocol — handoff docs are local, not committed |
| `~/.skills/AUDIT.md` | Added correction notice and patched bad deletion rows | Prevent future deletion work from trusting the bad heuristic bucket |
| `.handoff/SESSION-HANDOFF-2026-05-07.md` | Added Codex follow-up corrections and ledger pointer | Keep the handoff current |
| `.handoff/skills-migration-ledger-2026-05-07.md` | Added verified migration ledger | Create the durable action plan from actual file reads |
| `.handoff/skills-consolidation-task-list-2026-05-07.md` | Added working progress tracker | Give future sessions one place to mark task status |
| `tools/agent-context/agent-context` | Updated help for optional `scan-skills [name ...]` filters | Allow scoped context migration pilots |
| `tools/agent-context/lib/common.sh` | Improved fallback YAML frontmatter parser for block-scalar descriptions | Preserve multiline skill descriptions when PyYAML is unavailable |
| `tools/agent-context/lib/fetch.sh` | `scan-skills` now supports named filters and copies bundled text/code support files | Make skill references/templates retrievable through context |
| `tools/agent-context/lib/search.sh` | Indexes recursive cached package text; supports recursive `get --full`; fixes hyphenated search and SQL fallback | Make context search and retrieval cover support files |
| `tools/agent-context/test/integration.sh` | Made `check_output` use a here-string instead of an `echo | grep -q` pipe | Avoid false failures under `pipefail` on large outputs |

No production code, registry, or skill directory contents were changed.

---

## 4. Files Deleted

None.

---

## 5. Database/Schema Changes

None.

---

## 6. Bugs Fixed

None.

---

## 7. Features Built

None. Audit-only session.

---

## 8. Configuration Changes

| File | Change |
|---|---|
| `.gitignore` | Added `.handoff/` |

No CLAUDE.md edits, no registry edits, no settings.json edits, no hook changes.

---

## 9. Audit Results — `~/.skills/AUDIT.md`

### What was audited
432 skill directories in `~/.skills/` (= `~/.claude/skills/`, symlinked to the same physical directory). Cross-referenced against `registry.yaml` (90 agent-do tools).

### Headline numbers (from the audit)
- 437 classifiable units (387 active + 50 disabled `.off` + classifier misses; `reactome-database` was missed because its skill is nested)
- 17 flagged DELETE_REDUNDANT — **see corrections below, do not trust this bucket**
- 63 flagged FOLD_INTO_TOOL — strategy is sound, individual targets need verification
- 152 flagged FOLD_INTO_CONTEXT — strategy is sound (reference docs belong in `agent-do context`)
- 131 flagged KEEP — includes all `artful-*` (correctly)
- 74 flagged REVIEW (mostly the 50 `.off` skills + meta-skills like `skill-creator`, `hook-development`)

### What is sound in the audit
- The **bucket strategy** (PERSONA_VOICE / DOMAIN_EXPERT / API_WRAPPER / FRAMEWORK_DOCS / etc.) is conceptually correct.
- The **strategic recommendation** (move SDK reference docs into `agent-do context`, keep persona/domain skills, build `agent-bio` and `agent-ai` tool families) is the right direction.
- The **`.off` skill list** (50 entries) is accurate — those are skills with `SKILL.md.off`, already shelved by the user.
- The **`artful-*` classification** is correct (all `PERSONA_VOICE` / `KEEP`).

### What is NOT sound
- The **`DELETE_REDUNDANT` bucket** was generated by name-matching, not content reading. Confirmed errors:

| Skill flagged | Audit said | Actual truth | Source check |
|---|---|---|---|
| `save-to-obsidian` | duplicate of `obsidian` — DELETE | **Keep this one.** Mature, vault-aware, 73 lines, globs vault for `[[wikilinks]]`, multi-file hub notes. | `~/.skills/save-to-obsidian/SKILL.md` |
| `obsidian` | keep | **Delete this one.** 36-line skeleton, hardcoded placeholder tags, no vault scanning. | `~/.skills/obsidian/SKILL.md` |
| `pdf-recipe` | "narrow case — fold into pdf" | **Keep.** Different engine (Node + puppeteer-core), 2-page duplex layout, calls `~/.factory/scripts/generate-recipe-pdf.js`. Not a variant. | `~/.skills/pdf-recipe/SKILL.md` |
| `pdf-shoplist` | "narrow case — fold into pdf" | **Keep.** Different *input* (multiple recipe `.md` → ingredient extraction → category dedup → checkboxes). Data pipeline, not styling. | `~/.skills/pdf-shoplist/SKILL.md` |
| `pdf-star` | "branded variant — fold into pdf with --theme" | **Keep.** Hardcoded to `/Users/erik/Documents/AI/Custom_Coding/IAMtheSTAR/generate-styled-pdf.js`. Lives inside another project. | `~/.skills/pdf-star/SKILL.md` |
| `pdf-versova` | "branded variant — fold into pdf with --theme" | **Keep.** 308 lines of design system: 12 specific hex codes, JetBrains Mono, classification headers/footers. Substantial encoded brand. | `~/.skills/pdf-versova/SKILL.md` |

### Additional false positives verified by Codex
The audit flagged these for "family consolidation, then delete originals." Same name-based heuristic as the pdf-* miss. Codex read the actual skill bodies and found they are not deletion-safe duplicates:

- **`n8n-*` (7)**: `n8n-code-javascript`, `n8n-code-python`, `n8n-expression-syntax`, `n8n-mcp-tools-expert`, `n8n-node-configuration`, `n8n-validation-expert`, `n8n-workflow-patterns`
- **`tanstack-*` (4)**: `tanstack-query`, `tanstack-router`, `tanstack-start` (`.off`), `tanstack-table`

### Plausible deletion candidates (not executed)
- `obsidian` — smaller skeleton; `save-to-obsidian` is canonical and in active use.
- `openai-assistants` — deprecated upstream by OpenAI in favor of Responses API. Also already in `.off` list.
- `torch-geometric` — disabled twin of active `torch_geometric`; not empty, but duplicate by `diff -qr` except `SKILL.md.off` vs `SKILL.md`.

### Verdict on the audit as a whole
**Trust the strategy. Verify every individual deletion against the file contents.** The classifier was too eager to mark same-prefix skills as duplicates without reading them.

---

## 10. Known Remaining Issues

| Priority | Issue | Location | Description |
|---|---|---|---|
| HIGH | Audit deletion bucket was unreliable | `~/.skills/AUDIT.md` "Deletion Candidates Requiring Verification" section | Codex patched the obvious false positives in place. Still do not batch-delete from audit categories. |
| LOW | `reactome-database` packaging is odd | `~/.skills/reactome-database/reactome-database/` | Contains nested `SKILL.md`, references, and script. Repair/repackage review, not deletion. |
| LOW | `torch-geometric` is a disabled duplicate twin | `~/.skills/torch-geometric/` | Has `SKILL.md.off`, references, and scripts matching active `torch_geometric`; confirm before deletion. |
| DONE | Audit document corrected | `~/.skills/AUDIT.md` | Codex added a correction notice and patched the bad rows for obsidian, pdf-*, n8n-*, tanstack-*, torch-geometric, and reactome. |

---

## 11. Verification Commands

```bash
# Verify the audit file exists and is the version this handoff references
wc -l ~/.skills/AUDIT.md
# Expected after Codex correction: 1041 ~/.skills/AUDIT.md

# Verify no agent-do code was changed
cd /Users/erik/Documents/AI/Custom_Coding/agent-do && git status --short
# Expected after Codex correction: clean; .handoff is ignored

# Confirm .handoff is gitignored
cd /Users/erik/Documents/AI/Custom_Coding/agent-do && grep -n "^\.handoff" .gitignore
# Expected: line ~40, ".handoff/"

# Re-verify the obsidian correction (audit was backwards)
wc -l ~/.skills/obsidian/SKILL.md ~/.skills/save-to-obsidian/SKILL.md
# Expected: 36 obsidian, 73 save-to-obsidian — keep the longer one

# Re-verify the pdf-* family is genuinely diverse (audit said "all the same")
for d in pdf pdf-recipe pdf-shoplist pdf-star pdf-versova; do
  echo "=== $d ==="; head -4 ~/.skills/$d/SKILL.md
done

# Recreate the classified dataset if /tmp got wiped
python3 /tmp/extract_skills.py 2>/dev/null && python3 /tmp/extract_skills2.py && python3 /tmp/classify_skills.py
# (Scripts may also be lost on /tmp wipe — copy from this handoff section if needed.)

# Skill counts after Codex correction pass
find ~/.skills -mindepth 1 -maxdepth 1 -type d | wc -l
# Expected: 431 skill directories
ls ~/.skills | wc -l
# Expected: 433 top-level visible entries (431 dirs + AUDIT.md + CATALOG.md)
find ~/.skills -maxdepth 2 -name "SKILL.md.off" | wc -l
# Expected: 50

# agent-do tool count (for cross-referencing)
ls /Users/erik/Documents/AI/Custom_Coding/agent-do/tools/ | grep -c "^agent-"
# Expected: 90 (matches registry.yaml)
```

---

## 12. Subjects/Data State

| Dataset | Location | Rows | Verified? |
|---|---|---|---|
| Skill frontmatter | `/tmp/skills_data.json` | 437 | Yes — generated from `~/.skills/` walk |
| Classified skills | `/tmp/skills_classified.json` | 437 | Yes — but classification has errors (see §9) |
| agent-do registry snapshot | `/tmp/agent_do_registry.json` | 90 | Yes |
| Verified migration ledger | `.handoff/skills-migration-ledger-2026-05-07.md` | 431 skill directories | Yes — generated from current filesystem reads |
| Progress tracker | `.handoff/skills-consolidation-task-list-2026-05-07.md` | task board | Yes — current working list |
| TanStack context pilot | `~/.agent-do/context/cache/skills/skill-tanstack-*` | 3 packages | Yes — support files indexed and retrievable |

**Persistence warning:** All `/tmp/*` artifacts will not survive reboot. The durable outputs are now `~/.skills/AUDIT.md` plus `.handoff/skills-migration-ledger-2026-05-07.md`.

---

## 13. Next Steps (priority order)

### 1. (DONE by Codex) Re-read the audit's deletion bucket against actual file contents
The DELETE_REDUNDANT bucket cannot be trusted as-is. Codex read the remaining n8n and TanStack candidates and patched the audit to mark them not deletion-safe.

```bash
# Previously unverified candidates, now read by Codex
for d in n8n-code-javascript n8n-code-python n8n-expression-syntax \
         n8n-mcp-tools-expert n8n-node-configuration n8n-validation-expert \
         n8n-workflow-patterns \
         tanstack-query tanstack-router tanstack-table; do
  echo "=== $d ==="
  wc -l ~/.skills/$d/SKILL.md
  head -8 ~/.skills/$d/SKILL.md
  echo
done
```

Verdict: these are distinct sub-skills that share a prefix. Do not delete them until a deliberate migration/consolidation exists.

### 2. (DONE by Codex) Patch the audit document
`~/.skills/AUDIT.md` now says:
- keep `save-to-obsidian`; delete/review the smaller `obsidian` skeleton
- keep `pdf-recipe`, `pdf-shoplist`, `pdf-star`, `pdf-versova`
- keep active `n8n-*` and `tanstack-*` until deliberate migration
- treat `reactome-database` as nested/repair-needed, not empty

Codex edited the audit in place and added a correction notice at the top.

### 3. Decide whether to execute a much smaller Phase 0 cleanup
No deletion was executed. Plausible cleanup candidates are:
- `~/.skills/obsidian/` (the skeleton — keep `save-to-obsidian`)
- `~/.skills/openai-assistants/` (deprecated upstream)
- `~/.skills/torch-geometric/` (disabled twin of `torch_geometric`; not empty)

Do not delete `~/.skills/reactome-database/`; repair/repackage review is the correct next step because its skill is nested.

### 3b. (DONE by Codex) Build the verified migration ledger
Created `.handoff/skills-migration-ledger-2026-05-07.md` from current filesystem reads:
- 431 skill directories: 380 active, 50 disabled, 1 nested-active
- actions: 133 KEEP, 161 CONTEXT_MIGRATION, 82 TOOL_MIGRATION, 50 ARCHIVE_CANDIDATE, 4 DEFER_REVIEW, 1 REPAIR
- first batch: approval-only archive review for `obsidian`, `openai-assistants`, `torch-geometric`; repair `reactome-database`; context pilot for `tanstack-query`, `tanstack-router`, `tanstack-table`

### 3c. (DONE by Codex) Run the TanStack context pilot
Patched `agent-context` so `scan-skills` can reindex named skills and preserve bundled support files. Then ran:

```bash
agent-do context scan-skills tanstack-query tanstack-router tanstack-table
```

Verified:
- `skill-tanstack-query` support files, including `references/v4-to-v5-migration.md` and `templates/query-client-config.ts`
- `skill-tanstack-table` support files, including `references/server-side-patterns.md`
- `skill-tanstack-router` support files, including `references/common-errors.md`
- targeted searches for `v4-to-v5 migration keepPreviousData`, `server-side pagination manualPagination TanStack Table`, and `router-devtools-core vite plugin order`

Tests passed:

```bash
bash tools/agent-context/test/integration.sh
./test.sh
```

Source skills were not archived or deleted.

### 4. Decide on `.off` skill purge policy
50 skills are `.off`. The audit suggests "if shelved > 90 days, delete." Implementer choice — either bulk-delete or leave parked.

### 5. Begin Phase 1 (context migration) — only after the deletion bucket is verified
The strategy of moving the 152 reference-doc skills into `agent-do context` is sound, but it's a significant operation and should not start until #1 is done.

### 6. Build `agent-bio` prototype
The 28 biology-database skills (alphafold, pubmed, kegg, etc.) are the highest-leverage consolidation target. Pick 5 highest-traffic, build them as one tool with shared auth/rate-limit/snapshot. The audit Section "Proposed New `agent-do` Tool Families" sketches this.

---

## Important user-stated constraints (do not violate)

- **`artful-*` skills are sacred.** Never delete, never modify without explicit instruction. They are Erik's primary voice/style skills. All correctly classified as `PERSONA_VOICE` / `KEEP`.
- **`save-to-obsidian` is in active daily use.** Do not delete it. The audit was wrong.
- **The `pdf-*` family is in active use.** All five (pdf, pdf-recipe, pdf-shoplist, pdf-star, pdf-versova) are kept. The audit was wrong.
- **Trust the strategy of `~/.skills/AUDIT.md`.** Distrust its individual deletion calls.

---

## Honest assessment of the outgoing session

Two things went wrong here that the next agent (Codex or otherwise) should learn from:

1. **The classifier sorted by name and treated shorter names as canonical.** That's why it picked the 36-line `obsidian` skeleton over the 73-line `save-to-obsidian`. Shorter name ≠ canonical version.
2. **The classifier never opened the files in the `DELETE_REDUNDANT` bucket.** Same-prefix skills (pdf-*, n8n-*, tanstack-*) were assumed to be duplicates without reading the contents. For pdf-* this turned out to be flat wrong: different engines, different inputs, different output structures.

**Rule for next session:** No skill goes on a deletion list without the actual SKILL.md being read first. Heuristics are fine for bucketing into KEEP / FOLD_INTO_CONTEXT / FOLD_INTO_TOOL. They are not fine for deletions.
