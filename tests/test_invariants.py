"""Cross-component numeric invariants — the product must not bend component math."""
from __future__ import annotations

import json

import pytest


def test_draft_view_economics_matches_component_exactly(booted):
    """Invariant (b): the Draft-AFE view's code path (core.draft_economics) and a
    direct call into afe.economics.compute_economics return the SAME net NPV on a
    pinned input — bit-identical, not approximately."""
    core = booted
    cost = core.afe_cost_db.cost_rollup("acid_stimulation")["total"]
    kwargs = dict(uplift_decline_per_yr=0.75, realized_price_per_bbl=70.0,
                  working_interest=1.0, net_revenue_interest=0.80,
                  discount_rate=0.10)
    via_view = core.draft_economics(cost, 130.0, **kwargs)
    direct = core.afe_economics.compute_economics(cost, 130.0, **kwargs)
    assert via_view.net_npv_10pct_usd == direct.net_npv_10pct_usd
    assert via_view.npv_10pct_usd == direct.npv_10pct_usd
    assert via_view.payout_months == direct.payout_months
    assert via_view.net_npv_10pct_usd > 0     # sanity: a real, positive project


def test_optimizer_beats_greedy_and_matches_component_summary(booted):
    """Invariant (c): on the committed backlog the MILP risked NPV is >= greedy,
    and both match the component's own committed eval summary (evals/results/
    summary.json) at its pinned settings ($70 deck)."""
    core = booted
    summary_path = (core.APP_DIRS["capital"] / "evals" / "results" / "summary.json")
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text())
    econ = core.capital_economics.economics_frame(core.load_backlog(), 70.0, 0.10)
    for setting in summary["settings"]:
        budget = setting["budget_mm"] * 1e6
        rig = setting["rig_capacity"]
        program, greedy = core.optimize_program(econ, budget, rig)
        assert program.risked_npv >= greedy.risked_npv - 1e-6
        assert round(program.risked_npv / 1e6, 2) == pytest.approx(
            setting["milp_risked_npv_mm"], abs=0.01)
        assert round(greedy.risked_npv / 1e6, 2) == pytest.approx(
            setting["greedy_risked_npv_mm"], abs=0.01)
        assert setting["feasible"] and setting["beats_greedy"]
    # the honest headline numbers: ~3-5% / $4.4-7.8MM under a binding rig limit
    uplifts = [s["uplift_mm"] for s in summary["settings"] if s["rig_capacity"] <= 200
               and s["budget_mm"] >= 60]
    assert min(uplifts) >= 4.3 and max(uplifts) <= 7.9


def test_quarterly_schedule_respects_earliest_quarter(booted):
    """Every funded project is scheduled in a quarter >= its earliest_quarter."""
    core = booted
    projects = core.load_backlog()
    econ = core.capital_economics.economics_frame(projects, 70.0, 0.10)
    program, _ = core.optimize_program(econ, 60e6, 170)
    sched = core.capital_schedule.schedule_program(
        econ, program.selected_ids, projects, n_quarters=4, rig_per_quarter=45)
    assert len(sched) == program.n_selected
    earliest = {p.project_id: int(p.earliest_quarter) for p in projects}
    for _, row in sched.iterrows():
        q = int(str(row["quarter"]).lstrip("Q"))
        assert q >= earliest[row["project_id"]], (
            f"{row['project_id']} scheduled Q{q} before its earliest "
            f"Q{earliest[row['project_id']]}")


def test_pdp_uses_suite_discounting_kernel(booted):
    """The PDP Screener discounts through afe.econ_core (not a private formula):
    a one-month, one-bbl stream at 10% must price at exactly net/1.1^(1/12)."""
    core = booted
    from src import pdp
    assert pdp.econ_core is core.econ_core
    net = (70.0 - 12.0) * 0.80 * (1 - 0.075)
    pv = pdp.pv10([1.0], 70.0, 12.0, 0.80, 0.075, 0.10)
    assert pv == pytest.approx(net / 1.1 ** (1 / 12), rel=1e-12)
