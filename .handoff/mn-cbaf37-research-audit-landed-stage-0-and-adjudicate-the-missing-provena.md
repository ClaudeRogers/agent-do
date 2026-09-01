---
workflow: 2
manna: mn-cbaf37
track: mn-b7a0cc
source: Erik conversation 2026-08-22; supersedes the unexecuted pre-Stage-0 research prompt
base_commit: 7e43f285241ee687a4c42e0f62638e3748c3fc3a
scope: 'Research: audit landed Stage 0 and adjudicate the missing provenance protocol'
inputs:
- Erik conversation 2026-08-22; supersedes the unexecuted pre-Stage-0 research prompt
binding: sha256:e23eb44d8a55f8aac696af284045a2bce660086857cc52165e801975b295b9d0
---

# Handoff: Stage 0 Provenance Audit And Stage 1 Architecture Adjudication

Board state is canonical in `.manna/`. This file is the only current work order
for `mn-cbaf37`.

This handoff supersedes the unexecuted pre-Stage-0 prompt at
`.handoff/62-AGENT-DO-PROVENANCE-PROTOCOL-RESEARCH.md` as execution authority.
The older prompt remains a historical question inventory. It is not the current
baseline, architecture, or stage plan.

## Claim

```bash
agent-do manna claim mn-cbaf37
```

## Scope

Audit landed Manna Stage 0 as the incumbent workflow substrate, adjudicate only
the missing load-bearing provenance responsibilities, and return a ratifiable
Stage 1 authorization packet. Do not implement the recommendation.

## Inputs

- Erik conversation, 2026-08-22
- Current checked-in truth in the four repositories named below
- Landed Manna Stage 0 implementation, history, and tests
- Moon Two's hand-assembled provenance chain and A3 O2-order failure case
- Historical question inventory at
  `.handoff/62-AGENT-DO-PROVENANCE-PROTOCOL-RESEARCH.md`

## Work order

Execute the complete research and architecture mandate below. Treat Stage 0 as
the verified incumbent unless current code supplies a concrete falsifier. Design
only the smallest missing authority, evidence, attempt, admission, verdict,
ratification, gate, denominator, semantic-review, and risk-tier layer.

Claim the item before taking the repository snapshots. The claim is the only
authorized pre-research workflow mutation. After the claim, the research pass is
read-only across every repository in scope.

## Mandate

Act as the principal systems architect and adversarial protocol reviewer for
`agent-do`.

Determine what, if anything, must be built above the completed Manna Stage 0
substrate to provide a reusable protocol for load-bearing authority,
provenance, evidence admission, semantic review, ratification, and state
transitions.

This is not a greenfield design exercise. Stage 0 is the incumbent. Do not
redesign or rebuild its board, handoff, ownership, transaction, migration, or
presentation machinery unless current repository evidence demonstrates a
specific falsifier that cannot be repaired locally.

This is a read-only research and architecture task. Do not implement anything.

## The Current Question

Stage 0 built a secure workflow docket:

1. authoritative board state in `.manna/`;
2. one sealed `.handoff/` work order paired to each actionable item;
3. authenticated, restart-durable claim ownership;
4. fail-closed pairing, path, Git-visibility, and workflow-sprawl checks;
5. journaled, crash-recoverable lifecycle, initialization, migration, and
   presentation writes;
6. convergent legacy and mixed-board migration;
7. first-class blocker edges and ordered generated handoff views; and
8. discovery that directs identityless legacy boards toward migration.

Those statements are accepted program history, not permission to skip
verification. Verify the live implementation and tests before crediting any
capability.

The unresolved question is whether agent-do needs a semantic and evidentiary
layer above that docket, and what the smallest coherent version of that layer
is.

In plain terms:

```text
Stage 0 secures the case file and its owner.
This research decides the law of evidence and separation of powers.
```

## Objective

Design the smallest coherent protocol that closes only the verified gaps in:

