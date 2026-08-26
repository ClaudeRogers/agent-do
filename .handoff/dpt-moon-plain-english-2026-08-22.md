# The Day in Plain English — dpt audit, the moon question, and two experiments

**2026-08-22.** Companion docs with full receipts: `.handoff/dpt-audit-2026-08-22.md`, `.handoff/dpt-moon-program-2026-08-22.md`, raw data in `tools/agent-dpt/fixtures/p1-run1/` and `p1-run2/`.

## The morning question

You asked whether dpt — the automated design-scoring tool — is measuring what you intended (real design quality, "the moon") or something easier that merely resembles it ("fingers"). The stakes: the Palingenesis redesign was about to launch with dpt whispering a score to every build agent after every edit, and agents obey numbers.

## Part 1: The audit — dpt is a smoke detector wearing an art critic's clothes

I read every rule in the tool, then tested it the only honest way: by building controlled pages and seeing whether it could tell them apart. Four fixtures — two faithful implementations of your ratified Palingenesis design, one polished specimen of the neon-dashboard style your design bible explicitly bans, one deliberately broken page — plus your own recognitionoracle.com scored live.

What it got right: the broken page scored 29, an F, with four correctly named problems. As a detector of genuinely broken craft — unreadable text, invisible buttons, a delete button styled as the loudest thing on the page — dpt works.

What it got wrong: your ratified Dossier scored 67. The banned neon template scored 66. One point apart. The tool literally cannot tell your best design from the thing you banned. recognitionoracle — your own exemplar — got a 70, a B-minus, and dpt's "fix list" for it would have removed the coral accent, shrunk the huge headline, and filled in the breathing room: everything that makes the site itself. On your canon pages the fix list was eight items long, and all eight were either measurement bugs or direct orders to undo decisions you ratified on purpose.

Under the hood it was worse: the tool claims 72 rules but runs 65; the "sorted by impact" list isn't sorted and omits the most important rule entirely; its baseline file is shared by every session at once so parallel agents corrupt each other; its README cites a research directory that doesn't exist; and the auto-score hook grades whatever page the browser happens to have open — during the audit it scored an unrelated app five times and presented that as feedback on my edits.

Verdict: keep dpt as a pass/fail floor check. Never let an agent chase its score. The bug-fix work order is on the board (mn-2521d5), and a guardrail paragraph for the design bible is written and waiting to be pasted.

## Part 2: Your question that changed the plan

You then asked the real question: how will AI *know* good design without a ratified canon to look at — the goal being a machine so good it *builds* the canon. Nobody has solved this.

The answer I proposed: a canon was never the source of knowing — it's the residue of it. The people who built the great canons consulted no canon; they worked from deeper invariants that every style merely expresses. Three of them, and each is measurable by a machine in its own native terms:

1. **Physics.** Human vision is fixed hardware — contrast sensitivity, what survives a squint, what reads without color. Not culture, not fashion. A machine can test this mechanically: blur the page and see if the hierarchy survives; drain the color and see if the meaning survives.
2. **Economy.** In good design nothing is arbitrary: the whole page derives from a small set of laws. A machine can test this by compression: write the shortest statement of the design's governing principles, hand it to a second machine that has never seen the page, and measure how close the rebuild lands. Law survives compression; chaos doesn't.
3. **Lawful surprise.** The best work is far from what the machine would produce by default, yet completely lawful once you understand it. A machine can test this by sampling its own defaults for the same brief and measuring the distance.

Humans enter the loop only as reality-checks: your advance/kill decisions test the theory the way experiments test a scientist — never as a style to imitate. What survives goes into a museum as *grammars* — bodies of law, not screenshots — and that accumulating shelf of tested laws is precisely what a canon has always been. The machine builds it.

And one discipline held everything honest: every claim got a written test that could prove it wrong, filed *before* measuring.

## Part 3: Experiment 1 — the theory meets reality and loses two of three

The fleet: ten builder agents and fourteen judge agents, all blind — the rebuilders never saw the originals, the judges never knew which image was which or what the experiment was for.

