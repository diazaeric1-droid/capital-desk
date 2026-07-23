"""Coverage for the v0.3.0 levers: the Regulatory module, the Colorado-derived
refrac backlog, and the program-level Monte-Carlo."""
from __future__ import annotations

import io

import pytest

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
    # SPE exceedance keys: p90 = downside low case, p10 = upside high case
    assert mc["p90"] < mc["p50"] < mc["p10"]
    # the risked NPV IS the expected value — the MC mean must land near it
    assert abs(mc["mean"] - prog.risked_npv) < 0.1 * abs(prog.risked_npv)


def test_gas_gathering_cost_reduces_pv10(booted):
    """A positive gas gathering/processing cost lowers total PV10 (gas isn't an
    un-costed upper bound), and oil-only PV is untouched."""
    core = booted
    from src import pdp
    import io as _io
    tidy = pdp.load_pdp_csv(_io.StringIO(core.SYNTH_FLEET_CSV.read_text()))
    free, _ = pdp.screen_wells(tidy, 70.0, 12.0, 0.80, 0.075, 0.10, gas_price_per_mcf=3.0)
    costed, _ = pdp.screen_wells(tidy, 70.0, 12.0, 0.80, 0.075, 0.10,
                                 gas_price_per_mcf=3.0, gas_opex_per_mcf=0.5)
    assert costed["pv10_usd"].sum() < free["pv10_usd"].sum()
    assert costed["pv10_oil_usd"].sum() == pytest.approx(free["pv10_oil_usd"].sum())


def test_severance_on_gross_wellhead_and_afe_pdp_reconcile(booted):
    """Severance is on the gross wellhead base; the AFE restatement reproduces the
    PDP per-barrel net exactly, so the two engines value a barrel identically."""
    from src import pdp
    pv = pdp.pv10([1.0], 70.0, 12.0, 0.80, 0.075, 0.10)
    pdp_bbl_net = (70.0 * (1 - 0.075) - 12.0) * 0.80           # gross-wellhead base
    assert pv == pytest.approx(pdp_bbl_net / 1.1 ** (1 / 12), rel=1e-12)
    afe_bbl = common.net_npv_gross_wellhead_severance((70.0 - 12.0) * 0.80, 0.0, 70.0, 0.075)
    assert afe_bbl == pytest.approx(pdp_bbl_net, rel=1e-12)


def test_montecarlo_correlation_widens_tail_holds_mean(booted):
    """Geologic correlation ρ widens the program downside (lower P90 — SPE
    exceedance low case) without moving the mean — the success marginals stay at Pc."""
    core = booted
    txt = core.backlog_csv_text()
    econ = core.capital_economics.economics_frame(core.load_backlog(), 70.0, 0.10)
    prog, _ = core.optimize_program(econ, 60e6, 170.0)
    ids = tuple(sorted(prog.selected_ids))
    indep = common.program_montecarlo(txt, 70.0, 0.10, ids, price_sd=12.0, rho=0.0)
    corr = common.program_montecarlo(txt, 70.0, 0.10, ids, price_sd=12.0, rho=0.6)
    assert corr["p90"] < indep["p90"]      # wider downside (p90 = SPE low case)
    assert corr["mean"] == pytest.approx(indep["mean"], rel=0.03)  # mean preserved


def test_program_montecarlo_does_not_clamp_below_grid(booted):
    """Sub-$40 price draws must be linearly extrapolated, not flat-clamped to NPV($40):
    a deck well below the $40 grid floor must value materially lower than one at $45."""
    core = booted
    txt = core.backlog_csv_text()
    econ = core.capital_economics.economics_frame(core.load_backlog(), 70.0, 0.10)
    prog, _ = core.optimize_program(econ, 60e6, 170.0)
    ids = tuple(sorted(prog.selected_ids))
    low = common.program_montecarlo(txt, 30.0, 0.10, ids, price_sd=2.0)   # ~all draws < $40
    mid = common.program_montecarlo(txt, 45.0, 0.10, ids, price_sd=2.0)
    assert low["mean"] < mid["mean"] - 1.0   # not clamped to the same $40 floor value
