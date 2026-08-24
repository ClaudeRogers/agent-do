---
workflow: 2
manna: mn-e40d9a
track: mn-b7a0cc
source: null
base_commit: 3183ffc020a07ae7e375f81f067098326e80d5e6
scope: 'Manna: research if/how cross-repo board linkage should exist'
inputs: []
binding: sha256:252a6ed5812884cb8768ad7d1d7c7e340ac1436b5832db983a0a2e7d18aff95c
---

# Handoff: Manna: research if/how cross-repo board linkage should exist

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-e40d9a
```

## Scope

Manna: research if/how cross-repo board linkage should exist

## Inputs

- None declared.

## Work order

RESEARCH AND DESIGN ONLY - no implementation; the deliverable is a grounded recommendation Erik rules on. Do not bolt on a link field.

THE QUESTION: Boards are per-repo by design, but real work now spans repos - one program produced tool work on the agent-do board (mn-7ec6dc, mn-2521d5, mn-55530d) and product work on the palingenesis board (mn-27a833) with genuine dependency and shared provenance between them, held together today only by prose mentions. Erik (2026-08-24): we need a way to link manna or something - but it cannot be a quick bolt-on; it should be properly researched and grounded against existing code and manna direction. Decide IF cross-repo linkage belongs in manna's grammar at all, and if yes, design it properly.

GROUND YOURSELF FIRST (all in this repo unless noted):
- Doctrine: ARCHITECTURE.md Manna Subsystem section; CLAUDE.md Manna Board Conventions (grammar track|item|dream, single-truth rule, pairing gate, ownership gate/proof digests, trailer rule, landed_open self-cure, reconcile/lint semantics); the worktree note (boards do not follow worktrees).
- Code: tools/agent-manna (Rust: clap/serde/serde_yaml/sha2/fs2) - schema, verbs, reconcile, lint, sync, serve. Note manna serve already maintains a machine-local registry of every board for its root index - the natural substrate any cross-board resolution would use.
- Prior art in-estate: items' source: citation field and track: edges (same-board only); coord drops (cross-session pointers); agent-brief joining gh<->manna<->coord; zpc decisions on manna (query zpc for manna/board lessons and decisions).
- The motivating case study: this session's dual-track work (see agent-do .handoff/dpt-audit-2026-08-22.md and the design-rounds item mn-7ec6dc for the agent-do side; palingenesis mn-27a833 for the product side).

QUESTIONS THE RECOMMENDATION MUST ANSWER:
1. Is cross-repo linkage a real recurring need or a one-program artifact? Inventory actual cases (search both boards, zpc, handoffs).
2. If real: does it belong IN manna's grammar (schema field + verbs), ABOVE it (a federation/registry layer reading multiple boards, like serve/brief do), or BESIDE it (convention: sibling items citing counterpart ids in source:/description - the zero-code option usable today)?
3. What must a link NEVER break: per-repo ownership proofs, the pairing gate, landed_open evidence rules, reconcile/lint truthfulness on a board that cannot see the other repo, git-backed portability of a board cloned without its counterpart.
4. Semantics if built: link types (counterpart|blocks|informs|supersedes?), dangling-link behavior when the other repo is absent (degrade to citation, never error), whether done/reconcile should surface sibling state, lint rules, serve rendering.
5. Migration/adoption: what happens to today's prose-linked pairs; does the sibling convention remain the recommended floor even if a feature ships.

DELIVERABLE: a recommendation document (in this repo's .handoff/, named by this item) with: the case inventory, the decision (do nothing / convention only / registry layer / grammar change) with rationale grounded in the doctrine above, a falsifiable acceptance test for whichever is recommended, and - only if a build is recommended - a full implementation spec (schema, verbs, contracts block, lint/reconcile changes, tests) sized for a follow-up item. Record the load-bearing claim as a zpc position with falsifier. Implementation waits for Erik's ruling on the recommendation - taxonomy gate applies.

## Recommendation

Build a portable federation layer after Erik rules. Do not add a link field to
`Issue`, and do not let one board's lifecycle depend on another board being
present.

The correct boundary is:

1. Each participating repository carries its own durable board identity and
   outbound relation declarations in a tracked `.manna/federation.yaml`.
2. The existing machine-local `manna serve` registry resolves those declarations
   when counterpart boards are available.
3. Local Manna remains the sole authority for claim, block, done, handoff
   pairing, landed evidence, lint, and reconcile.
4. Missing counterpart boards degrade to an unresolved citation. They never make
   the local board invalid.

This is not a centralized estate board. It is a federation of autonomous boards.
The declaration travels with Git; the live explanation is a cache.

The load-bearing position is recorded as ZPC `pos-d13c04`:

> Cross-repo Manna relationships should be durable, board-qualified declarations
> in a repo-tracked federation manifest, resolved opportunistically by the
> machine-local board registry; they must never become remote lifecycle authority.

Its falsifier is a real admitted program that cannot remain truthful without an
atomic cross-board status transition, or a two-board fixture where the manifest
cannot stay lint-clean offline while resolution distinguishes absent, missing,
and divergent replicas.

## Case inventory

### Method and denominator

A bounded read-only scan covered `.manna/issues.jsonl` files under
`/Users/erik/Custom-Coding` to depth four. It pruned `.git`, `node_modules`,
`target`, virtual environments, `dist`, and `build`. It excluded exactly three
known agent-do Manna test-worktree copies:

- `agent-do-manna-integrity`
- `agent-do-manna-legacy-ordering`
- `agent-do-manna-mixed-convergence`

The remaining denominator was 30 boards and 1,110 issue rows. Excluding this
research item so it could not prove its own premise, the scan found:

- 91 cross-board ID field occurrences;
- 53 source issues;
- 10 directional repository pairs;
- 7 source boards;
- 87 occurrences in `description`, 3 in `title`, and 1 in `source`.

The 91 count is field occurrences, not inferred semantic edges. One issue names
the same target in both `description` and `source`. The scan makes a bounded
absence claim only: it does not inspect boards outside the named root or depth.

### Recurring shapes already in the estate

| Shape | Directional pairs | Evidence |
| --- | --- | --- |
| Tool and product integration | `agent-do` to `holy-ghostty`, and back | `agent-do/.manna/issues.jsonl:16,88,90,103`; `holy-ghostty/.manna/issues.jsonl:71,82` |
| Runtime provider and UI consumer | `agent-sessions` to `holy-ghostty`, and back | `agent-sessions/.manna/issues.jsonl:5-6`; `holy-ghostty/.manna/issues.jsonl:14,54` |
| Program root and engine subrepo | `aldebaran-group` to `dm-ephemeris`, and back | 38 outward and 31 return occurrences, including `aldebaran-group/.manna/issues.jsonl:23,39,164` and `aldebaran-group/dm-ephemeris/.manna/issues.jsonl:23-29,92-99` |
| Program root and research subrepo | `aldebaran-group` to `dm-ds-lab` | `aldebaran-group/.manna/issues.jsonl:235` |
| Downstream business artifact and source program | `business-plan-builder` to `aldebaran-group` | `business-plan-builder/.manna/issues.jsonl:1-2` |
| Publication and source research | `substack-writings` to `the-orient` and `scale-mechanics` | `substack-writings/.manna/issues.jsonl:27,67,69,71` |

This is recurring infrastructure pressure, not one Palingenesis artifact. The
largest cluster is parent-program to engine-repo coordination, while the
agent-do, Holy Ghostty, and agent-sessions pairs prove the same need between
independent products.

### Motivating Palingenesis case

The current case has real shared provenance but no machine-readable edge:

- The agent-do audit produced the DPT floor judgment and the repair items
  `mn-2521d5` and `mn-55530d` (`agent-do/.handoff/dpt-audit-2026-08-22.md` and
  `agent-do/.manna/issues.jsonl:105,110`).
- The Palingenesis work order says the agent-do engine was audited against that
  product, repaired in three waves, and carries its receipts by repo path
  (`palingenesis/.dev/session-prompts/08-dpt-scoring-truth.md:8-14`).
- Palingenesis `mn-27a833` points only to its local prompt and sibling product
  items (`palingenesis/.manna/issues.jsonl:37`). It does not identify the
  producing agent-do Manna items.
- Agent-do `mn-7ec6dc` says the design-rounds method was proven in Palingenesis
  (`agent-do/.manna/issues.jsonl:116`) but does not identify a Palingenesis board
  coordinate.

The facts exist. Their lineage is human-readable but not queryable.

### IDs are local, not estate-global

Thirteen `mn-xxxxxx` values occur in all five `vms.io`, `vms-c02`, `vms-c03`,
`vms-c06`, and `vms-c09` boards. These are inherited board copies, not evidence
of random generator collision. They still prove the architectural point: an
`mn-` ID alone cannot name one issue across the estate. A relation needs a board
coordinate plus the local issue ID.

## Current architecture constraints

1. `Issue` currently carries only local `track`, provenance `source`, paired
   `prompt`, and `handoff_digest` fields
   (`tools/agent-manna/src/issue.rs:144-212`). `track` validates against the same
   loaded issue set (`tools/agent-manna/src/main.rs:672-684`).
2. `.manna/board.yaml` pins strict versus legacy workflow but has no globally
   stable board coordinate (`tools/agent-manna/src/workflow.rs:87-112`).
3. A board is rooted at the checkout-local `.manna/`
   (`tools/agent-manna/src/store.rs:17-57`). The repo deliberately warns that a
   worktree carries another board copy (`tools/agent-coord:134-139` and
   `tests/test_worktree_binding.py:243-260`).
4. Ownership is local and proof-bearing. A visible claimant label cannot mutate
   a claimed row without the session token proof
   (`tools/agent-manna/src/issue.rs:358-386`).
5. `landed_open`, handoff pairing, and reconcile read local Git and local board
   state. Reverse pairing deliberately ignores foreign-board IDs
   (`tools/agent-manna/src/main.rs:2283-2312`).
6. `manna serve` already owns the correct discovery substrate: a machine-local
   path registry that indexes every registered board, but explicitly says it is
   a rendering and never a source
   (`tools/agent-manna/serve/serve.py:1-13,93-170,353-390`).
7. `agent-brief` proves the join pattern above the board. It reads one focused
   board, then joins GitHub, commits, coord, and sessions around the local Manna
   ID spine (`tools/agent-brief:272-325,466-529`). It does not make those systems
   board authority.

These constraints are strengths. Federation should compose them, not dissolve
them.

## Option decision

| Option | Decision | Reason |
| --- | --- | --- |
| Do nothing | Reject | The bounded estate inventory found 53 source issues across 10 directional repo pairs. |
| Convention only | Keep as the immediate floor, reject as the final design | It is portable and usable now, but cannot distinguish relation type, resolve status, detect stale targets, or disambiguate copied IDs. |
| Machine registry only | Reject | `~/.agent-do/manna/serve/boards.json` is machine-local derived state. Links stored there disappear on another machine and violate Git-backed portability. |
| Add `relations` to every `Issue` row | Reject | It expands the core item grammar, rewrites JSONL rows for metadata unrelated to local lifecycle, and tempts `blocked_by` or `done` to consult remote state. |
| Tracked federation manifest plus optional registry resolution | Recommend | The declaration remains portable and reviewable in its source repo while live resolution stays explicitly derived and degradable. |

External systems support typed relations, but they do so inside centralized
identity and authority domains. GitHub can add sub-issues from other repositories
and its dependency API identifies both repository and issue. Linear exposes
blocking, related, and duplicate relations inside one workspace. Jira links work
across spaces inside one site. Manna should borrow typed relation clarity, not
their central lifecycle coupling:

- [GitHub cross-repository sub-issues](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues?apiVersion=2022-11-28)
- [GitHub issue dependency API](https://docs.github.com/en/rest/issues/issue-dependencies)
- [Linear issue relations](https://linear.app/docs/issue-relations)
- [Jira linked work items](https://support.atlassian.com/jira-software-cloud/docs/link-issues/)

## Hard invariants

1. A repository cloned without any counterpart must retain the exact relation
   declaration and pass local `manna lint` and `manna reconcile`.
2. The durable coordinate is `board_id + issue_id`, never a path, registry slug,
   remote URL, or bare `mn-` ID.
3. The registry is a resolver cache. It cannot create, remove, or become the sole
   copy of a relation.
4. No relation may claim, block, unblock, complete, reopen, delete, reseal, or
   reconcile an issue in another board.
5. Local `blocked_by` remains local. External dependency state may be displayed,
   but it cannot derive local `status`.
6. Handoff pairing and digests remain byte-for-byte independent of federation.
7. `landed_open` accepts only local `Manna:` trailers from local Git history.
   A linked target's commit is never landing evidence for the source issue.
8. An unavailable target is expected degradation, not corruption. A present
   board missing the target is a stale-link observation, not a local lint error.
9. Multiple registered roots with one board ID are replicas. If their target row
   bytes disagree, resolution is `ambiguous`; the resolver never picks a winner.
10. Cross-board writes are never atomic. Reciprocity is two declarations, and
    one-way state remains valid and visible.
11. No prose link is auto-promoted. A candidate detector may propose relations,
    but an authenticated explicit command admits each declaration.
12. `source` remains provenance. It is not converted into a generic relationship
    bag.

## Full implementation specification

### Durable schema

Add one optional tracked authority file:

```yaml
version: 1
board_id: mb-5c54d1b4cce04f8b9f4418a9180ad87e
relations:
  - from: mn-27a833
    kind: informed_by
    to: manna://mb-973809091a7444329b38fa9a1ee7979f/mn-55530d
    hint: agent-do
