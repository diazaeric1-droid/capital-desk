"""Sources & BYOD — every dataset in the product, its provenance, and the three
bring-your-own-data contracts (WellDiagnosis JSON, backlog CSV, PDP monthly CSV).

Nothing is stored server-side: uploads are parsed in memory for this session only.
"""
from __future__ import annotations

import io
import json

import streamlit as st

import core
import product_theme as pt
import theme
from src import pdp
from views import common

OIL, NRI, DISC, DECK = common.deck()
ss = st.session_state

pt.masthead("capital", "Sources & BYOD",
            "What's real, what's synthetic, and how to bring your own data.")
_backlog_lbl = (common.BACKLOG_BYOD_LABEL if ss.get("backlog_csv_text")
                else common.BACKLOG_COLO_LABEL if ss.get("backlog_source") == "colorado"
                else common.BACKLOG_DEMO_LABEL)
_prod_lbl = common.PDP_BYOD_LABEL if ss.get("pdp_csv_text") else common.PDP_SYNTH_LABEL
pt.context_bar([
    ("Deck", DECK),
    ("Backlog", _backlog_lbl),
    ("Production", _prod_lbl),
])
st.caption(f"Component engines: AFE Copilot **v{core.AFE_VERSION}** · Capital "
           f"Optimizer **v{core.CAPITAL_VERSION}** · PDP Screener + Regulatory "
           "(product-native). The product version is in the page header.")

# ---- provenance -----------------------------------------------------------------
pt.section("Provenance", "Every number traces to one of these four sources.")

st.markdown("**1 · Synthetic 100-well Permian fleet — Screen default** "
            + pt.pill("synthetic, suite-shared", "warn"), unsafe_allow_html=True)
theme.data_badge("synthetic", "Modeled monthly oil — future deals / private "
                              "production aren't public data.")
st.markdown(
    "- The **same 100 well identities** (`well_001`…`well_100`) the other two "
    "operator products use — same basin / area / formation / lift / lateral from "
    "the shared `fleet_registry` — rendered as **monthly oil** for the PDP "
    "decline screen (the sibling apps express the fleet as daily SCADA).\n"
    "- Per-well Arps decline drawn off a deterministic seed (qi scaled by lateral "
    "and lift), staggered first-production months → a realistic maturity + PV10 "
    "spread, not 100 identical wells.\n"
    "- Committed at `data/synthetic/fleet_pdp.csv`; its generator "
    "(`generate_fleet_pdp.py`) sits beside it and reruns byte-identical.")

st.markdown("**2 · Colorado ECMC monthly production — Screen (real option)** "
            + pt.pill("REAL public data", "ok"), unsafe_allow_html=True)
theme.data_badge("real", "Colorado ECMC (formerly COGCC) public records — "
                         "redistributable under the Colorado Open Records Act.")
st.markdown(
    "- 28 DJ Basin horizontal wells (Weld County, Niobrara / Codell), ~2,000 "
    "well-months spanning 2017–2026, 17 operators.\n"
    "- Per-well, per-month oil / gas / water + producing days — genuine "
    "public-record production, not synthetic.\n"
    "- Reproducible: `data/real/colorado/fetch_colorado.py` harvests it from two "
    "free ECMC endpoints (see the README beside it).")

st.markdown("**3 · Synthetic 45-project capital backlog — used by Program** "
            + pt.pill("synthetic, defensible ranges", "warn"), unsafe_allow_html=True)
theme.data_badge("synthetic", "Modeled drilling / DUC / workover backlog — future "
                              "capital projects aren't public data.")
st.markdown(
    "- 45 projects with type-curve, capex, opex, Pc, and rig-day ranges "
    "order-of-magnitude consistent with public Permian figures.\n"
    "- Deliberately includes a sub-economic tail (13 of 45 at the $70 deck) and "
    "lumpy capex, so the optimizer's constraints genuinely bind.\n"
    "- Committed at `apps/capital-optimizer/data/synthetic/projects.csv`; its "
    "generator sits beside it.")

st.markdown("**4 · AFE tracker + cost templates — used by Authorize** "
            + pt.pill("synthetic, demo-seeded", "warn"), unsafe_allow_html=True)
theme.data_badge("synthetic", "Benchmark cost templates + a demo-seeded pipeline — "
                              "operator cost and authority data is never public.")
