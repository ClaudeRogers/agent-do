# The Agentic Work OS: Executive Brief

**Audience:** any team running a mix of human developers and AI coding agents.
**Companion:** the full technical design and the build board that implements it.

---

## 1. What this is, in one paragraph

A work system for teams where the workers are a mix of humans and AI agents. It answers six questions automatically, all day, without anyone remembering to ask them: What should be worked on next? Who has already claimed it? Is my branch still current with everyone else's finished work? Was the work done by an AI powerful enough for the job? Can we prove it? And what has actually been applied to production, beyond what git shows? On most teams today, those answers live in someone's head, in chat threads, and in the diligence of whoever happens to be careful. After this ships, they live in the machine. Any repository adopts the whole system with one config file and a ten line CI job.

## 2. The problem it kills

Coordination by conscientiousness works right up until it doesn't. One careful senior engineer reads everything and never collides with anyone. That is a property of a person, and it does not scale to five developers, ten AI agents, and a lead who is asleep. The failure modes this system removes:

- Two workers (human or AI) burn hours and AI credits on the same task because neither could see the other's claim.
- An agent starts blocked work because the dependency graph lived in a document it did not read.
- A schema change merges to main while a teammate's branch is in flight; they push days later and chaos ensues, textual conflicts at best, code that compiles against the wrong schema at worst.
- A major work item gets run on a weak or banned model, producing subtle garbage that costs more to find than the credits saved.
- A month later, nobody can prove which model produced a given commit, so quality problems cannot be traced to their cause.

The design goal: rules in the machine so nobody has to be careful.

Three legs hold that up. Claims stop two people doing the same work. Ordering stops people doing blocked work. Freshness stops people being blindsided by finished work landing underneath them.

## 3. How it works, mechanically

Four layers, each doing one job:

| Layer | Job | What it is |
|---|---|---|
| GitHub issues | The claim | Assigning yourself an issue IS claiming the work. Atomic, instant, visible to everyone, notifies everyone. First writer wins. |
| The work ledger | The ordering | A small file-based board inside the repo listing every work item and what blocks it. Blocked means untouchable. Agents read it at work start. |
| The policy file | The rulebook | One committed YAML file per repo (or one per org): model tiers, floors per work class, banned models, claim rules, freshness rules, required evidence. Rules change by pull request, so rule changes get reviewed like code. |
| CI | The wall | A pull request fails unless its issue is assigned to its author, its work item is unblocked, its branch is current with main, its declaration block is present, and its commit stamps meet the model floor. Failure messages are written for humans and say exactly what to fix. |

Plus the capability that makes model floors real: **provenance stamps**. Every commit made through an agent harness gets trailer lines recording the work item, the model, the effort level, and the session, written by the harness itself from its own configuration. Models are never asked to self-report, because models misreport. This is the difference between a rule and a suggestion.

## 4. Claiming work: one command, claim first

Claiming is a single command that sets up the entire workspace, in this order:

1. **Assign the GitHub issue.** This is the claim itself: one API call, first writer wins, visible to the whole team in seconds, notifies everyone. It happens at minute zero, before any branch or commit exists, and it requires no push.
2. **Mark the ledger.** The work item flips to in-progress on the in-repo board, so agents reading the board at work start see it too.
3. **Create the branch, named for the work.** The branch name carries the work item id plus a human friendly slug, for example `mn-a1b2c3/add-the-thing-to-the-other-thing`. Because the branch carries its own id, the CI mapping from branch to issue is self-documenting.
4. **Open a draft PR at first commit.** The draft PR is work-in-progress visibility: teammates can watch the work take shape. It is deliberately NOT the claim, for two mechanical reasons: a PR cannot exist until a commit is pushed, so it cannot claim at minute zero, and "check for an existing draft, then create one" leaves a race window where two workers slip past the check simultaneously. Issue assignment has no such window.

The order is the point. The claim lands before any code exists, so the duplicate-work hole closes at minute zero. Everything after it is workspace convenience that happens automatically.

Claiming never touches the main branch, so it can never trigger a deploy. Ledger state on main changes only when work merges, and deploy workflows ignore the board directory entirely as a belt-and-suspenders rule.

## 5. Staying current: the freshness leg

A claim protects you from duplicated work. Nothing about a claim protects you from someone else's finished work landing on main while your branch is in flight. That gets three treatments, from gentle to binding:

1. **The moment main moves under you (advisory, immediate).** When a merge lands on main touching paths near a live session's declared territory or an open branch, the affected sessions get an interrupt: main moved, these paths changed, your branch is now N commits behind. Drift is surfaced within minutes of the merge instead of discovered at push time.
2. **Before you push (advisory).** A local hook warns when your branch has fallen behind main and offers the merge, so conflicts get resolved on your machine, before anything reaches GitHub.
3. **At the merge gate (binding).** Branch protection requires branches to be current with main before merging, and CI re-runs against the merged result. This is what catches the dangerous case the local habit alone would miss: code that merges cleanly but is semantically wrong against a schema that changed underneath it.

