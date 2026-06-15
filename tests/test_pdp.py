"""PDP Screener numeric invariants — the product's only new math, pinned hard."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest

QI, D = 300.0, 0.6           # bopd, nominal annual decline (1/yr)
N_HIST = 24                  # months of history (t = 0..23)
LIMIT = 3.0                  # economic limit (bopd)


@pytest.fixture(scope="module")
def pdp(booted):
    from src import pdp as _pdp
    return _pdp


@pytest.fixture(scope="module")
def exp_fit(pdp):
    """Fit on a PERFECT exponential monthly series with known qi and D."""
    t = np.arange(N_HIST, dtype=float)
    q = QI * np.exp(-D * t / 12.0)
    return pdp.fit_well(t, q, "EXP-TEST")


def test_exponential_fit_recovers_parameters(pdp, exp_fit):
    assert exp_fit.model == "exponential"
    assert exp_fit.qi_bopd == pytest.approx(QI, rel=1e-6)
    assert exp_fit.di_annual == pytest.approx(D, rel=1e-6)
    assert exp_fit.b == 0.0
    assert exp_fit.t_last_months == float(N_HIST - 1)
    assert exp_fit.current_rate_bopd == pytest.approx(QI * np.exp(-D * (N_HIST - 1) / 12.0))


def test_remaining_eur_matches_analytic_integral(pdp, exp_fit):
    """Invariant (a): remaining EUR matches the exponential closed form
    (q_now − q_limit)/D — integrated FORWARD from the last history month — to
    <0.5%."""
    eur = pdp.remaining_eur(exp_fit, econ_limit_bopd=LIMIT)
    q_now = QI * np.exp(-D * (N_HIST - 1) / 12.0)
    analytic = (q_now - LIMIT) / D * 365.25        # bopd-years → bbl
    assert eur == pytest.approx(analytic, rel=0.005)


def test_forecast_starts_at_last_history_month_not_t0(pdp, exp_fit):
    """Regression sentinel for the from-t=0 bug (overstated remaining EUR ~2.16x
    in pe-copilot): integrating from first production must NOT be what we do."""
    eur = pdp.remaining_eur(exp_fit, econ_limit_bopd=LIMIT)
    from_zero = (QI - LIMIT) / D * 365.25          # the WRONG (re-counting) integral
    assert eur < 0.5 * from_zero                   # nowhere near the from-zero number
    rates, vols = pdp.forecast_volumes(exp_fit, econ_limit_bopd=LIMIT)
    # first forecast month sits just past the last history month (midpoint rule)
    expected_first = QI * np.exp(-D * (exp_fit.t_last_months + 0.5) / 12.0)
    assert rates[0] == pytest.approx(expected_first, rel=1e-9)
    assert rates[0] < exp_fit.current_rate_bopd


def test_pv10_matches_independent_brute_force(pdp, exp_fit):
    """Invariant (a, part 2): PV10 equals a hand-rolled monthly discounted sum
    under the effective-annual convention to <1e-6 relative."""
    price, loe, nri, sev, disc = 70.0, 12.0, 0.80, 0.075, 0.10
    _, vols = pdp.forecast_volumes(exp_fit, econ_limit_bopd=LIMIT)
    pv = pdp.pv10(vols, price, loe, nri, sev, disc)
    # severance on the GROSS wellhead base: tax the price, deduct LOE post-tax
    brute = sum(
        v * (price * (1.0 - sev) - loe) * nri / (1.0 + disc) ** ((m + 1) / 12.0)
        for m, v in enumerate(vols))
    assert pv == pytest.approx(brute, rel=1e-6)
    assert pv > 0


def test_hyperbolic_fit_recovery_and_b_bound(pdp):
    qi, di, b = 400.0, 0.9, 0.9
    t = np.arange(36, dtype=float)
    q = qi / np.power(1.0 + b * di * t / 12.0, 1.0 / b)
    fit = pdp.fit_well(t, q, "HYP-TEST")
    assert fit.model == "hyperbolic"
    assert fit.qi_bopd == pytest.approx(qi, rel=1e-3)
    assert fit.di_annual == pytest.approx(di, rel=1e-2)
    assert fit.b == pytest.approx(b, rel=1e-2)
    assert 0.0 < fit.b <= pdp.B_MAX


def test_economic_limit_and_month_cap(pdp):
    # already at/below the limit -> empty forecast, zero EUR and PV
    t = np.arange(12, dtype=float)
    q = 2.5 * np.exp(-0.3 * t / 12.0)              # all below the 3-bopd limit
    fit = pdp.fit_well(t, q, "DEAD-WELL")
    rates, vols = pdp.forecast_volumes(fit, econ_limit_bopd=3.0)
    assert len(rates) == 0
    assert pdp.remaining_eur(fit, econ_limit_bopd=3.0) == 0.0
    assert pdp.pv10(vols, 70.0) == 0.0
    # near-flat decline -> the 360-month cap binds before the rate limit
    q2 = 100.0 * np.exp(-0.01 * t / 12.0)
    fit2 = pdp.fit_well(t, q2, "FLAT-WELL")
    rates2, _ = pdp.forecast_volumes(fit2, econ_limit_bopd=3.0)
    assert len(rates2) == pdp.MAX_FORECAST_MONTHS


def test_csv_validation_messages(pdp):
    with pytest.raises(ValueError, match="Missing required columns"):
        pdp.load_pdp_csv(io.StringIO("well_id,oil_bbl\nW1,100\n"))
    with pytest.raises(ValueError, match="no data rows"):
        pdp.load_pdp_csv(io.StringIO("well_id,month,oil_bbl\n"))
    with pytest.raises(ValueError, match="Non-numeric"):
        pdp.load_pdp_csv(io.StringIO("well_id,month,oil_bbl\nW1,2024-01,abc\n"))
    with pytest.raises(ValueError, match="at least 6"):
        pdp.fit_well(np.arange(4.0), np.array([50.0, 40, 30, 20]), "SHORT")


def test_colorado_screen_end_to_end(pdp, booted):
    """All 28 real ECMC wells fit and value at the default deck."""
    core = booted
    raw = pd.read_csv(core.COLORADO_CSV).rename(columns={"date": "month"})
    tidy = pdp.load_pdp_csv(io.StringIO(raw.to_csv(index=False)))
    table, skipped = pdp.screen_wells(tidy, 70.0)
    assert len(table) == 28 and not skipped
    assert (table["pv10_usd"] >= 0).all()
    assert table["pv10_usd"].sum() > 0
    assert set(table["model"]) <= {"exponential", "hyperbolic"}
    roll = pdp.deal_rollup(table, asking_price_usd=25e6)
    assert roll["total_current_bopd"] > 0
    assert roll["usd_per_flowing_bbl"] == pytest.approx(
        25e6 / roll["total_current_bopd"])
    assert roll["pv10_minus_asking_usd"] == pytest.approx(
        roll["total_pv10_usd"] - 25e6)
