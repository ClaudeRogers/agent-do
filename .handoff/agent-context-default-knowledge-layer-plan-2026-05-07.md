# agent-context Default Knowledge Layer Plan - 2026-05-07

## Goal

Make `agent-context` the default agent knowledge layer for external docs and local skills: agents should consult it first for API/library/framework/documentation work, it should refresh WAN-backed docs before use when stale, and it should fail visibly when freshness cannot be verified.

This is not "fetch the whole internet all the time." The product contract should be:

- If the user asks about current docs, APIs, libraries, tools, SDKs, or standards, the agent first asks `agent-context` for fresh context.
- WAN-backed packages carry source, trust, fetch strategy, freshness metadata, and refresh status.
- Retrieval refreshes stale packages before returning content within a bounded latency budget.
- If fresh retrieval is required and refresh fails, the command exits nonzero and tells the agent what remains stale.
- Agents get query-specific commands from hooks/suggest, not generic placeholder examples.

## Progress Update - 2026-05-08

Implemented and validated:

- Phase 0 correctness repairs: context locking, registry concurrency, cache clear by name/id, visible FTS failures, recursive support-file reading, hyphenated query handling.
- Phase 1 freshness schema: additive migration, `package_files`, freshness metadata, `status` freshness counts, `stale`.
- Phase 2 first refresh engine: `refresh <id|name>`, `refresh --due`, URL/GitHub-file refresh paths, last-good cache preservation on failure.
- Phase 4 retrieval front door: `retrieve <query>`, `--fresh`, `--require-fresh`, `--offline`, token-budgeted content, provenance/freshness metadata.
- Phase 5 first adoption path: query-specific `suggest` output, UserPromptSubmit context retrieval nudge, PreToolUse raw-docs-fetch nudge.

Validation:

- `bash tools/agent-context/test/integration.sh`: 43 passed, 0 failed.
- `./test.sh`: 50 passed, 0 failed.
- `git diff --check`: clean.

Remaining:

- Complete Phase 2 HTTP conditional refresh details (`If-None-Match`, `If-Modified-Since`, `304`) and GitHub directory refresh.
- Phase 3 active sources and `sources sync`.
- Phase 6 bounded maintenance command and optional scheduler.
- Phase 7 trust/security/provenance hardening.

## Current Baseline

Already verified:

- `agent-context` works as an explicit CLI knowledge cache.
- 385 packages are indexed on this machine.
- Skill support-file indexing now works for search/get.
- `bash tools/agent-context/test/integration.sh`: 34 passed.
- `./test.sh`: 50 passed.

Blocking gaps from audit:

- `context` is marked `concurrency: read` even though it mutates global state.
- `cache clear <name>` leaves stale DB rows.
- `budget` fails silently on hyphenated FTS queries and does not read recursive support files.
- `fetch-repo` is file-only despite directory examples.
- `sources` are passive config entries, not ingestion inputs.
- Hook/suggest path does not strongly drive agents to query-specific context.

## Target Architecture

### Data Model

Keep `~/.agent-do/context` as the global store, but add explicit metadata:

- `package_meta`
  - `id`, `name`, `type`, `trust`, `tags`, `source`, `cache_path`
  - `source_kind`: `url`, `llms`, `github-file`, `github-dir`, `sitemap`, `local-skill`, `local-project`
  - `canonical_url`
  - `etag`
  - `last_modified`
  - `content_hash`
  - `fetched_at`
  - `checked_at`
  - `expires_at`
  - `refresh_status`: `fresh`, `stale`, `refreshing`, `failed`, `local`
  - `refresh_error`
  - `refresh_policy`: `on-use`, `daily`, `weekly`, `manual`, `local-mtime`

- `package_files`
  - `package_id`
  - `rel_path`
  - `source_url`
  - `content_hash`
  - `token_count`
  - `fetched_at`
  - `indexed_at`

- `sources`
  - backed by config YAML or SQLite, but used actively by refresh.
  - fields: `name`, `kind`, `location`, `trust`, `ttl`, `tags`, `aliases`, `enabled`, `crawl_limit`, `refresh_policy`.

