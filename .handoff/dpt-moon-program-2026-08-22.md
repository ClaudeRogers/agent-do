# The Moon Program — canon-free design knowing

**Date:** 2026-08-22 (v2, same day — v1's taste-corpus-as-ground revised out after Erik's correction) · **Predecessor:** `.handoff/dpt-audit-2026-08-22.md` · **Board:** dream mn-133b76 (this is its blueprint), item mn-2521d5 (prerequisite floor fixes)

**The moon, in Erik's words:** good design KNOWING. Self-inspiration. No canon to look at — it *builds* the canon because it's that good. Native vision in silicon's own latent space, producing award-level work, many, never the same twice. No one has solved this yet.

---

## The dissolution: canon was never the ground

"How will AI know good design without a ratified canon" contains a hidden assumption — that knowing rests on canon. It never has. The canon-builders (Rams, Tschichold, Brodovitch, the Swiss school) consulted no canon; they worked from invariants that every style merely instantiates. **Styles are theorems; the invariants are the axioms.** A canon is the residue of past knowing, not its source. So the machine doesn't need a canon to know — it needs the axioms, measured in its own native quantities, plus an honest way to be wrong.

Why no one has solved it: every existing approach is canon-derivative.
- **Rule lists** (dpt today, heuristic linters): encode one era's theorems as axioms → the audit measured the result — a sameness machine.
- **Preference models** (NIMA, LAION-aesthetics, any "trained on award winners"): distill the mean of the existing canon → beautiful regression to the familiar; never-before-seen is *penalized* by construction.
- **Raw generation** (prompt → design): samples the mode of the prior → the barf aesthetic is literally the null hypothesis of the medium.

The unclaimed ground is judgment from invariants. Three of them, each canon-free, each computable in silicon-native terms:

## The three axioms

**A1 — Physics.** The human visual system is fixed hardware: contrast sensitivity, pre-attentive pop-out, gestalt grouping, foveal acuity, working-memory limits, processing-fluency mechanics. Not cultural. A design violating them produces the flinch before any style opinion forms. *Measure:* dpt's floor rules (post mn-2521d5) + mechanical perception probes — squint test (render re-screenshotted under CSS blur: does hierarchy survive?), grayscale test (does it still read?), first-glance isolate. Pure image transforms plus model perception; zero new dependencies.

**A2 — Economy (truth to intent).** In good design nothing is arbitrary: given the content and its job, every visible decision derives from a small generative grammar. Birkhoff's order-over-complexity (1933) and Rams' "as little design as possible" were prose attempts at this axiom. *Measure — the round-trip test:* the judge writes the shortest complete style-grammar that captures the design (a token budget forces compression); a **blind** second instance rebuilds the design from the grammar alone; perceptual distance between original and reconstruction is scored from renders. Short grammar + faithful reconstruction + rich percept = lawful economy. Description length is the machine's own quantity — this is aesthetic judgment performed *in the latent space*, not through human rules.

**A3 — Lawful surprise (compression progress).** Schmidhuber's formal aesthetics: beauty for an observer is compression *progress* — the artifact its model could not predict that proves deeply lawful once inferred. Berlyne's inverted-U says the same in psychology: interest peaks where novelty resolves. *Measure — the self-null:* for the same brief, the machine samples its own default K times; the candidate's distance from that cloud is its surprise. The cliché fails here (it IS the prior's center, however cheaply it round-trips); the broken page fails A2 (arbitrary residue); the masterpiece alone passes both — far from the default, lawful under its own inferred grammar. **Sequence matters:** surprise scored at first glance, lawfulness scored after grammar inference — that ordering is the "aha" itself.

Self-inspiration, formalized by the same axioms: treat your own default as the null hypothesis to reject; mine the world-model's far domains for *grammar donors* (a mycelial network's branching law, a timetable's information economy, a stencil's figure-ground discipline — structural transfer, never lookalike transfer); compose a new grammar; keep what passes A1–A3. Inspiration = importing lawful structure across domains. Nothing in the loop consults a design canon.

## The epistemics: humans falsify, never dictate

Pure intrinsic criteria can drift into machine-beautiful, human-dead artifacts — the aesthetic analog of adversarial examples. The containment is not a taste canon; it is science. The machine holds an aesthetic **theory** stated in axiom terms; it produces; human response — Erik's advance/kill with reasons, dwell, the boardroom's one skeptical click — is the **experiment**. Refutation updates the axioms' weights and measures, never "copy what they liked." A panderer imitates preferences; a scientist revises theory. This is also the difference between calibration (v1's mistake — grounds judgment in an existing taste, reproduces it forever) and falsification (keeps the ground intrinsic, uses humans only to catch the theory being wrong).

**And this is how the canon gets built as output.** Survivors of axioms + falsification enter the museum as *grammars with their records* — not screenshots. A canon has always really been a body of laws (the grid, the ratio, the two-weight rule), not a gallery. A museum of machine-authored, falsification-tested grammars **is** a canon the machine wrote. Every decision joins the lineage — the same law the Dossier's decision bar already states.

