# mn-cbaf37: Stage 0 Provenance Audit and Stage 1 Architecture Adjudication

Date: 2026-08-24

Evidence snapshot:

    /Users/erik/.codex/scratch/mn-cbaf37/snapshot-7fa8029bc1c2cc98b2e6b525330ed28e3008ec36b6a3d955c27b2d91dcf8278e

Manifest SHA-256:

    7fa8029bc1c2cc98b2e6b525330ed28e3008ec36b6a3d955c27b2d91dcf8278e

Status: Primary research complete. Not independently reviewed, accepted, implemented, ratified, or closed.

## 1. Decision In One Page

**DESIGN PROPOSAL:** Keep Manna Stage 0 as the incumbent docket. Repair one localized Stage 0 defect first, then authorize a small opt-in provenance event layer inside the Manna storage and transaction boundary. Do not create a second board, database, service, plugin, or top-level tool.

What would actually be built:

1. An append-only, versioned provenance event family under ".manna/provenance/".
2. A policy record defining risk tier, authority roles, independence requirements, and sensitive-data boundaries.
3. An externally held event digest in the canonical Manna issue row. An event never authenticates itself.
4. One journaled Manna transition path that writes an immutable event and advances its canonical head with locking, expected-head comparison, idempotent retry, and crash recovery.
5. Derived review cards, indexes, and human views that declare the canonical head and fail reconciliation if they drift.

This closes the verified gap between "the case file has an authenticated owner" and "the submitted evidence was independently admitted for a bounded purpose." Stage 0 already owns work identity, claim ownership, lifecycle, handoff binding, migration, dependency edges, and crash-safe presentation. Its issue status must not be stretched to represent attempts, artifact admission, semantic verdicts, ratification, or gates. See E2 and E5.

**VERIFIED FACT:** Stage 0 has one serious incumbent defect: ordinary board mutation and some recovery paths use a permissive JSONL loader that skips malformed rows, then rewrite the complete board. A malformed row can therefore disappear during an otherwise valid claim, update, lifecycle transition, blocker change, or repair. Lint uses the same permissive loading path and can under-report the condition. Strict loading already exists and migration uses it. This is a Stage 0 repair, not justification for a new semantic layer. See E3 and E9.

**VERIFIED FACT:** Moon Two proves why the new layer is needed. Its A3 work order, synthesis, and decision card agreed byte-for-byte on one controlling sequence. Digests and replay were correct. Independent semantic review still rejected the sequence as wrong. The correction preserved A3 and created A4 rather than overwriting history. See M4 and M7.

**INFERENCE:** Hashes are identity instruments, not truth machines. The missing protocol is a law of admissible state change, not a stronger hashing scheme.

**Authorization recommendation:** Ratify the Stage 1 packet in Section 17 only after authorizing the strict-loader repair as a prerequisite. "mn-cbaf37" must remain "in_progress" until Erik accepts this report. No implementation, new item, filing, admission, or completion transition was performed.

## 2. Repository Snapshot

The evidence boundary is the content-addressed snapshot named above.

**VERIFIED FACT:** Capture ran from "2026-08-24T15:29:28.627688Z" through "2026-08-24T15:29:30.542083Z". Every repository received a reachable Git bundle, a HEAD archive, an extracted tree digest, full dirty inventory, and byte-verified copies of relevant modified or untracked files. Source hashes and relevant source sets matched immediately before and after capture. See S1 and S9.

| Repository | Frozen HEAD, branch | Capture state | Materially relevant working bytes |
|---|---|---|---|
| "/Users/erik/Custom-Coding/agent-do" | "29e816eff57e1c18259782bc372ad06f4b691432", main | Dirty | Modified Manna state, install/hooks/contracts/registry/tests/ZPC surfaces; untracked sealed current handoff and touch-ledger work. Full inventory is frozen. See S2 and S4. |
| "/Users/erik/Custom-Coding/aldebaran-group" | "d25e97db323ed4fcc67c61596fb6dd425dda657b", main | Dirty | Modified Manna presentation/state, dirty submodule worktrees, untracked historical Moon work orders and return material. Relevant copies were frozen; sensitive "fromErik" material was inventoried but not inspected or copied. See S5 and S6. |
| "/Users/erik/Custom-Coding/theta-indi" | "6b1ddba2edc06f41e2ec89cd777ffb088bd345cb", main | Dirty | Only ".gitignore" was modified and frozen. See S8. |
| "/Users/erik/Custom-Coding/the-orient" | "5c948115869a4935dc02c4ebe6895c7dee0c9fdf", main | Clean | None. See S7. |
| Theta publication mirror | "ecb753b24518820ba088dd927f9e3b6e39b35b4d", main | Clean | Captured as an auxiliary repository with its own bundle, archive, and tree digest. See S1. |

**VERIFIED FACT:** The frozen working board shows "mn-cbaf37" already claimed by "codex-01a02afe94d27b52", status "in_progress", with handoff digest "e23eb44...". The current handoff declares itself the sole work order and supersedes the historical prompt. See E15 and E16.

**Post-snapshot drift receipt:** At "2026-08-24T15:50:07Z", read-only Git metadata showed agent-do, theta-indi, and the-orient still at their frozen HEADs. Aldebaran had advanced to "7803d5df5dcd6d406bc65aa7caf25db2967134b7". Those newer Aldebaran bytes were not inspected or blended into this report. This is disclosed drift, not evidence invalidation.

No tests were executed. Only static inspection of frozen code, history bundles, checked-in tests, and frozen working overlays was used.

## 3. Stage 0 Incumbent Audit

| Predicate | Verdict | Evidence and classification |
|---|---|---|
| 1. Board identity and strict-mode durability | CLOSED | Board identity is explicit, validated, and used to distinguish initialized from identityless legacy state. Identity publication is the final initialization commit point. See E5 and E7. |
| 2. Canonical item-handoff pairing and reverse pointers | CLOSED | Board and handoff pointers are validated both ways; recovery and reconcile know the pair. See E5. |
| 3. Content binding and explicit resealing | CLOSED | Handoff content binding excludes the mutable binding field, validates the stored digest, and requires an explicit seal or rebind operation. See E5 and E7. |
| 4. Authenticated ownership and restart durability | CLOSED | Claim proof uses a machine-key-derived digest, constant-time comparison, stable host session identities, and a machine-local key outside the repository. Public owner labels are not credentials. See E2 and E6. |
| 5. Atomic claim and lifecycle transitions | PARTIAL | File locking, owner checks, and atomic replacement are present. The permissive loader can omit malformed rows before the atomic rewrite. This is a Stage 0 defect. See E3 and E4. |
| 6. Journal authentication, recovery, and idempotency | PARTIAL | Journal signing and recovery machinery are present, but pair-recovery paths can also load permissively and rewrite the board. This is the same Stage 0 defect, not provenance territory. See E6 and E3. |
| 7. Legacy, mixed, malformed, and cross-project migration convergence | CLOSED | Migration uses strict loading, validates identity and pairing, and rejects malformed or cross-project state rather than silently normalizing it. See E8 and E10. |
| 8. Symlink, path escape, Git visibility, and workflow-sprawl defenses | CLOSED | Canonical-root checks reject symlinks and escapes; lint reports untracked canonical state; reconcile detects active shadow workflows. See E5 and E10. |
| 9. Ordered handoff presentation, blocker markers, and generated index | CLOSED | ".manna/handoff-order.yaml" is canonical; dense filenames and the index are transactional derived presentation. See E7 and E10. |
| 10. Initialization atomicity | CLOSED | Initialization validates staged state, journals the transition, publishes board identity last, and has explicit interruption recovery. See E7. |
| 11. Migration and identity discoverability | CLOSED | Identityless nonempty boards receive migration guidance before mutation; bootstrap and lint surface the condition. See E5. |
| 12. Lint and reconcile coverage | PARTIAL | Coverage is broad, but the lint board loader skips malformed JSONL and may still return clean after warning on stderr. Reconcile fix paths inherit the rewrite risk. This is a Stage 0 defect. See E9. |

