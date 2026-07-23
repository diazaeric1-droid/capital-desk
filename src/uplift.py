"""Uplift decline economics — an EXACT Arps decline on the incremental uplift stream.

PE feedback (CD2): *"ability to modify curve for economics … a much more detailed
version with an exact production decline curve instead of a linear decline."*
The vendored AFE component models the uplift as an EXPONENTIAL decline
(qi·e^(−Di·t) — already a decline curve, not linear, but with no b knob and the
curve never plotted). This module generalises the uplift stream to the full Arps
family (exponential OR hyperbolic, qi/Di/b all user-set) using the kernel the
suite already ships (``econ_core.arps_monthly_rate``) and prices it through the
exact same discounting convention (``econ_core.discounted_pv``,
DF(m) = (1+r)^(m/12)) — ONE discounting kernel, no second convention invented.

Pure functions, no streamlit; the vendored ``apps/`` cores stay untouched.
``b < 1e-6`` reduces bit-identically to the vendored
``afe.economics.compute_economics`` exponential path (pinned by a product test),
so the Draft AFE page's "Exponential (legacy)" mode stays continuity-exact.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core import econ_core  # suite discounting convention (afe.econ_core)

DEFAULT_B = 1.0                  # harmonic default — typical for workover uplift tails
DEFAULT_HORIZON_YEARS = 5        # matches the AFE component's intervention horizon


def uplift_monthly_rates(qi_bopd: float, di_annual: float, b: float,
                         horizon_years: int = DEFAULT_HORIZON_YEARS) -> np.ndarray:
    """Monthly uplift rate (bopd) at months 1..12·horizon — Arps; b≈0 → exponential."""
    months = econ_core.month_index(horizon_years)
    return econ_core.arps_monthly_rate(qi_bopd, di_annual, b, months)


@dataclass
class UpliftEconomics:
    """Field-compatible with ``afe.economics.AFEEconomics`` so the Draft AFE view
    reads either object without caring which model produced it."""
    treatment_cost_usd: float
    incremental_first_year_bbl: float
    incremental_eur_bbl: float
    npv_10pct_usd: float
    payout_months: float
    dollars_per_incremental_bbl: float
    working_interest: float = 1.0
    net_revenue_interest: float = 1.0
    net_cost_to_operator_usd: float = 0.0
    net_npv_10pct_usd: float = 0.0
    model: str = "hyperbolic"    # "exponential" when b ≈ 0
    b: float = DEFAULT_B


def uplift_economics(
    treatment_cost_usd: float,
    incremental_rate_bopd: float,
    uplift_decline_per_yr: float = 0.6,
    b: float = DEFAULT_B,
    horizon_years: int = DEFAULT_HORIZON_YEARS,
    realized_price_per_bbl: float = 65.0,
    opex_per_bbl: float = 12.0,
    discount_rate: float = 0.10,
    working_interest: float = 1.0,
    net_revenue_interest: float = 1.0,
) -> UpliftEconomics:
    """AFE intervention economics with the uplift declining on an exact Arps curve.

    Mirrors ``afe.economics.compute_economics`` operation-for-operation (same
    5-year horizon, same price−opex margin, same ``econ_core`` PV / payout calls)
    with only the rate stream generalised — so at b≈0 the two are bit-identical.
    """
    months = econ_core.month_index(horizon_years)
    monthly_rate = econ_core.arps_monthly_rate(
        incremental_rate_bopd, uplift_decline_per_yr, b, months)
    monthly_vol = monthly_rate * econ_core.DAYS_PER_MONTH
    margin_per_bbl = realized_price_per_bbl - opex_per_bbl
    monthly_revenue = monthly_vol * margin_per_bbl

    pv = econ_core.discounted_pv(monthly_revenue, discount_rate)
    npv = pv - treatment_cost_usd
    payout = econ_core.payout_months(monthly_revenue, treatment_cost_usd)

    first_year_bbl = float(monthly_vol[:12].sum())
    eur = float(monthly_vol.sum())
    dollars_per_bbl = (treatment_cost_usd / first_year_bbl
                       if first_year_bbl > 0 else float("inf"))

    net_cost = treatment_cost_usd * working_interest
    net_pv = econ_core.discounted_pv(monthly_revenue * net_revenue_interest,
                                     discount_rate)
    net_npv = net_pv - net_cost

    return UpliftEconomics(
        treatment_cost_usd=treatment_cost_usd,
        incremental_first_year_bbl=first_year_bbl,
        incremental_eur_bbl=eur,
        npv_10pct_usd=npv,
        payout_months=payout,
        dollars_per_incremental_bbl=dollars_per_bbl,
        working_interest=working_interest,
        net_revenue_interest=net_revenue_interest,
        net_cost_to_operator_usd=net_cost,
        net_npv_10pct_usd=net_npv,
        model="exponential" if b < 1e-6 else "hyperbolic",
        b=float(b),
    )


def price_sensitivity(
    treatment_cost_usd: float,
    incremental_rate_bopd: float,
    prices: tuple[float, ...] = (45.0, 55.0, 65.0, 75.0, 85.0),
    **kwargs,
) -> list[dict]:
    """Price-strip rows with the SAME keys as ``afe.economics.price_sensitivity``
    (realized_price, npv_usd, net_npv_usd, payout_months, dollars_per_bbl), so the
    Draft AFE deck table renders either model's rows unchanged."""
    rows = []
    for p in prices:
        e = uplift_economics(treatment_cost_usd, incremental_rate_bopd,
                             realized_price_per_bbl=p, **kwargs)
        rows.append({
            "realized_price": p,
            "npv_usd": e.npv_10pct_usd,
            "net_npv_usd": e.net_npv_10pct_usd,
            "payout_months": e.payout_months,
            "dollars_per_bbl": e.dollars_per_incremental_bbl,
        })
    return rows


