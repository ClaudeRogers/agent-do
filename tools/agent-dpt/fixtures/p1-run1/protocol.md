# P1 Axiom Judge — pre-registered protocol (2026-08-22, before measurement)

Position under test: pos-99cee7. Validation set: tools/agent-dpt/fixtures/ + recognitionoracle.com hero.

## Parameters (fixed before any measurement)
- Grammar budget: 100 words per exhibit, same for all (forces compression; the budget does the discriminating, not effort).
- Blur probe: CSS filter blur(10px) at 1440x900 (squint approximation). Grayscale probe: grayscale(100%).
- A2 fidelity scale (fresh judge, blind to which image is original): 0 = unrelated designs, 10 = same design system, obviously a faithful build. PASS >= 7. Judge also lists concrete divergences.
- A3 family scale (fresh judge, position-shuffled unlabeled sets): 0 = clearly different generative habit, 10 = interchangeable family member. SURPRISE PASS (far from prior) <= 3; AT-PRIOR >= 7.
- Reconstruction: fresh agents, zero context beyond the grammar; system fonts; no file reads.
- Self-null: K=2 defaults per brief, deliberately plain prompts (sampling the prior's mode).

## Pre-registered predictions
| Exhibit | A1 physics | A2 fidelity@100w | A3 family-vs-null | Composite |
|---|---|---|---|---|
| canon-dossier | pass (hierarchy survives blur; reads gray) | >=7 | <=3 | PASS all |
| barf | probes pass-ish (blocks survive) | >=7 | >=7 (AT prior) | FAIL A3 only |
| broken | fail probes (no hierarchy under blur) | <4 | n/a | FAIL A2 (+A1) |
| oracle (live) | AT RISK — recorded pre-probe: 17 real hard contrast fails (white on coral CTA 2.86:1; coral accents 2.55:1) | >=6 | <=3 | predicted pass; A1 now doubtful — report honestly |

Falsification rule: if the composite cannot reproduce the ordering (dossier passes A2+A3; barf fails exactly A3; broken fails A2), the axioms as measured are refuted and pos-99cee7 flips.

Honesty notes (recorded in advance): I authored four exhibits this morning — grammar-writing and probe-reading are NOT blind; blindness lives in (a) reconstructors who never saw originals, (b) fresh judges scoring unlabeled images, (c) deterministic corroboration from dpt raw layer data (never its score). The productized P1 moves grammar-writing to a fresh instance too.

## The four grammars (the A2 compression artifacts, 100-word budget)

### G-dossier
Dark editorial research dossier. Ground warm charcoal #1B1917; cream text #E7E3DA; muted #A69D90; hairline rules cream@14%. Single accent sage green; verdict amber and soft clay. Georgia-class serif for headlines and prose; small sans for data; 12px uppercase letterspaced kickers. Top bar: serif PALINGENESIS wordmark, four quiet nav links, avatar dot; breadcrumb under. Serif h1 ~67px tight, max 18ch. Outline green GREENLIGHT chip + muted lineage line. Six-metric band: small-caps labels over 21px tabular numbers, hairline separators. 65ch prose, green dotted-underline cited links with superscripts. Sticky bottom bar: 'Your decision becomes part of the lineage', outline clay Kill, filled green Advance.

### G-barf
Neon analytics dashboard. Ground #0B0E1A; panels #131735 with #232B55 borders, 12px radius, cyan glow shadows; text white; muted blue-grey #8B90A0. Accents cyan #00E5FF, purple #7C4DFF, blue #2979FF, green #00E676, red #FF3B5C. Inter-class sans only; 10-12px uppercase card labels; 28-32px bold stat numbers. Left 232px sidebar: gradient INSIGHTSTREAM logo, seventeen icon+label items, glowing active pill. Top row: Dashboard h1, red LIVE outline pill, filled cyan Export, purple Share, blue Upgrade Now. Four-column KPI grid, purple-gradient hero card spanning two. Below: cyan-blue gradient bar chart panel, conic-gradient donut panel, 'View all'/'Learn more' cyan links.

### G-broken
Cluttered white deals portal. Arial default; stretched Impact logo (1.35x horizontal, clips left edge); Comic-Sans grey tagline; Courier uppercase letterspaced h4. Tiny grey 9-11px text everywhere; pure-black-on-white body; full-width black banner, white uppercase shouting. Red-on-blue HOT DEAL chip beside blue-ground green SAVE 50%. Justified 1280px intro paragraph, tight leading; centered narrow-leading story paragraph. Six stacked white rounded boxes, radii 3-33px increasing, shadows pointing inconsistent directions, each holding two tiny grey lines. Bare unlabeled inputs; small Submit, OK, Send, Continue buttons; one filled red Delete. Rows of 10px generic links: Click here, More, Info. Dense tiny grey footer sentences.

### G-oracle
Serene consumer landing hero, full viewport. Ground: soft radial pastel wash — pale lavender edges #EDE7F3 melting through rose, cream, mint center glows; no hard edges anywhere. Top: small serif 'Recognition Oracle' wordmark left, tiny muted 'Sign in' right. Everything else centered vertically: two-line Playfair-class display serif ~83px — 'Know yourself.' near-black, 'No jargon required.' muted lavender-grey; beneath, three short centered sans lines ~20px purple-grey: '12,000 years of pattern recognition.', '19 traditions.', 'One Oracle. Zero jargon.'; then a single coral #E8786B pill, white text, 'Get your free report'. Vast breathing margins; nothing else on the page.

## Self-null briefs (deliberately plain — sampling the mode)
- B-dossier: "Build a desktop detail page for one innovation candidate in an autonomous agricultural-innovation platform: name, status, six fitness metrics, mechanism description with sources, an economics table, reviewer verdicts, approve/reject actions. Single self-contained HTML file, 1440x900, system fonts."
- B-dash: "Build a desktop analytics dashboard page for a SaaS product: KPIs, a chart area, navigation. Single self-contained HTML file, 1440x900, system fonts."
- B-oracle: "Build a desktop landing page hero for a consumer product called Recognition Oracle that generates personalized self-knowledge reports. Single self-contained HTML file, 1440x900, system fonts."