No audited predicate is OPEN, REGRESSED, or OUTSIDE SCOPE.

**Required incumbent repair:** Replace permissive loading with strict loading on every path capable of rewriting canonical board state, pair state, recovery state, or returning a clean lint verdict. Add malformed-middle-row negative controls for claim, update, block, unblock, done, pair recovery, reconcile fix, and lint. Preserve the existing permissive reader only where a caller is expressly diagnostic and cannot write or declare success.

The landed history around "bb73706", "745efa8", "c905586", "ad30b65", and "eb98eef" is present in the frozen reachable bundle and is ancestral to the frozen HEAD; commit messages and Manna trailers are recorded in the manifest. See S3.

## 4. Objective Gap Matrix

| Objective | Adjudicated state | Evidence and consequence |
|---|---|---|
| Authenticated claim ownership and ordinary lifecycle writes | PARTIAL | Authentication and locking are closed; malformed-row rewrite safety is not. Repair Stage 0 locally. See E2 and E3. |
| Separate authorization, launch, admission, review, ratification, and gate authorities | OPEN | Manna models one claim owner and four work statuses, not these powers. New provenance responsibility. See E2. |
| Work-order content identity and base commit | PARTIAL | Handoff bytes are sealed and the handoff can name a base, but Manna does not bind accepted inputs, launch base, or attempt identity as one transition. See E5. |
| Immutable attempts, returns, artifacts, and admission receipts | OPEN | Moon Two hand-assembles these outside Manna. New provenance responsibility. See M1. |
| Blocker edges | CLOSED mechanically | Manna stores and validates edges. See E2. |
| Evidence-bound blocker release | OPEN | "unblock" removes the edge on authenticated owner request; reconcile treats done or missing blockers as resolved. Neither requires an admitted-evidence receipt. See E9. |
| Artifact accepted versus subject passed | OPEN | No orthogonal fields exist. Moon Two explicitly demonstrates accepted evidence while the phase remains red. See M7. |
| Current, superseded, rejected, and admitted attempt state | OPEN | Present only as repository-specific prose and filenames. |
| Numerator, denominator, membership, and provenance identity | OPEN generically | Moon Two has specific controls, but no portable record binds all four. See M8. |
| Unresolved human judgment as first-class state | OPEN | Project prose records rulings; Manna does not preserve unresolved semantic questions or bounded human decisions. |
| Next admissible action across orthogonal states | PARTIAL | Manna can suggest actionable work from lifecycle and blockers, but cannot derive the next semantic transition because those states do not exist. |

## 5. Verified Current Architecture

**VERIFIED FACT:** Repository authority places running code and checked-in files above historical notes. The taxonomy gate says a new tool must own distinct executable territory, state, or dependencies rather than merely provide conceptual cleanliness. See E1 and E17.

Current ownership boundaries:

- **Manna:** actionable work identity, lifecycle, claim ownership, handoff binding, dependency edges, migration, and generated presentation.
- **Spec:** intended change artifacts and file-derived change status, not semantic evidence admission.
- **Coord:** advisory presence, focus, and correlation. Its event stream tolerates malformed entries, guards are advisory, and command failures may be swallowed. It is not authority. See E13.
- **Harness contracts:** declared behavioral classes and bounded probes. They do not prove semantic correctness, complete absence of side effects, or external authority. See E12.
- **Git:** byte history and commit identity, not truth, launch authority, evidence admission, or human intent.
- **Context:** external documentation and citation material.
- **Sessions:** mutable transcript history, not canonical receipts.
- **Brief:** receipt-grounded synthesis and prose, not transition authority.
- **Prompt:** reusable prompt/template state, not action authorization.
- **ZPC:** advisory memory. Its own law says live observation outranks stored claims. It cannot become authority by remembering a decision. See E14.
- **Dispatcher telemetry:** unauthenticated mutable correlation evidence recording route, time, and exit behavior. It is not a content-bound receipt. Structured, natural-language, offline, and direct child-tool paths do not share one universal semantic interception point. See E11.

### Working hypotheses

| # | Verdict | Architectural consequence |
|---|---|---|
| 1 | PARTIALLY CONFIRMED | Stage 0 is sound enough to remain incumbent, subject to the strict-loader prerequisite. |
| 2 | PARTIALLY CONFIRMED | The smallest fit is a canonical event family plus a narrow Manna head anchor, not a free-standing mutable record. |
| 3 | CONFIRMED | Preserve Manna lifecycle. Keep semantic states orthogonal. |
| 4 | CONFIRMED | Templates, indexes, and decision cards should be derived or reconciled against the canonical event head. Moon Two and Orient currently hand-assemble such views. |
| 5 | CONFIRMED | No new top-level tool is justified now. |
| 6 | CONFIRMED | Git and handoff hashes prove bytes only. A3 supplies the falsifier for stronger claims. |
| 7 | CONFIRMED | Dispatcher telemetry is correlation evidence only. See E11. |
| 8 | CONFIRMED | Contract declarations classify promises but cannot prove meaning, outside authority, or total side-effect freedom. |
| 9 | CONFIRMED | No universal dispatcher covers structured, natural, offline, and direct-child invocation. |
| 10 | CONFIRMED | Documentation-only enforcement is bypassable and cannot own canonical transitions. |
| 11 | CONFIRMED | Fixed invariants with risk-scaled control intensity are necessary for adoption. |
| 12 | PARTIALLY CONFIRMED | Independent context and authority reduce shared error. Merely choosing a different model family does not itself establish independence. Independence must bind scope, inputs, role, and controlling context. |

### Remaining territory

**DESIGN PROPOSAL:** The protocol owns authenticated semantic transition records, immutable attempt lineage, bounded admission, verdict, ratification, gate and dependency evidence, quantitative claim identity, explicit unresolved decisions, and the next admissible action.

It references, but does not replace:

- Manna work IDs and claim ownership
- sealed handoffs
- Git commits and artifact bytes
- source citations and sensitive evidence locations
- repository constitutional content
- external systems and human rulings

It does not own meaning, truth, QA generally, coordination, memory, policy authorship, supply-chain attestation, or human judgment itself.

## 6. Moon Two Semantic Lessons

1. **VERIFIED FACT:** Moon Two separates constitutional authority, campaign state, launch, builder work, independent review, evidence admission, and final ratification. Builders do not perform the final audit. Chat is not canonical state. See M1.
2. **VERIFIED FACT:** Attempts and returns are immutable. Correction occurs through a new attempt and supersession rather than overwrite. Workers submit and leave final acceptance to a separate authority. See M1 and M2.
3. **VERIFIED FACT:** The A3 pro review found all requested digests aligned but returned REVISE because the controlling O2 dependency order was semantically wrong. Seven checks passed and one semantic check failed. See M4.
4. **VERIFIED FACT:** A4 corrected the order while preserving A3. The A4 artifact was accepted, but the phase remained red. See M7.
5. **VERIFIED FACT:** Moon Two records accepted evidence separately from a superseded decision surface. It also states that human ratification can define scope but cannot manufacture external provenance. See M8.
6. **VERIFIED FACT:** Red-gate stickiness, externally fixed denominators, and an independent pass are explicit campaign law. See M1.
7. **VERIFIED FACT:** The new control room is an honest read-only derived dashboard. It reads Manna plus a hand-authored campaign file, infers submission/admission from file existence, and detects changes using metadata such as modification time and size. It must therefore remain a view, not authority. See M10 and M11.

