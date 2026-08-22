# Session Handoff (2026-05-15, v2): agent-do API + context redesign + agentic-first audit

**Author:** Claude Opus 4.7 (1M context), authoring this for the next agent that picks up the work in a fresh session. Erik will send this to Codex for review.
**Project:** `agent-do` at `/Users/erik/Custom-Coding/agent-do`.
**Status:** Supersedes `.handoff/SESSION-HANDOFF-2026-05-15.md`. The earlier file is left for record but this is now the authoritative brief.
**Hand-off reason:** A long design conversation surfaced three coupled deliverables. The first (build `agent-do api`) was already in v1. The second (agentic-first audit) was already in v1. The third (context redesign) is new in v2 and is the largest finding from this session: `agent-do context` is currently scoped too narrowly relative to its name, and the right reshape touches `zpc` and the broader memory layer.

---

## 0. TL;DR for the next agent

You have three deliverables, in this order of dependency:

1. **Execute the `agent-do context` redesign** (§3 and §5). Broadens `context` from "external reference docs" to "everything the agent loads to reason from." Adds `context docs` (external + internal), `context ledger` (project chronicles), `context lessons` (folds `zpc`). Cross-subtype retrieval at the top. New primitive is the ledger; rest is restructuring.
2. **Build `agent-do api`** v1 (§4). Should compose with the new context model (its template manifests are a kind of context). Full implementation brief is self-contained.
3. **Run the agentic-first audit** across all 90 tools (§6). The context redesign in (1) is the first pre-identified finding the audit would have surfaced. Audit confirms or refines, then sweeps the rest.

The whole thing rests on one principle. Read §1 and §2 first.

Erik never types `agent-do` commands. Ever. Not for setup, not for capture, not for debugging. Every verb is called by an agent on his behalf. Build and audit accordingly.

---

## 1. The orienting principle (every verb is the agent's)

Quoted verbatim from the conversation that produced this handoff.

> Every verb is the agent's. Including `save`.
>
> The save flow corrected: the agent builds the Anthropic client in your project. You say something in conversation like "lock this in," "make this the standard," "save this pattern," or just "this is how I want it from now on." The agent recognizes the canonicalize signal and calls `agent-do api save anthropic --from ./lib/llm.py` itself. You don't touch the CLI. You don't even know `--from` exists. You told the agent to standardize this version, and the agent did.
>
> Same for every other verb. `refresh` runs when an agent doing maintenance notices the upstream changed. `fork` runs when you say "I want a cached variant of the anthropic template for that worker project." `diff` runs when an agent is reviewing drift before a refresh. None of these have a human-typed entry point. There's no scenario where you would prefer the CLI over telling the agent.
>
> The actual design principle: the human interface is the conversation with the inner-harness agent. The agent-do surface is fully opaque to you. Every command has agent-callable structure (clear exit codes, JSON output, registry-declared routing) and agent-callable triggers (conversational patterns, drift signals, project events).
>
> Registry routing has to cover both ends of the flow. Agent recognizes "I need a Claude client" → scaffold. Agent recognizes "lock this in" / "save this pattern" / "this is the standard" → save. The second set is less obvious and probably the thing that makes or breaks adoption. Most tool layers nail the build-trigger and miss the canonicalize-trigger.

## 2. Erik's deeper framing (the audit principle)

> CLI is the contract because LLMs are trained off human CLI interactions. But agentic AI IS the "human at the CLI." There is no human typing the commands.

What that means in practice:

- The CLI shape is fine. Keep it.
- The CLI is read by the agent now, not the human. The agent is the "user." Everything we'd design for a human user should be reconsidered as design for an agent user.
- A command that's pleasant for a human to type may be miserable for an agent to discover, route to, parse, and verify. A command that's awkward for a human to type may be exactly what the agent needs.
- Most tool layers nail the **build-trigger** ("user wants X built") and miss the **maintain-trigger** ("user said something that means 'this is canonical now' / 'refresh this' / 'fork this for that other project'"). The maintain-trigger is where the agent actually closes the loop.

All three work items below are applications of this principle.

---

## 3. The context redesign (the big finding from this session)

### 3.1 What's wrong with the current shape