st.markdown(
    "- 12 demo AFEs seeded into a product-local SQLite tracker on first run "
    "(gitignored under `data/state/`; your drafted AFEs persist locally).\n"
    "- Cost templates are synthetic Permian benchmarks with a programmatic "
    "contingency line and a tangible / intangible (IDC) split.")

st.divider()

# ---- BYOD ------------------------------------------------------------------------
pt.section("Bring Your Own Data",
           "Three contracts. Uploads are validated, parsed in memory, and never "
           "stored server-side.")

# 1) WellDiagnosis JSON
st.markdown("**WellDiagnosis JSON → Draft AFE**")
st.caption("Schema: `well_id, api_number, field, operator, intervention, "
           "primary_diagnosis, incremental_rate_bopd[, "
           "expected_uplift_decline_per_yr, requested_by]` — the export the "
           "Production Engineer Copilot produces.")
example = (core.EXAMPLES_DIR / "well_diagnosis_001.json").read_text()
st.download_button("Download example diagnosis (JSON)", data=example,
                   file_name="well_diagnosis_example.json", mime="application/json")
diag_up = st.file_uploader("WellDiagnosis JSON", type=["json"], key="data_diag_upload")
if diag_up is not None:
    try:
        payload = json.loads(diag_up.getvalue().decode("utf-8"))
        diag = core.afe_models.AFEDiagnosis.from_pe_copilot(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        st.error(f"Diagnosis rejected: {exc}")
        st.stop()
    ss["diag_preset"] = {k: getattr(diag, k) for k in (
        "well_id", "api_number", "field", "operator", "intervention",
        "primary_diagnosis", "incremental_rate_bopd",
        "expected_uplift_decline_per_yr", "requested_by")}
    st.success(f"Validated {diag.well_id} ({diag.intervention}) — preloaded into "
               "the Draft AFE page.")

# 2) Backlog CSV
st.markdown("**Backlog CSV → Program**")
st.caption("Required columns: "
           + ", ".join(f"`{c}`" for c in core.capital_projects.REQUIRED_CSV_COLUMNS))
st.download_button("Download backlog template (CSV)", data=common.BACKLOG_TEMPLATE,
                   file_name="backlog_template.csv", mime="text/csv")
bl_up = st.file_uploader("Backlog CSV", type=["csv"], key="data_backlog_upload")
if bl_up is not None:
    text = bl_up.getvalue().decode("utf-8", errors="replace")
    try:
        projects = common.parse_backlog(text)
    except ValueError as exc:
        st.error(f"Could not load backlog: {exc}")
        st.stop()
    ss["backlog_csv_text"] = text
    st.success(f"Loaded {len(projects)} projects — the Program pages now run on "
               "your backlog.")

# 3) PDP monthly CSV
st.markdown("**PDP monthly CSV → Screen**")
st.caption("Required columns: `well_id`, `month` (YYYY-MM), `oil_bbl`; optional "
           "`days`. One row per well per month.")
st.download_button("Download PDP template (CSV)", data=pdp.template_csv(),
                   file_name="pdp_monthly_template.csv", mime="text/csv")
pdp_up = st.file_uploader("Monthly production CSV", type=["csv"], key="data_pdp_upload")
if pdp_up is not None:
    text = pdp_up.getvalue().decode("utf-8", errors="replace")
    try:
        tidy = pdp.load_pdp_csv(io.StringIO(text))
    except ValueError as exc:
        st.error(f"Could not load production CSV: {exc}")
        st.stop()
    ss["pdp_csv_text"] = text
    st.success(f"Loaded {tidy['well_id'].nunique()} wells / {len(tidy)} well-months "
               "— select the uploaded source on the PDP Screener page.")

active = []
if ss.get("backlog_csv_text"):
    active.append("backlog (BYOD)")
if ss.get("pdp_csv_text"):
    active.append("PDP production (BYOD)")
if ss.get("diag_preset"):
    active.append("diagnosis (BYOD)")
if active:
    if st.button("Clear all uploaded data"):
        for k in ("backlog_csv_text", "pdp_csv_text", "diag_preset"):
            ss.pop(k, None)
        st.rerun()
    st.caption("Active this session: " + ", ".join(active) + ".")

st.caption("Nothing is stored server-side — uploads live in this session's memory "
           "and disappear when it ends.")

theme.references(["arps", "prms", "npv", "milp"])
