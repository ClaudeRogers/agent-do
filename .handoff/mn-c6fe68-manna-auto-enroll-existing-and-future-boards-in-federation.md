---
workflow: 2
manna: mn-c6fe68
track: mn-b7a0cc
source: Erik approval 2026-08-25; follow-up to mn-3962d9
base_commit: 0bff26540561c653e899f07ecd92e0f7b5381bcf
scope: 'Manna: auto-enroll existing and future boards in federation'
inputs:
- Erik approval 2026-08-25; follow-up to mn-3962d9
binding: sha256:cd7a7c535bfb561353f5e75911a33a7b0811381144a5d675b4a56fb1d82f5bb6
---

# Handoff: Manna: auto-enroll existing and future boards in federation

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-c6fe68
```

## Scope

Manna: auto-enroll existing and future boards in federation

## Inputs

- Erik approval 2026-08-25; follow-up to mn-3962d9

## Work order

Make portable federation identity the default for every canonical Manna board. Future boards created by manna init or agent-do bootstrap must receive a tracked federation manifest atomically and idempotently. Backfill every existing canonical Manna board once from an authoritative checkout, with per-repository receipts and without enrolling temporary worktrees, scratch clones, archives, or repositories without Manna. Preserve one shared identity across normal clones and worktrees; intentional independent forks remain explicit through federation fork. Do not infer or auto-create cross-repo relations, do not couple remote lifecycle, and do not push. Validate multi-machine convergence, recovery, existing-board migration, bootstrap behavior, contracts, documentation, and the estate inventory.

## Acceptance

1. `agent-do manna init` returns success only after the board has one valid tracked federation identity; reruns preserve its exact bytes and ID.
2. `agent-do manna migrate` leaves a migrated legacy board with the same default identity guarantee.
3. `agent-do bootstrap --recommend` identifies a strict Manna board missing federation identity, and ordinary bootstrap repairs it through the canonical `manna init` path.
4. A crash or failure between workflow convergence and federation convergence fails closed; a normal rerun recovers without replacing an already published identity.
5. Existing canonical boards receive exactly one identity from their primary checkout. Linked worktrees, scratch clones, archives, non-Manna repositories, and independently dirty replicas are excluded and named.
6. Normal clones and worktrees inherit the committed ID. Independent projects still require `federation fork --reason`.
7. No relation is inferred or created during initialization or migration.
8. The delivery records the exact estate denominator, initialized count, prior-enrollment count, exclusions, commit receipts, validation receipts, and the fact that nothing was pushed.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-c6fe68`.
4. Commit with `Manna: mn-c6fe68` and run `agent-do manna done mn-c6fe68` only after the work is verified.

## Delivery

Completed locally on 2026-08-25. Automatic identity enrollment is now the canonical Manna behavior, and the existing Git-backed board estate has been backfilled without inventing relations or publishing remote refs.

### Product behavior

- `manna init` and `manna migrate` converge workflow state and `.manna/federation.yaml` before reporting success.
- The first global-inbox dream also creates federation identity through the canonical initialization path.
- `agent-do bootstrap --recommend` and SessionStart repair discovery treat a missing federation manifest as incomplete Manna setup.
- A rerun preserves the existing manifest bytes and board ID. An interrupted first run fails closed and a normal rerun converges.
- The generated manifest is Git-visible and contains `relations: []`. Initialization never infers a cross-repository relation.
- Explicit `manna federation init` remains an idempotent repair command. Intentional identity separation still uses `manna federation fork --reason`.

### Implementation commits

| Commit | Purpose |
| --- | --- |
| `3f1e758` | Detect missing federation identity in bootstrap and SessionStart repair surfaces. |
| `688b938` | Auto-enroll init, migrate, and first global-inbox dream; add recovery, idempotency, Git-visibility, and documentation coverage. |
| `051b252` | Pin the routing test fixture to the checkout under test. |
| `14ad265` | Add this repository's tracked federation identity. |

### Estate denominator

The refreshed scan found 35 registered repository roots under `/Users/erik/Custom-Coding`:

- 23 authoritative, committed Manna repositories: initialized 23, previously initialized 0, unique identities 23.
- 9 linked worktrees: inherited their canonical repository's exact manifest, producing no new identities.
- 2 unborn scratch-stage repositories: excluded untouched.
- 1 repository without a Manna board: excluded untouched.

