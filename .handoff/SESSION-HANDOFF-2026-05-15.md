# Session Handoff (2026-05-15): agent-do API + Agentic-First Tool Audit

**Author:** Claude Opus 4.7 (1M context), authoring this for the next agent that picks up the work in a fresh `claude` session.
**Project:** `agent-do` at `/Users/erik/Documents/AI/Custom_Coding/agent-do`.
**Hand-off reason:** Mid-thread stale-cwd issue made the current session noisy; Erik is starting fresh. Two pieces of work are queued: a new tool to build, and an audit to run.

---

## 0. TL;DR for the next agent

You have two deliverables:

1. **Build `agent-do api`**: a new tool in the registry. Full implementation brief is in §3. v1 cut is small: four commands, one template (Anthropic, Python only), one registry entry. Scope is explicit; anti-goals are explicit.
2. **Run an agentic-first audit across all 90 existing tools**: a one-pass review of how truly agent-first each tool is. The principle, criteria, and deliverable format are in §4.

Both pieces hang off the same orienting principle, restated cleanly in §1. Read that first; everything else is downstream of it.

Erik never types `agent-do` commands. Ever. Not for setup, not for capture, not for debugging. Build and audit accordingly.

---

## 1. The orienting principle

Quoted verbatim from the conversation that produced this handoff. This is the spine of both work items.

> Every verb is the agent's. Including `save`.
>
> The save flow corrected: the agent builds the Anthropic client in your project. You say something in conversation like "lock this in," "make this the standard," "save this pattern," or just "this is how I want it from now on." The agent recognizes the canonicalize signal and calls `agent-do api save anthropic --from ./lib/llm.py` itself. You don't touch the CLI. You don't even know `--from` exists. You told the agent to standardize this version, and the agent did.
>
> Same for every other verb. `refresh` runs when an agent doing maintenance notices the upstream changed. `fork` runs when you say "I want a cached variant of the anthropic template for that worker project." `diff` runs when an agent is reviewing drift before a refresh. None of these have a human-typed entry point. There's no scenario where you would prefer the CLI over telling the agent.
>
> The actual design principle for `agent-do api`: the **human interface is the conversation with the inner-harness agent**. The agent-do surface is fully opaque to you. Every command has agent-callable structure (clear exit codes, JSON output, registry-declared routing) and agent-callable triggers (conversational patterns, drift signals, project events).
>
> The implication for the registry entry: routing keywords have to cover both ends of the flow. Agent recognizes "I need a Claude client" → scaffold. Agent recognizes "lock this in" / "save this pattern" / "this is the standard" → save. The second set is less obvious and probably the thing that makes or breaks adoption. Most tool layers nail the build-trigger and miss the canonicalize-trigger.

---

## 2. Erik's deeper framing (extrapolation)

The principle above doesn't only apply to the new `agent-do api` tool. It applies to **every tool in the registry**. Quoted from Erik in this session:

> CLI is the contract because LLMs are trained off human CLI interactions. But agentic AI IS the "human at the CLI." There is no human typing the commands.

What that means in practice:

- The CLI shape is fine. Keep it.
- The CLI is read by the agent now, not the human. The agent is the "user." Everything we'd design for a human user should be reconsidered as design for an agent user.
- A command that's pleasant for a human to type may be miserable for an agent to discover, route to, parse, and verify. A command that's awkward for a human to type may be exactly what the agent needs.
- Most tool layers nail the **build-trigger** ("user wants X built") and miss the **maintain-trigger** ("user said something that means 'this is canonical now' / 'refresh this' / 'fork this for that other project'"). The maintain-trigger is where the agent actually closes the loop.

Both work items below are applications of this principle.

---

## 3. Work item 1: Build `agent-do api` v1

This is the full implementation brief. It is self-sufficient. Hand this section to whichever agent does the implementation. (You may be that agent.)

### 3.1 What this is

A new `agent-do` tool that stores reusable API integration templates. Both third-party APIs (Anthropic, OpenAI, Stripe, Resend, Render) and custom internal APIs. Agents pull templates instead of re-deriving clients from upstream docs every project.

### 3.2 The principle that makes or breaks this

