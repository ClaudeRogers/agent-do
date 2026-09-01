# agent-do Contracts: operationalizing the five-beat rhythm

**Author:** Claude Opus 4.7 (1M context) for Erik Fritsch. For Codex review before adoption.
**Status:** Design proposal. Not implementation. The goal is to make a principle that already lives in the README into a machine-readable contract every tool declares and the audit grades against.

---

## 0. TL;DR

The README already states agent-do's core mental model:

> Connect -> Snapshot -> Interact -> Verify -> Save

Right now that's prose. It isn't enforced anywhere, it isn't declared per tool, the registry doesn't know about it, the routing layer doesn't use it, and the audit can't grade against it. As agent-do grows (now ~90 tools, with new ones arriving), every new tool ends up at "another tool at the top," with verbs invented per-tool, and the namespace flattens out into 90 unrelated surfaces.

**The proposal**: the five beats are contracts. Every tool declares which beats it implements and which of its commands belong to each beat. The registry validates the declaration. The agent's routing layer uses contracts to map intent. The audit grades each tool on whether its declared contracts honor their required shape. New tools cannot be merged without a contract declaration.

This collapses the proposed storage / action / writer / sync taxonomies (and any future re-inventions) back into the principle that already exists.

---

## 1. The five contracts

Each beat is a contract family. A tool implements one or more. Each contract has a required shape that the audit enforces.

### 1.1 Connect

**Purpose**: bring a tool into a usable state for subsequent commands.

**Required shape**:
- Takes the minimum input to identify the target (URL, db name, simulator id, session name, vault path, etc.).
- Returns a session id, attachment id, or pass/fail with a clear reason.
- Idempotent: calling connect twice on the same target is a no-op.
- Exit code 2 if input is ambiguous and clarification is needed.

**Examples**:
- `agent-do browse open <url>`
- `agent-do db connect <name>`
- `agent-do ios boot`
- `agent-do auth ensure <site>`

Many tools have no Connect beat (e.g., notify, pdf, obsidian). That's fine. The contract is declared as absent.

### 1.2 Snapshot

**Purpose**: show the current state of the world this tool sees, in a structured form the agent can reason from.

**Required shape**:
- Returns JSON when `--json` is set (the default for agent calls).
- Captures *enough* state for the agent to decide its next action without re-querying.
- Read-only. No side effects on the world or on agent-do's own storage.
- Stable schema across calls: snapshot v1 of the same state returns the same JSON shape.

This is the universal contract. Every mature tool should implement it. If a tool can't be snapshotted, the agent can't reason about it without acting blind.

**Examples**:
- `agent-do browse snapshot -i` (interactive elements with @refs)
- `agent-do db snapshot` (schema + connections)
- `agent-do context retrieve "<query>"` (matching content with provenance)
- `agent-do gh awaiting` (PR work-state)
- `agent-do harness inspect --json` (whole-system inventory)

### 1.3 Interact

**Purpose**: change state somewhere.

**Required shape**:
- Side-effectful. Mutates the world, the agent's state, or both.
- Reports what changed in JSON when `--json` is set.
- Atomic where possible: either the interaction completes or the system stays in its prior state.
- Exit code 2 if the requested change is ambiguous.

**Examples**:
- `agent-do browse click @e3`
- `agent-do db query "INSERT ..."`
- `agent-do gh merge <pr>`
- `agent-do render deploy <service>`
- `agent-do api scaffold anthropic --target ./lib/llm.py` (writes a file)
- `agent-do api save anthropic --from ./lib/llm.py` (writes to storage)

### 1.4 Verify

**Purpose**: confirm that an interaction reached the desired state.

**Required shape**:
- Reads state without changing it. (Even though Snapshot also reads, Verify is the narrower contract: "wait/check until X is true, or fail.")
- Returns pass/fail with reason.
- Either blocks until satisfied, exits on timeout, or returns immediately with current status (caller-controlled).

**Examples**:
- `agent-do browse wait --stable`
- `agent-do dpt score <screenshot>` (verifies UI quality)
- `agent-do context docs drift <name>` (verifies internal-doc consistency)
- `agent-do render logs <service>` (when used to verify deploy success)

### 1.5 Save

**Purpose**: persist a result so future sessions can find it.

**Required shape**:
- Writes to a known durable location (filesystem, OS keychain, DB, vault).
- Atomic write: never leaves partial files.
- Records provenance (when, by what session, from what source).
- Idempotent on identical input.