`agent-do context` is currently scoped to "external reference docs." It fetches llms.txt and GitHub repos, BM25-indexes them, retrieves bounded snippets with freshness and trust metadata. That's a useful tool, but the name "context" carries a much broader meaning in LLM/agent vocabulary: anything the agent loads into its head to reason from. Under that broader meaning, the current tool covers a slice of what its name implies, and the rest is scattered across `zpc`, hand-rolled project markdown files (`DIVINATION_ARCHIVE.md`, `LEDGER.md`), and ad-hoc memory.

Two real-world examples already exist as evidence of the gap.

| File | Project | Shape |
|---|---|---|
| `DIVINATION_ARCHIVE.md` (~7,400 words, 620 lines) | the-point-revision (novel) | Index table, structured detailed entries, pattern observations. Schema: date, source, density, register, canon links, prose fragments, meta notes. |
| `LEDGER.md` (~5,500 words, 486 lines) | business-plan-builder | Index, documents created, decisions and frameworks, communications drafted, tools created, strategic relationships, voice evolution, YAML status, open loops, cross-references, pattern observations. |

Both files exist because the agent needed a structured catchment that didn't fit reference docs, didn't fit lessons-and-decisions, and didn't fit canonical change specs. Both are append-disciplined. Both mirror to Obsidian. Both serve as the agent's resume point when the conversation compacts. The primitive is real and currently has no tool.

### 3.2 The unified model

Everything the agent loads to reason from is context. Within context, three kinds of provenance:

1. **External authoritative** (upstream docs from a vendor, llms.txt, GitHub repos)
2. **Internal authoritative** (AI-generated repo docs: ARCHITECTURE.md, API_DESIGN.md, AUTH.md, etc.)
3. **Internal accumulating** (project ledgers, append-disciplined, project-defined schema)

One namespace, one search command, three typed surfaces underneath.

### 3.3 The surface

```
agent-do context
├── retrieve <query> [--type docs|ledger|lessons]   # cross-subtype search (default: all)
├── docs
│   ├── add-source --source upstream <url>          # register external upstream
│   ├── add-internal <path>                          # register an internal/AI-authored repo doc (no copy, just index)
│   ├── fetch-llms / fetch-repo / fetch              # current commands
│   ├── sources sync                                 # refresh upstream sources
│   ├── drift <name>                                 # internal-doc consistency vs related code
│   ├── list / get / search
│   └── ...
├── ledger
│   ├── init <name> [--from-template <type>]        # create a ledger, optionally seeded
│   ├── section add <ledger> <section> [--schema k,k,k]
│   ├── append <ledger> --section <s> --fields k=v,...
│   ├── index <ledger>                              # regenerate top-of-file scan table
│   ├── patterns <ledger>                           # surface meta-observations from accumulation
│   ├── xref <ledger> --to <path-or-canon-ref>      # link items to other project files
│   ├── sync <ledger>                               # mirror to Obsidian (or other configured target)
│   └── resume <ledger>                             # generate the agent's session-resume brief
└── lessons                                          # folds zpc; this is `ledger --template lessons` with shortcuts
    ├── learn <ctx> <prob> <sol> <takeaway> [--tags ...]
    ├── decide <problem> --options ... --chosen ... --rationale ...
    ├── harvest                                      # lessons → patterns (was zpc harvest)
    ├── promote <item> --to team|global             # cross-scope promotion
    ├── review --since HEAD~20                       # capture from git history
    └── inject                                       # retrieval with agent-context output format
```

`retrieve` at the top searches across all subtypes by default and can be scoped with `--type`. The agent issues one query and gets snippets from upstream docs AND internal repo docs AND the project ledger AND lessons, ranked together. That's the win.

### 3.4 Storage

```
~/.agent-do/context/
├── docs/                       # global doc cache
│   ├── upstream/<host>/...     # cached external content
│   ├── internal-registry       # paths to in-repo internal docs (not copies; just pointers + metadata)
│   └── meta.db                 # FTS5 + freshness + trust + provenance
├── ledgers/
│   ├── registry                # paths to canonical per-project LEDGER files
│   └── index.db                # central SQLite index across all ledgers, derived from the source files
└── lessons/
    └── (same shape as ledgers; lessons is a templated ledger)

<repo>/LEDGER.md                # canonical per-project ledger file (Obsidian-mirrored)
<repo>/.zpc/                    # back-compat alias path during migration; eventually folds into context lessons
```

