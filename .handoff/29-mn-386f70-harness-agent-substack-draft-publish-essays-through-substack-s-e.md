---
workflow: 2
manna: mn-386f70
track: mn-b7a0cc
source: Erik request 2026-08-22; substack-writings posting session transcript
base_commit: 718c096d25e8e8c0626714529f1e64b3f59dd296
scope: 'Harness: agent-substack — draft/publish essays through Substack''s editor API'
inputs:
- Erik request 2026-08-22; substack-writings posting session transcript
binding: sha256:d033bd549132905280b8ca01190f54f06b833c71e6bde41c6c1459cc072176af
---

# Handoff: Harness: agent-substack — draft/publish essays through Substack's editor API

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-386f70
```

## Scope

Harness: agent-substack — draft/publish essays through Substack's editor API

## Inputs

- Erik request 2026-08-22; substack-writings posting session transcript

## Work order

Requested by Erik 2026-08-22 (substack-writings session fell back to raw browse for a post). Substack has no official write API; the web editor drives unofficial JSON endpoints (POST /api/v1/drafts, PUT /api/v1/drafts/:id, POST .../publish; body is a ProseMirror doc). Tool shape, five beats: connect = auth riding the shared browse session (browse login once, session save substack --shared; agent-auth profile later); snapshot = publication info + drafts + recent posts; interact = draft <file.md> --title --subtitle (markdown→ProseMirror converter is the real work), update, publish <id>; verify = read the draft/post back by id and compare; save = post URL + receipt. SAFETY: publish is outward-facing — attributes destructive+sensitive, default deliverable is a DRAFT Erik reviews in the Substack UI; publish only on explicit command. No new pip dependency: requests + cookies from the browse session (python-substack exists but adds a dependency for little — our own thin client keeps auth unified with browse). Registry entry + contracts block + routing metadata ('post to substack' routes here) + bounds declarations, per Adding Tools. Interim, already true today: browse login https://substack.com then session save substack --shared gives every lane a shared login the tool will inherit.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-386f70`.
4. Commit with `Manna: mn-386f70` and run `agent-do manna done mn-386f70` only after the work is verified.
