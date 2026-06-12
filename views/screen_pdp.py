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
src_options = [common.PDP_REAL_LABEL, common.PDP_BYOD_LABEL]
c_src, c_ask = st.columns([2, 1])
with c_src:
    source_choice = st.radio("Production source", src_options, horizontal=True,
                             help="The Colorado slice is genuine public-record "
                                  "ECMC data. Upload your own monthly CSV on this "
                                  "page or the Data page.")
with c_ask:
    asking_mm = st.number_input("Asking price ($MM, 0 = none)", 0.0, 5000.0, 25.0, 1.0,
                                help="The seller's number — compared against PV10.")

if source_choice == common.PDP_BYOD_LABEL and not ss.get("pdp_csv_text"):
    st.info("No uploaded CSV yet — add one below (or on the Data page). "
            "Showing the real Colorado slice meanwhile.")
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
        ss["data_source"] = common.PDP_BYOD_LABEL
        st.success(f"Loaded {up.name} — select 'Uploaded monthly CSV' above.")

csv_text, source_label, is_byod = common.resolve_pdp(source_choice)
pt.context_bar([("Deck", DECK), ("Data", source_label),
                ("Convention", "Forecast forward from last history month")])
theme.data_badge(
    "real",
    "User-uploaded monthly production — parsed in memory only." if is_byod else
    "Colorado ECMC (formerly COGCC) public records — DJ Basin horizontals, Weld County.")

a1, a2, a3 = st.columns(3)
loe = a1.slider("LOE ($/bbl)", 4.0, 30.0, 12.0, 0.5,
                help="Lease operating expense per barrel.")
severance_pct = a2.slider("Severance + ad valorem (%)", 0.0, 15.0, 7.5, 0.5,
                          help="Production-tax drag on net revenue (~7.5% is a "
                               "typical Colorado all-in).")
econ_limit = a3.slider("Economic limit (bopd)", 1.0, 10.0,
                       pdp.DEFAULT_ECON_LIMIT_BOPD, 0.5,
                       help="Forecast stops at this rate or 360 forecast months, "
                            "whichever comes first.")

table, skipped = common.screen_table(csv_text, OIL, loe, NRI,
                                     severance_pct / 100.0, DISC, econ_limit)

if table.empty:
    pt.empty_state("No wells could be fit from this file.",
                   "Each well needs at least 6 positive monthly rates.")
    st.stop()

roll = pdp.deal_rollup(table, asking_mm * 1e6 if asking_mm > 0 else None)

pt.kpi_row([
    {"label": "Deal PV10", "value": f"${roll['total_pv10_usd']/1e6:,.1f}MM",
     "help": "Sum of per-well PV of forward net revenue at the deck discount."},
    {"label": "Remaining EUR", "value": f"{roll['total_eur_bbl']/1e3:,.0f} Mbbl"},
    {"label": "Current Production", "value": f"{roll['total_current_bopd']:,.0f} bopd"},
    {"label": "Wells Fit", "value": f"{roll['n_wells']}"
        + (f" ({len(skipped)} skipped)" if skipped else "")},
])

if asking_mm > 0:
    prem = roll["pv10_minus_asking_usd"]
    ratio = roll["pv10_over_asking"]
    verdict = (pt.pill(f"PV10 covers asking — {ratio:,.2f}x ({prem/1e6:+,.1f}MM)", "ok")
               if prem >= 0 else
               pt.pill(f"PV10 below asking — {ratio:,.2f}x ({prem/1e6:+,.1f}MM)", "bad"))
    st.markdown(
        f"**Asking ${asking_mm:,.0f}MM** → "
        f"**${roll['usd_per_flowing_bbl']:,.0f}/flowing bbl** · {verdict}",
        unsafe_allow_html=True)
    st.caption("Quick-look only: PDP PV10 vs. asking ignores upside (PUDs, "
               "behind-pipe), G&A, and plugging liability — it answers 'is the "
               "producing base alone close to the number'.")

pt.section("PV10 by Well", "Ranked — where the deal's value concentrates.")
bar = go.Figure(go.Bar(
    x=table["well_id"], y=table["pv10_usd"] / 1e6,
    marker_color=theme.BLUE,
    hovertemplate="%{x}: $%{y:.2f}MM<extra></extra>"))
bar.update_layout(xaxis_title="well", yaxis_title="PV10 ($MM)",
                  xaxis=dict(tickangle=-45, tickfont=dict(size=9)))
st.plotly_chart(theme.style_fig(bar, height=320, legend=False), width="stretch")
theme.source_note(
    "PV10 ($MM) per well: Arps forecast from the last history month to the "
    f"{econ_limit:.0f}-bopd economic limit; net revenue = oil x (price − LOE) x "
    "NRI x (1 − severance), discounted effective-annually at the deck.")

pt.section("Per-Well Screen", "Fit parameters and value, one row per well.")
disp = table.rename(columns={
    "well_id": "Well", "model": "Model", "qi_bopd": "qi (bopd)",
    "di_annual": "Di (1/yr)", "b": "b", "r_squared": "R²", "n_months": "Months",
    "current_bopd": "Current (bopd)", "remaining_eur_bbl": "Remaining EUR (bbl)",
    "pv10_usd": "PV10 $"})
st.dataframe(disp, width="stretch", hide_index=True,
             column_config={
                 "PV10 $": st.column_config.NumberColumn(format="$%,.0f"),
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
t_hist, q_hist = pdp.well_history(g)
fit = pdp.fit_well(t_hist, q_hist, well_id=ss["well_id"])
fc_rates, _fc_vols = pdp.forecast_volumes(fit, econ_limit)

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