Migration must be additive. Existing caches should continue to search/get before a full refresh.

### Commands

Add or harden these commands:

- `context refresh [id|name]`
  Refresh one package by canonical source.

- `context refresh --due [--limit N] [--budget-sec N]`
  Refresh only expired/stale packages.

- `context refresh --all [--source S]`
  Explicit full refresh, never automatic in hooks.

- `context retrieve <query> [--max-tokens N] [--fresh|--require-fresh] [--json]`
  Search, identify candidates, refresh stale WAN packages, then return token-budgeted content with citations and freshness metadata.

- `context stale [--json]`
  Show stale/failed packages and next refresh command.

- `context sources sync [name|--all]`
  Turn configured sources into indexed packages. This makes `add-source` meaningful.

- `context scan-skills [--root PATH] [name ...]`
  Keep the current default but allow explicit roots and discover known roots.

Existing commands remain:

- `search`: fast, no network by default.
- `get`: fetch cached package/file; should report staleness in metadata.
- `budget`: kept but internally backed by `retrieve` selection logic.
- `inject`: kept but should use same recursive content reader as `retrieve`.

## Implementation Phases

### Phase 0 - Repair Current Correctness Bugs

Files:

- `registry.yaml`
- `tools/agent-context/lib/common.sh`
- `tools/agent-context/lib/cache.sh`
- `tools/agent-context/lib/search.sh`
- `tools/agent-context/lib/budget.sh`
- `tools/agent-context/lib/fetch.sh`
- `tools/agent-context/test/integration.sh`

Tasks:

1. Change registry concurrency from `read` to a safer classification or add command-level write metadata if the registry supports it.
2. Add a `with_context_lock` helper using `flock` around all mutating commands.
3. Set SQLite `busy_timeout` in Python DB calls.
4. Fix `cache clear <name>` by resolving canonical package id before deleting DB rows.
5. Make `budget` quote FTS terms exactly like `search`.
6. Make `budget`/`inject` use recursive supported files.
7. Make failed FTS parsing visible in JSON/text instead of silent empty success.
8. Update tests for all above regressions.

Acceptance:

- Clearing by name and id removes both cache and DB rows.
- `budget 30000 "v4-to-v5 migration keepPreviousData"` returns `skill-tanstack-query`.
- Parallel `scan-skills`/`search` smoke test does not corrupt the DB.

### Phase 1 - Add Freshness Metadata and Migration

Files:

- `tools/agent-context/lib/common.sh`
- new `tools/agent-context/lib/schema.sh` or Python helper under `tools/agent-context/lib/`
- `tools/agent-context/test/integration.sh`

Tasks:

1. Add additive schema migration support with a schema version table.
2. Add metadata columns/tables listed above.
3. Backfill existing packages:
   - local skill/project packages become `refresh_status=local`.
   - fetched packages become `refresh_status=stale` unless `fetched_at` is inside default TTL.
4. Add `context stale`.
5. Ensure old stores initialize and migrate idempotently.

Acceptance:

- `context status --json` includes fresh/stale/failed counts.
- Old temp store and current real store migrate without dropping packages.
- `search/get/list` still work after migration.

### Phase 2 - Build the WAN Refresh Engine

Files:

- new `tools/agent-context/lib/refresh.sh`
- `tools/agent-context/lib/fetch.sh`
- `tools/agent-context/agent-context`
- tests under `tools/agent-context/test/`

Tasks:

1. Implement common fetch result object:
   - status
   - fetched files
   - source URL(s)
   - etag/last-modified/content hash
   - checked_at/fetched_at/expires_at
   - error
2. HTTP URL refresh:
   - use `If-None-Match` and `If-Modified-Since` when available.
   - handle `304 Not Modified`.
   - validate text/markdown content type when possible.
3. `llms.txt` refresh:
   - check `llms-full.txt`, then `llms.txt`.
   - preserve the actual URL used.
   - optionally parse linked markdown URLs in a later phase, behind a crawl limit.
4. GitHub file refresh:
   - use `gh api` when available.
   - store blob SHA/content hash.