The practice "pull main into your branch and resolve before pushing" stops being a rule people remember and becomes a thing the machine does, reminds about, and ultimately enforces.

## 6. Changes outside git: database migrations and other one-shot production changes

There is one place where "everything is a pull request" genuinely breaks down. Code converges through git: the diff is the change, merge is the deploy, review happens before anything is real. A production database is different in kind. It is a living singleton, and applying a migration is a one-shot side effect that happens outside git. The SQL file is code; the moment it runs against production is not. So the rule becomes: PR the plan, gate the side effect on the merge, and compensate for the unreviewable part with three things: pre-apply review of the plan, a queryable record of what has actually been applied, and drift detection between the two.

**"This is what I want to do next" is a schema PR.** The intent starts as a GitHub issue like any other work. The plan is a dedicated, tiny schema PR containing exactly one thing: the migration file plus an intent block in plain English (what changes, why, risk class, the rollback line). Merge is the approval. Apply is the execution. Nothing else rides in that PR, so it can be read, questioned, or vetoed in one sitting.

**Two classes, because velocity matters.** Migrations split by blast radius, and the two kinds deserve different gates:

- **Class 1, additive** (nullable columns, new tables, indexes, seeds): near-zero risk, trivially reversible. The standing database owner may approve and apply immediately, and the file plus intent block rides the campaign PR as the record. Apply-then-ratify. This preserves agent velocity, since builds often need the live schema to continue.
- **Class 2, breaking** (drops, renames, type changes, data rewrites): PR-first, two human approvals, apply only after merge. These are exactly the changes where a second reader catches what the author is too close to see, and hours of review latency is cheap against a bad rewrite of live data.

The boundary is enforced mechanically, not by judgment calls: CI auto-classifies a migration file containing statements like DROP, ALTER TYPE, RENAME, UPDATE, or DELETE as Class 2 and requires both approvals before merge. A CODEOWNERS rule on the migrations directory makes the database owner's review mandatory on every schema PR regardless of author.

**The ledger of what is actually live.** The real gap on most teams is that "what has been applied to production" lives in someone's memory. The fix is one convention: every migration ends with one extra INSERT into a tiny bookkeeping table (filename, applied when, applied by). Production state becomes queryable, and CI gains a drift check that compares migration files on main against the ledger in both directions: main has files never applied, and production has changes no merged file describes. The second direction is the one that protects against migrations running live for days while their files sit on an unmerged branch.

**The longer arc.** The eventual answer to "you cannot review a state change" is a staging database: managed providers now support database branching, so a schema PR can spin up a preview branch, apply there, run the test suite against it, and only then earn its merge. That is real infrastructure and a deliberate later waypoint, not a prerequisite. The two-class rule plus the ledger is the right weight for a small team today.

The same shape covers every one-shot production side effect, not just databases: infrastructure changes, feature-flag flips, data backfills. PR the plan, gate the apply, ledger the fact, detect drift.

## 7. Where enforcement actually happens

Three rungs, deliberately different in strength:

1. **At work start (advisory, and unique to this design).** The session itself checks the floor before any work happens. A session running a below-floor model gets a loud warning and cannot claim the item. This is the only enforcement point that fires BEFORE the credits are spent. CI can only catch waste after the fact; the harness prevents it.
2. **At commit and push (advisory).** Local hooks warn when someone touches paths another live worker has claimed, warn when a branch has drifted behind main, and stamp the provenance trailers automatically.
3. **At merge (binding).** CI is the hard wall. Nothing under-floor, unclaimed, out-of-order, or stale reaches the main branch.

Advisory locally, binding at the gate. Sessions never get bricked mid-flight; violations stay possible but never silent. The bar is deliberate-and-detectable, not impossible, by design.

## 8. Running many sessions at once: the live-session layer

The claim board coordinates the team at the work-item level, over days. Beneath it sits a second coordination plane for the live-session level, over minutes and hours, because the modern reality is that a single developer routinely runs several AI sessions at once in the same repository: one building, one auditing, one researching, two watching long jobs. Without coordination, those sessions collide with each other exactly the way uncoordinated teammates do, except faster.

The live-session layer is a shared state board those sessions read and write. It is zero-daemon and git-local, and it provides:

