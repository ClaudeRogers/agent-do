# Claude Code And Codex Integration

agent-do ships hooks that teach coding agents to prefer `agent-do` tools over raw CLI commands. The hooks use a nudge approach: they add context reminders but do not block commands by default.

## Quick Setup

```bash
./install.sh                # Installs Claude hooks; auto-installs Codex hooks if ~/.codex/ exists
./install.sh --codex        # Force Codex hook install even without ~/.codex/
./install.sh --no-codex     # Skip Codex install even when ~/.codex/ is present
./install.sh --uninstall    # Remove all installed hooks (both surfaces)
```

The installer:
1. Symlinks `agent-do` into `~/.local/bin`
2. Writes the `~/.agent-do/install-path` breadcrumb (used by wrappers to find the repo)
3. Installs Claude Code hook wrappers to `~/.claude/hooks/`
4. Optionally installs Codex hook wrappers to `~/.codex/hooks/`
5. Installs Python dependencies
6. Prints a Claude `settings.json` snippet and (when Codex installed) a `~/.codex/hooks.json` template

## Upgrade Model: Thin Wrappers

Installed hooks under `~/.claude/hooks/` and `~/.codex/hooks/` are NOT full
copies of the repo files. They are tiny **wrappers** (Python `runpy.run_path`
for `.py`, `exec` for `.sh`) that resolve the repo root and delegate to the
canonical hook at `<repo>/hooks/<file>` or `<repo>/hooks/codex/<file>`.

This means:

- **`git pull` updates flow through automatically.** Fixes to the canonical
  hooks (registry routing, safe-commit logic, bootstrap feedback) take effect
  on the next event without re-running `install.sh`.
- **Hook imports work.** Wrappers add `<repo>/lib/` to `sys.path` before
  delegating, so `from registry import ...` resolves correctly.
- **The wrapper format is versioned** (`WRAPPER_VERSION` in `install.sh`).
  When the wrapper logic itself needs to change (rare), bump the version and
  re-run `install.sh` to refresh the wrappers. The canonical hooks below
  don't need to know or care.

Repo resolution order inside each wrapper:

1. `AGENT_DO_REPO` environment variable
2. `~/.agent-do/install-path` breadcrumb (written by `install.sh`)
3. Wrapper bails with a clear stderr message if neither resolves

What you typically do after `git pull`:

```bash
git pull
# Done. Next hook event uses the new behavior.
```

When you'd re-run `install.sh`:

- After bumping `WRAPPER_VERSION` in the installer (repo will announce this)
- When a new hook is added (new file in `hooks/` that needs a corresponding wrapper)
- When you move the repo to a different path (re-running rewrites the breadcrumb)
- After `--uninstall` if you change your mind

## The 4-Layer Hook System

### Layer 1: SessionStart: PATH + Context Injection

**File:** `hooks/agent-do-session-start.sh`

Runs once per Claude Code session. Two jobs:
- **Adds agent-do to PATH** via `CLAUDE_ENV_FILE` so all `Bash` tool calls can find it
- **Injects a tooling reminder** into Claude's context with the `agent-do` pattern and project-scoped likely tools
- **Prompts for project bootstrap when needed** with a native macOS dialog at session start when project-local setup like `zpc` or `manna` is missing

SessionStart is not a chat surface, but the current hook can trigger a native macOS bootstrap dialog directly when bootstrap work is pending. If bootstrap is not pending, it falls back to context injection only.

Path auto-detection chain (no hardcoded paths):
1. `which agent-do` (already in PATH)
2. `~/.local/bin/agent-do` (symlink from `install.sh`)
3. `~/.agent-do/install-path` (breadcrumb file)

### Layer 2: UserPromptSubmit: Prompt Routing

**File:** `hooks/agent-do-prompt-router.py`

Analyzes every user prompt and suggests relevant agent-do tools only when the match is strong enough to be useful. When `ANTHROPIC_API_KEY` is available, the hook can use Sonnet 4.6 adaptive thinking over the compact full `agent-do` catalog. The model chooses from real registered tools and returns concise, exact commands; weak matches stay silent.

Prompt-time coordination is targeted. UserPromptSubmit emits `Coord Focus Required` context when active peers exist, the current agent has no focus, and the prompt is starting workspace work. The reminder is non-blocking because blocking hooks stop the agent turn instead of letting the model satisfy the requirement.

The deterministic fallback stays conservative: completion/status prompts still get completion-check context, design-quality prompts still get the DPT path, and generic tool suggestions stay silent instead of guessing.

