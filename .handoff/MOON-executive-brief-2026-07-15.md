# Executive Brief: The Agentic Work OS

**For:** Erik (CIO, principal developer)
**Subject:** What the coordination and enforcement platform is, how it will run, and what daily life looks like once it exists.
**Companion:** `.handoff/MOON-agentic-work-os-2026-07-15.md` (full technical design), build board in this repo's `.manna/`.

---

## 1. What this is, in one paragraph

A work system for teams where the workers are a mix of humans and AI agents. It answers four questions automatically, all day, without anyone remembering to ask them: What should be worked on next? Who has already claimed it? Was the work done by an AI powerful enough for the job? Can we prove it? Today those answers live in your head, in Slack threads, and in Chris's diligence. After this ships, they live in the machine. The pilot is vms.io; the product is a pattern any team repo can adopt with one config file.

## 2. The problem it kills

Chris claimed campaign 05 by reading carefully and acting well. That worked because Chris is Chris. It does not scale to three developers, ten AI agents, and you asleep. The failure modes it removes:

- Two workers (human or AI) burn hours and AI credits on the same task because neither could see the other's claim.
- An agent starts blocked work because the dependency graph lived in a document it did not read.
- A big campaign gets run on a weak or banned model, producing subtle garbage that costs more to find than the credits saved.
- A month later, nobody can prove which model produced a given commit, so quality problems cannot be traced to their cause.

The design goal, in your words: rules in the machine so nobody has to be careful.

## 3. How it works, mechanically

Four layers, each doing one job:

| Layer | Job | What it is |
|---|---|---|
| GitHub issues | The claim | Assigning yourself an issue IS claiming the work. Atomic, instant, visible to everyone, notifies everyone. First writer wins. |
| The work ledger (manna) | The ordering | A small file-based board inside the repo listing every work item and what blocks it. Blocked means untouchable. Agents read it at work start. |
| The policy file | The rulebook | One committed YAML file per team repo (or one per org): model tiers, floors per work class, banned models, claim rules, required evidence. Change the rules by editing one file in a PR you approve. |
| CI | The wall | A pull request fails unless: its issue is assigned to its author, its work item is unblocked, its declaration block is present, and its commit stamps meet the model floor. Failure messages are written for humans and say exactly what to fix. |

Plus one new capability that makes the floors real: **provenance stamps**. Every commit made through an agent harness gets trailer lines recording the work item, the model, the effort level, and the session, written by the harness itself from its own configuration. Models are never asked to self-report, because they misreport. This is the difference between a rule and a suggestion.

## 4. Where enforcement actually happens

Three rungs, deliberately different in strength:

1. **At work start (advisory, unique to us).** The agent session itself checks the floor before any work happens. A session running a below-floor model gets a loud warning and cannot claim the item. This is the only enforcement point in the industry that fires BEFORE the credits are spent. CI can only catch waste after the fact; the harness prevents it.
2. **At commit (advisory).** Local hooks warn when someone touches paths another live worker has claimed, and stamp the provenance trailers automatically.
3. **At merge (binding).** CI is the hard wall. Nothing under-floor, unclaimed, or out-of-order reaches main.

Advisory locally, binding at the gate. Sessions never get bricked mid-flight; violations are always possible but never silent.

## 5. A day in the life

**You, dispatching work.** You look at one board (or GitHub itself) and see every item with its floor, its claim state, its blockers, and which live sessions are working right now on what, with which models. You launch a Codex agent for campaign 04 with a one-line prompt. The session claims the GitHub issue itself, sets its presence, verifies its own model clears the floor, and starts. If someone already claimed it, the session tells you immediately instead of duplicating the work. You approve rule changes the way you approve code: by PR to the policy file.

**You, as main dev.** In team repos, identical experience to your agents: your commits get stamped, your PRs carry the declaration block the template pre-fills, CI checks you like everyone else. In your personal repos: nothing. The system is inert anywhere the policy file or org mapping does not exist. Zero hooks, zero stamps, zero noise.

**Chris today.** agent-do is already his daily driver, so he gets the same ambient loop the agents get: the board injected at session start, one-command claiming (or plain GitHub assignment, both stay mirrored), floors checked before work begins, stamps written automatically by his installed hooks. His one-time cost is running the setup command once per machine so stamping and hooks are verified live. After that, his diligence stops being the load-bearing wall of the system and becomes what it should be: craftsmanship on top of a floor that holds by itself. GitHub remains the visibility surface everyone shares, including anyone glancing in from outside.

**The next hire.** Onboarding is three lines: install agent-do (required tooling on this team, same standing as git), run the setup command, claim something grab-safe from the board. CI teaches the rest through its failure messages. The protocol document becomes one page, because the machine enforces what documents used to beg for.

**An AI agent (any harness: Claude Code, Codex, Cursor).** Wakes up, learns the repo's rules from the session context injected automatically, claims atomically, works inside its declared paths, commits with evidence attached, opens a PR that passes the wall. If it is the wrong model for the job, it finds out in the first ten seconds, not after four hours of spend.

