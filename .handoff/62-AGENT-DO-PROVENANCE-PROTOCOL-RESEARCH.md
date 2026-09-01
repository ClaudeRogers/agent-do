# Agent-Do Load-Bearing Provenance Protocol

## Research And Architecture Mandate

You are the principal systems architect and adversarial protocol reviewer for
`agent-do`.

Your task is to determine whether, where, and how `agent-do` should codify a
reusable project protocol for load-bearing authority, provenance, work
admission, and state transitions.

This is a read-only research and design task. Do not implement anything.

## Objective

Design the smallest coherent protocol that can prevent silent changes to:

1. who may authorize, launch, admit, ratify, or update state;
2. which exact inputs, bytes, source versions, and receipts support an action;
3. which population or denominator supports a quantitative claim;
4. which dependencies are satisfied, by what admitted evidence;
5. which attempt and artifact are current, superseded, rejected, or admitted;
6. which human judgments remain unresolved; and
7. what the next admissible action actually is.

The protocol must be reusable beyond Moon Two, especially in `theta-indi` and
`the-orient`, without imposing campaign-grade ceremony on low-risk work.

Do not promise zero risk. The protocol should make unauthorized, stale,
ambiguous, or unsupported transitions detectable and fail closed where the
declared risk warrants it. It must also surface semantic uncertainty that no
hash or deterministic replay can resolve.

## Repository Scope

Read only these repositories:

- `/Users/erik/Custom-Coding/agent-do`
- `/Users/erik/Custom-Coding/aldebaran-group`
- `/Users/erik/Custom-Coding/theta-indi`
- `/Users/erik/Custom-Coding/the-orient`

Do not inspect `/Users/erik/.factory` or any content under `~/.factory`. It is
old and non-authoritative for this task.

Do not use external web research. Repository truth is sufficient for this
design pass.

## Source-Of-Truth Rules

Within each repository, follow its nearest `AGENTS.md` and its declared source
priority. In `agent-do`, running checked-in code and tests outrank prose.

In the required `Repository Snapshot`, record for each repository:

- absolute root;
- current `HEAD` commit;
- branch;
- clean or dirty status;
- files materially relevant to this research that are modified or untracked.

Do not alter or normalize dirty state. Do not assume uncommitted state is
canonical. Label every finding as one of:

- `VERIFIED FACT`
- `INFERENCE`
- `DESIGN PROPOSAL`
- `OPEN HUMAN DECISION`

Every verified fact must cite an exact repository-relative `path:line` range.
If code and prose disagree, show both and follow the repository's authority
order.

## Non-Mutation Covenant

You may read files and run commands that are demonstrably read-only.

You must not:

- edit, create, delete, format, or regenerate repository files;
- modify `.manna`, Coord state, session state, telemetry, caches, hooks, refs,
  branches, indexes, databases, or installed configuration;
- create or claim issues;
- change issue status or blockers;
- run `agent-do` or a child tool merely to discover behavior if invocation can
  write telemetry or local state;
- install dependencies;
- commit, push, open a PR, or change production/external systems;
- write the proposed schema, templates, or code into any repository.

Static inspection is preferred. If a runtime check is essential, prove its
read-only boundary first and redirect all incidental state to an approved
temporary directory outside the repositories. Report the exact command and
side-effect analysis.

## Problem Context

Moon Two has built a strong but hand-assembled governance chain:

```text
constitution
-> explicit authorization
-> immutable attempt/work order
-> launch
-> durable return
-> independent review
-> canonical admission
-> reserved human ratification where required
-> explicit state update and dependency release
```

Its central law is not paperwork. It is that preparation, authorization,
launch, submission, admission, ratification, gate passage, and state update are
different events owned by different authorities.

The clearest failure case is the P1-I A3 O2-order defect. A wrong dependency
order was copied consistently into the work order, synthesis, and decision
card. Hashes matched. Replay was deterministic. Internal controls passed. A
separate semantic review still found the controlling sequence wrong. This
proves:

1. byte identity is not semantic truth;
2. deterministic agreement can preserve a shared error;
3. derived views must not become independent authorities;
4. independent semantic review remains load-bearing at selected risk tiers.

Study this example directly rather than relying on this summary.

## Required Evidence Map

### Agent-Do Core