**INFERENCE:** A3 is the decisive architectural fixture. Any protocol that accepts A3 merely because all bytes agree has confused consistency with correctness.

## 7. Threat And Failure Model

### Trust boundary

The trusted local mechanism consists of:

- the Manna executable and frozen policy version
- the canonical repository files
- the machine-local identity key
- the filesystem, locking, and authenticated journal implementation
- explicit human authorities for decisions no mechanism can make

A malicious operating-system administrator, repository-key custodian, or principal with authority to rewrite both canonical state and its history remains outside what local hashes can defeat. Cross-machine signing is useful only if independent key custody and verification are real.

| Failure | Accidental or negligent defense | Compromised or malicious-process defense | Residual limit |
|---|---|---|---|
| Stale prompt, base, or input | Pin exact identities and reject mismatch before launch or admission. | Expected-head CAS and role checks prevent silent canonical advancement. | A correctly pinned source may still be wrong. |
| Copied but wrong requirement | Require high-risk independent semantic review. | Separate reviewer and admission authority. | Honest reviewers can still agree incorrectly. |
| Duplicated prose drift | Generate or reconcile views from canonical events. | Refuse transitions when a required derived view declares a stale head. | Prose outside declared scope may remain stale. |
| Worker self-admission or ratification | Policy separation and wrong-owner rejection. | Authenticated role grants and immutable receipts. | A colluding authority can still admit bad work. |
| Unauthorized or non-atomic transition | One Manna lock, journal, expected head, no-clobber event, anchor-last publication. | Tamper-evident history and ownership validation. | A hostile machine-key custodian can forge local authority. |
| Blocker cleared before evidence | Require an admitted receipt and make blocker satisfaction plus edge removal one transaction. | Direct board edits become detectable by reconciliation. | An admitted receipt may itself embody bad judgment. |
| Runtime population called external authority | Require "provenance_class" and source receipt. | Reject incompatible class transitions. | Classification ultimately depends on policy authorship. |
| Hidden membership or denominator change | Bind numerator, denominator, membership manifest, inclusion rule, and source digest. | Treat mutation as a new claim or superseding event. | A frozen denominator may still be conceptually inappropriate. |
| Hash presented as truth | Schema and UI label hashes as byte identity only. | Reject receipt types that claim semantic proof from a digest. | No validator can force intellectual honesty outside canonical state. |
| Mutable testimony presented as receipt | Require immutable content identity and external anchor. | Reject unbound URLs, chat, telemetry, or mutable files as final receipts. | External systems may later become unavailable. |
| Direct, natural, offline, or child invocation bypass | Canonical admission remains impossible without Manna transition validation. | Bypassed execution cannot acquire admitted state. | Work can still happen outside protocol; only canonical acceptance is controlled. |
| Partial write, retry, concurrent race | Journaled intent, request ID, expected head, and deterministic recovery. | Same-record CAS ensures one winner. | Filesystem or lock implementation must be proven in Stage 1. |
| Old immutable attempt mistaken as current | Explicit current head and supersession links. | Derived views must identify the head they replayed. | Humans may still quote obsolete material elsewhere. |
| Accepted artifact confused with passing subject | Separate admission and verdict dimensions. | Illegal-transition tests. | The semantic verdict remains judgment. |
| Ratification confused with provenance | Ratification event may authorize scope but cannot change provenance class. | Type-level transition rejection. | Humans can still ratify poor policy. |
| Sensitive or blind input leakage | Reference digest, custodian, retention class, and access boundary without copying content. | Derived views redact by field classification. | A permitted reviewer can still disclose material. |
| Honest disagreement | Preserve inconclusive, deviations, unresolved decisions, and next authority. | No forced green state. | Resolution remains human or domain-specific. |

No cryptographic signature is recommended for Stage 1. Local HMAC and Git identity are adequate for detecting accidental or unprivileged local process violations. Signing becomes meaningful only when a verifier and key custodian sit across a real trust boundary.

## 8. Canonical State Machine

**DESIGN PROPOSAL:** Work lifecycle stays in Manna. Provenance dimensions are separate replayed projections.

~~~text
Manna work:      open -> in_progress <-> blocked -> done
Authorization:   prepared -> authorized -> revoked
Attempt:         prepared -> launched -> submitted -> superseded
                         \-> aborted
Artifact:        pending -> admitted -> superseded
                         \-> rejected
Subject verdict: unreviewed -> pass | fail | inconclusive
Ratification:    not_ready -> ready -> ratified | declined -> superseded
Gate:            red -> eligible -> passed -> invalidated
Dependency:      blocked -> satisfied

authorized -> launched
submitted -> artifact pending
artifact admitted -> subject review
subject pass -> ratification ready
ratified -> gate eligible
gate passed -> dependency satisfied
~~~

The model preserves:

~~~text
prepared != authorized != launched
submitted != admitted
artifact admitted != subject passed
ratification-ready != ratified
ratified != gate passed
old immutable attempt != current state
~~~

### Legal transition ownership

All transitions use one authenticated request ID, expected current head, policy digest, and Manna lock. Failure is fail-closed. A repeated identical request returns the original receipt. A conflicting request ID or stale head is rejected. An interruption is recovered from an authenticated intent journal; readers recognize only the externally anchored head.

| Transition | Owner | Preconditions and receipt |
|---|---|---|
| prepare | Preparer | Sealed work order, scope, non-effects, base, inputs, territories, policy and risk classification. Produces immutable prepared-attempt event. |
| authorize | Authorizer | Prepared attempt exists; required source and policy identities match. Produces bounded authorization receipt. |
| revoke_authorization | Authorizer | Authorization current and no forbidden downstream state. Otherwise requires invalidation/supersession. |
| launch | Launcher | Authorized attempt, current Manna owner, fresh base and inputs, dependencies satisfied for launch. |
| submit | Worker and claim owner | Launched attempt; immutable return and artifacts identified; deviations and unresolved decisions declared. |
| review | Reviewer | Submitted attempt; review scope and independence predicates satisfied. Produces pass, fail, or inconclusive semantic review receipt. |
| admit or reject_artifact | Admission owner | Submitted artifact and required review receipts exist. Admission states exact accepted purpose and explicit non-effects. |
| supersede_attempt | Authorizer or admission owner, as policy assigns | Replacement attempt exists; old bytes remain immutable; links are explicit in both event projections. |
| present_for_ratification | State integrator | Required admissions and verdicts exist; unresolved decisions are enumerated. |
| ratify or decline | Human ratifier | Exact package, scope, and receipts presented. Ratification does not alter source provenance. |
| pass_gate or invalidate_gate | Gate owner | All exact predicates, denominator identity, negative controls, ratification conditions, and current heads match. |
| satisfy_dependency | Dependency authority | Admitted blocker receipt applies to the exact edge and scope. Provenance event plus Manna edge removal are one logical transaction. |
| complete_work | Manna owner or designated state integrator | Existing Manna completion law plus policy-defined semantic terminal condition. It does not collapse the orthogonal states. |

