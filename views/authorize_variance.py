"""Variance — actual vs. AFE on closed-out jobs, with supplemental-AFE policy flags.

Port of the AFE Copilot variance analyzer: portfolio variance, worst-offender
category by absolute $ overrun (unbudgeted lines included — never hidden), and
the >10% overrun flag that policy says requires a supplemental AFE.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import core
import product_theme as pt
import theme

ss = st.session_state
OIL = float(ss.get("oil_price", 70.0))
NRI = float(ss.get("nri", 0.80))
DISC = float(ss.get("discount", 0.10))

pt.masthead("capital", "Variance",
            "Actual vs. AFE on closed-out jobs — where the money actually went.")
pt.context_bar([
    ("Deck", f"${OIL:.0f}/bbl · NRI {NRI:.0%} · {DISC:.1%} disc"),
    ("Data", "Demo closed-out actuals (synthetic)"),
    ("Policy", f"Supplement above +{core.afe_variance.SUPPLEMENT_THRESHOLD_PCT:.0f}% overrun"),
])

afe_df, actuals_df = core.afe_variance.demo_variance_data()
vs = core.afe_variance.analyze_variance(afe_df, actuals_df)

pt.kpi_row([
    {"label": "AFEs Analyzed", "value": vs.n_afes},
    {"label": "Portfolio Variance", "value": f"{vs.overall_variance_pct:+.1f}%",
     "delta": f"${vs.total_actual_usd - vs.total_afe_usd:,.0f}",
     "delta_color": "inverse"},
    {"label": "Over Budget", "value": vs.over_budget_count},
    {"label": "Total Actual", "value": f"${vs.total_actual_usd/1e6:,.2f}MM"},
])

if vs.worst_offender_category:
    pct_txt = (f" ({vs.worst_offender_pct:+.0f}%)"
               if vs.worst_offender_pct is not None else " (unbudgeted)")
    st.markdown(
        f"**Worst-offender category:** {vs.worst_offender_category} — "
        f"**${vs.worst_offender_overrun_usd:,.0f}** overrun{pct_txt}. "
        + pt.pill("ranked by $ overrun, not %", "info"),
        unsafe_allow_html=True)
if vs.unbudgeted_categories:
    st.warning("Unbudgeted actuals (no AFE line existed): "
               + ", ".join(vs.unbudgeted_categories))
if vs.supplement_required_afes:
    st.error("Supplemental AFE required (actuals exceed the AFE by more than "
             f"{core.afe_variance.SUPPLEMENT_THRESHOLD_PCT:.0f}%): "
             + ", ".join(vs.supplement_required_afes))

pt.section("Line-Level Detail", "Per-category variance, sorted by largest overrun.")
merged = afe_df.merge(actuals_df, on=["afe_number", "category"], how="outer").fillna(0)
merged["variance_usd"] = merged["actual_usd"] - merged["line_total_usd"]
merged = merged.sort_values("variance_usd", ascending=False)
disp = merged.rename(columns={
    "afe_number": "AFE", "category": "Category", "line_total_usd": "AFE Budget $",
    "actual_usd": "Actual $", "variance_usd": "Variance $"})
st.dataframe(disp, width="stretch", hide_index=True,
             column_config={c: st.column_config.NumberColumn(format="$%,.0f")
                            for c in ("AFE Budget $", "Actual $", "Variance $")})
st.download_button("Download variance (CSV)", data=merged.to_csv(index=False),
                   file_name="afe_variance.csv", mime="text/csv")
theme.source_note(
    "Per-category variance (USD) = actual − AFE budget; demo actuals include a "
    "100%-unbudgeted Fishing line and a rig overrun that trips the supplemental-"
    "AFE policy. The worst offender ranks by absolute $ so unbudgeted lines are "
    "never silently dropped.")

theme.references(["npv"])