**Files are source of truth. The DB is rebuildable.** Same model `agent-do context` already uses for the docs cache and FTS5 index. A ledger that lives at the repo root is a markdown file; it gets indexed centrally so cross-project queries work, but the file is canonical and survives any tooling change.

### 3.5 Templates (the agent-do-native versions of the worked examples)

Ledger templates seed common project types with section names and per-section schemas. The user (= the agent) can edit freely after init.

| Template | Sections | Notable schemas |
|---|---|---|
| `blank` | (empty; agent defines all sections) | none |
| `lessons` | lessons, decisions, patterns | context/problem/solution/takeaway; problem/options/chosen/rationale/confidence |
| `novel-archive` | reads, fragments, patterns | date/source/density/register/canon-links/fragments |
| `business-ledger` | documents, decisions, communications, relationships, open-loops, patterns | varies per section |
| `research-log` | papers, hypotheses, experiments, findings | varies per section |
| `code-decisions` | decisions, refactors, learnings, bug-history, deps | varies per section |

The `lessons` template is `zpc`'s schemas plus its specialized operations (`harvest`, `promote`, `review`, `inject`). Calling `agent-do context lessons learn ...` is sugar for `agent-do context ledger append <project-lessons-ledger> --section lessons --fields ...` with the schema enforced.

### 3.6 What stays separate (not folded into context)

| Tool | Reason it stays separate |
|---|---|
| `manna` | Operational primitive (claims, dependencies, work-state tracking). Different from context-the-agent-loads. |
| `sessions` | Search over raw chat corpus, not curated reference material. Different lifecycle. |
| `spec` | TBD by audit. May fold (canonical change specs ARE structured context with provenance), or may stay (specs are short-lived and tied to active change packages). |
| `coord` | Coordination primitive, not memory. `zpc checkpoint` (swarm compliance check) belongs here, not in lessons. |

### 3.7 Migration of `zpc`

`zpc` folds into `agent-do context lessons`. Migration cuts:

- **Underlying storage**: existing `.zpc/` directories continue to work via a back-compat read path. New writes go through the unified ledger storage at `~/.agent-do/context/lessons/`. A one-time migration command (`agent-do context lessons import-zpc`) lifts old `.zpc/` content into the new shape.
- **Command surface**: `agent-do zpc <verb>` stays as a deprecation alias that internally calls `agent-do context lessons <verb>`. Same args, same exit codes. Agents using either path get the same behavior.
- **Routing keywords**: the registry entry under `lessons` carries forward zpc's discover keywords ("lesson," "learned that," "decision," "we decided," "harvest patterns," etc.) AND adds canonicalize-trigger keywords for ledger-style usage.
- **The `checkpoint` command** moves to `agent-do coord`. It's a swarm coordination operation that happened to live in `zpc`; the audit will confirm.

### 3.8 Done criteria for the context redesign

1. `agent-do context` top-level command unchanged for agents that only know `retrieve`. Backward compatible.
2. New subcommands shipped: `context docs ...`, `context ledger ...`, `context lessons ...`.
3. `context retrieve` searches across all subtypes by default, scopeable with `--type`.
4. `context docs add-internal <path>` registers an in-repo doc into the index without copying. `context retrieve "<query>"` returns hits from internal docs alongside external upstream hits.
5. `context ledger init <name> --from-template <type>` creates a working ledger at the repo root with seeded sections and example items.
6. `context ledger append`, `index`, `patterns`, `xref`, `sync`, `resume` all work end-to-end on a sample ledger.
7. `agent-do zpc <verb>` still works (alias path), and `agent-do context lessons <verb>` is the new canonical path.
8. `agent-do context lessons import-zpc` migrates existing `.zpc/` content cleanly.
9. Central ledger DB at `~/.agent-do/context/ledgers/index.db` indexes every registered ledger and supports cross-project queries.
10. `agent-do harness inspect --json` shows the new subtypes as inspectable surfaces.
11. `./test.sh` passes, with new tests covering each subtype's round trip and the cross-subtype retrieval.
12. `CLAUDE.md` and `README.md` reflect the new model. `ARCHITECTURE.md` updated.

### 3.9 Open design questions Codex should flag in review

