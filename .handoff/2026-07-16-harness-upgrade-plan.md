# agent-do Harness Upgrade Plan — Model Consolidation, ZPC Read Loop, Browse Self-Heal, agent-git Expansion, Discovery Fixes

**Date:** 2026-07-16 · **Author:** Claude (Fable 5) session with Erik · **Executor:** Codex
**Repo:** `/Users/erik/Custom-Coding/agent-do` · **Suggested branch:** `feat/harness-upgrade-2026-07`

## Context

An audit found agent-do's own LLM call sites running stale-to-retired models (browse vision and screen on `claude-sonnet-4-20250514`, past its June 2026 retirement; agent-eval defaulting to `claude-3-sonnet-20240229`, retired July 2025), a write-only global memory tier in zpc, a browse-daemon wedge failure mode that lives as a logged lesson instead of tool behavior, a thin agent-git missing high-leverage safety commands, and `agent-gh` absent from the discovery index. This plan fixes all five as independent workstreams. Each workstream has explicit acceptance criteria; run `./test.sh` plus the per-workstream checks before calling anything done.

**Cross-cutting rules for the executor:**
- Follow existing repo conventions (bash tools follow agent-git's `--json` flag pattern; Python tools follow agent-gh's argparse style; registry.yaml entries must describe only capabilities that exist).
- Never fabricate a model ID. Where this plan says "populate from live API," call the provider's model-list endpoint and print the **complete, untruncated** list into your work log before choosing. A truncated listing that hides the answer is worse than no check.
- Do not touch: `~/.zshrc` (especially the `claude-1m` alias), `tools/agent-gh` behavior, any tool not named below.
- Update `CHANGELOG.md` once per workstream.

---

## Workstream 1 — Multi-provider model resolution (`models.yaml`)

**Goal:** one noticeable file governs every LLM call agent-do makes; both Anthropic and OpenAI are first-class; a sunsetted model can never run.

### 1.1 Create `models.yaml` (repo root, sibling of `registry.yaml`)

```yaml
# models.yaml — THE single source of truth for every LLM call agent-do makes.
# Change models here, nowhere else. Entries are "provider/model-id";
# a bare id means anthropic. Validate with: agent-do models doctor
version: 1
roles:
  fast:      # intent routing, suggest, JSON extraction
    chain: []          # populate at build time — see 1.5
    env: AGENT_DO_MODEL_FAST
  vision:    # screenshot description: browse, screen, vision tools
    chain: []
    env: AGENT_DO_MODEL_VISION
  deep:      # eval grading, agent-api default, correctness-critical calls
    chain: []
    env: AGENT_DO_MODEL_DEEP
retired: {}  # per-provider lists, doctor-maintained; resolver hard-skips these
  # anthropic: [claude-3-sonnet-20240229, claude-sonnet-4-20250514]
  # openai: []
```

Resolution order per role: env override (accepts `provider/model` or bare id) → first chain entry not in `retired` → error with actionable message. `AGENT_DO_AI_MODEL` remains honored as a legacy alias for the `fast` role env.

### 1.2 Create `lib/models.py`

