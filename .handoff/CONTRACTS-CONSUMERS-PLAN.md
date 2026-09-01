# Contracts Go Load-Bearing: the consumers milestone

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Split by file ownership per workstream — see §3.

**Goal:** Make the v1.3 contract declarations consumed and enforced — behavior audited, drift detected, concurrency derived, routing informed — so an agent can *trust* the registry instead of merely reading it.

**Architecture:** Five consumers over the existing `contracts:` data, plus one trunk of registry reconciliation that verification proved must land first. All engines live in `lib/contracts*.py`; live orchestration stays in `tools/agent-harness` (owns `agent_do_cmd` runner). Everything is additive — no CLI renames, no schema breaks except one new attribute (`own_state`).

**Tech stack:** Python 3.11 (lib/, harness, tests), bash (tools), PyYAML, existing test.sh harness + GitHub Actions.

**Verification basis (2026-06-12, 5-agent fan-out against HEAD `534b177`):** every anchor below was checked against live code; the dry runs in §1 were executed against the real registry and all 94 tools.

---

## 0. TL;DR

v1.3 declared the contracts; nothing consumes them. This milestone builds the consumers — and verification found the registry itself isn't yet clean enough to enforce against:

- **23 declared-but-unimplemented verbs across 17 tools** (the `metrics` class is bigger than we knew: `slack read`, `dns update/list`, `manna update/delete`, `macos tree`, `discord read/join`, …) — found by a drift-parser dry run with **0 false positives over all 94 tools**.
- **15 concurrency violations** the new validator rule would flag today: 4 genuine (`dns`, `usb`, `creds`, `clipboard` are `read` but mutate shared state), 11 misfires (tools whose only writes touch their *own* cache — needs a new `own_state` attribute).
- The audit's safely-probeable surface: 452 read-pure verbs → ~376 zero-arg → **~108 local-safe**, 73 session-gated (clean-error), 164 network/credential (UNBOUNDED curl — must be opt-in), 6 hang-risk (`wait`/`scan`), ~25 prose-stated-arg traps.

So the dependency graph is: **WS-A (reconcile registry) is the trunk**; the validator rule (WS-B) and drift CI gate (WS-D2) hang off it; surface (WS-C), audit (WS-E), and routing (WS-F) fan out in parallel from day one.

---

## 1. What verification established (facts the plan is built on)

**Anchors (current as of `534b177`):**
- `lib/registry.py:16` CONTRACT_BEATS; `:25-32` CONTRACT_ATTRIBUTES; `:34` _BEATLESS_ATTRIBUTES; `:188` get_tool_contracts; `:206` get_tool_contract_attributes; `:225` _contract_command_exists (first-token matching); `:233-317` validate_tool_contracts (multi_beat loop ends `:314`, `ok` set `:316`); `:320` validate_registry_contracts; `:102-122` build_registry_context (catalog = 29,612 chars ≈ 7.4k tokens, shipped whole on every LLM route, no budget guard).
- `bin/intent-router:98-179` route_intent (cache return `:110-113`, fuzzy `:115-118`, LLM `:173-179`); `:160` **model still hardcoded `claude-opus-4-5-20251101`**; `:194-339` execute() builds 6 separate output dicts; cache persists the *entire* result dict (`lib/cache.py:230`) and replays it verbatim on hits.
- `bin/pattern-matcher:219-255` match_intent convergence.
- `lib/telemetry.py:103` append_event(event_type, source, **payload) → events.jsonl.
- `tools/agent-harness` (single 1049-line file): `agent_do_cmd(*args, timeout=10)` at `:110` (returns rc=124 on timeout, sets AGENT_DO_TELEMETRY_SUPPRESS=1); build_parser `:915`; contracts subparser `:958-963` (choices `["validate","propose"]` at `:959`); dispatch `:1011-1036`; help text `:900-901`.
- `lib/contracts.py` (300 lines): safety-surface aggregation **inlined** in render_markdown `:177-194` (markdown-coupled — must be extracted); propose_tool_contracts `:92` short-circuits declared tools (drift needs a bypass).
- `registry.yaml`: harness commands map `:3210-3215`, harness contracts block `:3252-3261`.
- Gate state: `lib/contracts-baseline.yaml` deleted; `tests/test_contracts_gate.py:137-142` asserts errors==0/ok, `:167-174` strict-era asserts warnings==0. **Any new error OR warning reds the gate** — reconciliation must precede the rule.