### Logical atomicity

The event file may be physically written before its board anchor, but it is not canonical until the Manna row points to its exact SHA-256. The journal records intent and pre-state. The anchor is published last. Recovery either completes the exact transition or leaves the prior head canonical. Unanchored event bytes are inert evidence, not state.

## 9. Minimum Portable Record

### Canonical family

**DESIGN PROPOSAL:**

~~~text
.manna/provenance-policy.yaml
.manna/provenance/<work-id>/events/<sequence>-<event-id>.json
.manna/issues.jsonl -> provenance_head { event_id, sha256, policy_sha256 }
~~~

The issue row supplies the external binding. No event contains or claims its own final digest.

### Fields and invariants

| Field | Invariant carried |
|---|---|
| protocol, schema_version | Parser and transition law are explicit; unknown versions fail closed. |
| event_id, sequence, request_id | Immutable identity, ordering, and idempotent retry. |
| previous_event | Exact predecessor ID and digest; no fork without an explicit conflict outcome. |
| work_id, attempt_id | Stable work identity separated from immutable execution identity. |
| supersedes | Correction never overwrites history. |
| transition, state_after | Event intent and complete orthogonal projection can be replay-verified. |
| policy and risk | Authority and control intensity bind to an exact policy version. |
| actor, authority_class, role_grant | Who acted, under which power, and which grant authorized it. |
| scope, non_effects | Exact effect and what the transition explicitly does not decide. |
| work_order | Independently bound work-order path and digest. |
| base, inputs | Exact Git and accepted input identities; mutable references alone are inadmissible. |
| territories | Writable, read-only, forbidden, blind, and sensitive boundaries. |
| dependencies | Exact edge plus admitted satisfaction receipt where applicable. |
| deliverables, acceptance_conditions | What must be returned and how it may be judged. |
| artifacts | Path or URI, digest, as-of identity, custodian, and sensitivity class. |
| facts, proposals, deviations, unresolved_decisions | Epistemic categories cannot silently collapse into one conclusion. |
| review | Reviewer, scope, verdict, controlling inputs, and independently checkable separation predicates. |
| admission | Exact artifact, admitted purpose, admission owner, and explicit non-effects. |
| quantitative_claim | Numerator, denominator, membership rule and manifest, provenance class, and source receipt. |
| negative_controls | Exact expected failure, observed diagnostic, and result. |
| state_after, next_admissible_action | Current state and next legal transition are explicit and replay-checkable. |

### Minimal concrete example

~~~json
{
  "protocol": "agent-do.provenance.event",
  "schema_version": 1,
  "event_id": "pv-01K39A4-ADMIT-A4",
  "sequence": 6,
  "request_id": "req-01K39A4-ADMIT-A4",
  "previous_event": {
    "event_id": "pv-01K39A3-REVIEW-A4",
    "sha256": "8a02...91bf"
  },
  "work_id": "mn-687319",
  "attempt_id": "a4",
  "supersedes": ["a3"],
  "transition": "artifact.admit",
  "policy": {
    "path": ".manna/provenance-policy.yaml",
    "sha256": "41bf...028c"
  },
  "risk": {
    "tier": "high",
    "reasons": ["constitutional dependency order", "gate consequence"]
  },
  "actor": {
    "principal": "session:review-seat-2",
    "authority_class": "admission_owner",
    "role_grant_sha256": "027d...aa90"
  },
  "scope": {
    "effect": "admit A4 as evidence of the corrected O2 dependency order",
    "non_effects": [
      "does not pass the subject",
      "does not ratify Phase 1",
      "does not pass the gate",
      "does not complete the Manna item"
    ]
  },
  "work_order": {
    "path": "moon-two/handoff-prompts/P1-I_mn-687319-a4_o2-ordering-correction.md",
    "sha256": "51f0...b772"
  },
  "base": {
    "repository": "aldebaran-group",
    "git_commit": "d25e97db323ed4fcc67c61596fb6dd425dda657b"
  },
  "inputs": [
    {"kind": "decision_card_a3", "sha256": "a4c0...a711"},
    {"kind": "independent_review_a3", "sha256": "c221...3d18"}
  ],
  "territories": {
    "writable": [],
    "read_only": ["moon-two/receipts/phase1/"],
    "forbidden": [".handoff/fromErik/"],
    "sensitive": []
  },
  "artifacts": [
    {
      "path": "moon-two/receipts/phase1/PHASE-ONE-DECISION-CARD-A4.md",
      "sha256": "03b1...1a55",
      "as_of_git": "d25e97db323ed4fcc67c61596fb6dd425dda657b"
    }
  ],
  "review": {
    "receipt_event": "pv-01K39A3-REVIEW-A4",
    "scope": "semantic O2 dependency order",
    "independence": {
      "worker_is_reviewer": false,
      "controlling_context_reused": false
    },
    "verdict": "pass"
  },
  "admission": {
    "artifact_state": "admitted",
    "purpose": "corrected ordering evidence only"
  },
  "quantitative_claim": null,
  "negative_controls": [
    {
      "mutation": "swap source closure before Erik O2 decisions",
      "expected": "semantic_order_mismatch",
      "observed": "semantic_order_mismatch"
    }
  ],
  "state_after": {
    "authorization": "authorized",
    "attempt": "submitted",
    "artifact": "admitted",
    "subject_verdict": "unreviewed",
    "ratification": "not_ready",
    "gate": "red"
  },
  "unresolved_decisions": ["Erik has not ratified the corrected sequence"],
  "next_admissible_action": {
    "transition": "subject.review",
    "authority_class": "independent_reviewer"
  }
}
~~~

External canonical anchor:

~~~json
{
  "provenance_head": {
    "event_id": "pv-01K39A4-ADMIT-A4",
    "sha256": "9d90...b4e2",
    "policy_sha256": "41bf...028c"
  }
}
~~~

Derived views must declare the head event, head digest, generator version, and generation time. Reconciliation recomputes the view from canonical events and rejects mismatches.

## 10. Existing-Capability Matrix