5. GitHub directory refresh:
   - fetch recursive tree for default branch or configured ref.
   - preserve relative paths.
   - respect extension allowlist and crawl limit.
6. Local skill refresh:
   - rescan when source `SKILL.md` or support-file mtimes/hash changed.

Acceptance:

- Local HTTP fixture test covers 200, 304, changed ETag, failed refresh.
- GitHub directory fetch works against a mocked `gh` fixture, no live network required for tests.
- Refresh never deletes last-good cached content on WAN failure; it marks stale/failed.

### Phase 3 - Make Sources Active

Files:

- `tools/agent-context/lib/sources.sh`
- `tools/agent-context/lib/refresh.sh`
- `tools/agent-context/agent-context`
- `registry.yaml`
- `README.md`

Tasks:

1. Extend `add-source` with source kind:
   - `--kind url|llms|github-file|github-dir|sitemap|local-skill`
   - `--trust official|maintainer|community|local`
   - `--ttl 1d|7d|30d`
   - `--tags`
   - `--alias`
2. Implement `sources sync`.
3. Make `fetch`, `fetch-llms`, and `fetch-repo` optionally register a source.
4. Update docs so source lifecycle is clear:
   - add-source registers.
   - sources sync indexes.
   - refresh updates.

Acceptance:

- `add-source` + `sources sync` produces indexed package(s).
- `sources` shows last sync and freshness.
- Disabled sources are skipped by `refresh --due`.

### Phase 4 - Build the Agent Retrieval Front Door

Files:

- `tools/agent-context/lib/search.sh`
- `tools/agent-context/lib/budget.sh`
- new `tools/agent-context/lib/retrieve.sh`
- `tools/agent-context/agent-context`

Tasks:

1. Implement `retrieve <query>`:
   - search locally first.
   - rank candidates.
   - classify stale candidates.
   - refresh stale WAN candidates if `--fresh` or default policy requires it.
   - assemble recursive files within token budget.
   - include source URLs, fetched_at, checked_at, expires_at, refresh_status.
2. Make `budget` delegate to the same selector without network by default.
3. Add `--require-fresh`:
   - exits nonzero if selected WAN package cannot be verified fresh.
   - still reports last-good cached content metadata separately if JSON mode requests it.
4. Add `--offline`:
   - never performs network.
   - reports stale state.

Acceptance:

- One command gives an agent everything needed for a docs-backed answer.
- Freshness status is explicit in text and JSON.
- `retrieve --require-fresh` fails closed when WAN refresh fails.

### Phase 5 - Make Agents Use It by Default

Files:

- `registry.yaml`
- `bin/suggest`
- `lib/registry.py`
- `hooks/agent-do-prompt-router.py`
- `hooks/agent-do-session-start.sh`
- tests:
  - `tests/test_v11_routing.py`
  - `tests/test_prompt_hook_ai.py`
  - `tests/test_suggest_ai.py`

Tasks:

1. Update registry examples and recommended entrypoints to `retrieve`, not placeholder `search authentication`.
2. Make `agent-do suggest "<docs query>"` produce a query-specific command:
   - `agent-do context retrieve "<original query>" --fresh --max-tokens 8000`
3. Add UserPromptSubmit nudge for docs/API/library/framework/current/latest prompts:
   - advisory text should require context retrieval before answering/implementing.
   - use query-specific command.
   - do not run WAN fetch inside the hook.
4. Add SessionStart project guidance:
   - if repo docs mention `agent-do context` or project signals include docs/API/library work, mention `context retrieve`.
   - keep it short.
5. Add PreToolUse nudge for raw `curl`/custom docs fetch scripts when `context retrieve/fetch` is the right path.

Acceptance:

- Prompt "use latest TanStack Query docs" emits `agent-do context retrieve "use latest TanStack Query docs" --fresh`.
- Weak/non-doc prompts stay quiet.
- Telemetry records context suggestions and follow-through.

### Phase 6 - Always-Current Background Maintenance

Files:

