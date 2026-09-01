---
workflow: 2
manna: mn-3962d9
track: mn-b7a0cc
source: Erik approval 2026-08-24; .handoff/mn-e40d9a-manna-research-if-how-cross-repo-board-linkage-should-exist.md
base_commit: c69860b2158aca1c1a90e1afff17af3cf40a018a
scope: 'Manna: implement portable cross-repo federation'
inputs:
- Erik approval 2026-08-24; .handoff/mn-e40d9a-manna-research-if-how-cross-repo-board-linkage-should-exist.md
binding: sha256:714c6e90a003d5ff5b9e0352d67745e69c3739bd1debfa2cd4ed671862ff6426
---

# Handoff: Manna: implement portable cross-repo federation

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-3962d9
```

## Scope

Manna: implement portable cross-repo federation

## Inputs

- Erik approval 2026-08-24; .handoff/mn-e40d9a-manna-research-if-how-cross-repo-board-linkage-should-exist.md

## Work order

Implement the Erik-approved mn-e40d9a federation v1 specification in full: tracked .manna/federation.yaml identity and relation authority, typed board-qualified relations, authenticated journaled mutations, local-only lint and reconcile rules, registry-backed resolved/unavailable/missing/ambiguous reads, counterpart reciprocity, serve rendering, registry contracts, documentation, and the complete hermetic test matrix. Preserve local ownership, blocker, done, pairing, handoff, and landed-evidence invariants. Do not add relation fields to Issue, couple local lifecycle to remote state, auto-migrate prose, or choose divergent replicas.

## Delivery

Completed on local `main` in commit `901490541ce40e94b10b44764164326033addd96` (`feat(manna): add portable board federation`). No remote ref was pushed.

Shipped:

- Opt-in tracked `.manna/federation.yaml` manifests with stable `mb-` plus 32-lowercase-hex identities.
- `federation init`, `federation status`, `federation fork`, `relate`, `unrelate`, and `relations` command surfaces.
- The closed relation vocabulary: `counterpart`, `informed_by`, `depends_on`, and `supersedes`.
- HMAC-authenticated, project-bound, board-locked, crash-recoverable mutations and fork archives.
- Registry-backed resolution with `resolved`, `unavailable`, `missing`, and `ambiguous` states, plus four-state counterpart reciprocity.
- Local-only lint and reconcile validation. Remote lifecycle and remote commit evidence remain derived display data only.
- Federation identity and relation rendering in the incumbent Manna cockpit.
- Registry contracts, generated tool documentation, architecture/schema/user documentation, Rust tests, Python serve tests, and hermetic two-board integration coverage.

Preserved invariants:

- Existing boards remain federation-disabled until an explicit `agent-do manna federation init`.
- Relations are not stored on `Issue`; local ownership, blockers, completion, handoff seals, and landed evidence remain locally authoritative.
- Remote completion never mutates source issue or handoff bytes.
- Missing and ambiguous targets fail `relations --check`; an unavailable registry is a successful degraded read.
- Divergent replicas are never selected by registry order.

Verification receipts:

- `./test.sh`: 115 passed, 0 failed.
- `cargo fmt --check`: passed.
- `cargo clippy --all-targets -- -D warnings`: passed.
- `cargo test`: 159 library tests and 43 CLI tests passed, 0 failed.
- `bash tools/agent-manna/test/integration.sh`: 363 passed, 0 failed.
- `python -m unittest tests.test_manna_serve`: 32 passed, 0 failed.
- `agent-do harness contracts validate`: 99 tools, 99 declared, 0 missing, 0 errors, 0 warnings.
- `agent-do harness contracts drift`: 0 declared-but-unimplemented verbs.
- `bin/gen-tools-doc --check`: passed.

Needed next: none for the approved implementation. Adoption is intentionally explicit per repository.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-3962d9`.
4. Commit with `Manna: mn-3962d9` and run `agent-do manna done mn-3962d9` only after the work is verified.