| Invariant | Existing owner | Proven capability | Gap | Can compose | Required change |
|---|---|---|---|---|---|
| Work identity and owner | Manna | Stable ID, authenticated claim, lifecycle lock. See E2. | Strict-loader defect. | Yes | Repair loader use. |
| Work-order bytes | Manna handoff | Sealed content binding and reverse pointer. | No attempt-specific accepted-input binding. | Yes | Reference handoff digest from prepare and launch events. |
| Immutable attempts | Moon Two convention | Attempt-specific paths and supersession by correction. | No portable enforcement. | Yes | Canonical attempt events. |
| Authorization roles | Project constitutions | Moon, Theta, and Orient declare role boundaries. | No generic authenticated transition law. | Yes | Policy role grants plus role-checked events. |
| Artifact byte identity | Git and hashes | Exact bytes and as-of commit. | Identity is not admission or truth. | Yes | Artifact identity inside submission and admission events. |
| Evidence admission | Project review prose | Moon and Orient record bounded rulings. | Hand-assembled and not mechanically linked to current state. | Yes | Typed admission event. |
| Semantic verdict | Human reviewer | Independent review can reject shared errors. | Cannot be generated from byte agreement. | Yes | Preserve reviewer scope, independence, and verdict. |
| Ratification and gate | Human/project policy | Theta and Orient reserve ratification to Erik; Moon keeps red sticky. | No portable orthogonal state. | Yes | Typed events, human authority remains external. |
| Dependency edges | Manna | Mechanical blocker graph. | Edge can clear without admitted evidence. | Yes | Atomic evidence-bound satisfaction transition. |
| Quantitative claim | Moon-specific records | External denominator and membership controls. | No portable schema. | Yes | Typed quantitative-claim object. |
| Negative controls | Moon and Orient | Exact mutation and expected diagnostic conventions. | Not generally required or bound. | Yes | Risk-policy requirement and receipt. |
| Derived presentation | Manna and Moon control room | Transactional Manna index; read-only Moon dashboard. | Semantic views may duplicate state. | Yes | Head declaration and reconciliation. |
| Dispatcher receipt | Dispatcher telemetry | Route correlation and exit status. | Mutable, unauthenticated, not content-bound. | No as authority | Reference only as auxiliary evidence. |
| Contract declaration | Harness | Command-surface classification and bounded probes. | Promise is not semantic proof. | Yes as policy input | Never treat as verdict or admission. |
| Advisory memory | ZPC, sessions | Context and learned conventions. | Mutable and non-authoritative. | Yes as input | Pin accepted bytes if used. |
| Sensitive evidence | Project boundaries | Theta and Orient already separate public, blind, and local surfaces. | No generic redaction/reference law. | Yes | Sensitivity class, custodian, digest-only references. |
| Current state and next action | Manna | Work lifecycle and blocker-based actionability. | No orthogonal semantic projection. | Yes | Replay current provenance head. |

### Universal candidate invariants

| # | Invariant | Stage 0 status | Remaining gap | Decision |
|---|---|---|---|---|
| 1 | One canonical machine-readable authority record | PARTIAL | Manna is canonical for work, not semantic events. | Refine: one canonical append-only event family plus one external head, not one mutable omnibus record. |
| 2 | Every action traces to authorization and reserved owner | PARTIAL | Claim owner exists; prepare, launch, admit, ratify, and gate powers do not. | Refine and adopt. |
| 3 | Preparation and launch are separate | OPEN | No machine state. | Adopt. |
| 4 | Every attempt has immutable identity, path, and independent digest | OPEN | Moon convention only. | Adopt. |
| 5 | Input mismatch, stale base, ownership collision, or authority ambiguity stops execution | PARTIAL | Ownership collision closes; provenance input and base checks do not. | Refine and adopt. |
| 6 | Workers submit durable returns and do not self-admit where independence is required | OPEN | Project law only. | Adopt with risk-policy threshold. |
| 7 | Admission, verdict, ratification, gate, and issue lifecycle are independent | OPEN | Manna has only lifecycle. | Adopt. |
| 8 | Dependencies clear only from admitted evidence and authorized transition | PARTIAL | Edges exist, evidence-bound clearing does not. | Adopt. |
| 9 | Quantitative claims bind numerator, denominator, membership, provenance class, and receipt | OPEN | Moon-specific only. | Adopt. |
| 10 | Gate denominator is fixed outside judged behavior | OPEN generically | Project-specific law only. | Adopt for quantitative gates. |
| 11 | Ratification may author scope but cannot manufacture external provenance | OPEN generically | Moon states it, Manna does not model it. | Adopt. |
| 12 | Every executable gate demonstrates an intended failure and diagnostic | OPEN generically | Some project negative controls exist. | Adopt above trivial risk. |
| 13 | Digests prove byte identity, not truth or authority | CLOSED as observed design principle | Not enforced in a semantic schema. | Adopt explicitly. |
| 14 | High-risk semantic decisions receive independent review | OPEN generically | A3 proves the need. | Adopt. |
| 15 | Red remains red until exact predicates and reserved authority clear it | OPEN generically | Manna blocked/open is not semantic gate state. | Adopt. |
| 16 | Current state and next admissible action are explicit | PARTIAL | Only work actionability exists. | Adopt. |
| 17 | Sensitive inputs may be referenced without public copying | OPEN generically | Project-specific boundaries exist. | Adopt. |
| 18 | Control intensity scales with risk; core truth and authority invariants do not | OPEN generically | No shared classifier. | Adopt. |

## 11. Architecture Options And Scores

Scores are 1 to 5, where 5 is strongest. Cost and Cer score higher when migration cost and ceremony are lower.

| Option | SSA | OL | BR | SH | AC | RA | Paths | Neutral | No-CI | Cost | Test | Cer | Sensitive | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1. Narrow Stage 0 extensions only | 3 | 3 | 2 | 3 | 5 | 4 | 3 | 4 | 5 | 5 | 5 | 4 | 3 | 49 |
| 2. Canonical event family composed with Manna | 5 | 5 | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4 | 5 | 4 | 5 | 62 |
| 3. Manna monolith | 5 | 1 | 4 | 4 | 5 | 5 | 4 | 4 | 5 | 3 | 5 | 3 | 4 | 52 |
| 4. Extend spec | 3 | 4 | 2 | 3 | 2 | 3 | 3 | 4 | 4 | 4 | 3 | 4 | 3 | 42 |
| 5. Registry/contracts plus validators | 3 | 4 | 3 | 3 | 2 | 3 | 4 | 4 | 4 | 4 | 4 | 4 | 3 | 45 |
| 6. Common receipt and transition layer | 5 | 4 | 4 | 5 | 5 | 5 | 5 | 5 | 5 | 3 | 5 | 3 | 5 | 59 |
| 7. New first-class tool | 5 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 2 | 4 | 2 | 4 | 49 |
| 8. External incubation plugin | 3 | 5 | 2 | 4 | 3 | 3 | 3 | 4 | 4 | 5 | 4 | 5 | 4 | 49 |

Abbreviations: single-source authority, overlap avoidance, bypass resistance, semantic honesty, atomicity/concurrency, recovery/auditability, invocation compatibility, stack neutrality, operation without CI, migration cost, testability, ceremony, and sensitive-data boundaries.

**DESIGN PROPOSAL:** Option 2 wins because semantic state becomes portable without splitting the transaction owner. Option 6 is a possible end state, but building it now would create abstraction before two independent consumers prove the common boundary.

Falsifier for Option 2: Stage 1 cannot make the event plus Manna head logically atomic, requires a second mutable source, or cannot support one ordinary repository and one governance-heavy repository with the same core schema.

Falsifier for Option 6: two non-Manna consumers do not emerge with the same transition semantics, or adapters become the real authorities.

## 12. Recommended Near-Term Architecture

Build an opt-in provenance module within "agent-manna", but keep its semantic state in a separate append-only record family.

Manna continues to own:

- work ID, claim, lifecycle, blockers
- canonical handoff pairing and digest
- repository-local locking, journaling, recovery, migration
- provenance head anchoring and transition authorization

The provenance family owns:

- attempt lineage
- authorization and launch
- submission, review, and bounded admission
- verdict, ratification, gate, and dependency evidence
- denominator identity
- unresolved decisions and next admissible action

Project policy continues to own:

- substantive constitutional rules
- role appointments
- consequence thresholds
- semantic acceptance criteria
- human ratification

Explicit non-effects:

- No second task board.
- No generated filename or dashboard becomes authority.
- No generic protocol declares semantic truth.
- No low-risk task requires high-risk review.
- No sensitive evidence is copied merely to make a receipt self-contained.
- No dispatcher interception is claimed to prevent all off-protocol execution.
- No self-admission is permitted where policy requires independence.
- No new top-level executable family is created.

## 13. Defensible End State