```

Rules:

- `board_id` is `mb-` plus 32 lowercase hex characters generated from 128 bits
  of `OsRng`. It is public identity, not a credential.
- A normal clone or Git worktree preserves `board_id` and is another replica of
  the same logical board.
- An intentional project fork uses an explicit journaled `federation fork`
  operation. It generates a new ID, archives the inherited manifest, and starts
  with no active relations. It never silently inherits external authority.
- `from` must exist on the local board.
- `to` is the canonical portable URI `manna://<board_id>/<issue_id>`.
- `hint` is optional human context. It is never identity and may be stale.
- Rows serialize in deterministic `(from, kind, to)` order with exact duplicate
  rejection.
- Git history is the audit trail. Target title, status, claimant, path, and last
  resolution are never copied into the durable file.

Do not add fields to `Issue` or `.manna/board.yaml` in version 1. Keeping the
optional federation identity in its own manifest lets existing boards remain
valid until they opt in and keeps older issue JSONL readers intact.

### Relation vocabulary

| Kind | Meaning from the local issue's perspective | Lifecycle effect |
| --- | --- | --- |
| `counterpart` | The target is the same program concern split across board ownership. Symmetry is expected but not required. | None |
| `informed_by` | The local issue consumes evidence, doctrine, or a deliverable produced by the target. | None |
| `depends_on` | The local outcome relies on the target outcome. The resolver may show target status. | None |
| `supersedes` | The local issue replaces the target in program lineage. | None; it does not close the target |