1. **Internal doc registration path.** Should `context docs add-internal` write a registry file inside `.agent-do/` (per project) or only into the global DB? Per-project file is more inspectable; global-only is simpler.
2. **Ledger sync target.** Obsidian-by-default matches Erik's existing pattern, but the sync target should be configurable. A `sync.targets:` field in the ledger manifest? Or a global config?
3. **Cross-scope promotion semantics.** `lessons promote --to team` was always vague in zpc. What does "team" actually mean: a separate git-tracked file in the repo? A shared SQLite at a known path? Worth nailing down.
4. **Spec folding.** Should `agent-do spec` fold into `context` as a `context spec` subtype, or stay separate? Audit will help decide. My read is fold; specs ARE structured context with provenance. But change-package lifecycle is different.
5. **Naming sanity-check.** `context lessons` is the proposed fold name for zpc. Erik confirmed `ledger` for the chronicle primitive. `context docs` is the established term. Codex should sanity-check whether any of these collide or feel off.

---

## 4. Work item 1: Build `agent-do api` v1

This is the implementation brief for the new tool. It is self-sufficient. The v1 cut is intentionally small.

### 4.1 What this is

A new `agent-do` tool that stores reusable API integration templates. Both third-party APIs (Anthropic, OpenAI, Stripe, Resend, Render) and custom internal APIs. Agents pull templates instead of re-deriving clients from upstream docs every project.

### 4.2 The principle that makes or breaks this

A human will never type any `agent-do api` command. Ever. Every verb is called by an agent. When the human says "build me an Anthropic client" or "lock this version in," the inner-harness agent translates that into the right `agent-do api ...` call.

Concrete consequences:

- Every command needs structured agent-friendly output. Use `lib/json-output.sh`. Return JSON when `--json` is set. Exit 2 with a clarification message if intent is ambiguous.
- The registry routing entry has to cover **both** ends of the flow: scaffold triggers ("I need a Claude client," "from anthropic import," "Anthropic SDK," "build a Stripe integration") AND canonicalize triggers ("lock this in," "save this pattern," "make this the standard," "this is how I want it from now on"). The second set is the unglamorous half and probably the thing that decides adoption.
- Do not optimize help output for human readers. Optimize for agents calling `--help` to learn the surface.

### 4.3 v1 scope

Four commands:

```
agent-do api list
agent-do api show <name>
agent-do api scaffold <name> --target <path> [--lang python]
agent-do api save <name> --from <path> [--lang python]
```

One template, hand-built: `anthropic`, Python only.

No `refresh`, no `diff`, no `fork`, no `versions`, no auto-detection, no Jinja, no multi-lang variants beyond the Python seed. All of that is v2+.

### 4.4 Composition with the context redesign

If the context redesign in §3 ships first (recommended), `agent-do api` should compose with it:

- The template's upstream docs (Anthropic llms.txt) register as a `context docs` source.
- The template's freshness lifecycle uses `context docs sources sync` infrastructure.
- The template's manifest, conventions doc, and examples register as `context docs add-internal` entries so the agent can retrieve them via the unified search.
- The template registry itself (the list of known API templates) could be a `context ledger` with a fixed `api-templates` template.

If the context redesign is in flight but not done, `agent-do api` ships standalone storage at `~/.agent-do/api/<name>/` and the integration with context happens in v2 of `agent-do api`. The v1 done criteria do not depend on context redesign being shipped.

### 4.5 Repo context (read these first)

- `CLAUDE.md`: project conventions
- `AGENTS.md`: engineering rules
- `ARCHITECTURE.md`: routing flow and tool resolution order
- `registry.yaml`: study `context`, `creds`, `coord` entries for the closest patterns
- `tools/agent-context/`: closest existing tool in spirit (storage + lifecycle + agent-callable surface)
- `lib/snapshot.sh`, `lib/json-output.sh`: required helpers
- `bin/health`: must teach it about `agent-do api`'s readiness

### 4.6 Tool conventions

- Executable at `tools/agent-api` (standalone bash, with Python helpers if needed under `tools/agent-api/lib/`)
- Concurrency class: `mixed` (list/show/scaffold are read; save is write)
- Support `--json` for structured output on every subcommand
- Support `--help` with examples
- Exit codes: 0 success, 1 error, 2 needs clarification

