# Changelog

## [0.3.0] — 2026-06-14

Lever build-out: deeper economics + a fourth module + program risk + a live loop.

### Added
- **Regulatory Filing module (new `File` section).** Deterministic draft worksheets
  mapping product data onto **CO ECMC Form 7** (monthly production, from the PDP
  fleet) and **TX RRC Form W-3** (plugging record, from a P&A AFE), with an
  honest "review worksheet, not a certified filing" frame and a BYOK cover note.
- **Gas in the PDP screen.** PV10 now values **oil + gas** — gas rides each well's
  producing GOR off the oil decline at a gas-price input; oil-only and total PV10
  are broken out per well, current rate is reported in **BOE/d**, and the synthetic
  fleet now carries `gas_mcf`. Set gas price 0 for the oil-only view.
- **Deal benchmarks (Screen).** $/flowing-BOE vs a typical PDP A&D band, PV10/asking
  multiple, and PV10 per flowing BOE.
- **Program-level Monte-Carlo (Optimizer).** P10/P50/P90 + P(loss) on the whole
  funded program over price *and* each project's chance of success (success books
  NPV at the sampled price, a dry hole loses its capex), with a distribution
  histogram. The MC mean tracks the deterministic risked NPV (a built-in check).
- **Colorado refrac backlog (real-well Program).** A backlog source that derives
  refrac/recompletion candidates from the **real** Colorado ECMC fleet's decline
  fits — real well identities + shapes, modeled workover economics — so the
  optimizer runs the same MILP on real wells.
- **Live detect→authorize→reconcile loop.** The Pipeline Board can advance an AFE
  through review → approval → **execution**; executing it generates closed-out
  actuals that appear on the **Variance** page — the chain closed in-product.

### Changed
- **Severance is now a deck-level input** applied to BOTH the AFE net economics and
  the PDP screen, so the two value barrels identically (was: PDP charged severance,
  the AFE did not).
- **Pipeline "Net NPV" uses a per-intervention type-typical uplift** (ESP swap 150
  bopd, scale 60, paraffin 30, …) less severance — so the ranking reflects the kind
  of job, not just its cost (was: a flat +100 bopd for every AFE).
- **Draft AFE inputs persist.** The form is keyed and an example/upload/chained
  diagnosis loads only when the source changes — manual edits are no longer
  clobbered on every rerun.
- **Frontier has its own budget/rig sliders** (shared with the Optimizer), so it
  works when landed on first.

### Tests
- `tests/test_pdp_fleet.py`: gas adds value and oil-only is backward-compatible;
  severance reduces PV10 monotonically. `tests/test_core.py`: nav is now 5
  sections / 9 pages. 36 tests pass.

## [0.2.0] — 2026-06-14

PE-readiness pass before live tester access: requested drill-downs, a shared
fleet for the deal screen, and chart/table legibility.

### Added
- **Screen now runs on the suite-shared 100-well synthetic fleet by default**,
  with the real Colorado ECMC slice and a BYOD upload as the other two sources.
  The synthetic fleet reuses the **same well identities** (`well_001`…`well_100`)
  the sibling products (Operations Center, Engineering Workbench) use — same
  basin / area / formation / lift / lateral from the shared `fleet_registry` —
  rendered as monthly oil so the same asset reads coherently across the suite.
  Committed at `data/synthetic/fleet_pdp.csv` (deterministic seed, instant
  cold-start); generator `data/synthetic/generate_fleet_pdp.py` regenerates it
  byte-identical. Each well has a realistic Arps decline and a staggered
  first-production month → a genuine maturity + PV10 spread (100/100 fit,
  R² ≥ 0.96), not 100 identical wells.
- **Variance — category drill-down.** A "Variance by Category" bar chart
  (overruns red, savings green) plus a category selector that drills the
  Line-Level Detail into the AFE lines behind a single category, with a
  per-category budget/actual/variance KPI row. Variance % column added; the
  100%-unbudgeted line is still surfaced, never dropped.
- **Per-well identity** on the PDP drill-down (name · basin · area · formation ·
  lift), enriched from the shared registry for synthetic wells.

### Changed
- **"Risked NPV by Project" (Backlog) is now legible and ranked.** Every bar is
  labeled with its project id, the #1 project is green + annotated with its name
  and value, and hovering any bar shows its name and type. The Project Inventory
  table is now **sorted by risked NPV with a Rank column**, so the top project is
  unambiguous (previously the chart hid all x labels and the table was unsorted).
- **PV10-by-Well chart** caps to the top 25 wells (highest in green) with a
  concentration caption, so a 100-well fleet stays readable; the full ranking
  stays in the table + CSV.
- PDP asking-price defaults to 0 (screen value only) instead of a fixed $25MM,
  which mis-framed large fleets; severance help is no longer Colorado-specific.