## 6. What gets built (plain names)

Four pieces, three of which can be built in parallel starting now:

1. **GitHub issue commands** for the agent toolkit, so claiming is scriptable by every agent.
2. **The ledger-to-GitHub bridge**: twin issues created and kept in sync automatically; the machine registry the CI reads becomes generated output, never hand-edited.
3. **The stamp tool**: writes and verifies provenance trailers; includes a diagnostic that discovers what each harness exposes and generates the per-harness setup doc.
4. **The rulebook engine**: reads the policy file, powers the session warnings, the commit hooks, the board view, and the CI check. The CI job in any repo becomes ten lines that call this one engine. Includes the doctor (verify and repair a machine's setup) and the one-command onboarding setup.

The existing pieces (the ledger, the live-session presence layer with verified liveness, the notification system) shipped already and are running today.

## 7. Scope control

Activation requires an explicit opt-in per repo (a committed policy file) or per org (one entry in your private org map, e.g. Versova-Intelligence-Division). Everything else on your machine and every personal repo behaves exactly as it does today. Turning it on for a new team repo is: copy the policy file, add the ten-line CI job, done. That final artifact is also the NewCo deliverable: the portable spec is a working file plus an engine, not a memo.

## 8. Required tooling, and what happens when it is missing

agent-do is required tooling on the team, the same standing as git: it was built to do exactly this job, and everyone works through it. But the system never *assumes* a working install, because assumptions are where enforcement systems rot. Drift is detected and remediated at three points:

- **CI validates outcomes, not setups.** The wall checks stamps, claims, and ordering on the PR itself, so a machine with missing hooks or no agent-do at all still gets caught, and the failure message names the cure: run the doctor.
- **`agent-do policy doctor [--fix]`** is the cure: one command that verifies the binary, the harness hooks (registered, not just present, the classic failure), the repo's git hooks, live stamping (test commit), GitHub auth, and policy resolution. It fixes what it safely can and reports the rest.
- **Session start self-checks.** In a policy repo, a session on a broken setup is told so in its first screen of context, pointed at the doctor, before any work begins.

Setup for a new machine or hire is one command; drift on an existing machine is caught by the next PR at the latest, usually by the next session start.

## 9. What this is not

- Not surveillance. It records what model did what work and who claimed what, which is billing and quality data you already want, and nothing else.
- Not a gate on people's judgment. Below-floor is surfaced, not silently blocked in-session; the stated norm holds: below-floor is never resourcefulness, surface the constraint and the owner decides.
- Not fragile to its own absence. Every binding check lives in CI and reads the artifacts, so local tooling gaps degrade to advisory gaps, never to enforcement holes.

## 10. Rollout, in dependency order (no dates; lanes, not phases)

1. Three parallel lanes start immediately: issue commands, ledger bridge, stamp tool.
2. The rulebook engine lands on top of all three.
3. Ambient session behavior (auto-claim, floor warnings, board injection) lands on the engine.
4. vms.io retrofits piece by piece under the workstream already running there, which continues unchanged with today's tools in the meantime.
5. NewCo spec falls out of step 4 as a working artifact.

You will notice each stage as a subtraction: fewer things you have to say in prompts, fewer protocol reminders in briefs, shorter onboarding documents.

## 11. Decisions only you can make

1. **Bless the model tier table** (Frontier: Fable 5 / Codex 5.6 Sol at xhigh minimum; Strong: Opus 4.6 / Sonnet 5; Banned: Opus 4.8 and fast mode on floor work). Cursor policy still open.
2. **Agent claim identity:** agents claim as their operator's GitHub identity (recommended; keeps GitHub assignment the single atomic lock, with the session stamp distinguishing which agent did the work) or as separate bot identities.
3. **Owner-gated items** (MOON-class): visible on GitHub but unassignable, or ledger-only.
4. **Org-wide activation now** via your org map, or repo-by-repo policy files only.

## 12. Honest caveats

- The stamp is as trustworthy as the harness config it reads. A determined person can fake a trailer; CI plus the no-self-approval review norm is the backstop. The bar is deliberate-and-detectable, not impossible, by design.
- Harness attribution is uneven today (your Fable sessions name the model; Cursor is generic; some Claude Code setups stamp nothing). The diagnostic tool exists precisely to map and close this per harness, but expect a short tail of setup friction per new harness.
- The ledger bridge touches the Rust core of the issue tracker; it is the trunk most likely to surface edge cases, which is why the running vms.io workstream does not wait on it.

---

**Bottom line:** you are converting team discipline from a property of people into a property of infrastructure. Claims become atomic and visible, ordering becomes machine-read, model quality becomes enforced before spend and provable after merge, and none of it requires anyone to remember anything. Chris's experience gets simpler, not heavier. Your experience becomes dispatch-and-verify instead of remind-and-hope. And the whole thing exports to NewCo as one file and one engine.
