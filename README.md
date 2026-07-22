# agent-do

<p align="center">
  <img src="assets/agent-do-logo.png" alt="agent-do logo" width="360" />
</p>

<p align="center"><strong>The world-facing outer harness for AI coding agents.</strong></p>

AI coding agents are strong inside a repository. They read files, write code, run
tests, and reason through local changes.

The hard part is everything that is not your code: browsers, authentication, cloud
services, databases, screenshots, design review, work tracking, project memory,
PR triage, notifications, and the local machine itself.

`agent-do` gives agents one durable command contract for that outer world:

```bash
agent-do <tool> <command> [args...]
```

One law runs all of it: snapshot before you act, keep receipts. Every tool
declares that law as a machine-readable contract, and the work boards hold it
too: status comes from receipts, never testimony.

It looks like a CLI because the shell is the simplest contract every coding
agent can already use. But it is not primarily a human productivity CLI.

Humans install it, configure credentials, approve local-machine permissions, read
outputs, and occasionally run commands directly for debugging. In normal use, the
caller is the AI agent or its harness. The agent calls `agent-do` to browse,
authenticate, inspect services, review PRs, query data, track work, coordinate
with other agents, and verify results without inventing one-off shell glue.

It is not a replacement for Claude Code, Codex, Cursor, or any other inner agent.
It is the operating layer around them: structured tools, shared credentials,
discoverability, readiness checks, hooks, work boards, and stateful workflows
that make good agent behavior easier to repeat.

## Why It Exists

Agents can improvise. That is useful until the session becomes a pile of custom
curl calls, one-off Playwright scripts, raw vendor CLIs, copied secrets, and
half-remembered setup steps.

`agent-do` narrows that surface.

- One command shape
- One registry of tools, each with a machine-readable safety contract
- One readiness and bootstrap path
- One credential layer
- One discoverability layer
- One work-board grammar
- One hook surface for nudges without hard-blocking work

The goal is not abstraction for its own sake. The goal is repeatable agency:
the agent should be able to inspect the world, act on it, verify the result, and
leave behind enough structure for the next agent to continue.

## Mental Model

Mature `agent-do` tools follow the same rhythm:

```text
Connect -> Snapshot -> Interact -> Verify -> Save
```

Snapshot is the hinge. An agent cannot reason well about a browser page, a
database schema, a cloud service, or an iOS screen unless it can first see the
current state in a structured way.

```bash
agent-do db connect mydb
agent-do db snapshot
agent-do db query "SELECT * FROM orders LIMIT 10"
agent-do db disconnect
```

### Contracts: the safety layer

The rhythm is machine-readable. Every tool declares a `contracts:` block in
`registry.yaml` mapping each command verb to its beats, with `attributes:` flags
(destructive, long_running, polymorphic, composite, sensitive, passthrough) for
the shapes a single beat cannot express. All 95 registered tools declare
contracts; a tool cannot merge without one.

Orchestrators consume the declarations directly:

```bash
agent-do harness contracts surface --json
```

That returns safety buckets (read_only, write, destructive, sensitive,
long_running, passthrough, own_state) as verb lists, answering scheduling
questions mechanically: which commands can run in parallel, which mutate state,
which deserve confirmation before an agent runs them.

Declarations are kept true, not trusted:

```bash
agent-do harness contracts validate   # gate: registry shape + 95/95 coverage, runs in CI
agent-do harness contracts drift      # registry promises vs live tool --help
agent-do harness contracts audit      # behavioral probe of the read surface
```

## Install

```bash
git clone https://github.com/ovachiever/agent-do.git
cd agent-do
./install.sh
```

`install.sh` is idempotent. It symlinks `agent-do` into `~/.local/bin`, writes
an install-path breadcrumb under `~/.agent-do/`, generates the discovery index
from `registry.yaml`, installs Python dependencies, offers optional npm and
cargo builds for the browser and board tools, and runs a health check.

Hooks install as thin wrappers that delegate into the repo, so `git pull`
updates hook behavior without re-running the installer. Claude Code hooks always
install; Codex hooks install when `~/.codex/` exists (`--codex` forces,
`--no-codex` skips). The installer prints the settings.json registration snippet
and never edits your settings itself. `./install.sh --uninstall` removes the
symlink and the wrappers.

See [docs/INTEGRATION.md](docs/INTEGRATION.md) for hook registration and behavior.

## First Run

```bash
agent-do --health
agent-do bootstrap --recommend
agent-do bootstrap
```

`--health` checks whether the harness is usable. `bootstrap --recommend` shows
which stateful tools should be initialized for the current machine or
repository. `bootstrap` initializes the pieces that are actually needed.

## Finding The Right Tool

