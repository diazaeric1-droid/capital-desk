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
pt.context_bar([("Deck", DECK), ("Data", source_label),
                ("Solver", "Program re-solved at every point")])

projects = common.parse_backlog(csv_text)
total_capex = sum(p.capex_usd for p in projects)
ss.setdefault("budget_mm", 60)
ss.setdefault("rig_cap", min(170, int(sum(p.rig_days for p in projects))))
budget = float(ss["budget_mm"]) * 1e6
rig_cap = float(ss["rig_cap"])
st.caption(f"Constraints from the Optimizer page: ${budget/1e6:,.0f}MM budget · "
           f"{rig_cap:.0f} rig-days (adjust them there).")


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
        mode="lines+markers", line=dict(color=theme.NAVY),
        hovertemplate="budget $%{x:,.0f}MM → $%{y:,.1f}MM<extra></extra>"))
    ff.add_vline(x=budget / 1e6, line_dash="dash", line_color=theme.GREEN,
                 annotation_text=f"budget ${budget/1e6:,.0f}MM")
    ff.update_layout(xaxis_title="capital budget ($MM)",
                     yaxis_title="optimal risked NPV ($MM)")
    st.plotly_chart(theme.style_fig(ff, height=330, legend=False), width="stretch")
    theme.source_note("Optimal risked NPV ($MM) re-solved by 0/1 MILP (CBC) at "
                      "each budget, rig limit fixed; discounting at the deck.")
    st.caption("The curve flattens — diminishing marginal value of capital. That "
               "flattening is the picture that sizes (or caps) the budget ask.")
with r:
    pt.section("Price-Deck Sensitivity", "The program re-optimized at each oil price.")
    strip = _price_strip(csv_text, DISC, budget, rig_cap)
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