A human will never type any `agent-do api` command. Ever. Not for setup, not for capture, not for debugging. Every verb is called by an agent. The human's interface is the conversation with the inner-harness agent (Claude Code, Codex, Cursor). When the human says "build me an Anthropic client" or "lock this version in," the inner-harness agent translates that into the right `agent-do api ...` call.

Concrete consequences:

- Every command needs structured agent-friendly output. Use `lib/json-output.sh`. Return JSON when `--json` is set. Exit 2 with a clarification message if intent is ambiguous.
- The registry routing entry has to cover **both** ends of the flow: scaffold triggers ("I need a Claude client," "from anthropic import," "Anthropic SDK," "build a Stripe integration") AND canonicalize triggers ("lock this in," "save this pattern," "make this the standard," "this is how I want it from now on"). The second set is the unglamorous half and probably the thing that decides adoption.
- Do not optimize help output for human readers. Optimize for agents calling `--help` to learn the surface.

### 3.3 v1 scope (do this, nothing more)

Four commands:

```
agent-do api list
agent-do api show <name>
agent-do api scaffold <name> --target <path> [--lang python]
agent-do api save <name> --from <path> [--lang python]
```

One template, hand-built: `anthropic`, Python only.

No `refresh`, no `diff`, no `fork`, no `versions`, no auto-detection of "this looks like an anthropic client," no Jinja, no multi-lang variants beyond the Python seed. All of that is v2+.

### 3.4 Repo context (read these first)

- `CLAUDE.md`: project conventions
- `AGENTS.md`: engineering rules
- `ARCHITECTURE.md`: routing flow and tool resolution order
- `registry.yaml`: study `context`, `creds`, `coord` entries for the closest patterns
- `tools/agent-context/`: closest existing tool in spirit (storage + lifecycle + agent-callable surface)
- `lib/snapshot.sh`, `lib/json-output.sh`: required helpers
- `bin/health`: must teach it about `agent-do api`'s readiness

### 3.5 Tool conventions

- Executable at `tools/agent-api` (standalone bash, with Python helpers if needed under `tools/agent-api/lib/`)
- Concurrency class: `mixed` (list/show/scaffold are read; save is write)
- Support `--json` for structured output on every subcommand
- Support `--help` with examples
- Exit codes: 0 success, 1 error, 2 needs clarification

### 3.6 Storage shape

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

### 3.7 Anthropic template seed (Python)

The file at `variants/python.py` must:

- Use `from anthropic import Anthropic`
- Default `model="claude-sonnet-4-6"`, default `max_tokens=64000` (never small arbitrary token limits)
- Prompt caching on by default: when `system` is provided, wrap it as `[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]`
- Read `ANTHROPIC_API_KEY` from env, fail loudly if missing
- Provide a single top-level `chat(messages, system=None, model=..., max_tokens=..., cache=True)` function
- Include docstrings explaining each preference and why it's the default

Parameterized slots use `{{SLOT_NAME}}` syntax. v1 slots: `{{PROJECT_NAME}}` only, used in the module docstring. Source the value from the basename of the directory containing `--target`. Plain string substitution at scaffold time, no templating engine.

### 3.8 Registry entry

Add an entry under `tools.api` in `registry.yaml` modeled on existing entries. The routing block must include:

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

### 3.9 Composition with existing surfaces

- **`agent-do context`**: when a template has a `context_source_id` and that source is registered via `agent-do context add-source`, `show` reports freshness and calls `agent-do context retrieve` for upstream doc snippets.
- **`agent-do creds`**: surface `declared_env` from the template manifest through `agent-do --health` and `agent-do creds required api`. Hook into the dispatcher's existing credential preload path.
- **`agent-do harness`**: register template staleness as an inspectable surface so `agent-do harness inspect --json` includes API templates with last-verified timestamps.

### 3.10 Done criteria

1. `./test.sh` passes from repo root.
2. New tool registered and discoverable via `agent-do --list` and `agent-do api --help`.
3. `agent-do api list` returns the anthropic template after clean install on a fresh `~/.agent-do/`.
4. `agent-do api scaffold anthropic --target /tmp/test_llm.py` drops a working Python file that imports `anthropic` and is functional with `ANTHROPIC_API_KEY` set.
5. `agent-do api save anthropic --from /tmp/test_llm.py` updates the stored template and records the change in `manifest.yaml`.
6. Registry entry passes `agent-do harness inspect --json` validation.
7. New integration test under `tools/agent-api/test/` covers the scaffold → save round trip.
8. `CLAUDE.md` and `README.md` updated with one line each pointing at the new tool.