**Dry-run results:**
- Concurrency rule (read + write-beat verb → error): **15 tools flagged**: clipboard, creds, debug, dns, dpt, eval, figma, ghidra, ide, pdf2md, prompt, tail, usb, vision, wireshark. Classes 2 (write w/o write verbs) and 3 (mixed all-read): zero.
- Drift declared-only channel: **23 tokens / 17 tools**, all manually verified genuine: slack `read`; dns `update`,`list`; manna `update`,`delete`; macos `tree`; discord `read`,`join`; calendar `delete`; clipboard `history`; cloud `deploy`,`logs`; colab `new`; debug `backtrace`; figma `inspect`,`list`; homekit `scene`; jupyter `export`,`kernel`; logs `filter`; obsidian `refresh`; pdf `extract`; sheets `create`. Help-only channel: 431 tokens — **intentional curation, advisory only, never gate on it**.
- Audit probe of local-safe verbs: none hung; all bounded. But: `manna list --json` exits 2 with empty output (broken); `unbrowse status --json` and `swarm status --json` emit prose (flag ignored). Cloud tools (render, vercel, supabase, cloudflare, clerk, okta, namecheap, resend, gcp) use curl with **no --max-time and no lib/retry.sh** — unbounded.
- gcp is the only tool with multi-word registry command keys (`auth status`) — drift matcher must check first-token AND full-path sets.

---

## 2. Workstreams

### WS-A — Registry reconciliation (THE TRUNK)

**Files:**
- Modify: `registry.yaml` (17 tool entries for drift; 4 + 11 entries for concurrency; contracts blocks accordingly)
- Modify: `lib/registry.py:25-32` (add `own_state` to CONTRACT_ATTRIBUTES)
- Modify: `lib/contracts-lexicon.yaml` (overrides for the 11 own_state verbs so propose stays in sync)
- Test: `tests/test_contracts_gate.py` (vocabulary assertion update)

- [ ] **A1: Add `own_state` to the attribute vocabulary — test first.**
  In `tests/test_contracts_gate.py` `check_attribute_schema`, update the vocabulary assertion:
  ```python
  require(
      set(CONTRACT_ATTRIBUTES)
      == {"destructive", "long_running", "polymorphic", "composite",
          "sensitive", "passthrough", "own_state"},
      f"unexpected attribute vocabulary: {CONTRACT_ATTRIBUTES}",
  )
  ```
  Run: `python3 tests/test_contracts_gate.py` → FAIL (vocabulary mismatch).
  Then in `lib/registry.py` CONTRACT_ATTRIBUTES add:
  ```python
      "own_state",   # writes confined to the tool's own cache/state/derived
                     # output — parallel-safe relative to other tools
  ```
  Run again → PASS. Commit: `feat(contracts): own_state attribute for self-confined writes`

