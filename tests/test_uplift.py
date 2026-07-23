"""src/uplift.py invariants — the exact-Arps uplift economics (PE feedback CD2).

The load-bearing claim: at b≈0 the new module is BIT-IDENTICAL to the vendored
``afe.economics`` exponential path (deterministic economics AND the seeded
Monte-Carlo), so "Exponential (legacy)" mode is continuity-exact and the
hyperbolic mode is the same math with only the rate stream generalised.
"""
from __future__ import annotations

import numpy as np
import pytest

KW = dict(uplift_decline_per_yr=0.75, realized_price_per_bbl=70.0,
          working_interest=1.0, net_revenue_interest=0.80, discount_rate=0.10)
COST = 250_000.0
RATE = 130.0


@pytest.fixture(scope="module")
def uplift(booted):
    from src import uplift as _uplift
    return _uplift


def test_b_zero_matches_component_bit_identical(uplift, booted):
    """b=0 uplift_economics == afe.economics.compute_economics, exactly."""
    core = booted
    mine = uplift.uplift_economics(COST, RATE, b=0.0, **KW)
    theirs = core.afe_economics.compute_economics(COST, RATE, **KW)
    assert mine.npv_10pct_usd == theirs.npv_10pct_usd
    assert mine.net_npv_10pct_usd == theirs.net_npv_10pct_usd
    assert mine.payout_months == theirs.payout_months
    assert mine.incremental_first_year_bbl == theirs.incremental_first_year_bbl
    assert mine.incremental_eur_bbl == theirs.incremental_eur_bbl
    assert mine.net_cost_to_operator_usd == theirs.net_cost_to_operator_usd
    assert mine.model == "exponential"


def test_hyperbolic_exceeds_exponential_at_same_qi_di(uplift):
    """b>0 keeps a fatter tail: EUR and NPV must exceed the b=0 case at equal
    qi/Di (both start at the same qi and the hyperbolic declines slower)."""
    exp = uplift.uplift_economics(COST, RATE, b=0.0, **KW)
    hyp = uplift.uplift_economics(COST, RATE, b=1.0, **KW)
    assert hyp.incremental_eur_bbl > exp.incremental_eur_bbl
    assert hyp.npv_10pct_usd > exp.npv_10pct_usd
    assert hyp.model == "hyperbolic" and hyp.b == 1.0


def test_rates_and_pv_hand_check(uplift, booted):
    """First-month rate matches the Arps closed form; NPV matches a hand-rolled
    discounted sum under the suite's effective-annual convention."""
    core = booted
    qi, di, b = 100.0, 0.6, 1.0
    rates = uplift.uplift_monthly_rates(qi, di, b)
    assert len(rates) == 60
    assert rates[0] == pytest.approx(qi / (1.0 + b * di * (1 / 12.0)) ** (1.0 / b),
                                     rel=1e-12)
    e = uplift.uplift_economics(COST, qi, uplift_decline_per_yr=di, b=b,
                                realized_price_per_bbl=70.0, discount_rate=0.10)
    vols = rates * core.econ_core.DAYS_PER_MONTH
    brute = sum(v * (70.0 - 12.0) / (1.1 ** ((m + 1) / 12.0))
                for m, v in enumerate(vols)) - COST
    assert e.npv_10pct_usd == pytest.approx(brute, rel=1e-9)


def test_price_sensitivity_mirrors_component_row_keys(uplift, booted):
    """Same row keys as afe.economics.price_sensitivity (the deck table renders
    either), and b=0 rows equal the component's rows exactly."""
    core = booted
    mine = uplift.price_sensitivity(COST, RATE, b=0.0, **{
        k: v for k, v in KW.items() if k != "realized_price_per_bbl"})
    theirs = core.afe_economics.price_sensitivity(COST, RATE, **{
        k: v for k, v in KW.items() if k != "realized_price_per_bbl"})
    assert [set(r) for r in mine] == [set(r) for r in theirs]
    for m, t in zip(mine, theirs):
        assert m["realized_price"] == t["realized_price"]
        assert m["npv_usd"] == t["npv_usd"]
        assert m["net_npv_usd"] == t["net_npv_usd"]
        assert m["payout_months"] == t["payout_months"]


def test_monte_carlo_b_zero_matches_component_seeded(uplift, booted):
    """Same seed + same draw structure → the b≈0 Arps Monte-Carlo reproduces the
    vendored simulate_economics exactly (percentiles, mean, payout prob, tornado)."""
    core = booted
    mine = uplift.simulate_uplift_economics(COST, RATE, uplift_decline_per_yr=0.6,
                                            b=0.0, realized_price_per_bbl=70.0,
                                            n_trials=2000, seed=42)
    theirs = core.afe_economics.simulate_economics(COST, RATE,
                                                   uplift_decline_per_yr=0.6,
                                                   realized_price_per_bbl=70.0,
                                                   n_trials=2000, seed=42)
    assert mine.npv_p10_usd == theirs.npv_p10_usd
    assert mine.npv_p50_usd == theirs.npv_p50_usd
    assert mine.npv_p90_usd == theirs.npv_p90_usd
    assert mine.npv_mean_usd == theirs.npv_mean_usd
    assert mine.probability_of_payout == theirs.probability_of_payout
    assert mine.base_npv_usd == theirs.base_npv_usd
    for k in theirs.tornado:
        assert mine.tornado[k] == theirs.tornado[k]


def test_monte_carlo_hyperbolic_shifts_distribution_up(uplift):
    """At the same qi/Di, sampling around the fatter-tailed b=1 stream must move
    the whole NPV distribution up vs. b=0 (more volume in every trial)."""
    from src import uplift as _u
    hyp = _u.simulate_uplift_economics(COST, RATE, b=1.0, n_trials=2000, seed=42)
    exp = _u.simulate_uplift_economics(COST, RATE, b=0.0, n_trials=2000, seed=42)
    assert hyp.npv_p50_usd > exp.npv_p50_usd
    assert hyp.npv_mean_usd > exp.npv_mean_usd


def test_uses_suite_kernel(uplift, booted):
    """No second discounting convention: src.uplift discounts through the same
    afe.econ_core module object as everything else."""
    core = booted
    assert uplift.econ_core is core.econ_core
    dollars = np.array([1.0] * 12)
    assert uplift.econ_core.discounted_pv(dollars[:0], 0.10) == 0.0
