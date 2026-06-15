"""PDP Screener — the A&D quick-look on producing wells (NEW in Capital Desk).

Per-well Arps fit (exponential AND hyperbolic; lower SSE wins) on monthly oil,
forecast FORWARD FROM THE LAST HISTORY MONTH to the economic limit, remaining
EUR, and PV10 under the suite's effective-annual discounting (afe.econ_core).
Default data is REAL: 28 Colorado ECMC DJ Basin horizontals. Bring a monthly CSV
to screen your own deal.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import product_theme as pt
import theme
from src import pdp
from views import common

OIL, NRI, DISC, DECK = common.deck()
ss = st.session_state

pt.masthead("capital", "PDP Screener",
            "Decline-fit, remaining EUR, and PV10 per well — the deal quick-look.")

# ---- source + assumptions -----------------------------------------------------
# Default = the suite-shared 100-well synthetic fleet (same well identities as
# Operations Center + Engineering Workbench), with the REAL Colorado ECMC slice and
# a BYOD upload as the other two options.
src_options = [common.PDP_SYNTH_LABEL, common.PDP_REAL_LABEL, common.PDP_BYOD_LABEL]
c_src, c_ask = st.columns([2, 1])
with c_src:
    source_choice = st.radio("Production source", src_options, horizontal=True,
                             help="The default is the suite's shared 100-well "
                                  "synthetic Permian fleet (same wells the other "
                                  "operator products use). The Colorado slice is "
                                  "genuine public-record ECMC data. Or upload your "
                                  "own monthly CSV here or on the Data page.")
with c_ask:
    asking_mm = st.number_input("Asking price ($MM, 0 = none)", 0.0, 5000.0, 0.0, 5.0,
                                help="The seller's number — compared against PV10. "
                                     "0 = no asking price (screen value only).")

if source_choice == common.PDP_BYOD_LABEL and not ss.get("pdp_csv_text"):
    st.info("No uploaded CSV yet — add one below (or on the Data page). "
            "Showing the synthetic fleet meanwhile.")
with st.expander("Bring your own monthly production (CSV)"):
    st.caption("Required columns: `well_id`, `month` (YYYY-MM), `oil_bbl`; "
               "optional `days` (producing days — improves the rate basis). "
               "Nothing is stored server-side.")
    st.download_button("Download template CSV", data=pdp.template_csv(),
                       file_name="pdp_monthly_template.csv", mime="text/csv")
    up = st.file_uploader("Monthly production CSV", type=["csv"], key="pdp_upload_page")
    if up is not None:
        text = up.getvalue().decode("utf-8", errors="replace")
        try:
            pdp.load_pdp_csv(io.StringIO(text))
        except ValueError as exc:
            st.error(f"Could not load production CSV: {exc}")
            st.stop()
        ss["pdp_csv_text"] = text
        st.success(f"Loaded {up.name} — select '{common.PDP_BYOD_LABEL}' above.")

csv_text, source_label, is_byod = common.resolve_pdp(source_choice)
pt.context_bar([("Deck", DECK), ("Data", source_label),
                ("Convention", "Forecast forward from last history month")])
if source_label == common.PDP_SYNTH_LABEL:
    theme.data_badge(
        "synthetic",
        "Suite-shared 100-well synthetic Permian fleet (same well identities as "
        "Operations Center + Engineering Workbench), rendered as monthly oil — "
        "future deals / private production aren't public data. Switch to the "
        "Colorado ECMC slice above for genuine public-record production.")
elif is_byod:
    theme.data_badge("real", "User-uploaded monthly production — parsed in memory only.")
else:
    theme.data_badge(
        "real",
        "Colorado ECMC (formerly COGCC) public records — DJ Basin horizontals, Weld County.")

SEV = common.severance_frac()      # from the global deck — same tax the AFE charges
a1, a2, a3, a4, a5 = st.columns(5)
loe = a1.slider("LOE ($/bbl)", 4.0, 30.0, 12.0, 0.5,
                help="Lease operating expense per barrel of oil.")
gas_price = a2.slider("Gas price ($/mcf)", 0.0, 8.0, 3.00, 0.25,
                      help="Realized gas price. Gas rides each well's producing GOR "
                           "off the oil decline; set 0 to value oil only.")
gas_opex = a3.slider("Gas gathering ($/mcf)", 0.0, 2.0, 0.50, 0.05,
                     help="Gathering / compression / processing cost deducted from "
                          "gas revenue, so gas PV isn't an un-costed upper bound.")
econ_limit = a4.slider("Economic limit (bopd)", 1.0, 10.0,
                       pdp.DEFAULT_ECON_LIMIT_BOPD, 0.5,
                       help="Forecast stops at this rate or 360 forecast months, "
                            "whichever comes first.")
dmin_pct = a5.slider("Terminal decline (%/yr)", 0.0, 15.0,
                     pdp.DEFAULT_DMIN_ANNUAL * 100.0, 1.0,
                     help="Modified-hyperbolic Dmin: the forecast switches from "
                          "hyperbolic to exponential once its decline reaches this, "
                          "so high-b wells don't over-forecast EUR. Only binds on wells "
                          "whose initial decline exceeds it. 0 = pure Arps.")
dmin = dmin_pct / 100.0
st.caption(f"Severance + ad valorem of **{SEV:.1%}** comes from the global deck "
           "(sidebar) — the same drag the AFE net economics apply. Forecast uses a "
           f"**{dmin_pct:.0f}%/yr terminal decline** (Dmin).")

table, skipped = common.screen_table(csv_text, OIL, loe, NRI, SEV, DISC, econ_limit,
                                     gas_price=gas_price, dmin=dmin, gas_opex=gas_opex)

if table.empty:
    pt.empty_state("No wells could be fit from this file.",
                   "Each well needs at least 6 positive monthly rates.")
    st.stop()

roll = pdp.deal_rollup(table, asking_mm * 1e6 if asking_mm > 0 else None)
has_gas = roll.get("total_pv10_gas_usd", 0.0) > 0
gas_share = (roll["total_pv10_gas_usd"] / roll["total_pv10_usd"] * 100.0
             if has_gas and roll["total_pv10_usd"] else 0.0)

pt.kpi_row([
    {"label": "Deal PV10 (oil+gas)" if has_gas else "Deal PV10 (oil only)",
     "value": f"${roll['total_pv10_usd']/1e6:,.1f}MM",
     "delta": (f"{gas_share:.0f}% from gas" if has_gas else None), "delta_color": "off",
     "help": "Sum of per-well PV of forward net revenue at the deck discount. Gas is "
             "valued at the gas price via each well's GOR; set gas price 0 for oil-only."},
    {"label": "Remaining EUR (oil)", "value": f"{roll['total_eur_bbl']/1e3:,.0f} Mbbl"},
    {"label": "Current Rate", "value": f"{roll['total_current_boepd']:,.0f} boepd",
     "help": f"{roll['total_current_bopd']:,.0f} bopd oil + gas/6 (energy-equivalent)."},
    {"label": "Wells Fit", "value": f"{roll['n_wells']}"
        + (f" ({len(skipped)} skipped)" if skipped else "")},
])

# Low-confidence-fit guard: a noisy well with a weak decline fit can still post a
# large PV10. Flag it so it is never silently trusted — the synthetic fleet has a
# deliberate messy tail, and real / BYOD data is where this bites hardest.
lowfit = table[table["r_squared"] < 0.5]
if len(lowfit):
    tot = table["pv10_usd"].sum()
    share = (lowfit["pv10_usd"].sum() / tot * 100.0) if tot else 0.0
    names = ", ".join(lowfit["well_id"].head(6))
    st.warning(
        f"⚠️ {len(lowfit)} well(s) have a weak decline fit (R² < 0.5) yet carry "
        f"{share:.0f}% of PV10 — treat their value as low-confidence: {names}"
        + (" …" if len(lowfit) > 6 else "") + ". See the R² column below.")

if asking_mm > 0:
    prem = roll["pv10_minus_asking_usd"]
    ratio = roll["pv10_over_asking"]
    verdict = (pt.pill(f"PV10 covers asking — {ratio:,.2f}x ({prem/1e6:+,.1f}MM)", "ok")
               if prem >= 0 else
               pt.pill(f"PV10 below asking — {ratio:,.2f}x ({prem/1e6:+,.1f}MM)", "bad"))
    st.markdown(
        f"**Asking ${asking_mm:,.0f}MM** → "
        f"**${roll['usd_per_flowing_bbl']:,.0f}/flowing bbl** · "
        f"**${roll['usd_per_flowing_boe']:,.0f}/flowing boe** · {verdict}",
        unsafe_allow_html=True)
    st.caption("Quick-look only: PV10 values producing oil + gas at the deck; it "
               "ignores upside (PUDs, behind-pipe), G&A, and plugging liability. "
               "$/flowing boe divides asking by oil+gas/6, the fairer metric on "
               "gas-rich wells. It answers 'is the producing base alone close to "
               "the number'.")

    # --- A&D benchmarking: where this deal sits vs typical PDP metrics ----------
    pt.section("Deal Benchmarks", "Where the asking sits against typical PDP A&D ranges.")
    LO_BOE, HI_BOE = 25_000.0, 50_000.0       # typical $/flowing-boe band for PDP packages
    upb = roll["usd_per_flowing_boe"]
    pv10_mult = roll["pv10_over_asking"]
    boe_pill = (pt.pill("below band — cheap", "ok") if upb < LO_BOE
                else pt.pill("above band — rich", "bad") if upb > HI_BOE
                else pt.pill("in typical band", "info"))
    mult_pill = (pt.pill("PV10 ≥ asking", "ok") if pv10_mult >= 1.0
                 else pt.pill("PV10 < asking", "bad"))
    bcols = st.columns(3)
    bcols[0].metric("$/flowing BOE", f"${upb:,.0f}",
                    help=f"Typical PDP band ≈ ${LO_BOE:,.0f}–${HI_BOE:,.0f}/flowing boe.")
    bcols[1].metric("PV10 / Asking", f"{pv10_mult:,.2f}x")
    bcols[2].metric("PV10 / flowing BOE",
                    f"${roll['total_pv10_usd']/roll['total_current_boepd']:,.0f}"
                    if roll['total_current_boepd'] else "—")
    st.markdown(f"vs the ${LO_BOE/1e3:,.0f}–${HI_BOE/1e3:,.0f}k/flowing-boe PDP band: "
                f"{boe_pill} · {mult_pill}", unsafe_allow_html=True)
    theme.source_note(
        "Benchmark band is a rule-of-thumb PDP range, not a fitted comp set — a "
        "directional gut-check, not an appraisal. $/flowing boe = asking ÷ (oil + gas/6).")

# table is already PV10-descending; cap the bar chart to the top wells so 100-well
# fleets stay readable (the full ranking lives in the table + CSV below).
TOP_N = 25
ranked = table.reset_index(drop=True)
shown = ranked.head(TOP_N)
top_share = (shown["pv10_usd"].sum() / ranked["pv10_usd"].sum() * 100.0
             if ranked["pv10_usd"].sum() > 0 else 0.0)
cap_txt = (f"Top {len(shown)} of {len(ranked)} wells" if len(ranked) > TOP_N
           else "All wells, ranked")
pt.section("PV10 by Well", f"{cap_txt} — where the deal's value concentrates.")
# Highlight the single highest-value well so the #1 is unmistakable.
colors = [theme.GREEN if i == 0 else theme.BLUE for i in range(len(shown))]
bar = go.Figure(go.Bar(
    x=shown["well_id"], y=shown["pv10_usd"] / 1e6,
    marker_color=colors,
    hovertemplate="%{x}: $%{y:.2f}MM<extra></extra>"))
bar.update_layout(xaxis_title="well (ranked by PV10)", yaxis_title="PV10 ($MM)",
                  xaxis=dict(tickangle=-45, tickfont=dict(size=9)))
st.plotly_chart(theme.style_fig(bar, height=320, legend=False), width="stretch")
if len(ranked):
    top = ranked.iloc[0]
    st.caption(
        f"Highest-value well: **{top['well_id']}** at "
        f"**${top['pv10_usd']/1e6:,.1f}MM** PV10"
        + (f" · the top {len(shown)} wells hold {top_share:.0f}% of total PV10."
           if len(ranked) > TOP_N else "."))
theme.source_note(
    "PV10 ($MM) per well: Arps forecast from the last history month to the "
    f"{econ_limit:.0f}-bopd economic limit; net revenue = [oil x (price − LOE) + "
    "gas x gas-price] x NRI x (1 − severance), gas riding the oil decline at the "
    "well's GOR, discounted effective-annually at the deck. Green = highest-value well.")

pt.section("Per-Well Screen", "Fit parameters and value, one row per well.")
# Name lookup so the table isn't an opaque list of API numbers: prefer a well_name
# carried in the data (Colorado / synthetic), else the shared registry.
tidy_names = common.pdp_tidy(csv_text)
if "well_name" in tidy_names.columns:
    name_map = tidy_names.groupby("well_id")["well_name"].first().to_dict()
else:
    import fleet_registry
    name_map = {w: fleet_registry.get(w).name for w in table["well_id"]}
disp = table.copy()
disp.insert(1, "name", disp["well_id"].map(name_map).fillna(""))
cols = ["well_id", "name", "model", "qi_bopd", "di_annual", "b", "r_squared",
        "n_months", "current_bopd", "current_boepd", "gor_mcf_bbl",
        "remaining_eur_bbl", "pv10_oil_usd", "pv10_gas_usd", "pv10_usd"]
disp = disp[[c for c in cols if c in disp.columns]].rename(columns={
    "well_id": "Well", "name": "Name", "model": "Model", "qi_bopd": "qi (bopd)",
    "di_annual": "Di (1/yr)", "b": "b", "r_squared": "R²", "n_months": "Months",
    "current_bopd": "Current (bopd)", "current_boepd": "Current (boepd)",
    "gor_mcf_bbl": "GOR (mcf/bbl)", "remaining_eur_bbl": "Remaining EUR (bbl)",
    "pv10_oil_usd": "PV10 oil $", "pv10_gas_usd": "PV10 gas $", "pv10_usd": "PV10 total $"})
st.dataframe(disp, width="stretch", hide_index=True,
             column_config={
                 "PV10 oil $": st.column_config.NumberColumn(format="$%,.0f"),
                 "PV10 gas $": st.column_config.NumberColumn(format="$%,.0f"),
                 "PV10 total $": st.column_config.NumberColumn(format="$%,.0f"),
                 "Remaining EUR (bbl)": st.column_config.NumberColumn(format="%,.0f"),
             })
st.download_button("Download per-well screen (CSV)", data=table.to_csv(index=False),
                   file_name="pdp_screen.csv", mime="text/csv")
if skipped:
    with st.expander(f"Skipped wells ({len(skipped)})"):
        for wid, reason in skipped:
            st.caption(f"{wid}: {reason}")

# ---- per-well drill-down ---------------------------------------------------------
pt.section("Well Drill-Down", "History, fit, and the forward forecast.")
well_ids = list(table["well_id"])
if ss.get("well_id") not in well_ids:
    ss["well_id"] = well_ids[0]
st.selectbox("Well", well_ids, key="well_id")

tidy = common.pdp_tidy(csv_text)
g = tidy[tidy["well_id"] == ss["well_id"]]

# Identity line: use whatever metadata the source carries (Colorado rows carry
# well_name/operator/field/formation), and enrich the suite-shared synthetic ids
# (well_0NN) from the shared fleet registry so the same well reads coherently
# across all three products.
_row0 = g.iloc[0] if len(g) else None
_bits: list[str] = []
if _row0 is not None:
    for col, fmt in (("well_name", "{}"), ("operator", "{}"),
                     ("field", "{}"), ("formation", "{}")):
        val = str(_row0[col]) if col in g.columns and pd.notna(_row0[col]) else ""
        if val and val.lower() != "nan":
            _bits.append(fmt.format(val))
if not _bits and source_label == common.PDP_SYNTH_LABEL:
    import fleet_registry
    m = fleet_registry.get(ss["well_id"])
    _bits = [m.name, f"{m.basin} · {m.area}", m.formation, f"{m.lift} lift"]
if _bits:
    st.caption("**" + ss["well_id"] + "** — " + " · ".join(dict.fromkeys(_bits)))

# cached fit — only re-runs the curve fit when the well, limit, or Dmin changes
t_hist, q_hist, fit, fc_rates = common.fit_one_well(csv_text, ss["well_id"], econ_limit, dmin)

fig = go.Figure()
fig.add_trace(go.Scatter(x=t_hist, y=q_hist, mode="markers", name="history",
                         marker=dict(color=theme.BLUE, size=6),
                         hovertemplate="month %{x:.0f}: %{y:.1f} bopd<extra></extra>"))
t_fit = np.linspace(t_hist[0], t_hist[-1], 120)
fig.add_trace(go.Scatter(
    x=t_fit, y=pdp.arps_rate(t_fit / 12.0, fit.qi_bopd, fit.di_annual, fit.b),
    mode="lines", name=f"{fit.model} fit", line=dict(color=theme.NAVY, dash="dot")))
if len(fc_rates):
    t_fc = fit.t_last_months + np.arange(1, len(fc_rates) + 1) - 0.5
    fig.add_trace(go.Scatter(x=t_fc, y=fc_rates, mode="lines", name="forecast",
                             line=dict(color=theme.GREEN)))
fig.add_vline(x=fit.t_last_months, line_dash="dash", line_color=theme.GREY,
              annotation_text="forecast starts here")
fig.add_hline(y=econ_limit, line_dash="dot", line_color=theme.RED,
              annotation_text=f"economic limit {econ_limit:.0f} bopd")
fig.update_layout(xaxis_title="months since first production", yaxis_title="oil rate (bopd)")
st.plotly_chart(theme.style_fig(fig, height=340), width="stretch")
theme.source_note(
    f"{ss['well_id']}: {fit.model} fit (qi {fit.qi_bopd:,.0f} bopd, Di "
    f"{fit.di_annual:.2f}/yr, b {fit.b:.2f}, R² {fit.r_squared:.2f} on "
    f"{fit.n_points} months). The forecast integrates FORWARD from the last "
    "history month — integrating from t=0 would re-count produced barrels and "
    "overstate remaining EUR ~2–3x.")

theme.references(["arps", "prms", "npv"])
