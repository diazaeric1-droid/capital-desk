"""Regulatory Filing — draft worksheets for two common upstream filings from data
the product already holds (the roadmapped 4th module).

* CO ECMC Form 7 (Monthly Production) from a well-month of the PDP production data.
* TX RRC Form W-3 (Plugging Record) from a P&A AFE in the pipeline.

Deterministic field-mapping; the optional LLM (BYOK) writes a cover note only.
Honest: these are review worksheets, not certified e-file payloads.
"""
from __future__ import annotations

import datetime as _dt

import pandas as pd
import streamlit as st

import core
import fleet_registry
import product_theme as pt
import theme
from src import regulatory
from views import common

OIL, NRI, DISC, DECK = common.deck()
ss = st.session_state

pt.masthead("capital", "Regulatory Filing",
            "Draft Form 7 (CO production) and W-3 (TX plugging) worksheets from your data.")
pt.context_bar([("Deck", DECK),
                ("Scope", "Draft worksheets — review before filing"),
                ("Forms", "CO ECMC Form 7 · TX RRC Form W-3")])

st.warning("These are **draft field-mapping worksheets**, not certified filings. "
           "Field names track the public forms; reconcile against the current "
           "official form revision and your system of record before submitting.")

form_choice = st.radio(
    "Filing", ["CO ECMC Form 7 — Monthly Production", "TX RRC Form W-3 — Plugging Record"],
    horizontal=True)


def _llm_cover_note(draft: regulatory.FilingDraft) -> None:
    """Optional BYOK cover note; deterministic worksheet stands alone without a key."""
    if st.button("Draft a cover note (LLM, optional)"):
        key = (ss.get("anthropic_key") or "").strip()
        if not key:
            st.info("Add an Anthropic key in the sidebar for the narrated cover note — "
                    "the worksheet above is complete without it.")
            return
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=key)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=400,
                messages=[{"role": "user", "content":
                           "Write a 3-sentence professional cover note for this "
                           "regulatory filing worksheet. Be precise and conservative; "
                           "do not invent values.\n\n" + draft.to_markdown()}])
            st.markdown("".join(b.text for b in msg.content if hasattr(b, "text")))
        except Exception as exc:  # noqa: BLE001 — never block on the LLM
            st.warning(f"Cover note unavailable ({type(exc).__name__}).")


def _render(draft: regulatory.FilingDraft) -> None:
    pt.section(draft.title, f"{draft.form} · {draft.jurisdiction}")
    st.dataframe(pd.DataFrame(draft.fields, columns=["Field", "Value"]),
                 width="stretch", hide_index=True)
    if draft.notes:
        st.caption("  •  ".join(draft.notes))
    st.download_button("Download worksheet (Markdown)", data=draft.to_markdown(),
                       file_name=f"{draft.form.replace(' ', '_')}_{_dt.date.today()}.md",
                       mime="text/markdown")
    _llm_cover_note(draft)


# ---------------------------------------------------------------------------
if form_choice.startswith("CO"):
    src_choice = st.radio("Production source",
                          [common.PDP_SYNTH_LABEL, common.PDP_REAL_LABEL],
                          horizontal=True)
    csv_text, source_label, _ = common.resolve_pdp(src_choice)
    tidy = common.pdp_tidy(csv_text)
    wells = sorted(tidy["well_id"].unique())
    c1, c2 = st.columns(2)
    well = c1.selectbox("Well", wells)
    g = tidy[tidy["well_id"] == well].copy()
    months = [str(p) for p in g["_period"]]
    month = c2.selectbox("Reporting month", months[::-1])   # most-recent first
    row = g[g["_period"].astype(str) == month].iloc[0]

    # identity: real data carries operator/well_name/field/formation; synthetic
    # wells fall back to the shared fleet registry.
    meta = fleet_registry.get(str(well)) if str(well).startswith("well_") else None
    def _col(name, default=""):
        return str(row[name]) if name in g.columns and pd.notna(row.get(name)) else default
    draft = regulatory.co_form7_production(
        month=month,
        operator=_col("operator", "Demo Operator LLC (synthetic)" if meta else "—"),
        well_name=_col("well_name", meta.name if meta else str(well)),
        api=_col("api", meta.api14 if meta else str(well)),
        field_name=_col("field", meta.area if meta else "—"),
        formation=_col("formation", meta.formation if meta else ""),
        oil_bbl=row.get("oil_bbl"),
        gas_mcf=row.get("gas_mcf", 0.0),
        water_bbl=row.get("water_bbl", 0.0),
        days=row.get("days"))
    _render(draft)

else:
    df = core.pipeline_df()
    pa = df[df["intervention"] == "p_and_a"]
    if pa.empty:
        pt.empty_state("No P&A AFE in the pipeline.",
                       "Draft a plug-and-abandon AFE on the Draft AFE page first, then "
                       "return here to map it onto Form W-3.")
        st.stop()
    afe_no = st.selectbox("P&A AFE", sorted(pa["afe_number"]))
    r = pa[pa["afe_number"] == afe_no].iloc[0]
    well = str(r["well_id"])
    meta = fleet_registry.get(well) if well.startswith("well_") else None
    last = str(r.get("last_updated") or _dt.date.today())
    draft = regulatory.tx_w3_plugging(
        afe_number=afe_no, well_id=well,
        api=(meta.api14 if meta else "—"),
        operator="Demo Operator LLC",
        field_name=(meta.area if meta else "—"),
        estimated_cost_usd=float(r["total_cost_usd"]),
        plug_date=last,
        total_depth_ft=(meta.lateral_length_ft if meta else None))
    _render(draft)

theme.references(["npv"])
