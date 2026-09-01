# Contributing to agent-do

Thank you for your interest in contributing. This document covers the essentials.

## Getting Started

```bash
git clone https://github.com/ovachiever/agent-do.git
cd agent-do
./install.sh
./test.sh
```

`./install.sh` symlinks the CLI, installs the hook wrappers, and asks before
registering them in Claude's `settings.json`. Two flags decide that last step
without a prompt:

```bash
./install.sh --register-hooks   # merge the hook set into settings.json, no questions
./install.sh --print-only       # never touch settings.json; print the snippet to merge
```

The merge is idempotent and additive: it backs the file up to
`settings.json.bak.<epoch>` before writing, adds only registrations that are
missing, leaves your own hooks and every other settings key untouched, and
makes no write at all on a second run. `--uninstall` removes exactly the
entries the installer added. A piped or non-interactive run never modifies
settings.json unless `--register-hooks` says so.

## Project Structure

```
agent-do              # Main entry point (bash)
bin/                  # Core routing and discovery scripts
lib/                  # Shared libraries (Python, bash, Node.js)
tools/agent-*         # Individual tools (standalone or directory-based)
hooks/                # Claude Code integration hooks
registry.yaml         # Master tool catalog
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full routing flow and component map.

## Adding a Tool

0. **The taxonomy gate, answered before any code:** is this a new domain, or a new verb on a domain that already exists? The registry grows by family surfaces, never by unbounded flat names. `agent-do hardware <serial|bluetooth|usb|printer|midi>` fronts five domains through one entry; `agent-do meetings` fronts three providers the same way. A capability that reads as a verb on an existing family (a new provider, a new action in a covered territory) joins that family tool instead of claiming a top-level name. Only genuinely new territory earns one. State the answer in the PR description; reviewers ask this question first.
1. Create an executable at `tools/agent-<name>` that supports `--help`. Standalone scripts and directories with a nested `agent-<name>` executable both work; `--list` discovers tools by filesystem scan.
2. Add a `registry.yaml` entry with `description`, `capabilities`, `commands`, and `examples`.
   - Add `routing` metadata (discovery keywords, raw CLI equivalents, readiness hints, project signals) when the tool should participate in `suggest`, prompt-hook routing, or PreToolUse nudges.
   - Add `credentials` metadata when the tool needs API keys or tokens, so `agent-do creds` can declare, check, and resolve them.
3. Declare a `contracts:` block mapping each command verb to its beats (Connect → Snapshot → Interact → Verify → Save), with `attributes:` flags for verbs a single beat cannot express. This is mandatory: the gate fails any registry tool without one. Draft it with `agent-do harness contracts propose --tool <name>`, which applies `lib/contracts-lexicon.yaml` mechanically. Verbs the lexicon does not know get a classification in the lexicon (or a per-tool `overrides:` entry) and a regenerated draft; the proposed inventory is a build product, never hand-edited.
4. Declare a `bounds:` block for any cap the tool ships. If a command bounds its output, say where the number came from: `{source: registry|derived|measured|none, ref, why}`, keyed by verb (or `*` for caps in shared library code that belong to no single verb). `registry` cites an authority key and the literal must equal it; `derived` cites an expression over keys and the factor in it is the explanation; `measured` means counted at call time, so shipping a literal contradicts it; `none` means no ceiling governs the number, which is an explicit exemption from the capacity checks and never silence. Find what you owe with `./agent-do harness contracts validate` — it names the file and line of every undeclared cap. Numbers themselves come from `agent-do harness quantity lookup`, never from memory.
5. Run the gates before submitting:

```bash
./agent-do harness contracts validate   # Shape errors, full coverage, concurrency, bound provenance
./agent-do harness contracts drift      # Registry promises vs the tool's own --help
./agent-do harness bounds drift         # Declared caps vs the ceilings they cite, + router coverage
./test.sh                               # Full suite (runs the gates plus all tool tests)
```

Shared helpers reduce boilerplate:

- `lib/snapshot.sh` for structured JSON snapshot output
- `lib/json-output.sh` for `--json` flag support
- `lib/retry.sh` for API error recovery with backoff

## Testing

```bash
./test.sh                                      # Root suite (includes the contracts gate and drift check)
cd tools/agent-browse && npm test              # Browser tool tests (Vitest)
cd tools/agent-manna && cargo test             # Issue tracker unit tests (Rust)
bash tools/agent-manna/test/integration.sh     # Manna integration tests
bash tools/agent-context/test/integration.sh   # Context tool integration tests
```

Directory-based tools own their suites; the manna Rust unit and integration suites above also run inside `./test.sh`, while the browse and context suites run standalone. Python tool tests live in `tests/` and are wired into `./test.sh`. Run the relevant suite before submitting changes.

## Working in Lanes (parallel agents)

Large bodies of work run as a swarm of agent sessions, one lane each. Lanes
split by **file ownership, never by phase**: every lane reads, writes, and
verifies its own paths to completion. Splitting by phase (one agent researches,
another implements, a third tests) hands the same files between agents and
turns every boundary into a chance to lose context.

A lane begins as a Manna item. `agent-do manna create` generates its canonical
work order; `agent-do manna sync` gives it the derived
`.handoff/<NN>[b<MM>]-<mn-id>-<slug>.md` name and refreshes the index. Stage the lane by expanding that file in place
with **[`docs/LANE-PROMPT-TEMPLATE.md`](docs/LANE-PROMPT-TEMPLATE.md)**. Never
copy the work order into `.dev/`, `.handoffs/`, or a campaign-local prompt
tree. The template carries the required sections and the reasons behind them: the
claim block, the pasted project-memory blob (`agent-do zpc inject --compact`,
2000-char bound, pasted verbatim rather than left as a command for the agent to
run), owned paths with named non-owned neighbors, `file:line` ground truth
verified during staging, the integration contract pinned character for
character across every lane that consumes it, numbered verification, and the
completion block.

If `manna init` classifies an existing nonempty board as legacy, do not create
pairs by hand. Run `agent-do manna migrate` once with the repository owner’s
authorization. It admits the complete board through the recoverable migration
journal; all later work uses the same strict create, seal, claim, and done path.

Manna creates the pair in both directions: the item points at the generated
handoff and the handoff opens with the exact claim command. `manna claim`
refuses a broken pair; `agent-do manna reconcile` also reports shadow roots.
Priority is changed with `agent-do manna order <id> <position>`, never by
renaming files. Dependencies remain `blocked_by` edges; a bare synchronized
filename is safe to launch, while `bMM` holds it for blocker priority `MM`.
Agents coordinate through
`agent-do coord` (focus, claims, publishes), not through chat.

## Code Conventions

- **Bash tools**: `set -euo pipefail`, source shared helpers, support `--help` and `--json`
- **Python components**: Python 3.10+, type hints where helpful, no unnecessary dependencies
- **Node.js tools**: ES modules, Playwright for browser work, Vitest for tests
- **Rust components**: Stable Rust, Clippy clean, standard error handling

Follow existing patterns in the codebase. Consistency over novelty.

## Commits

- Conventional Commits: `feat(scope):`, `fix:`, `docs:`, `chore:`. One logical change per commit.
- Work tracked on the manna board cites its issue with a `Manna: mn-xxxxxx` trailer (same mechanic as `Co-Authored-By`).
- Scan staged changes for secrets before committing. `agent-do git commit` runs a redacted secret scan over staged additions and blocks the commit on findings; `--no-scan` is an explicit bypass that warns and records telemetry.
- Write commit messages that explain the *why*, not just the *what*.

## Pull Requests

1. Fork the repository and create a feature branch
2. Keep diffs small and focused on a single concern
3. Include test coverage for new functionality
4. Run `./test.sh` and confirm it passes, including the contracts gate and drift check
5. Write a clear commit message that explains the *why*, not just the *what*

## Reporting Issues

Open a GitHub issue with:

- What you expected to happen
- What actually happened
- Steps to reproduce
- Your platform (macOS, Linux, etc.) and relevant tool versions

## Security

If you discover a security vulnerability, please report it privately. See [SECURITY.md](SECURITY.md) for details.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
