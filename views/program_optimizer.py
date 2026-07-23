"""Optimizer — the program that maximizes risked NPV under budget + rig limits.

Exact 0/1 MILP (CBC via PuLP) vs. the greedy rank-by-efficiency baseline most
operators actually use, with the LP-relaxation bound so the result is provably
near-optimal. Honest framing: on this backlog the optimizer's edge is ~3–5%
($4.4–7.8MM) when the rig limit binds — real committee-scale money, no inflation.
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
ss = st.session_state

pt.masthead("capital", "Optimizer",
            "MILP vs. greedy at the same constraints — with a provable optimality bound.")
csv_text, source_label, _is_byod = common.resolve_backlog()
pt.context_bar([("Deck", common.program_deck()), ("Data", source_label),
                ("Solver", "CBC branch-and-bound (PuLP)")])
common.page_purpose(
    "**What this page answers:** which projects should we fund under a fixed "
    "capital budget AND a fixed rig fleet — and how much better is that slate "
    "than the ranking most operators use?\n\n"
    "**Use it to build the funded program:** set budget + rig-days, read the "
    "funded slate, the quarterly schedule, and the program-level P10/P50/P90. "
    "The MILP result is provably near-optimal (LP bound shown) and honestly "
    "framed against the greedy baseline.")

projects = common.parse_backlog(csv_text)
total_capex = sum(p.capex_usd for p in projects)
total_rig = sum(p.rig_days for p in projects)

ss.setdefault("budget_mm", 60)
ss.setdefault("rig_cap", min(170, int(total_rig)))
c1, c2 = st.columns(2)
with c1:
    st.slider("Capital budget ($MM)", 10, max(10, int(total_capex / 1e6)), step=5,
              key="budget_mm")
with c2:
    st.slider("Rig-day capacity", 10, max(10, int(total_rig)), step=10, key="rig_cap")
budget = float(ss["budget_mm"]) * 1e6
rig_cap = float(ss["rig_cap"])

econ = common.econ_frame(csv_text, OIL, DISC)
try:
    program, greedy = common.solve_program(csv_text, OIL, DISC, budget, rig_cap)
except ValueError as exc:  # InfeasibleProgram is a ValueError
    st.error(str(exc))
    st.stop()

sel = set(program.selected_ids)
uplift = program.risked_npv - greedy.risked_npv
uplift_pct = uplift / greedy.risked_npv * 100.0 if greedy.risked_npv > 0 else 0.0

pt.kpi_row([
    {"label": "Program Risked NPV", "value": f"${program.risked_npv/1e6:,.1f}MM"},
    {"label": "Capital Deployed", "value": f"${program.capex_used/1e6:,.1f}MM",
     "delta": f"of ${budget/1e6:,.0f}MM budget", "delta_color": "off"},
    {"label": "Rig-Days Used", "value": f"{program.rig_used:.0f} / {rig_cap:.0f}"},
    {"label": "Projects Selected", "value": f"{program.n_selected} / {program.n_available}"},
    {"label": "Capital Efficiency", "value": f"{program.weighted_cap_eff:.2f}x",
     "help": "Capex-weighted risked NPV per $ of capital across the funded slate."},
    {"label": "Optimizer vs. Greedy", "value": f"+${uplift/1e6:,.1f}MM",
     "delta": f"+{uplift_pct:.1f}%", "help": "MILP over a rank-by-efficiency "
                                             "first-fit at the same budget + rig limit."},
])

gap_txt = (f" The solution is within **{program.optimality_gap_pct:.2f}%** of the "
           f"LP-relaxation bound (${(program.lp_bound or 0)/1e6:,.1f}MM) — provably "
           "near-optimal."
           if program.optimality_gap_pct is not None else "")
st.success(
    f"The MILP captures **${uplift/1e6:,.1f}MM (+{uplift_pct:.1f}%)** more risked NPV "
    f"than a rank-by-efficiency first-fit at the same constraints.{gap_txt}")
st.caption(
    "Honest framing: on this backlog the optimizer's edge over a competent greedy "
    "ranking is ~3–5% ($4.4–7.8MM) and only when the rig limit binds — the value of "
    "optimizing two scarce resources jointly, not a 10x headline. When only the "
    "budget binds, greedy nearly ties.")

# ---- funded vs rejected + allocation ----------------------------------------------
l, r = st.columns(2)
with l:
    pt.section("Funded vs. Rejected", "Capex vs. risked NPV; marker size ∝ rig-days.")
    sc = econ.copy()
    sc["funded"] = sc["project_id"].isin(sel)
    maxr = sc["rig_days"].max()
    # always a Series (a scalar fallback would crash on size[g.index] for a
    # zero-rig-day backlog — e.g. a BYOD upload with the column all zero).
    size = ((sc["rig_days"] / maxr * 30 + 6) if maxr > 0
            else pd.Series(12.0, index=sc.index))
    scat = go.Figure()
    for funded, name, color in [(True, "Funded", theme.GREEN),
                                (False, "Rejected", theme.GREY)]:
        g = sc[sc["funded"] == funded]
        if len(g):
            scat.add_trace(go.Scatter(
                x=g["capex_usd"] / 1e6, y=g["risked_npv_usd"] / 1e6, mode="markers",
                name=name, text=g["project_id"],
                marker=dict(color=color, size=size[g.index],
                            line=dict(width=0.5, color=theme.BG)),
                hovertemplate="%{text}<br>capex $%{x:.1f}MM<br>risked NPV "
                              "$%{y:.1f}MM<extra>" + name + "</extra>"))
    # label the single highest-NPV funded project so the scatter is identifiable
    # without hovering every point.
    fund = sc[sc["funded"]]
    if len(fund):
        tp = fund.loc[fund["risked_npv_usd"].idxmax()]
        scat.add_annotation(x=tp["capex_usd"] / 1e6, y=tp["risked_npv_usd"] / 1e6,
                            text=tp["project_id"], showarrow=True, arrowhead=2,
                            ax=18, ay=-16, font=dict(size=9, color=theme.GREEN))
    scat.update_layout(xaxis_title="capex ($MM)", yaxis_title="risked NPV ($MM)")
    st.plotly_chart(theme.style_fig(scat, height=330), width="stretch")
    theme.source_note("0/1 MILP (CBC via PuLP); funded points cluster toward high "
                      "NPV per unit capex AND per rig-day.")
with r:
    pt.section("Allocation by Category", "Where the funded capital goes.")
    bc = pd.DataFrame([{"Category": k, "Capex $MM": v["capex"] / 1e6,
                        "Risked NPV $MM": v["risked_npv"] / 1e6}
                       for k, v in program.by_category.items()])
    if len(bc):
        pf = go.Figure()
        pf.add_bar(x=bc["Category"], y=bc["Capex $MM"], name="Capex $MM",
                   marker_color=theme.NAVY)
        pf.add_bar(x=bc["Category"], y=bc["Risked NPV $MM"], name="Risked NPV $MM",
                   marker_color=theme.BLUE)
        pf.update_layout(barmode="group")
        st.plotly_chart(theme.style_fig(pf, height=330), width="stretch")
        theme.source_note("Funded program grouped by project type; capex and "
                          "risked NPV in $MM.")
    else:
        pt.empty_state("Nothing funded under the current constraints.")

# ---- quarterly schedule -------------------------------------------------------------
pt.section("Quarterly Schedule",
           "The funded program laid into quarters under per-quarter rig capacity, "
           "respecting each project's earliest start quarter.")
rig_q = st.slider("Rig-day capacity per quarter", 20, max(int(rig_cap), 20),
                  max(int(rig_cap) // 4, 20), 5)
sched = core.capital_schedule.schedule_program(
    econ, list(sel), projects, n_quarters=4, rig_per_quarter=rig_q)
if len(sched):
    agg = (sched.groupby("quarter")
           .agg(capex=("capex_usd", "sum"), rig=("rig_days", "sum"),
                npv=("risked_npv_usd", "sum"), n=("project_id", "size"))
           .reset_index())
    sf = go.Figure()
    sf.add_bar(x=agg["quarter"], y=agg["capex"] / 1e6, name="Capex $MM",
               marker_color=theme.NAVY)
    sf.add_bar(x=agg["quarter"], y=agg["rig"], name="Rig-days",
               marker_color=theme.RED, yaxis="y2")
    sf.update_layout(barmode="group",
                     yaxis_title="capex ($MM)",
                     yaxis2=dict(overlaying="y", side="right", title="rig-days"))
    over = agg[agg["rig"] > rig_q]
    if len(over):
        st.caption(
            f"⚠️ {', '.join(over['quarter'])} exceeds the {rig_q:.0f} rig-day/quarter "
            "cap: projects that don't fit any earlier feasible quarter spill into the "
            "final quarter rather than being dropped. Raise the per-quarter cap or the "
            "rig limit on the Optimizer to clear the overflow.")
    st.plotly_chart(theme.style_fig(sf, height=300), width="stretch")
    theme.source_note("Greedy bin-pack by capital efficiency into the earliest "
                      "feasible quarter ≥ each project's earliest_quarter; unplaceable "
                      "projects spill into the final quarter (may exceed the per-quarter "
                      "cap — flagged above). Left axis capex ($MM), right axis rig-days.")
    disp = sched.copy()
    disp["capex_usd"] = disp["capex_usd"].map(lambda v: f"${v/1e6:,.2f}MM")
    disp["risked_npv_usd"] = disp["risked_npv_usd"].map(lambda v: f"${v/1e6:,.2f}MM")
    st.dataframe(
        disp.rename(columns={"quarter": "Quarter", "name": "Project",
                             "category": "Type", "capex_usd": "Capex",
                             "rig_days": "Rig-Days", "risked_npv_usd": "Risked NPV"})
        [["Quarter", "Project", "Type", "Capex", "Rig-Days", "Risked NPV"]],
        width="stretch", hide_index=True)
else:
    pt.empty_state("No funded projects to schedule.")

# ---- recommended program table ---------------------------------------------------
pt.section("Recommended Program", "The funded slate, ranked by risked NPV.")
ptab = econ[econ["project_id"].isin(sel)].sort_values(
    "risked_npv_usd", ascending=False).copy()
ptab["Capex"] = ptab["capex_usd"].map(lambda v: f"${v/1e6:,.2f}MM")
ptab["Risked NPV"] = ptab["risked_npv_usd"].map(lambda v: f"${v/1e6:,.2f}MM")
ptab["Cap. Eff."] = ptab["capital_efficiency"].map(lambda v: f"{v:.2f}x")
ptab["IRR"] = ptab["irr_pct"].map(
    lambda v: ">500%" if pd.notna(v) and v >= 500 else (f"{v:.0f}%" if pd.notna(v) else "—"))
ptab["Pc"] = ptab["pc"].map(lambda v: f"{v:.0%}")
out = (ptab[["project_id", "name", "label", "area", "Capex", "Risked NPV",
             "Cap. Eff.", "IRR", "Pc"]]
       .rename(columns={"project_id": "ID", "name": "Project", "label": "Type",
                        "area": "Area"}))
st.dataframe(out, width="stretch", hide_index=True)
st.download_button("Download funded program (CSV)", data=out.to_csv(index=False),
                   file_name="funded_program.csv", mime="text/csv")
theme.source_note("Selection by exact 0/1 MILP (CBC); greedy baseline and LP bound "
                  "reported above keep the uplift claim honest.")

# ---- program-level Monte-Carlo --------------------------------------------------
pt.section("Program Risk — Monte-Carlo",
           "The funded program's NPV distribution over price AND each project's "
           "chance of success — the P-curve a committee signs against, not a single "
           "risked point.")
mc1, mc2 = st.columns(2)
price_sd = mc1.slider("Oil-price uncertainty (± $ std-dev)", 4.0, 25.0, 12.0, 1.0,
                      help="Std-dev of realized oil price around the deck; each "
                           "project also succeeds with probability Pc (else it loses "
                           "its capex as a dry hole).")
rho = mc2.slider("Geologic correlation (ρ)", 0.0, 0.9, 0.3, 0.05,
                 help="How correlated dry-hole risk is across the slate (shared "
                      "basin/geology). 0 = independent (optimistic tail); higher ρ "
                      "widens the downside — the realistic case for a single-basin "
                      "program. The mean is unchanged; only the spread (P10) moves.")
mc = common.program_montecarlo(csv_text, OIL, DISC, tuple(sorted(sel)),
                               price_sd=price_sd, rho=rho)
if mc is None:
    pt.empty_state("Nothing funded to simulate under the current constraints.")
else:
    pt.kpi_row([
        {"label": "P10 NPV (Downside)", "value": f"${mc['p10']/1e6:,.0f}MM"},
        {"label": "P50 NPV (Median)", "value": f"${mc['p50']/1e6:,.0f}MM"},
        {"label": "P90 NPV (Upside)", "value": f"${mc['p90']/1e6:,.0f}MM"},
        {"label": "Mean NPV", "value": f"${mc['mean']/1e6:,.0f}MM"},
        {"label": "P(Program Loss)", "value": f"{mc['p_loss']*100:.0f}%",
         "help": "Share of trials where the whole funded program returns < $0."},
    ])
    hist = go.Figure(go.Histogram(x=mc["samples"] / 1e6, nbinsx=40,
                                  marker_color=theme.BLUE))
    hist.add_vline(x=mc["p50"] / 1e6, line_dash="dash", line_color=theme.NAVY,
                   annotation_text="P50")
    hist.add_vline(x=0, line_dash="dot", line_color=theme.RED)
    hist.update_layout(xaxis_title="program NPV ($MM)", yaxis_title="trials")
    st.plotly_chart(theme.style_fig(hist, height=300, legend=False), width="stretch")
    st.caption(f"Deterministic risked NPV (${program.risked_npv/1e6:,.1f}MM) sits near "
               "the mean (correlation widens the spread, not the mean); the P10 is what "
               f"price + correlated dry-hole risk (ρ={rho:.2f}) do to the downside. Raise "
               "ρ for a more conservative, single-basin underwrite.")
    theme.source_note(
        "5,000 trials: price ~ Normal(deck, ±sd); each funded project books its "
        "unrisked NPV at the sampled price on success (prob Pc) or −capex on a dry "
        "hole. Per-project NPV(price) interpolated from a cached price grid.")

theme.references(["milp", "npv", "monte_carlo"])