## Standing laws

1. **No global score exists anywhere.** Persisted facts: floor pass/fail, per-axiom results, pairwise records, museum cell occupancy, falsification events. Any scalar target resurrects the sameness machine (measured today: dpt's 0-100 rated the banned template one point under the ratified canon).
2. **No external style corpus ever enters the judge.** References and world-seeds may feed *generation* as grammar donors; judgment consults only the axioms. The moment "looks like the winners" enters the judge, the program is NIMA with extra steps.
3. **Judgment happens on renders** (visual truth), comparatively where comparison is needed, position-swapped, with the axiom being applied named in the verdict.

## Dependency graph

```
P0 dpt floor fixes (mn-2521d5) ─┐
                                ├─→ P1 Axiom Judge ──→ P3 Self-inspiration generator ──→ P4 Museum of grammars
   (fixtures already exist) ────┘        │
                                         └─→ P2 Falsification journal (decision lineage)
```

- **P0 — filed, claimable.** The floor gate must not lie (faux-bold, oklch blindness, 44px-on-inline, global baseline, hook mislabeling).
- **P1 — the Axiom Judge.** Round-trip test + self-null distance + physics probes, as a protocol first (skill + browse + model calls; zero new registry surface). **Falsifier, runnable day one against the preserved validation set (`tools/agent-dpt/fixtures/`, README carries the protocol):** blind, the composite must order this morning's fixtures — canon Dossier: cheap round-trip AND far from prior; neon template: cheap round-trip, AT the prior (fails A3); broken page: round-trip failure (fails A2). recognitionoracle must pass all three. If the composite cannot reproduce that ordering, the axioms are mis-measured or wrong — say so and revise, don't ship.
- **P2 — falsification journal.** The decision lineage (advance/kill + reasons; past ratification events mined from session history) stored as experiments against the theory, with which axiom each refutes or confirms. Explicitly NOT a calibration target.
- **P3 — self-inspiration generator.** Sample-the-default as null; grammar donors from far domains; compose; pre-screen against the axioms before any human sees a candidate.
- **P4 — museum of grammars.** Quality-diversity archive: cells over grammar families; entry = beat the occupant under the axioms or open a new cell; holdings = grammar + renders + falsification record. **Never-twice falsifier:** after 10 briefs, no two occupants judged same-family. The museum's contents are the machine-built canon.
- **Taxonomy gate:** P1/P2 can live as a skill + journal with no registry surface. New dpt verbs (`judge`, `probes`, `museum`) or any new tool/dependency: Erik's explicit go first.

## P1 run 1 — results (2026-08-22, same day; falsifier fired, theory revised)

Pre-registered protocol and raw data: session scratchpad `p1/` (protocol.md, results.json, grammars, 10 blind-built pages, 14 blind judge verdicts, probe renders). Fleet: 10 builders (4 reconstructors from 100-word grammars, 6 null-samplers), 14 fresh judges (8 fidelity, position-swapped; 6 family, order-shuffled), all blind to purpose.

**A1 physics — VALIDATED, 4/4 predictions held.** Blur probe: canon-dossier's hierarchy fully survives (headline → chip → metrics → actions); oracle near blur-invariant (best in set); barf survives as blocks but its attention ordering collapses into ~8 equal saturated pulls; broken's content layer evaporates — only the logo, the shout-band, and the red Delete button survive, a destructive action winning the page. Grayscale probe: canon keeps all meaning (words + underlines + fill carry semantics redundantly); barf fails diagnostically — its three CTAs become identical grey pills (hue-only hierarchy) and its pie goes meaningless. Plus honest findings on the exemplar: recognitionoracle carries 17 genuine hard contrast failures (white-on-coral 2.86:1, coral accents 2.55:1) under its superb gestalt. A1 is the validated leg: cheap, mechanical, discriminates exactly as pre-registered.

**A2 round-trip at 100 words — REFUTED AS A DISCRIMINATOR.** Fidelity (blind, swapped): dossier 8/8, barf 8/8, broken 8/8 (predicted <4), oracle 9/9. Zero separation. Two diagnosed causes: the broken fixture is a *compressible parody* — its chaos was authored by recipe, so a short grammar captures it (real-world brokenness accretes, it isn't generated); and the reconstructor shares the design prior, so it fills spec gaps stereotypically — fidelity partly measures *stereotypy*, not lawfulness. Revision required before A2 gates anything: derivation-form grammars (principles the page must follow, not features it has), budget sweep (fidelity-vs-budget slope, not one point), and a reconstructor steered away from its own defaults.

**A3 self-null distance — HALF VALIDATED, and the half that failed taught the most.** Family-vs-own-default (blind, shuffled): canon-dossier 2/2, oracle 2/3 — both far from the prior, as predicted. But barf scored 2/2 — predicted ≥7 (at-prior). The 2026 prior's actual defaults are *not* neon barf: for these briefs it produced a clean light SaaS review console, a clean indigo analytics page, and a genuinely handsome dark-luxe landing. Neon-on-dark is a 2023-era attractor the prior has left. Consequence: self-null distance is a valid *self-inspiration* pressure but cannot catch *genre*-derivativeness — the familiarity-across-the-medium axis (in program v1, folded away in v2) returns as its own mandatory leg.

**Bonus finding, the run's strongest:** the two independent nulls per brief converged so tightly that blind judges described each pair as "one habit" — same layout, same palette, same component culture, from two instances sharing zero context. The sameness attractor is not a hypothesis; it is now a measured property of the raw prior. That is the museum's reason to exist, demonstrated.

**Composite verdict per the pre-registered falsifier:** the composite as operationalized FAILED to reproduce the target ordering — barf would have survived it (A2 pass, A3 surprise-pass, only A1's grayscale/attention marginal against it). pos-99cee7 flipped on that evidence; successor position v2 filed: A1 kept as-is; A2 rebuilt as derivation + budget-sweep; A3 split into two legs (self-null + genre familiarity). New falsifier: a re-run must fail barf on the familiarity leg (≥7) and fail broken on revised A2, while canon and oracle still pass all legs. The method — pre-register, falsify, revise in the open — did on day one what no amount of argument would have: it found the two mis-measures and validated the one sound leg.

## P1 run 2 — results (2026-08-22, ~1h after run 1; two clauses held, two refuted, v3 dictated)

Pre-registered protocol + raw data: `p1/run2/` (protocol.md, results.json); fleet: 4 blind reconstructors from 40-word derivation grammars, 8 familiarity judges, 8 swapped fidelity judges.

**Revised A2 (derivation-form, 40 words) — the mechanism works; my thresholds didn't.** Broken collapsed from 8.0 (run 1, enumerated) to **2.0** — a six-point slope. The rebuild was a *different mess entirely* (a dense 2004 coupon bazaar vs the original's sparse grey drift): arbitrariness has many realizations, only law reconstructs. The lawful pages held high: oracle 9.0, dossier 6.0, barf 5.0 — a 4–7 point lawful-vs-lawless gap, visually confirmed (the dossier rebuild, "Corven Institute," is an unmistakable sibling of the canon derived from 45 words — and a handsome page in its own right, previewing grammars-as-seeds). But two absolute thresholds missed (dossier 6.0 vs pledged ≥7 — judges credited the shared *law* and docked free *voice*; barf 5.0 vs ≥6). v3: score the relative gap at fixed budget, re-anchor the judge to "same governing law?", and isolate genre-attractor support from law-transmission.

**New familiarity leg — kills what run 1 missed, and fired on the exemplar.** Barf: **10.0 unanimous**, genre named on sight ("neon dark-mode SaaS analytics dashboard template… ThemeForest/Tailwind admin kits nearly one-to-one"). Dossier: 5.5, with the run's gold sentence — *"influences are instantly recognizable but I cannot name a specific template category this whole page belongs to"* — the moon criterion in a blind judge's mouth. But recognitionoracle scored **8.5**: both judges named its genre in a phrase ("pastel aurora-gradient wellness landing hero… near-identical instances are everywhere") while noting departures the scale had nowhere to credit. Diagnosis: the leg conflates genre-*membership* (award work often has it) with kit-*interchangeability* (what derivative actually means). v3 splits them; only the product kills. And one honest datum stands regardless of instrument: two blind judges instantly naming the exemplar's genre says the moon standard — *builds* the canon — asks for more than even a beautiful genre-resident page.

**Falsifier verdict (pos-1834a8):** barf-kill HELD, broken-kill HELD, canon-passes REFUTED marginally (A2 6.0), oracle-passes REFUTED (familiarity 8.5). v2 refuted 2-of-4; pos-1834a8 flipped on evidence; v3 filed with its own falsifier. Two full falsification cycles in one day, each miss converted into a precise instrument revision — the loop is the product.

## Palingenesis meanwhile

Waves A–C run on the primitive composite now: fixed floors + screenshot-and-eyes + the R1 guardrail + the style-guide checkpoint. First live duty for P1 if greenlit: Wave B lane outputs as its first real subjects — and the ratified canon's role shifts correctly from *ground truth* to *one entry in the museum with a strong falsification record*.

## Honesty ledger

- True Kolmogorov complexity is uncomputable; the round-trip test is a budgeted approximation — good enough to separate lawful from arbitrary, and falsifiable where it isn't.
- Model self-distance and reconstruction scoring carry judge biases (familiarity pull, position, busy-preference). Mitigations are structural: swap, blind reconstruction, axiom-named verdicts — and P1's fixture falsifier exists to catch what survives.
- "Award-level every time" is a social outcome no instrument guarantees. What the axioms buy: never flinch-worthy, never arbitrary, never derivative — reliably worthy of entry. The lineage does the rest, and that is not a limitation of the machine; it is how canons have always been ratified.