### 3.11 Anti-goals (do not do these in v1)

- No `refresh`, `diff`, `fork`, or `versions` commands.
- No auto-detection of "this looks like an anthropic client."
- No TypeScript or Cloudflare Worker variants.
- No templating engine. Plain `{{SLOT}}` string substitution only.
- No CLI output optimized for humans. Optimize for agents calling with `--json`.

### 3.12 When done

Write `.handoff/agent-do-api-v1-built.md` summarizing what shipped, what each command does, the registry keywords that route to it, and any deviations from this brief. The inner-harness agent will use that to learn how to call the new tool.

---

## 4. Work item 2: Agentic-first audit of all 90 tools

This is the new piece. The principle in §1 and §2 is the lens. Apply it to every tool currently in `registry.yaml`.

### 4.1 Goal

Produce a single audit report that grades every tool on how truly agent-first it is. The report is diagnosis only. No refactors in this pass. Refactor work gets prioritized AFTER Erik reviews the findings.

### 4.2 Criteria (apply each to every tool)

For each tool, evaluate the following on a 1-5 scale or pass/fail as noted:

1. **Trigger coverage (build vs maintain).** Does the tool's `routing.prompt_patterns` and `discover_keywords` cover *both* the build-trigger ("user wants this thing done") AND the canonicalize/maintain/refresh/lock-in triggers ("user said something that means 'standardize this' / 'refresh that' / 'do this for the other project too'")? Most tools nail the first and miss the second. **Pass requires both ends covered.**

2. **Output shape.** Does every command support `--json`? Is the default output structured (parseable, low-context) or prose? **Pass requires `--json` on every subcommand and structured-by-default output.**

3. **Help text orientation.** Does `--help` optimize for an agent learning the surface in one read, or is it organized like a human-facing man page? Are examples actual agent calls (with parameter forms an agent would emit) or human shell shortcuts? **Pass requires agent-readable, scannable, parameter-rich help.**

4. **Interactive blockers.** Does any subcommand require interactive input that an agent can't satisfy? (Prompts without `--yes`, pagers without `--no-pager`, tty checks, REPLs without a non-interactive mode.) **Pass requires no blocking interactive paths for the agent.**

5. **Exit code discipline.** Does the tool exit 2 ("needs clarification") when intent is ambiguous, or does it guess and return 0 with a fuzzy result? **Pass requires exit 2 in at least one realistic ambiguous case, or clear documentation that ambiguity isn't reachable.**

6. **Conversational trigger surface.** Are the routing patterns expressed as ways an agent would recognize a user's natural-language intent, or as raw CLI keywords? Example of agent-shaped: `"\\block (this|that) in\\b"`. Example of CLI-shaped: `"agent-do api save"`. **Pass requires the patterns to be conversational, not CLI-mirrored.**

7. **The Erik test.** If a human user said the following in conversation, would the agent know to call this tool? Generate 3-5 realistic conversational prompts that should route to this tool. Walk through the prompt-router behavior and see if it picks the right tool. **Pass requires at least 3 of 5 realistic prompts to route correctly.**

### 4.3 Grading scale (per tool, overall)

- **A**: Truly agent-first. Passes all seven criteria.
- **B**: Mostly agent-first. Passes 5-6 criteria.
- **C**: CLI-shaped with agent paint. Passes 3-4 criteria.
- **D**: Human-first with agent fallback. Passes 1-2 criteria.
- **F**: An agent would never reach for this in practice. Passes 0 criteria.

### 4.4 Deliverable

`.handoff/agentic-first-audit-2026-05-15.md` with this shape:

```markdown
# Agentic-First Tool Audit (2026-05-15)

## Summary

- A: <count> tools (<list>)
- B: <count>
- C: <count>
- D: <count>
- F: <count>

Top systemic gaps (patterns that show up across many tools):
1. ...
2. ...
3. ...

## Per-tool grades

| Tool | Trigger | Output | Help | Blockers | Exit codes | Conv triggers | Erik test | Grade | Top fix |
|---|---|---|---|---|---|---|---|---|---|
| browse | ... | ... | ... | ... | ... | ... | ... | B | ... |
...

## Detailed notes (one section per C/D/F tool)

### <tool>
**Grade: C**
**The Erik test prompts I tried:**
- "..." → routed to <tool>? yes/no
- "..." → routed to <tool>? yes/no
**Top fix:** ...
```