AI prompt routing receives the catalog, not a deterministic shortlist. This keeps the hook from duplicating local matcher effort before the model has decided which tool, if any, is worth surfacing.

Use `AGENT_DO_HOOK_AI=off` for deterministic-only hook behavior, `auto` for best effort, or `on` to require the AI path.

### Layer 3: PreToolUse: Command Interception

**File:** `hooks/agent-do-pretooluse-check.py` (shared by Claude Code and Codex)

Watches every `Bash` tool call. When an agent tries to run a raw command that has an agent-do equivalent (e.g., `xcrun simctl`, `vercel deploy`, `kubectl`), it injects a hard nudge with the closest native replacement command and any relevant setup hint.

**Codex compatibility:** Codex supports `hookSpecificOutput.additionalContext` on PreToolUse as of the May 2026 hooks release. The same hook works in both runtimes; the prior `agent-do-pretooluse-codex.py` suppress-stdout wrapper is obsolete and was removed. Codex users install a thin runpy pass-through at `~/.codex/hooks/agent-do-pretooluse-check.py` (shipped under `hooks/codex/`); the install handles this automatically.

**Nudge mode (default):** Adds `additionalContext`. The agent sees the reminder but the command still runs.

Examples:
- `npx playwright test` → `agent-do browse ...` + browser-install hint when relevant
- `xcrun simctl io booted screenshot` → `agent-do ios screenshot`
- `psql ...` → `agent-do db ...`

**Block mode (opt-in):** Change `additionalContext` to `permissionDecision: "deny"` in the hook output to block raw commands entirely. Claude Code supports the block decision; Codex parses it but does not enforce it yet (per the May 2026 hooks docs), so block mode is effectively Claude-only.

Intercepted commands include:
- `vercel`, `npx vercel`, `curl api.vercel.com`
- `supabase`, `npx supabase`, `curl supabase.co`
- `render services`, `curl api.render.com`
- `xcrun simctl`, `simctl`
- `adb shell/install/logcat`
- `osascript`, `automator`
- `docker ps/logs/exec/compose`
- `kubectl`, `ssh user@host`, `psql`, `mysql`
- `aws s3/ec2/lambda`, `gcloud`, `az vm/storage`
- ImageMagick, ffmpeg (image/video/audio)

Safe commands are skipped (git, npm, python, basic shell tools, localhost curl, etc.).

### Layer 4: Stop: Safe Auto-Commit

**Claude file:** `hooks/auto-commit.sh`
**Codex file:** `hooks/codex/auto-commit.sh` (adds coord-focus and env-var scoping)

Runs at the end of every agent turn. Auto-commits the work the agent just shipped so it never gets lost between sessions, tagged with the agent's session id for clean bisectable history.

**Safety: respects pre-commit hooks.** Never uses `--no-verify`. The flow:

1. Try a clean commit. If pre-commit passes, done.
2. If pre-commit auto-fixed files in place (black, ruff, prettier, eslint --fix), re-stage the modified files and retry once.
3. If commit still fails, leave the work staged, write a recovery breadcrumb at `.handoff/auto-commit-blocked-<session>.md`, fire a macOS notification (Basso sound), and exit non-zero.

The breadcrumb has the full pre-commit output, the staged file list, and recovery instructions. Work is recoverable; nothing is silently bypassed. Pre-commit hooks exist to catch real things (leaked secrets, broken syntax, lint violations); silently bypassing them is exactly the worst kind of automation failure.

**Codex scoping:** the Codex version restricts auto-commit to paths declared in `CODEX_AUTO_COMMIT_PATHS` / `AGENT_AUTO_COMMIT_PATHS` env vars or the current `agent-do coord focus` paths. A repo-wide focus is treated as a coordination signal, not a commit allowlist; the hook falls back to "commit staged files only" or "skip" rather than ever bulk-committing the whole tree.

## Registering Hooks in settings.json

Claude Code hooks must be registered in `~/.claude/settings.json`. They are NOT auto-discovered.

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/agent-do-session-start.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/agent-do-prompt-router.py",
            "timeout": 5
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/agent-do-pretooluse-check.py",
            "timeout": 5
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/auto-commit.sh",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

If you already have hooks in `settings.json`, merge the agent-do entries into the existing arrays for each event.

### Codex registration

