"""Pipeline Board — every in-flight AFE: status, authority routing, audit trail.

Condensed port of the AFE Copilot demo's Overview + per-AFE drill-down onto one
board backed by the product-local SQLite tracker (seeded on first run; gitignored).
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

pt.masthead("capital", "Pipeline Board",
            "Every in-flight AFE — status, dollars, required authority, audit trail.")
pt.context_bar([
    ("Deck", f"${OIL:.0f}/bbl · NRI {NRI:.0%} · {DISC:.1%} disc"),
    ("Data", "Demo tracker (SQLite, product-local)"),
    ("Policy", "Supplement required above +10% overrun"),
])


@st.cache_data(show_spinner=False)
def _pipeline(_token: int) -> pd.DataFrame:
    return core.pipeline_df()


@st.cache_data(show_spinner=False)
def _events(afe_number: str, _token: int) -> pd.DataFrame:
    return core.get_tracker().events(afe_number)


@st.cache_data(show_spinner=False)
def _variance_pct(afe_number: str) -> float | None:
    """AFE-level actual-vs-budget overrun % from the demo closed-out actuals."""
    afe_df, actuals_df = core.afe_variance.demo_variance_data()
    if afe_number not in set(afe_df["afe_number"]) | set(actuals_df["afe_number"]):
        return None
    budget = float(afe_df.loc[afe_df["afe_number"] == afe_number, "line_total_usd"].sum())
    actual = float(actuals_df.loc[actuals_df["afe_number"] == afe_number, "actual_usd"].sum())
    return ((actual - budget) / budget * 100.0) if budget else None


def _net_npv(row) -> float | None:
    """Deterministic net-NPV ranking column at the GLOBAL deck (+100 BOPD nominal
    uplift — comparable across AFEs; the real uplift lives in each diagnosis).
    P&A is cost-only: no production economics."""
    if row["intervention"] == "p_and_a" or row["intervention"] not in core.afe_cost_db.COST_TEMPLATES:
        return None
    e = core.draft_economics(float(row["total_cost_usd"]), 100.0,
                             realized_price_per_bbl=OIL,
                             net_revenue_interest=NRI, discount_rate=DISC)
    return float(e.net_npv_10pct_usd)


token = ss.get("_afe_cache_token", 0)
df = _pipeline(token)

if df.empty:
    pt.empty_state("No AFEs in the tracker yet.",
                   "Draft one on the Draft AFE page and submit it to the pipeline.")
    st.stop()

in_flight = df.status.isin(list(core.afe_tracker.IN_FLIGHT_STATUSES))
pt.kpi_row([
    {"label": "In-Flight $", "value": f"${df.loc[in_flight, 'total_cost_usd'].sum()/1e6:.1f}MM",
     "help": "Draft + engineering-review + finance-review AFEs."},
    {"label": "In-Flight AFEs", "value": int(in_flight.sum())},
    {"label": "Approved (Not Executed)", "value": int((df.status == "approved").sum())},
    {"label": "Above PE Authority", "value": int((df["required_approver"] != "Production Engineer").sum()),
     "help": "AFEs needing an Engineering Manager or higher sign-off."},
])

pt.section("AFE Pipeline",
           "One row per AFE. Supplement flags an actual >10% over the AFE "
           "(policy requires a supplemental AFE before further spend).")
rows = []
for _, r in df.iterrows():
    var_pct = _variance_pct(r["afe_number"])
    supplement = (var_pct is not None
                  and var_pct > core.afe_variance.SUPPLEMENT_THRESHOLD_PCT)
    try:
        net_npv = _net_npv(r)
    except Exception:  # noqa: BLE001 — ranking column must never take down the board
        net_npv = None
    rows.append({
        "AFE #": r["afe_number"],
        "Well": r["well_id"],
        "Intervention": str(r["intervention"]).replace("_", " "),
        "Gross Cost $": float(r["total_cost_usd"]),
        "Net NPV $": net_npv,
        "Status": str(r["status"]).replace("_", " "),
        "Required Approver": r["required_approver"],
        "Days in Status": int(r["days_in_status"]),
        "Bottleneck": r["bottleneck_risk"],
        "Supplement": "REQUIRED" if supplement else "",
        "Variance": (f"{var_pct:+.0f}%" if var_pct is not None else "—"),
    })
board = pd.DataFrame(rows)
st.dataframe(
    board, width="stretch", hide_index=True,
    column_config={
        "Gross Cost $": st.column_config.NumberColumn(format="$%,.0f"),
        "Net NPV $": st.column_config.NumberColumn(format="$%,.0f"),
    })
st.download_button("Download pipeline (CSV)", data=board.to_csv(index=False),
                   file_name="afe_pipeline.csv", mime="text/csv")
theme.source_note(
    "Tracker rows from the product-local SQLite store; Net NPV (USD) is a "
    "deterministic ranking column at the global deck (+100 BOPD nominal uplift); "
    "variance = actual − AFE budget (%) on demo closed-out actuals.")

pt.section("Authority Routing",
           "Delegation-of-authority: the sign-off level each AFE's dollar value requires.")
ladder = pd.DataFrame(
    [{"Limit": ("Above $1,000,000" if limit == float("inf")
                else f"Up to ${limit:,.0f}"), "Approver": role,
      "AFEs at This Tier": int((df["required_approver"] == role).sum())}
     for limit, role in core.afe_tracker.AUTHORITY_LIMITS])
st.dataframe(ladder, width="stretch", hide_index=True)

pt.section("Audit Trail", "Immutable status-change log — appended, never overwritten.")
sel = st.selectbox("AFE", sorted(df["afe_number"]), key="board_afe")
ev = _events(sel, token)
if ev.empty:
    st.caption("No status-change events recorded for this AFE.")
else:
    st.dataframe(ev[["ts", "from_status", "to_status", "actor", "note"]],
                 width="stretch", hide_index=True)
    st.caption("Every transition is appended to the event log — the audit shape an "
               "internal-audit / SOX reviewer expects of a capital tracker.")

theme.references(["npv"])