Inspect at minimum:

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `agent-do`
- `registry.yaml`
- `lib/registry.py`
- `lib/contracts.py`
- `lib/contracts_drift.py`
- `lib/contracts_audit.py`
- `lib/telemetry.py`
- `bin/intent-router`
- `bin/pattern-matcher`
- `bin/gen-index`
- `bin/gen-tools-doc`
- `install.sh`
- `test.sh`
- `.github/workflows/`
- `docs/LANE-PROMPT-TEMPLATE.md`
- `docs/INTEGRATION.md`
- all directly relevant tests

Inspect the live implementations, registry entries, docs, and tests for:

- `manna`
- `coord`
- `prompt`
- `sessions`
- `brief`
- `spec`
- `harness`
- `git`
- `context`
- ZPC only to establish why advisory memory is or is not authority

### Moon Two Exemplar

Inspect at minimum:

- `MOON-TWO-PLAN.md`
- `moon-two/DECISIONS.md`
- `moon-two/STATE.md`
- `moon-two/CAMPAIGN.md`
- `moon-two/OPERATIONS.md`
- `moon-two/WORKER-LAW.md`
- `moon-two/ISSUE-GRAPH.md`
- `moon-two/templates/`
- the P1-I A1 through current attempt prompts, returns, reviews, synthesis,
  decision cards, and decision records

Pay special attention to:

- the difference between immutable bytes, admitted evidence, ratification
  authority, and current state;
- independently stored prompt digests;
- retries with new attempt identities rather than overwrite;
- accepted evidence whose derived decision surface was superseded;
- red-gate stickiness;
- denominator provenance classes;
- negative controls;
- the A3 O2-order defect and its correction path;
- any place one overloaded status obscures several independent states.

### Portability Targets

For `theta-indi`, inspect its constitutional source, lock generation/checking,
human ratification model, Manna state, publication mirror, consent/data lineage,
and local-versus-tracked boundaries.

For `the-orient`, inspect its charter, method, launcher, tracked handoff prompts,
Manna state, claim/citation registers, blind-lane and reviewer isolation,
phase gates, and local-versus-tracked boundaries.

Do not broaden into general product or code review. Extract only constraints
that affect protocol portability.

## Working Hypotheses To Falsify

Treat all of the following as hypotheses, not instructions:

1. The best initial fit is composition around existing tools, anchored by one
   checked-in, versioned canonical protocol specification.
2. `manna` should represent authorization and work lineage, `spec` normative
   change packages, `coord` ownership and publication pointers, `harness`
   executable evidence, `git` content identity, and `context` external-source
   provenance.
3. Templates and human-readable views should be generated or validated from
   one canonical record rather than separately maintained.
4. A new top-level tool is justified only if it owns genuinely new executable
   territory and state that existing families cannot coherently own.
5. Current dispatcher telemetry is correlation evidence, not an authoritative
   receipt.
6. Current contract declarations classify intent but do not prove read-only
   behavior, full command coverage, semantic correctness, or absence of side
   effects.
7. Current Manna issue state alone is insufficient to represent work attempt,
   submission, review, artifact admission, ratification, and gate state.
8. There is no current universal dispatch interception point because
   structured, natural-language, offline, and root-special paths differ.
9. A protocol that depends only on documentation or routing advice is bypassable
   and therefore cannot be load-bearing.
10. A universal heavyweight workflow would fail adoption; control intensity
    must scale with declared risk while a small invariant core remains
    mandatory.

For each hypothesis, return `CONFIRMED`, `PARTIALLY CONFIRMED`, or `REJECTED`,
with evidence and consequences.

## Required Analysis

### 1. Define The Territory

Give this protocol a precise domain boundary. Distinguish it from:

- task tracking;
- source citation;
- agent memory;
- software supply-chain attestation;
- ordinary Git history;
- orchestration/coordination;
- quality assurance;
- constitutional or policy content itself.

State what the protocol owns, what it references, and what remains owned by
existing tools. Apply agent-do's taxonomy gate before recommending a new tool.

### 2. Threat And Failure Model

Model at least:

- stale prompts and stale base commits;
- copied-but-wrong controlling requirements;
- duplicated prose drifting from canonical state;
- a worker marking its own work complete;
- non-atomic or unauthorized state transitions;
- blocker removal before evidence admission;
- a runtime-observed population relabelled as external authority;
- denominator or membership changes hidden behind unchanged rates;
- hashes used as proof of truth rather than byte identity;
- mutable refs or records presented as immutable receipts;
- natural or direct invocation bypassing enforcement;
- partial writes, crashes, retries, and concurrent claim races;
- current state inferred from old immutable prompts;
- accepted artifacts confused with passing subject verdicts;
- human ratification treated as source provenance;
- sensitive or blind inputs leaking into derived records;
- an honest semantic disagreement no mechanical validator can settle.