- **Liveness-verified presence.** Session identities are anchored to the actual running process, so a crashed session, an abandoned terminal, or a recycled pane can never appear as an active worker. Peers render as active, idle, dead, or stopped, always with a last-seen age. The board cannot lie in either direction: no ghost workers, no invisible ones.
- **Roles and territories.** A session declares itself builder, auditor, or researcher, and a builder declares an exclusive write-domain. Two writers whose territories overlap get an immediate advisory interrupt on both sides, naming the exact paths in contention. An auditor working a writer's paths sends the writer a courtesy notice, formalizing the freeze-during-audit behavior good teams invent by hand.
- **Structured focus.** Each session declares a goal and a phase (building, gating, watching, quiet, blocked, stopped), so sessions that are merely watching stop looking like workers, and a session going quiet during an audit says so as data instead of prose.
- **File drops.** Handoffs between sessions are pointers to files on the board, never content in a mailbox: a research session drops its findings, and the building session that declared the need gets a dependency interrupt.
- **A commit guard and a journal.** A warn-only pre-commit check flags staged paths that intersect a live peer's claim or territory, and an event journal answers who claimed, declared, or published what, and when, without archaeology.

The two planes compose. The claim on the GitHub issue says: this campaign is mine. Territories say: within it, session A owns the API directory, session B owns the UI, session C reads everything and writes nothing. The board view joins them, so a work item shows which live sessions are on it right now and which models they are running, which is also how model floors get checked per session before any spend. Sessions retire themselves automatically at session end, and dead ones age off the board on their own.

## 9. A day in the life

**The team lead, dispatching.** One board shows every item with its floor, its claim state, its blockers, and which live sessions are working right now, on what, with which models. Launching an agent on a work item is a one line prompt. The session claims the issue itself, verifies its own model clears the floor, and starts. If someone already claimed the item, the session reports the conflict immediately instead of duplicating the spend. Rule changes go through a pull request to the policy file, reviewed like any other code.

**Every developer.** The team toolkit is required tooling, with the same standing as git, and it gives humans the same ambient loop the agents get: the board injected at session start, one-command claiming that assigns the issue and cuts the branch and readies the draft PR, floors checked before work begins, a heads-up when main moves under an open branch, evidence stamps written automatically by installed hooks. The one-time cost is a single setup command per machine, verified live. After that, individual diligence stops being the load-bearing wall of the system and becomes what it should be: craftsmanship on top of a floor that holds by itself. GitHub remains the visibility surface everyone shares, including anyone glancing in from outside.

**A developer running a fleet.** Six sessions in one repo at once: two building different corners of a claimed campaign, one auditing, one researching, two watching long jobs. Each declares its role and territory in one command. The two builders cannot silently overlap: the moment their territories intersect, both are interrupted with the exact paths in contention. The auditor's presence sends the writers a courtesy notice, so they hold their paths quiet until the audit passes. Finished research lands as a drop pointing at a file, and the builder that needs it gets a dependency interrupt. When a session ends or crashes, it retires or is marked dead automatically; nothing it claimed haunts the board.

**The next hire.** Onboarding is three lines: install the toolkit (required tooling on this team, same standing as git), run the setup command, claim something grab-safe from the board. CI teaches the rest through its failure messages. The protocol document becomes one page, because the machine enforces what documents used to beg for.

**An AI agent, on any harness.** Wakes up, learns the repo's rules from the session context injected automatically, claims atomically, works inside its declared paths, commits with evidence attached, opens a pull request that passes the wall. If it is the wrong model for the job, it finds out in the first ten seconds, not after four hours of spend.

## 10. What the system consists of

Four components on top of an existing agent toolkit:

