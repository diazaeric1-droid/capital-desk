"""Variance — actual vs. AFE on closed-out jobs, with supplemental-AFE policy flags.

Port of the AFE Copilot variance analyzer: portfolio variance, worst-offender
category by absolute $ overrun (unbudgeted lines included — never hidden), and
the >10% overrun flag that policy says requires a supplemental AFE.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import core
import product_theme as pt
import theme
from views import common

ss = st.session_state
OIL = float(ss.get("oil_price", 70.0))
NRI = float(ss.get("nri", 0.80))
DISC = float(ss.get("discount", 0.10))

pt.masthead("capital", "Variance",
            "Actual vs. AFE on closed-out jobs — where the money actually went.")
n_live = len(ss.get("live_actuals", {}))
pt.context_bar([
    ("Deck", f"${OIL:.0f}/bbl · NRI {NRI:.0%} · {DISC:.1%} disc"),
    ("Data", f"Demo closed-out actuals (synthetic){f' + {n_live} executed live' if n_live else ''}"),
    ("Policy", f"Supplement above +{core.afe_variance.SUPPLEMENT_THRESHOLD_PCT:.0f}% overrun"),
])
common.page_purpose(
    "**What this page answers:** did closed-out jobs actually cost what their "
    "AFE said — and which cost category is blowing out?\n\n"
    "**Use it after execution:** the close-out step of the AFE loop. It ranks "
    "the worst-offender category by absolute $ (unbudgeted lines included, "
    "never hidden) and flags any AFE whose overrun crosses the "
    f"+{core.afe_variance.SUPPLEMENT_THRESHOLD_PCT:.0f}% policy line where a "
    "supplemental AFE is required.")
if n_live:
    st.info(f"Including {n_live} AFE(s) you executed on the Pipeline Board this session "
            "— the detect → authorize → reconcile loop, closed in-product.")

# Demo closed-out actuals PLUS any AFEs executed from the Pipeline Board this session.
afe_df, actuals_df = common.combined_variance_frames()
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
    pct_txt = (f" ({vs.worst_offender_pct:+.0f}% over its AFE line)"
               if vs.worst_offender_pct is not None
               else " (100% unbudgeted — no AFE line existed)")
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

# Per-line variance frame (one row per AFE × category), plus a per-category roll-up.
merged = afe_df.merge(actuals_df, on=["afe_number", "category"], how="outer").fillna(0)
merged["variance_usd"] = merged["actual_usd"] - merged["line_total_usd"]
merged["variance_pct"] = (merged["variance_usd"]
                          / merged["line_total_usd"].replace(0, pd.NA)) * 100.0

by_cat = (merged.groupby("category", as_index=False)
          .agg(afe_budget=("line_total_usd", "sum"), actual=("actual_usd", "sum")))
by_cat["variance_usd"] = by_cat["actual"] - by_cat["afe_budget"]
by_cat["variance_pct"] = (by_cat["variance_usd"]
                          / by_cat["afe_budget"].replace(0, pd.NA)) * 100.0
by_cat = by_cat.sort_values("variance_usd", ascending=False).reset_index(drop=True)

pt.section("Variance by Category",
           "Each cost category's actual-vs-AFE — overruns red, savings green.")
cf = go.Figure(go.Bar(
    x=by_cat["category"], y=by_cat["variance_usd"],
    marker_color=[theme.RED if v > 0 else theme.GREEN for v in by_cat["variance_usd"]],
    text=[f"${v:,.0f}" for v in by_cat["variance_usd"]], textposition="outside",
    hovertemplate="%{x}: $%{y:,.0f} vs AFE<extra></extra>"))
cf.update_layout(xaxis_title="cost category", yaxis_title="variance vs AFE ($)",
                 xaxis=dict(tickangle=-30))
st.plotly_chart(theme.style_fig(cf, height=300, legend=False), width="stretch")
theme.source_note(
    "Variance ($) = actual − AFE budget per category; a 100%-unbudgeted category "
    "(no AFE line existed) shows its full actual as overrun — never dropped.")

pt.section("AFE Line Detail", "Pick a category to drill into the AFE lines behind it.")
cats = ["All categories"] + list(by_cat["category"])
pick = st.selectbox("Drill into category", cats, key="variance_cat",
                    help="Choose a single cost category to see every AFE line in it; "
                         "'All categories' shows the full line-level table.")
if pick == "All categories":
    view = merged.sort_values("variance_usd", ascending=False)
else:
    view = merged[merged["category"] == pick].sort_values("variance_usd", ascending=False)
    row = by_cat[by_cat["category"] == pick].iloc[0]
    pct_txt = ("unbudgeted" if pd.isna(row["variance_pct"])
               else f"{row['variance_pct']:+.0f}%")
    pt.kpi_row([
        {"label": f"{pick} — AFE Budget", "value": f"${row['afe_budget']:,.0f}"},
        {"label": "Actual", "value": f"${row['actual']:,.0f}"},
        {"label": "Variance", "value": f"${row['variance_usd']:,.0f}",
         "delta": pct_txt, "delta_color": "inverse"},
        {"label": "AFE Lines", "value": int(len(view))},
    ])

disp = view.rename(columns={
    "afe_number": "AFE", "category": "Category", "line_total_usd": "AFE Budget $",
    "actual_usd": "Actual $", "variance_usd": "Variance $", "variance_pct": "Variance %"})
st.dataframe(
    disp[["AFE", "Category", "AFE Budget $", "Actual $", "Variance $", "Variance %"]],
    width="stretch", hide_index=True,
    column_config={
        **{c: st.column_config.NumberColumn(format="$%,.0f")
           for c in ("AFE Budget $", "Actual $", "Variance $")},
        "Variance %": st.column_config.NumberColumn(format="%+.0f%%",
                                                    help="Blank = unbudgeted (no AFE line)"),
    })
st.download_button("Download variance (CSV)", data=merged.to_csv(index=False),
                   file_name="afe_variance.csv", mime="text/csv")
theme.source_note(
    "Per-line variance (USD) = actual − AFE budget; demo actuals include a "
    "100%-unbudgeted Fishing line and a rig overrun that trips the supplemental-"
    "AFE policy. The worst offender ranks by absolute $ so unbudgeted lines are "
    "never silently dropped.")
