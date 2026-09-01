---
workflow: 2
manna: mn-c7e91b
track: mn-b7a0cc
source: 'Erik ratified design 2026-08-31 (Holy: One Ledger, Two Faces — track mn-9a97cc on holy-ghostty''s board). Consumer: Holy native board/attention surfaces. Filed by the holy-ghostty design session; agent-do worker builds it.'
base_commit: 7f7ac1c639dd3a56ad6ddcc98672416c36999270
scope: 'manna state --json: expose the derived board model from the core'
inputs:
- 'Erik ratified design 2026-08-31 (Holy: One Ledger, Two Faces — track mn-9a97cc on holy-ghostty''s board). Consumer: Holy native board/attention surfaces. Filed by the holy-ghostty design session; agent-do worker builds it.'
binding: sha256:667c27a305ba129a51a776b137abd4a597c256437527d37d77a4843bace68e24
---

# Handoff: manna state --json: expose the derived board model from the core

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-c7e91b
```

## Scope

manna state --json: expose the derived board model from the core

## Inputs

- Erik ratified design 2026-08-31 (Holy: One Ledger, Two Faces — track mn-9a97cc on holy-ghostty's board). Consumer: Holy native board/attention surfaces. Filed by the holy-ghostty design session; agent-do worker builds it.

## Work order

Promote the rich derived board model to a first-class core output. serve's board.py already derives it (items joined with blockers, dependents, handoff order, claimant liveness+pulse, Manna-trailer commits, drift, federation, git summary, effective-status buckets now/next/waiting/decisions/dreams/tracks); the core offers only the thin list --json (no description, no blocked_by, no prompt) and show has no --json at all. Deliver: manna state --json returning the full page-model shape (minus per-process act_token/actor; claim_token_hash and legacy_migration stay stripped), house pattern registry+contracts+tests+docs; rebase serve on it so page and native clients render one output. Holy consumes this verbatim — it replaces manna list --json as Holy's contract.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-c7e91b`.
4. Commit with `Manna: mn-c7e91b` and run `agent-do manna done mn-c7e91b` only after the work is verified.

## Delivered

- Added `manna state --json` as the canonical whole-board model in the Rust core.
- Preserved complete public issue rows while stripping `claim_token_hash`,
  `legacy_migration`, `act_token`, and `actor` from the contract.
- Derived graph buckets, handoff priority, claimant attention, Git receipts,
  drift, federation, and coord state once in the core.
- Replaced the Python page-model derivation with a thin adapter over the core
  command. The serve daemon now adds only its process-local fields.
- Registered the command and updated the public and tool-specific docs.

## Verification receipts

- `PATH="$PWD/.venv/bin:$PATH" ./test.sh`: 121 passed, 0 failed.
- `PATH="$PWD/.venv/bin:$PATH" bash tools/agent-manna/test/integration.sh`:
  387 passed, 0 failed.
- `PATH="$PWD/.venv/bin:$PATH" .venv/bin/python tests/test_manna_serve.py`:
  41 passed.
- `cargo test --quiet --manifest-path tools/agent-manna/Cargo.toml`: 208
  passed across the library and binary targets.
- `cargo clippy --manifest-path tools/agent-manna/Cargo.toml --all-targets -- -D warnings`:
  passed.
- `cargo fmt --manifest-path tools/agent-manna/Cargo.toml -- --check`: passed.
- `agent-do harness contracts validate`: 102 declared tools, 0 errors, 0
  warnings.
- `bin/gen-tools-doc --check`: passed.
