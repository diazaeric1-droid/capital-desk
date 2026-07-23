"""Pipeline Board — every in-flight AFE: status, authority routing, audit trail.

Condensed port of the AFE Copilot demo's Overview + per-AFE drill-down onto one
board backed by the product-local SQLite tracker (seeded on first run; gitignored).
The per-AFE detail panel renders the full status journey as a stepper with an
explicit "what's remaining to get this approved" line (PE feedback CD4).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import core
import product_theme as pt
import theme
from src import afe_status
from views import common

ss = st.session_state
OIL = float(ss.get("oil_price", 70.0))
NRI = float(ss.get("nri", 0.80))
DISC = float(ss.get("discount", 0.10))
SEV = float(ss.get("severance_pct", 7.5)) / 100.0

# Type-typical first-year incremental oil (BOPD) by intervention — a defensible
# per-TYPE uplift so the board's Net NPV reflects the kind of job, not just its
# cost (the old flat +100 made every AFE's NPV pure inverse-cost). The real
# per-well uplift still lives in each well's diagnosis on the Draft AFE page.
TYPICAL_UPLIFT_BOPD = {
    "acid_stimulation": 80.0,
    "scale_treatment": 60.0,
    "esp_swap": 150.0,
    "esp_to_beam_conversion": 40.0,
    "rod_pump_workover": 50.0,
    "gas_lift_optimization": 70.0,
    "paraffin_treatment": 30.0,
}

pt.masthead("capital", "Pipeline Board",
            "Every in-flight AFE — status, dollars, required authority, audit trail.")
pt.context_bar([
    ("Deck", f"${OIL:.0f}/bbl · NRI {NRI:.0%} · {DISC:.1%} disc"),
    ("Data", "Demo tracker (SQLite, product-local)"),
    ("Scope", "In-flight + approved AFEs (not yet executed)"),
])
common.page_purpose(
    "**What this page answers:** where does every in-flight AFE stand, whose "
    "sign-off does it still need, and where is it stuck?\n\n"
    "**Use it to run the AFE review:** the board ranks the slate (Net NPV is a "
    "type-typical ranking basis), the authority ladder shows the $-routed "
    "sign-off tiers, and the **AFE Detail** panel below shows one AFE's full "
    "journey — a stepper of every stage, days-in-status, and exactly what's "
    "remaining to get it approved. Advancing an AFE to *executed* sends its "
    "actuals to the Variance page.")


@st.cache_data(show_spinner=False)
def _pipeline(_token: int) -> pd.DataFrame:
    return core.pipeline_df()


@st.cache_data(show_spinner=False)
def _events(afe_number: str, _token: int) -> pd.DataFrame:
    return core.get_tracker().events(afe_number)


def _net_npv(row) -> float | None:
    """Deterministic net-NPV ranking column at the GLOBAL deck, using a TYPE-typical
    first-year uplift per intervention (so the ranking reflects the kind of job, not
    just its cost). Severance from the deck is applied for consistency with the
    Draft AFE page. P&A is cost-only: no production economics."""
    intervention = row["intervention"]
    uplift = TYPICAL_UPLIFT_BOPD.get(intervention)
    if uplift is None or intervention not in core.afe_cost_db.COST_TEMPLATES:
        return None
    e = core.draft_economics(float(row["total_cost_usd"]), uplift,
                             realized_price_per_bbl=OIL,
                             net_revenue_interest=NRI, discount_rate=DISC)
    return float(common.net_npv_gross_wellhead_severance(
        e.net_npv_10pct_usd, e.net_cost_to_operator_usd, OIL, SEV))


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
           "One row per in-flight AFE. Net NPV uses a TYPE-typical first-year uplift "
           "per intervention (an ESP swap is credited more than a paraffin treatment) "
           "— a ranking basis, not a per-well forecast; the real uplift lives in each "
           "well's diagnosis on Draft AFE. Closed-out actual-vs-AFE variance lives on "
           "the Variance page.")
rows = []
for _, r in df.iterrows():
    try:
        net_npv = _net_npv(r)
    except Exception:  # noqa: BLE001 — ranking column must never take down the board
        net_npv = None
    rows.append({
        "AFE #": r["afe_number"],
        "Well": r["well_id"],
        "Intervention": str(r["intervention"]).replace("_", " "),
        "Gross Cost $": float(r["total_cost_usd"]),
        "Net NPV (type-typical) $": net_npv,
        "Status": str(r["status"]).replace("_", " "),
        "Required Approver": r["required_approver"],
        "Days in Status": int(r["days_in_status"]),
        "Bottleneck": r["bottleneck_risk"],
    })
board = pd.DataFrame(rows)
st.dataframe(
    board, width="stretch", hide_index=True,
    column_config={
        "Gross Cost $": st.column_config.NumberColumn(format="$%,.0f"),
        "Net NPV (type-typical) $": st.column_config.NumberColumn(
            format="$%,.0f",
            help="Net NPV at the deck using a TYPE-typical first-year uplift per "
                 "intervention (ESP swap 150 bopd, scale 60, paraffin 30, …) less "
                 "severance — a ranking basis, not each well's real upside. "
                 "Blank = P&A or an intervention with no production economics."),
    })
st.download_button("Download pipeline (CSV)", data=board.to_csv(index=False),
                   file_name="afe_pipeline.csv", mime="text/csv")
theme.source_note(
    "Tracker rows from the product-local SQLite store; 'Net NPV (type-typical)' "
    "values each AFE at the global deck using a per-intervention typical first-year "
    "uplift less severance — it ranks the slate by economic merit, not each well's "
    "real forecast. For actual-vs-AFE overruns and the supplemental-AFE policy, see "
    "the Variance page.")

pt.section("Authority Routing",
           "Delegation-of-authority: the sign-off level each AFE's dollar value requires.")
ladder = pd.DataFrame(
    [{"Limit": ("Above $1,000,000" if limit == float("inf")
                else f"Up to ${limit:,.0f}"), "Approver": role,
      "AFEs at This Tier": int((df["required_approver"] == role).sum())}
     for limit, role in core.afe_tracker.AUTHORITY_LIMITS])
st.dataframe(ladder, width="stretch", hide_index=True)

pt.section("AFE Detail — Journey, What's Remaining, Audit Trail",
           "Pick an AFE to see its full status journey, exactly what's still needed "
           "to get it approved, and its immutable event log — then advance it from "
           "here. Executing an AFE generates closed-out actuals on the Variance "
           "page, closing the detect → authorize → reconcile loop in-product.")
order = list(core.afe_tracker.STATUS_ORDER)
sel = st.selectbox("AFE", sorted(df["afe_number"]), key="board_afe")
row = df[df["afe_number"] == sel].iloc[0]
cur = str(row["status"])
approver = str(row["required_approver"])
days_in = int(row["days_in_status"])

# --- status stepper: the tracker's REAL machine (draft → … → executed; 'rejected'
# is a terminal off-path branch — never an invented stage) --------------------------
chips = []
for stage, state in afe_status.stage_states(cur, order):
    label = stage.replace("_", " ")
    if state == afe_status.CURRENT:
        chips.append(pt.pill(f"{label} · {days_in}d in status", "info"))
    elif state == afe_status.DONE:
        chips.append(pt.pill(f"✓ {label}", "ok"))
    else:
        chips.append(pt.pill(label, "muted"))
stepper = " → ".join(chips)
if not afe_status.is_on_path(cur, order):
    stepper += " &nbsp; " + pt.pill(f"{cur.replace('_', ' ')} — terminal", "bad")
st.markdown(stepper, unsafe_allow_html=True)
st.markdown(f"**What's remaining:** {afe_status.whats_remaining(cur, approver)}",
            unsafe_allow_html=True)
st.caption(f"{sel} · {row['well_id']} · {str(row['intervention']).replace('_', ' ')} "
           f"· ${row['total_cost_usd']:,.0f} routes to **{approver}** · open "
           f"{int(row['days_open'])}d total · bottleneck risk {row['bottleneck_risk']}.")

ev = _events(sel, token)
durations = afe_status.stage_durations(ev)
if durations:
    bits = []
    for stage, d in durations.items():
        sla = core.afe_tracker.STAGE_SLA_DAYS.get(stage)
        bits.append(f"{stage.replace('_', ' ')}: {d:.1f}d"
                    + (f" (SLA {sla}d)" if sla else ""))
    st.caption("Realized days per completed stage — " + " · ".join(bits))
else:
    st.caption("No completed stages logged yet — realized per-stage days (vs. the "
               "stage SLAs) appear once this AFE advances.")

lc1, lc2 = st.columns([1, 2])
if cur == "executed":
    lc1.success("Executed")
    live = sel in ss.get("live_actuals", {})
    lc2.caption("Executed this session — its actuals are on the Variance page."
                if live else "Already executed (pre-seeded). The Variance page shows a "
                "separate set of closed-out actuals; execute an in-flight AFE here to "
                "add it there.")
elif cur not in order:
    # terminal / non-advanceable status the lifecycle doesn't model (e.g. 'rejected',
    # 'cancelled') — STATUS_ORDER only covers the draft→executed path, so guard the
    # index lookup instead of letting it raise on the render path.
    lc1.warning(cur.replace("_", " ").title())
    lc2.caption(f"This AFE is **{cur.replace('_', ' ')}** — not on the active "
                "review→execution path, so there's nothing to advance.")
else:
    nxt = order[min(order.index(cur) + 1, len(order) - 1)]
    if lc1.button(f"Advance → {nxt.replace('_', ' ')}"):
        try:
            tracker = core.get_tracker()
            tracker.advance(sel, nxt, note="Advanced via Pipeline Board")
            if nxt == "executed":
                ss.setdefault("live_actuals", {})
                ss["live_actuals"][sel] = common.generate_afe_actuals(
                    sel, str(row["intervention"]))
            ss["_afe_cache_token"] = ss.get("_afe_cache_token", 0) + 1
            st.rerun()
        except Exception as exc:  # noqa: BLE001 — surface, never crash the board
            st.error(f"Could not advance: {type(exc).__name__}: {exc}")
    lc2.caption(f"Current status: **{cur.replace('_', ' ')}** → next: "
                f"**{nxt.replace('_', ' ')}**.")
if ss.get("live_actuals"):
    st.caption("Executed this session (now on the Variance page): "
               + ", ".join(sorted(ss["live_actuals"])))

st.markdown("**Audit trail** — immutable status-change log, appended, never "
            "overwritten:")
if ev.empty:
    st.caption("No status-change events recorded for this AFE.")
else:
    st.dataframe(ev[["ts", "from_status", "to_status", "actor", "note"]],
                 width="stretch", hide_index=True)
    st.caption("Every transition is appended to the event log — the audit shape an "
               "internal-audit / SOX reviewer expects of a capital tracker.")

theme.references(["npv"])
