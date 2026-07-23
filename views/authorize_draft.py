"""Draft AFE — diagnosis in, decision-ready AFE out.

Manual inputs or a WellDiagnosis JSON (chained from the Production Engineer
Copilot) become a costed AFE: an EDITABLE line-item cost table (add / remove /
reprice; contingency, IDC split, routing, and economics react live), the well's
ACTUAL production trend next to the uplift assumption, an exact Arps uplift
decline (hyperbolic b editable, exponential legacy mode preserved), WI/NRI net
economics at the global deck, Monte-Carlo P10/50/90 with a tornado, and a
markdown + .docx download. Every number is deterministic — the LLM narrative
alone is BYOK-optional (key in the sidebar).
"""
from __future__ import annotations

import datetime as _dt
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import core
import product_theme as pt
import theme
from src import afe_costs, pdp, uplift
from views import common

ss = st.session_state
OIL = float(ss.get("oil_price", 70.0))
NRI = float(ss.get("nri", 0.80))
DISC = float(ss.get("discount", 0.10))

UPLIFT_HYP = "Hyperbolic (Arps)"
UPLIFT_EXP = "Exponential (legacy)"

pt.masthead("capital", "Draft AFE",
            "Turn a well diagnosis into a costed, routed, economics-backed AFE.")
pt.context_bar([
    ("Deck", common.deck()[3]),
    ("Data", "Benchmark cost templates (synthetic Permian) — editable below"),
    ("Narrative", "BYOK-optional — all numbers keyless"),
])
common.page_purpose(
    "**What this page answers:** what will this intervention cost, is it worth "
    "it at the deck, and who has to sign it?\n\n"
    "**Use it when** a diagnosis (yours or a PE-Copilot JSON) says a well needs "
    "a job: pick the intervention, **edit the line-item costs** in the table "
    "below, set the uplift and its exact decline curve, sanity-check against "
    "the well's real production trend, then generate the AFE document and "
    "submit it to the Pipeline Board.")

# ---- diagnosis input --------------------------------------------------------
pt.section("Diagnosis", "Load an example, upload a WellDiagnosis JSON, or type it in.")

# Product-local examples FIRST (keyed to suite well ids that resolve in the
# bundled production sources, so the trend panel lights up out-of-the-box), then
# the vendored component examples (ED-xxxH ids — no production source, honest
# empty state, kept for schema continuity).
_example_paths: dict[str, Path] = {}
for _d in (core.PRODUCT_EXAMPLES_DIR, core.EXAMPLES_DIR):
    if _d.exists():
        for _p in sorted(_d.glob("well_diagnosis*.json")):
            _example_paths.setdefault(_p.name, _p)
c_src1, c_src2 = st.columns(2)
with c_src1:
    chosen = st.selectbox("Example diagnosis",
                          ["(manual)"] + list(_example_paths),
                          help="well_diagnosis_well_017 is keyed to a suite well "
                               "(well_017 · Reeves 17H) with bundled production "
                               "history — pick it to see the Well Trend panel "
                               "populated end-to-end. The ED-xxxH examples are the "
                               "component's originals (no production source).")
with c_src2:
    up = st.file_uploader("WellDiagnosis JSON (from PE Copilot)", type=["json"],
                          help="Validated before it can become an AFE — bad fields "
                               "are reported in plain English.")

interventions = list(core.afe_cost_db.COST_TEMPLATES)

# Form fields live in keyed session state, so MANUAL EDITS PERSIST across reruns.
# An example / upload / chained diagnosis is applied to the form ONLY when the
# source actually changes (tracked by a token), instead of re-clobbering the form
# on every rerun (the old value= pattern silently discarded manual edits).
_DEFAULTS = {
    "d_well_id": "ED-001H", "d_api": "42-109-12345", "d_field": "Delaware Basin",
    "d_operator": "Operator LLC", "d_intervention": interventions[0],
    "d_requested_by": "Eric Diaz, Staff PE",
    "d_diagnosis": ("Scale signature with declining intake pressure; treatment "
                    "required before mechanical work."),
    "d_rate": 100.0, "d_decline": 0.6, "d_wi": 1.0,
    "d_uplift_model": UPLIFT_HYP, "d_b": uplift.DEFAULT_B,
}
for _k, _v in _DEFAULTS.items():
    ss.setdefault(_k, _v)

# An ACTUAL re-pick of the example selectbox makes that example fresh again
# (the seen-set below otherwise applies each token at most once).
if chosen != ss.get("_ex_choice"):
    ss["_ex_choice"] = chosen
    ss.setdefault("_diag_tokens_seen", set()).discard(f"example:{chosen}")