1. who may prepare, authorize, launch, submit, admit, review, ratify, pass a
   gate, or update canonical state;
2. which exact inputs, bytes, source versions, artifacts, and receipts support
   an action;
3. which population, membership rule, numerator, and denominator support a
   quantitative claim;
4. which dependencies are satisfied, by what admitted evidence and authorized
   transition;
5. which attempt and artifact are current, superseded, rejected, admitted, or
   accepted for a precisely bounded purpose;
6. which semantic disagreements and human judgments remain unresolved; and
7. what the next admissible action is.

The protocol must remain portable beyond Moon Two, especially to `theta-indi`,
`the-orient`, and an ordinary small software repository. It must not impose
campaign-grade ceremony on low-risk work.

Do not promise zero risk. Make unauthorized, stale, ambiguous, or unsupported
transitions detectable and fail closed where the declared risk warrants it.
State plainly what no hash, replay, schema, or model can prove.

## Non-Goals

Do not:

1. create another task board or work-order root;
2. replace `.manna/` or `.handoff/` merely for conceptual cleanliness;
3. turn generated filenames or indexes into authority;
4. collapse authorization, submission, admission, verdict, ratification, gate,
   and issue completion into one status;
5. treat a digest as proof of truth, meaning, or authority;
6. treat agent memory, chat history, telemetry, or model self-report as a
   canonical receipt;
7. prescribe a universal heavyweight ceremony;
8. introduce a framework, dependency, database, service, or tool family without
   proving existing composition cannot own the required invariant; or
9. implement, file follow-on work, claim other items, or change project state.

## Repository Scope

Read only these repositories:

- `/Users/erik/Custom-Coding/agent-do`
- `/Users/erik/Custom-Coding/aldebaran-group`
- `/Users/erik/Custom-Coding/theta-indi`
- `/Users/erik/Custom-Coding/the-orient`

Do not inspect `/Users/erik/.factory` or anything under `~/.factory`. It is old
and non-authoritative for this task.

Do not use external web research. Repository truth is sufficient for this
architecture pass.

## Source And Authority Rules

Within each repository, follow the nearest `AGENTS.md` and declared source
priority. Running checked-in code and tests outrank summaries and roadmap prose.

Record a repository snapshot for each root:

- absolute root;
- `HEAD` commit;
- branch;
- clean or dirty status;
- materially relevant modified or untracked files; and
- whether any relevant file changes during inspection.

Do not normalize dirty state. Do not assume uncommitted state is canonical. If
dirty state makes current versus canonical meaning ambiguous, stop and report
the ambiguity.

Use these epistemic registers for every substantive conclusion:

- `VERIFIED FACT`
- `INFERENCE`
- `DESIGN PROPOSAL`
- `OPEN HUMAN DECISION`

Every `VERIFIED FACT` must cite an exact repository-relative `path:line` range.
If implementation and prose disagree, show both and follow the repository's
authority order.

## Non-Mutation Covenant

After claiming `mn-cbaf37`, only demonstrably read-only inspection is allowed.

Do not:

- edit, create, delete, format, regenerate, stage, or commit repository files;
- mutate `.manna`, `.handoff`, Coord, session state, telemetry, caches, hooks,
  refs, branches, indexes, databases, or installed configuration;
- run `manna sync`, `manna reconcile --fix`, bootstrap, installers, formatters,
  generators, or tests that write inside a scoped repository;
- invoke `agent-do` or a child tool merely to discover behavior when invocation
  may write telemetry or local state;
- install dependencies;
- push, open a pull request, or change any production or external system; or
- write the proposed schema, templates, report, or code into a repository.

Prefer static inspection. If a runtime check is essential, first prove its
read-only boundary and redirect every incidental write to an approved scratch
location outside the scoped repositories. Report the exact command and its
side-effect analysis.

Return the architecture report in the session. Persistence and implementation
are separate, later-authorized actions.

## Historical Input And Supersession

