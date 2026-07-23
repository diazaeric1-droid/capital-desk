"""Methods & Limitations — the honest model card.

Names every assumption, convention, and limitation up front so a reviewing PE
judges the METHOD on its merits and knows exactly where the edges are. No fake
numbers; deterministic; no compute.
"""
from __future__ import annotations

import streamlit as st

import core
import product_theme as pt
import theme
from views import common

OIL, NRI, DISC, DECK = common.deck()

pt.masthead("capital", "Methods & Limitations",
            "What's real, what's modeled, the conventions, and the known edges.")
pt.context_bar([("Deck", DECK),
                ("Engines", f"AFE v{core.AFE_VERSION} · Capital v{core.CAPITAL_VERSION}"),
                ("Stance", "Judge the method — the data is illustrative")])
common.page_purpose(
    "**What this page answers:** what assumptions and conventions sit under "
    "every number in the product, and where are the known edges?\n\n"
    "**Use it before trusting a number:** this is the model card — real vs. "
    "synthetic data per surface, the single discounting convention, and every "
    "named limitation. If a result surprises you, the explanation is probably "
    "here.")

st.markdown(
    "**How to read this product.** The petroleum-engineering math is real and "
    "reconciles under one convention; the *data* behind the headline numbers is "
    "synthetic, because forward capital programs and most production aren't public. "
    "Evaluate the method and the honesty of the framing — not the absolute dollars. "
    "Everything below is the model card: assumptions stated, limitations named.")

pt.section("Data provenance", "Real vs. synthetic, per surface.")
st.markdown(
    "- **REAL (public record):** the Colorado ECMC slice on the Screen — 28 DJ Basin "
    "horizontals, ~2,000 well-months, 2017–2026 — and the *refrac backlog* derived "
    "from those wells' actual decline fits.\n"
    "- **SYNTHETIC (modeled, badged in-app):** the default 100-well Screen fleet "
    "(shares the suite's well identities; mixed exp/hyperbolic declines, realistic "
    "noise + a few deliberately low-R² wells), the 45-project capital backlog, the "
    "AFE cost templates, and the demo AFE tracker.\n"
    "- Provenance is badged on every page; full detail on the **Sources & BYOD** page.")

pt.section("Economics conventions", "One convention, applied everywhere.")
st.markdown(
    "- **Suite convention: Pxx = probability of exceedance — P10 is the high case, P90 the low case.** "  # noqa: E501 — the portfolio sentence stays verbatim on one line (pinned by test)
    "Every P10/P50/P90 label in this product (the Draft-AFE "
    "Monte-Carlo, the Optimizer's program P-curve) follows this SPE convention; "
    "the relabel is display-level only — the underlying percentile math is "
    "untouched and pinned by test.\n"
    "- **Discounting is effective-annual:** DF(m) = (1+r)^(m/12). A 10% input means "
    "10% per YEAR — not the 10.47% monthly compounding implies (pinned by a test).\n"
    "- **Severance + ad valorem** is a single deck input applied to BOTH the AFE net "
    "economics and the PDP screen, so the two value barrels identically. It is levied "
    "on the **gross wellhead value** (the statutory base): the price is taxed and LOE / "
    "gathering are deducted post-tax.\n"
    "- **NRI** governs revenue share; on the **Program** pages each project carries "
    "its OWN NRI from the backlog (the sidebar NRI drives Authorize + Screen).\n"
    "- **LOE** is a flat $/bbl on the screen; the AFE net economics deduct a $12/bbl "
    "operating cost (disclosed on the page).\n"
    "- **Horizon differs by engine** (a known simplification): AFE intervention "
    "economics run a 5-year horizon; the Capital Optimizer's project type curves run "
    "15 years. Immaterial at typical declines, but a steep AFE uplift-decline truncates "
    "more under the 5-year cut.")

pt.section("PDP Screener — method", "Per-well decline → forward forecast → PV10.")
st.markdown(
    "- **Fit:** exponential AND hyperbolic Arps on monthly oil; lower-SSE model wins "
    "(exponential on ties). R² is reported per well and **low-confidence fits "
    "(R² < 0.5) are flagged** — they still post PV10, so they're never silently trusted.\n"
    "- **Forecast forward from the LAST history month**, never t=0 (integrating from "
    "t=0 re-counts produced barrels and overstates remaining EUR ~2–3×).\n"
    "- **Terminal decline (Dmin):** a modified-hyperbolic switch to exponential once "
    "the instantaneous decline reaches Dmin (default 6%/yr, adjustable), so fat-tailed "
    "high-b wells don't over-forecast EUR. It only binds on wells whose fitted initial "
    "decline Di exceeds Dmin — a well already declining slower than the floor is "
    "unaffected.\n"
    "- **Gas:** valued by riding the well's **trailing-12-month GOR** off the oil "
    "decline at a gas price (so a gassing-up/down well's forward gas reflects its "
    "current GOR, not a lifetime average); oil and gas PV10 are broken out and current "
    "rate is shown in BOE/d.")