Version 1 must not include `blocks`, `blocked_by`, `duplicate`, or a generic
`related` kind:

- `blocks` implies status authority Manna cannot truthfully exercise offline.
- `duplicate` implies a canonical merge and lifecycle transition across boards.
- `related` is a junk drawer that adds no action beyond prose.

If a program requires fail-closed cross-board gating, federation version 1 is
not sufficient. Keep the gate in one controlling board and return for a separate
authority design. Do not simulate the gate with status polling or manual closure.

### Commands

```text
agent-do manna federation init
agent-do manna federation status [--json]
agent-do manna federation fork --reason <text>
agent-do manna relate <local-id> --kind <kind> --to <manna-uri> [--hint <text>]
agent-do manna unrelate <local-id> --kind <kind> --to <manna-uri>
agent-do manna relations [<local-id>] [--resolve] [--check] [--json]
```

Behavior:

- `federation init` is idempotent and creates the manifest only after its
  authenticated transaction is durable.
- `federation fork` is explicit and destructive. It binds exact before and after
  bytes in the existing HMAC journal and retains the prior manifest in a tracked
  federation archive.
- `relate` and `unrelate` take the board-wide lock, re-read both the issue board
  and manifest, validate active local ownership, journal exact before and after
  bytes, then atomically replace the manifest.