Separate accidental error, negligent shortcut, compromised local process, and
malicious actor. State the trust boundary explicitly. Do not add cryptography
as a talisman; recommend signing or attestations only if the threat model and
key custody make them meaningful.

### 3. Canonical State Model

Design or select a state model that does not overload one `status` field.
Evaluate at minimum these orthogonal dimensions:

- authorization state;
- work/issue lifecycle;
- attempt lifecycle;
- artifact admission state;
- subject or candidate verdict;
- ratification readiness and ratification state;
- gate state;
- dependency/blocker state;
- supersession state.

Specify legal transitions, transition owners, required preconditions,
receipts, failure behavior, idempotency, concurrency expectations, and recovery
after interruption.

The model must distinguish at least:

```text
prepared != authorized != launched
submitted != admitted
artifact accepted != subject passed
ratification-ready != ratified
ratified != gate passed
old immutable attempt != current state
```

### 4. Minimum Portable Record

Propose the minimum versioned machine-readable record or record family. Include
only fields that carry an invariant. Evaluate fields for:

- protocol/schema version;
- stable work and attempt identities;
- correction/supersession links;
- authority class and actor/role;
- exact scope and explicit non-effects;
- immutable prompt/work-order path and independently held digest;
- pinned base and accepted input identities;
- writable, read-only, and forbidden territories;
- dependencies and admitted blocker receipts;
- deliverables and acceptance conditions;
- artifact paths, hashes, and as-of identities;
- facts, proposals, deviations, and unresolved human decisions;
- reviewer independence and review scope;
- admission receipt and exact admitted scope;
- quantitative claim/denominator identity and provenance class;
- negative-control evidence;
- current state and next admissible action.

Explain what is canonical, what is derived, and how generated views prove they
match canonical state. No record may authenticate its own final bytes without
an external binding.

### 5. Existing-Capability Matrix

For every required invariant, map:

| Invariant | Existing owner/tool | Proven capability | Gap | Can compose? | Requires change? |
|---|---|---|---|---|---|

Do not credit a capability merely because documentation names it. Verify the
implementation and tests. Distinguish:

- content-bound receipt;
- derived evidence;
- mutable testimony;
- advisory memory;
- human ruling.

### 6. Architecture Options

Evaluate at least:

1. documentation/templates only;
2. one canonical spec plus composition of existing tools;
3. extension of `spec`;
4. extension of `manna`;
5. cross-cutting contract/registry declarations plus validators;
6. dispatch middleware or a common receipt layer;
7. a new first-class tool;
8. an external plugin for incubation.

Score each option against:

- single-source authority;
- bypass resistance;
- semantic honesty;
- compatibility with structured and natural invocation;
- atomicity and concurrency;
- recovery and auditability;
- stack-neutral adoption;
- support without CI;
- migration cost;
- conceptual overlap with existing tools;
- testability;
- operational ceremony;
- security and sensitive-data boundaries.

Recommend one near-term architecture and, if different, one defensible end
state. Explain what evidence would falsify the recommendation.

### 7. Risk Tiers

Define a compact risk classifier from consequences, reversibility, authority
surface, data sensitivity, concurrency, external side effects, and proof burden.

Identify the invariant controls required at every tier. Then scale only the
intensity of:

- reasoning effort;
- isolation/worktree use;
- review independence;
- number and strength of negative controls;
- deterministic reruns;
- evidence granularity;
- human ratification;
- clean-checkout or whole-system verification.

Show at least three worked examples:

1. a trivial reversible documentation correction;
2. a normal code change with tests;
3. a constitutional, denominator, production, or sensitive-data change.

The low tier must remain useful and honest, not ceremonial noise. The high tier
must fail closed.

### 8. Adversarial Validation Strategy

Specify tests that could prove the protocol implementation wrong. Include:

- schema and transition property tests;
- illegal transition and wrong-owner tests;
- same-record concurrency races;
- stale base and input-hash mismatch;
- blocker release without admitted evidence;
- derived-view drift;
- record self-authentication attempts;
- denominator identity and provenance mutation;
- one-field negative controls with exact diagnostics;
- read-only command side-effect detection;
- direct/natural/offline dispatch bypass tests;
- interrupted write and idempotent retry;
- accepted-artifact/failed-subject separation;
- a fixture modeled on A3 where all bytes agree on the same wrong semantic
  ordering and only independent semantic review can reject it;
- adoption checks that run locally when no CI exists.

State what cannot be mechanically proven.