pt.section("PDP Screener — limitations", "")
st.markdown(
    "- Gas is GOR-ridden — **no separate gas decline, NGL/shrink/Btu, or basis "
    "differential**. NGL-rich or dry-gas wells need a fuller gas model.\n"
    "- **Gas carries an explicit gathering/processing cost** ($/mcf, on the Screen) "
    "deducted from gas revenue, so gas PV is not an un-costed upper bound; it still "
    "omits NGL/shrink/Btu and basis differential. Set the gas price to 0 for an "
    "oil-only screen.\n"
    "- The **economic limit is tested on the OIL rate only**, so any remaining gas "
    "beyond the oil cutoff is dropped — conservative (under-values gas-weighted wells).\n"
    "- **No water / SWD disposal cost** in the screen LOE (the suite's Deferment/PE "
    "apps model SWD drag; this quick-look does not).\n"
    "- PV10 is the **producing base only** — no PUDs, behind-pipe, G&A, or plugging "
    "liability. The $/flowing-BOE benchmark band is a rule-of-thumb, not a fitted comp set.")

pt.section("Capital Optimizer — method & limitations", "")
st.markdown(
    "- **Exact 0/1 MILP** (CBC) maximizing risked NPV under a capital budget + rig-day "
    "capacity; an **LP-relaxation bound** proves near-optimality; the baseline it beats "
    "is a **rank-by-efficiency first-fit** (not 'rank-and-cut').\n"
    "- **Honest edge:** ~3–5% ($4–8MM) over a competent greedy, and only when the rig "
    "limit binds — the value of optimizing two scarce resources jointly, not a 10× headline.\n"
    "- **Quarterly schedule** is a greedy bin-pack; projects that don't fit any earlier "
    "feasible quarter **spill into the final quarter and can exceed the per-quarter rig "
    "cap** (flagged in-app when it happens).\n"
    "- **Program Monte-Carlo** samples price (Normal) and each project's chance of "
    "success (Bernoulli → dry hole loses capex); per-project NPV(price) is interpolated "
    "and **linearly extrapolated** past the grid (NPV is linear in price), so stressed "
    "low/high decks aren't clamped. Dry-hole outcomes are correlated by an adjustable "
    "**geologic-correlation ρ** (single-factor Gaussian copula; default 0.3) — ρ=0 is "
    "independent (optimistic tail), higher ρ widens the downside for a single-basin "
    "slate. The mean is unchanged by ρ; only the spread moves. Still a screening "
    "P-curve, not a full reservoir simulation.\n"
    "- **Colorado refrac backlog** keeps the real wells' identities + decline shapes but "
    "the workover economics are modeled assumptions: incremental IP ≈ 2.0–3.5× current "
    "rate, capex ~$0.9–2.4MM, Pc ~0.62–0.85 — the load-bearing numbers a reviewer should "
    "interrogate.")

pt.section("AFE & Variance — method & limitations", "")
st.markdown(
    "- Cost templates are **synthetic Permian benchmarks**; the tangible/intangible "
    "(IDC) split and authority-routing thresholds are illustrative. On Draft AFE the "
    "line items are **fully editable** (add/remove/reprice; contingency and routing "
    "re-roll from the edits); **edited lines are session-only** — the tracker stores "
    "only the resulting total, and switching intervention re-seeds the benchmark.\n"
    "- The Draft-AFE **uplift decline is an exact Arps curve**: hyperbolic (qi, Di, "
    "b editable — the default) or the legacy exponential (b = 0), integrated over a "
    "**5-year horizon** through the same `econ_core` discounting kernel as "
    "everything else. At b = 0 the hyperbolic path is bit-identical to the legacy "
    "exponential model (pinned by a test). The uplift b is a **model choice, not a "
    "fitted parameter** — the Monte-Carlo samples rate/Di/price and holds b fixed.\n"
    "- The Draft-AFE **Well Trend chart** overlays the ASSUMED uplift on the well's "
    "actual history (matched by well id/name against the BYOD upload, the synthetic "
    "fleet, then the Colorado slice; baseline fit at PDP defaults). It is a "
    "sanity-check, not a fitted job forecast; wells absent from every source get an "
    "honest empty state (the demo ED-xxxH ids have no production source).\n"
    "- The generated **AFE document body prices the benchmark template with the "
    "exponential model** (the vendored schema carries no b / edited costs); a "
    "product addendum on the document discloses the on-page model, b, and edited "
    "total whenever they differ.\n"
    "- The Pipeline Board's **Net NPV uses a per-intervention type-typical uplift** "
    "(ESP swap 150 bopd, scale 60, …) — a ranking basis, NOT each well's real forecast "
    "(that lives in the well's diagnosis on Draft AFE).\n"
    "- The Pipeline Board's **status stepper shows the tracker's real machine** "
    "(draft → engineering review → finance review → approved → executed; 'rejected' "
    "is a terminal off-path branch). There is no separate 'closed-out' stage — "
    "close-out reconciliation is the Variance page.\n"
    "- The Draft-AFE **Monte-Carlo is GROSS NPV** (before WI/NRI), labeled as such.\n"
    "- Variance runs on demo closed-out actuals plus any AFE you execute live this "
    "session; **live actuals are session-only** and reset on reload.")

pt.section("Regulatory Filing — disclaimer", "")
st.markdown(
    "- The Form 7 / W-3 outputs are **draft field-mapping worksheets for review, NOT "
    "certified e-file payloads**. Field names track the public forms; reconcile against "
    "the current official form revision and your system of record before submitting.")

theme.data_badge("synthetic", "This page makes no numeric claims — it documents how "
                              "every other page computes and where its edges are.")
theme.references(["arps", "prms", "npv", "milp"])