- If `from` is actively `in_progress` or `blocked`, its exact owner proof is
  required. Open and done rows may receive lineage declarations from an
  authenticated session because the issue row and lifecycle are not mutated.
- `relations` without `--resolve` reads only local durable state.
- `--resolve` reads only the machine-local serve registry. It never searches the
  network or writes the board.
- `--check` exits nonzero for a present board with a missing target or for
  divergent replicas. An unavailable board remains a successful degraded read.

Resolution states are exact:

| State | Predicate |
| --- | --- |
| `resolved` | One logical registered board has the target issue, and every registered replica agrees on the target row bytes. |
| `unavailable` | No registered board has the target `board_id`. |
| `missing` | A registered, unambiguous board exists but has no target issue ID. |
| `ambiguous` | Registered replicas share the board ID but disagree on the target row or federation identity. |

For `counterpart`, output also carries one of `reciprocity: confirmed`,
`reciprocity: one_way`, `reciprocity: unavailable`, or
`reciprocity: ambiguous`. One-way never fails local lint.

### Registry contract addition

The follow-up implementation should extend the Manna registry entry as follows:

```yaml
commands:
  federation: Initialize, inspect, or explicitly fork a portable Manna federation identity
  relate: Add one typed outbound cross-board relation
  unrelate: Remove one typed outbound cross-board relation
  relations: List local relations and optionally resolve them through registered boards
contracts:
  connect:
    - federation
  snapshot:
    - federation
    - relations
  interact:
    - federation
    - relate
    - unrelate
  verify:
    - relations
  attributes:
    federation:
      - polymorphic
      - composite
      - destructive
    unrelate:
      - destructive
```