The earlier prompt is:

```text
.handoff/62-AGENT-DO-PROVENANCE-PROTOCOL-RESEARCH.md
sha256:a4ec4df9a4a2b3fd081337b67534cededb96ea06db5e208e48828660beb20b3f
```

Use it only to ensure no important question was lost. Its greenfield framing
is superseded. Any conflict is resolved in favor of this handoff and current
repository truth.

The landed Stage 0 history includes, at minimum, the original Stage 0 merge and
later integrity closures identified in local history around `bb73706`,
`745efa8`, `c905586`, `ad30b65`, and `eb98eef`. Verify exact ancestry, trailers,
and current code rather than relying on those short names as proof.

## Stage 0 Incumbent Audit

Before proposing architecture, build a predicate matrix for the incumbent.

For every claimed Stage 0 capability, return exactly one verdict:

- `CLOSED`
- `PARTIAL`
- `OPEN`
- `OUTSIDE SCOPE`
- `REGRESSED`

At minimum, audit:

1. board identity and strict-mode durability;
2. canonical item-handoff pairing and reverse pointers;
3. content binding and explicit resealing;
4. authenticated ownership and restart durability;
5. atomic claim and lifecycle transitions;
6. journal authentication, crash recovery, and idempotency;
7. legacy, mixed, malformed, and cross-project migration convergence;
8. symlink, path escape, Git visibility, and workflow-sprawl defenses;
9. ordered handoff presentation, blocker markers, and generated index;
10. initialization atomicity;
11. migration and identity discoverability; and
12. lint and reconcile coverage.

For every `PARTIAL`, `OPEN`, or `REGRESSED` result, distinguish:

- a Stage 0 defect that should be repaired in the incumbent;
- a genuinely new provenance-layer responsibility; or
- a policy question no mechanism can resolve alone.

Do not relabel an ordinary Stage 0 bug as a reason to build a new protocol
layer.

## Objective Gap Matrix

Test the following current assessment rather than accepting it:

| Objective | Current hypothesis |
| --- | --- |
| Authenticated claim ownership and ordinary lifecycle writes | Largely closed by Stage 0 |
| Separate authorization, launch, admission, review, ratification, and gate authorities | Partial or open |
| Work-order content identity and base commit | Partial |
| Immutable attempts, returns, artifact identities, and admission receipts | Open |
| Blocker edges | Closed mechanically |
| Evidence-bound blocker release | Open |
| Artifact accepted versus subject passed | Open |
| Current, superseded, rejected, and admitted attempt state | Open |
| Numerator, denominator, membership, and provenance identity | Open or tool-specific only |
| Unresolved human judgment as first-class state | Open |
| Next admissible action across orthogonal states | Partial |

If current code falsifies any row, replace the hypothesis with evidence.

## Central Semantic Failure Case

Study Moon Two's P1-I A3 O2-order defect directly.

A wrong controlling dependency order was copied consistently into a work
order, synthesis, and decision card. Digests matched. Replay was deterministic.
Internal controls passed. Independent semantic review found the sequence was
still wrong.

Use the case to test these propositions:

1. byte identity is not semantic truth;
2. deterministic agreement can preserve a shared error;
3. a generated view must not become an independent authority;
4. a worker must not admit its own work at high risk; and
5. independent semantic review remains load-bearing where consequence warrants
   it.

## Required Evidence Map

### Agent-Do Stage 0

Inspect at minimum:

