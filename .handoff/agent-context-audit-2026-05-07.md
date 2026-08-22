# agent-context Audit - 2026-05-07

## Verdict

`agent-context` is a real local knowledge library, not an autonomous agent memory. It stores fetched docs and scanned skills under `~/.agent-do/context`, indexes package metadata/content in SQLite FTS5, and exposes retrieval commands through `agent-do context`.

It works for explicit CLI use:

- `agent-do context status` reports 385 indexed packages on this machine.
- `agent-do context search "v4-to-v5 migration keepPreviousData"` finds `skill-tanstack-query`.
- `agent-do context get skill-tanstack-query --file references/v4-to-v5-migration.md` returns the bundled support file.
- `bash tools/agent-context/test/integration.sh` passes: 34 passed, 0 failed.
- `./test.sh` passes: 50 passed, 0 failed.

It does not reliably get called by agents automatically. The repo has suggestion/nudge plumbing, but the prompt router only emits high-confidence tool suggestions, the context suggestions are generic, and telemetry shows no recorded high-confidence prompt suggestions for `context` in the current event set. Direct tool calls exist, including this audit session, but the adoption path depends on the agent choosing to call it.

## What It Is

Source claims:

- `registry.yaml:2-12`: knowledge library for external docs, llms.txt, GitHub, local skills, token budgeting, annotations, feedback, and global storage.
- `tools/agent-context/agent-context:30-71`: CLI commands for search/get/list, sources, fetching, cache, annotations, budget/inject, build/validate, status/init.
- `ARCHITECTURE.md:265` and `CLAUDE.md:167`: Bash + Python tool with global `~/.agent-do/context`, SQLite FTS5, BM25/trust-tier ranking.

Runtime model:

- `common.sh:5-7`: storage paths are `$AGENT_DO_HOME/context` or `~/.agent-do/context`.
- `common.sh:204-228`: `init` creates an FTS5 `packages` table and `package_meta`.
- `search.sh:6-74`: `_index_package` recursively reads cached text/code files into `content_preview`.
- `search.sh:78-217`: `search` queries FTS5 and reranks by trust/feedback.
- `search.sh:220-388`: `get` fetches one package, a named file, or full recursive cached content.

## Findings

### High - registry concurrency is wrong for a mutating global cache

`registry.yaml:77` marks `context` as `concurrency: read`, but many commands mutate global state: `fetch`, `fetch-llms`, `fetch-repo`, `scan-local`, `scan-skills`, `cache clear`, `annotate`, `feedback`, `add-source`, `remove-source`, and even `get` updates access stats.

Evidence:

- `fetch.sh:69`, `fetch.sh:149`, `fetch.sh:226`, `fetch.sh:307`, `fetch.sh:416` call `_index_package`.
- `search.sh:262-269` updates `last_accessed` and `access_count` during `get`.
- `cache.sh:123-154` deletes cache/index state.
- `annotate.sh:104`, `annotate.sh:186` append JSONL.
- `sources.sh:191`, `sources.sh:203` rewrite config.

Impact: multiple agents can run write commands concurrently against one SQLite DB and shared cache without a lock. The registry advertises it as safe read-only work.

### High - `cache clear <name>` leaves stale DB rows

`cache.sh:103-134` resolves the cache path by `id OR name`, deletes the directory, then deletes DB rows only where `id = target`.

Repro:

```bash
HOME=<tmp> AGENT_DO_HOME=<tmp> agent-do context scan-skills alpha
HOME=<tmp> AGENT_DO_HOME=<tmp> agent-do context cache clear alpha
HOME=<tmp> AGENT_DO_HOME=<tmp> agent-do context list
```

Observed result: `alpha` is still listed after `Cleared: alpha`, but its cache directory is gone. Clearing by canonical id works; clearing by displayed name corrupts the package entry.

### High - `budget` is not equivalent to `search`

`search.sh:145-150` quotes each FTS term, so hyphenated terms like `v4-to-v5` work. `budget.sh:52` still builds raw `fts_query = " OR ".join(expanded_terms)` and catches all FTS exceptions by returning no rows.

Repro:

```bash
agent-do context search "v4-to-v5 migration keepPreviousData" --limit 3
agent-do context budget 30000 "v4-to-v5 migration keepPreviousData" --json
```

Observed result: search finds `skill-tanstack-query`; budget returns success with `0` packages and `0` tokens. A non-hyphenated query finds content.

Impact: the advertised "token-aware context budgeting for agents" fails silently on realistic library/version/API terms.

### Medium - `budget` and `inject` omit recursive support files

`search` and `get --full` now handle recursive cached files. `budget.sh:111-118` and `budget.sh:176-184` only read the first one of `content.md`, `DOC.md`, `SKILL.md`, or `README.md`.