**DESIGN PROPOSAL:** A shared receipt and transition library becomes defensible only after at least two tool families other than Manna need the same event validation, replay, redaction, and CAS semantics.

At that point:

- Manna remains the adapter for actionable work.
- Other stacks may bind the same event family to their own external canonical head.
- The common kernel owns schema validation, event replay, transition legality, digesting, policy evaluation, and derived-view proofs.
- It still owns no board, policy content, semantic judgment, or human authority.

The end state is abandoned if adapters need materially different state laws, if users interact mainly with duplicated adapter state, or if a common library weakens Manna’s crash and ownership guarantees.

## 14. Risk Tiers And Examples

### Classifier

Score each axis 0, 1, or 2:

- consequence
- irreversibility
- authority surface
- data sensitivity
- concurrency
- external side effects
- proof burden

Classification:

- LOW: total 0 to 3, no hard trigger
- NORMAL: total 4 to 7, no hard trigger
- HIGH: total 8 or more, or any hard trigger involving constitutional authority, production mutation, denominator change, sensitive or blind data, human rights/consent, or irreversible external effect

Every tier keeps the same small invariant core:

- exact work and attempt identity
- explicit authorization
- pinned inputs or declared mutable inputs
- exact scope and non-effects
- durable result identity
- current state and next action
- hashes labeled as identity only

Only intensity scales.

| Example | Tier | Required controls |
|---|---|---|
| Correct one reversible documentation typo | LOW | Preparer, authorizer, and worker may be one actor. One attempt, work-order binding, diff identity, lightweight acceptance. No independent semantic reviewer unless the text is authoritative. |
| Normal code change with tests | NORMAL | Separate submission from admission, pinned base, tests and one negative control where executable behavior changes, review appropriate to repository practice, artifact versus subject state kept distinct. |
| Constitution, denominator, production, or sensitive-data change | HIGH | Separate worker, semantic reviewer, admission owner, and human ratifier where applicable; isolated inputs; exact denominator and membership; negative controls; deterministic rerun where meaningful; whole-system verification; red gate; fail-closed transitions. |

Reasoning effort, isolation, review independence, evidence granularity, negative controls, reruns, ratification, and whole-system verification scale upward. Truth and authority invariants do not.

## 15. Adversarial Validation Plan

Stage 1 and later implementations must include:

1. Schema property tests over unknown versions, missing fields, invalid enums, and replay equivalence.
2. Exhaustive illegal-transition tests.
3. Wrong-owner and missing-role-grant tests.
4. Same-head concurrent transition races with exactly one winner.
5. Stale base, stale handoff, stale policy, and stale accepted-input rejection.
6. Blocker release without an admitted edge-specific receipt.
7. Derived-view drift and forged head declaration.
8. A record attempting to authenticate its own final bytes.
9. Denominator, membership, inclusion-rule, and provenance-class one-field mutations.
10. Exact one-field negative controls with stable expected diagnostics.
11. Read-only command side-effect detection in external scratch.
12. Structured, natural-language, offline, direct-child, and root-special bypass attempts. Off-path execution may occur, but canonical admission must remain impossible.
13. Interrupted event write before anchor, after journal, and during anchor publication.
14. Idempotent retry of the same request and conflicting reuse of a request ID.
15. Accepted artifact with failed or unreviewed subject.
16. Cross-project import, version migration, unknown-version refusal, and downgrade resistance.
17. Sensitive-field redaction and blind-lane non-disclosure.
18. The A3 fixture: every byte, digest, replay, and derived view agrees on one wrong O2 order; only independent semantic review rejects it.

Mechanically provable:

- schema, identity, role, transition, CAS, journal, replay, supersession, and declared evidence relationships
- declared reviewer separation predicates
- exact byte equality and negative-control diagnostics

Not mechanically provable:

- semantic truth
- reviewer competence, honesty, or genuine independence of thought
- whether the declared denominator answers the right scientific question
- whether an authority ought to have been appointed
- whether omitted evidence exists
- whether a human ruling is wise
- whether a malicious root-level custodian rewrote every local trust anchor

## 16. Adoption And Migration

### agent-do

Add the event family as an opt-in Manna capability. Existing boards remain valid. Items without a policy have no semantic provenance state and retain existing lifecycle behavior. Strict loading must be repaired first.

### Moon Two

Do not rewrite A1 through A4 or any immutable receipt. Import them as reference events whose artifact identities point to existing bytes. A3 remains immutable and superseded; A4 becomes its correction. Existing decision and review documents remain historical evidence. The control room becomes a derived adapter that reads canonical event state rather than inferring admission from file existence.

### theta-indi

**VERIFIED FACT:** Theta keeps constitutional source, actor history, ratification authority, generated locks, consent lineage, and publication mirroring distinct. Only Erik ratifies constitutional changes, while the lock proves exact constitutional bytes. See T1 and T2.

Adoption should reference exact constitution and lock identities, preserve Erik’s separate ratification event, and keep sensitive corpus bytes local. The public mirror remains derived publication, not a second authority. See T4.

### the-orient

**VERIFIED FACT:** Orient already separates claim registers, blind research lanes, fresh review seats, red-team release, human gate decisions, and final ratification. Its charter explicitly says the ledger is not the verdict. See O1 and O4.

Import existing review and ruling documents by reference. Preserve blind inputs outside public derived events. Model release to a reviewer separately from reviewer assessment, admission, and Erik’s ruling. Historical ".handoffs/" stay immutable; active workflow authority remains ".handoff/" plus ".manna/".

### Ordinary small repository

Install Manna as today. Default to a low-risk policy:

- one compact event per meaningful action
- roles may combine
- no independent review unless consequence or project policy triggers it
- Git diff and test receipt are enough for ordinary admission
- no denominator, ratification, or gate objects unless used

This avoids campaign-grade ceremony while retaining identity, authority, scope, and current-state honesty.

## 17. Stage 1 Authorization Packet

### Objective

Prove that one Manna item can carry a role-checked, immutable, externally bound attempt chain through:

~~~text
prepare -> authorize -> launch -> submit -> review -> admit
~~~

The work status remains independent throughout.

### Prerequisite

Repair all permissive-load-to-rewrite and permissive-load-to-clean-lint paths. Negative tests must show a malformed middle row cannot be erased or hidden by claim, update, lifecycle, blocker, recovery, reconcile, or lint.

### Explicit non-goals

- Full denominator and gate implementation
- Human ratification UI
- Universal dispatch interception
- External signing or PKI
- New service, database, dependency, framework, plugin, or top-level tool
- Migration of Moon Two history
- Automatic semantic judgment
- Filing later work

### Likely owner and files

Owner: "agent-manna".

Likely implementation surfaces:

- "tools/agent-manna/src/provenance.rs", new narrow module
- "tools/agent-manna/src/issue.rs"
- "tools/agent-manna/src/store.rs"
- "tools/agent-manna/src/workflow.rs"
- "tools/agent-manna/src/main.rs"
- "tools/agent-manna/test/integration.sh"
- directly relevant Rust tests
- Manna schema and command documentation

### Canonical and derived state

- Canonical: immutable event bytes plus issue-row external head and policy digest
- Derived: replayed current state, next action, human card, index, dashboard adapter
- An unanchored event is non-canonical
- A derived view without a matching head and generator declaration is stale

### Authorities introduced

- preparer
- authorizer
- launcher
- worker
- reviewer
- admission owner

Low-risk policy may assign several roles to one principal. High-risk policy must forbid worker self-review and self-admission.