- `AGENTS.md`
- `CLAUDE.md`
- `README.md`
- `ARCHITECTURE.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `CHANGELOG.md`
- `agent-do`
- `bin/bootstrap`
- `hooks/claude/agent-do-session-start.sh`
- `hooks/cursor/` and relevant Cursor integration
- `tests/test_bootstrap.sh`
- `tests/test_session_start_reads.py`
- `tools/agent-manna/src/main.rs`
- `tools/agent-manna/src/store.rs`
- `tools/agent-manna/src/workflow.rs`
- `tools/agent-manna/src/reconcile.rs`
- `tools/agent-manna/test/integration.sh`
- all directly relevant Rust tests
- `.manna/board.yaml`
- `.manna/workflow.yaml`
- `.manna/handoff-order.yaml`
- representative current `.manna/issues.jsonl` rows and sealed handoffs

Also inspect the live ownership boundaries of:

- `manna`
- `spec`
- `coord`
- `harness`
- `git`
- `context`
- `sessions`
- `brief`
- `prompt`
- ZPC only to establish why advisory memory is or is not authority

### Moon Two Exemplar

Inspect the constitutional, decision, state, campaign, operations, worker-law,
issue-graph, template, attempt, return, review, synthesis, and ratification
surfaces that actually govern Moon Two.

Pay special attention to:

- immutable bytes versus admitted evidence;
- attempt correction by supersession rather than overwrite;
- accepted evidence with a superseded decision surface;
- red-gate stickiness;
- denominator provenance;
- negative controls;
- reviewer independence; and
- the A3 O2-order defect and correction path.

### Portability Targets

For `theta-indi`, inspect only the constitutional source, locks, human
ratification, Manna state, publication mirror, consent and data lineage, and
tracked versus local boundaries needed for protocol portability.

For `the-orient`, inspect only the charter, method, launcher, tracked handoffs,
Manna state, claim and citation registers, blind-lane isolation, review
isolation, phase gates, and tracked versus local boundaries needed for
protocol portability.

Do not broaden this task into a general product or code review.

## Working Hypotheses To Falsify

Return `CONFIRMED`, `PARTIALLY CONFIRMED`, or `REJECTED` for each hypothesis,
with exact evidence and architectural consequence.

1. Stage 0 is a sound incumbent substrate and should be extended or composed,
   not replaced.
2. The smallest near-term fit is composition around existing tools, anchored
   by one versioned canonical provenance record or record family.
3. Manna should continue to own actionable work identity, ownership, lifecycle,
   and dependency edges, but should not overload its single issue status with
   attempt, artifact, verdict, ratification, and gate state.
4. Templates, indexes, decision cards, and other human-readable views should be
   generated or mechanically reconciled from canonical records.
5. A new top-level tool is justified only if it owns new executable territory
   and state that no existing family can coherently own.
6. Git and handoff digests can establish byte identity but not truth,
   authorization, semantic correctness, or admission.
7. Current dispatcher telemetry is correlation evidence, not an authoritative
   receipt.
8. Contract declarations classify promised behavior but do not prove semantic
   correctness, complete side-effect freedom, or external authority.
9. No universal dispatch interception point currently covers structured,
   natural-language, offline, and root-special paths.
10. Documentation-only enforcement is bypassable and cannot be load-bearing.
11. A universal heavyweight workflow would fail adoption; truth and authority
    invariants stay fixed while control intensity scales with risk.
12. Cross-family independent review reduces shared semantic failure better than
    self-review from the same controlling context.

## Required Analysis

### 1. Define The Remaining Territory

Define what the post-Stage-0 protocol owns. Distinguish it from:

- task tracking and claim ownership already owned by Manna;
- source citation;
- agent memory;
- ordinary Git history;
- software supply-chain attestation;
- orchestration and coordination;
- quality assurance;
- constitutional or policy content; and
- human judgment itself.

State what it owns, what it references, and what remains with existing tools.
Apply agent-do's taxonomy gate before recommending a new tool.

### 2. Threat And Failure Model

Model at least:

- stale prompts, bases, inputs, and mutable references;
- copied-but-wrong controlling requirements;
- duplicated prose drifting from canonical state;
- a worker admitting or ratifying its own work;
- unauthorized or non-atomic state transitions;
- blocker removal before evidence admission;
- runtime populations relabeled as external authority;
- hidden denominator or membership changes;
- hashes presented as truth rather than identity;
- mutable testimony presented as an immutable receipt;
- direct, natural, or offline invocation bypassing enforcement;
- partial writes, retries, concurrent races, and stale repair;
- old immutable attempts mistaken for current state;
- accepted artifacts confused with passing subjects;
- human ratification treated as source provenance;
- sensitive or blind inputs leaking into derived records; and
- honest semantic disagreement no validator can settle.

Separate accidental error, negligent shortcut, compromised local process, and
malicious actor. State the trust boundary. Do not add cryptography as a talisman.
Recommend signing only when the threat model and key custody make it meaningful.

### 3. Canonical State Model

Design or select a model with orthogonal dimensions for:

- authorization;
- work lifecycle;
- attempt lifecycle;
- artifact admission;
- subject or candidate verdict;
- ratification readiness and ratification;
- gate state;
- dependency state; and
- supersession.

It must preserve:

```text
prepared != authorized != launched
submitted != admitted
artifact accepted != subject passed
ratification-ready != ratified
ratified != gate passed
old immutable attempt != current state
```

For every legal transition, specify owner, preconditions, receipts, failure
behavior, idempotency, concurrency behavior, and interruption recovery.

### 4. Minimum Portable Record

Propose the smallest versioned machine-readable record or record family. Every
field must carry an invariant.

Evaluate fields for:

- protocol and schema version;
- stable work and immutable attempt identities;
- correction and supersession links;
- authority class and actor role;
- exact scope and explicit non-effects;
- independently held work-order digest;
- pinned base and accepted input identities;
- writable, read-only, and forbidden territories;
- dependencies and admitted blocker receipts;
- deliverables and acceptance conditions;
- artifact paths, hashes, and as-of identities;
- facts, proposals, deviations, and unresolved decisions;
- reviewer independence and review scope;
- admission receipt and exact admitted scope;
- quantitative claim and denominator identity;
- negative-control evidence;
- current state; and
- next admissible action.

Explain what is canonical, what is derived, and how a derived view proves it
matches canonical state. No record may authenticate its own final bytes without
an external binding.

### 5. Existing-Capability Matrix

For every required invariant, provide:

| Invariant | Existing owner | Proven capability | Gap | Can compose | Required change |
| --- | --- | --- | --- | --- | --- |

Do not credit capabilities merely because documentation names them. Distinguish
content-bound receipt, derived evidence, mutable testimony, advisory memory,
and human ruling.

### 6. Architecture Options

Evaluate at minimum:

1. no new protocol, only narrow Stage 0 extensions;
2. one canonical protocol record composed with existing tools;
3. extension of `manna`;
4. extension of `spec`;
5. cross-cutting registry or contract declarations plus validators;
6. a common receipt or transition layer;
7. a new first-class tool; and
8. an external plugin for incubation.

Score each against:

- single-source authority;
- overlap with Stage 0;
- bypass resistance;
- semantic honesty;
- atomicity and concurrency;
- recovery and auditability;
- compatibility across invocation paths;
- stack-neutral adoption;
- support without CI;
- migration cost;
- testability;
- ceremony; and
- sensitive-data boundaries.

Recommend one near-term architecture and, if different, one defensible end
state. State what evidence would falsify each recommendation.

### 7. Risk Tiers

Define a compact classifier using consequence, reversibility, authority
surface, data sensitivity, concurrency, external side effects, and proof
burden.

Keep a small invariant core at every tier. Scale only the intensity of:

- reasoning effort;
- isolation;
- independent review;
- negative controls;
- deterministic reruns;
- evidence granularity;
- human ratification; and
- whole-system verification.

Work examples for:

1. a trivial reversible documentation correction;
2. a normal code change with tests; and
3. a constitutional, denominator, production, or sensitive-data change.

Low risk must remain useful rather than ceremonial. High risk must fail closed.

### 8. Adversarial Validation

Specify tests capable of proving the proposed implementation wrong, including:

- schema and transition property tests;
- illegal-transition and wrong-owner tests;
- same-record concurrency races;
- stale base and input mismatches;
- blocker release without admitted evidence;
- derived-view drift;
- self-authenticating record attempts;
- denominator identity or provenance mutation;
- exact one-field negative controls and diagnostics;
- read-only command side-effect detection;
- structured, natural, direct, and offline bypass tests;
- interrupted write and idempotent retry;
- accepted-artifact versus failed-subject separation;
- cross-project migration and downgrade resistance; and
- an A3-shaped fixture where every byte agrees on one wrong semantic order and
  only independent review rejects it.

State what cannot be mechanically proven.

### 9. Adoption And Migration

Show how the recommendation fits:

- agent-do itself;
- Moon Two without rewriting immutable history;
- theta-indi's constitution and human ratification;
- the-orient's claim-level provenance and blind lanes; and
- an ordinary small software repository.

Preserve existing canonical records. Prefer adapters, validation, and generated
views over wholesale migration. Separate tracked governance state from local
memory and sensitive evidence.

### 10. Stage 1 Authorization Packet

Propose Stage 1 as the smallest implementation that can falsify the core
architecture. Do not assume Stage 1 must implement the entire protocol.

Stage 1 must state:

- exact objective and invariant closed;
- explicit non-goals;
- likely files and tool owners;
- canonical source and derived views;
- legal transitions and authorities introduced;
- compatibility boundary with Stage 0;
- acceptance tests and negative controls;
- migration behavior;
- rollback or abandonment condition;
- evidence that would falsify the architecture; and
- human decisions required before authorization.

Do not name later numbered stages merely to make the roadmap look complete.
Describe later capability bands only where dependency evidence determines their
order. The report, not this handoff, determines how many later stages exist.

### 11. Residual Risk And Semantic Limits

Identify exactly which failures remain possible after the recommended design.
Separate detectable misconduct, mechanically preventable transitions, semantic
uncertainty, and authority that must remain human.

## Universal Candidate Invariants

Assess, refine, and adopt or reject each candidate. Credit Stage 0 where earned.

1. One canonical machine-readable authority record; repeated prose is derived
   or mechanically reconciled.
2. Every action traces to explicit authorization and a reserved owner.
3. Preparation and launch are separate.
4. Every attempt has a unique immutable identity, path, and independently held
   digest; correction never overwrites history.
5. Input mismatch, stale base, ownership collision, or authority ambiguity
   stops execution.
6. Workers submit durable returns and never admit their own work at tiers where
   independence is required.
7. Artifact admission, subject verdict, ratification, gate state, and issue
   lifecycle are independent fields.
8. Dependencies clear only from admitted evidence and an authorized transition.
9. Every quantitative claim binds numerator, denominator, membership identity,
   provenance class, and source receipt.
10. A gate denominator is fixed outside the behavior it judges.
11. Human ratification may author scope but cannot manufacture external
    provenance.
12. Every executable gate demonstrates an intended failure path and expected
    diagnostic.
13. Digests prove byte identity, not truth or authority.
14. High-risk semantic decisions receive independent review not generated from
    the same controlling text.
15. Red remains red until all exact predicates and the reserved authority clear
    it.
16. Current state and next admissible action are explicit, not inferred from
    chat, old prompts, or mutable testimony.
17. Sensitive inputs may be referenced without being copied into public or
    derived records.
18. Control intensity scales by risk; truth and authority invariants do not.

For each invariant, return:

| Invariant | Stage 0 status | Evidence | Remaining gap | Adopt, refine, or reject |
| --- | --- | --- | --- | --- |

## Independent Review Boundary

The primary researcher produces one complete report from repository evidence.
It must not simulate a second independent reviewer inside the same context.

After the primary report is complete, a separately filed cross-family review
should receive:

- the same repository snapshot identities;
- this sealed handoff;
- the primary report; and
- an instruction to re-open evidence, not merely edit prose.

That reviewer should attack citations, state transitions, authority boundaries,
architecture scores, migration claims, and falsifiers. Disagreements become an
explicit adjudication ledger for Erik. Human ratification remains separate from
both model outputs.

The planned model assignment is Fable 5 for the primary long-horizon research
pass and GPT-5.6 Sol for the independent adversarial pass. Model assignment does
not grant authority and may be changed without changing protocol truth.

## Required Deliverable

Return one self-contained architecture report in this exact top-level order:

1. `Decision In One Page`
2. `Repository Snapshot`
3. `Stage 0 Incumbent Audit`
4. `Objective Gap Matrix`
5. `Verified Current Architecture`
6. `Moon Two Semantic Lessons`
7. `Threat And Failure Model`
8. `Canonical State Machine`
9. `Minimum Portable Record`
10. `Existing-Capability Matrix`
11. `Architecture Options And Scores`
12. `Recommended Near-Term Architecture`
13. `Defensible End State`
14. `Risk Tiers And Examples`
15. `Adversarial Validation Plan`
16. `Adoption And Migration`
17. `Stage 1 Authorization Packet`
18. `Later Capability Bands, If Evidence Requires Them`
19. `Open Human Decisions`
20. `Falsifiers And Residual Risk`
21. `Evidence Ledger`

Include:

- a state diagram;
- one minimal concrete example record;
- a Stage 0 closed/partial/open matrix;
- a scored architecture comparison;
- explicit legal transition ownership;
- exact path and line evidence;
- explicit non-effects; and
- a short plain-English explanation of what would actually be built and why.

Every proposal must trace to a verified gap. Every proposed new field must carry
an invariant. Every stage must have a kill condition.

Limit `Open Human Decisions` to questions repository truth cannot resolve. For
each, provide the default recommendation and consequence of each plausible
answer.

Do not hide contradictions. If no additional protocol is justified, say so. If
current tools cannot compose safely, identify the minimum prerequisite rather
than inventing a workaround.

## Stop Conditions

Stop and report rather than infer when:

- source authority cannot be established;
- a required or relevant file changes during inspection;
- a read-only check would mutate state;
- dirty state makes current versus canonical meaning ambiguous;
- a proposal creates a second mutable source of truth;
- a transition cannot be atomic under the storage model;
- a receipt does not bind the content or event it claims to prove;
- a recommendation depends on undocumented human intent;
- Stage 0 behavior regresses and the regression must be repaired before higher
  architecture can be assessed; or
- sensitive or blind material cannot be inspected within its authority and
  retention boundary.

## Definition Of Done

The research item is complete only when the report:

1. verifies the Stage 0 incumbent predicate by predicate;
2. distinguishes Stage 0 defects from genuinely new protocol territory;
3. makes a bounded territory decision;
4. identifies one canonical source and every derived view;
5. defines orthogonal states, legal transitions, owners, and receipts;
6. maps all 18 candidate invariants to existing capability or verified gap;
7. ranks architecture options with falsifiers;
8. scales ceremony without weakening truth and authority;
9. addresses agent-do, Moon Two, theta-indi, the-orient, and a small repository;
10. includes mechanical negative controls and admits semantic limits;
11. provides one ratifiable, falsifiable Stage 1 authorization packet;
12. does not invent later stages unsupported by dependency evidence; and
13. leaves all repositories and external systems unchanged after the claim.

## Completion

1. Return the primary report and verification receipts in the research session.
2. Do not implement or file the proposed Stage 1 work.
3. Do not mark `mn-cbaf37` done before Erik accepts the report or explicitly
   delegates acceptance.
4. If continuation context changes, update only this canonical handoff and reseal
   it with:

```bash
agent-do manna handoff seal mn-cbaf37
```

5. Commits that advance or close this item must carry:

```text
Manna: mn-cbaf37
```

6. Filing, staging, retracking, or mirroring commits must not carry the trailer.