### Hardened (production-readiness audit)
A multi-agent adversarial audit (PE/VP scrutiny) drove these correctness/honesty
fixes ahead of live tester access:
- **Pipeline ↔ Variance reconciliation.** The variance demo and the live tracker
  shared AFE numbers but described different jobs; the Pipeline Board even mixed a
  tracker gross cost with a variance overrun in one row and flagged a "Supplement
  REQUIRED / +23%" on an AFE still in *engineering review* (no actuals can exist).
  Renumbered the closed-out variance AFEs to distinct prior-year IDs
  (`AFE-2025-0188/0191`, documented in VENDORING.md) and removed the cross-dataset
  Variance/Supplement columns from the Pipeline Board — actual-vs-AFE now lives
  only on the Variance page, where it is self-consistent.
- **Honest deck.** Program pages now show "NRI per-project" (each backlog project
  carries its own NRI); the sidebar NRI drives Authorize + Screen only, instead of
  appearing to feed the program economics it never touched.
- **Draft AFE disclosures.** Surfaced the hidden $12/bbl LOE; relabeled the
  Monte-Carlo as **Gross NPV (before WI/NRI)** so it no longer reads as net;
  marked First-Year Add as gross; and snapshotted the generated AFE so the
  preview, .docx cover, filename, and submitted pipeline row can't disagree after
  an edit (with a staleness warning).
- **PDP screen.** Disclosed that PV10 is **oil-only** (gas/NGL excluded); flagged
  low-confidence wells (R² < 0.5) that still carry material PV10; added a Name
  column and corrected the upload-source message.
- **Program legibility/correctness.** IRR's 500% clamp sentinel renders as
  ">500%"; `inf` payout renders as "—"; the frontier price strip always includes
  the actual deck price (the green "current deck" bar no longer vanishes off a
  $50/60/70/80 grid); the frontier flat tail is correctly attributed to the
  binding rig limit, not "diminishing capital value"; the optimizer scatter labels
  its top funded project and is hardened against a zero-rig backlog; added a
  portfolio capital-efficiency KPI and a quarterly-overflow warning.
- **Provenance.** Colorado slice corrected to span **2017–2026** (earliest record
  is 2017-04).

### Tests
- New `tests/test_pdp_fleet.py`: the synthetic fleet is committed, schema-valid,
  deterministic (byte-identical regeneration), shares the registry identity, and
  screens 100/100 wells with a realistic spread; the source resolver defaults to
  synthetic and maps the real label to Colorado.

## [0.1.0] — 2026-06-11

Initial release — the capital workflow console: authorize → program → screen.

### Added
- **Authorize** (from afe-copilot v0.6.2, condensed): Pipeline Board (SQLite
  tracker, authority routing, audit trail, supplement flags), Draft AFE (manual
  or WellDiagnosis-JSON input, cost rollup with tangible/IDC split, WI/NRI net
  economics, Monte-Carlo P10/50/90 + tornado, markdown + .docx export,
  submit-to-pipeline), Variance (actual-vs-AFE with >10% supplement policy).
- **Program** (from capital-optimizer v0.2.3): Backlog (45 projects, 13
  sub-economic at the $70 deck, BYOD CSV contract + template), Optimizer (exact
  MILP vs. greedy at the same budget + rig limits with the honest ~3–5% /
  $4.4–7.8MM gap framing and LP-bound note, quarterly schedule respecting
  earliest start), Frontier & Sensitivity (budget frontier + price strip, both
  re-optimized per point at the global deck).
- **Screen** (new `src/pdp.py` — the product's only new math): per-well Arps
  fits (exponential + hyperbolic via scipy, lower SSE wins) on monthly oil,
  forecast forward from the last history month, remaining EUR to the economic
  limit, PV10 through `afe.econ_core`, deal rollup with $/flowing-bbl and a
  PV10-vs-asking verdict — running on real Colorado ECMC production (28 DJ
  Basin wells) or a BYOD monthly CSV.
- **Data**: consolidated provenance + the three BYOD contracts with template
  downloads and schema validation.
- Product chrome: global price deck (price / NRI / effective-annual discount),
  BYOK-optional Anthropic key (session-only), enterprise theme, product switcher.
- 28 product tests, including pinned numeric invariants: PDP remaining EUR vs.
  the exponential closed form (<0.5%), PV10 vs. a brute-force discounted sum
  (<1e-6), Draft-view economics bit-identical to `afe.economics`, optimizer
  results matching the component's committed eval summary ($143.66MM MILP vs.
  $139.29MM greedy at $60MM/170 rig-days), and the effective-annual lock
  (`discount_factors([12], 0.10) == 1.10`).

### Architecture
- Vendored-apps + importlib alias loader (`afe`, `capital`) — byte-identical
  mirrors, no import rewriting needed (see VENDORING.md). One process, one
  `pip install`, Python 3.12.
