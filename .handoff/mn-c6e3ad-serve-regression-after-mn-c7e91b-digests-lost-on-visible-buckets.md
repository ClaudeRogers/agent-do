---
workflow: 2
manna: mn-c6e3ad
track: mn-b7a0cc
source: 'Erik live report + read-only audit 2026-08-31 19:0x (screenshot: aldebaran-group cockpit); regression from mn-c7e91b commit 239d00f'
base_commit: 37d57a5e98be32ddf75f33014031e246020fd904
scope: 'serve regression after mn-c7e91b: digests lost on visible buckets, live reconcile per state, stalled first paint'
inputs:
- 'Erik live report + read-only audit 2026-08-31 19:0x (screenshot: aldebaran-group cockpit); regression from mn-c7e91b commit 239d00f'
binding: sha256:0eca875846cd52bf63a52bed40c2e4c1782b8f31e440b06b708d9c29b45ffed2
---

# Handoff: serve regression after mn-c7e91b: digests lost on visible buckets, live reconcile per state, stalled first paint

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-c6e3ad
```

## Scope

serve regression after mn-c7e91b: digests lost on visible buckets, live reconcile per state, stalled first paint

## Inputs

- Erik live report + read-only audit 2026-08-31 19:0x (screenshot: aldebaran-group cockpit); regression from mn-c7e91b commit 239d00f

## Work order

Regression audit of 239d00f (manna state --json rebase), verified live 2026-08-31 evening against aldebaran-group (243 rows). FOUR FINDINGS. (1) DIGEST COLUMN SHOWS RAW TITLES: digest_lib.apply(slug, state['all']) decorates only all[] (serve.py:445 and fast_state). The old Python derive built now/next/waves/dreams/decisions/tracks as references to the same row dicts, so decorating all[] decorated every bucket; the Rust core serializes each bucket as an independent copy, so every visible sheet (rowText = r.digest || r.title, app.js:31) falls back to titles. Receipt: live /aldebaran-group/api/state has all[0].digest=true while now[0]/next[0]/waves[0].items[0]/dreams[0]/decisions[0]/tracks[0].items[0] all lack digest. Fix direction: apply digests to every bucket, or re-share references, or have apply() index by id across the whole state. (2) LIVE RECONCILE ON EVERY FULL STATE: CACHE.state() calls board_lib.derive(root, AGENT_DO, markers, live=True) (serve.py:437) which omits --cached-drift, so each signature change pays a full live reconcile. Measured: manna-core state --json --cached-drift = 2.1s vs live = 35.9s on aldebaran; end-to-end /api/state = 41.6s. The pre-rebase serve NEVER ran reconcile (old board.py docstring: reads the drift file the last reconcile left behind). Consequences: first full paint 40-60s behind the fast=1 snapshot, SSE first push serialized behind the same recompute (serve.py:783-785), summary/ask requests queued behind it (observed: summary endpoint exceeded 30s before answering). Also a semantics change: drift/inbox now reflect a fresh reconcile (aldebaran live drift count 10759) instead of the cached advisory file. Fix direction: full state uses --cached-drift too; live reconcile only on explicit action. (3) STRIP SAYS RECONCILE UNAVAILABLE during the long fast window: app.js:555 shows it when drift.source != reconcile and !drift.present; fast_state's cached-drift payload reports present=false on boards without a fresh drift.yaml, and because of (2) the correcting full state arrives ~40-60s late or never before the next churn. (4) FAST STATE OMITS the digests block (digests: None) and introduces building:true, which the untouched front-end does not know — no loading indication during the gap. TEST GAP: the 41-test serve suite passed through all of this — it pins payload shape, not cross-bucket digest decoration, first-paint latency, or the live-vs-cached drift mode. Add regression coverage for each finding.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-c6e3ad`.
4. Commit with `Manna: mn-c6e3ad` and run `agent-do manna done mn-c6e3ad` only after the work is verified.