The `federation` destructive annotation is deliberately conservative because
the same top-level verb contains `fork`. If contract subverb precision is later
added, only `federation fork` should retain that attribute.

### Lint and reconcile

`manna lint` remains local and deterministic. Add rules for:

- `federation_tracking`: an existing manifest and archive are Git-tracked;
- `federation_shape`: version, board ID, URI, enum, and deterministic order;
- `relation_source`: every `from` ID exists locally;
- `relation_duplicate`: no exact duplicate or self-link;
- `relation_local_target`: a target using the same `board_id` is rejected because
  same-board edges belong in current local grammar.

Lint must not consult the registry and must not fail because a target board or
target issue is absent.

`manna reconcile` keeps its current local authority. Add only local findings:

- a relation source removed by an out-of-band board edit;
- federation durable files missing from the Git index;
- a local manifest/archive transaction that did not converge.

Do not add sibling status to `landed_open`, `dead_claim`, `blocker_desync`,
`prompt_pairing`, or `handoff_presentation`. Remote resolution belongs to
`manna relations --resolve`, `manna serve`, and consumers such as `agent-brief`.

`done` must neither resolve nor print remote state as a prerequisite. It closes
only the owned local row after the existing handoff and shadow-work-order gates.

### Serve and brief rendering

Extend `manna serve`'s private registry entries with each manifest `board_id`.
Keep path slugs for URLs, but resolve by board ID. Group identical replicas and
surface divergent ones as ambiguous.

Each issue drawer gets a `RELATIONS` section showing:

- relation kind;
- target hint and portable URI;
- resolution state;
- resolved title and status when safe;
- reciprocity for `counterpart`;
- a clear `counterpart board unavailable on this machine` degradation.

Relations do not change NOW, NEXT, WAITING, NEEDS DECISION, or DRIFT placement.
Those waves remain local board truth.

If `agent-brief` traverses relations, its internal thread key becomes the full
Manna URI. The current bare `mn-` display may remain for the focused board, but
cross-board receipts must be board-qualified so copied IDs cannot join
accidentally.

### Code and documentation surface

The follow-up item should own, at minimum:

- `tools/agent-manna/src/federation.rs` for schema, URI, canonical serializer,
  resolver result types, and mutation plans;
- `tools/agent-manna/src/main.rs` for CLI verbs and output envelopes;
- `tools/agent-manna/src/store.rs` and `workflow.rs` for locking, journal binding,
  scaffold, Git tracking, archive, and recovery;
- `tools/agent-manna/src/reconcile.rs` for local-only findings;
- `tools/agent-manna/serve/serve.py`, `board.py`, and static UI for registry
  identity, replica grouping, and rendering;
- `tools/agent-brief` for board-qualified remote joins, only if traversal ships
  in the same item;
- `registry.yaml`, `ARCHITECTURE.md`, `CLAUDE.md`, `SCHEMA.md`, `README.md`, and
  `docs/TOOLS.md`;
- Rust unit tests, Manna integration tests, serve tests, brief fixtures if
  touched, contracts drift, and the root gate.

### Tests required before admission

1. Manifest parse and exact canonical round-trip.
2. Board ID generation shape and deterministic rejection of malformed IDs.
3. URI parse and format round-trip.
4. Allowed-kind table, duplicate rejection, self-link refusal, and local source
   existence.