- [ ] **A2: BUILD the 23 promised verbs (Erik's call: implement, don't delete).** The registry's promises become real. One sub-task per tool, independently ownable (file ownership = `tools/agent-<name>` + its test + registry entry), TDD per verb: failing test → minimal implementation matching the registry description → help text → contracts block already declares it → green. The 17 tools and their owed verbs:
  - `slack read` (read channel via existing token surface) · `dns update`, `dns list` · `manna update`, `manna delete` (Rust — cargo test) · `macos tree` (accessibility tree dump; macos_ops already walks AX elements) · `discord read`, `discord join` · `calendar delete` · `clipboard history` · `cloud deploy`, `cloud logs` · `colab new` · `debug backtrace` · `figma inspect`, `figma list` · `homekit scene` · `jupyter export`, `jupyter kernel` · `logs filter` · `obsidian refresh` (verify against current obsidian surface — may exist under another name) · `pdf extract` · `sheets create`.
  - Escape hatch per verb: if implementation proves infeasible as promised (e.g. an API surface that doesn't exist), remove the verb + file a manna issue with the evidence — but the default is BUILD.
  - Each sub-task runs `./agent-do <tool> --help` + the tool's test + `harness contracts drift --tool <name>` (once D1 lands) to confirm the promise is honored.
  Run after all: `./agent-do harness contracts validate --strict` → PASS; drift declared-only channel → empty.
  Commits: one per tool, `feat(<tool>): implement promised <verbs>`

- [ ] **A3: Correct the 4 genuine concurrency lies.** `dns` (update mutates provider records), `usb` (mount/eject mutate the OS mount table), `creds` (store/delete/export mutate the shared keychain), `clipboard` (copy/clear mutate the OS clipboard singleton): `concurrency: read` → `mixed`.
  Commit: `fix(registry): dns/usb/creds/clipboard are mixed, not read`

- [ ] **A4: Annotate the 11 own_state tools.** Add `own_state` to the write-beat verbs of: prompt (save), dpt (build, baseline), eval (run, create), ghidra (analyze, decompile), pdf2md (convert, batch), tail (stop, prune — keep destructive on prune), vision (source *, detect), wireshark (capture, filter), figma (export), debug (break, continue, step), ide (open, goto). Mirror each in `lib/contracts-lexicon.yaml` overrides (with a comment) so `contracts propose` regenerates identically.
  Run: `./agent-do harness contracts validate --strict` → PASS. `python3 tests/test_contracts_gate.py` → PASS.
  Commit: `feat(registry): annotate own_state on self-confined write verbs`

- [ ] **A5: File tool-bug issues found by probing** (not fixed here): `agent-do manna create "manna list --json exits 2 with empty output" ...`; same for `unbrowse status --json` and `swarm status --json` ignoring the flag. These are the audit's first findings; the audit (WS-E) will keep them honest.

### WS-B — Concurrency cross-check rule (depends: A)

**Files:**
- Modify: `lib/registry.py` (validate_tool_contracts, insert after `:314` before `ok` at `:316`)
- Test: `tests/test_contracts_gate.py` (new `check_concurrency_alignment`)

- [ ] **B1: Failing test.** New check modeled on check_attribute_schema, registered in main():
  ```python
  def check_concurrency_alignment() -> None:
      read_with_write = {
          "commands": {"list": "...", "set": "..."},
          "concurrency": "read",
          "contracts": {"snapshot": ["list"], "interact": ["set"]},
      }
      result = validate_tool_contracts("demo", read_with_write)
      require("concurrency_mismatch" in error_codes(result),
              f"read tool with interact verb must error: {result}")

      read_with_own_state = {
          "commands": {"list": "...", "save": "..."},
          "concurrency": "read",
          "contracts": {"snapshot": ["list"], "save": ["save"],
                         "attributes": {"save": ["own_state"]}},
      }
      result = validate_tool_contracts("demo", read_with_own_state)
      require(result["ok"] and "concurrency_mismatch" not in error_codes(result),
              f"own_state writes must not force mixed: {result}")

      write_without_writes = {
          "commands": {"list": "..."},
          "concurrency": "write",
          "contracts": {"snapshot": ["list"]},
      }
      result = validate_tool_contracts("demo", write_without_writes)
      require("concurrency_overdeclared" in warning_codes(result),
              f"write tool with zero write verbs should warn: {result}")
  ```
  Run → FAIL (codes don't exist).

- [ ] **B2: Implement.** In validate_tool_contracts after the multi_beat loop: compute `write_verbs = verbs whose beat-union intersects {connect, interact, save} minus verbs whose attributes include own_state`. Rules: `concurrency == "read" and write_verbs` → error `concurrency_mismatch` (listing the verbs); `concurrency == "write" and not write_verbs and any beats declared` → warning `concurrency_overdeclared`; `concurrency == "mixed" and not write_verbs` → warning `concurrency_overdeclared`. (Verbs with long_running/composite/polymorphic still count as writes if they hold a write beat — only own_state exempts.)
  Run gate test + `./agent-do harness contracts validate --strict` → PASS (registry already reconciled by WS-A).
  Commit: `feat(contracts): concurrency derived from contracts — read tools cannot hold world-writes`

### WS-C — Safety surface for orchestrators (no deps)

**Files:**
- Modify: `lib/contracts.py` (extract `safety_surface()`, refactor render_markdown to consume it)
- Modify: `tools/agent-harness` (choices `:959`, dispatch, help), `registry.yaml:3215` + harness contracts block
- Test: `tests/test_contracts_gate.py`

- [ ] **C1: Failing test.**
  ```python
  def check_cli_surface() -> None:
      result = run_agent_do("harness", "contracts", "surface", "--json")
      require(result.returncode == 0, f"surface failed: {result.stderr}")
      payload = json.loads(result.stdout)
      for key in ("read_only", "write", "destructive", "sensitive",
                  "long_running", "passthrough", "own_state"):
          require(key in payload, f"surface missing {key}: {list(payload)}")
      require({"tool": "manna", "verb": "delete"} in payload["destructive"],
              f"known destructive verb missing: {payload['destructive'][:5]}")
      require(len(payload["read_only"]) > 400, "read surface implausibly small")
  ```
  Run → FAIL.

- [ ] **C2: Implement `safety_surface(payload) -> dict`** in lib/contracts.py: from a propose_contracts payload, emit verb lists as `{"tool": t, "verb": v}` objects — `read_only` (beat-union ⊆ {snapshot, verify}), `write` (the rest), plus one bucket per attribute. Refactor render_markdown `:177-194` to derive its counts/sections from safety_surface (one source of truth). Harness: `contracts surface --json` over the **merged** registry (orchestrators schedule what's actually installed; the gate stays bundled-only — note the asymmetry in --help).
  Run test → PASS. Commit: `feat(harness): contracts surface — machine-readable safety surface for orchestrators`

- [ ] **C3: Point CLAUDE.md's swarm/concurrency section at it** (one line: per-verb scheduling truth = `agent-do harness contracts surface --json`).

### WS-D — Drift check (D1 no deps; D2 depends: A)

**Files:**
- Create: `lib/contracts_drift.py`
- Modify: `tools/agent-harness` (choices, dispatch, help), `registry.yaml` harness entry
- Test: `tests/test_contracts_drift.py` (+ test.sh line)

- [ ] **D1: Engine + CLI, fixture-tested.** Parser spec (verified 0 FP across all 94 tools — implement exactly):
  1. Capture stdout+stderr of `agent-do <tool> --help` (use agent_do_cmd from harness, or accept pre-captured text — engine takes `(commands_map, help_text)` so tests are hermetic).
  2. argparse branch: `^  \{([^}]+)\}` → split on `,`.
  3. Per exactly-2-space-indented line: skip if first token starts with `-`, `agent-`, or `$`. `sig` = text before the first 2+-space description gap. `lead` = leading sig tokens until a token starting with `-` or containing `<[{`. **Prose filter:** no description column AND len(lead) > 2 → skip.
  4. Split `lead` on ` / ` (space-slash-space) for aliases; per alias take the run of `^[a-z][a-z0-9-]*$` tokens, stopping at any token containing `{|<[`; record first token AND full run.
  5. Ignore list: verb `help`, alias `ls`. **Never gate by section-header text** (verified trap: NOTES/ENV VARS/BRANCHES headers ate real verbs four times).
  6. A registry key is implemented iff it appears in the first-token set OR full-path set (absorbs gcp's multi-word keys).
  Output channels: `declared_only` (registry promises, help lacks — **the failing channel**) and `help_only` (advisory, never fails). CLI: `agent-do harness contracts drift [--tool X] [--json]`, exit 1 iff declared_only non-empty.
  Test with fixture: fake tool + fake registry entry, one phantom verb, one undocumented verb, one argparse-style help, one ` / ` alias, one prose paragraph containing `--yes`. TDD: test → FAIL → implement → PASS.
  Commit: `feat(harness): contracts drift — registry-vs-implementation verb diff`

- [ ] **D2 (after A2): Wire into test.sh + CI.** `check_cmd "contracts drift" "$AGENT_DO" harness contracts drift` in test.sh; add a drift step to `.github/workflows/contracts-gate.yml`... **CI caveat:** drift shells every tool's --help — ubuntu lacks macOS-only binaries but --help must still work (it did for all 94 locally; ubuntu unverified). Put drift in the macOS `ci.yml` suite job (via test.sh) only; do not add to the ubuntu gate until observed green.

### WS-E — Live behavioral audit (no deps; reconciliation improves results but doesn't block)

**Files:**
- Create: `lib/contracts_audit.py` (grading engine, runner injected)
- Modify: `tools/agent-harness` (audit loop + dispatch), `registry.yaml` harness entry (audit under verify in its contracts block)
- Test: `tests/test_contracts_audit.py` (+ test.sh line)

- [ ] **E1: Invocation policy (the safety core), test-first.** `eligible(tool, verb, contracts, commands)` returns an action: `probe` | `skip:<reason>`. Policy:
  - beat-union(verb) ⊆ {snapshot, verify}; else `skip:write-surface`.
  - any attribute on the verb → `skip:attributed` (long_running hangs, polymorphic may write, sensitive leaks into logs, composite acts).
  - verb description contains a required `<placeholder>` outside `[...]` → `skip:needs-args`; ALSO name-based denylist {read, show, describe, inspect, get, diff, code, link, search, load, pr} → `skip:needs-args` (verified: prose-stated required args carry no `<>` marker).
  - hang denylist {wait, scan} → `skip:hang-risk`.
  - tool requires credentials (registry `credentials.required`) → `skip:network` unless `--include-network` (cloud tools make unbounded curl calls; with creds present they hit live third-party APIs).
  Test with synthetic registry entries covering each branch → FAIL → implement → PASS.

- [ ] **E2: Probe + grading, tri-state.** For each `probe` verb: run via injected runner (harness passes `agent_do_cmd`, timeout configurable, default 15s), once bare and once with `--json`. Grade:
  - `ok` — rc==0, and if --json attempted, stdout parses as JSON;
  - `clean-skip` — nonzero rc with a structured/explanatory error (no session, no creds, no target): the contract held, environment didn't;
  - `fail` — rc==124 (hung), empty output with nonzero rc, `--json` produced prose or empty (the manna-list class), or crash traceback.
  Record run context: which creds present (names only, via registry credentials keys ∈ env — never values), platform. Output: per-tool per-verb verdicts + summary; `--json`; `--out` writes `.handoff/contracts-audit.md`.
  Fixture test: fake registry + two fake tools (one healthy JSON emitter, one that ignores --json, one that sleeps past timeout) → assert one ok / one fail(json) / one fail(timeout). TDD throughout.
  Commit: `feat(harness): contracts audit — bounded behavioral grading of the read surface`

- [ ] **E3: Wire machinery test into test.sh** (fixture-based only). The audit itself is **not** CI-gated — results are host-dependent (creds/sessions). Run `./agent-do harness contracts audit --out .handoff/contracts-audit.md` once and review findings (expected first crop: the --json liars).

- [ ] **E4: Scheduled audit (Erik's call: must be automatic — "I'd never remember").**
  `agent-do harness contracts audit --install-schedule [weekly|daily]` writes a launchd agent at `~/Library/LaunchAgents/com.agent-do.contracts-audit.plist` (macOS-native; no cron) running:
  `<repo>/agent-do harness contracts audit --out ~/.agent-do/audit/contracts-audit.md --notify`
  `--notify` emits through the existing notify contract: `agent-do notify emit contracts_audit --fact failures=N --fact new_failures=M` — silent when clean, pings Erik through his notify rules when a tool starts breaking its contract. One-time setup documented in the same task:
  `agent-do notify set-rule contracts_audit --recipient me --event contracts_audit --match new_failures>0 --message "Contracts audit: {new_failures} new failures" --cooldown 1d`
  `--uninstall-schedule` removes the plist. Tests: plist content generated to a temp path matches expected (no live launchctl in tests); `--notify` invokes notify emit via a fake binary on PATH.
  Commit: `feat(harness): scheduled contracts audit with notify integration`

### WS-F — Routing consumption (no deps)

**Files:**
- Modify: `lib/registry.py:102-122` (build_registry_context), `bin/intent-router`, `bin/pattern-matcher`
- Test: `tests/test_v11_routing.py` (extend), `tests/test_contracts_gate.py` (context encoding)

- [ ] **F1: Compact contracts in the LLM catalog, token-aware.** Extend build_registry_context: per tool append ONE line, e.g. `Safety: writes=[click,fill,...] destructive=[session delete] sensitive=[auth store-creds]` — emit only write/destructive/sensitive/passthrough sets (read is the default; omitting it keeps the line short). Measure: catalog must stay under ~9k tokens (currently 7.4k; budget the encoding, drop the writes= list to a count if a tool exceeds ~120 chars). Test: assert catalog contains `destructive=` for a known tool and total length < 36_000 chars.
- [ ] **F2: Route annotation + MODE-AWARE posture (Erik's call: ask by default, label-and-log in auto mode).** At route_intent convergence (`bin/intent-router:179`): resolve chosen tool+command against contracts (invert get_tool_contracts; reuse `_contract_command_exists` first-token logic) → add `beats`, `attributes` keys to the result. **Annotate AFTER `cache_result`/`note_route_outcome` so annotations are never persisted into patterns.db and replayed stale** (cache.py:230 serializes the whole dict — verified leak path). Thread the keys explicitly into the success/dry_run output dicts in execute().
  Posture, gated on auto mode (`AGENT_DO_AUTO_DESTRUCTIVE=1` env — the repo's existing env-var config pattern; document in CLAUDE.md env list):
  - **Auto mode ON:** destructive/sensitive routes execute; annotate + `append_event("route_intent_mismatch", ...)` when intent text is read-leaning (leading verb ∈ {show, list, get, what, check, view, read, find}) but resolved beats ∩ {interact, save} or attributes ∩ {destructive, sensitive}.
  - **Auto mode OFF (default):** a route whose resolved verb carries `destructive` or `sensitive` does NOT execute — exit 2 (the existing needs-clarification contract) with `clarification_needed` explaining what it resolved to and how to proceed (`rerun with AGENT_DO_AUTO_DESTRUCTIVE=1` or invoke the structured command directly). Read-leaning-mismatch telemetry fires in both modes.
  Tests: fake destructive route with env unset → exit 2 + clarification mentions the verb; with env set → executes + result carries attributes; mismatch event appears in events.jsonl (temp AGENT_DO_HOME).
- [ ] **F3: Mirror annotation in pattern-matcher** at match_intent return (`:219-255`).
- [ ] **F4: Un-hardcode the router model.** `bin/intent-router:160` → `os.environ.get("AGENT_DO_AI_MODEL", "claude-opus-4-5-20251101")` (keeps current behavior as default; CLAUDE.md documents the env var already). Test: route with AGENT_DO_AI_MODEL set + fake anthropic module, assert model passed through.
  Commits per slice; messages `feat(routing): ...`.

### WS-G — Docs + closeout (depends: all)

- [ ] CHANGELOG `## Unreleased`: one bullet per workstream.
- [ ] ARCHITECTURE.md Contracts Layer section: add surface/drift/audit commands + concurrency derivation + routing annotation.
- [ ] CLAUDE.md: harness command list + concurrency section (surface command); note audit is local-only.
- [ ] `zpc decide` × 2: own_state attribute decision; audit read-surface-only policy decision.
- [ ] Full `./test.sh` green; push; CI green; regenerate `.handoff/contracts-inventory-v2.md` (picks up own_state + reconciled registry).

---

## 3. Dependency graph & file ownership (swarm-ready)

```
A1 (own_state vocab — the milestone's FIRST commit, one line + test)
A (registry reconciliation; trunk — A2 is now the long pole:
   17 independent tool-implementation sub-tasks, each owning
   tools/agent-<name> + its test + registry entry; swarm these)
├──> B (validator rule)            owns: lib/registry.py(validate), gate-test concurrency check
└──> D2 (drift CI gating; waits for ALL of A2 — gate only gates truth)
C (surface; depends A1 only)           owns: lib/contracts.py, harness surface branch
D1 (drift engine) ── parallel          owns: lib/contracts_drift.py, tests/test_contracts_drift.py
E (audit)     ── parallel              owns: lib/contracts_audit.py, tests/test_contracts_audit.py
F (routing)   ── parallel              owns: bin/intent-router, bin/pattern-matcher, build_registry_context
G (docs)      ── after all
```
Shared-file contention: `tools/agent-harness` (C, D1, E all add dispatch branches) and `tests/test_contracts_gate.py` (A, B, C) — **one agent owns each shared file's wiring**, or sequence those merges; engines live in separate new lib modules precisely so the harness diff stays mechanical. A's registry.yaml edits should land before parallel agents regenerate anything from it.

---

## 4. Done criteria

1. `./agent-do harness contracts validate --strict` green WITH the concurrency rule active; registry carries `own_state` where true and zero phantom verbs.
2. `harness contracts drift` exit 0 on the reconciled registry; runs inside test.sh on macOS CI; declared-only channel empty.
3. `harness contracts surface --json` returns the seven buckets; CLAUDE.md points orchestrators at it.
4. `harness contracts audit` runs locally with bounded probes, tri-state grading, network off by default; fixture tests in test.sh; first real report written to `.handoff/contracts-audit.md`.
5. Route results carry `beats`/`attributes`; `route_intent_mismatch` events appear in events.jsonl; cache replays carry NO stale annotations; `AGENT_DO_AI_MODEL` honored.
6. Full `./test.sh` and both CI workflows green; CHANGELOG Unreleased updated; both zpc decisions logged.

---

## 5. Decisions (resolved by Erik, 2026-06-12)

1. **own_state attribute** — approved. The 11 self-confined writers keep `concurrency: read` with `own_state` on their write verbs; orchestrator parallelism preserved.
2. **The 23 phantom verbs get BUILT, not deleted.** The registry's promises become implementations (WS-A2, one sub-task per tool, swarm-parallel). Per-verb escape hatch: infeasible-as-promised → remove + manna issue with evidence.
3. **Mode-aware routing posture.** Default = destructive/sensitive natural-language routes do not execute; exit 2 with a clarification (the existing needs-clarification contract). `AGENT_DO_AUTO_DESTRUCTIVE=1` = execute, annotate, and log mismatches. Telemetry fires in both modes.
4. **Audit is automatic.** launchd-scheduled (weekly default), report to `~/.agent-do/audit/`, failures surface through `agent-do notify emit contracts_audit` so a breaking tool pings Erik without anyone remembering to run anything.