### Compatibility boundary

Existing Stage 0 boards and items remain byte-compatible and behavior-compatible. Provenance is enabled only by explicit policy and item head fields. Existing Manna status and claim commands retain their meanings.

### Acceptance tests and negative controls

Stage 1 is accepted only if:

- transition and role property tests pass
- same-head concurrency yields one winner
- stale base, input, handoff, policy, and head fail closed
- interrupted writes recover idempotently
- self-authentication is rejected
- worker self-review and self-admission fail under high-risk policy
- artifact admission does not set subject verdict or Manna completion
- a derived card with one changed field fails reconciliation
- unknown schema versions and downgrades fail closed
- one low-risk example is materially lighter than the high-risk A3 fixture
- the A3-shaped semantic fixture remains rejected only by independent review, not falsely "proved" by hashes

### Migration

No bulk migration. Existing projects opt in. Existing evidence can later be referenced through explicit import events without altering source bytes.

### Rollback or abandonment

Because opt-in state is separate, abandonment means stopping new provenance transitions and continuing ordinary Stage 0 lifecycle. Existing event bytes remain inert historical evidence.

### Kill conditions

Abandon this architecture if:

1. It needs a second mutable source of truth.
2. Event plus head cannot be made logically atomic and recoverable under Manna’s storage model.
3. A Manna state mutation can bypass provenance preconditions while still producing canonical admission.
4. One small repository and one governance-heavy repository cannot share the invariant core.
5. Low-risk usage requires campaign-grade ceremony.
6. The record must authenticate itself.
7. Sensitive inputs must be copied into public state.
8. Attempt, artifact, verdict, ratification, gate, or work lifecycle must be collapsed to make the implementation tractable.

### Human decisions required before authorization

Section 19 decisions 1 through 4 must be answered. No implementation is authorized by this report alone.

## 18. Later Capability Bands, If Evidence Requires Them

No later numbered stages are justified yet.

Evidence establishes three possible dependency-ordered capability bands:

1. **Quantitative and gate law:** denominator manifests, provenance classes, gate predicates, red stickiness, and evidence-bound dependency release. This depends on the Stage 1 event and role kernel proving viable.
2. **Human ratification and sensitive-boundary adapters:** human signing surfaces, blind-lane release, public mirrors, and external custody. This depends on real cross-boundary key and retention requirements.
3. **Shared transition kernel:** extraction from Manna into a common library. This depends on at least two non-Manna consumers demonstrating the same semantics.

Each band must receive a separate authorization packet and kill condition. None should be pre-filed merely because it is imaginable.

## 19. Open Human Decisions

| Decision | Default recommendation | Alternatives and consequences |
|---|---|---|
| 1. Who grants protocol roles? | Track a policy record naming authority classes; Erik or the repository’s declared constitutional authority grants human roles. Manna session proof authenticates the acting session, not the legitimacy of the appointment. | Automatic role derivation is lighter but risks treating possession of a session as authority. External identity infrastructure is stronger across machines but adds custody and operational cost. |
| 2. What are the hard high-risk triggers? | Constitution, production mutation, denominator change, sensitive/blind data, irreversible external effect, and human consent always force HIGH. | Allowing recorded downgrades improves flexibility but risks normalizing exceptions. Forbidding all downgrades is safer but may become ceremonial. |
| 3. Where does canonical provenance live? | ".manna/provenance/", externally anchored by the Manna issue row. | A separate top-level root creates competing authority. A service improves centralized control but fails offline and small-repository requirements. |
| 4. Who may integrate provenance state with Manna completion? | A policy-designated state integrator or the authenticated Manna owner after all required semantic predicates are satisfied. | Letting any reviewer complete the item collapses review and lifecycle authority. Reserving every completion to Erik does not scale. |
| 5. When should signatures replace local HMAC? | Only when evidence crosses a machine, organization, or custodian boundary and independent key custody exists. | Signing everything now creates cryptographic theater. Never signing leaves cross-boundary identity weaker when such boundaries emerge. |

Repository truth cannot resolve these appointments and thresholds.

## 20. Falsifiers And Residual Risk

### Recommendation falsifiers

The near-term recommendation is wrong if:

- strict Stage 0 loading cannot be restored without redesigning the board substrate
- journaled anchor-last publication cannot provide one logical transition
- event replay cannot remain deterministic across schema migration
- role policy becomes a second mutable authority
- project adapters must reinterpret core state names
- low-risk adoption is not simpler than existing hand-assembled governance
- direct Manna lifecycle actions can manufacture semantic admission
- an A3-shaped shared semantic error becomes automatically accepted

The defensible end state is wrong if no two independent non-Manna consumers emerge.

### Residual risk

**Mechanically preventable:**

- illegal state transitions
- stale base or head
- wrong authenticated role
- self-admission where forbidden
- overwritten attempt history
- blocker release without the declared receipt
- derived-view drift
- hidden declared denominator mutation
- partial and competing writes

**Detectable but not always preventable:**

- direct off-protocol work
- manual canonical file edits
- unauthorized view publication
- use of obsolete attempts
- policy downgrade
- omission of required receipt fields
- local tampering by an actor who does not control every trust anchor

**Semantic uncertainty:**

- a perfectly consistent but wrong controlling requirement
- reviewer error or shared framing
- an inappropriate denominator
- incomplete evidence
- ambiguous interpretation
- competing defensible judgments

**Authority that remains human:**

- constitutional meaning
- appointment of authorities
- risk exceptions
- admission where evidence requires judgment
- ratification
- final gate decisions under unresolved semantics

No hash, schema, replay, model, or signature can prove truth, wisdom, completeness, reviewer independence of mind, or rightful human authority. The protocol can make claims explicit, transitions bounded, and misconduct visible. It cannot replace judgment.

## 21. Evidence Ledger

All repository citations point to the frozen evidence tree, never the later live checkouts.

### Snapshot and claim receipts

- **S1:** "manifest.json:1-31", method, timestamps, auxiliary mirror, agent-do head.
- **S2:** "manifest.json:20-40", agent-do archive, bundle, head, tree and overlay hashes.
- **S3:** "manifest.json:274-353", Stage 0 ancestry, subjects, and trailers.
- **S4:** "manifest.json:355-450", agent-do status before and after.
- **S5:** "manifest.json:579-805", Aldebaran head and verified relevant overlay.
- **S6:** "manifest.json:803-1107", Aldebaran dirty and excluded inventory.
- **S7:** "manifest.json:1371-1385", clean Orient snapshot.
- **S8:** "manifest.json:1387-1418", Theta snapshot and verified ".gitignore".
- **S9:** "manifest.json:1421-1422", superseded candidate and verified final snapshot.
- **E15:** "agent-do working-overlay:.manna/issues.jsonl:111", existing claim and sealed handoff pointer.
- **E16:** "agent-do working-overlay:.handoff/mn-cbaf37-research-audit-landed-stage-0-and-adjudicate-the-missing-provena.md:1-21", current authority and supersession.

### agent-do

