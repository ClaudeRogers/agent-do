# DPT audit fixtures — the falsification set (2026-08-22)

Five controlled pages built for the dpt audit (`.handoff/dpt-audit-2026-08-22.md`) and
reused as the standing validation set for the Moon Program's Axiom Judge
(`.handoff/dpt-moon-program-2026-08-22.md`, P1; dream mn-133b76).

| Fixture | What it is | Measured dpt score (2026-08-22 engine, 1440x900) |
|---|---|---|
| canon-today.html | Honest implementation of the liked Palingenesis direction, Today surface (Erik 2026-08-22: a direction he liked, NOT a ratified canon — nothing is approved until his decision bar says so) | 75 B |
| canon-dossier.html | Same liked direction, flagship Dossier surface | 67 C+ (false critical: touch targets) |
| barf.html | Disciplined neon-template anti-canon (the banned aesthetic) | 66 C+ |
| broken.html | Deliberately broken craft (floor-sensitivity control) | 29 F (correct) |
| oklch-probe.html | All colors in oklch() (Tailwind v4 default) | 53 D+ with chromatic 97 — parser blindness proof |

Axiom Judge falsifier (run blind, on renders):
- canon-dossier: cheap round-trip grammar AND far from the generative prior — passes A2+A3
- barf: cheap round-trip, AT the prior's center — fails A3 (lawful but nothing learned)
- broken: round-trip failure (arbitrary residue) — fails A2
- recognitionoracle.com (live): passes all three

A judge that cannot reproduce that ordering refutes the axioms as measured (pos-99cee7).
Scans/screenshots are regenerable: `agent-do browse open "file://$(pwd)/tools/agent-dpt/fixtures/<name>.html"` then `agent-do dpt scan --current --json`.

## P1 run 1 (2026-08-22) — executed

The falsifier above FIRED. Full pre-registered protocol and raw results: `p1-run1/protocol.md` + `p1-run1/results.json`; narrative: `.handoff/dpt-moon-program-2026-08-22.md` §"P1 run 1 — results". Outcome: A1 physics validated 4/4; A2 100-word round-trip refuted as discriminator (all exhibits 8-9); A3 self-null refuted for barf (the 2026 prior moved past neon — familiarity leg mandatory). Positions: pos-99cee7 withdrawn on evidence, pos-1834a8 is the live v2.

## P1 run 2 (2026-08-22, same day) — executed
Revised measures: derivation-form 40w grammars + genre-familiarity leg. Protocol + raw: `p1-run2/`. Outcome: broken collapsed 8.0→2.0 (derivation kill works); barf familiarity 10.0 unanimous (template kill works); canon A2 6.0 missed its ≥7 clause (law transmitted, voice free — absolute thresholds abandoned); recognitionoracle familiarity 8.5 (genre-membership ≠ kit-interchangeability). pos-1834a8 withdrawn; pos-3e46bf is live v3 (gap-scored A2, product-scored A3).

## mn-55530d (2026-08-22, later same day) — residual false positives retired
Fixed engine baseline at 1440x900: canon-today **85** clean, canon-dossier **86** clean (zero criticals — sr02 rebuilt on WCAG 2.5.8: 24px floor + inline-text exemption, 3 chips exempt, Advance passes; ts01 prose-only; ts09 band to 4.5x; cf12 status-role exempt; cf04 status-chip allowance; aa10 sticky/fixed excluded), broken **30 F** with all real criticals intact, oklch-probe **76** clean, barf **INCOMPLETE** (honest refusal). Clearance position: pos-b47840 withdrawn met/superseded; pos-d19b3f live — dpt cleared as floor + regression instrument, never a taste target.
