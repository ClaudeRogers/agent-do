# Lane NN: <one line naming the lane's territory and what changes in it>

<!--
CANONICAL LANE PROMPT. Copy this file to `NN-SLUG.md` (continue the directory's
numbering) and replace every <ANGLE BRACKET> placeholder. Delete no section: a
section with nothing to say says "none", because a missing section reads as an
oversight and an agent will go looking for it.

Two rules the whole format exists to enforce:

  1. Lanes split by FILE OWNERSHIP, never by phase. Each lane reads, writes, and
     verifies its own scope to completion. "Agent 1 researches, agent 2 builds,
     agent 3 tests" is not a swarm, it is a relay race with three chances to
     drop the baton.
  2. The prompt is self-contained. The agent receiving it has no memory of the
     planning conversation, cannot see the other lanes, and cannot ask you a
     question mid-flight. Anything it needs must be ON this page or reachable
     by a command ON this page.

Pairing (both directions, or the staging is not done):
  - the issue points here:  agent-do manna update <mn-ID> --prompt <absolute path to this file>
  - this file opens with the exact claim commands for that issue
`agent-do manna reconcile` flags either half when it dangles.
-->

## Claim first

```bash
cd <ABSOLUTE REPO PATH>
agent-do manna claim <mn-ID>
agent-do coord touch
agent-do coord focus set "<short goal>" --path <owned path> [--path <owned path>...]
agent-do coord claim <primary owned path> --reason "lane NN: <why>"
```

## Repo

`<ABSOLUTE REPO PATH>`

## Project memory (MANDATORY — orchestrator pastes the real output here)

<!--
Paste the LITERAL output of the command below into this section before handing
the prompt to an agent. Do not summarize it, do not link to it, do not tell the
agent to run it: a fresh agent that has to fetch its own context usually does
not, and the swarm relearns what the project already knows. The bound exists so
this stays a section, not a chapter.

    agent-do zpc inject --compact     # 2000-char bound, patterns + top lessons
                                      # truncation marker: [zpc inject truncated]

If the repo has no `.zpc` store, write "none (no .zpc store in this repo)" and
move on. If the compact flag is unavailable in the checkout you are staging
from, `agent-do zpc patterns` is the fallback, trimmed by hand to the same bound.
-->

```
<PASTE `agent-do zpc inject --compact` OUTPUT VERBATIM>
```

## Mission

<WHAT CHANGES AND WHY, in a paragraph a stranger can act on. Name the failure
the lane closes, not the feature it adds. Then the deliverables, numbered:>

1. **<Deliverable>.** <Observable end state. What exists, where, behaving how.>
2. **<Deliverable>.** <Same.>

## Owned paths

- `<path>` <(new) if it does not exist yet>
- `<path>`

Non-owned neighbors (do NOT edit): `<path>` (<lane N>), `<path>` (<lane N>).

<!--
Name the neighbors and their owners explicitly. "Everything else" is not a
boundary an agent can check itself against. Overlapping writers get a coord
contention interrupt, but the prompt should make the overlap impossible first.
-->

## Ground truth (verified this session, <YYYY-MM-DD>)

<!--
Every line here is something you CHECKED against the source during this
staging session. Not remembered, not copied from an earlier report, not
inferred from a filename. A stale `file:line` costs the agent more than no
line at all, because it spends its first minutes trusting it.
-->

- `<file>:<line>` — <what is there and why the lane needs it>
- <Frozen behavior the lane must not change, and how you confirmed it is frozen>
- <Convention to follow, with the existing example to copy>
- <Anything the agent must verify for itself, said plainly: "verify X against
  the live system; do not guess.">

## Integration contract (pinned verbatim; lanes <N>/<N> consume it)

<!--
The exact strings shared across lanes: env var names, file paths, filenames,
markers, exit codes, kill-switches, schemas. Verbatim in every prompt that
touches them. This section is why parallel lanes converge instead of colliding,
so copy it between prompts character for character rather than paraphrasing.
-->

- <Pinned name/path/marker and its meaning>
- <Kill-switch and its default>
- <What stays frozen: exit codes, schemas, output shapes>

## Verification (run before `done`)

<!--
Numbered, each one a command or an observation with a pass condition. The agent
runs ALL of them before closing the issue and reports literal output. "Tests
pass" is not a verification step; the command and its result are.
-->

1. <Command → expected observable result>
2. <Command → expected observable result>
3. <Regression check: the thing most likely to break silently>
4. <Gate: `./test.sh`, `./agent-do harness contracts validate`, `bash -n`, as applicable>

## Out of scope

<Everything adjacent and tempting that belongs to another lane or another day.
Name the other lane where it lives. An agent that knows where the work went
does not do it "just quickly".>

## On completion

```bash
agent-do manna done <mn-ID>
agent-do coord publish add <short-key> --status ready --summary "<what is now true>"
```

Commit (Conventional Commits) trailer: `Manna: <mn-ID>`.

<!--
Staging is finished when all three artifacts exist: the manna issues (real
`mn-` ids, quoted from the CLI, never invented), one prompt file per lane, and
the lane table whose launch column names gates ("Wave B, after 01 + 02") rather
than durations.
-->
