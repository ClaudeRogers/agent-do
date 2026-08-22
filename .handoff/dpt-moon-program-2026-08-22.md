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

## Palingenesis meanwhile

Waves A–C run on the primitive composite now: fixed floors + screenshot-and-eyes + the R1 guardrail + the style-guide checkpoint. First live duty for P1 if greenlit: Wave B lane outputs as its first real subjects — and the ratified canon's role shifts correctly from *ground truth* to *one entry in the museum with a strong falsification record*.

## Honesty ledger

- True Kolmogorov complexity is uncomputable; the round-trip test is a budgeted approximation — good enough to separate lawful from arbitrary, and falsifiable where it isn't.
- Model self-distance and reconstruction scoring carry judge biases (familiarity pull, position, busy-preference). Mitigations are structural: swap, blind reconstruction, axiom-named verdicts — and P1's fixture falsifier exists to catch what survives.
- "Award-level every time" is a social outcome no instrument guarantees. What the axioms buy: never flinch-worthy, never arbitrary, never derivative — reliably worthy of entry. The lineage does the rest, and that is not a limitation of the machine; it is how canons have always been ratified.