1. **GitHub issue commands**, so claiming is scriptable by every agent and every session, and the one-command claim workflow (assign, mark, branch, draft) is the same everywhere.
2. **The ledger-to-GitHub bridge**: twin issues created and kept in sync automatically; the machine registry the CI reads is generated output, never hand-edited; branch names carry their own work-item ids.
3. **The stamp tool**: writes and verifies provenance trailers, and includes a diagnostic that discovers what each harness exposes and generates the per-harness setup doc automatically.
4. **The rulebook engine**: reads the policy file and powers the session warnings, the commit and push hooks, the freshness alerts, the board view, and the CI check. The CI job in any repo becomes ten lines that call this one engine. Includes the doctor (verify and repair a machine's setup) and the one-command onboarding setup.

Beneath these sit the already-shipped foundations: the in-repo work ledger, the live-session coordination layer described in section 8, and an event-driven notification system.

## 11. Scope control

Activation is explicit opt-in: a committed policy file per repo, or one entry in a private org map for org-wide adoption. Everywhere else, the system is completely inert. No hooks fire, no stamps are written, no board appears. Personal repos behave exactly as they always did. Turning on a new team repo is: copy the policy file, add the ten line CI job, done. That pair of artifacts is also the portable spec: adopting the system on a new team is a working file plus an engine, not a memo.

## 12. Required tooling, and what happens when it is missing

The toolkit is required on adopting teams, but the system never assumes a working install, because assumptions are where enforcement systems rot. Drift is detected and remediated at three points:

- **CI validates outcomes, not setups.** The wall checks stamps, claims, ordering, and freshness on the pull request itself, so a machine with missing hooks (or no toolkit at all) still gets caught, and the failure message names the cure: run the doctor.
- **The doctor** is the cure: one command that verifies the binary, the harness hooks (registered, not merely present, which is the classic failure), the repo's git hooks, live stamping via a test commit, GitHub auth, and policy resolution. It fixes what it safely can and reports the rest.
- **Session start self-checks.** In a policy repo, a session on a broken setup is told so in its first screen of context, pointed at the doctor, before any work begins.

Setup for a new machine or hire is one command; drift on an existing machine is caught by the next pull request at the latest, usually by the next session start.

## 13. What this is not

- Not surveillance. It records which model did what work and who claimed what: billing and quality data a team already wants, and nothing else.
- Not a gate on people's judgment. Below-floor is surfaced, not silently blocked in-session; the working norm: running below the floor is never resourcefulness, surface the constraint and let the owner decide.
- Not fragile to its own absence. Every binding check lives in CI and reads the artifacts, so local tooling gaps degrade to advisory gaps, never to enforcement holes.

## 14. Rollout, in dependency order

1. Three parallel lanes can start immediately: the issue commands, the ledger bridge, the stamp tool.
2. The rulebook engine lands on top of all three.
3. Ambient session behavior (auto-claim, floor warnings, freshness alerts, board injection) lands on the engine.
4. The pilot repo retrofits piece by piece while its existing workstream continues unchanged with today's tools. Four pieces need no build at all and can be adopted immediately: branch protection requiring branches to be current with main, deploy workflows ignoring the board directory, a CODEOWNERS rule on the migrations directory, and the migration ledger convention.
5. The portable spec falls out of step 4 as a working artifact any other team can adopt.

Each stage is felt as a subtraction: fewer things to say in prompts, fewer protocol reminders in briefs, shorter onboarding documents.

## 15. Decisions each team makes at adoption

1. **The model tier table.** Which models qualify as frontier tier and strong tier, minimum effort levels, and any models banned by name. An example shape: frontier tier for large campaigns, schema and design phases, and anything touching live production data; strong tier for spec-following build phases and routine debt; an explicit banned list for models the team has found unreliable, plus fast modes on floor work.
2. **Agent claim identity.** Agents claim as their operator's GitHub identity (recommended: GitHub assignment stays the single atomic lock, and the session stamp distinguishes which agent did the work) or as separate bot identities.
3. **Gated items.** Items reserved for the owner: visible on the GitHub board but unassignable, or ledger-only.
4. **Activation scope.** Org-wide via the org map, or repo-by-repo policy files.
5. **The database owner and the class boundary.** Who holds the standing approval for additive migrations, and which statement patterns force a migration into the two-approval class.

## 16. Honest caveats

- The stamp is as trustworthy as the harness configuration it reads. A determined person can fake a trailer; CI plus a no-self-approval review norm is the backstop. The bar is deliberate-and-detectable, not impossible, by design.
- Harness attribution is uneven across the industry today: some harnesses name the exact model in commit trailers, some stamp a generic tool name, some stamp nothing. Squash-merges can also strip commit trailers from the main branch depending on repo settings, which is why CI checks commits before merge and the PR declaration block is the evidence that survives a squash. The diagnostic exists precisely to map and close this per harness, but expect a short tail of setup friction with each new harness a team adopts.
- Surface parity is about local versus cloud, not GUI versus CLI. Desktop apps and IDE extensions run the same local engine as the CLI, with the same hooks and settings, so they get the full ambient experience. Cloud-hosted sessions (browser-based coding sessions and cloud tasks) run on remote machines that ignore personal settings, which is why enforcement assets belong at the repository level: repo-committed hooks travel with every clone, and the CI wall holds regardless of what any local machine has installed.
- The ledger bridge is the component most likely to surface edge cases, which is why a pilot's existing workstream should keep moving on current tools while it hardens behind them.

---

**Bottom line:** this converts team discipline from a property of people into a property of infrastructure. Claims become atomic, instant, and visible before any code exists. Ordering becomes machine-read. Branches stop going stale silently. Production changes that live outside git get a plan that is reviewed, a ledger that is queryable, and drift that is detected. Model quality becomes enforced before spend and provable after merge. And none of it requires anyone to remember anything. Careful developers get simpler days, not heavier ones. Leads dispatch and verify instead of remind and hope. The entire system exports to the next team as one file and one engine.
