# Codex hook bundle for agent-do

This directory ships the Codex-specific install bundle that mirrors what
`install.sh` does for Claude Code. The wrappers here use `runpy.run_path` to
forward to the canonical hooks at `<repo>/hooks/`, so a single source of truth
serves both surfaces. Codex supports `hookSpecificOutput.additionalContext` on
PreToolUse as of the May 2026 hooks release; the same nudges Claude Code sees
flow through.

## Install

```bash
mkdir -p ~/.codex/hooks
cp hooks/codex/agent-do-prompt-router.py    ~/.codex/hooks/
cp hooks/codex/agent-do-pretooluse-check.py ~/.codex/hooks/
cp hooks/codex/auto-commit.sh               ~/.codex/hooks/
chmod +x ~/.codex/hooks/auto-commit.sh

# Register the hooks (merge with any existing ~/.codex/hooks.json entries)
cp hooks/codex/hooks.json.example ~/.codex/hooks.json
```

`install.sh --codex` does this automatically when `~/.codex/` is present.

## What each file does

| File | Role |
|---|---|
| `agent-do-prompt-router.py` | Thin wrapper. `runpy.run_path` forwards stdin/stdout to the repo's `hooks/agent-do-prompt-router.py`. Emits AI-classified routing nudges. |
| `agent-do-pretooluse-check.py` | Thin wrapper. Forwards to the repo's `hooks/agent-do-pretooluse-check.py`. Emits raw-command nudges when an `agent-do` tool exists for the same job. |
| `auto-commit.sh` | Stop-event auto-commit with **safe-commit pattern**: no `--no-verify`, retries once after pre-commit auto-fix, fails loudly with `.handoff/auto-commit-blocked-<session>.md` breadcrumb + macOS notification when pre-commit really blocks. Includes coord-focus / env-var scoping so it never commits the whole repo on accident. |
| `hooks.json.example` | The Codex hook registration template. Copy to `~/.codex/hooks.json` and merge with existing entries. |

## What's in this bundle

| File | Role |
|---|---|
| `agent-do-session-start.py` | Codex SessionStart: project context, tooling reminder, bootstrap dialog with macOS notification + log on completion. |
| `agent-do-prompt-router.py` | Codex UserPromptSubmit: AI-classified routing nudges. |
| `agent-do-pretooluse-check.py` | Codex PreToolUse: raw-command nudges (`agent-do api` instead of `from anthropic import` etc.). |
| `screenshot-capture.sh` | Codex UserPromptSubmit: detects `ss` shorthand, attaches the latest screenshot. |
| `annotate.py` | Codex UserPromptSubmit: saves `#tag` / `#note` prompts as annotations. |
| `stop-quality-gate.sh` | Codex Stop dispatcher: runs `stop-quality-gate.py` for advisory DPT scoring, then chains to `auto-commit.sh`. |
| `stop-quality-gate.py` | Codex DPT scoring helper used by the dispatcher. |
| `auto-commit.sh` | Codex Stop: safe-commit pattern with coord-focus / env-var scoping. |
| `hooks.json.example` | The Codex hook registration template. Copy to `~/.codex/hooks.json` and merge with existing entries. |

## Repo resolution

The wrappers look for the repo in this order:

1. `AGENT_DO_REPO` environment variable
2. `~/.agent-do/install-path` breadcrumb (written by `install.sh`)
3. `~/Custom-Coding/agent-do` default fallback (edit the wrapper if your clone is elsewhere)

## Auto-commit safety

`auto-commit.sh` **respects pre-commit hooks**. It never uses `--no-verify`.
Flow:

1. Try a clean commit. If it succeeds, done.
2. If pre-commit hooks auto-fixed files in place (formatters, linters with
   `--fix`), re-stage and retry once.
3. If commit still fails, write `.handoff/auto-commit-blocked-<session>.md`
   with the pre-commit output and staged file list, fire a macOS notification
   (Basso sound), exit non-zero. The work stays staged; you recover by
   reviewing the breadcrumb and committing manually.

This is opt-in safety. The auto-commit habit stays; silent bypass goes.