**Examples**:
- `agent-do browse session save <name>`
- `agent-do context lessons learn ...` (saves a lesson)
- `agent-do context ledger append <ledger> --section ...`
- `agent-do obsidian write <content>` (writes to vault with frontmatter)
- `agent-do creds store <key>` (OS keychain write)
- `agent-do pdf <input>` (writes a PDF)

Note: Save is distinct from Interact even when both write to disk. Save is about *persistence of a result*; Interact is about *changing state in the world*. `api save` writes a template (Save); `api scaffold` writes a project file (Interact). The verb name matches the contract.

---

## 2. The `contracts:` block in `registry.yaml`

Every tool declares its contracts. Schema:

```yaml
tools:
  browse:
    description: AI-first headless browser automation
    concurrency: mixed
    contracts:
      connect:
        - open                 # agent-do browse open <url>
        - login                # agent-do browse login <url>
      snapshot:
        - snapshot             # primary
        - screenshot           # alternate: visual snapshot
      interact:
        - click
        - fill
        - type
        - press
        - hover
        - check
        - select
        - upload
      verify:
        - wait
      save:
        - session save
        - capture stop
```

Two things this codifies:

1. **The tool declares which beats it implements.** Absent beats are absent. An audit can read this and check claims.
2. **For each beat, the tool lists the subcommand verbs that belong to it.** This is what the routing layer uses: when the agent's intent maps to "snapshot," the router knows `browse snapshot` is one valid target.

Compact form for small tools:

```yaml
tools:
  obsidian:
    contracts:
      save: [write]
```

That's the whole declaration. Obsidian is a Save-only tool. No Connect, no Snapshot, no Interact, no Verify.

---

## 3. Routing layer uses contracts

Today's `routing.prompt_patterns` and `discover_keywords` map prompts to tools. Add a second layer: map prompts to contract intents.

```yaml
tools:
  browse:
    routing:
      intents:
        connect:  ["open the browser to", "navigate to", "go to <url>"]
        snapshot: ["what's on the page", "show me the page", "list interactive elements"]
        interact: ["click", "fill", "type", "select"]
        verify:   ["wait for", "is it loaded", "did it settle"]
        save:     ["save this session", "remember this auth", "stop capturing"]
```

The prompt-router resolves in two passes:

1. Pick the contract intent that matches the prompt (snapshot, interact, save, etc.).
2. Within that intent, pick the tool whose `intents.<beat>` patterns match.

This is more robust than today's flat keyword match because the intent is named. "Wait for it to settle" routes to verify; "show me the page" routes to snapshot; both are clearly different even if they share words with other tools.

---

## 4. Audit grades against contracts

The agentic-first audit (planned in the v2 handoff) collapses to: **does each declared contract honor its required shape?**

Per-tool grading becomes per-contract grading:

| Contract | Pass requires | Common failure mode |
|---|---|---|
| Connect | idempotent, clear input, exit 2 on ambiguity | not idempotent (re-connect changes session id) |
| Snapshot | `--json`, read-only, stable schema | mutates state during snapshot, prose-only output |
| Interact | atomic, reports change, exit 2 on ambiguity | partial writes, silent failure |
| Verify | read-only, clear pass/fail | conflates with snapshot |
| Save | atomic, durable, provenance recorded | overwrites without backup, no provenance |

Overall tool grade is the lowest grade across declared contracts. If a tool claims Snapshot but doesn't return JSON, it fails Snapshot, and the tool fails overall.

This replaces the seven hand-wavy criteria from the v2 audit with five contract-specific tests. Every test is mechanical (script-checkable) except the "stable schema" and "atomic" ones, which need light human/agent review.

---

## 5. Worked examples

Showing how representative tools declare their contracts and what their grade-relevant verbs look like.

### `browse`

```yaml
contracts:
  connect:  [open, login]
  snapshot: [snapshot, screenshot]
  interact: [click, fill, type, press, hover, check, select, upload, viewport]
  verify:   [wait]
  save:     [session save, capture stop]
```

Full five-beat tool. Mature.

### `api` (new)

```yaml
contracts:
  snapshot: [list, show]
  interact: [scaffold, save]
```

Two beats. Templates are Snapshot/Save shaped; scaffold writes into a project (Interact); `save` writes a template canonical (also Interact, because it changes durable state on the agent-do side). No Connect (no session), no Verify (out of scope for v1).

