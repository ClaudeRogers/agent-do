# agent-do Harness Upgrade Plan v2 — Approved for Execution

**Date:** 2026-07-20 · **Supersedes:** `.handoff/2026-07-16-harness-upgrade-plan.md` (v1)
**Authors:** Claude (Fable 5) session with Erik; revised per Codex review of 2026-07-20 (all review claims code-verified)
**Repo:** `/Users/erik/Custom-Coding/agent-do` · **Branch:** `feat/harness-upgrade-2026-07`

## Verified defects motivating this plan

All confirmed by direct code inspection:

1. `tools/agent-browse/agent-browse` `restart` path runs `pkill -f "node.*agent-browse.*daemon.js"` — kills **every** session's daemon, not just the caller's. `stop_daemon()` signals whatever pid the file contains with no identity verification. Cross-session contamination is a live bug today, not a future risk.
2. `tools/agent-git` `cmd_commit` runs `git add -A` when nothing is staged — violates ownership-based staging and can sweep unrelated in-flight work into a commit.
3. Stale/retired model defaults: browse vision + `agent.js` + screen + vision tools on `claude-sonnet-4-20250514` (past retirement); `agent-eval` default `claude-3-sonnet-20240229` (retired 2025); `intent-router` default Opus 4.5; `ai_router.py` adaptive-thinking allowlist includes discontinued `claude-mythos-preview`, excludes current models.
4. `zpc promote --to global` writes `global-lessons.jsonl` but `cmd_inject` never reads it — global memory is write-only.
5. `~/.factory/agent-do-index.yaml` lists 77 of 94 tools (missing: appleevents auth clerk cloudflare context creds gh harness meetings namecheap obsidian okta psql resend spec transcribe vector). It is a stale hand-maintained cache, not a one-line omission.
6. The `suggest`/`find` dispatch path (`agent-do` ~line 311) `exec`s `bin/suggest` directly, bypassing the credential preload every normal tool gets.
7. `registry.yaml` `git` entry claims capabilities that don't exist ("resolve conflicts", "interactive rebase", "AI commit messages").

## Cross-cutting rules for the executor

- Follow repo conventions: bash tools mirror agent-git's `--json` pattern; Python tools mirror agent-gh's argparse style; every new CLI verb gets a `registry.yaml` contract entry.
- **Never fabricate a model ID.** Where this plan says "populate from live API," call the provider's model-list endpoint and record the **complete, untruncated** list in the work log before choosing.
- **Never print a secret.** Secret-scan output redacts matched values; test fixtures use obviously-fake keys.
- **Tests never touch the operator's real state.** Any test exercising zpc, creds, or `~/.agent-do` state must isolate via `AGENT_DO_HOME` (and `ZPC_GLOBAL_DIR` if separately derived) pointed at a temp dir.
- Do not touch: `~/.zshrc` (especially the `claude-1m` alias), `tools/agent-gh` behavior, generated-template standalone contracts, any tool not named below.
- `CHANGELOG.md` entry per commit. Conventional Commits, one logical change per commit, exactly the six below. Before each commit: `git diff --cached | rg -i "(api[_-]?key|secret|token|password)"`.

---

## Commit 1 — `fix(models): centralize current internal model defaults`

Anthropic-only consolidation step; no provider abstraction yet. Scope: **agent-do-owned internal generation defaults only** — NOT generated standalone templates (`agent-api` scaffold output), NOT embeddings/transcription utilities, NOT user-facing provider engines where the user names a model.

1. Create `models.yaml` (repo root):