That yields 32 usable checkouts carrying 23 canonical identities. Every canonical manifest is tracked, clean relative to its checkout, byte-identical at `HEAD`, and introduced by a one-file commit carrying `Manna: mn-c6fe68`.

### Canonical board receipts

| Repository | Branch | Manifest commit | Board ID |
| --- | --- | --- | --- |
| `IAMthat.vision` | `main` | `42e294880b14a5473ab37915a09fce120018e950` | `mb-691e7d17571c4a61f5ea3ac30e9e20f0` |
| `X-writings` | `main` | `9371bce901c90f2c200b635239319cba3b90d662` | `mb-775079170d358bdf057941b242d01f23` |
| `agent-do` | `main` | `14ad265f6484eadc33dfd2f82e6ad6ff01a78f89` | `mb-615bf342bcb87e41e7d54a7c6c0b84ae` |
| `agent-llm` | `main` | `66b8d906dcdbf615bf736568a4cc9ac527813f92` | `mb-ff5fb3826a79aeb4c7f8808c12f4f019` |
| `agent-sessions` | `main` | `154cf9c82cc5c459a4418cf757b4b4e6f2195195` | `mb-418c9c2b0ee805492e5e113dd9f199e7` |
| `aldebaran-group` | `main` | `3c49b3834d025161d78c916f4b237938b472877f` | `mb-dd0c7bb728d3dbcd7b02078b6e7ccc8d` |
| `aldebaran-group/dm-ds-lab` | `agent/iamthat-resonance-eval` | `686bdc73f78ed651e5aa647379ab56066bec1563` | `mb-a2c71a0e7bd8aae32eb021d4c2fabcfd` |
| `aldebaran-group/dm-ephemeris` | `main` | `3fe6ace0bb0be3edb9f8d4813953d9dacf0ab5d5` | `mb-5ede9590ddc309131765c04d6200cfaa` |
| `aqueduct-dream` | `main` | `254731d3157c6144b1c56f76dedec746b8da5a10` | `mb-8bc2c541962c214df7f835afc4266aa6` |
| `business-plan-builder` | `main` | `958b562eeb6e44d2400a1a1cc085c8664f902ecf` | `mb-8bf5e6e1cc4b09978448e0fa196c3b1b` |
| `holy-ghostty` | `main` | `7b16f9136c628a7928baaaab6148dde09fbe6778` | `mb-87598702f834dad27f9bb5856a2072ea` |
| `old-model-detector` | `main` | `41a9bf9f4e5be9c613c4c74b3d6993aff826dc64` | `mb-868c0b2e0b30c7bec1ad1cedff9b0a59` |
| `palingenesis` | `main` | `30a0c419b67d4d63402a2304e668d04ce05a7644` | `mb-1412f9334b84defdec0bf0cd048f7a58` |
| `scale-mechanics` | `main` | `0a27a773b30244a68bd840b0fcb7c9567e0e0caf` | `mb-27a3c1ac08d0af2ae0e200c708bc5640` |
| `substack-writings` | `main` | `9ad3206c47af70d90e9398b83206e5ea9f3c28e1` | `mb-51006bcb8a35fca3909e930acb88b450` |
| `the-orient` | `main` | `14d571a5cca9429e7bcdec04df017983c0d68c14` | `mb-31befd9de75db231d3fc49883cf82fe8` |
| `the-point-revision` | `main` | `4796a5a3dabbae6be9ea28a46ba2e3a5a8609b60` | `mb-101c82071da7d5d88ab3e00150130bba` |
| `theta-indi` | `main` | `23c20150b4a6162339ac11a4a849cbe3b837a32e` | `mb-3c49f124a80791eabb112f070289a2ed` |
| `versova-align` | `q2-project-actions-menu` | `7fc61d6bc1c056c01f5b7f8b1448de4541fffd96` | `mb-ea94cb84fa6b2c31b3bde32051350a1b` |
| `versova-mr_president` | `sec/web-auth-hardening` | `63feb53c4c1b8e9b431f777221ce9f79f2e87b16` | `mb-494379337dce4ddf1bafa5793f007710` |
| `versova-research` | `staging` | `725443866a5aa9da7896cb68e86f86f4e36f8c5e` | `mb-66ed9fd1faed0ee09d173b941d4b2bc1` |
| `versova-supply-intelligence` | `main` | `2d66c67a3e228203dfbf4f6fcafaae09463bd798` | `mb-d31bed25dfecd803f17707e441e48b6b` |
| `vms.io` | `main` | `9a921babcf7a0598ddab6605722e60e56a1d0ba5` | `mb-8d5aaab0bfa0cecbc476f2ae4bebef9a` |

