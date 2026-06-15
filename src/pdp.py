"""PDP Screener math — per-well Arps decline fits, remaining EUR, and PV10 for a
producing-asset (PDP) A&D quick-look.

The ONLY new math in Capital Desk; everything else reuses vendored component code.
Pure functions, no streamlit. Discounting delegates to the suite kernel
(``afe.econ_core``, re-exported by ``core``) so the screen values cash flows with
the exact same effective-annual convention (DF(m) = (1+r)^(m/12)) the AFE Copilot
authorizes against and the Capital Optimizer allocates against.

Conventions
-----------
* Input grain: one row per well per month — ``well_id, month (YYYY-MM), oil_bbl``
  with optional ``days`` (producing days; used to convert volume to rate).
* Rate (bopd) = oil_bbl / days when producing days are reported, else
  oil_bbl / DAYS_PER_MONTH (365.25/12).
* Fit: exponential (b = 0) AND hyperbolic (b ∈ (0, 1.5]) via scipy ``curve_fit``
  on rate vs. time; the lower-SSE model wins (exponential on ties — fewer knobs).
* Forecast starts FORWARD FROM THE LAST HISTORY MONTH — never from t = 0. An Arps
  fit is parameterised at first production, so integrating from t = 1 re-counts
  every barrel already produced (the exact ~2.16x remaining-EUR overstatement bug
  found and fixed in the Production Engineer Copilot). Forward monthly volumes are
  evaluated at month MIDPOINTS (midpoint rule), so the discrete sum tracks the
  continuous integral to well under 0.5%.
* Economic limit: forecast stops at the first month whose rate falls below the
  limit (default 3.0 bopd) or after 360 forecast months, whichever comes first.
* PV10: monthly net revenue = oil_bbl x (oil_price - loe_per_bbl) x nri x
  (1 - severance_frac), discounted with ``econ_core.discounted_pv`` (end-of-month,
  effective-annual).

Sources: Arps (1945) decline curves; SPE-PRMS reserve conventions; standard
upstream DCF.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from core import econ_core  # suite discounting convention (afe.econ_core)

DAYS_PER_MONTH = econ_core.DAYS_PER_MONTH

DEFAULT_ECON_LIMIT_BOPD = 3.0     # stripper-well cutoff for the quick-look
MAX_FORECAST_MONTHS = 360         # 30-year cap, whichever comes first
MIN_FIT_POINTS = 6                # below this a monthly Arps fit is not credible
B_MAX = 1.5                       # hyperbolic exponent upper bound
DI_MIN, DI_MAX = 1e-4, 15.0       # nominal annual decline bounds (1/yr)

# BYOD monthly-CSV contract (optional columns: gas_mcf, days)
REQUIRED_PDP_COLUMNS: list[str] = ["well_id", "month", "oil_bbl"]
OPTIONAL_PDP_COLUMNS: list[str] = ["gas_mcf", "days"]

MCF_PER_BOE = 6.0                 # 6 mcf gas ≈ 1 barrel of oil equivalent (energy basis)


# ---------------------------------------------------------------------------
# input loading / validation
# ---------------------------------------------------------------------------

def load_pdp_csv(path_or_buffer) -> pd.DataFrame:
    """Load + validate a monthly PDP CSV (``well_id, month, oil_bbl[, days]``).

    Raises ``ValueError`` with a human-readable message on any schema problem so
    callers (the Streamlit views) can surface a clean ``st.error`` instead of a
    stack trace. Returns a tidy frame with parsed month indices per well.
    """
    try:
        df = pd.read_csv(path_or_buffer)
    except Exception as exc:  # noqa: BLE001 — normalize parser errors
        raise ValueError(f"Could not parse the CSV: {exc}") from exc

    missing = [c for c in REQUIRED_PDP_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required columns: {missing}. "
            f"Required: {REQUIRED_PDP_COLUMNS} (optional: {OPTIONAL_PDP_COLUMNS}).")
    if df.empty:
        raise ValueError("CSV contains no data rows.")

    df = df.copy()
    df["oil_bbl"] = pd.to_numeric(df["oil_bbl"], errors="coerce")
    bad = df["oil_bbl"].isna()
    if bad.any():
        raise ValueError(
            "Non-numeric or missing oil_bbl at row(s): "
            f"{list(df.index[bad][:10] + 1)}.")
    if "days" in df.columns:
        df["days"] = pd.to_numeric(df["days"], errors="coerce")
    if "gas_mcf" in df.columns:
        df["gas_mcf"] = pd.to_numeric(df["gas_mcf"], errors="coerce").fillna(0.0)

    try:
        df["_period"] = pd.PeriodIndex(
            pd.to_datetime(df["month"].astype(str), format="mixed"), freq="M")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            f"Could not parse the 'month' column as year-month (e.g. 2024-03): {exc}"
        ) from exc

    df["well_id"] = df["well_id"].astype(str)
    return df.sort_values(["well_id", "_period"]).reset_index(drop=True)


def template_csv() -> str:
    """A fill-in-and-upload template for the BYOD monthly schema (gas optional)."""
    return ("well_id,month,oil_bbl,gas_mcf,days\n"
            "WELL-001,2023-01,9500,14200,31\n"
            "WELL-001,2023-02,8800,13100,28\n"
            "WELL-001,2023-03,8300,12400,31\n")


def gas_oil_ratio_mcf_bbl(group: pd.DataFrame) -> float:
    """A well's producing GOR (mcf gas per bbl oil) from its history — used to ride
    the gas forecast off the oil decline (solution-gas behaviour). 0 when there is
    no gas column or no oil."""
    if "gas_mcf" not in group.columns:
        return 0.0
    oil = float(group["oil_bbl"].sum())
    gas = float(pd.to_numeric(group["gas_mcf"], errors="coerce").fillna(0.0).sum())
    return (gas / oil) if oil > 0 else 0.0


def well_history(group: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """(t_months, rate_bopd) for ONE well's rows (already month-sorted).

    t is the calendar month offset from the well's first reported month, so gaps
    in reporting keep their true spacing. Rate uses producing days when present.
    """
    per = group["_period"]
    p0 = per.iloc[0]
    t = np.array([(p.year - p0.year) * 12 + (p.month - p0.month) for p in per],
                 dtype=float)
    oil = group["oil_bbl"].to_numpy(dtype=float)
    if "days" in group.columns:
        days = group["days"].to_numpy(dtype=float)
        days = np.where(np.isfinite(days) & (days > 0), days, DAYS_PER_MONTH)
    else:
        days = np.full_like(oil, DAYS_PER_MONTH)
    rate = oil / days
    return t, rate


# ---------------------------------------------------------------------------
# Arps fitting
# ---------------------------------------------------------------------------

def _exp_rate(t_years, qi, di):
    return qi * np.exp(-di * t_years)


def _hyp_rate(t_years, qi, di, b):
    return qi / np.power(1.0 + b * di * t_years, 1.0 / b)


def arps_rate(t_years, qi: float, di: float, b: float):
    """Arps rate (bopd) at t (years since first history month). b=0 → exponential."""
    t_years = np.asarray(t_years, dtype=float)
    if b < 1e-9:
        return _exp_rate(t_years, qi, di)
    return _hyp_rate(t_years, qi, di, b)


@dataclass
class WellFit:
    well_id: str
    model: str                # "exponential" | "hyperbolic"
    qi_bopd: float            # fitted rate at t=0 (first history month)
    di_annual: float          # nominal annual decline (1/yr)
    b: float                  # 0 for exponential
    sse: float
    r_squared: float
    n_points: int
    t_last_months: float      # month index of the last history point (t=0 at first)
    current_rate_bopd: float  # last OBSERVED rate (not the fit)


def fit_well(t_months, rates_bopd, well_id: str = "") -> WellFit:
    """Fit exponential AND hyperbolic Arps on monthly oil rate; keep the lower SSE.

    Raises ``ValueError`` when the well has fewer than ``MIN_FIT_POINTS`` positive
    finite rates (a monthly fit on less history is noise, not a forecast).
    """
    t = np.asarray(t_months, dtype=float)
    q = np.asarray(rates_bopd, dtype=float)
    mask = np.isfinite(q) & (q > 0) & np.isfinite(t)
    t, q = t[mask], q[mask]
    if len(t) < MIN_FIT_POINTS:
        raise ValueError(
            f"{well_id or 'well'}: need at least {MIN_FIT_POINTS} positive monthly "
            f"rates to fit a decline (got {len(t)}).")

    ty = t / 12.0
    qi0 = float(q[0])
    span = max(float(ty[-1] - ty[0]), 1e-6)
    # crude initial decline from endpoints, clipped into bounds
    d0 = float(np.clip(np.log(max(q[0], 1e-9) / max(q[-1], 1e-9)) / span,
                       0.05, DI_MAX * 0.5)) if q[-1] < q[0] else 0.3

    def _sse(pred):
        return float(np.sum((q - pred) ** 2))

    exp_fit = None
    try:
        (qi_e, di_e), _ = curve_fit(
            _exp_rate, ty, q, p0=[qi0, d0],
            bounds=([1e-9, DI_MIN], [np.inf, DI_MAX]), maxfev=20000)
        exp_fit = (float(qi_e), float(di_e), 0.0, _sse(_exp_rate(ty, qi_e, di_e)))
    except Exception:  # noqa: BLE001 — fit can fail on pathological series
        pass

    hyp_fit = None
    try:
        (qi_h, di_h, b_h), _ = curve_fit(
            _hyp_rate, ty, q, p0=[qi0, max(d0, 0.2), 0.8],
            bounds=([1e-9, DI_MIN, 1e-3], [np.inf, DI_MAX, B_MAX]), maxfev=20000)
        hyp_fit = (float(qi_h), float(di_h), float(b_h),
                   _sse(_hyp_rate(ty, qi_h, di_h, b_h)))
    except Exception:  # noqa: BLE001
        pass

    if exp_fit is None and hyp_fit is None:
        raise ValueError(f"{well_id or 'well'}: decline fit did not converge.")

    # lower SSE wins; exponential on (near-)ties — fewer parameters, same fit
    if hyp_fit is None or (exp_fit is not None
                           and exp_fit[3] <= hyp_fit[3] * (1.0 + 1e-9)):
        qi, di, b, sse = exp_fit
        model = "exponential"
        pred = _exp_rate(ty, qi, di)
    else:
        qi, di, b, sse = hyp_fit
        model = "hyperbolic"
        pred = _hyp_rate(ty, qi, di, b)

    ss_tot = float(np.sum((q - q.mean()) ** 2))
    r2 = 1.0 - sse / ss_tot if ss_tot > 0 else 0.0

    return WellFit(
        well_id=well_id, model=model, qi_bopd=qi, di_annual=di, b=b, sse=sse,
        r_squared=float(r2), n_points=int(len(t)), t_last_months=float(t[-1]),
        current_rate_bopd=float(q[-1]))


# ---------------------------------------------------------------------------
# forecast forward from the LAST history month
# ---------------------------------------------------------------------------

def forecast_volumes(fit: WellFit,
                     econ_limit_bopd: float = DEFAULT_ECON_LIMIT_BOPD,
                     max_months: int = MAX_FORECAST_MONTHS,
                     ) -> tuple[np.ndarray, np.ndarray]:
    """Forward monthly (rates_bopd, volumes_bbl), starting AFTER the last history
    month — never from t=0 (that re-counts produced barrels; see module docstring).

    Month k (k = 1..) covers (t_last + k - 1, t_last + k]; its rate is evaluated at
    the month midpoint t_last + k - 0.5 (midpoint rule) and its volume is
    rate x DAYS_PER_MONTH. The forecast stops at the first month whose rate is
    below ``econ_limit_bopd``, or after ``max_months``, whichever comes first.
    Returns empty arrays when the well is already at/below the economic limit.
    """
    k = np.arange(1, int(max_months) + 1, dtype=float)
    t_mid_years = (fit.t_last_months + k - 0.5) / 12.0
    rates = arps_rate(t_mid_years, fit.qi_bopd, fit.di_annual, fit.b)
    below = np.nonzero(rates < econ_limit_bopd)[0]
    n = int(below[0]) if len(below) else int(max_months)
    rates = rates[:n]
    return rates, rates * DAYS_PER_MONTH


def remaining_eur(fit: WellFit,
                  econ_limit_bopd: float = DEFAULT_ECON_LIMIT_BOPD,
                  max_months: int = MAX_FORECAST_MONTHS) -> float:
    """Remaining EUR (bbl) = the integral of the forward forecast to the economic
    limit (midpoint-rule monthly sum; matches the analytic (q_now - q_limit)/D
    exponential integral to <0.5% — pinned by a product test)."""
    _, vols = forecast_volumes(fit, econ_limit_bopd, max_months)
    return float(vols.sum())


def pv10(volumes_bbl, oil_price: float, loe_per_bbl: float = 12.0,
         nri: float = 0.80, severance_frac: float = 0.075,
         discount: float = 0.10, *, gas_volumes_mcf=None,
         gas_price_per_mcf: float = 0.0) -> float:
    """PV of the forward net-revenue stream under the suite discounting convention.

    monthly oil net revenue = oil_bbl x (oil_price - loe_per_bbl) x nri x (1 - severance)
    plus, when ``gas_volumes_mcf`` and a gas price are given,
    monthly gas net revenue = gas_mcf x gas_price x nri x (1 - severance)
    discounted end-of-month, effective-annual (econ_core.discounted_pv) — month 1
    is the first full month after the last history month. Gas defaults OFF so the
    oil-only signature is unchanged.
    """
    vols = np.asarray(volumes_bbl, dtype=float)
    if vols.size == 0:
        return 0.0
    net = vols * (oil_price - loe_per_bbl) * nri * (1.0 - severance_frac)
    if gas_volumes_mcf is not None and gas_price_per_mcf > 0:
        gas = np.asarray(gas_volumes_mcf, dtype=float)
        net = net + gas * gas_price_per_mcf * nri * (1.0 - severance_frac)
    return float(econ_core.discounted_pv(net, discount))


# ---------------------------------------------------------------------------
# deal screen (per-well table + rollup)
# ---------------------------------------------------------------------------

def screen_wells(df: pd.DataFrame, oil_price: float, loe_per_bbl: float = 12.0,
                 nri: float = 0.80, severance_frac: float = 0.075,
                 discount: float = 0.10,
                 econ_limit_bopd: float = DEFAULT_ECON_LIMIT_BOPD,
                 max_months: int = MAX_FORECAST_MONTHS,
                 gas_price_per_mcf: float = 0.0,
                 ) -> tuple[pd.DataFrame, list[tuple[str, str]]]:
    """Fit + value every well in a tidy monthly frame (from ``load_pdp_csv``).

    Returns ``(table, skipped)``: one row per fit-able well — qi, Di, b, model,
    r², current oil/gas rate, remaining oil EUR, gas EUR, oil/gas/total PV10 —
    sorted by total PV10 descending, plus a list of (well_id, reason) for wells
    that could not be fit. Gas rides the oil decline at the well's producing GOR;
    with ``gas_price_per_mcf=0`` (or no gas column) the screen is oil-only.
    """
    if "_period" not in df.columns:
        raise ValueError("screen_wells expects the frame returned by load_pdp_csv().")
    rows: list[dict] = []
    skipped: list[tuple[str, str]] = []
    for well_id, g in df.groupby("well_id", sort=True):
        t, q = well_history(g)
        try:
            fit = fit_well(t, q, well_id=str(well_id))
        except ValueError as exc:
            skipped.append((str(well_id), str(exc)))
            continue
        _, vols = forecast_volumes(fit, econ_limit_bopd, max_months)
        eur = float(vols.sum())
        gor = gas_oil_ratio_mcf_bbl(g)                       # mcf/bbl, 0 when no gas
        gas_vols = vols * gor                                # forecast gas (mcf)
        gas_eur = float(gas_vols.sum())
        pv_oil = pv10(vols, oil_price, loe_per_bbl, nri, severance_frac, discount)
        pv_total = pv10(vols, oil_price, loe_per_bbl, nri, severance_frac, discount,
                        gas_volumes_mcf=gas_vols, gas_price_per_mcf=gas_price_per_mcf)
        cur_oil = fit.current_rate_bopd
        cur_gas = cur_oil * gor                               # current gas rate (mcfd)
        rows.append({
            "well_id": str(well_id),
            "model": fit.model,
            "qi_bopd": round(fit.qi_bopd, 1),
            "di_annual": round(fit.di_annual, 4),
            "b": round(fit.b, 3),
            "r_squared": round(fit.r_squared, 3),
            "n_months": fit.n_points,
            "current_bopd": round(cur_oil, 1),
            "current_gas_mcfd": round(cur_gas, 1),
            "current_boepd": round(cur_oil + cur_gas / MCF_PER_BOE, 1),
            "gor_mcf_bbl": round(gor, 3),
            "remaining_eur_bbl": round(eur, 0),
            "gas_eur_mcf": round(gas_eur, 0),
            "pv10_oil_usd": round(pv_oil, 0),
            "pv10_gas_usd": round(pv_total - pv_oil, 0),
            "pv10_usd": round(pv_total, 0),
        })
    table = pd.DataFrame(rows)
    if not table.empty:
        table = table.sort_values("pv10_usd", ascending=False).reset_index(drop=True)
    return table, skipped


def deal_rollup(table: pd.DataFrame, asking_price_usd: float | None = None) -> dict:
    """Roll the per-well screen up to the deal: total PV10 (oil + gas), remaining
    oil EUR, current oil + BOE production, and (when an asking price is given)
    $/flowing bbl, $/flowing BOE, and the PV10-vs-asking premium."""
    if table.empty:
        out = {"n_wells": 0, "total_pv10_usd": 0.0, "total_pv10_oil_usd": 0.0,
               "total_pv10_gas_usd": 0.0, "total_eur_bbl": 0.0,
               "total_gas_eur_mcf": 0.0, "total_current_bopd": 0.0,
               "total_current_boepd": 0.0}
    else:
        boepd = (float(table["current_boepd"].sum()) if "current_boepd" in table
                 else float(table["current_bopd"].sum()))
        out = {
            "n_wells": int(len(table)),
            "total_pv10_usd": float(table["pv10_usd"].sum()),
            "total_pv10_oil_usd": float(table.get("pv10_oil_usd", table["pv10_usd"]).sum()),
            "total_pv10_gas_usd": float(table["pv10_gas_usd"].sum()) if "pv10_gas_usd" in table else 0.0,
            "total_eur_bbl": float(table["remaining_eur_bbl"].sum()),
            "total_gas_eur_mcf": float(table["gas_eur_mcf"].sum()) if "gas_eur_mcf" in table else 0.0,
            "total_current_bopd": float(table["current_bopd"].sum()),
            "total_current_boepd": boepd,
        }
    if asking_price_usd is not None and asking_price_usd > 0:
        out["asking_price_usd"] = float(asking_price_usd)
        out["usd_per_flowing_bbl"] = (
            asking_price_usd / out["total_current_bopd"]
            if out["total_current_bopd"] > 0 else float("inf"))
        out["usd_per_flowing_boe"] = (
            asking_price_usd / out["total_current_boepd"]
            if out["total_current_boepd"] > 0 else float("inf"))
        out["pv10_minus_asking_usd"] = out["total_pv10_usd"] - asking_price_usd
        out["pv10_over_asking"] = (out["total_pv10_usd"] / asking_price_usd
                                   if asking_price_usd > 0 else float("inf"))
    return out
