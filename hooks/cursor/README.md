# Cursor hook bundle for agent-do

Cursor adapters that translate Cursor's hook JSON into the canonical Claude
hooks under `hooks/claude/`, then translate responses back into Cursor's
`additional_context` / `continue` / `permission` fields.

## Install

From the agent-do repo root:

```bash
./install.sh --cursor
```

Or manually:

```bash
mkdir -p ~/.cursor/hooks
cp hooks/cursor/*.py ~/.cursor/hooks/
chmod +x ~/.cursor/hooks/*.py
cp hooks/cursor/hooks.json.example ~/.cursor/hooks.json   # merge if one exists
```

Restart Cursor after installing. Open **Settings → Hooks** to confirm the
three agent-do entries appear under **User config**.

## Files

| File | Cursor event | Delegates to |
|------|--------------|--------------|
| `agent-do-session-start.py` | `sessionStart` | `hooks/claude/agent-do-session-start.sh` |
| `agent-do-prompt-router.py` | `beforeSubmitPrompt` | `hooks/claude/agent-do-prompt-router.py` |
| `agent-do-pretooluse-check.py` | `preToolUse` (matcher: `Shell`) | `hooks/claude/agent-do-pretooluse-check.py` |
| `cursor_compat.py` | shared | JSON translation + repo resolution |
| `hooks.json.example` | registration | copy/merge into `~/.cursor/hooks.json` |

## Upgrade model

The adapters resolve the repo via `AGENT_DO_REPO` or `~/.agent-do/install-path`,
then subprocess the canonical Claude hooks. After `git pull`, hook behavior
updates on the next event without reinstalling — unless the adapter files
themselves change, in which case re-run `./install.sh --cursor`.

## Composer / Agent

Cursor's **Agent** mode (the multi-step agent formerly called Composer) uses
the same hook events:

- starting a new Agent chat → `sessionStart`
- each user message → `beforeSubmitPrompt`
- each `Shell` tool call → `preToolUse`

Tab inline completions use different events (`beforeTabFileRead`, `afterTabFileEdit`).
agent-do does not register Tab hooks.

## Avoid duplicate hooks

Cursor loads **two** hook sources:

1. **User config** — `~/.cursor/hooks.json` (Cursor adapters)
2. **Claude user config** — `~/.claude/settings.json` (same file Claude Code uses)

If both register agent-do, hooks run twice. The Claude wrappers no-op for Cursor
payloads, but still execute.

## `sessionStart` and `~/.claude/settings.json`

**Do not register `SessionStart` in `~/.claude/settings.json` while using
Cursor.** Cursor reads that file as Claude user config and fires `sessionStart`
before `MainThreadShellExec` is ready, producing:

```text
Error: MainThreadShellExec not initialized
```

Remove `SessionStart` from `settings.json` for Cursor. Keep `beforeSubmitPrompt`
and `preToolUse` in `~/.cursor/hooks.json`. Restore `SessionStart` in
`settings.json` only when using the Claude Code app.

See `docs/INTEGRATION.md` → "sessionStart startup race" for the full timeline.
