"""Draft AFE — diagnosis in, decision-ready AFE out.

Manual inputs or a WellDiagnosis JSON (chained from the Production Engineer
Copilot) become a costed AFE: benchmark cost rollup with the tangible/intangible
(IDC) split, WI/NRI net economics at the global deck, Monte-Carlo P10/50/90 with
a tornado, and a markdown + .docx download. Every number is deterministic — the
LLM narrative alone is BYOK-optional (key in the sidebar).
"""
from __future__ import annotations

import datetime as _dt
import json
import tempfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import core
import product_theme as pt
import theme

ss = st.session_state
OIL = float(ss.get("oil_price", 70.0))
NRI = float(ss.get("nri", 0.80))
DISC = float(ss.get("discount", 0.10))

pt.masthead("capital", "Draft AFE",
            "Turn a well diagnosis into a costed, routed, economics-backed AFE.")
pt.context_bar([
    ("Deck", f"${OIL:.0f}/bbl · NRI {NRI:.0%} · {DISC:.1%} disc"),
    ("Data", "Benchmark cost templates (synthetic Permian)"),
    ("Narrative", "BYOK-optional — all numbers keyless"),
])

# ---- diagnosis input --------------------------------------------------------
pt.section("Diagnosis", "Load an example, upload a WellDiagnosis JSON, or type it in.")

sample_files = sorted(core.EXAMPLES_DIR.glob("well_diagnosis*.json"))
c_src1, c_src2 = st.columns(2)
with c_src1:
    chosen = st.selectbox("Example diagnosis",
                          ["(manual)"] + [p.name for p in sample_files])
with c_src2:
    up = st.file_uploader("WellDiagnosis JSON (from PE Copilot)", type=["json"],
                          help="Validated before it can become an AFE — bad fields "
                               "are reported in plain English.")

preset: dict = {}
if up is not None:
    try:
        payload = json.loads(up.getvalue().decode("utf-8"))
        diag_ok = core.afe_models.AFEDiagnosis.from_pe_copilot(payload)
        preset = {k: getattr(diag_ok, k) for k in (
            "well_id", "api_number", "field", "operator", "intervention",
            "primary_diagnosis", "incremental_rate_bopd",
            "expected_uplift_decline_per_yr", "requested_by")}
        st.success(f"Validated diagnosis for {diag_ok.well_id} ({diag_ok.intervention}).")
    except (ValueError, json.JSONDecodeError) as exc:
        st.error(f"Diagnosis rejected: {exc}")
        st.stop()
elif chosen != "(manual)":
    preset = json.loads((core.EXAMPLES_DIR / chosen).read_text())
elif ss.get("diag_preset"):
    preset = ss["diag_preset"]          # loaded on the Data page

interventions = list(core.afe_cost_db.COST_TEMPLATES)
f1, f2, f3 = st.columns(3)
well_id = f1.text_input("Well ID", value=preset.get("well_id", "ED-001H"))
api = f2.text_input("API #", value=preset.get("api_number", "42-109-12345"))
field = f3.text_input("Field", value=preset.get("field", "Delaware Basin"))
f4, f5, f6 = st.columns(3)
operator = f4.text_input("Operator", value=preset.get("operator", "Operator LLC"))
intervention = f5.selectbox(
    "Intervention", interventions,
    index=(interventions.index(preset["intervention"])
           if preset.get("intervention") in interventions else 0))
requested_by = f6.text_input("Requested by",
                             value=preset.get("requested_by", "Eric Diaz, Staff PE"))
diagnosis_text = st.text_area(
    "Primary diagnosis", height=90,
    value=preset.get("primary_diagnosis",
                     "Scale signature with declining intake pressure; treatment "
                     "required before mechanical work."))
g1, g2, g3 = st.columns(3)
rate = g1.number_input("Incremental uplift (BOPD)", 1.0, 5000.0,
                       float(preset.get("incremental_rate_bopd", 100.0)), 5.0)
decline = g2.number_input("Uplift decline (1/yr)", 0.05, 1.95,
                          float(preset.get("expected_uplift_decline_per_yr", 0.6)), 0.05)
wi = g3.number_input("Working interest (WI)", 0.0, 1.0, 1.0, 0.05,
                     help="Operator's share of COST. Revenue share (NRI) and price "
                          "come from the global deck in the sidebar.")

# ---- cost rollup ------------------------------------------------------------
pt.section("Cost Rollup", "Benchmark template with the tangible / intangible (IDC) split.")
rollup = core.afe_cost_db.cost_rollup(intervention)
pt.kpi_row([
    {"label": "AFE Total (Gross)", "value": f"${rollup['total']:,.0f}"},
    {"label": "Tangible (Capitalized)", "value": f"${rollup['tangible']:,.0f}"},
    {"label": "Intangible (IDC)", "value": f"${rollup['intangible']:,.0f}"},
    {"label": "Routes To", "value": core.afe_tracker.required_approver(rollup["total"])},
])