When the agent knows the tool:

```bash
agent-do <tool> <command> [args...]
```

When the agent knows the goal but not the tool:

```bash
agent-do --list                          # full registered inventory
agent-do find playwright                 # keyword search across the registry
agent-do suggest "check render logs"     # task to likely tool and command
agent-do suggest --project               # likely tools for this repository
```

When a human or harness wants natural-language routing:

```bash
agent-do -n "take an iOS screenshot"        # LLM-routed
agent-do --offline "check render logs"      # pattern-matched, no API key
agent-do --how "review PRs waiting for me"  # explain the route, then run it
```

Natural-language and offline routing use three exit codes: `0` success, `1`
error, `2` needs clarification. An orchestrator that sees `2` should ask a
follow-up and retry with `--context`.

## Work Boards

`agent-do manna` is git-backed issue tracking built for agents: session claims
prevent two agents from working the same issue, and board state lives in the
repository under `.manna/`.

Every issue is a **track** (a named grouping with intent), an **item** on a
track, or a **dream** (raw intake, exempt from tracking, converted or closed
with a written reason). Commits that advance an item cite it with a
`Manna: mn-xxxxxx` trailer. The board is the only backlog.

```bash
agent-do manna init
agent-do manna create "Fix auth redirect" --type item --track mn-a1b2c3 \
  --source "docs/auth-audit.md" --prompt /abs/path/to/work-order.md
agent-do manna claim mn-d4e5f6
agent-do manna done mn-d4e5f6
```

Beyond title and status, issues carry four schema fields: `type` (track, item,
dream), `track` (the parent track), `source` (where the work came from), and
`prompt` (an absolute path to the work-order prompt paired with the issue, so
the instructions that define done travel with the issue).

Raw ideas enter through `dream`, which files the spark on the nearest board up
the directory tree, or the global inbox when no board exists:

```bash
agent-do manna dream "Cache the registry parse" --source "profiling session"
```

Two commands keep the board honest:

```bash
agent-do manna lint              # board grammar check; findings exit 1
agent-do manna reconcile         # drift between the board and reality
agent-do manna reconcile --fix   # safe fixes: abandon dead claims,
                                 # unblock resolved blockers
```

`reconcile` is receipts over testimony: it reads git history for `Manna:`
trailers, probes whether claiming sessions are still alive, and checks blockers
against actual state instead of trusting what the board says about itself.

## The Ambient Loop

With the Claude Code hooks installed, board-driven work needs no ceremony:

- **SessionStart** pins the session identity (`AGENT_DO_COORD_SESSION`,
  `MANNA_SESSION_ID`) so coordination presence and board claims survive pid
  recycling, then injects the current board into context. If the previous
  session left unresolved drift, the greeting includes it.
- **SessionEnd** retires coordination presence and runs a bounded
  `manna reconcile --write-drift` advisory, leaving findings in
  `.manna/drift.yaml` for the next session's greeting.

Everything is presence-gated: repositories without a `.manna/` board see none
of it.

The wider hook model stays non-blocking by design: hooks suggest relevant tools
at session start, route fuzzy user prompts to likely `agent-do` commands,
surface coordination context when another agent is active in the same project,
and record outcome telemetry so nudges can be measured instead of guessed. No
hook hard-blocks work.

## Multi-Agent Coordination

```bash
agent-do coord touch
agent-do coord peers
agent-do coord focus set "private Render networking" --path render.yaml --phase building
agent-do coord claim render.yaml --reason "blueprint wiring"
agent-do coord interrupts
```

`coord` is a shared state board, not an agent chat system. Presence is
liveness-verified: a dead session can never read as an active peer. Agents
declare roles (builder, auditor, researcher, overseer) with exclusive-writer
territories, place advisory claims on paths, publish artifacts, drop file
pointers for each other, and read contention, notice, dependency, and novelty
interrupts derived from all of it. A warn-only pre-commit guard
(`agent-do coord guard install`) flags commits that touch another agent's live
claims.

## Memory

Two memory systems with a clean division of labor:

| | `context` | `zpc` |
|---|---|---|
| Holds | External reference docs | Lessons and decisions from real work |
| Question it answers | What do the docs say? | What did we learn using them? |
| Scope | Global (`~/.agent-do/context/`) | Per-project (`.zpc/`) |
| Typical calls | `context retrieve`, `context fetch-llms` | `zpc learn`, `zpc decide`, `zpc patterns` |

## Internal Model Roles

Tools that need an LLM internally resolve it by role (fast, vision, deep)
through `models.yaml` instead of hard-coding model IDs. `agent-do models
resolve <role>` returns the current provider and model, and `agent-do models
doctor` verifies the configured lists.

## Credentials