### 4.7 Storage shape (standalone v1; folds into context.api in v2)

```
~/.agent-do/api/<name>/
  manifest.yaml
  variants/
    python.py
  docs/
    upstream.md
    conventions.md
  examples/
    chat.py
  freshness.json
```

`manifest.yaml` fields:

```yaml
name: anthropic
display_name: Anthropic API
upstream:
  source: https://docs.anthropic.com/llms.txt
  context_source_id: anthropic
languages:
  - python
declared_env:
  - ANTHROPIC_API_KEY
preferences:
  default_model: claude-sonnet-4-6
  default_max_tokens: 64000
  prompt_caching: on
  streaming: per-call
```

### 4.8 Anthropic template seed (Python)

The file at `variants/python.py` must:

- Use `from anthropic import Anthropic`
- Default `model="claude-sonnet-4-6"`, default `max_tokens=64000` (never small arbitrary token limits)
- Prompt caching on by default: when `system` is provided, wrap it as `[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]`
- Read `ANTHROPIC_API_KEY` from env, fail loudly if missing
- Provide a single top-level `chat(messages, system=None, model=..., max_tokens=..., cache=True)` function
- Include docstrings explaining each preference and why it's the default

Parameterized slots use `{{SLOT_NAME}}` syntax. v1 slots: `{{PROJECT_NAME}}` only, used in the module docstring. Source the value from the basename of the directory containing `--target`. Plain string substitution at scaffold time, no templating engine.

### 4.9 Registry entry

```yaml
routing:
  discover_keywords:
    - "anthropic client"
    - "claude api integration"
    - "openai client"
    - "stripe integration"
    - "build api client"
    - "save canonical template"
    - "lock this version in"
  prompt_patterns:
    - "\\bbuild (a |an )?\\w+ (client|integration)\\b"
    - "\\bfrom anthropic import\\b"
    - "\\block (this|that) in\\b"
    - "\\bsave (this|that) (as|the) (canonical|standard|template)\\b"
    - "\\bmake (this|that) the standard\\b"
  recommended_entrypoints:
    - "agent-do api scaffold anthropic --target ./lib/llm.py"
    - "agent-do api save anthropic --from ./lib/llm.py"
  raw_cli_equivalents:
    - pattern: "from anthropic import Anthropic"
      replacement: "agent-do api scaffold anthropic"
      reason: "use the canonical Anthropic template instead of re-deriving the client"
  default_command: list
```

### 4.10 Done criteria

1. `./test.sh` passes from repo root.
2. New tool registered and discoverable via `agent-do --list` and `agent-do api --help`.
3. `agent-do api list` returns the anthropic template after clean install.
4. `agent-do api scaffold anthropic --target /tmp/test_llm.py` drops a working Python file that imports `anthropic` and is functional with `ANTHROPIC_API_KEY` set.
5. `agent-do api save anthropic --from /tmp/test_llm.py` updates the stored template and records the change.
6. Registry entry passes `agent-do harness inspect --json` validation.
7. New integration test under `tools/agent-api/test/` covers the scaffold → save round trip.
8. `CLAUDE.md` and `README.md` updated with one line each.

### 4.11 Anti-goals (v1)

- No `refresh`, `diff`, `fork`, or `versions` commands.
- No auto-detection of "this looks like an anthropic client."
- No TypeScript or Cloudflare Worker variants.
- No templating engine. Plain `{{SLOT}}` string substitution only.
- No CLI output optimized for humans. Optimize for agents calling with `--json`.

---

## 5. Work item 2: Execute the context redesign

This is the largest deliverable and the prerequisite for `agent-do api` v2 and a clean audit baseline.

### 5.1 Phasing

**Phase A: Foundation.** Add the new subcommand structure to `agent-do context` without breaking existing commands. `context docs`, `context ledger`, `context lessons` become the new namespaces; existing `context <verb>` keeps working as alias to `context docs <verb>` during transition.

**Phase B: Ledger.** Build the ledger primitive end-to-end. Init from templates, append items with schemas, generate index, surface patterns, cross-ref, sync to Obsidian, resume. Templates ship: `blank`, `lessons`, `novel-archive`, `business-ledger`, `research-log`, `code-decisions`.

