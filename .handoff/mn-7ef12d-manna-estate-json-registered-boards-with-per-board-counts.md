---
workflow: 2
manna: mn-7ef12d
track: mn-b7a0cc
source: 'Erik ratified design 2026-08-31 (Holy: One Ledger, Two Faces — track mn-9a97cc on holy-ghostty''s board). Consumer: Holy native board/attention surfaces. Filed by the holy-ghostty design session; agent-do worker builds it.'
base_commit: 7f7ac1c639dd3a56ad6ddcc98672416c36999270
scope: 'manna estate --json: registered boards with per-board counts'
inputs:
- 'Erik ratified design 2026-08-31 (Holy: One Ledger, Two Faces — track mn-9a97cc on holy-ghostty''s board). Consumer: Holy native board/attention surfaces. Filed by the holy-ghostty design session; agent-do worker builds it.'
binding: sha256:2c7f03fd0a31e365ecfb121bb8593578e9c28fb1588ba0d691be80becb3dd183
---

# Handoff: manna estate --json: registered boards with per-board counts

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-7ef12d
```

## Scope

manna estate --json: registered boards with per-board counts

## Inputs

- Erik ratified design 2026-08-31 (Holy: One Ledger, Two Faces — track mn-9a97cc on holy-ghostty's board). Consumer: Holy native board/attention surfaces. Filed by the holy-ghostty design session; agent-do worker builds it.

## Work order

Machine-readable estate: every board in the serve registry (~/.agent-do/manna/serve/boards.json) with root, slug, status counts, dreams, decisions, drift count+age, latest update, and coord attention rollup (needs-you/working/here/gone) — the /api/boards shape as a core CLI output, independent of the serve daemon. Consumer: Holy's estate strip and single attention badge. House pattern registry+contracts+tests+docs.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-7ef12d`.
4. Commit with `Manna: mn-7ef12d` and run `agent-do manna done mn-7ef12d` only after the work is verified.

## Delivered

- Added `manna estate [--json]` as a daemon-independent CLI over the exact
  `/api/boards` derivation.
- Preserved every registered board, including missing roots, with root, slug,
  effective status counts, dreams, decisions, drift timestamp and count,
  latest update, and coord attention rollups.
- Registered `estate` as a read-only snapshot verb and regenerated the public
  tool catalog.
- Added focused adapter, wrapper, error, YAML, JSON, missing-root, and
  no-daemon coverage.

## Validation

- `./test.sh`: 121 passed, 0 failed on a tracked-source-stable snapshot
  (`sha256:c2c054ce27e0cc2dcb3e0f4feb951b5971ee67cd861bbd360691591676edf71e`).
- `python tests/test_manna_estate.py`: 4 passed.
- Live `manna estate --json`: 35 registered boards, zero building rows, and
  every row carried the required contract fields.
- `agent-do harness contracts validate`: 102 of 102 tools declared, zero
  errors, zero warnings.
- `agent-do harness contracts drift --json`: `ok: true`, zero declared-only
  verbs.
- `bin/gen-tools-doc --check`, `bash -n`, `py_compile`, and `git diff --check`:
  passed.