Codex uses `~/.codex/hooks.json` instead of Claude's `settings.json`. The installer copies wrappers to `~/.codex/hooks/` and prints the registration template. The full template lives at `hooks/codex/hooks.json.example` and looks like:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.codex/hooks/agent-do-prompt-router.py",
            "timeout": 5,
            "statusMessage": "Checking agent-do routing"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.codex/hooks/agent-do-pretooluse-check.py",
            "timeout": 10,
            "statusMessage": "Checking agent-do tool preference"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.codex/hooks/stop-quality-gate.sh",
            "timeout": 30,
            "statusMessage": "Finalizing turn"
          }
        ]
      }
    ]
  }
}
```

The Codex wrappers under `~/.codex/hooks/` are thin: each one uses `runpy.run_path` to forward stdin/stdout to the matching repo hook at `<repo>/hooks/`. The repo is resolved via `AGENT_DO_REPO`, the `~/.agent-do/install-path` breadcrumb, or a `~/Custom-Coding/agent-do` fallback. Edits to the repo hooks flow through to Codex automatically; no reinstall needed.

## CLAUDE.md Integration

Add this to your project's `CLAUDE.md` so Claude knows about agent-do even without hooks:

```markdown
## agent-do (Universal Automation CLI)

BEFORE using raw commands (xcrun, adb, osascript, curl for APIs, etc.),
CHECK if agent-do has a tool:

    agent-do <tool> <command> [args...]   # Structured API (AI/scripts)
    agent-do -n "what you want"           # Natural language (humans)
    agent-do suggest "task"               # likely tool/command for a task
    agent-do suggest "task" --ai on        # require Sonnet-backed command selection
    agent-do suggest --project            # likely tools for this repo
    agent-do find <keyword>               # keyword search across tools
    agent-do creds check --tool <tool>    # check declared tool credentials
    agent-do creds store <ENV_VAR> --stdin # store a secret in the secure store
    agent-do spec list                    # list repo-local specs and changes
    agent-do spec status --change <id>    # inspect one change package
    agent-do --health                     # Dependency readiness
    agent-do bootstrap --recommend        # Detect pending project setup
    agent-do nudges stats                 # summary of hook nudges on this machine
    agent-do --list                       # List all 89 tools
    agent-do <tool> --help                # Per-tool help

Key tools: vercel, render, supabase, gcp, browse, ios, android, macos, tui, db,
docker, k8s, cloud, ssh, excel, slack, image, video, audio, git, gh, ci, zpc
```

## Nudge vs Block Mode

By default, hooks use **nudge mode** where the host supports it: they add context reminders but do not prevent commands from running. This is still the recommended approach because:

- Claude learns the pattern over a session (the reminder accumulates)
- No false positives blocking legitimate commands
- Users can override when agent-do isn't appropriate

The difference in `v1.1` is that the nudges are now more exact:
- prompt-time suggestions are AI-ranked from the full registered catalog and only surface concrete `agent-do <tool> <command>` paths when confidence is high
- PreToolUse nudges can point at the closest raw-command replacement
- SessionStart can suggest likely tools for the current repo instead of a generic static list
- local telemetry is available through `agent-do nudges stats|recent`

To switch Claude PreToolUse to **block mode**, edit `hooks/agent-do-pretooluse-check.py` and change the output from `additionalContext` to `permissionDecision: "deny"`. Do not use block mode for coord focus reminders; those need to be seen by the agent so it can set focus and continue.

## Architecture

```
Coding Agent Session
    │
    ├─ SessionStart ──→ agent-do-session-start.sh
    │   └─ Adds agent-do to PATH + injects project-aware tool reminder
    │
    ├─ UserPromptSubmit ──→ agent-do-prompt-router.py
    │   └─ AI-classifies prompt intent (coord / tools / docs / design /
    │     completion) and emits high-confidence context only. Silent when
    │     AI router is unavailable; state-grounded paths still fire.
    │
    ├─ PreToolUse (Bash) ──→ agent-do-pretooluse-check.py
    │   └─ One hook, both runtimes. Codex supports additionalContext as
    │     of May 2026; same nudge shows up in both Claude Code and Codex.
    │     Codex install adds a thin runpy wrapper at ~/.codex/hooks/.
    │
    └─ Stop ──→ auto-commit.sh
        └─ Safe-commit pattern: respects pre-commit hooks, retries once
          after auto-fix, fails loudly with .handoff breadcrumb + macOS
          notification. Codex variant adds coord-focus / env scoping.
```

All four hooks work independently. You can install any subset.

## Uninstalling

```bash
./install.sh --uninstall
```

This removes the symlink, breadcrumb, and hook files. You'll need to manually remove the hook entries from `~/.claude/settings.json`.
