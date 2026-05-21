# Engineering Spec: agent-gh Review Doctrine + Merge Gates

## Problem

`agent-do gh` exposes the PR review surface (`pr`, `diff`, `threads`, `checks`,
`audit`, `review`, `approve`, `request-changes`, `merge`) but does not encode
*how* a review should be conducted. Quality depends entirely on the calling
agent's own discipline. Two concrete gaps:

1. `cmd_merge` runs `gh pr merge` with no preconditions — it will merge a PR with
   failing checks, unresolved review threads, or no recorded approval.
2. `cmd_review_summary` (`gh review <n>`) prints counts only. It does not tell
   the agent which changed files carry risk, and it carries no guidance on
   review conduct or voice.

The result: review quality is uneven across agents. A disciplined agent reviews
well; a terse one rubber-stamps. The doctrine that produces good reviews lives
in operator headspace, not in the tool.

## Goal

Bake review discipline into `agent-gh` so it is the default behavior for every
agent and every PR, in any repo, for anyone who downloads agent-do. Split into:

- **Mechanical gates** — deterministic preconditions the tool enforces.
- **Doctrine** — a versioned guidance text the tool surfaces on every review.

## Non-goals

- The tool does not review code. Judging correctness, writing comments, and
  voice remain the agent's work. The tool gates and guides; it does not think.
- No change to `audit`, `diff`, `threads`, `checks`, `inbox`, `awaiting`.
- No repo-specific or person-specific context baked in (that stays per-invocation).

## Components

### C1. Risk classifier — `classify_risk(paths) -> RiskReport`

Pure function. Maps each changed path to a risk tier by pattern match.

Tiers:

| Tier | Meaning | Example patterns |
|---|---|---|
| `critical` | Security / authorization / data-integrity surface | `middleware.`, `/auth`, `auth.(ts\|js\|py)`, `rate.?limit`, `/rls`, `migrations?/`, `.sql$`, `secret`, `credential`, `token`, `session`, `crypto`, `password`, `cors`, `csp`, `permission` |
| `elevated` | Build / deploy / dependency surface | `.github/workflows/`, `Dockerfile`, `render.yaml`, `vercel.json`, `*.tf`, `package.json`, `*-lock.*`, `requirements.txt`, `Cargo.toml`, `.env*`, `next.config.*` |
| `standard` | Everything else | — |

Patterns are case-insensitive, matched against the full repo-relative path.
Highest matched tier wins for the path. The report's overall `tier` is the
highest tier present across all paths.

`RiskReport` shape:

```json
{
  "tier": "critical",
  "counts": { "critical": 2, "elevated": 1, "standard": 4 },
  "signals": [
    { "path": "apps/web/middleware.ts", "tier": "critical", "reason": "auth perimeter" },
    { "path": "apps/web/lib/rate-limit.ts", "tier": "critical", "reason": "rate limiting" },
    { "path": "render.yaml", "tier": "elevated", "reason": "deploy config" }
  ]
}
```

`signals` lists only `critical` and `elevated` paths (the ones worth the agent's
attention); `standard` paths are counted but not enumerated.

### C2. `gh review <n>` enrichment

`cmd_review_summary` is extended. It remains the "start a review" entrypoint.

Behavior added:
- Compute `classify_risk(changed_paths(detail))`.
- Text mode: print the existing summary, then a `Risk:` section listing the
  overall tier and each `critical`/`elevated` signal, then the doctrine
  (see C5) as a trailing block.
- JSON mode: add `risk` (the `RiskReport`) and `doctrine` (the doctrine text)
  keys to the payload.

`gh review <n>` becomes the single call that hands an agent everything it needs
to start: PR shape, check/thread state, risk classification, and the doctrine.

### C3. `gh merge` gates

`cmd_merge` is extended. Before invoking `gh pr merge`, it calls
`merge_gate(ref) -> GateResult`.

`merge_gate` fetches `pr_detail`, `pr_checks`, `pr_threads` and evaluates:

| Gate | Condition | Result |
|---|---|---|
| `checks` | any check in fail bucket | **block** |
| `threads` | any unresolved review thread | **block** |
| `mergeable` | `merge_state` not in {CLEAN, UNKNOWN} | **block** |
| `approval` | `review_decision` != APPROVED | **block** |
| `risk` | risk tier == `critical` | **warn** — requires `--confirm-risk` |

`GateResult` shape:

```json
{
  "allowed": false,
  "blocks": [
    { "gate": "checks", "reason": "2 checks failing: build, web-test" },
    { "gate": "approval", "reason": "no approving review recorded" }
  ],
  "warnings": [
    { "gate": "risk", "reason": "critical-tier paths changed (middleware.ts, rate-limit.ts) — pass --confirm-risk after tracing control flow" }
  ]
}
```

