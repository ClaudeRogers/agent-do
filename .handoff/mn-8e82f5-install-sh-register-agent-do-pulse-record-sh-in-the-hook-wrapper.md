---
workflow: 2
manna: mn-8e82f5
track: mn-b7a0cc
source: null
base_commit: 7e43f285241ee687a4c42e0f62638e3748c3fc3a
scope: 'install.sh: register agent-do-pulse-record.sh in the hook wrapper list'
inputs: []
binding: sha256:18808ac7d0083e21b39831072bfaa38eddac8dd7541a6bcce334e2d9b963ef10
---

# Handoff: install.sh: register agent-do-pulse-record.sh in the hook wrapper list

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-8e82f5
```

## Scope

install.sh: register agent-do-pulse-record.sh in the hook wrapper list

## Inputs

- None declared.

## Work order

Follow-up to mn-1f446f: install.sh was dirty from another active lane during the pulse build, so the wrapper was hand-installed to ~/.claude/hooks and registered in settings.json directly. Add the pulse hook to install.sh's CLAUDE_HOOKS list (events: UserPromptSubmit, PreToolUse, PostToolUse, Notification, Stop, StopFailure, SessionEnd) once that file is free, so fresh installs get it

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-8e82f5`.
4. Commit with `Manna: mn-8e82f5` and run `agent-do manna done mn-8e82f5` only after the work is verified.