### 4.5 Suggested order

Start with tools Erik uses heavily and that have rich command surfaces. Get a calibration on the gradient there, then sweep the rest fast.

High-traffic first batch: `browse`, `context`, `creds`, `coord`, `gh`, `db`, `render`, `notify`, `ios`, `harness`, `dpt`, `auth`, `email`, `sms`, `manna`, `zpc`, `vercel`, `supabase`, `cloudflare`, `macos`.

Then the rest.

### 4.6 Anti-goals for the audit

- **No refactors during the audit.** Audit is diagnosis only. The whole point is to get the map before the surgery.
- **Don't grade based on what the code DOES.** Grade based on what the agent would experience trying to use it: read `--help`, read the registry routing block, simulate the agent's natural path to the tool from a user prompt.
- **Don't pad.** One row per tool in the table. One sentence per cell. One top fix. The detailed notes section is only for C/D/F tools, and even there it's brief.
- **Don't claim a tool is A without running the Erik test.** Three out of five realistic prompts must actually route. If you can't simulate the prompt-router locally, document the prompts and mark them "untested" and grade conservatively.

---

## 5. Architecture changes from this session

None. No production code, registry, or skill directory contents changed in the conversational design pass. The only file edits in this session were:

- `README.md` (logo display width 720 → 360)
- `assets/agent-do-logo.png` (replaced with 712x712 Photoshop-resized version, ~248KB)
- `assets/agent-do-logo.jpg` (removed)
- `.gitignore` (`.handoff/` added)

All four are already committed and pushed to `main`. See §7 for the commit chain.

---

## 6. Files this session created/modified