### `obsidian`

```yaml
contracts:
  save: [write]
```

One beat. Writer-only adapter. Knows vault path + frontmatter conventions; writes one file per call.

### `context`

```yaml
contracts:
  snapshot: [retrieve, list, get, search, sources, status]
  interact: [add-source, fetch, fetch-llms, fetch-repo, sync, refresh, maintain]
  save:     [annotate, feedback]
```

Three beats. No Connect (stateless). No Verify (per-source freshness is part of Snapshot's provenance metadata).

### `gh`

```yaml
contracts:
  snapshot: [inbox, awaiting, prs, pr, diff, threads, checks]
  interact: [review, approve, request-changes, comment, merge, ready, draft, checkout, edit, update-branch]
  verify:   [audit]
  save:     []  # writes happen via Interact verbs; nothing separately saved
```

### `manna`

```yaml
contracts:
  snapshot: [list, show, status, context]
  interact: [create, claim, abandon, block, unblock, done]
  save:     []  # writes are part of Interact; no separate Save verb
```

### `render`

```yaml
contracts:
  connect:  []  # uses creds, no separate connect
  snapshot: [services, deploys, logs, env, status]
  interact: [deploy, restart, env-set, env-unset]
  verify:   [logs --since, status]
  save:     []
```

`logs --since` does double duty (Snapshot in general; Verify when used right after a deploy). Acceptable: a single verb can belong to multiple beats if context decides which.

### `db`

```yaml
contracts:
  connect:  [connect, disconnect]
  snapshot: [snapshot, schema, query]
  interact: [query]  # when query is INSERT/UPDATE/DELETE
  verify:   []
  save:     []
```

Mixed `query`: SELECT is Snapshot, mutating queries are Interact. The contract block records both; concurrency stays `mixed`.

### `dpt`

```yaml
contracts:
  snapshot: [scan, report]
  verify:   [score, diff, baseline, violations]
```

Pure read tool. All verify work.

---

## 6. Implementation phases

### Phase A: Inventory (no code changes yet)

Walk every tool in `registry.yaml`. For each, propose its `contracts:` block based on existing commands. Produce `.handoff/contracts-inventory.md` with one section per tool: declared block + notes on ambiguous verbs.

Deliverable: a draft contracts declaration for all ~90 tools. Reviewed by Erik before any code changes land.

### Phase B: Declare

Add `contracts:` blocks to `registry.yaml` for every tool. No behavioral changes yet.

Audit check at this stage: every tool has a `contracts` block; every listed verb actually exists in the tool's commands; no verb is listed under two beats unless the tool deliberately overloads it (with a note).

### Phase C: Validate

Extend `agent-do harness inspect --json` to validate contract claims:

- For every claimed Snapshot verb, call it with `--json` and check the response parses as JSON.
- For every claimed Save verb, dry-run it and check it reports a writable destination.
- For every claimed Connect verb, call it twice and check idempotence (or that the verb declares it can't be idempotent and why).
- For every claimed Verify verb, check it's read-only by inspecting that no FS/network state changes between two invocations.

Most of this can be light. Hard checks where they're cheap; soft warnings where they're not.

### Phase D: Integrate routing

Add `routing.intents:` block as defined in §3. Update `bin/intent-router` and `hooks/agent-do-prompt-router.py` to use intents as the first-level routing dimension. Existing `prompt_patterns` and `discover_keywords` stay as fallback.

### Phase E: Audit (the agentic-first audit, contract-shaped)

Now the audit is mechanical. Run the validators from Phase C across all 90 tools. Output `.handoff/contracts-audit.md` grading each tool per contract. Top systemic gaps surface naturally.

### Phase F: New-tool rule

Add to `AGENTS.md` / `CLAUDE.md`: any new tool added to `tools/` must declare `contracts:` in its registry entry. Pre-merge check runs Phase C validators. No tool ships without contracts.

---

## 7. What this gives us

1. **A line that doesn't bend.** Storage, action, writer, sync, snapshot, retrieval are not new categories. They're folded into the existing five beats. Future "new categories" get the same treatment.
2. **Routing gets smarter.** Intents route on what the agent *means*, not just keyword overlap. "Wait for it to settle," "save this," "show me the state," "merge this" each match a contract, not a tool name.
3. **The audit gets mechanical.** Most contract checks are scriptable. The Erik test from the v2 audit becomes: does each contract intent route to the right tool for 3+ realistic prompts.
4. **New tools have a shape.** Any new tool comes with a contract declaration. The reviewer asks: "what beats does this implement, and does each beat honor its required shape?"
5. **The principle that's been in the README all along finally has teeth.** Connect → Snapshot → Interact → Verify → Save was descriptive prose; this proposal makes it the structural contract.

---

## 8. Done criteria

1. `.handoff/contracts-inventory.md` exists with proposed declarations for all 90 tools.
2. `registry.yaml` has a `contracts:` block on every tool.
3. `agent-do harness inspect --json` validates contracts and reports per-tool conformance.
4. `routing.intents:` blocks added; `bin/intent-router` uses intents as first-level routing dimension.
5. `.handoff/contracts-audit.md` exists with per-contract grades for every tool.
6. `AGENTS.md` updated with the new-tool rule.
7. `README.md` updated: the Mental Model section explicitly names the five contracts as the agent-do convention every tool follows.
8. `./test.sh` passes throughout; new tests cover the validators.

---

## 9. Open design questions for Codex review

1. **Verb overlap across beats.** `query` in `db` is Snapshot for SELECT, Interact for mutations. `logs` in `render` is Snapshot in general, Verify after a deploy. Should the contract block list these explicitly under both beats, or should the runtime decide per call? My instinct: list under both, with a `disambiguator` field if needed.
2. **Connect for stateless tools.** Tools that use `creds` and have no session of their own (render, vercel, supabase) currently have no Connect verb. Should Connect be implicit ("creds-resolved" counts), or simply absent from the contracts declaration? My instinct: absent. Connect is for tools with explicit sessions.
3. **Concurrency vs contracts.** The existing `concurrency: read|write|mixed` is orthogonal to the contracts but related. Should concurrency derive from contracts (Snapshot/Verify are read; Connect/Interact/Save are write/mixed), or stay independent? My instinct: stay independent. They answer different questions.
4. **The `routing.intents:` migration.** Existing `prompt_patterns` and `discover_keywords` overlap with the new intents block. Keep all three (intents primary, others fallback)? Migrate everything into intents? My instinct: keep all three short-term, deprecate `prompt_patterns` once intents prove out.
5. **Phase ordering.** Is the A → F sequence right, or should Phase D (routing integration) happen before Phase E (audit) so the audit can use intent routing in the Erik test? My instinct: D before E. The audit's prompt-routing test depends on intents existing.
6. **Naming.** "Contracts" is the working name. Alternatives: "beats," "primitives," "verbs," "operations." Codex may have a preference based on convention elsewhere in the repo.

---

## 10. What this does NOT propose

This is intentionally scoped. The plan does not:

- Add or remove any top-level tool.
- Rename `agent-do <tool>` invocations. CLI stays flat.
- Force a new namespace level (no `agent-do inner ...` / `agent-do outer ...`).
- Replace the v2 handoff's other deliverables (api build, context redesign). It makes them sharper, but it doesn't supersede them.

It only operationalizes the five-beat principle that's been load-bearing prose in the README and turns it into machine-readable structure the registry, routing, and audit can use.

---

## 11. What changes in the v2 handoff if this lands

1. The agentic-first audit (§6) gets replaced with the contract audit defined above. Same destination, sharper criteria.
2. The api implementation brief (§4) gains a one-line `contracts:` declaration in its registry entry.
3. The context redesign (§3, §5) gets one new piece: every context subtype declares its contracts the same way every tool does.
4. §11 anti-patterns gains one entry: "no new tool merges without a contracts declaration."

Everything else in the v2 handoff stands.

---

## 12. Recommended sequence

If this plan clears Codex review:

1. Phase A (inventory) starts immediately. It's pure read-and-propose; no risk.
2. Phase B (declare) goes in alongside the v2 handoff's context redesign and api build.
3. Phase C (validate) ships with the context redesign Phase A from the v2 handoff.
4. Phase D (routing) ships next.
5. Phase E (audit) replaces the v2 handoff's §6 audit deliverable.
6. Phase F (new-tool rule) lands in AGENTS.md as a hard gate before the audit closes.

Total surface change: contracts blocks across 90 tools, intents blocks across the same set, one harness validator, one audit refactor, one AGENTS.md rule. No new top-level commands. No renames.
