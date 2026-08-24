---
workflow: 2
manna: mn-e209fb
track: mn-455a88
source: 'session 2026-08-24, zpc global-layer audit and prune; Erik: how do we make zpc global lessons record only the correct things and apply them at the right time'
base_commit: 59804a1867f81d683fe1a51091ac25a36c9e0a27
scope: 'zpc: global lessons earn entry (rule + why + when) and fire on trigger, not at session start'
inputs:
- 'session 2026-08-24, zpc global-layer audit and prune; Erik: how do we make zpc global lessons record only the correct things and apply them at the right time'
binding: sha256:619e21488d29f24a682345c4749faeb0bb7b86e58b6482bd6143358415116546
---

# Handoff: zpc: global lessons earn entry (rule + why + when) and fire on trigger, not at session start

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-e209fb
```

## Scope

zpc: global lessons earn entry (rule + why + when) and fire on trigger, not at session start

## Inputs

- session 2026-08-24, zpc global-layer audit and prune; Erik: how do we make zpc global lessons record only the correct things and apply them at the right time

## Work order

Erik's ruling 2026-08-24: global lessons must earn their weight in gold and saffron; after the prune the machine-wide store holds two. Three mechanisms, one item. (1) Entry gate: promote --to global refuses (exit 2, writes nothing, same shape as position add without --falsifier) unless the row carries a rule stated as an instruction, a why, and a when (the trigger: prompt words, a command about to run, a path glob, or a moment such as before-commit), plus a cross-project receipt (--seen-in two or more projects, or --scope machine|user); machine-generated rows are never eligible. (2) Delivery on trigger: each global lesson's when is matched by the hooks that already fire at those moments (UserPromptSubmit prompt router, PreToolUse Bash, PostToolUse Edit/Write, pre-commit guard) and that one lesson is injected right then; SessionStart carries only the count and any when:always rows, which should be near zero. This is the answer to mn-7ec6dc's third question (how does AI know now is the time, months from now): the situation summons the lesson, never the name. (3) Exit: a lesson that fires and is ignored repeatedly, or is challenged, jumps the re-litigation queue; lesson delivery rides the existing harness nudges effectiveness telemetry (follow/ignore/expire). The bar in one sentence: a rule with its reason and its trigger, proven beyond one project, and the whole global set fits on one screen. New fields and a changed verb: taxonomy gate applies, nothing built until Erik greenlights the shape.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-e209fb`.
4. Commit with `Manna: mn-e209fb` and run `agent-do manna done mn-e209fb` only after the work is verified.
