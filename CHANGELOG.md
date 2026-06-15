# Changelog

## [0.4.3] — 2026-06-15

Promoted the three substantive re-audit *disclosures* into real code (the rest are
documented engineering choices).
- **Severance on the gross wellhead base.** Both the PDP screen and the AFE net
  economics now tax the gross price and deduct LOE/gathering post-tax (the statutory
  base), instead of taxing the post-LOE margin. The two engines still value a barrel
  identically (pinned by a test); ~1–2% more tax than before.
- **Gas operating cost.** A gathering/compression/processing input ($/mcf, default
  $0.50) is deducted from gas revenue, so gas PV is no longer an un-costed upper bound.
- **Geologic correlation (ρ) in the program Monte-Carlo.** Dry-hole outcomes are now
  correlated via a single-factor Gaussian copula with an adjustable ρ (default 0.3) —
  ρ=0 is independent (optimistic), higher ρ widens the downside for a single-basin
  slate. The mean is unchanged by ρ; only the P10/spread moves.

Left as documented choices (not bugs): the AFE 5-yr vs Optimizer 15-yr horizons
(short intervention life vs new-well life), and the oil-rate economic limit
(conservative). 48 tests pass.

## [0.4.2] — 2026-06-15

Closed the remaining re-audit tail — the Regulatory Filing worksheet field-mapping
warts (all bounded by the "draft, not a certified filing" disclaimer) + two low items.
- **W-3 Plugging Record:** stopped sourcing Total Depth from the well's lateral length
  (wrong quantity), the proposed plug date from the AFE's last-status timestamp, and the
  operator from a hardcoded "Demo Operator LLC" — all now render "— (enter …)" prompts,
  and the note no longer claims operator/API/TD carry from the AFE (they aren't tracked).
- **CO Form 7:** defaults to the REAL Colorado source; selecting the synthetic fleet now
  warns that it's a Texas/Permian demo identity that doesn't correspond to a Colorado well.
  Water renders "— (not in source)" instead of a misleading reported 0 when absent.
- **Colorado refrac backlog:** the incremental IP now anchors on a robust trailing-6-month
  mean rate, not a single noisy last month.
- **Disclosure:** Dmin only binds on wells whose Di exceeds it (Methods page + slider help).

## [0.4.1] — 2026-06-15

New-surface re-audit (a second adversarial pass over everything added since v0.1.0,
since the original audit predated it). 25 findings; the three real correctness defects
are fixed, the rest are disclosed.

### Fixed
- **Pipeline Board crash** when a non-advanceable AFE (e.g. the seeded `rejected`
  AFE-2026-0052) was picked in the lifecycle dropdown — `STATUS_ORDER.index()` raised
  on the render path (the try/except only wrapped the click). Now guarded with a
  terminal-state notice; also corrected the "executed → see Variance" caption that
  over-promised for pre-seeded executed AFEs.
- **Program Monte-Carlo** flat-clamped sub-$40 price draws to the $40 NPV, making the
  P10 / P(loss) optimistic at stressed decks. Now **linearly extrapolates** past both
  grid ends (NPV is exactly linear in price).
- **PDP gas** rode a single lifetime-average GOR; the displayed "current" gas rate
  could contradict the well's own last month ~5×. Forward GOR now uses a **trailing
  12-month** window and the current gas rate is read from the **actual last producing
  month**.
- **Dmin** terminal decline made monotone for the (unreachable-on-shipped-data) regime
  where Dmin ≥ a well's fitted Di. Form 7 GOR shows "—" for a zero-oil month.

### Disclosed (Methods & Limitations + captions)
- Gas carries no gathering/processing cost (gas PV is an upper bound); severance is on
  the post-LOE base; AFE 5-yr vs Optimizer 15-yr horizons; the economic limit is on oil
  only; the Colorado refrac uplift/capex/Pc ranges; and the program-MC P10 is optimistic
  under correlated single-basin geology (now read as a screening floor).

## [0.4.0] — 2026-06-15

Peer-review hardening — pre-empt the three critiques a reservoir-minded PE will raise.
- **Terminal decline (Dmin) on the PDP forecast.** A modified-hyperbolic switch to
  exponential once a well's instantaneous decline reaches Dmin (default 6%/yr,
  adjustable on the Screen), so fat-tailed high-b hyperbolic fits don't over-forecast
  EUR. Reduces to plain Arps for exponential fits / Dmin ≤ 0. Pinned by a test.
- **Realistic synthetic fleet.** The 100-well screen fleet is no longer suspiciously
  perfect: a mix of exponential + hyperbolic declines, per-well noise tiers, and a few
  mid-life workover/dip disruptions → R² spans ~0.14–1.00 (median ~0.97), so the
  low-confidence (R² < 0.5) guard actually fires and the demo reads like real data.
- **Methods & Limitations page** (new, under Data). The honest model card: real vs.
  synthetic per surface, every economics convention, and the named limitations
  (oil-only-ish gas, no SWD cost, scheduler overflow, type-typical AFE uplift, gross MC,
  session-only live actuals, draft-not-certified filings). Pre-empts the gotchas.

## [0.3.1] — 2026-06-14

Low-value polish sweep (the remaining audit tail), no behavioural changes:
- **Honesty/wording:** the greedy baseline is now described as a "rank-by-efficiency
  first-fit" (not "rank-and-cut"); the Frontier docstring no longer cites a "$55 /
  next $10MM" that the charts don't sample; the vendored variance engine docstring
  drops its unimplemented "vendor / rig" breakdown promise; the Variance page renames
  "Line-Level Detail" → "AFE Line Detail", spells out the 100%-unbudgeted case, and
  drops an inapt NPV citation.
- **Dead code/state:** removed the write-only `data_source` session state (6 writes +
  the default); removed a dead `econ_frame` solve inside the cached frontier.
- **Surfaced/added:** component engine versions (AFE v0.6.2 · Capital v0.2.3) now show
  on the Data page; the Backlog inventory adds an **F&D ($/bbl)** column benchmarked to
  ~$8–15/bbl Permian; the Data page's context-bar labels use the canonical source names.
- **Perf:** the PDP drill-down fit is cached (no re-fit on unrelated reruns).
- **CI:** opt the runner's JS actions into Node 24 (Node 20 is being retired).

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