### 9. Adoption And Migration

Show how the recommended protocol would fit:

- agent-do itself;
- Moon Two without rewriting its immutable history;
- theta-indi's file-level constitution and human ratification;
- the-orient's claim-level provenance, blind lanes, and review isolation;
- an ordinary small software repository.

Preserve each repository's existing canonical records. Prefer adapters,
validation, and generated views over wholesale migration. Distinguish tracked
governance state from clone-local memory and sensitive evidence.

### 10. Staged Plan, Not Implementation

Provide a staged implementation proposal, but do not execute it.

Each stage must include:

- objective;
- exact likely files or tool families affected;
- compatibility boundary;
- acceptance tests;
- negative controls;
- migration behavior;
- rollback or abandonment condition;
- human decisions required before authorization.

The first stage should be the smallest change capable of testing the core
architecture. Do not introduce a new framework, dependency, database, or tool
family without demonstrating why composition cannot satisfy the requirement.

## Universal Candidate Invariants

Assess, refine, and either adopt or reject each candidate:

1. One canonical machine-readable authority record; repeated prose is derived
   or mechanically reconciled.
2. Every action traces to explicit authorization and a reserved owner.
3. Preparation and launch are separate.
4. Every attempt has a unique immutable identity, path, and independently held
   digest; correction never overwrites history.
5. Input mismatch, stale base, ownership collision, or authority ambiguity
   stops execution.
6. Workers submit durable returns and never admit their own work.
7. Artifact admission, subject verdict, ratification, gate state, and issue
   lifecycle are independent fields.
8. Dependencies clear only from admitted evidence and an authorized transition.
9. Every quantitative claim binds numerator, denominator, denominator identity,
   provenance class, and source receipt.
10. A gate denominator is fixed outside the behavior it judges.
11. Human ratification can author scope but cannot manufacture external
    provenance.
12. Every executable gate demonstrates an intended failure path with the
    expected diagnostic.
13. Hashes prove byte identity, not truth or authority.
14. High-risk semantic decisions receive independent review not generated from
    the same controlling text.
15. Red remains red until all exact predicates and the reserved authority clear
    it.
16. Current state and next admissible action are explicit; neither is inferred
    from chat, old prompts, or mutable testimony alone.
17. Sensitive inputs may be referenced without being copied into public or
    derived records.
18. Control intensity scales by risk; truth and authority invariants do not.

## Required Deliverable

Return one self-contained architecture report with this exact top-level order:

1. `Decision In One Page`
2. `Repository Snapshot`
3. `Verified Current Architecture`
4. `Moon Two Lessons`
5. `Threat And Failure Model`
6. `Canonical State Machine`
7. `Minimum Portable Record`
8. `Existing-Capability Matrix`
9. `Architecture Options And Scores`
10. `Recommended Near-Term Architecture`
11. `Defensible End State`
12. `Risk Tiers And Examples`
13. `Adversarial Validation Plan`
14. `Adoption And Migration`
15. `Staged Implementation Proposal`
16. `Open Human Decisions`
17. `Falsifiers And Residual Risk`
18. `Evidence Ledger`

Use tables where they make comparison precise. Include a state diagram and at
least one concrete example record, but keep the record minimal. Every proposal
must link back to a verified gap or invariant.

Limit `Open Human Decisions` to questions that genuinely cannot be resolved
from repository truth. For each question, state the default recommendation and
the consequence of each plausible answer.

Do not hide contradictions. If a safe, coherent protocol cannot be composed
from the current tools, say so plainly and identify the minimum prerequisite.

## Stop Conditions

Stop and report rather than infer if:

- the authority of a source cannot be established;
- a required file changed during inspection;
- a read-only check would mutate state;
- dirty state makes current versus canonical meaning ambiguous;
- the proposed architecture would create a second mutable source of truth;
- a transition cannot be made atomic under the stated storage model;
- a claimed receipt does not bind the content or event it purports to prove;
- a recommendation depends on undocumented human intent.

## Definition Of Done

The task is complete only when the report:

- makes a bounded, evidence-backed territory decision;
- identifies one canonical source and all derived views;
- defines orthogonal states, legal transitions, owners, and receipts;
- maps every invariant to existing capability or a verified gap;
- gives a ranked architecture recommendation with falsifiers;
- scales operational ceremony without weakening core truth constraints;
- addresses agent-do, Moon Two, theta-indi, the-orient, and a small repository;
- includes mechanical negative controls and admits semantic limits;
- leaves all repositories and external state unchanged.