- **The physics test passed perfectly, four for four.** Under blur, your Dossier's structure survives intact; the broken page's content literally evaporates, leaving the red Delete button winning the whole page. Drained of color, your canon keeps every meaning (the words and underlines carry it); the neon template's three buttons collapse into identical grey pills — its hierarchy was color alone.
- **The compression test failed to discriminate.** Everything — including the broken page — rebuilt at 8 or 9 out of 10. Why: I had *described* the broken page's chaos in detail, which is itself a recipe, and the rebuilder's own good taste quietly filled every gap.
- **The "is this just your default?" test half-worked.** Your canon and the oracle measured far from the machine's defaults, as hoped — but so did the neon template, because the machine's defaults have quietly moved on from neon. "Different from my default" cannot catch "copies a known genre."
- **The accidental gold:** two separate AIs, given the same brief with zero shared context, produced designs so alike that blind judges called each pair "one habit." The sameness problem — the whole reason the museum exists — is not a theory. It is now measured.

The theory was declared partly wrong in writing, and version 2 was filed with new tests.

## Part 4: Experiment 2 — the revised measures earn their kills, and the exemplar teaches a lesson

Two changes: describe each page in 40 words of *governing principles only* (no feature lists), and add a new judge question — "have you seen this design language a thousand times?"

- **The broken page collapsed from 8.0 to 2.0.** The blind rebuild was a *completely different mess* — a dense 2004 coupon bazaar versus the original's sparse grey drift. Chaos cannot be transmitted through principles; only law reconstructs. Kill confirmed.
- **The neon template was named on sight** — "neon dark-mode SaaS analytics dashboard template, ThemeForest admin-kit style" — 10 out of 10 from both judges independently. Kill confirmed.
- **Your Dossier rebuilt at 6.0** where I had pledged 7. The judges' own words show why that's a near-miss of the instrument, not the design: they credited the transmitted *system* — same charcoal ground, same cream serif, same reserved green, same sticky decision bar — and docked the rebuild for choosing a different *voice* (a heavier headline face). Lesson learned: score the gap between lawful and lawless (6–9 versus 2), never absolute numbers.
- **The surprise: recognitionoracle scored 8.5 on familiarity.** Both judges instantly named its genre — "pastel aura-gradient wellness hero, the Calm/Co-Star lane" — while noting its refinements with nowhere on the scale to credit them. Two truths come out of that. First, the instrument conflates *living in a genre* (award winners do it constantly) with *being swappable for the genre's template kit* (the actual sin) — version 3 splits those. Second, honestly: the moon standard you set — work so good it builds the canon — asks for more than even a beautiful genre-resident page. The page that came closest to the criterion was your canon Dossier, in a blind judge's exact words: *"influences are instantly recognizable but I cannot name a specific template category this whole page belongs to."* That sentence is the moon, measured.
- **The moment worth savoring:** from 45 words of law, a blind agent regrew a gorgeous sibling of your Dossier — different institution, different innovation, same soul, and a genuinely handsome page. That is the museum working in miniature: laws as seeds that regrow quality.

## Where the theory stands tonight

Version 3, filed with its own could-prove-it-wrong test: the physics floor stays as-is (validated); the law test is scored as a relative gap at a fixed compression budget; derivativeness becomes familiarity *times* interchangeability — only the product kills. Unchanged from day one: no global score exists anywhere in the system, humans falsify rather than dictate, and the canon is the *output* — a museum of tested grammars.

## What's filed where

- **Audit:** `.handoff/dpt-audit-2026-08-22.md` + the visual artifact page ("Fingers for the Moon")
- **Theory + both runs:** `.handoff/dpt-moon-program-2026-08-22.md`
- **Rerunnable evidence:** `tools/agent-dpt/fixtures/` (the five test pages) + `p1-run1/`, `p1-run2/` (protocols and raw results)
- **Board:** mn-2521d5 (dpt bug fixes, open, claimable), mn-133b76 (the moon program dream, awaiting your conversion)
- **Journal:** two theory versions retired with evidence, pos-3e46bf live; lessons les-b2a63e, les-42c430, les-3b85ac

## What it means for Palingenesis

The redesign doesn't wait for any of this: Waves A–C run on the working composite — dpt floors, your eyes on screenshots, the guardrail paragraph. The moon program grows alongside, and its first real duty, when you say so, is judging Wave B's lane outputs — real stakes, first entries in the record.

## Open decisions

1. **Run 3** — needs fresh test pages (today's set is now calibration, not test). Say go.
2. **Make it permanent** — `dpt judge / probes / museum` as real tool verbs; waits on your taxonomy gate.
3. **Paste the guardrail** into 00-DESIGN-NORTH-STAR.md before Wave A launches (it lives in the Palingenesis repo).