items = core.afe_cost_db.lookup_cost_template(intervention)
direct = [li for li in items if li.category != "Contingency"]
contingency = sum(li.total_usd for li in items if li.category == "Contingency")
wf = go.Figure(go.Waterfall(
    orientation="v",
    measure=["relative"] * (len(direct) + 1) + ["total"],
    x=[li.category for li in direct] + ["Contingency", "Total AFE"],
    y=[li.total_usd for li in direct] + [contingency, 0],
    text=[f"${li.total_usd:,.0f}" for li in direct]
         + [f"${contingency:,.0f}", f"${rollup['total']:,.0f}"],
    textposition="outside",
    connector={"line": {"color": theme.GRID}},
    increasing={"marker": {"color": theme.BLUE}},
    decreasing={"marker": {"color": theme.RED}},
    totals={"marker": {"color": theme.NAVY}},
    hovertemplate="%{x}: $%{y:,.0f}<extra></extra>"))
wf.update_layout(yaxis_title="USD")
st.plotly_chart(theme.style_fig(wf, height=340, legend=False), width="stretch")
theme.source_note("Benchmark cost template for the selected intervention; bars in "
                  "USD building direct line items → contingency → total AFE.")
with st.expander("Line-Item Detail"):
    st.dataframe(pd.DataFrame(
        [{"Category": x.category, "Description": x.description, "Qty": x.qty,
          "Unit": x.unit, "Unit Cost $": x.unit_cost_usd, "Total $": x.total_usd,
          "Vendor": x.vendor or "TBD", "Class": x.cost_class} for x in items]),
        width="stretch", hide_index=True,
        column_config={"Unit Cost $": st.column_config.NumberColumn(format="$%,.0f"),
                       "Total $": st.column_config.NumberColumn(format="$%,.0f")})

# ---- net economics at the deck -----------------------------------------------
pt.section("Net Economics",
           f"WI {wi:.0%} of cost · NRI {NRI:.0%} of revenue · ${OIL:.0f}/bbl · "
           f"{DISC:.1%} effective-annual discount.")
if intervention == "p_and_a":
    pt.empty_state("P&A is a cost-only job — production economics do not apply.",
                   "Justified against remaining liability, plugging-bond release, "
                   "and avoided idle-well carrying cost.")
    econ = None
else:
    econ = core.draft_economics(rollup["total"], rate, uplift_decline_per_yr=decline,
                                realized_price_per_bbl=OIL, working_interest=wi,
                                net_revenue_interest=NRI, discount_rate=DISC)
    pt.kpi_row([
        {"label": "Gross NPV", "value": f"${econ.npv_10pct_usd/1e6:,.2f}MM"},
        {"label": "Net NPV to Operator", "value": f"${econ.net_npv_10pct_usd/1e6:,.2f}MM",
         "help": "WI% of cost, NRI% of revenue — what the operator actually books."},
        {"label": "Payout", "value": ("—" if econ.payout_months == float("inf")
                                      else f"{econ.payout_months:.0f} mo")},
        {"label": "First-Year Add", "value": f"{econ.incremental_first_year_bbl:,.0f} bbl"},
    ])
    deck_rows = core.afe_economics.price_sensitivity(
        rollup["total"], rate, uplift_decline_per_yr=decline,
        working_interest=wi, net_revenue_interest=NRI, discount_rate=DISC)
    deck_df = pd.DataFrame(deck_rows)
    deck_df = pd.DataFrame({
        "Realized $/bbl": deck_df["realized_price"].map(lambda v: f"${v:,.0f}"),
        "Gross NPV": deck_df["npv_usd"].map(lambda v: f"${v/1e6:,.2f}MM"),
        "Net NPV": deck_df["net_npv_usd"].map(lambda v: f"${v/1e6:,.2f}MM"),
        "Payout (mo)": deck_df["payout_months"].map(
            lambda v: f"{v:.0f}" if v != float("inf") else "—")})
    st.dataframe(deck_df, width="stretch", hide_index=True)
    theme.source_note("Price-deck sensitivity: NPV at a fixed uplift across a "
                      "realized-price strip, WI/NRI and discount held at the deck.")

# ---- Monte-Carlo --------------------------------------------------------------
pt.section("Probabilistic Economics",
           "10,000 trials over uplift (±30%), decline (±0.15 abs), and price (~$12 sd).")
if intervention == "p_and_a":
    st.caption("Not applicable to a cost-only job.")
