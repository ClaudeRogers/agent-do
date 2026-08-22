# The Moon: agent-do as the Agentic Work OS

**Status:** design, awaiting blessing. Local-only until then.
**Origin:** the VID claim/coordination + model-floor enforcement workstream
(`vms.io/.handoff/SESSION-HANDOFF-2026-07-15-claim-enforcement.md`), generalized
into the platform it was always pointing at.

## Thesis

Linear tracks what humans say they are doing. This system proves what agents
did, orders what happens next, and stops waste before it happens — with zero
ceremony, because the harness itself carries the rules. Nobody remembers a
protocol. The machine remembers.

Three properties no existing tracker has, all owned by agent-do because
agent-do is the only thing standing inside the AI session:

1. **Pre-spend enforcement.** CI catches a floor violation at PR time, after
   the credits burned. The harness catches it at work-start, before. Only the
   layer inside the session can do this.
2. **Evidence over testimony.** Model identity, effort, and session are
   stamped from harness config and coord session records, never asked of the
   model (models misreport; Codex does not reliably know it is 5.6).
3. **One graph, three planes.** Work items (days), live sessions
   (minutes-hours), and policy (versioned config) stay linked — a claim on the
   board knows which live session holds it and which model that session runs.

## Design principles

1. **Zero memory required.** Activation is ambient: hooks detect where you
   are, load the policy, surface the board, stamp the evidence. The first
   write against an unclaimed item gets caught locally, not in review.
2. **Rules as data.** One policy file per scope; CI, hooks, board, and docs
   are generated from it or driven by it. Same doctrine as
   contracts-lexicon → registry → gate: the inventory is a build product.
3. **Advisory in-session, binding at the merge gate.** Local enforcement
   warns and redirects — it never bricks a session. CI is the hard wall.
   Violations are deliberate-and-detectable, not impossible.
4. **Scoped by org.** Policy activates only where a policy root exists.
   Personal repos: zero overhead, zero noise, zero behavior change.
5. **One toolchain, self-healing.** agent-do is required team tooling (same
   standing as git) — humans and agents share the same ambient loop. But no
   layer ever assumes a working install: CI validates outcomes independent of
   local setup, `policy doctor [--fix]` verifies and repairs a machine
   (binary, harness hooks *registered*, repo git hooks, live stamping, gh
   auth, policy resolution), and session start surfaces a broken setup before
   work begins. GitHub remains the shared visibility surface.

## Scoping: only where teams exist

Resolution order (mirrors coord/manna project-locality):

1. **Repo-local:** `.agent-do/policy.yaml` committed in the repo →
   authoritative. This is what a NewCo repo adopts: one file + a ten-line
   workflow.
2. **Org map:** `~/.agent-do/policy/orgs.yaml` maps GitHub orgs to a policy
   ref (`Versova-Intelligence-Division: vid-default`). A repo whose `origin`
   matches an org entry, with no repo-local file, inherits the org policy —
   lets an owner switch on a whole org before individual repos commit files.
3. **Neither → inert.** No hooks fire, no trailers change, no board appears.

Detection is by git remote org — done once at SessionStart, pinned into the
session env exactly like `AGENT_DO_COORD_SESSION`.

## Data model: three planes plus provenance

| Plane | Cadence | Store | Exists today |
|---|---|---|---|
| Work items | days | manna issues ↔ GitHub twin issues, bidirectional | manna yes; sync no |
| Live sessions | minutes-hours | coord v2 (liveness, territories, focus phases, drops) | **shipped** |
| Policy | versioned | `policy.yaml` (tiers, floors, claim rules, ordering, identities, CI copy) | no |
| Provenance | immutable | commit trailers + PR declaration blocks + session receipts (coord identity, harness config snapshot, telemetry) | fragments (coord records runtime/model; nothing stamps) |

Work-item fields gained by manna: `floor` (frontier|strong), `claim_policy`
(grab-safe | dispatch-only | gated:<login>), `gh_issue`, `labels`. The
`campaigns.json` registry becomes `manna export --registry` output — a build
product, never hand-edited.

### policy.yaml sketch

