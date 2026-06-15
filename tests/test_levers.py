"""Coverage for the v0.3.0 levers: the Regulatory module, the Colorado-derived
refrac backlog, and the program-level Monte-Carlo."""
from __future__ import annotations

import io

from src import regulatory
from views import common


def test_regulatory_form7_maps_production():
    d = regulatory.co_form7_production(
        month="2025-06", operator="Op LLC", well_name="W1", api="42-000-00001",
        field_name="DJ", oil_bbl=9000, gas_mcf=12000, water_bbl=3000, days=30,
        formation="Codell")
    labels = [l for l, _ in d.fields]
    assert d.form == "CO ECMC Form 7" and d.jurisdiction == "Colorado ECMC"
    assert {"Oil produced (bbl)", "Gas produced (mcf)", "Water produced (bbl)"} <= set(labels)
    assert "| Field | Value |" in d.to_markdown()


def test_regulatory_w3_maps_plugging():
    d = regulatory.tx_w3_plugging(
        afe_number="AFE-2026-0050", well_id="well_050", api="42-329-30050",
        operator="Op LLC", field_name="Midland Co., TX", estimated_cost_usd=238000,
        plug_date="2026-01-01", total_depth_ft=9800)
    labels = [l for l, _ in d.fields]
    assert d.form == "TX RRC Form W-3"
    assert "Cement plugs (schedule)" in labels
    assert "$238,000" in dict(d.fields)["Estimated plugging cost"]


def test_colorado_refrac_backlog_valid_and_binds(booted):
    core = booted
    txt = common.colorado_workover_csv()
    projs = core.capital_projects.projects_from_csv(io.StringIO(txt))
    assert len(projs) >= 20                                  # ~28 fit-able CO wells
    econ = core.capital_economics.economics_frame(projs, 70.0, 0.10)
    assert econ["capex_usd"].sum() > 0
    assert (econ["risked_npv_usd"] <= 0).sum() >= 1          # a real sub-economic tail


def test_program_montecarlo_brackets_the_deterministic_risked_npv(booted):
    core = booted
    txt = core.backlog_csv_text()
    econ = core.capital_economics.economics_frame(core.load_backlog(), 70.0, 0.10)
    prog, _ = core.optimize_program(econ, 60e6, 170.0)
    mc = common.program_montecarlo(txt, 70.0, 0.10, tuple(sorted(prog.selected_ids)))
    assert mc["p10"] < mc["p50"] < mc["p90"]
    # the risked NPV IS the expected value — the MC mean must land near it
    assert abs(mc["mean"] - prog.risked_npv) < 0.1 * abs(prog.risked_npv)