- **E1:** "agent-do:AGENTS.md:9-14", source priority.
- **E2:** "agent-do:tools/agent-manna/src/issue.rs:7-64,144-213,253-443", identity, statuses, ownership, blockers.
- **E3:** "agent-do:tools/agent-manna/src/store.rs:184-258,381-404,565-637", permissive loader and rewrite defect.
- **E4:** "agent-do:tools/agent-manna/src/store.rs:260-456", board locking, atomic replacement, checked transitions.
- **E5:** "agent-do:tools/agent-manna/src/workflow.rs:1-172,355-615,1393-1499", canonical roots, paths, identity, binding, authentication.
- **E6:** "agent-do:tools/agent-manna/src/workflow.rs:1606-2007,2442-2490", machine key, runtime identity, handoff validation, journal authentication.
- **E7:** "agent-do:tools/agent-manna/src/workflow.rs:2760-3178,4026-4470", initialization, recovery, presentation transactions, sealing.
- **E8:** "agent-do:tools/agent-manna/src/workflow.rs:5182-5362", strict migration and initialization entry.
- **E9:** "agent-do:tools/agent-manna/src/main.rs:695-728,1139-1159,1810-1873", permissive workflow loading, unblock, lint.
- **E10:** "agent-do:tools/agent-manna/src/store.rs:983-1004; tools/agent-manna/src/workflow.rs:6268-6279; tools/agent-manna/test/integration.sh:855-1059", checked-in tests.
- **E11:** "agent-do:agent-do:208-286,368-412; lib/telemetry.py:103-121", dispatch paths and telemetry.
- **E12:** "agent-do:lib/contracts_audit.py:1-168", bounded behavioral audit.
- **E13:** "agent-do:tools/agent-coord:602-751,1542-1616,2184-2209", advisory coordination.
- **E14:** "agent-do:registry.yaml:494-571,3526-3544,3813-3848", existing tool families.
- **E17:** "agent-do:CONTRIBUTING.md:43-50", taxonomy gate.

### Moon Two

- **M1:** "aldebaran-group:MOON-TWO-PLAN.md:502-630,652-796", authority, immutable attempts, review, red gates, denominators.
- **M2:** "aldebaran-group:moon-two/WORKER-LAW.md:3-48", worker submission and correction law.
- **M3:** "aldebaran-group:moon-two/templates/WORK-ORDER.md:1-50; RETURN.md:1-39; REVIEW.md:1-23".
- **M4:** "aldebaran-group:moon-two/reviews/mn-687319-a3-pro-confirmation.md:1-78", byte agreement and semantic failure.
- **M5:** "aldebaran-group:moon-two/receipts/phase1/PHASE-ONE-DECISION-CARD-A3.md:13-86", wrong sequence and red state.
- **M6:** "aldebaran-group:moon-two/receipts/phase1/PHASE-ONE-SYNTHESIS-A3.md:55-117", duplicated wrong order.
- **M7:** "aldebaran-group:moon-two/reviews/mn-687319-a4.md:1-69", corrected attempt, admission, red phase.
- **M8:** "aldebaran-group:moon-two/DECISIONS.md:249-316", accepted evidence, superseded decision, provenance and denominator rulings.
- **M9:** "aldebaran-group:moon-two/CAMPAIGN.md:21-62; OPERATIONS.md:14-25", campaign authority and blocker/gate transitions.
- **M10:** "aldebaran-group:moon-two/control-room/README.md:3-28", derived read-only dashboard law.
- **M11:** "aldebaran-group:moon-two/control-room/server.py:61-102,257-329", inferred state and read-only server.

### Theta and Orient

- **T1:** "theta-indi:constitution/README.md:1-42; PREAMBLE.md:1-25", source and human ratification.
- **T2:** "theta-indi:constitution/principles/consent-data.md:1-31; lockgen.py:1-86", consent lineage and deterministic locks.
- **T3:** "theta-indi:ORCHESTRATOR-REVIEW.md:3-71", recommendation versus human decision.
- **T4:** "theta publication mirror:GOVERNANCE.md:3-22", mirror governance and ratification.
- **O1:** "the-orient:CHARTER.md:8-56; METHOD.md:5-39", ledger, independence, kill tests, blind lanes.
- **O2:** "the-orient:LAUNCHER.md:1-59; .handoffs/README.md:9-44", launch, seats, submission boundary.
- **O3:** "the-orient:reviews/phase1-a4-verification.md:1-30", bounded verification and ratification readiness.
- **O4:** "the-orient:reviews/red-team-mandate.md:1-24,79-158", isolation, frozen package, negative controls.
- **O5:** "the-orient:reviews/red-team-ruling.md:1-31", human admission and denominator correction without rewriting original evidence.

### Frozen evidence locations

- Snapshot manifest: "/Users/erik/.codex/scratch/mn-cbaf37/snapshot-7fa8029bc1c2cc98b2e6b525330ed28e3008ec36b6a3d955c27b2d91dcf8278e/manifest.json"
- agent-do HEAD tree: "/Users/erik/.codex/scratch/mn-cbaf37/snapshot-7fa8029bc1c2cc98b2e6b525330ed28e3008ec36b6a3d955c27b2d91dcf8278e/repositories/agent-do/head"
- agent-do overlay: "/Users/erik/.codex/scratch/mn-cbaf37/snapshot-7fa8029bc1c2cc98b2e6b525330ed28e3008ec36b6a3d955c27b2d91dcf8278e/repositories/agent-do/working-overlay"
- Aldebaran HEAD tree: "/Users/erik/.codex/scratch/mn-cbaf37/snapshot-7fa8029bc1c2cc98b2e6b525330ed28e3008ec36b6a3d955c27b2d91dcf8278e/repositories/aldebaran-group/head"
- Aldebaran overlay: "/Users/erik/.codex/scratch/mn-cbaf37/snapshot-7fa8029bc1c2cc98b2e6b525330ed28e3008ec36b6a3d955c27b2d91dcf8278e/repositories/aldebaran-group/working-overlay"
- Theta HEAD tree: "/Users/erik/.codex/scratch/mn-cbaf37/snapshot-7fa8029bc1c2cc98b2e6b525330ed28e3008ec36b6a3d955c27b2d91dcf8278e/repositories/theta-indi/head"
- Orient HEAD tree: "/Users/erik/.codex/scratch/mn-cbaf37/snapshot-7fa8029bc1c2cc98b2e6b525330ed28e3008ec36b6a3d955c27b2d91dcf8278e/repositories/the-orient/head"
- Theta publication mirror: "/Users/erik/.codex/scratch/mn-cbaf37/snapshot-7fa8029bc1c2cc98b2e6b525330ed28e3008ec36b6a3d955c27b2d91dcf8278e/auxiliary/theta-indi-constitution/head"

### Independent review boundary

This report is the primary review only. It does not simulate an independent adversarial reviewer.

The separate review packet should contain:

1. Snapshot manifest digest "7fa8029b...f8278e"
2. The four frozen repository HEADs and auxiliary Theta mirror HEAD
3. Sealed handoff digest "e23eb44d...b9d0"
4. This report
5. Instructions to reopen frozen evidence and attack citations, loader classification, state transitions, role boundaries, scores, migration claims, and falsifiers
6. An explicit disagreement ledger for Erik

Model assignment does not confer authority. Human acceptance remains separate.

## Completion Status

The required primary research report is complete. The recommendation was not implemented, no follow-on item was filed, and "mn-cbaf37" was not marked done.

## TL;DR

Stage 0 should stay. It already secures the work item, owner, handoff, lifecycle, and repository writes, but it has one real bug: malformed board rows can be silently dropped during some rewrites. Fix that first. Then build a small opt-in Manna event log that separately records authorization, attempts, review, evidence admission, verdicts, ratification, and gates. Moon Two’s A3 failure proves why this matters: every hash and document agreed, but the meaning was still wrong. The report is complete, nothing was implemented, and the item remains open for Erik’s acceptance.
