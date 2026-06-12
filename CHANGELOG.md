# Changelog

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