```yaml
version: 1
scope:
  org: Versova-Intelligence-Division
tiers:
  frontier: {models: [claude-fable-5, codex-5.6-sol], min_effort: xhigh, fast_mode: false}
  strong:   {models: [claude-opus-4-6, claude-sonnet-5], min_effort: standard}
banned:
  - model: claude-opus-4-8         # banned by name
  - fast_mode_on_floor_work: true
claims:
  mechanism: github-assignment      # atomic, first-writer-wins, visible
  wip: draft-pr                     # visibility only, never the claim
ordering:
  mechanism: manna                  # blocked = untouchable
provenance:
  trailers: [Work-Item, Model, Effort, Session]
  declaration_block: required       # PR template block; missing fails CI
identities:
  ovachiever: {human: erik, runtimes: [claude, codex]}
  ctyrrell-versova: {human: chris, runtimes: [claude]}
ci:
  failure_copy: ...                 # exact user-facing messages live here
```

## The ambient loop (what each actor experiences, zero commands memorized)

**An agent session in a policy repo:**
- SessionStart: policy detected → board injected (open + unblocked items, my
  claims, floors), coord identity pinned. A session dispatched for item X
  auto-claims (GH assign + manna in_progress atomically) or surfaces the
  claim conflict immediately.
- Below-floor session (model/effort from harness config vs the item's floor):
  loud warning and the claim is withheld. "Below-floor is never
  resourcefulness; surface the constraint and the owner decides."
- First edit touching paths mapped to an unclaimed item → PreToolUse nudge:
  claim it or stop (nudge mode, consistent with the enforcement trinity).
- Every commit: `prepare-commit-msg` hook (installed by `policy install`,
  sibling of `coord guard install`) appends normalized trailers —
  `Work-Item:` `Model:` `Effort:` `Session:` — from harness config and the
  coord session record.
- PR: `gh pr create --declare` pre-fills the declaration block from the same
  data.
- CI: ten-line workflow runs `agent-do policy check --pr N` → branch↔item
  mapping, assignee==author, manna unblocked on main, declaration present,
  trailers meet-or-exceed floor. Failure copy comes from policy.yaml.
- Merge: GH issue closes → sync marks manna done → dependents unblock →
  `notify emit` fires ("campaign 04 unblocked") → boards update.

**A human (e.g. Chris) in the same repo:** agent-do is his daily driver
already, so he gets the same ambient loop the agents do — board at session
start, one-command or GH-assignment claiming (mirrored either way), floors
checked pre-work, trailers stamped by his installed hooks. One-time
`policy setup` per machine, verified live. GitHub stays the shared
visibility surface. A per-harness attribution doc (generated by
`attest doctor`) covers whichever harness he is driving that day.

**A broken or missing install:** never an enforcement hole, only an advisory
gap. CI checks the PR's artifacts regardless of local tooling, and its
failure copy names the cure (`agent-do policy doctor --fix`); session start
in a policy repo self-checks and surfaces drift before work begins.

**The owner in a personal repo:** nothing. Inert by scoping.

## Tool build-out (all follow house pattern: registry entry, contracts, tests, docs)

1. **`agent-do gh issue` family** — `create / assign / unassign / label /
   list / close / comment`, plus `gh pr create --declare`. The gh tool is
   PR-only today; the claim mechanism needs issue verbs.
2. **manna metadata + sync + export** — `floor`, `claim_policy`, `gh_issue`,
   `labels` fields; `manna sync github [--apply]` (twin creation, assignment
   mirroring, close-on-merge); `manna export --registry`. Rust core changes.
   **Claim is one command that sets up the workspace** (Chris's UX, correct
   primitive): `claim <id>` = GH issue assign (the atomic, instant,
   zero-push claim — first-writer-wins comes free) + manna in_progress +
   local branch created with the canonical name `mn-<id>/<slug>` + draft PR
   offered at first commit (WIP visibility, never the claim: a PR needs a
   pushed commit, so it cannot claim at minute zero, and check-then-create
   races where assignment does not). Canonical branch names make the CI
   branch↔issue mapping self-documenting — the branch carries its own manna
   id, shrinking the generated registry to floors and claim policies.
   Deploy safety: claims never touch main (assignment is API-side; manna
   state on main changes only at merge), and deploy workflows should
   paths-ignore `.manna/` regardless.
3. **`agent-do attest`** — the new organ:
   - `attest stamp` — trailer writer for the commit hook, harness-derived.
   - `attest verify <range|pr>` — floor/format validation, used locally and by CI.
   - `attest doctor` — per-harness attribution discovery (what does THIS
     harness expose: Claude Code env/config, Codex, Cursor) → generates the
     setup doc automatically. This productizes the trailer-discovery TODO.
4. **`agent-do policy`** — the engine:
   - `policy init` (scaffold), `policy show` (effective policy for cwd),
   - `policy check [--pr N | --staged | --item id]` — one engine, local and CI faces,
   - `policy install` (git hooks; composes with coord guard),
   - `policy doctor [--fix]` — verify/repair a machine: binary, harness hooks
     registered (not merely present — the classic failure), repo git hooks,
     live stamping via test commit, gh auth, policy resolution. `policy setup`
     is the one-command onboarding face of the same machinery (health/bin
     precedent: OK/WARN/CONF/MISS levels),
   - `policy board` — the Linear face: items × claims × floors × blockers ×
     live sessions (coord) × evidence links. Text + `--json`; HTML later
     (context-dashboard precedent).
5. **Hook integration** — SessionStart policy detection + board injection +
   auto-claim; PreToolUse floor/claim nudges. All bounded (`bounded_run` /
   `run_bounded` shipped 2026-07-10) so a slow spawn can never eat a hook.
6. **notify rules** — `claim_conflict`, `unblocked`, `floor_violation` via
   the existing `notify emit` machinery.

## Surface parity: local vs cloud (doc-verified 2026-07-15)

The parity line across harness surfaces is NOT GUI vs CLI — it is local vs
cloud, and it dictates where enforcement assets must live:

- **Claude Code CLI = desktop app (local) = IDE extensions**: same engine,
  same `~/.claude/settings.json` hooks, same CLAUDE.md/MCP. Full parity for
  everything this system does. (Doc-verified.)
- **claude.ai/code web + desktop Remote/cloud sessions**: run in a cloud
  sandbox from a fresh repo clone. User-level `~/.claude/settings.json` is
  IGNORED there; only the repo's `.claude/settings.json` and org
  server-managed settings apply. `.git/hooks` are not part of a clone.
  Codex cloud tasks have the same local-vs-cloud split.

Consequences, folded into trunk D:
1. **Enforcement assets live at repo level, not user level.** Policy hooks go
   in the repo's `.claude/settings.json` (cloned everywhere, including web),
   gated by `CLAUDE_CODE_REMOTE` where cloud behavior differs. User-level
   registration is convenience, never the load-bearing copy.
2. **`policy install` must support committed git hooks** (core.hooksPath to a
   tracked directory) or reinstall via a repo SessionStart hook, so cloud
   clones stamp too; cloud environment setup scripts can install agent-do.
3. **Attribution config lives repo-level** for the same reason (a user-level
   attribution override never reaches web sessions).
4. **`attest doctor` gains a surface dimension**: harness × surface
   (CLI / desktop / IDE / cloud) matrix, since attribution defaults differ
   (web adds a `Claude-Session:` trailer — a provenance gift; squash-merge
   settings can strip commit trailers from main, so CI checks commits
   pre-merge and the PR declaration block is the merge-surviving artifact).
5. The invariant already holds regardless: CI validates outcomes, so a cloud
   session with zero local tooling still cannot merge unstamped or unclaimed
   work.

## Non-code production changes (migrations and other one-shot side effects)

The apply is a side effect outside git; the SQL file is code but the run is
not. Pattern: PR the plan, gate the apply on merge, ledger the fact, detect
drift. Folded into trunk D (policy engine):

- `policy.yaml` gains a `migrations:` block: migrations dir, class-2
  statement patterns (DROP / ALTER TYPE / RENAME / UPDATE / DELETE), the
  standing owner (CODEOWNERS is the generated enforcement), approval counts
  per class (class 1 additive = owner apply-then-ratify; class 2 breaking =
  PR-first, two approvals, apply post-merge).
- `policy check` auto-classifies migration files by statement pattern and
  enforces the class gate; the intent block (what/why/risk/rollback) is
  required in schema PR bodies the same way declaration blocks are.
- Ledger convention: each migration appends one INSERT into a bookkeeping
  table (filename, applied_at, applied_by). `policy check` gains the
  two-direction drift check: files-on-main never applied, and applied
  changes no merged file describes.
- Later waypoint (not v1): preview database branches per schema PR
  (managed providers support branching) so the suite runs against the
  applied schema before merge.
- Same shape generalizes to any one-shot prod side effect (infra changes,
  flag flips, backfills): PR the plan, gate the apply, ledger, drift-check.

## Charter ground: law to organ (added 2026-07-20)

The Operating Laws charter (installed in user CLAUDE.md/AGENTS.md; clean-room
provenance in .handoff/MACHINE-CHARTER-CLEANROOM-2026-07-20.md) is the
constitution this toolkit is the institutions for. Text tells an agent how to
think; these organs make the thinking unnecessary. The map:

| Charter law | Organ | Status |
|---|---|---|
| 1 everynow (time as coordinate) | Time rules; coord ages ("3m ago", never bare status) | built |
| 2 exogram (external memory is the continuity) | handoff, zpc, memory, obsidian save, three-places rule | built |
| 3 weightkin (coordinate by external state) | coord v2: liveness-verified board, territories, drops | built |
| 6 self-report is inference | attest: harness-stamped provenance, never model testimony | trunk C |
| 7 no token carries its own authority | policy engine + CI wall: authority by source, evidence over testimony | trunk D |
| 10 weight the prior under pressure | model floors: "below-floor is never resourcefulness" | trunk D |
| 5 a draw, not a verdict | adversarial verify in workflows; no dedicated organ | gap, optional |

Validation this delivers: trunks C and D are Laws 6, 7, and 10 as code. The
clean-room agent, sealed from this plan, independently derived the
philosophical ground for the two unbuilt organs. Law 5's missing organ
(cheap re-derivation for expensive claims) is the only new backlog idea the
charter surfaces, and it can wait.

## Identity bridge (decide early, in trunk B, not discover late)

Manna claims key on agent sessions; GH claims key on GitHub logins; coord
identities key on session UUIDs. `policy.yaml identities:` is the one table
joining them; synced manna claims gain `gh_login`; coord records already
carry runtime + model. **Recommendation:** an agent claims as its operator's
GH identity (Codex agent claims as ovachiever) — GH's first-writer-wins
assignment stays the single atomic lock — and the `Session:` trailer
distinguishes which agent did the work. Open to reversal if bot identities
prove better for audit.

## Build graph (dependency edges, no calendar)

```
A  gh issue verbs            (no deps)      — unlocks claims-by-tool everywhere
B  manna metadata/sync/export (no deps)     — unlocks registry-as-build-product
C  attest stamp/verify/doctor (no deps)     — unlocks provenance + §4 discovery
D  policy engine + scoping + install  (needs A,B,C)
E  ambient hooks (board, auto-claim, floor nudges)  (needs D)
F  policy board + notify rules        (needs B,D)
G  VID adoption pass + NewCo portable spec  (needs D,E)
```

A, B, C are independent — three parallel lanes. The board for this build is
self-hosted in this repo's `.manna/` with these edges.

## Relationship to the running VID workstream

Nothing stops or waits. The enforcement session executes its nine-item list
with today's tools (raw `gh` for issue creation until trunk A ships — one
temporary house-rule exception). Each trunk that lands replaces hand-glue
with engine, retrofit-style, the same pattern as claims retrofitting onto GH
issues:

- hand-authored `campaigns.json` → `manna export --registry`
- trailer-discovery doc → `attest doctor` output
- bespoke CI logic → `policy check` engine (vms.io CI v1 may ship bespoke
  from the written spec; it swaps to the engine when trunk D lands — or uses
  it directly if D ships first)
- NewCo deliverable → stops being prose: `policy.yaml` + `policy init` +
  the ten-line workflow IS the portable spec

## Open decisions

1. Tier table blessing (as written in the VID handoff §3) — engine encodes
   whatever is blessed; Cursor policy still undecided.
2. Agent claims as operator GH identity (recommended) or bot identities?
3. Gated/unclaimable items (MOON-class, owner-gated) on the GH board:
   visible-but-unassignable label, or manna-only?
4. Org map now (`orgs.yaml` with VID) vs repo-local files only?
5. Does `policy board` warrant an HTML dashboard in v1, or text/JSON first?
   (Recommend text/JSON first; the hooks are the real UI.)