Merge proceeds only when `blocks` is empty AND every `risk` warning is cleared
by `--confirm-risk`. Otherwise `cmd_merge` prints the `GateResult` and exits 2
(the established "needs action" code) without calling `gh pr merge`.

Escape hatch: `--force` clears all `blocks`. When used, the tool prints a loud
single-line notice naming each gate bypassed, and the bypass is recorded via
the existing telemetry path. `--force` does not suppress the printed reasons.
`--confirm-risk` clears only the `risk` warning, never a `block`.

### C4. `gh doctrine` command

New leaf command. Prints `REVIEW_DOCTRINE` to stdout. No arguments. Exists so
the doctrine is inspectable on its own and so other tooling can surface it.

### C5. `REVIEW_DOCTRINE`

A module-level string constant in `tools/agent-gh`. Versioned with the tool
(single-file tool — the constant is the canonical, git-tracked copy). Editable
by editing the constant. Content is the universal review doctrine: chain
ownership, diff-over-description, verify-before-bless, risk-tiered scrutiny,
review voice, the pass/fixable/judgment decision rule, merge hygiene. It
carries no repo-specific or person-specific context.

Full proposed text is reviewed separately before implementation (operator
sign-off on voice required).

## Command surface — before / after

| Command | Before | After |
|---|---|---|
| `gh review <n>` | PR + check + thread counts | + risk classification + doctrine |
| `gh merge <n>` | runs `gh pr merge` unconditionally | gated; blocks on failing checks / unresolved threads / dirty merge state / missing approval; warns on critical risk |
| `gh doctrine` | — | new; prints `REVIEW_DOCTRINE` |
| `gh audit <n>` | unchanged | unchanged (deep findings pass; complementary to the gate) |

New flags on `gh merge`: `--force` (clear blocks, loud), `--confirm-risk`
(clear the critical-risk warning).

## Relationship to `gh audit`

`audit` and the merge gate are complementary, not duplicative:
- `audit` is the deep, heuristic findings pass — lockfile blast radius, Sentry
  config, env wiring, etc. — producing a `verdict`. The agent runs it during
  review.
- `merge_gate` is the narrow, fast, deterministic precondition check at the
  moment of merge. It does not re-run audit heuristics; it checks the four
  hard preconditions plus the risk tier.

The risk classifier (C1) is shared: `audit_pr` gains a `risk` field in its
output using the same `classify_risk` function, so the deep pass and the gate
agree on what is critical.

## Data shapes (JSON mode)

`gh review <n> --json`:

```json
{
  "pr": { "...": "existing pr_detail" },
  "checks": { "count": 0, "items": [] },
  "unresolved_threads": { "count": 0, "items": [] },
  "risk": { "...": "RiskReport (C1)" },
  "doctrine": "REVIEW_DOCTRINE text"
}
```

`gh merge <n>` on a blocked merge (exit 2):

```json
{ "...": "GateResult (C3)" }
```

## Testing

`tests/test_gh.py` is extended (no new test file):

- `classify_risk`: critical paths (`middleware.ts`, `*.sql`, `auth.ts`),
  elevated paths (`render.yaml`, `package-lock.json`), standard paths, mixed
  set → correct overall tier and counts.
- `merge_gate`: each block fires independently (mock detail/checks/threads);
  clean PR yields `allowed: true`; critical risk yields a `risk` warning;
  `--force` clears blocks; `--confirm-risk` clears only the warning.
- `gh review --json` includes `risk` and `doctrine` keys.
- `gh doctrine` prints non-empty text.
- All mock-based — no live GitHub calls, consistent with existing `test_gh.py`.

## Registry

`registry.yaml` `gh` entry: add `doctrine` to `commands`; note the gated
`merge` and risk-aware `review` in `capabilities`. No routing or credential
changes.

## Acceptance criteria

- `gh merge` on a PR with a failing check exits 2 and does not merge.
- `gh merge` on a PR with unresolved threads exits 2 and does not merge.
- `gh merge` on a PR with no approving review exits 2 and does not merge.
- `gh merge --force` on the same PR merges and prints the bypassed gates.
- `gh merge` on a critical-risk PR without `--confirm-risk` exits 2; with it,
  and no blocks, merges.
- `gh review <n>` surfaces the risk tier and the doctrine.
- `gh doctrine` prints the doctrine standalone.
- `./test.sh` passes with the extended `test_gh.py`.