elif st.button("Run Monte-Carlo NPV"):
    mc = core.afe_economics.simulate_economics(
        treatment_cost_usd=rollup["total"], incremental_rate_bopd=rate,
        uplift_decline_per_yr=decline, realized_price_per_bbl=OIL,
        discount_rate=DISC)
    pt.kpi_row([
        {"label": "P10 NPV (Downside)", "value": f"${mc.npv_p10_usd/1e6:,.2f}MM"},
        {"label": "P50 NPV (Median)", "value": f"${mc.npv_p50_usd/1e6:,.2f}MM"},
        {"label": "P90 NPV (Upside)", "value": f"${mc.npv_p90_usd/1e6:,.2f}MM"},
        {"label": "P(Payout < 24 mo)", "value": f"{mc.probability_of_payout*100:.0f}%"},
    ])
    items_t = sorted(mc.tornado.items(), key=lambda kv: kv[1]["swing"])
    labels = [k.replace("_", " ") for k, _ in items_t]
    lows = [v["low"] for _, v in items_t]
    highs = [v["high"] for _, v in items_t]
    base = mc.base_npv_usd
    tor = go.Figure()
    tor.add_trace(go.Bar(y=labels, x=[base - lo for lo in lows], base=lows,
                         orientation="h", name="downside", marker_color=theme.RED,
                         hovertemplate="low NPV: $%{base:,.0f}<extra></extra>"))
    tor.add_trace(go.Bar(y=labels, x=[hi - base for hi in highs], base=base,
                         orientation="h", name="upside", marker_color=theme.BLUE,
                         hovertemplate="high NPV: $%{x:,.0f}<extra></extra>"))
    tor.add_vline(x=base, line_dash="dash", line_color=theme.NAVY,
                  annotation_text=f"base ${base/1e6:,.2f}MM")
    tor.update_layout(barmode="overlay", xaxis_title="NPV (USD)")
    st.plotly_chart(theme.style_fig(tor, height=300), width="stretch")
    theme.source_note("Tornado: NPV (USD) swing as each variable moves over its "
                      "sampled range; dashed line is the base case.")

# ---- AFE document --------------------------------------------------------------
pt.section("AFE Document",
           "Deterministic markdown + Word export — keyless. Add a key in the "
           "sidebar for the LLM-written narrative.")
diag_dict = {
    "well_id": well_id, "api_number": api, "field": field, "operator": operator,
    "intervention": intervention, "primary_diagnosis": diagnosis_text,
    "incremental_rate_bopd": float(rate),
    "expected_uplift_decline_per_yr": float(decline),
    "requested_by": requested_by,
}
if st.button("Generate AFE", type="primary"):
    problems = core.afe_models.AFEDiagnosis(**diag_dict).validate()
    if problems:
        st.error("Fix the diagnosis first: " + " · ".join(problems))
    else:
        byok = (ss.get("anthropic_key") or "").strip()
        markdown = None
        if byok:
            try:
                with st.spinner("Drafting the LLM narrative (your key)…"):
                    markdown = core.afe_drafter.run_drafter(
                        core.afe_models.AFEDiagnosis(**diag_dict), api_key=byok)
            except Exception as exc:  # noqa: BLE001 — bad key/limits → deterministic path
                st.warning("LLM narrative unavailable "
                           f"({type(exc).__name__}) — rendering the deterministic AFE.")
        if markdown is None:
            markdown = core.afe_markdown(diag_dict, working_interest=wi,
                                         net_revenue_interest=NRI, realized_price=OIL)
        ss["_afe_markdown"] = markdown
        ss["_afe_pending"] = {"well_id": well_id, "intervention": intervention,
                              "total_cost_usd": rollup["total"],
                              "requested_by": requested_by}

if ss.get("_afe_markdown"):
    with st.expander("AFE Preview", expanded=True):
        st.markdown(ss["_afe_markdown"])
    d1, d2, d3 = st.columns(3)
    d1.download_button("Download .md", ss["_afe_markdown"],
                       file_name=f"AFE_{well_id}_{intervention}.md")
    try:
        with tempfile.TemporaryDirectory() as td:
            p = core.afe_docx_builder.build_docx(
                ss["_afe_markdown"], Path(td) / "afe.docx",
                core.afe_models.AFEDiagnosis(**diag_dict))
            docx_bytes = p.read_bytes()
        d2.download_button(
            "Download .docx", docx_bytes,
            file_name=f"AFE_{well_id}_{intervention}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    except Exception as exc:  # noqa: BLE001 — docx must never block the markdown
        d2.caption(f"docx unavailable: {type(exc).__name__}")
    pending = ss.get("_afe_pending") or {}
    if d3.button("Submit to Pipeline"):
        tracker = core.get_tracker()
        existing = core.pipeline_df()
        next_num = max((int(str(n).split("-")[-1]) for n in existing.get("afe_number", [])
                        if str(n).startswith("AFE-")), default=53) + 1
        afe_no = f"AFE-{_dt.date.today().year}-{next_num:04d}"
        today = _dt.date.today().isoformat()
        tracker.upsert(core.afe_tracker.AFERecord(
            afe_number=afe_no, well_id=pending.get("well_id", well_id),
            intervention=pending.get("intervention", intervention),
            total_cost_usd=float(pending.get("total_cost_usd", rollup["total"])),
            status="draft", created_date=today, last_updated=today,
            requested_by=pending.get("requested_by", requested_by),
            notes="Submitted via Draft AFE"))
        ss["_afe_cache_token"] = ss.get("_afe_cache_token", 0) + 1
        st.success(f"{afe_no} added to the pipeline as draft — see the Pipeline Board.")

theme.references(["npv", "monte_carlo"])