- new `tools/agent-context/lib/maintenance.sh`
- `tools/agent-context/agent-context`
- maybe `install.sh` if adding optional launchd wiring
- `README.md`

Tasks:

1. Implement `context maintain`:
   - runs `refresh --due` with a small default budget.
   - prunes cache by `cache_max_mb` without touching pinned packages.
   - reports stale/failed counts.
2. Add optional local scheduler support:
   - macOS launchd plist generation, opt-in only.
   - no background scheduler by default unless user enables it.
3. SessionStart can run a cheap `stale --json` check, not WAN refresh.
4. If stale critical docs are detected, nudge agent to run `refresh --due` or `retrieve --fresh`.

Acceptance:

- Maintenance can run repeatedly without changing fresh packages.
- WAN failures do not destroy last-good cache.
- User can disable all background behavior.

### Phase 7 - Trust, Security, and Provenance

Files:

- `tools/agent-context/lib/common.sh`
- `tools/agent-context/lib/refresh.sh`
- `SECURITY.md`
- `README.md`

Tasks:

1. Trust policy enforcement:
   - official sources outrank community.
   - untrusted sources require explicit add/fetch.
   - retrieval shows trust badges and source URLs.
2. No authenticated WAN fetch by default:
   - no cookies.
   - no browser session reuse.
   - no secrets in cached URLs/logs.
3. Redaction:
   - telemetry should never store full fetched content.
   - logs should redact tokens/query params that look secret.
4. Rate limits:
   - per-domain timeout and max files.
   - backoff after repeated failures.

Acceptance:

- Secret-looking query params are not printed in summaries.
- Retrieval includes provenance for every returned package/file.
- Trust policy can block community packages for `--require-official`.

### Phase 8 - Rollout and Migration

Tasks:

1. Run schema migration on real store.
2. Re-register current high-value sources:
   - active skill roots.
   - common official docs already in cache.
   - TanStack pilot docs/skills.
3. Run `context refresh --due`.
4. Monitor:
   - `agent-do context status --json`
   - `agent-do nudges stats --json`
   - hook follow-through for `context`
5. Tighten nudge thresholds once false positives are known.

Acceptance:

- Existing 385 packages remain searchable.
- Context suggestions appear for docs/API prompts.
- Context follow-through is measurable.

## Test Plan

Unit/integration coverage:

- `cache clear` by id and name.
- SQLite migration from old schema.
- Locking under parallel scan/refresh/search.
- FTS quoting for hyphenated terms.
- Recursive budget/inject/retrieve content assembly.
- HTTP refresh 200/304/error with a local test server.
- GitHub directory fetch with mocked `gh`.
- Source add/sync/refresh lifecycle.
- `retrieve --fresh`, `--require-fresh`, and `--offline`.
- Hook/suggest query-specific context commands.
- Telemetry records context suggestion/follow/ignore outcomes.

Canonical commands:

```bash
bash tools/agent-context/test/integration.sh
./test.sh
agent-do context status --json
agent-do context retrieve "TanStack Query v5 keepPreviousData migration" --fresh --json
agent-do suggest "use latest TanStack Query docs" --json
agent-do nudges stats --json
```

## Rollout Order

Recommended first implementation slice:

1. Phase 0 correctness.
2. Phase 1 freshness metadata.
3. Phase 4 `retrieve` in offline/no-refresh mode.
4. Phase 5 query-specific suggest/hook command pointing at `retrieve`.
5. Phase 2 refresh engine.
6. Phase 3 active sources.
7. Phase 6 maintenance.
8. Phase 7 security/trust hardening throughout, finalized before default-on.

Reason: agents can start using one stable front door early (`retrieve`), while WAN freshness lands behind that front door without changing agent behavior again.

## Definition Of Done

`agent-context` can be treated as the default knowledge layer when all are true:

- A docs/API/library prompt gets a query-specific context nudge.
- `context retrieve "<prompt>" --fresh` returns fresh content or fails closed.
- Source/provenance/freshness are visible in output.
- Background maintenance is optional and bounded.
- The current package cache survives WAN failures.
- Integration and root tests pass.
- Telemetry can show whether agents actually follow the context path.