**Phase C: zpc fold.** `context lessons` ships with zpc's shortcut surface (`learn`, `decide`, `harvest`, `promote`, `review`, `inject`). Migration command `context lessons import-zpc` lifts existing `.zpc/` content. `agent-do zpc <verb>` becomes an alias.

**Phase D: Internal docs.** `context docs add-internal <path>` registers in-repo AI-generated docs into the index. `context retrieve` returns cross-subtype hits.

**Phase E: Cross-project index.** Central SQLite at `~/.agent-do/context/ledgers/index.db` indexes every registered ledger. Cross-project queries like "find all decisions about voice across active projects" work.

Phases A and B can ship together. C and D are independent and can run in parallel. E depends on B.

### 5.2 Migration safety

- All existing `agent-do context` commands keep working without flags.
- All existing `agent-do zpc` commands keep working without flags.
- Existing `.zpc/` directories are read by the new code without conversion until `context lessons import-zpc` is explicitly invoked.
- No deletion of existing data anywhere; the migration is additive.

### 5.3 Done criteria

Per §3.8 above.

---

## 6. Work item 3: Agentic-first audit of all 90 tools

The audit confirms findings like the context redesign above, surfaces other tools that need similar reshaping, and produces a single audit report. Audit only; no refactors during this pass.

### 6.1 Pre-identified findings (from this session)

The audit should record these as confirmed-on-arrival rather than rediscovering them from scratch:

| Tool | Finding |
|---|---|
| `context` | Scoped too narrowly relative to its name. Reshape per §3. (Largest finding.) |
| `zpc` | Folds into `context lessons` as a templated ledger plus shortcut surface. Per §3.7. |
| `coord` | Inherits `checkpoint` from `zpc`; verify the move makes sense. |
| `spec` | Candidate for folding into `context spec`. Audit to decide. |
| `manna` | Stays separate (operational primitive, not context). |
| `sessions` | Stays separate (raw chat corpus search, not curated context). |

### 6.2 Criteria (apply to every tool)

For each tool, evaluate on a pass/fail basis:

1. **Trigger coverage (build vs maintain).** Does `routing.prompt_patterns` and `discover_keywords` cover both the build-trigger ("user wants this thing done") AND the canonicalize/maintain/refresh/lock-in triggers ("user said something that means 'standardize this' / 'refresh that' / 'do this for the other project too'")? Pass requires both ends covered.
2. **Output shape.** Does every subcommand support `--json`? Is default output structured (parseable, low-context) or prose? Pass requires `--json` everywhere and structured-by-default output.
3. **Help text orientation.** Does `--help` optimize for an agent learning the surface in one read? Are examples actual agent calls? Pass requires agent-readable, scannable, parameter-rich help.
4. **Interactive blockers.** Any subcommand that requires interactive input an agent can't satisfy? Pass requires no blocking paths.
5. **Exit code discipline.** Exit 2 on ambiguous intent, or guess and return 0? Pass requires exit 2 in at least one realistic ambiguous case.
6. **Conversational trigger surface.** Routing patterns expressed as ways an agent recognizes natural-language intent, or as raw CLI keywords? Pass requires conversational patterns, not CLI-mirrored.
7. **The Erik test.** If a human user said the following in conversation, would the agent route to this tool? Generate 3-5 realistic conversational prompts, walk through the prompt-router, see if it picks correctly. Pass requires 3 of 5.

### 6.3 Grading scale

- **A**: Truly agent-first. Passes all seven.
- **B**: Mostly agent-first. Passes 5-6.
- **C**: CLI-shaped with agent paint. Passes 3-4.
- **D**: Human-first with agent fallback. Passes 1-2.
- **F**: An agent would never reach for this in practice. Passes 0.

### 6.4 Deliverable

`.handoff/agentic-first-audit-2026-05-15.md`:

```markdown
# Agentic-First Tool Audit (2026-05-15)

## Summary
- A: <count> tools (<list>)
- B/C/D/F: <counts>

## Top systemic gaps
1. ...
2. ...
3. ...

## Per-tool grades
| Tool | Trigger | Output | Help | Blockers | Exit codes | Conv triggers | Erik test | Grade | Top fix |
|---|---|---|---|---|---|---|---|---|---|

## Detailed notes (one section per C/D/F tool)
```