### Linked-worktree receipts

| Worktree | Branch | Manifest commit | Canonical identity |
| --- | --- | --- | --- |
| `agent-do-manna-integrity` | `fix/manna-integrity` | `03282b3024b8c26bdd443627a967d81d171fbac9` | `agent-do` |
| `agent-do-manna-legacy-ordering` | `fix/manna-legacy-migration-ordering` | `954f72c83aa6856982a01af878fd97c27073e152` | `agent-do` |
| `agent-do-manna-mixed-convergence` | `fix/manna-mixed-convergence` | `e504591dd76babf061094ba77b6af172879b6b1f` | `agent-do` |
| `agent-do-mn-3962d9-federation` | `feat/mn-3962d9-federation` | `7c793233f5699331344808c95259e9c0d88b8f8c` | `agent-do` |
| `agent-do-mn-c6fe68-auto-enroll` | `feat/mn-c6fe68-auto-enroll` | `5400d4ddfbf63e520e8ff9d85751cb8362d51b48` | `agent-do` |
| `vms-c02` | `feat/people-wave` | `be96453ef29693247bdf4a1a63133e5a1a628083` | `vms.io` |
| `vms-c03` | `feat/platform-glue` | `9e27bd33809db1223f2fdcbad074c76390cbc769` | `vms.io` |
| `vms-c06` | `fix/strety-vto-form-rename` | `eb8ea95360ff2c3964ed9093d27bdb3cb674f83a` | `vms.io` |
| `vms-c09` | `fix/campaign-09-security-sweep` | `8df5f3b38e971924dbeb1de6767beceb3a1f6749` | `vms.io` |

The replica commits contain only `.manna/federation.yaml`, carry `Manna: mn-c6fe68`, and preserve each parent repository's exact manifest bytes. Older agent-do worktree branches were not forced through newer board migration rules; the manifest was propagated through ordinary Git history.

### Exclusions

| Repository | Reason |
| --- | --- |
| `automation-station` | Unborn `main` with no checked-in branch commit and zero issue rows. A safety snapshot ref exists, but it is not release history. |
| `egora` | Unborn `main` with no checked-in branch commit. Its one-row scratch board remains untouched. |
| `fritsch-food` | No `.manna/issues.jsonl`, so it is not a Manna board. |

### Verification receipts

- `bash tools/agent-manna/test/integration.sh`: 385 passed, 0 failed.
- `cargo fmt --check`: passed.
- `cargo clippy --all-targets --all-features -- -D warnings`: passed.
- `cargo test`: 159 library tests and 43 CLI tests passed.
- `python tests/test_session_start_reads.py`: passed.
- `python tests/test_v11_routing.py`: passed after pinning its executable lookup to the checkout under test.
- `./test.sh`: 116 passed, 0 failed in the canonical environment. The first isolated-worktree run reported 11 dependency-start failures because PyYAML and browser `node_modules` were absent there; the corrected canonical-environment rerun was fully green.
- Estate verifier: 23 canonical manifests, 23 unique valid IDs, 9 byte-identical linked replicas, 3 named exclusions, 32 usable checkouts, and no federation journal residue.
- Idempotency verifier: all 23 canonical `manna init` reruns returned `changed: false`.
- `agent-do manna serve --scan /Users/erik/Custom-Coding --json`: refreshed 35 registered roots.
- Production binary rebuilt with `cargo build --release`.

### Publication boundary

Nothing was pushed. The behavior and all receipts are complete on this machine. Other machines receive the automatic default only after the agent-do commits are published through the normal Git release path. Four canonical receipts currently live on non-main branches (`dm-ds-lab`, `versova-align`, `versova-mr_president`, and `versova-research`), and the nine linked-worktree receipts remain on their named branches until normal branch integration.
