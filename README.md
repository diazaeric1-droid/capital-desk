# Capital Desk

**The capital meeting in one product: authorize the work, optimize the program,
screen the deal.**

Capital Desk consolidates the Upstream Copilot Suite's capital-workflow apps into
one Streamlit product — the console a capital committee actually sits in front
of. Every number on every page is deterministic and runs with **zero API keys**;
an Anthropic key (bring-your-own, session-only) adds an LLM-written AFE
narrative and nothing else.

## Modules

Every page opens with an ℹ️ **"What is this page for?"** popover — plain-PE
language on what question the page answers and when to use it.

| Section | Page | What it does |
|---|---|---|
| **Authorize** | Pipeline Board | Every in-flight AFE in a SQLite tracker: status, days-in-status, delegation-of-authority routing ($ → required approver), >10% overrun supplement flags — and a per-AFE **status stepper** (draft → … → executed) with an explicit **"what's remaining to get this approved"** line, realized days-per-stage vs SLA, and the immutable audit trail |
| | Draft AFE | Manual inputs **or** a WellDiagnosis JSON → an **editable line-item cost table** (add/remove/reprice; contingency, IDC split, routing, and economics react live), the well's **actual production trend vs. the uplift assumption** (honest empty state when no source knows the well), an **exact Arps uplift decline** (hyperbolic b editable, exponential legacy mode preserved, curve plotted), WI/NRI net economics at the deck, Monte-Carlo P10/50/90 + tornado on the selected model, markdown + .docx export, submit-to-pipeline |
| | Variance | Actual vs. AFE on closed-out jobs — worst offender by absolute $ (unbudgeted lines never hidden), supplemental-AFE policy flags |
| **Program** | Backlog | The realistic 45-project inventory (13/45 sub-economic at the $70 deck — deliberately), a **Colorado refrac backlog derived from real PDP wells**, or a bring-your-own backlog CSV |
| | Optimizer | Exact 0/1 MILP (CBC) vs. the greedy baseline at the same budget + rig-day limits, LP-relaxation optimality bound, quarterly schedule, **and a program-level Monte-Carlo (P10/P50/P90, P(loss)) over price + dry-hole risk** |
| | Frontier & Sensitivity | Efficient frontier (optimal NPV re-solved per budget) + price-deck sensitivity (program re-optimized per price), with on-page budget/rig controls |
| **Screen** | PDP Screener | Per-well Arps fit (exponential AND hyperbolic) on monthly oil, forecast **forward from the last history month**, remaining EUR, **PV10 on oil + gas**, deal rollup with $/flowing-bbl and **$/flowing-BOE vs. an A&D benchmark band**. Runs on the **suite-shared 100-well synthetic fleet** (default), the **real Colorado ECMC** slice, or a BYOD upload |
| **File** | Regulatory Filing | **New.** Deterministic draft worksheets for **CO ECMC Form 7** (monthly production) and **TX RRC Form W-3** (plugging, from a P&A AFE); BYOK cover note |
| **Data** | Sources & BYOD | Provenance for every dataset + the three upload contracts (WellDiagnosis JSON, backlog CSV, PDP monthly CSV); nothing stored server-side |

The **detect → authorize → reconcile** loop closes in-product: a PE Copilot
WellDiagnosis drafts an AFE → the Pipeline Board advances it to **executed** →
its actuals appear on the **Variance** page.

## Built on

| Component | Version | Contribution |
|---|---|---|
| [afe-copilot](https://github.com/diazaeric1-droid) | v0.6.2 | Cost templates + rollup, net economics + Monte-Carlo, SQLite tracker + authority routing, variance analyzer, docx builder, LLM drafter (BYOK) |
| [capital-optimizer](https://github.com/diazaeric1-droid) | v0.2.3 | 45-project backlog + CSV contract, per-project risked economics, MILP/greedy/LP-bound optimizers, quarterly scheduler |
| **PDP Screener** (`src/pdp.py`) | new in this product | Arps fits + remaining EUR + PV10 deal quick-look — built on `afe.econ_core` discounting, run on the **suite-shared 100-well synthetic fleet** (default), **real Colorado ECMC production**, or a BYOD upload |

## Architecture

Vendored-apps + alias-loader (the pe-pipeline pattern): each component repo is
mirrored byte-identical under `apps/` and `core.py` loads each app's `src/`
package under a distinct importlib alias (`afe`, `capital`) so the whole product
runs in **one Python process** — no subprocesses, no per-app environments, one
`pip install`. See `VENDORING.md` for the exact mirror record.

```
app.py             product shell: global price deck + st.navigation
core.py            alias loader + bootstrap + headless API (no streamlit import)
src/pdp.py         PDP screener math + well-id/name matcher (pure functions)
src/uplift.py      exact-Arps uplift economics + seeded MC for Draft AFE (pure)
src/afe_costs.py   editable AFE cost-line rollup (pure; mirrors cost_db exactly)
src/afe_status.py  AFE status-journey helpers for the Pipeline Board stepper
src/regulatory.py  Form 7 / W-3 draft-worksheet field mapping
views/             one module per page (presentation only)
apps/              byte-identical vendored components (read-only)
data/synthetic/    suite-shared 100-well fleet as monthly oil (committed, seeded)
data/real/         real Colorado ECMC production (mirrored, reproducible)
data/state/        runtime artifacts (tracker DB) — gitignored, self-seeding
```

`afe.econ_core` is the suite's single discounting kernel — effective-annual,
`DF(m) = (1+r)^(m/12)` — re-exported by `core.py` and used by **all three**
modules, so the AFE you authorize, the program you optimize, and the deal you
screen are valued under one convention.

## Run locally

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

First run seeds the demo AFE tracker (12 AFEs) into `data/state/` automatically.
Tests: `.venv/bin/pip install pytest && .venv/bin/python -m pytest -q`.

## Honest framing (read this before the demo)

- **The backlog is realistic, not flattering.** 13 of its 45 projects are
  sub-economic at the $70 deck, capex is lumpy, and total demand far exceeds any
  one-year budget — that is what makes the constraints bind.
- **The optimizer's edge is real but modest:** ~3–5% ($4.4–7.8MM) over a
  competent greedy ranking, and only when the rig limit binds — the value of
  optimizing two scarce resources jointly. When only the budget binds, greedy
  nearly ties. The LP-relaxation bound is reported so "near-optimal" is provable,
  not asserted.
- **PDP forecasts start at the last history month.** Integrating an Arps fit
  from t=0 re-counts produced barrels and overstates remaining EUR ~2–3x (a real
  bug found and fixed elsewhere in this suite — pinned here by a test).
- **Discounting is effective-annual everywhere.** A 10% input means 10% per
  year; `econ_core.discount_factors([12], 0.10) == 1.10` exactly, by test.
- **Colorado production is genuinely real** (ECMC public records, reproducible
  fetch script) and selectable on the Screen page. The default screen fleet, the
  backlog, the cost templates, and the tracker contents are synthetic — clearly
  badged in-app — because operators' forward capital and most private production
  data are never public. The synthetic screen fleet reuses the **same 100 well
  identities** the sibling products use, so the asset reads coherently across the
  suite.