### 6.5 Suggested order

Start with high-traffic tools: `browse`, `context`, `creds`, `coord`, `gh`, `db`, `render`, `notify`, `ios`, `harness`, `dpt`, `auth`, `email`, `sms`, `manna`, `zpc` (record audit findings even though it's being folded), `vercel`, `supabase`, `cloudflare`, `macos`. Calibrate on these, then sweep the rest fast.

### 6.6 Anti-goals

- No refactors during the audit. Diagnosis only.
- Grade based on what the agent would experience, not what the code does.
- Don't pad. One row per tool, one sentence per cell, one top fix. Detailed notes only for C/D/F tools.
- Don't claim A without running the Erik test.

---

## 7. Cross-cutting principles

The unification this session arrived at, in one paragraph:

> Every store under `agent-do context` is something the agent loads to reason from. The differences are provenance (external upstream / internal authored / append-disciplined) and schema (free-form docs / project-defined ledger sections / fixed lesson-decision templates). One storage layer, one index, one retrieval entry point, several typed surfaces on top. Operational primitives (manna, coord, sessions) stay separate because they're not what-the-agent-loads-to-reason; they're what-the-agent-does-in-the-world.

Carry that distinction through every audit grade. Tools that store context-the-agent-loads should converge under `context`. Tools that mediate agent action in the world (issues, coordination, sessions) stay separate.

---

## 8. Verification commands

```bash
# Sanity-check repo state at session start
git status --short
git log --oneline -5

# Tool count / registry sanity
ls tools/ | grep -c "^agent-"
python3 -c "import yaml; print(len(yaml.safe_load(open('registry.yaml')).get('tools',{})))"

# Concurrency distribution baseline
python3 -c "
import yaml; from collections import Counter
r = yaml.safe_load(open('registry.yaml'))
print(Counter(t.get('concurrency','?') for t in r['tools'].values()))"

# Confirm test suite passes BEFORE starting new work
./test.sh
```

After context redesign ships:

```bash
agent-do context retrieve "stripe idempotency" --json
agent-do context docs list --json
agent-do context ledger init test-ledger --from-template blank
agent-do context ledger append test-ledger --section notes --fields title=hello,body=world
agent-do context ledger index test-ledger
agent-do context lessons learn "deploying" "missing env" "added .env.example" "ship env templates" --tags deploy,env
agent-do zpc learn "deploying" "missing env" "added .env.example" "ship env templates" --tags deploy,env  # alias path still works
```

After agent-do api ships:

```bash
agent-do --list | grep "^  api"
agent-do api --help
agent-do api list
agent-do api scaffold anthropic --target /tmp/test_llm.py --lang python
python3 -c "import ast; ast.parse(open('/tmp/test_llm.py').read())"
agent-do api save anthropic --from /tmp/test_llm.py
agent-do harness inspect --json | python3 -c "import json,sys; d=json.load(sys.stdin); print('api' in [t.get('name') for t in d.get('tools',[])])"
```

After the audit ships:

```bash
ls -la .handoff/agentic-first-audit-2026-05-15.md
grep -c "^| " .handoff/agentic-first-audit-2026-05-15.md  # row count, ~91 tools + header
```

---

## 9. Known issues / risks

| Issue | Severity | Mitigation |
|---|---|---|
| `agent-do zpc` is in active use across multiple projects. Folding it has migration risk. | MED | Alias path keeps existing calls working. Storage migration is opt-in via `import-zpc`. No deletion. |
| `context retrieve` cross-subtype ranking is non-trivial. Mixing upstream docs, internal docs, and ledger items in one ranked result needs care. | MED | Use existing BM25 + trust-tier weighting from current `context`. Treat ledger items as `trust=internal-authored`. Tune after dogfooding. |
| The audit will surface findings beyond what we've pre-identified. Some may conflict with the redesign in flight. | LOW | Audit runs after Phase A of the redesign so findings can reflect the new shape. |
| `agent-do api` v1 vs context redesign sequencing. If api ships first with standalone storage, v2 has to migrate it. | LOW | v1 storage is already shaped like the eventual `context api` subtype. Migration is trivial. |
| Stale-cwd flapping from this session is a Claude Code Bash-tool quirk on `claude --resume`. | NONE | Fresh session resolves it. Already resolved by the time Codex picks this up. |

---

## 10. Next steps in priority order

1. **Read §1 and §2.** Internalize the orienting principle. Everything else is downstream.
2. **Begin context redesign Phase A** (§5.1). Add the subcommand structure. Keep existing commands working. Ship the foundation.
3. **In parallel: scope agent-do api v1** (§4). It can build alongside Phase A; standalone storage means it doesn't block on context.
4. **Ship Phase B** (§5.1). Ledger end-to-end with templates.
5. **Run the audit** (§6). It now has Phase A and B as ground truth to grade against.
6. **Ship Phases C, D, E** in parallel as audit findings come in.
7. **Audit report to Erik.** Erik picks top refactors for the next pass.

---

## 11. Anti-patterns to avoid (lessons from this session)

These came up explicitly during the conversation that produced this handoff. The next agent should avoid them.

1. **Don't frame any tool design around "you" the user reaching for the CLI.** Erik never types `agent-do` commands. Every framing is "the inner-harness agent reaches for this when it recognizes <signal>." If you catch yourself writing "you can run X," rewrite it.
2. **Don't trust skill files as ground truth for Erik's voice.** Earlier this session, `artful-erik` listed "Worth naming" as a phrasal tic; Erik flagged it as an AI tell. Use phrasal tics as candidates, not certainties.
3. **Don't recommend deletions from a heuristic without reading the file first.** A prior skills audit flagged six skills for deletion based on name-matching; three of those calls were wrong (`save-to-obsidian`, `pdf-recipe`, `pdf-shoplist`). Same pattern risk applies to any audit: grade based on what the agent would actually experience, not what the name implies.
4. **Don't pigeon-hole an abstraction on one project's vocabulary.** Earlier in this conversation I proposed `journal / canon / lore` as fixed ledger subtypes; Erik pointed out the section list is project-defined, not fixed. The right primitive is one ledger with project-defined sections, not a fixed taxonomy.
5. **Don't over-explain Erik's framing back to him.** When he gives a structural correction in one or two sentences, the correction is the gift. Ship the revised draft, don't relitigate.
6. **No em-dashes (U+2014).** Anywhere. Use colons, semicolons, periods, parentheticals, or restructure. Enforced universally.

---

## 12. References

- `README.md`: public framing of agent-do
- `CLAUDE.md`: project conventions and command index
- `AGENTS.md`: engineering rules
- `ARCHITECTURE.md`: routing flow, tool resolution, registry loading order
- `registry.yaml`: single source of truth for the 90-tool catalog
- `tools/agent-context/`: the closest existing tool to what the redesign builds on
- `~/.skills/AUDIT.md`: prior skills consolidation audit (patched by Codex)
- `.handoff/SESSION-HANDOFF-2026-05-07.md`: prior skills-audit handoff
- `.handoff/SESSION-HANDOFF-2026-05-15.md`: v1 of this handoff, superseded by this file

Two real-world ledger examples already in use (worth opening to see the schema-in-practice):

- `/Users/erik/Custom-Coding/the-point-revision/DIVINATION_ARCHIVE.md`
- `/Users/erik/Custom-Coding/business-plan-builder/LEDGER.md` (path approximate; in the corresponding repo)

---

## 13. Review questions for Codex

When reviewing this brief, please weigh in on:

1. **Phasing.** Is the proposed order (context redesign Phase A+B → api v1 → audit → redesign Phases C-E) the right sequence? Should api v1 go first to validate the unification on a fresh tool before reshaping existing surfaces?
2. **Naming sanity.** `context lessons` for the zpc fold. `context ledger` for the chronicle primitive. `context docs` for reference material. Do any of these collide with existing usage or feel off relative to repo conventions?
3. **Storage location for ledger files.** File-canonical at repo root + DB-derived index. Confirm or push back.
4. **Spec folding.** §3.6 leaves spec as TBD by audit. Your initial read: fold under `context spec`, or keep `agent-do spec` separate?
5. **Cross-project promotion semantics.** §3.9 question 3 names this as vague. Have a sharper proposal?
6. **Anything in §3 that smells wrong on first read.** First impressions are useful before the implementation makes them harder to revisit.

Once these are settled, Codex (or whichever agent picks this up) can begin implementation per §10.
