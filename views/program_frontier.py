"""Frontier & Sensitivity — what the next $10MM is worth, and what $55 oil does.

Efficient frontier (optimal risked NPV re-solved at each budget level) plus a
price-deck sensitivity, both honoring the GLOBAL deck's discount rate — the two
charts a VP always asks for before signing the budget ask.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import product_theme as pt
import theme
from views import common

OIL, NRI, DISC, DECK = common.deck()
ss = st.session_state

pt.masthead("capital", "Frontier & Sensitivity",
            "The marginal value of capital, and the program's price-deck exposure.")
csv_text, source_label, _is_byod = common.resolve_backlog()
pt.context_bar([("Deck", common.program_deck()), ("Data", source_label),
                ("Solver", "Program re-solved at every point")])

projects = common.parse_backlog(csv_text)
total_capex = sum(p.capex_usd for p in projects)
total_rig = sum(p.rig_days for p in projects)
ss.setdefault("budget_mm", 60)
ss.setdefault("rig_cap", min(170, int(total_rig)))
# Budget + rig live controls (shared session keys with the Optimizer page, so a
# change here updates both — and the page works even if you land here first).
c1, c2 = st.columns(2)
with c1:
    st.slider("Capital budget ($MM)", 10, max(10, int(total_capex / 1e6)), step=5,
              key="budget_mm")
with c2:
    st.slider("Rig-day capacity", 10, max(10, int(total_rig)), step=10, key="rig_cap")
budget = float(ss["budget_mm"]) * 1e6
rig_cap = float(ss["rig_cap"])
st.caption("These constraints are shared with the Optimizer page — changing them "
           "here updates both.")


@st.cache_data(show_spinner="Re-solving the frontier (12 MILP solves)…")
def _frontier(csv_text: str, price: float, discount: float, rig: float,
              max_budget: float, steps: int = 12):
    rows = []
    econ = common.econ_frame(csv_text, price, discount)
    for i in range(1, steps + 1):
        b = max_budget * i / steps
        prog, _greedy = common.solve_program_uncached(csv_text, price, discount, b, rig)
        rows.append({"budget": b, "risked_npv": prog.risked_npv,
                     "n_selected": prog.n_selected})
    return rows, len(econ)


@st.cache_data(show_spinner="Re-optimizing across the price strip…")
def _price_strip(csv_text: str, discount: float, budget: float, rig: float,
                 prices=(50.0, 60.0, 70.0, 80.0)):
    rows = []
    for px in prices:
        prog, _greedy = common.solve_program_uncached(csv_text, px, discount,
                                                      budget, rig)
        rows.append({"price": px, "risked_npv": prog.risked_npv,
                     "n_selected": prog.n_selected})
    return rows


l, r = st.columns(2)
with l:
    pt.section("Efficient Frontier", "Optimal risked NPV at each budget level.")
    front, _n = _frontier(csv_text, OIL, DISC, rig_cap, float(total_capex))
    ff = go.Figure(go.Scatter(
        x=[f["budget"] / 1e6 for f in front],
        y=[f["risked_npv"] / 1e6 for f in front],
        customdata=[f["n_selected"] for f in front],
        mode="lines+markers", line=dict(color=theme.NAVY),
        hovertemplate="budget $%{x:,.0f}MM → $%{y:,.1f}MM "
                      "(%{customdata} projects)<extra></extra>"))
    ff.add_vline(x=budget / 1e6, line_dash="dash", line_color=theme.GREEN,
                 annotation_text=f"budget ${budget/1e6:,.0f}MM")
    ff.update_layout(xaxis_title="capital budget ($MM)",
                     yaxis_title="optimal risked NPV ($MM)")
    st.plotly_chart(theme.style_fig(ff, height=330, legend=False), width="stretch")
    theme.source_note(f"Optimal risked NPV ($MM) re-solved by 0/1 MILP (CBC) at each "
                      f"budget, with the rig limit FIXED at {rig_cap:.0f} rig-days; "
                      "discounting at the deck.")
    st.caption("The curve flattens once the binding constraint shifts from capital to "
               f"the fixed {rig_cap:.0f}-rig-day limit (and the economic projects run "
               "out) — past that point more budget buys little NPV. Raise the rig limit "
               "on the Optimizer to see the frontier extend.")
with r:
    pt.section("Price-Deck Sensitivity", "The program re-optimized at each oil price.")
    # include the actual deck price so the green "current deck" bar always appears
    # (a deck of $65 would otherwise fall between the hardcoded $50/60/70/80 grid).
    strip_prices = tuple(sorted({50.0, 60.0, 70.0, 80.0, round(OIL, 2)}))
    strip = _price_strip(csv_text, DISC, budget, rig_cap, prices=strip_prices)
    pp = go.Figure(go.Bar(
        x=[f"${s['price']:.0f}" for s in strip],
        y=[s["risked_npv"] / 1e6 for s in strip],
        marker_color=[theme.GREEN if abs(s["price"] - OIL) < 1e-9 else theme.BLUE
                      for s in strip],
        text=[f"{s['n_selected']} projects" for s in strip], textposition="outside",
        hovertemplate="%{x}: $%{y:,.1f}MM<extra></extra>"))
    pp.update_layout(xaxis_title="realized oil price ($/bbl)",
                     yaxis_title="program risked NPV ($MM)")
    st.plotly_chart(theme.style_fig(pp, height=330, legend=False), width="stretch")
    theme.source_note("Program re-optimized at each price ($/bbl) at fixed budget "
                      "+ rig limit; green bar marks the current deck price band.")
    st.caption("Selection changes with price — marginal projects drop out at $50, "
               "not just shrink. That's why the program is re-optimized per price, "
               "not just re-priced.")

theme.references(["milp", "npv"])