```yaml
# models.yaml — source of truth for agent-do's OWN internal LLM calls.
# (Generated templates and user-selected engines are out of scope by design.)
# Validate with: agent-do models doctor
version: 1
roles:
  fast:      # intent routing, suggest, JSON extraction
    chain: []          # populate from live Anthropic /v1/models — full list in work log
    env: AGENT_DO_MODEL_FAST      # legacy alias also honored: AGENT_DO_AI_MODEL
  vision:    # screenshot understanding: browse, screen, vision tools
    chain: []
    env: AGENT_DO_MODEL_VISION
  deep:      # eval default grading, correctness-critical internal calls
    chain: []
    env: AGENT_DO_MODEL_DEEP
models: {}   # per-model capability records, doctor-populated (see Commit 2):
             #   endpoint, modalities, reasoning params, max_tokens ceiling
retired:     # per-provider; resolver hard-skips. Distinct from "unavailable to
             #   these credentials" — see Commit 2 doctor semantics.
  anthropic: [claude-3-sonnet-20240229, claude-sonnet-4-20250514]
```

2. Create `lib/models.py`: `resolve(role)` (env override → first non-retired chain entry → actionable error) and `generation_params(model)` reading **stored capability records** — no name-prefix inference, no "unknown means adaptive" assumption. For Commit 1, capability records for the chosen Anthropic models are fetched from the live Models API (it returns a per-model `capabilities` tree including thinking types) and written into `models.yaml` under `models:`.
3. Migrate internal call sites: `lib/ai_router.py` (delete `DEFAULT_FAST_MODEL` + allowlist; keep `call_json_model` signature), `bin/intent-router`, `tools/agent-screen/screen_ops.py`, `tools/agent-vision/vision_ops.py`, browse `vision.js`/`agent.js` (one cached `resolveModel()` helper via `agent-do models resolve vision --json`), `tools/agent-eval` **default only** — explicit `model:` values inside user eval files are preserved verbatim; fix the stale example text in the tool's embedded docs.
4. `tools/agent-api`: generated templates stay standalone (env-driven `ANTHROPIC_MODEL` with a literal fallback — refresh the seed's literal to a current model at scaffold-write time, but the template must not import agent-do internals).
5. Minimal `agent-do models list|resolve <role> [--json]` CLI + dispatcher + registry contract + index entry.

**Acceptance:** `rg "claude-[a-z0-9.-]+" tools lib bin` finds hardcoded IDs only in `models.yaml`, generated-template seeds, tests, and docs. Unit tests: resolution order, retired-skip, eval explicit-model preservation. Smoke: one live call per role.

## Commit 2 — `feat(models): add capability-aware OpenAI fallback`

1. Provider-prefixed entries (`anthropic/...`, `openai/...`; bare = anthropic) across chains, env overrides, and `retired`.
2. `llm_call(role, messages, *, json_schema=None, images=None, max_tokens=...)` dual-provider wrapper. OpenAI path uses the **Responses API with its current parameter structure (nested `reasoning.effort` etc.) verified against live docs at build time** — do not recall shapes. Runtime fallback: model-not-found walks to next chain entry (may cross providers), loud warning + telemetry nudge, raise only when chain exhausted.
3. Per-model capability records under `models:` drive everything (endpoint, modality, reasoning params). Anthropic records doctor-fetched from the Models API capability tree; OpenAI records curated at config time and doctor-verified (their model list + published docs; current family per OpenAI docs is GPT-5.6 — confirm live).
4. `models doctor [--fix]`:
   - Queries both providers' model lists. **Bounded and explicit:** absent optional provider key → warn-and-skip that provider, never fail; `agent-do --health` inherits warn-only semantics.
   - Distinguishes **retired** (absent from the provider's public list) from **unavailable** (present but 403/credential-scoped). Only retired is eligible for persistence, and only under `--fix`.
   - Refreshes capability records; flags newer same-tier candidates (report-only).
5. Fix `suggest`/`find` dispatch to route through the same credential-resolution preload as `exec_tool` (today it `exec`s `bin/suggest` raw).
6. Registry contracts for every `models` verb.

**Acceptance:** provider-prefix parsing tests; cross-provider fallback test (mock 404); retired-vs-unavailable doctor test (mock 403); health passes with `OPENAI_API_KEY` unset; suggest AI path succeeds using store-resolved credentials.

## Commit 3 — `fix(zpc): include global lessons in read surfaces`

1. `cmd_inject` (`tools/agent-zpc/lib/integration.sh`): `--- Global Lessons (machine-wide) ---` section (tail -10 of `global-lessons.jsonl`) before project lessons; silent no-op when absent/empty; keep total inject bounded.
2. `cmd_status`: global lesson count. `zpc query --global`: include global store, entries tagged `[global]`.
3. **Tests first, isolated:** all zpc tests run under a temp `AGENT_DO_HOME`; they must never read or mutate the operator's real global store.
4. **Seed after tests pass**, via the supported path (`zpc learn` in a scratch project → `zpc promote --to global`), verifying dedup on repeat promotion:
   - worktree lesson: gitignored env files don't exist in fresh worktrees → seed from parent; use `agent-do git worktree --seed` (tags `git,worktree,env`).
   - browse lesson: wedged daemon ≠ lost state; sessions persist on disk; self-heal now automatic (tags `browse,daemon`).

**Acceptance:** isolated tests green; real `agent-do zpc inject` shows both seeds exactly once; empty-global projects show no section.

## Commit 4 — `feat(browse): add session-safe daemon diagnosis and self-heal`

Isolation is the hard requirement: sessions already own distinct `$TMPDIR/agent-browser-${SESSION}.{sock,pid}` files; **nothing here may signal, probe, or delete another session's daemon or files.**

1. **Remove broad process killing from every path** — the `restart` handler's `pkill -f "node.*agent-browse.*daemon.js"` goes away entirely. No pattern-kills anywhere.
2. **Daemon identity in argv:** launch `daemon.js` with explicit `--session <name> --socket <path>` argv so identity is verifiable via `ps` argv on any platform (no environment inspection needed).
3. **Identity-verify before every signal** — in `stop_daemon` and all other paths, not just self-heal: pid from own-session `PID_FILE` must map to a live process whose argv contains `daemon.js` **and** this session's `--session` value. Mismatch (pid reuse) → clean own-session files, never signal.
4. **`ping` in `protocol.js` + daemon handler:** answers `{success, session, children, uptime_s}` regardless of page state, and **must not auto-launch a browser** — probe over a raw socket connection (like the existing `daemon_responsive` probe does), never through `send_command`, whose ensure-daemon behavior auto-launches. Audit that the ping handler is exempt from any auto-launch middleware in the daemon.
5. **Distinct states, distinct handling:** (a) no pid file → normal cold start; (b) pid file but pid dead or identity-mismatched → clean own files, cold start; (c) pid alive + identity ok + socket missing → clean, restart; (d) pid alive + socket present + ping timeout → **wedge**: SIGTERM verified pid, bounded wait, SIGKILL fallback, clean own files, restart, proceed with original command, one stderr line: `agent-browse: daemon for session '<SESSION>' was wedged — auto-restarted (saved sessions persist on disk)`. Healthy-idle (pingable, no page) is NOT a wedge.
6. Pre-flight applies to non-lifecycle commands only (everything except `launch/close/restart/status/session*/doctor`).
7. **`browse doctor`:** current session only — session name + derivation, pid + identity-verified, socket present, pingable, page-responsive, child count, per-state diagnosis. `session active` remains the read-only multi-session listing.

**Acceptance (mandatory):** two-session isolation test — daemons under `AGENT_BROWSER_SESSION=isoA`/`isoB` with pages loaded; wedge A (SIGSTOP or test hook); command in A auto-heals and succeeds; **assert B's pid, page, and socket untouched.** Plus: healthy-idle daemon not restarted; pid-reuse case cleans without signaling; manual `restart` in A leaves B running.

## Commit 5 — `feat(git): add guarded worktree and recovery operations`

1. **`cmd_commit` staging fix (breaking change, intentional):** delete the `git add -A` fallback. Nothing staged → refuse with a message naming the fix (`git add <paths>` / stage by ownership). Registry + help updated.
2. **Secret-scan gate on `commit`:** scan **added lines only** of `git diff --cached`; named detectors (api-key, token, password-assignment, private-key-block, provider-key-shapes e.g. `sk-…`); on hit block with file, line, detector — **matched value redacted, never printed**. Bypass exists but is noisy and intentional: `--no-scan` prints a prominent warning and is logged to telemetry. JSON: `{blocked, findings:[{file,line,detector}]}`.
3. **`worktree add <branch> [--path <dir>] [--no-seed]`** (+ `list`, `remove`): `git worktree` wrappers; seeding default-on copies gitignored local files (`.env`, `.env.*`, `CLAUDE.local.md`, plus `.agent-do/worktree-seed` entries) from parent checkout; never overwrite existing targets; report what was seeded.
4. **`snap list|diff|restore <file>`:** read side of the `refs/auto/<branch>` shadow-ref convention; `restore` writes to `<file>.recovered` by default (`--in-place` to overwrite); graceful message when ref absent.
5. **`conflicts`:** conflicted files (`--diff-filter=U`) with marker counts; `--json`.
6. **`recover` (truly read-only):** structured reflog (last ~20) + unreachable-commit report via `git fsck --unreachable --no-reflogs` — **not** `--lost-found`, which writes into `.git/lost-found`.
7. **`sweep [--apply]`:** dry-run is the default output; `--apply` executes (no `--force` overload). Excludes: current branch, protected names (`main`, `master`, repo default), branches checked out in **any worktree** (`git worktree list` awareness), branches with no upstream, branches with unpushed commits.
8. **Registry honesty:** `git` entry rewritten to actual commands; drop false claims; "AI commit messages" → "heuristic commit messages from diff".

**Acceptance:** fixture-repo tests — commit refuses when nothing staged; scan blocks planted fake key with redacted output and `--no-scan` warns loudly; worktree seeds `.env.local` and refuses overwrite; `recover` leaves `.git` byte-identical (assert no `.git/lost-found`); sweep dry-run lists but deletes nothing, `--apply` respects every exclusion; registry ⊆ actual commands.

## Commit 6 — `fix(discovery): derive installed index from registry`

`registry.yaml` is already the canonical inventory (`agent-do find github` resolves `gh` correctly today); the stale surface is the hand-maintained `~/.factory/agent-do-index.yaml` (77/94 tools listed; 17 missing including `gh`).

1. **Generator:** `bin/gen-index` renders the index from `registry.yaml` + a small repo-owned override file (`docs/index-overrides.yaml` or similar) for category grouping and one-line phrasing. Wire into `install.sh`/update flow so `~/.factory/agent-do-index.yaml` becomes an **installed cache**, never hand-edited.
2. **Test the generator in-repo:** `tests/test_index_generation.sh` asserts every `tools/agent-<name>` has a registry entry and appears in generated output — CI never depends on a developer's home-directory file.
3. Regenerate and install the index (all 94 tools, including `gh` and `models`).
4. **Help banners:** `agent-git --help` first line: `Local repository operations. For GitHub PRs/reviews use: agent-do gh`; mirrored line in `agent-gh --help`.
5. **Only after the derived index is installed:** update `~/.claude/CLAUDE.md` quick-reference — add `| GitHub PRs/reviews | agent-do gh inbox / pr <n> / audit <n> / merge <n> |`, keep the gh-grep row for code search.

**Acceptance:** generated index contains all tools; generation test green; a spot-check `agent-do find github` and index lookup both surface `gh`.

---

## Final gates

Per commit: targeted tests + registry contract validation + `./test.sh`. Before merge: live provider smoke calls (one per role, both providers where keys exist) and the two-daemon isolation test.

**Non-goals:** no tool renames; no agent-gh behavior changes; no `~/.zshrc` changes (`claude-1m` stays exactly as-is); generated templates remain standalone; no heavy new deps (Python OpenAI SDK acceptable; Node side prefers raw fetch).

**Risks:** browse vision has 8 call sites — consolidate through one helper before swapping models; pid-reuse edge demands the identity check in *every* signal path; OpenAI Responses API shapes verified live, never recalled; `git add -A` removal is a behavior change some caller may depend on — search repo + hooks for `agent-git commit` callers and note in CHANGELOG.