Impact: after scanning a skill with references/templates, `search` can find support-file content and `get --file` can retrieve it, but `budget`/`inject` do not assemble those same files for agents.

### Medium - `fetch-repo` only fetches single files, despite docs/examples implying docs directories

`README.md:252-254` advertises `agent-do context fetch-repo vercel/next.js docs/`. `fetch.sh:197-212` says "file/directory", but `_fetch_repo_path` at `fetch.sh:247-259` calls GitHub's contents endpoint and expects `.content`, which only exists for file objects.

Repro:

```bash
AGENT_DO_HOME=<tmp> agent-do context fetch-repo vercel/next.js docs/
```

Observed result: exit code 1 with no useful output in the explicit-path branch. `gh api repos/vercel/next.js/contents/docs/ --jq .type` confirms GitHub returns an array for directories.

### Medium - `sources` are passive registry entries, not ingestion sources

`sources.sh:214-248` can list/add/remove source config entries, but no fetch/search/build path consumes those configured sources automatically.

Repro:

```bash
AGENT_DO_HOME=<tmp> agent-do context add-source test-source https://raw.githubusercontent.com/anthropics/anthropic-cookbook/main/README.md
AGENT_DO_HOME=<tmp> agent-do context list
```

Observed result: source is listed, but no package is indexed.

Impact: `multi-source registry with trust-tier resolution` is overstated. It is currently source metadata plus manual fetch commands.

### Medium - agent discoverability is too weak and generic

`agent-do suggest "how do I use latest TanStack Query docs?" --json` returns `context`, but its primary command is `agent-do context search authentication`.

Relevant code:

- `registry.yaml:65-69`: recommended entrypoints are hard-coded examples.
- `bin/suggest:149-163`: primary comes from the generic registry entrypoint.
- `lib/registry.py:186-225`: routing detects doc/reference intent, not query-specific context retrieval.
- `hooks/agent-do-prompt-router.py:396-398`: prompt hook intentionally avoids generic search/status suggestions unless directly asked.

Impact: agents get a weak hint, not a ready-to-run query. That matches the user-visible behavior: agents often do not call it.

### Medium - `scan-skills` is hardcoded to `~/.claude/skills`

`fetch.sh:331` only scans `${HOME}/.claude/skills`. On this machine that is a symlink to `/Users/erik/.skills`, so it indexes the 380 active skills there. It does not scan `/Users/erik/.codex/skills` or `/Users/erik/.agents/skills`, and it only considers top-level `*/SKILL.md`.

Impact: the current store can miss Codex/Agents skill locations and nested skills unless they happen to exist under the Claude symlink.

### Low - annotations and feedback accept nonexistent packages

`annotate.sh:28-104` and `annotate.sh:153-186` validate argument shape, not package existence.

Repro:

```bash
AGENT_DO_HOME=<tmp> agent-do context annotate nonexistent-pkg note
AGENT_DO_HOME=<tmp> agent-do context feedback nonexistent-pkg up
```

Observed result: both succeed; search still has no package.

### Low - build/validate is disconnected from runtime ingestion

`build.sh:5-161` validates/copies `DOC.md` and `SKILL.md` packages into a `dist` directory with `registry.json`, but there is no command that imports that build output into `~/.agent-do/context/cache` and indexes it.

Impact: useful as a packaging validator, not currently a complete private-package ingestion workflow.

## Recommendation

Keep the current `agent-context` direction. It is good enough as an explicit local retrieval tool and the recent support-file indexing fix makes skill migration feasible.

Before treating it as the default agent knowledge layer, fix in this order:

1. Correct concurrency semantics and add locking around mutating commands.
2. Fix `cache clear <name>` to delete by resolved canonical id.
3. Bring `budget` and `inject` up to parity with `search/get`: quoted FTS, recursive files, no silent empty success on query parser errors.
4. Either implement recursive GitHub directory fetching or change docs/help to say file-only.
5. Make `sources` either actively ingestable or label them as config-only.
6. Improve `suggest` and prompt-router context nudges so docs/reference prompts produce query-specific commands.
7. Extend `scan-skills` to discover the actual active skill roots on this machine, or make the scan root explicit.

## Verification Commands

```bash
agent-do context status
agent-do context search "v4-to-v5 migration keepPreviousData" --limit 3
agent-do context get skill-tanstack-query --file references/v4-to-v5-migration.md
agent-do context budget 30000 "v4-to-v5 migration keepPreviousData" --json
agent-do suggest "how do I use latest TanStack Query docs?" --json
bash tools/agent-context/test/integration.sh
./test.sh
agent-do nudges stats --json
```
