"""Backlog — the capital inventory the optimizer chooses from.

The committed 45-project synthetic Permian backlog (deliberately including a
sub-economic tail — 13 of 45 at the $70 deck — so the constraints actually bind),
or bring your own backlog CSV in the component's documented schema.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import core
import product_theme as pt
import theme
from views import common

OIL, NRI, DISC, DECK = common.deck()

pt.masthead("capital", "Backlog",
            "The project inventory — risked per-project economics at the deck.")

# ---- source (BYOD upload wins; also offered on the Data page) -------------------
csv_text, source_label, is_byod = common.resolve_backlog()
pt.context_bar([("Deck", DECK), ("Data", source_label)])

with st.expander("Bring your own backlog (CSV)"):
    st.caption("Required columns: "
               + ", ".join(f"`{c}`" for c in core.capital_projects.REQUIRED_CSV_COLUMNS)
               + ". Nothing is stored server-side — parsed in memory for this session.")
    st.download_button("Download template CSV", data=common.BACKLOG_TEMPLATE,
                       file_name="backlog_template.csv", mime="text/csv")
    up = st.file_uploader("Backlog CSV", type=["csv"], key="backlog_upload_page")
    if up is not None:
        text = up.getvalue().decode("utf-8", errors="replace")
        try:
            common.parse_backlog(text)
        except ValueError as exc:
            st.error(f"Could not load backlog: {exc}")
            st.stop()
        st.session_state["backlog_csv_text"] = text
        st.session_state["data_source"] = common.BACKLOG_BYOD_LABEL
        st.success(f"Loaded {up.name} — the Program pages now run on your backlog.")
        st.rerun()
    if is_byod and st.button("Revert to the demo backlog"):
        st.session_state.pop("backlog_csv_text", None)
        st.session_state["data_source"] = "Bundled demo data"
        st.rerun()

theme.data_badge(
    "real" if is_byod else "synthetic",
    "User-uploaded backlog — parsed in memory only." if is_byod else
    "Modeled drilling / DUC / workover backlog — future capital projects aren't public data.")

econ = common.econ_frame(csv_text, OIL, DISC)
sub_econ = int((econ["risked_npv_usd"] <= 0).sum())
projects = common.parse_backlog(csv_text)
total_capex = sum(p.capex_usd for p in projects)
total_rig = sum(p.rig_days for p in projects)

pt.kpi_row([
    {"label": "Projects", "value": len(econ)},
    {"label": "Backlog Capex", "value": f"${total_capex/1e6:,.0f}MM"},
    {"label": "Backlog Rig-Days", "value": f"{total_rig:,.0f}"},
    {"label": "Sub-Economic at Deck", "value": f"{sub_econ} / {len(econ)}",
     "help": "Projects whose risked NPV ≤ 0 at the current price + discount — "
             "the tail the optimizer must leave behind."},
])
st.caption(
    f"{sub_econ} of {len(econ)} projects are sub-economic at the ${OIL:.0f} deck — "
    "a defensible committee backlog, not a flattering one. Total backlog capex far "
    "exceeds any single-year budget, which is exactly what makes the budget and "
    "rig constraints bind on the Optimizer page.")

pt.section("Risked NPV by Project", "Ranked at the deck — the sub-economic tail in red.")
d = econ.sort_values("risked_npv_usd", ascending=False)
fig = go.Figure(go.Bar(
    x=d["project_id"], y=d["risked_npv_usd"] / 1e6,
    marker_color=[theme.BLUE if v > 0 else theme.RED for v in d["risked_npv_usd"]],
    hovertemplate="%{x}: $%{y:.2f}MM<extra></extra>"))
fig.update_layout(xaxis_title="project (ranked)", yaxis_title="risked NPV ($MM)",
                  xaxis=dict(showticklabels=False))
st.plotly_chart(theme.style_fig(fig, height=320, legend=False), width="stretch")
theme.source_note(
    "Risked NPV ($MM) = Pc x PV(net revenue) − capex per project (Arps type curve "
    "→ monthly DCF, effective-annual discounting at the deck); red = sub-economic.")

pt.section("Project Inventory", "Per-project risked economics at the deck.")
table = econ[["project_id", "name", "label", "area", "capex_usd", "risked_npv_usd",
              "npv_usd", "irr_pct", "payout_months", "eur_bbl", "capital_efficiency",
              "pc", "rig_days"]].copy()
table = table.rename(columns={
    "project_id": "ID", "name": "Project", "label": "Type", "area": "Area",
    "capex_usd": "Capex $", "risked_npv_usd": "Risked NPV $", "npv_usd": "NPV $",
    "irr_pct": "IRR %", "payout_months": "Payout (mo)", "eur_bbl": "EUR (bbl)",
    "capital_efficiency": "Cap. Eff. (x)", "pc": "Pc", "rig_days": "Rig-Days"})
st.dataframe(
    table, width="stretch", hide_index=True,
    column_config={
        "Capex $": st.column_config.NumberColumn(format="$%,.0f"),
        "Risked NPV $": st.column_config.NumberColumn(format="$%,.0f"),
        "NPV $": st.column_config.NumberColumn(format="$%,.0f"),
        "EUR (bbl)": st.column_config.NumberColumn(format="%,.0f"),
        "Cap. Eff. (x)": st.column_config.NumberColumn(format="%.2f"),
        "Pc": st.column_config.NumberColumn(format="%.2f"),
    })
st.download_button("Download backlog economics (CSV)", data=econ.to_csv(index=False),
                   file_name="backlog_economics.csv", mime="text/csv")
theme.source_note(
    "One row per project: Arps (qi, Di, b) type curve → 15-yr monthly volumes → "
    "net margin x NRI → PV at the deck discount; risked NPV chance-weights "
    "revenue only (cost is certain).")

theme.references(["arps", "npv"])
