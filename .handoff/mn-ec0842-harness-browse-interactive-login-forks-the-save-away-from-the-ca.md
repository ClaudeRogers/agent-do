---
workflow: 2
manna: mn-ec0842
track: mn-455a88
source: vms.io Strety capture 2026-08-21; Erik's two-week double-login reports; agent-browse source read
base_commit: 2bde3b6a5165c909ed53d6e0a84baad976e1efd4
scope: 'Harness: browse interactive login forks the save away from the canonical session name'
inputs:
- vms.io Strety capture 2026-08-21; Erik's two-week double-login reports; agent-browse source read
binding: sha256:17ab04acd22b82c47c96b81bba89371b7ae173ee4968dbde6ecfb6d42414ad8a
---

# Handoff: Harness: browse interactive login forks the save away from the canonical session name

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-ec0842
```

## Scope

Harness: browse interactive login forks the save away from the canonical session name

## Inputs

- vms.io Strety capture 2026-08-21; Erik's two-week double-login reports; agent-browse source read

## Work order

Root cause of Erik's two-week double-login pattern (vms.io Strety capture 2026-08-21 was the fourth incident). Mechanism, verified in source: resolve_save_target_name (tools/agent-browse/agent-browse:86) silently forks a save to <name>@<agent-session> whenever the plain name already exists and the daemon is agent-scoped — so a fresh human MFA login saved with 'login done --save strety' lands at strety@tmux-22 while the expired canonical stays enthroned. session load (agent-browse:1290) is literal — no fork awareness — so every other lane loads the stale canonical, hits the sign-in wall, and asks the human to log in again. Repair attempts recurse: 'session save strety' forks right back unless --shared is passed, reporting success:true with the real name buried in JSON.

Fix, three parts: (1) 'login done --save' defaults to --shared — a human-completed interactive login is inherently the shared credential; fork-on-write protection is for automated saves, never for an MFA ceremony. (2) Any save that forks must surface a top-level warning naming the fork and the --shared escape — a silent redirect reporting success is the killer. (3) 'session load <plain>' should warn when a fresher agent-scoped fork exists (staleness beats name purity); consider a 'session promote <name>@<agent>' verb to bless a fork into canonical.

Canonical strety was repaired manually 2026-08-21 (load strety@tmux-22 → save strety --shared → live-navigation verified authenticated). Interim rule until this ships: every login-done save carries --shared.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-ec0842`.
4. Commit with `Manna: mn-ec0842` and run `agent-do manna done mn-ec0842` only after the work is verified.