5. Active claimed source refuses a non-owner with zero file changes.
6. Open and done source rows can receive a relation without changing issue JSONL
   or handoff bytes.
7. Two independent repos resolve one relation when both are registered.
8. Clone only the source repo: lint and reconcile remain clean, relation output
   becomes `unavailable`.
9. Register the target board with the issue removed: output becomes `missing`,
   while local lint remains clean.
10. Register two replicas with the same board ID and differing target rows:
    output becomes `ambiguous`; no replica wins by mtime or registration order.
11. Complete the target: the resolver shows `done`, but source status,
    `blocked_by`, claim, and handoff digest remain byte-identical.
12. Local `Manna:` trailer tests prove a target repo commit cannot satisfy source
    `landed_open`.
13. Counterpart reciprocity reports all four states without mutating either repo.
14. Crash injection at every manifest transaction phase converges to exact before
    or exact after bytes.
15. `federation fork` archives inherited identity and relations, writes a new ID,
    and never resolves as the old board.
16. Existing boards with no federation manifest retain byte-identical list,
    show, context, lint, reconcile, sync, claim, and done behavior.
17. `agent-do harness contracts validate`, contracts drift, Rust tests, Manna
    integration, serve tests, and `./test.sh` pass with zero warnings.

## Migration and convention floor

Before any feature ships, use this explicit prose convention:

```text
Sibling: <repo>#<mn-id> (<counterpart|informed_by|depends_on|supersedes>)
```

Use `source:` only when the sibling actually is provenance. Otherwise put the
line in the description. This convention remains the readability floor after
federation ships.

Adoption must be opt-in:

1. `manna federation init` assigns an identity to each participating board.
2. A read-only candidate audit scans prose and emits proposed commands with
   receipts. It writes nothing.
3. An authenticated operator admits each edge with `manna relate`.
4. Existing prose stays. It is human context, not duplicate machine authority.
5. Done historical rows are not rewritten. The separate manifest can add
   lineage without changing their issue bytes or handoff seals.
6. No counterpart repo is changed automatically and no reciprocal edge is
   assumed.

For the motivating case, the candidate audit should propose, not apply, the
exact DPT and design-round links after Erik approves their semantics. No
follow-up item or mutation is authorized by this recommendation alone.

## Falsifiable acceptance test

The recommendation passes only if one hermetic fixture proves all of the
following at once:

1. Board A declares an `informed_by` edge to Board B and commits only its own
   manifest.
2. Board A cloned alone passes lint and reconcile and prints `unavailable`.
3. Registering Board B changes only the derived read to `resolved`.
4. Completing the target changes the rendered sibling status but changes zero
   bytes in Board A.
5. Removing the target produces `missing` without invalidating Board A.
6. A divergent second Board B replica produces `ambiguous`, independent of
   registration order.
7. A foreign session cannot alter a relation whose local source is actively
   claimed.
8. No remote commit, status, proof, or handoff can satisfy Board A's claim,
   block, done, pairing, landed, lint, or reconcile gates.

Any failure rejects this architecture. In particular, if correct product
behavior requires cross-board status mutation, stop. That is a larger authority
protocol, not federation version 1.

## Ruling packet

Recommended ruling: authorize one follow-up implementation item for the full
federation shape above. Do not authorize an issue-row link field, a registry-only
graph, or cross-board lifecycle automation.

Kill the follow-up if any implementation requires:

- the target board to exist for local lint or reconcile to pass;
- a path or serve slug as durable identity;
- automatic remote writes or reciprocal transactions;
- remote status to derive local `blocked` or `done`;
- rewriting handoff content or issue JSONL merely to add a relation;
- picking one divergent replica by freshness;
- parsing prose directly into admitted relations.

One ruling remains for Erik: approve or reject this bounded federation layer.
The recommendation includes `depends_on` as displayable intent with zero
lifecycle effect. If that phrase still overstates authority, remove the kind
from version 1 rather than weakening the local blocker invariant.

Research deliverable status: submitted for ruling. No implementation was
performed, no follow-up Manna item was filed, and this item should remain open
until Erik accepts, rejects, or revises the recommendation.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-e40d9a`.
4. Commit with `Manna: mn-e40d9a` and run `agent-do manna done mn-e40d9a` only after the work is verified.