Public API (keep it this small):
- `resolve(role: str) -> dict` → `{"provider": "anthropic"|"openai", "model": str, "role": str}`. Applies resolution order and retired-skip.
- `generation_params(provider, model) -> dict` → provider-correct reasoning/thinking params. Anthropic: adaptive thinking for anything not on a **legacy denylist** (prefixes `claude-3-`, `claude-opus-4-0/4-1/4-5`, `claude-sonnet-4-0/4-5`, `claude-haiku-4-5` → legacy or no thinking; unknown/new models → `{"thinking": {"type": "adaptive"}}`). This replaces `ai_router.py`'s allowlist, which is backwards (includes discontinued `claude-mythos-preview`, excludes everything current). OpenAI: the equivalent reasoning-effort params for its current API — verify the current parameter shape from OpenAI's live docs, don't recall it.
- `llm_call(role, messages, *, json_schema=None, images=None, max_tokens=4096) -> dict|str` — thin dual-provider wrapper (anthropic + openai SDKs) with the runtime fallback: on a model-not-found error, log a loud warning + telemetry nudge (`lib/telemetry.py` exists), walk to the next chain entry (may cross providers), retry once per entry. Raise only when the chain is exhausted.
- Credentials via the existing creds layer (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY` through `tools/agent-creds` resolution, same as other API tools).

### 1.3 New CLI verb: `agent-do models`

- `models list` — roles, resolved model per role, chain, retired list.
- `models resolve <role> [--json]` — prints resolution result; this is the interface Node/bash call sites use.
- `models doctor [--fix]` — queries **both** providers' live model-list endpoints (Anthropic `GET /v1/models` with `x-api-key`; OpenAI `GET /v1/models` with bearer). Reports: configured IDs that no longer exist (with `--fix`, append to `retired`), chain entries currently retired-listed, and newer same-tier candidates (name-pattern + created-at heuristic, report-only). Wire into `bin/health` so `agent-do --health` flags model rot.
- Register in the bash dispatcher, `registry.yaml`, and `~/.factory/agent-do-index.yaml`.

### 1.4 Migrate the seven call sites

| File | Today | Change |
|---|---|---|
| `lib/ai_router.py` | `DEFAULT_FAST_MODEL="claude-sonnet-4-6"` + adaptive allowlist | delete both; use `models.resolve("fast")` + `generation_params()`; keep `call_json_model` signature so `bin/suggest` is untouched |
| `bin/intent-router` | default `claude-opus-4-5-20251101` | `models.resolve("fast")`; keep `AGENT_DO_AI_MODEL` override |
| `tools/agent-browse/vision.js` (7 sites) + `agent.js` (1) | `claude-sonnet-4-20250514` | one `resolveModel()` helper: `execSync("agent-do models resolve vision --json")` once per process, cached; branch anthropic/openai for the image call |
| `tools/agent-screen/screen_ops.py` | `claude-sonnet-4-20250514` | `lib/models.py` `llm_call("vision", ...)` |
| `tools/agent-vision/vision_ops.py` | `claude-sonnet-4-20250514` | same |
| `tools/agent-eval` | default `claude-3-sonnet-20240229` (+ stale doc examples at lines 23/199) | default from `resolve("deep")`; fix the embedded examples |
| `tools/agent-api` | `claude-opus-4-8` (current) | keep `ANTHROPIC_MODEL` env compat; fall back to `resolve("deep")` when unset |

### 1.5 Populate chains from live data (build-time step, not config guesswork)

Query both providers' full model lists, print them complete in the work log, then fill chains with **currently-live** IDs following this intent: `fast` and `vision` lead with the best current mid-tier Anthropic model (as of writing, `claude-sonnet-5`), then a current OpenAI mid-tier, then a cheaper Anthropic fallback; `deep` leads with the best current Opus-tier (`claude-opus-4-8`), then a current OpenAI flagship. Seed `retired` with `claude-3-sonnet-20240229` and `claude-sonnet-4-20250514`.

### 1.6 Acceptance

- `rg "claude-[a-z0-9.-]+" tools lib bin --no-heading | grep -v models.yaml` returns no hardcoded model IDs outside `models.yaml`, tests, and docs.
- Unit tests: resolution order (env beats chain), retired-skip, provider-prefix parsing, legacy-denylist thinking logic (unknown model → adaptive).
- `agent-do models doctor` runs green against live APIs; `bin/health` includes it.
- One smoke call per role succeeds (e.g. `agent-do browse` vision describe on a local screenshot; `suggest` with AI path enabled).

---

## Workstream 2 — zpc: close the global read loop

**Problem:** `zpc promote --to global` writes `$ZPC_GLOBAL_DIR/global-lessons.jsonl`, but `cmd_inject` (`tools/agent-zpc/lib/integration.sh`) reads only project files. Global memory is currently write-only.

1. **`cmd_inject`:** add a section **before** project lessons: `--- Global Lessons (machine-wide) ---` containing `tail -n 10` of `global-lessons.jsonl`. Silent no-op when the file is absent/empty. Keep total inject size bounded.
2. **`cmd_status`:** report global lesson count alongside project counts (it already computes `global_exists`).
3. **`zpc query --global`:** include global store in query results, each tagged `[global]`.
4. **Seed two lessons** into the global store (via the supported code path, not hand-edited JSONL):
   - context "fresh git worktree", problem "dev server crashes mysteriously", solution "gitignored env files (.env.local etc.) don't exist in new worktrees — copy from parent checkout", takeaway "worktrees need env seeding; use agent-do git worktree --seed", tags "git,worktree,env".
   - context "agent-do browse automation", problem "browse commands hang; daemon alive but no browser children", solution "restart the daemon — sessions persist on disk", takeaway "wedged daemon ≠ lost state; self-heal now automatic", tags "browse,daemon".
5. **Acceptance:** `agent-do zpc inject` in any project shows the Global Lessons section with both seeds; empty-global projects show no section; `status` counts match.

---

## Workstream 3 — browse daemon self-heal (session isolation is the hard requirement)

**Architecture facts (verified):** sessions are isolated by construction — `SESSION` derives from `--session` → `AGENT_BROWSER_SESSION` → agent identity (`CLAUDE_SESSION_ID`, `CODEX_THREAD_ID`, …) → `default`; socket and pid file are `$TMPDIR/agent-browser-${SESSION}.{sock,pid}`; each session runs its own `daemon.js`. Multiple agents run concurrent isolated browsers. **Nothing in this workstream may signal, probe, or delete another session's daemon or files.**

### 3.1 Add a protocol-level `ping`

`daemon.js` gains a `ping` action that answers `{success: true, session, children: <n>, uptime_s}` regardless of page state. **Do not reuse `daemon_responsive()` as the wedge detector** — it succeeds only when a live page is loaded, so a healthy idle daemon reads as unresponsive and would be needlessly restarted. New bash probe `daemon_pingable()` (bounded ~2s socket ping).

### 3.2 Wedge definition and self-heal

Wedge := `is_daemon_running()` (own-session pid alive) AND own-session socket exists AND `ping` times out. On wedge, during pre-flight for non-lifecycle commands (everything except `launch/close/restart/status/session*/doctor`):

1. **Identity-verify before any signal:** read pid from own-session `PID_FILE`; confirm via `ps` that the pid's command line contains `daemon.js` **and** its environment/argv matches this `SESSION`. If identity doesn't match (pid reuse), do **not** signal — just remove the stale pid/socket files and start fresh.
2. SIGTERM the verified pid; bounded wait; SIGKILL only if still alive. **Never `pkill -f agent-browser`** or any pattern kill — that is the cross-session contamination path.
3. Remove own-session `.sock`/`.pid` only. Never glob other sessions' files.
4. `start_daemon`, proceed with the original command, emit one stderr line: `agent-browse: daemon for session '<SESSION>' was wedged — auto-restarted (saved sessions persist on disk)`.

### 3.3 `browse doctor`

New subcommand reporting, for the **current session only**: session name and how it was derived, pid + identity-verified?, socket present?, pingable?, page-responsive?, child count (from ping), and stale-file diagnosis. `session active` remains the multi-session *listing* view; doctor never acts across sessions.

### 3.4 Acceptance (isolation test is mandatory)

Test script: start two daemons under `AGENT_BROWSER_SESSION=isoA` and `isoB`, each with a page loaded. Wedge A (SIGSTOP its daemon, or a test hook making it stop answering). Run a read command in session A → observe auto-restart + notice, command succeeds. **Assert session B's pid is unchanged, its page still loaded, its socket untouched.** Also: healthy-idle daemon (launched, no page) must NOT be restarted by pre-flight; pid-reuse case (stale pid file pointing at a live non-daemon pid) must clean files without signaling.

---

## Workstream 4 — agent-git: thin → right-sized

`tools/agent-git` (bash, ~410 lines) keeps its shape: JSON contracts, safety rails, discoverability. Raw `git` remains the path for exotic operations — do not chase parity. Six additions + one honesty fix:

1. **`worktree add <branch> [--path <dir>] [--seed]`** (+ `worktree list`, `worktree remove <dir>`): thin wrappers over `git worktree`, plus `--seed` (default **on**; `--no-seed` to skip) copies gitignored-but-required local files from the parent checkout into the new worktree: default list `.env`, `.env.*`, `CLAUDE.local.md`, extendable via `.agent-do/worktree-seed` (one path per line) in the repo. Never overwrite an existing file in the target; report what was seeded (JSON mode included). *Rationale: gitignored env files silently missing from fresh worktrees is a recurring mystery-crash trap.*
2. **`snap list|diff|restore <file>`**: read-side of the auto-snapshot shadow-ref convention (`refs/auto/<branch>`, written by an external Stop hook). `list` shows snapshot commits for the current branch; `diff` compares working tree to newest snapshot; `restore <file>` checks a file out of the newest snapshot (to a `.recovered` suffix by default; `--in-place` to overwrite). Degrade gracefully with a clear message when the ref doesn't exist. *Rationale: the safety net currently lives in one user's zsh aliases; agent-do makes it available to every agent/harness.*
3. **`commit` secret-scan gate**: before committing, scan the staged diff (`git diff --cached`) for `(api[_-]?key|secret|token|password|BEGIN [A-Z]+ PRIVATE KEY|sk-[A-Za-z0-9]{20,})` (case-insensitive where sane). On hit: block, print offending lines/files, exit nonzero. `--no-scan` overrides. JSON mode reports `{blocked: true, findings: [...]}`.
4. **`conflicts`**: list conflicted files (`git diff --name-only --diff-filter=U`) with per-file conflict-marker counts; `--json`. Makes the registry's existing claim true.
5. **`recover`**: read-only. Last ~20 reflog entries (structured) + dangling commits from `git fsck --lost-found`, with one-line subjects. No mutations — pairs with `snap restore` for the action side.
6. **`sweep [--dry-run]`**: delete local branches already merged into the default branch. **Dry-run is the default**; `--force` executes. Never touches current branch, `main`, `master`, or anything with an unpushed upstream delta.
7. **Registry honesty:** rewrite `registry.yaml`'s `git` entry to the real command set (drop "resolve conflicts"/"interactive rebase" claims; "AI commit messages" → "heuristic commit messages from diff"); add the new commands. Update help text.

**Acceptance:** each new command has a test in the repo's test harness (worktree seeding verified with a fixture repo containing a gitignored `.env.local`; secret-scan blocks a planted key and `--no-scan` passes it; sweep dry-run lists but does not delete). `registry.yaml` git capabilities ⊆ actual commands.

---

## Workstream 5 — discovery & docs

1. **`~/.factory/agent-do-index.yaml`:** add the missing `gh` line under DATA: `gh: "GitHub PR review workstation - inbox, awaiting, audit, threads, checks, approval-gated merge"`. Add `models` under META.
2. **Completeness guard:** add `tests/test_index_complete.sh` — every `tools/agent-<name>` directory/file must have an entry in both `registry.yaml` and the index; fail loud listing omissions. (This is the class of bug that hid agent-gh.)
3. **Help banners:** first line of `agent-git --help`: `Local repository operations. For GitHub PRs/reviews use: agent-do gh`. Mirror line in `agent-gh --help`.
4. **`~/.claude/CLAUDE.md` quick-reference:** update the GitHub row to point at `agent-do gh` for PR/review workflows (row currently says use raw `gh` CLI / gh-grep only): `| GitHub PRs/reviews | agent-do gh inbox / pr <n> / audit <n> / merge <n> |`. Keep gh-grep row for code search.
5. **`CHANGELOG.md`** entries per workstream; bump version per repo convention.

---

## Build order & verification

1. **WS1 models** (live breakage first) → 2. **WS2 zpc** → 3. **WS3 browse** → 4. **WS4 git** → 5. **WS5 discovery**.

Each workstream: implement → run `./test.sh` + workstream acceptance → commit (Conventional Commits, one logical change per commit: `feat(models): ...`, `fix(zpc): ...`, `feat(browse): ...`, `feat(git): ...`, `docs(index): ...`). Do not batch the whole plan into one commit. Before any commit: `git diff --cached | rg -i "(api[_-]?key|secret|token|password)"`.

**Non-goals:** no tool renames; no agent-gh behavior changes; no changes to `~/.zshrc` (the `claude-1m` alias stays exactly as-is); no new heavy dependencies (OpenAI SDK for Python is acceptable and expected; for Node prefer raw fetch over adding a dependency to browse).

**Risks to watch:** vision.js provider branch is the largest surface (7 call sites — consolidate them through one helper before touching models); pid-reuse edge in WS3 (identity-verify is mandatory, see 3.2.1); OpenAI param shapes drift (verify from live docs at build time, don't recall).
