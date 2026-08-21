---
workflow: 2
manna: mn-300dae
track: mn-b7a0cc
source: Erik bug report 2026-08-21; dm-ds convergence session + this session both hit it
base_commit: 314809bb4ecc8a849e9f3a3789819db628ce74c5
scope: 'Manna: dream needs --description — a spark is a title, not the whole idea'
inputs:
- Erik bug report 2026-08-21; dm-ds convergence session + this session both hit it
binding: sha256:19c8fe50409562c27c53419bf2950c3e957dcb01451103d3afc744e09d2bf092
---

# Handoff: Manna: dream needs --description — a spark is a title, not the whole idea

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-300dae
```

## Scope

Manna: dream needs --description — a spark is a title, not the whole idea

## Inputs

- Erik bug report 2026-08-21; dm-ds convergence session + this session both hit it

## Work order

Bug shape (hit twice on 2026-08-21, two different sessions including this one): manna dream takes a single positional spark used as the title, capped at 500 chars (issue.rs:225), with no --description argument. Agents naturally pass the full idea text as the spark; long text fails the title bound, short text strands the substance, and the workaround is a second call: dream then update --description. Ideas get filed as bare titles or not at all.

Fix, three parts: (1) add --description to the dream subcommand (main.rs Dream args, wired into issue creation like create's description). (2) When the spark exceeds the title bound, the error must teach the split: 'a spark is a title — put the substance in --description'. (3) Consider accepting the same convention as create (positional title + description) for symmetry; keep the single-arg form valid.

Interim workaround for all sessions: dream "<short title>" then manna update <id> --description "<full text>".

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-300dae`.
4. Commit with `Manna: mn-300dae` and run `agent-do manna done mn-300dae` only after the work is verified.