```bash
agent-do creds required render            # what a tool needs
agent-do creds store RENDER_API_KEY --stdin
agent-do creds check --tool render
```

`creds required` is the public setup contract for every tool: required keys,
optional keys, and feature-specific notes when a tool can run partially without
a key. The dispatcher, router, and health checker resolve declared tool secrets
from the secure store automatically, so secrets never appear in command
arguments, shell history, or docs.

## Tool Tour

95 registered tools. The flagships:

| Tool | What it does |
|---|---|
| `browse` | Headless browser with @ref element selection, SSO/MFA login handoff into headless state, persistent auth sessions, API capture and replay |
| `auth` | Site-level auth orchestration: probes the live checkpoint, advances one safe step at a time, ensures authenticated state through a strategy ladder |
| `manna` | Git-backed work boards: tracks, items, dreams, claims, lint, reconcile |
| `coord` | Shared state board for parallel agents: presence, roles, territories, claims, interrupts |
| `gh` | GitHub PR work-state: inbox, review, unresolved threads, checks, audit with deploy probes |
| `db` | Database client for PostgreSQL, MySQL, SQLite: connect, snapshot schema, query |
| `excel` | Workbook automation: read and write cells, formulas, sheets |
| `dpt` | Design Perception Tensor: 72-rule visual quality scoring of the live page, 0-100 |

The rest of the catalog covers cloud platforms (`render`, `vercel`, `supabase`,
`cloudflare`, `gcp`, `docker`, `k8s`), identity providers (`clerk`, `okta`),
domains and email infrastructure (`namecheap`, `dns`, `resend`), devices and
desktops (`ios`, `android`, `macos`, `screen`, `hardware`), perception
(`vision`, `ocr`, `image`, `video`, `audio`), documents and data (`sheets`,
`pdf`, `pdf2md`, `jupyter`), knowledge surfaces (`obsidian`, `notion`,
`calendar`), and communication (`email`, `sms`, `slack`, `meetings`), plus a
root `notify` contract that routes one message across providers.

See [docs/TOOLS.md](docs/TOOLS.md) for the full map, and
`agent-do <tool> --help` for command details.

### Browser automation

```bash
agent-do browse open https://app.example.com
agent-do browse snapshot -i
agent-do browse fill @e3 "admin@example.com"
agent-do browse click @e7
agent-do browse wait --stable
```

For authenticated sessions:

```bash
agent-do browse login https://app.example.com   # headed window for SSO/MFA
agent-do browse login done --save mysite        # transfer auth to headless
agent-do browse session load mysite             # instant auth next session
```

### GitHub review work

```bash
agent-do gh inbox
agent-do gh audit owner/repo#123 --reply --probe-deploys
```

`gh audit` inspects PR metadata, checks, unresolved threads, changed files,
diff content, lockfile blast radius, and deployment hints, and can draft
engineering review text with concrete fix guidance.

### Visual QA

```bash
agent-do browse open http://localhost:7847
agent-do dpt score          # scores the page open in the browse daemon
agent-do dpt violations     # fix list sorted by impact
```

### Live desktop control

Commands that drive the visible desktop or a real browser window require an
explicit runtime modifier, scoped and time-bounded:

```bash
agent-do +live(scope=desktop,ttl=15m) macos click @g5
```

## Architecture

At runtime, the core is plain:

```text
agent-do <tool> <command>
        |
        v
tools/agent-<name>
```

The supporting layers are:

- `registry.yaml` for tool metadata, routing hints, and contracts
- `models.yaml` for internal model roles
- `tools/` for tool implementations
- `lib/` for shared helpers
- `hooks/claude/` and `hooks/codex/` for harness integration
- `bin/` for routing, health, bootstrap, and discovery

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system map.

## Requirements

- Python 3.10+
- Node.js 18+ for browser tooling
- Rust for `manna`
- `tmux` for terminal-session tooling
- Optional API keys for providers you want to use

Install Python dependencies with:

```bash
pip install -r requirements.txt
```

## Security

Do not put secrets in repos, logs, screenshots, or review comments. Use
`agent-do creds` for API keys and tokens; declared secrets resolve from the
secure store at execution time.

`agent-do context` fetches public reference material without browser cookies or
saved auth state. HTML sources are cached locally with raw provenance plus
extracted searchable text. Agent-facing context output redacts common token,
key, secret, signature, password, auth, and credential query parameters.

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Development

Run the root smoke suite:

```bash
./test.sh
```

Selected deeper checks:

```bash
cd tools/agent-browse && npm test
cd tools/agent-manna && cargo test
bash tools/agent-context/test/integration.sh
bash tools/agent-manna/test/integration.sh
```

Contribution guidance lives in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