preset: dict = {}
token = "manual"
# Session presets carry a sequence number (bumped by common.set_diag_preset), so
# a FRESH handoff from another page (PDP Screener drill-down, Variance supplement
# flag, the trend quick-fill below, the Data page) is applied exactly once — even
# if an example is still selected in the box, and even if an older session preset
# was already consumed.
_sp_token = f"session-preset:{int(ss.get('_diag_preset_seq', 0))}"
if up is not None:
    try:
        payload = json.loads(up.getvalue().decode("utf-8"))
        diag_ok = core.afe_models.AFEDiagnosis.from_pe_copilot(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        st.error(f"Diagnosis rejected: {exc}")
        st.stop()
    preset = {k: getattr(diag_ok, k) for k in (
        "well_id", "api_number", "field", "operator", "intervention",
        "primary_diagnosis", "incremental_rate_bopd",
        "expected_uplift_decline_per_yr", "requested_by")}
    token = f"upload:{up.name}:{up.size}"
    st.success(f"Validated diagnosis for {diag_ok.well_id} ({diag_ok.intervention}).")
elif ss.get("diag_preset") and _sp_token not in ss.get("_diag_tokens_seen", set()):
    preset = ss["diag_preset"]          # freshly chained in from another page
    token = _sp_token
elif chosen != "(manual)":
    preset = json.loads(_example_paths[chosen].read_text())
    token = f"example:{chosen}"


def _apply_preset(p: dict) -> None:
    text_map = {"d_well_id": "well_id", "d_api": "api_number", "d_field": "field",
                "d_operator": "operator", "d_requested_by": "requested_by",
                "d_diagnosis": "primary_diagnosis"}
    for key, src in text_map.items():
        if p.get(src) is not None:
            ss[key] = str(p[src])
    if p.get("intervention") in interventions:
        ss["d_intervention"] = p["intervention"]
    if p.get("incremental_rate_bopd") is not None:
        ss["d_rate"] = float(min(5000.0, max(1.0, float(p["incremental_rate_bopd"]))))
    if p.get("expected_uplift_decline_per_yr") is not None:
        ss["d_decline"] = float(min(1.95, max(0.05, float(p["expected_uplift_decline_per_yr"]))))


# Each token is applied AT MOST ONCE (a seen-set, not a single last-token): a
# still-selected example must never re-clobber a fresher cross-page preset on the
# next rerun, and vice versa. Picking a different example (new token) reloads.
_seen = ss.setdefault("_diag_tokens_seen", set())
if token != "manual" and token not in _seen:
    _apply_preset(preset)
    _seen.add(token)
    ss["_diag_token"] = token
    if not token.startswith("session-preset"):
        st.caption("Loaded into the form — edit any field freely; your edits persist "
                   "and won't reset on rerun (pick a different example to reload).")

f1, f2, f3 = st.columns(3)
well_id = f1.text_input("Well ID", key="d_well_id",
                        help="Well ids are portable across the suite: an Operations "
                             "Center / Engineering Workbench id (well_001–well_100, "
                             "e.g. well_017 · Reeves 17H), a name like 'Reeves 1H', "
                             "or a Colorado API (05-…) resolves to bundled production "
                             "history in the Well Trend panel below.")
api = f2.text_input("API #", key="d_api")
field = f3.text_input("Field", key="d_field")
f4, f5, f6 = st.columns(3)
operator = f4.text_input("Operator", key="d_operator")
intervention = f5.selectbox("Intervention", interventions, key="d_intervention")
requested_by = f6.text_input("Requested by", key="d_requested_by")
diagnosis_text = st.text_area("Primary diagnosis", height=90, key="d_diagnosis")
g1, g2, g3 = st.columns(3)
rate = g1.number_input("Incremental uplift (BOPD)", 1.0, 5000.0, step=5.0, key="d_rate",
                       help="First-year incremental oil rate the job is expected to "
                            "add. Your number is never auto-overwritten — the caption "
                            "below anchors it against the intervention's type-typical.")
_typ_uplift = common.TYPICAL_UPLIFT_BOPD.get(intervention)
if _typ_uplift is not None:
    g1.caption(f"typical first-year uplift for {intervention.replace('_', ' ')} ≈ "
               f"**{_typ_uplift:.0f} BOPD** (the Pipeline Board ranks with this "
               "figure)")
else:
    g1.caption("no type-typical uplift for this intervention (cost-only job — "
               "the Pipeline Board shows no Net NPV for it)")
decline = g2.number_input("Uplift decline Di (1/yr)", 0.05, 1.95, step=0.05, key="d_decline",
                          help="Nominal annual decline of the uplift stream — the Di "
                               "of the Arps curve below (both models share it).")
wi = g3.number_input("Working interest (WI)", 0.0, 1.0, step=0.05, key="d_wi",
                     help="Operator's share of COST. Revenue share (NRI) and price "
                          "come from the global deck in the sidebar.")
h1, h2 = st.columns([1.4, 1])
uplift_model = h1.radio("Uplift decline model", [UPLIFT_HYP, UPLIFT_EXP],
                        key="d_uplift_model", horizontal=True,
                        help="How the incremental uplift declines over the 5-yr "
                             "horizon. Hyperbolic Arps (default) adds the b-factor "
                             "for the exact curve shape; Exponential (legacy) is "
                             "the component's original qi·e^(−Di·t) model, kept "
                             "for continuity.")
IS_HYP = uplift_model == UPLIFT_HYP
if IS_HYP:
    b_val = h2.number_input("Arps b-factor", 0.05, 1.95, step=0.05, key="d_b",
                            help="Hyperbolic exponent: b→0 is exponential, b=1 "
                                 "harmonic. Higher b = fatter tail = more late-life "
                                 "volume at the same qi/Di.")
else:
    b_val = 0.0
    h2.caption("Legacy exponential: qi·e^(−Di·t) — exactly the original model "
               "(b = 0), for continuity with previously drafted AFEs.")

# ---- well trend + uplift decline shape (CD1 + CD2) ---------------------------
pt.section("Well Trend & Uplift Decline",
           "Sanity-check the economics against the well's ACTUAL production trend "
           "(left) and see the exact decline shape assumed for the uplift (right).")

months60 = core.econ_core.month_index(uplift.DEFAULT_HORIZON_YEARS)      # 1..60
uplift_rates = uplift.uplift_monthly_rates(rate, decline, b_val)         # selected model
alt_b = uplift.DEFAULT_B if not IS_HYP else 0.0
alt_rates = uplift.uplift_monthly_rates(rate, decline, alt_b)            # comparison
alt_name = (f"hyperbolic b={uplift.DEFAULT_B:.1f} (comparison)" if not IS_HYP
            else "exponential (comparison)")

tl, tr = st.columns([1.15, 1])
with tl:
    hit = common.find_well_production(well_id)
    if hit is None:
        pt.empty_state(
            f"No production history found for '{well_id}' in the loaded sources.",
            "Searched: your uploaded monthly CSV (if any), the suite synthetic "
            "fleet (well_001–well_100, or names like 'Reeves 1H'), and the real "
            "Colorado ECMC slice (API ids like 05-123-40438). The demo AFE ids "
            "(ED-001H…) exist in no production source — enter a known well id or "
            "name to see its trend here.")
        # One-click quick-fill: known-resolvable ids so a new PE sees the panel
        # working instead of concluding it's broken. The well id is staged via the
        # sanctioned session-preset handoff (applied BEFORE the widgets render on
        # the next run) — NEVER a direct write to the widget-owned d_well_id key.
        qf1, qf2 = st.columns([2, 1])
        _qf_pick = qf1.selectbox(
            "Show a producing well instead", ["well_017", "well_001", "05-123-40438"],
            format_func=common.well_label, key="d_trend_quickfill",
            help="well_0NN = suite synthetic fleet (shared with Operations Center / "
                 "Engineering Workbench); 05-… = real Colorado ECMC. Only the well "
                 "id changes — every other form field keeps your edits.")
        qf2.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
        if qf2.button("Use this well", key="d_trend_quickfill_go"):
            common.set_diag_preset({"well_id": _qf_pick})
            st.rerun()
    else:
        csv_w, src_w, wid = hit
        fit = None
        try:
            t_hist, q_hist, fit, fc_rates = common.fit_one_well(
                csv_w, wid, pdp.DEFAULT_ECON_LIMIT_BOPD)
        except ValueError:
            g_w = common.pdp_tidy(csv_w)
            g_w = g_w[g_w["well_id"] == wid]
            t_hist, q_hist = pdp.well_history(g_w)
        trend = go.Figure()
        trend.add_trace(go.Scatter(
            x=t_hist, y=q_hist, mode="markers", name="history",
            marker=dict(color=theme.BLUE, size=5),
            hovertemplate="month %{x:.0f}: %{y:.1f} bopd<extra>history</extra>"))
        n_fc = len(months60)
        base_pad = np.zeros(n_fc)
        if fit is not None:
            base = np.asarray(fc_rates[:n_fc], dtype=float)
            base_pad[:len(base)] = base
            t_anchor = fit.t_last_months
            t_base = t_anchor + np.arange(1, len(base) + 1) - 0.5
            trend.add_trace(go.Scatter(
                x=t_base, y=base, mode="lines", name="base forecast (fitted)",
                line=dict(color=theme.GREY, dash="dash")))
            base_lbl = f"{fit.model} fit"
        else:
            trailing = float(np.mean(q_hist[-6:])) if len(q_hist) else 0.0
            t_anchor = float(t_hist[-1]) if len(t_hist) else 0.0
            base_pad[:] = trailing
            t_base = t_anchor + months60 - 0.5
            trend.add_trace(go.Scatter(
                x=t_base, y=base_pad, mode="lines",
                name="base (trailing 6-mo mean — too little history to fit)",
                line=dict(color=theme.GREY, dash="dash")))
            base_lbl = "trailing 6-month mean (< 6 fit points)"
        t_comb = t_anchor + months60 - 0.5
        trend.add_trace(go.Scatter(
            x=t_comb, y=base_pad + np.asarray(uplift_rates, dtype=float),
            mode="lines", name="base + AFE uplift (assumed)",
            line=dict(color=theme.GREEN)))
        trend.add_vline(x=t_anchor, line_dash="dash", line_color=theme.GREY,
                        annotation_text="job assumed here")
        trend.update_layout(xaxis_title="months since first production",
                            yaxis_title="oil rate (bopd)")
        st.plotly_chart(theme.style_fig(trend, height=320), width="stretch")
        theme.source_note(
            f"{common.well_label(wid)} — {src_w}. Baseline: {base_lbl} at PDP defaults (3-bopd limit, "
            "6%/yr Dmin — not the Screen page sliders). The green case adds the "
            "AFE's ASSUMED uplift on top of the baseline — a sanity-check overlay, "
            "not a fitted forecast of the job.")
with tr:
    shape = go.Figure()
    shape.add_trace(go.Scatter(
        x=months60, y=uplift_rates, mode="lines",
        name=(f"hyperbolic b={b_val:.2f}" if IS_HYP else "exponential (selected)"),
        line=dict(color=theme.GREEN),
        hovertemplate="month %{x}: %{y:.1f} bopd<extra></extra>"))
    shape.add_trace(go.Scatter(
        x=months60, y=alt_rates, mode="lines", name=alt_name,
        line=dict(color=theme.GREY, dash="dot")))
    shape.update_layout(xaxis_title="months after job",
                        yaxis_title="incremental rate (bopd)")
    st.plotly_chart(theme.style_fig(shape, height=320), width="stretch")
    vols = np.asarray(uplift_rates, dtype=float) * core.econ_core.DAYS_PER_MONTH
    theme.source_note(
        f"The exact uplift decline the economics integrate: Arps "
        f"qi/(1+b·Di·t)^(1/b) at qi={rate:.0f} bopd, Di={decline:.2f}/yr"
        + (f", b={b_val:.2f}" if IS_HYP else " (b=0, exponential)")
        + f" → first-year add {float(vols[:12].sum()):,.0f} bbl, 5-yr uplift EUR "
          f"{float(vols.sum()):,.0f} bbl (gross).")

# ---- cost rollup (CD3 — editable line items) --------------------------------
pt.section("Cost Rollup — Edit the Line Items",
           "This is where AFE costs are edited: add, remove, or reprice any line "
           "(double-click a cell; '+' adds a row). Contingency, the tangible/IDC "
           "split, authority routing, and every economics number below react live.")

# Reseed the contingency % when the intervention changes (same token pattern as
# the diagnosis preset), so each template starts at its benchmark 10%/15%.
if ss.get("_cost_token") != intervention:
    ss["d_conting_pct"] = afe_costs.default_contingency_pct(intervention) * 100.0
    ss["_cost_token"] = intervention

seed_df = afe_costs.seed_lines(intervention)
e1, e2 = st.columns([3, 1])
with e1:
    # keyed per intervention: switching templates re-seeds the editor; switching
    # back restores that template's session edits.
    edited_df = st.data_editor(
        seed_df, num_rows="dynamic", key=f"d_cost_editor::{intervention}",
        width="stretch", hide_index=True,
        column_config={
            "category": st.column_config.TextColumn("Category", required=True),
            "description": st.column_config.TextColumn("Description"),
            "qty": st.column_config.NumberColumn("Qty", min_value=0.0),
            "unit": st.column_config.TextColumn("Unit"),
            "unit_cost_usd": st.column_config.NumberColumn(
                "Unit Cost $", min_value=0.0, format="$%,.0f"),
            "tangible": st.column_config.CheckboxColumn(
                "Tangible", help="Capitalized equipment (depreciated) vs. "
                                 "intangible workover cost (IDC, expensed)."),
            "vendor": st.column_config.TextColumn("Vendor"),
        })
with e2:
    conting_pct = st.number_input(
        "Contingency (% of direct)", 0.0, 50.0, step=1.0, key="d_conting_pct",
        help="Computed on the edited direct cost — reseeds to the benchmark "
             "(10% / 15%) when the intervention changes.")
    st.caption("Edits are **session-only** (nothing is stored server-side); "
               "switching the intervention re-seeds its benchmark template.")

rollup = afe_costs.rollup_from_lines(edited_df, float(conting_pct) / 100.0)
pt.kpi_row([
    {"label": "AFE Total (Gross)", "value": f"${rollup['total']:,.0f}",
     "help": "Edited direct lines + contingency — feeds the economics, the "
             "Monte-Carlo, and the pipeline submission below."},
    {"label": "Tangible (Capitalized)", "value": f"${rollup['tangible']:,.0f}"},
    {"label": "Intangible (IDC)", "value": f"${rollup['intangible']:,.0f}"},
    {"label": "Routes To", "value": core.afe_tracker.required_approver(rollup["total"]),
     "help": "Delegation-of-authority routing recomputed from the EDITED total — "
             "repricing a line can change who must sign."},
])

cats = list(rollup["by_category"].items())
wf = go.Figure(go.Waterfall(
    orientation="v",
    measure=["relative"] * (len(cats) + 1) + ["total"],
    x=[c for c, _ in cats] + ["Contingency", "Total AFE"],
    y=[v for _, v in cats] + [rollup["contingency"], 0],
    text=[f"${v:,.0f}" for _, v in cats]
         + [f"${rollup['contingency']:,.0f}", f"${rollup['total']:,.0f}"],
    textposition="outside",
    connector={"line": {"color": theme.GRID}},
    increasing={"marker": {"color": theme.BLUE}},
    decreasing={"marker": {"color": theme.RED}},
    totals={"marker": {"color": theme.NAVY}},
    hovertemplate="%{x}: $%{y:,.0f}<extra></extra>"))
wf.update_layout(yaxis_title="USD")
st.plotly_chart(theme.style_fig(wf, height=340, legend=False), width="stretch")
theme.source_note("Bars in USD from the EDITED line items above (grouped by "
                  "category) → contingency → total AFE. Seeded from the benchmark "
                  "template for the selected intervention.")

# ---- net economics at the deck -----------------------------------------------
SEV = float(ss.get("severance_pct", 7.5)) / 100.0     # deck severance (shared with Screen)


def _net_npv_after_severance(net_npv: float, net_cost: float) -> float:
    """Apply the deck severance to an AFE net NPV on the **gross-wellhead** base (the
    statutory base the PDP screen uses), so the two engines value a barrel identically."""
    return common.net_npv_gross_wellhead_severance(net_npv, net_cost, OIL, SEV)


_model_desc = (f"Arps hyperbolic (b={b_val:.2f})" if IS_HYP else "exponential (legacy)")
pt.section("Net Economics",
           f"WI {wi:.0%} of cost · NRI {NRI:.0%} of revenue · ${OIL:.0f}/bbl − "
           f"$12/bbl LOE · {SEV:.1%} severance · {DISC:.1%} effective-annual discount "
           f"· uplift model: {_model_desc}, 5-yr horizon.")
st.caption(f"Cost basis: the **editable line items above** — AFE total "
           f"${rollup['total']:,.0f}.")
if intervention == "p_and_a":
    pt.empty_state("P&A is a cost-only job — production economics do not apply.",
                   "Justified against remaining liability, plugging-bond release, "
                   "and avoided idle-well carrying cost.")
    econ = None
else:
    if IS_HYP:
        econ = uplift.uplift_economics(
            rollup["total"], rate, uplift_decline_per_yr=decline, b=b_val,
            realized_price_per_bbl=OIL, working_interest=wi,
            net_revenue_interest=NRI, discount_rate=DISC)
    else:
        econ = core.draft_economics(rollup["total"], rate, uplift_decline_per_yr=decline,
                                    realized_price_per_bbl=OIL, working_interest=wi,
                                    net_revenue_interest=NRI, discount_rate=DISC)
    net_npv_sev = _net_npv_after_severance(econ.net_npv_10pct_usd,
                                           econ.net_cost_to_operator_usd)
    pt.kpi_row([
        {"label": "Gross NPV", "value": f"${econ.npv_10pct_usd/1e6:,.2f}MM"},
        {"label": "Net NPV to Operator", "value": f"${net_npv_sev/1e6:,.2f}MM",
         "help": f"WI% of cost, NRI% of revenue, less {SEV:.1%} severance — what the "
                 "operator books. Same tax basis the PDP screen applies."},
        {"label": "Payout", "value": ("—" if econ.payout_months == float("inf")
                                      else f"{econ.payout_months:.0f} mo")},
        {"label": "First-Year Add (gross)", "value": f"{econ.incremental_first_year_bbl:,.0f} bbl",
         "help": "Gross incremental oil — not reduced by NRI."},
    ])
    if IS_HYP:
        deck_rows = uplift.price_sensitivity(
            rollup["total"], rate, uplift_decline_per_yr=decline, b=b_val,
            working_interest=wi, net_revenue_interest=NRI, discount_rate=DISC)
    else:
        deck_rows = core.afe_economics.price_sensitivity(
            rollup["total"], rate, uplift_decline_per_yr=decline,
            working_interest=wi, net_revenue_interest=NRI, discount_rate=DISC)
    deck_df = pd.DataFrame(deck_rows)
    net_cost = econ.net_cost_to_operator_usd
    deck_df = pd.DataFrame({
        "Realized $/bbl": deck_df["realized_price"].map(lambda v: f"${v:,.0f}"),
        "Gross NPV": deck_df["npv_usd"].map(lambda v: f"${v/1e6:,.2f}MM"),
        "Net NPV (after sev.)": deck_df["net_npv_usd"].map(
            lambda v: f"${_net_npv_after_severance(v, net_cost)/1e6:,.2f}MM"),
        "Payout (mo)": deck_df["payout_months"].map(
            lambda v: f"{v:.0f}" if v != float("inf") else "—")})
    st.dataframe(deck_df, width="stretch", hide_index=True)
    theme.source_note(f"Price-deck sensitivity: NPV at a fixed uplift ({_model_desc}) "
                      f"across a realized-price strip; WI/NRI, {SEV:.1%} severance, "
                      "and discount held at the deck.")

# ---- Monte-Carlo --------------------------------------------------------------
pt.section("Probabilistic Economics — Gross NPV",
           "10,000 trials over uplift (±30%), decline (±0.15 abs), and price (~$12 sd) "
           f"around the {_model_desc} uplift stream. These are GROSS NPV (before "
           "WI/NRI), so they bracket the Gross NPV above — not the Net-to-Operator "
           "figure.")
if intervention == "p_and_a":
    st.caption("Not applicable to a cost-only job.")
else:
    # Results PERSIST across widget touches (same idiom as the _afe_snapshot on
    # the AFE document below): the run + an input snapshot live in session state,
    # render whenever present, and a staleness warning fires when the current
    # inputs no longer match the run — a PE who tweaks price after running keeps
    # the P10/P50/P90 they were quoting, clearly flagged as pre-tweak.
    _mc_inputs_now = {"afe_total": float(rollup["total"]), "rate": float(rate),
                      "decline": float(decline), "b": float(b_val),
                      "model": uplift_model, "oil": OIL, "disc": DISC}
    if st.button("Run Monte-Carlo NPV", key="d_run_mc",
                 help="10,000 seeded trials — deterministic for the same inputs. "
                      "Results stay on screen until you re-run; editing any "
                      "driving input flags them as stale."):
        if IS_HYP:
            mc_run = uplift.simulate_uplift_economics(
                treatment_cost_usd=rollup["total"], incremental_rate_bopd=rate,
                uplift_decline_per_yr=decline, b=b_val,
                realized_price_per_bbl=OIL, discount_rate=DISC)
        else:
            mc_run = core.afe_economics.simulate_economics(
                treatment_cost_usd=rollup["total"], incremental_rate_bopd=rate,
                uplift_decline_per_yr=decline, realized_price_per_bbl=OIL,
                discount_rate=DISC)
        ss["_afe_mc"] = mc_run
        ss["_afe_mc_inputs"] = dict(_mc_inputs_now)

mc = None if intervention == "p_and_a" else ss.get("_afe_mc")
if mc is not None:
    if ss.get("_afe_mc_inputs") != _mc_inputs_now:
        st.warning("Inputs changed since this Monte-Carlo ran (cost lines, uplift, "
                   "decline model, or deck) — the P10/P50/P90 below reflect the "
                   "**previous** inputs. Click **Run Monte-Carlo NPV** to refresh.")
    # SPE exceedance labels (suite convention): P90 = downside low case (the
    # engine's 10th-percentile field), P10 = upside high case (90th percentile).
    # Display-level relabel only — the vendored/product MC math is untouched.
    pt.kpi_row([
        {"label": "P90 Gross NPV (Downside)", "value": f"${mc.npv_p10_usd/1e6:,.2f}MM",
         "help": "SPE exceedance convention: P90 = the low case, exceeded in 90% "
                 "of trials (the distribution's 10th percentile)."},
        {"label": "P50 Gross NPV (Median)", "value": f"${mc.npv_p50_usd/1e6:,.2f}MM"},
        {"label": "P10 Gross NPV (Upside)", "value": f"${mc.npv_p90_usd/1e6:,.2f}MM",
         "help": "SPE exceedance convention: P10 = the high case, exceeded in only "
                 "10% of trials (the distribution's 90th percentile)."},
        {"label": "P(Payout < 24 mo)", "value": f"{mc.probability_of_payout*100:.0f}%"},
    ])
    _mc_snap = ss.get("_afe_mc_inputs") or {}
    if _mc_snap.get("model", uplift_model) == UPLIFT_HYP:
        _mc_b = float(_mc_snap.get("b", b_val))
        st.caption(f"Trials sample uplift rate, Di, and price around the Arps "
                   f"stream with **b = {_mc_b:.2f} held fixed** (b itself is not "
                   "sampled — it is a model choice, not a measured uncertainty).")
    items_t = sorted(mc.tornado.items(), key=lambda kv: kv[1]["swing"])
    labels = [k.replace("_", " ") for k, _ in items_t]
    lows = [v["low"] for _, v in items_t]
    highs = [v["high"] for _, v in items_t]
    base = mc.base_npv_usd
    tor = go.Figure()
    tor.add_trace(go.Bar(y=labels, x=[base - lo for lo in lows], base=lows,
                         orientation="h", name="downside", marker_color=theme.RED,
                         hovertemplate="low NPV: $%{base:,.0f}<extra></extra>"))
    tor.add_trace(go.Bar(y=labels, x=[hi - base for hi in highs], base=base,
                         orientation="h", name="upside", marker_color=theme.BLUE,
                         hovertemplate="high NPV: $%{x:,.0f}<extra></extra>"))
    tor.add_vline(x=base, line_dash="dash", line_color=theme.NAVY,
                  annotation_text=f"base ${base/1e6:,.2f}MM")
    tor.update_layout(barmode="overlay", xaxis_title="NPV (USD)")
    st.plotly_chart(theme.style_fig(tor, height=300), width="stretch")
    theme.source_note("Tornado: NPV (USD) swing as each variable moves over its "
                      "sampled range; dashed line is the base case.")

# ---- AFE document --------------------------------------------------------------
pt.section("AFE Document",
           "Deterministic markdown + Word export — keyless. Add a key in the "
           "sidebar for the LLM-written narrative.")
diag_dict = {
    "well_id": well_id, "api_number": api, "field": field, "operator": operator,
    "intervention": intervention, "primary_diagnosis": diagnosis_text,
    "incremental_rate_bopd": float(rate),
    "expected_uplift_decline_per_yr": float(decline),
    "requested_by": requested_by,
}
# On-page assumptions the document schema doesn't carry (the vendored AFEDiagnosis
# has no b / edited-cost fields) — snapshotted so the staleness warning fires when
# they change after generation, and appended to the markdown as an addendum.
extras_now = {"uplift_model": uplift_model, "b": float(b_val),
              "afe_total": float(rollup["total"])}
if st.button("Generate AFE", type="primary"):
    problems = core.afe_models.AFEDiagnosis(**diag_dict).validate()
    if problems:
        st.error("Fix the diagnosis first: " + " · ".join(problems))
    else:
        byok = (ss.get("anthropic_key") or "").strip()
        markdown = None
        if byok:
            try:
                with st.spinner("Drafting the LLM narrative (your key)…"):
                    markdown = core.afe_drafter.run_drafter(
                        core.afe_models.AFEDiagnosis(**diag_dict), api_key=byok)
            except Exception as exc:  # noqa: BLE001 — bad key/limits → deterministic path
                st.warning("LLM narrative unavailable "
                           f"({type(exc).__name__}) — rendering the deterministic AFE.")
        if markdown is None:
            markdown = core.afe_markdown(diag_dict, working_interest=wi,
                                         net_revenue_interest=NRI, realized_price=OIL)
        # Product-layer addendum: the vendored document body prices the BENCHMARK
        # template with the EXPONENTIAL model (its schema has no b / edited costs),
        # so the on-page assumptions are disclosed rather than silently divergent.
        addendum = ["", "---",
                    "*Capital Desk addendum — on-page assumptions at generation:*",
                    ("*Uplift decline model: hyperbolic Arps "
                     f"(Di = {decline:.2f}/yr, b = {b_val:.2f}) — note the document "
                     "body's economics above use the component's exponential model.*"
                     if IS_HYP else
                     f"*Uplift decline model: exponential (Di = {decline:.2f}/yr).*")]
        template_total = core.afe_cost_db.cost_rollup(intervention)["total"]
        if abs(rollup["total"] - template_total) > 0.5:
            addendum.append(
                f"*AFE total per the edited line items: ${rollup['total']:,.0f} "
                "(the cost table above is the unedited benchmark template).*")
        ss["_afe_markdown"] = markdown + "\n" + "\n".join(addendum)
        # Snapshot the EXACT inputs the markdown was generated from, so the preview,
        # the .docx cover, the filename, and submit-to-pipeline all describe ONE AFE
        # even if the form is edited afterwards (the preview must never silently
        # disagree with the file you download or the pipeline row you create).
        ss["_afe_snapshot"] = dict(diag_dict)
        ss["_afe_extras"] = dict(extras_now)
        ss["_afe_pending"] = {"well_id": well_id, "intervention": intervention,
                              "total_cost_usd": rollup["total"],
                              "requested_by": requested_by}
        ss.pop("_afe_submitted", None)   # a fresh document supersedes the old toast

if ss.get("_afe_markdown"):
    snap = ss.get("_afe_snapshot") or diag_dict
    snap_extras = ss.get("_afe_extras") or extras_now
    if snap != diag_dict or snap_extras != extras_now:
        st.warning("Inputs changed since this AFE was generated (form, cost lines, "
                   "or decline model) — the preview and downloads below reflect the "
                   "**generated** version. Click **Generate AFE** again to refresh "
                   "them to the current form.")
    snap_well = snap.get("well_id", well_id)
    snap_int = snap.get("intervention", intervention)
    with st.expander("AFE Preview", expanded=True):
        st.markdown(ss["_afe_markdown"])
    d1, d2, d3 = st.columns(3)
    d1.download_button("Download AFE (Markdown)", ss["_afe_markdown"],
                       file_name=f"AFE_{snap_well}_{snap_int}.md")
    try:
        with tempfile.TemporaryDirectory() as td:
            p = core.afe_docx_builder.build_docx(
                ss["_afe_markdown"], Path(td) / "afe.docx",
                core.afe_models.AFEDiagnosis(**snap))
            docx_bytes = p.read_bytes()
        d2.download_button(
            "Download AFE (Word .docx)", docx_bytes,
            file_name=f"AFE_{snap_well}_{snap_int}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    except Exception as exc:  # noqa: BLE001 — docx must never block the markdown
        d2.caption(f"docx unavailable: {type(exc).__name__}")
    pending = ss.get("_afe_pending") or {}
    if d3.button("Submit to Pipeline"):
        tracker = core.get_tracker()
        existing = core.pipeline_df()
        next_num = max((int(str(n).split("-")[-1]) for n in existing.get("afe_number", [])
                        if str(n).startswith("AFE-")), default=53) + 1
        afe_no = f"AFE-{_dt.date.today().year}-{next_num:04d}"
        today = _dt.date.today().isoformat()
        tracker.upsert(core.afe_tracker.AFERecord(
            afe_number=afe_no, well_id=pending.get("well_id", well_id),
            intervention=pending.get("intervention", intervention),
            total_cost_usd=float(pending.get("total_cost_usd", rollup["total"])),
            status="draft", created_date=today, last_updated=today,
            requested_by=pending.get("requested_by", requested_by),
            notes="Submitted via Draft AFE"))
        ss["_afe_cache_token"] = ss.get("_afe_cache_token", 0) + 1
        ss["_afe_submitted"] = afe_no
    if ss.get("_afe_submitted"):
        st.success(f"{ss['_afe_submitted']} added to the pipeline as draft.")
        common.next_step(
            "views/authorize_pipeline.py",
            "→ Track and advance it on the board (Pipeline Board)",
            help="The submitted AFE lands in draft status — the AFE Detail panel "
                 "shows its journey stepper, required approver, and what's "
                 "remaining to get it approved.")

theme.references(["arps", "npv", "monte_carlo"])