# ---------- Monte-Carlo on the Arps stream ------------------------------------

@dataclass
class UpliftMonteCarloResult:
    """Field-compatible with ``afe.economics.MonteCarloResult``."""
    n_trials: int
    npv_p10_usd: float
    npv_p50_usd: float
    npv_p90_usd: float
    npv_mean_usd: float
    probability_of_payout: float
    tornado: dict[str, dict[str, float]]
    base_npv_usd: float


def _arps_batched(qi, di, b: float, months) -> np.ndarray:
    """(n,) qi/Di draws × (T,) months → (n, T) Arps rates; b is a fixed scalar.
    The b < 1e-6 branch reproduces ``econ_core.exp_uplift_rate``'s batched path
    operation-for-operation (bit-identical — pinned by test)."""
    qi = np.atleast_1d(np.asarray(qi, dtype=float))
    di = np.atleast_1d(np.asarray(di, dtype=float))
    t = np.asarray(months, dtype=float) / 12.0
    if b < 1e-6:
        return qi[:, None] * np.exp(-di[:, None] * t[None, :])
    return qi[:, None] / np.power(1.0 + b * di[:, None] * t[None, :], 1.0 / b)


def simulate_uplift_economics(
    treatment_cost_usd: float,
    incremental_rate_bopd: float,
    uplift_decline_per_yr: float = 0.6,
    b: float = DEFAULT_B,
    realized_price_per_bbl: float = 65.0,
    horizon_years: int = DEFAULT_HORIZON_YEARS,
    opex_per_bbl: float = 12.0,
    discount_rate: float = 0.10,
    n_trials: int = 10_000,
    rate_rel_spread: float = 0.30,
    decline_abs_spread: float = 0.15,
    price_sd: float = 12.0,
    payout_cap_months: int = 24,
    seed: int | None = 42,
) -> UpliftMonteCarloResult:
    """Monte-Carlo NPV mirroring ``afe.economics.simulate_economics`` — same draw
    structure, same seed, same anchors — with the uplift stream generalised to
    Arps(b). ``b`` is held FIXED across trials (the sampled uncertainties stay
    rate / decline / price, exactly as in the component); at b≈0 the result is
    bit-identical to the vendored simulation (pinned by a product test)."""
    rng = np.random.default_rng(seed)

    rate_lo = incremental_rate_bopd * (1 - rate_rel_spread)
    rate_hi = incremental_rate_bopd * (1 + rate_rel_spread)
    rate_draws = rng.uniform(rate_lo, rate_hi, n_trials)

    decline_lo = uplift_decline_per_yr - decline_abs_spread
    decline_hi = uplift_decline_per_yr + decline_abs_spread
    decline_draws = np.clip(rng.uniform(decline_lo, decline_hi, n_trials), 1e-6, 2.0)

    price_draws = np.clip(rng.normal(realized_price_per_bbl, price_sd, n_trials),
                          1.0, None)

    months = econ_core.month_index(horizon_years)

    def _npv(rate, decl, price) -> np.ndarray:
        monthly_vol = _arps_batched(rate, decl, b, months) * econ_core.DAYS_PER_MONTH
        margin = np.atleast_1d(np.asarray(price, dtype=float)) - opex_per_bbl
        monthly_revenue = monthly_vol * margin[:, None]
        return econ_core.discounted_pv(monthly_revenue, discount_rate) - treatment_cost_usd

    npvs = _npv(rate_draws, decline_draws, price_draws)

    # payout within the cap — undiscounted cumulative revenue vs cost, per draw
    monthly_vol = _arps_batched(rate_draws, decline_draws, b, months) * econ_core.DAYS_PER_MONTH
    monthly_revenue = monthly_vol * (price_draws - opex_per_bbl)[:, None]
    cap = max(1, min(payout_cap_months, len(months)))
    cumulative = np.cumsum(monthly_revenue, axis=1)
    paid = cumulative[:, cap - 1] >= treatment_cost_usd
    prob_payout = float(np.mean((npvs > 0) & paid))

    p10, p50, p90 = (float(x) for x in np.percentile(npvs, [10, 50, 90]))

    base = float(_npv(incremental_rate_bopd, uplift_decline_per_yr,
                      realized_price_per_bbl)[0])

    def _one(rate, decl, price) -> float:
        return float(_npv(rate, decl, price)[0])

    decl_lo_anchor = max(uplift_decline_per_yr - decline_abs_spread, 1e-6)
    decl_hi_anchor = min(uplift_decline_per_yr + decline_abs_spread, 2.0)
    price_lo_anchor = max(realized_price_per_bbl - 1.2816 * price_sd, 1.0)
    price_hi_anchor = realized_price_per_bbl + 1.2816 * price_sd

    tornado: dict[str, dict[str, float]] = {}
    for name, lo_vals, hi_vals in (
        ("incremental_rate_bopd",
         (rate_lo, uplift_decline_per_yr, realized_price_per_bbl),
         (rate_hi, uplift_decline_per_yr, realized_price_per_bbl)),
        ("uplift_decline_per_yr",
         (incremental_rate_bopd, decl_hi_anchor, realized_price_per_bbl),
         (incremental_rate_bopd, decl_lo_anchor, realized_price_per_bbl)),
        ("realized_price_per_bbl",
         (incremental_rate_bopd, uplift_decline_per_yr, price_lo_anchor),
         (incremental_rate_bopd, uplift_decline_per_yr, price_hi_anchor)),
    ):
        low_npv = _one(*lo_vals)
        high_npv = _one(*hi_vals)
        tornado[name] = {"low": low_npv, "high": high_npv,
                         "swing": abs(high_npv - low_npv)}

    return UpliftMonteCarloResult(
        n_trials=n_trials,
        npv_p10_usd=p10,
        npv_p50_usd=p50,
        npv_p90_usd=p90,
        npv_mean_usd=float(np.mean(npvs)),
        probability_of_payout=prob_payout,
        tornado=tornado,
        base_npv_usd=base,
    )