| File | Purpose | Status |
|---|---|---|
| `.handoff/SESSION-HANDOFF-2026-05-15.md` | This document | created |
| `README.md` | Halved logo display width to 360px | committed + pushed |
| `assets/agent-do-logo.png` | New 712x712 Photoshop-resized logo | committed + pushed |
| `assets/agent-do-logo.jpg` | Old jpg logo | removed |
| `/Users/erik/Documents/Documents/Personal-KB/Obsidian/Erkverse/+/The Outer Harness.md` | The "outer harness" essay, vault-canonical | created (outside repo) |
| `docs/essays/the-outer-harness.md` | Essay draft (later moved by Erik's /push workflow to `.dev/`) | superseded |

No registry edits, no tool edits, no test changes.

---

## 7. Git state

Branch: `main`
HEAD: `ed087e2 Halve README logo display width to 360px`
Recent commits this session:

```
ed087e2 Halve README logo display width to 360px
67a3366 Replace logo with Photoshop-resized version (712x712, 248KB)
0800433 Reduce logo to 50% (627x627, 399KB)
ec21605 [agent-19e75730] Auto-commit: 3 files (README.md,assets/agent-do-logo.jpg,assets/agent-do-logo.png)
```

Pushed to origin/main. No uncommitted changes expected at handoff.

---

## 8. Verification commands for the next agent

```bash
# Sanity-check repo state at session start
git status --short
git log --oneline -5

# Confirm logo render path
grep -n "agent-do-logo" README.md
ls -la assets/

# Tool count / registry sanity
ls tools/ | grep -c "^agent-"
python3 -c "import yaml; print(len(yaml.safe_load(open('registry.yaml')).get('tools',{})))"

# Concurrency distribution (for audit baseline)
python3 -c "
import yaml; from collections import Counter
r = yaml.safe_load(open('registry.yaml'))
print(Counter(t.get('concurrency','?') for t in r['tools'].values()))"

# Confirm test suite passes BEFORE starting new work
./test.sh
```

After agent-do api is built:

```bash
./test.sh
./agent-do --list | grep "^  api"
./agent-do api --help
./agent-do api list
./agent-do api scaffold anthropic --target /tmp/test_llm.py --lang python
ls -la /tmp/test_llm.py
python3 -c "import ast; ast.parse(open('/tmp/test_llm.py').read())"  # syntactically valid
./agent-do api save anthropic --from /tmp/test_llm.py
./agent-do harness inspect --json | python3 -c "import json,sys; d=json.load(sys.stdin); print('api' in [t.get('name') for t in d.get('tools',[])])"
```

After the audit is run:

```bash
ls -la .handoff/agentic-first-audit-2026-05-15.md
wc -l .handoff/agentic-first-audit-2026-05-15.md
grep -c "^| " .handoff/agentic-first-audit-2026-05-15.md  # row count, should be ~91 (header + 90 tools + new api)
```

---

## 9. Known remaining issues from this session

| Issue | Severity | Note |
|---|---|---|
| Stale-cwd flapping in this Claude Code session | LOW (cosmetic) | Diagnosed mid-thread. A one-time directory inode swap (during the earlier EPERM stretch) left Claude Code's persistent Bash tool subprocess holding a vnode reference to the now-orphan inode. `claude --resume` preserves the stale handle; a fresh `claude` session would clear it. Erik is starting fresh after this handoff, which should resolve it. |
| `agent-do api` does not exist yet | TRACKED HERE | Work item 1. |
| 90 tools not yet audited for agent-first orientation | TRACKED HERE | Work item 2. |
| Other Codex sessions running in parallel on this machine | NORMAL | Erik routinely has dozens of agents running. Not a problem in practice; flagged only because it's worth knowing the environment isn't single-agent. |

---

## 10. Next steps in priority order

1. Read §1 and §2. Internalize the orienting principle. Both work items depend on it.
2. Build `agent-do api` v1 per §3. Self-contained brief. Done criteria are testable in 9 commands (§8).
3. Run the audit per §4. Produce `.handoff/agentic-first-audit-2026-05-15.md`.
4. Report back to Erik with: (a) a summary of the audit grades, (b) the top 3 systemic gaps the audit surfaced, (c) the top 5 tools that should be refactored first based on usage frequency × current grade. Erik will pick which refactors run next.

---

## 11. Anti-patterns to avoid (lessons from this session)

These came up explicitly during the conversation that produced this handoff. The next agent should avoid them.

1. **Don't frame any tool design around "you" the user reaching for the CLI.** Erik never types `agent-do` commands. Every framing has to be "the inner-harness agent reaches for this when it recognizes <signal>." If you catch yourself writing "you can run X," rewrite it.
2. **Don't trust skill files as ground truth for Erik's voice.** `artful-erik` lists "Worth naming" as a phrasal tic; Erik flagged it as an AI tell. Use phrasal tics from the skill as candidates, not certainties. When in doubt, read like a person.
3. **Don't recommend deletions from a heuristic without reading the file first.** The skills audit earlier this month flagged six skills for deletion based on name-matching; three of those calls were wrong (`save-to-obsidian`, `pdf-recipe`, `pdf-shoplist`). Same pattern risk applies to any audit: grade based on what the agent would actually experience, not what the name implies.
4. **Don't over-explain Erik's framing back to him.** When he gives a structural correction in one or two sentences, the correction is the gift. Ship the revised draft, don't relitigate.
5. **No em-dashes (U+2014).** Anywhere. Use colons, semicolons, periods, parentheticals, or restructure. The artful-* skills enforce this universally.

---

## 12. References to the rest of the project

- `README.md`: public framing of agent-do
- `CLAUDE.md`: project conventions and command index
- `AGENTS.md`: engineering rules (rules mantra, debugging discipline, TDD)
- `ARCHITECTURE.md`: routing flow, tool resolution, registry loading order
- `registry.yaml`: single source of truth for the 90-tool catalog
- `tools/agent-context/`: the closest existing tool to what `agent-do api` becomes
- `~/.skills/AUDIT.md`: the prior skills consolidation audit (patched by Codex with corrections); separate work item, not relevant to these two deliverables
- `.handoff/SESSION-HANDOFF-2026-05-07.md`: prior handoff covering the skills audit; left as-is

The next agent should not need to read anything outside §3 and §4 of this document plus the repo conventions in `CLAUDE.md` / `AGENTS.md` / `ARCHITECTURE.md` to ship both work items.
