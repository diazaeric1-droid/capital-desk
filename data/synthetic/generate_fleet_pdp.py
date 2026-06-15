"""Generate the suite's shared 100-well fleet as MONTHLY oil production for the
PDP Screener.

These are the SAME 100 well identities the other two operator products use
(``well_001`` … ``well_100`` from the vendored ``fleet_registry`` — same basin,
area, formation, lift, lateral length, and first-production month). Operations
Center and Engineering Workbench express the fleet as ~400 days of *daily* SCADA;
a producing-asset (PDP) A&D screen needs *monthly* oil with a fit-able decline,
so this generator renders the same fleet at monthly grain instead.

Per well, off a deterministic seed (the well number), we draw realistic Permian
horizontal Arps parameters — qi scaled by lateral length and lift type, a steep
first-year decline (hyperbolic, b∈[0.85,1.25]) — and emit monthly oil from the
registry's ``first_prod`` month forward to ``END_MONTH``. Each well therefore has
a different maturity (younger wells are flush and high-value; 2021-vintage wells
are deep on the curve near the economic limit), so the screen produces a genuine
PV10 spread instead of 100 identical declines.

Output: ``fleet_pdp.csv`` with the PDP monthly contract columns
(``well_id, month, oil_bbl, gas_mcf, days``) plus ``well_name`` for display. Gas
rides each well's GOR off the oil decline. Deterministic: reruns are byte-identical
(seeded per well; no wall-clock).

Honest framing: SYNTHETIC. Future capital deals and most private production are
not public data; the real, public-record option on the same page is the Colorado
ECMC slice. Ranges are order-of-magnitude consistent with public Permian figures.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Vendored fleet_registry lives at the repo root (two levels up from data/synthetic/).
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
import fleet_registry  # noqa: E402  (path set above)

OUT = Path(__file__).parent / "fleet_pdp.csv"
N_WELLS = 100
END_MONTH = pd.Period("2026-05", freq="M")   # last reported month (matches the SCADA fleet end)
DAYS_PER_MONTH = 365.25 / 12.0

# Lift-type initial-rate multipliers: flowing/gas-lift wells come on stronger,
# rod-pump wells are the lower-rate mature tail (consistent with the registry mix).
_LIFT_QI = {"Flowing": 1.25, "Gas lift": 1.15, "ESP": 1.0, "Rod pump": 0.72}


def _gor_for(n: int, meta) -> float:
    """Per-well gas-oil ratio (scf/bbl), deterministic, biased high for gassy lifts
    (mirrors the suite's SCADA fleet generator so the same well reads consistently)."""
    rng = np.random.default_rng(n + 7000)
    base = float(rng.uniform(600, 1400))
    if meta.lift in ("Gas lift", "Flowing"):
        base += float(rng.uniform(700, 1400))
    elif meta.lift == "Rod pump":
        base *= 0.85
    return float(np.clip(base, 500, 3000))


def _arps_rate(t_years: np.ndarray, qi: float, di: float, b: float) -> np.ndarray:
    """Arps rate (bopd) at t years since first production; b≈0 → exponential."""
    if b < 1e-6:
        return qi * np.exp(-di * t_years)
    return qi / np.power(1.0 + b * di * t_years, 1.0 / b)


def _well_params(n: int, meta) -> tuple[float, float, float]:
    """Deterministic (qi_bopd, di_nominal_annual, b) for well number ``n``."""
    rng = np.random.default_rng(20260614 + n)
    lat_factor = meta.lateral_length_ft / 9500.0          # longer laterals → more oil
    basin_factor = 1.08 if meta.basin == "Midland" else 1.0
    lift_factor = _LIFT_QI.get(meta.lift, 1.0)
    qi = float(rng.uniform(470, 1180) * lat_factor * basin_factor * lift_factor)
    qi = float(np.clip(qi, 180, 1900))
    # ~20% of the fleet declines exponentially (b≈0, gentler initial decline); the
    # rest are hyperbolic. A real fleet is a mix, not all one model.
    if rng.random() < 0.20:
        b = 0.0
        di = float(rng.uniform(0.55, 1.00))
    else:
        b = float(rng.uniform(0.85, 1.25))
        di = float(rng.uniform(1.05, 1.75))               # nominal annual decline (1/yr)
    return qi, di, b


def _well_rows(well_id: str) -> list[dict]:
    meta = fleet_registry.get(well_id)
    n = int(well_id.rsplit("_", 1)[-1])
    qi, di, b = _well_params(n, meta)
    gor = _gor_for(n, meta)                               # scf/bbl, constant per well
    rng = np.random.default_rng(770000 + n)

    first = pd.Period(meta.first_prod, freq="M")
    if first > END_MONTH:                                  # guard odd registry dates
        first = END_MONTH - 12
    months = pd.period_range(first, END_MONTH, freq="M")

    # Per-well data QUALITY tier → monthly scatter (sigma). Most wells report clean,
    # some are noisy, a few are messy (low R²) — so the screen's low-confidence guard
    # has real wells to flag and the fleet isn't suspiciously perfect.
    qd = rng.random()
    sigma = (rng.uniform(0.04, 0.09) if qd < 0.62
             else rng.uniform(0.10, 0.18) if qd < 0.86
             else rng.uniform(0.24, 0.42))               # messy tail → genuinely low R²
    # ~18% of wells carry a mid-life disruption (a workover bump or an operational
    # dip) that no single Arps curve fits — realistic structure that lowers R².
    bump_mid = int(len(months) * rng.uniform(0.30, 0.65))
    has_bump = rng.random() < 0.18
    bump_mag = rng.uniform(1.20, 1.70) if rng.random() < 0.5 else rng.uniform(0.45, 0.75)

    rows: list[dict] = []
    for k, per in enumerate(months):
        t_mid_years = (k + 0.5) / 12.0                    # month midpoint, in years
        rate = float(_arps_rate(np.array([t_mid_years]), qi, di, b)[0])
        if has_bump and bump_mid <= k < bump_mid + 4:     # 4-month workover/dip event
            rate *= bump_mag
        # uptime: mostly full, with an occasional partial-month downtime event
        if rng.random() < 0.06:
            days = int(rng.integers(8, 24))
        else:
            days = int(rng.integers(28, 32))
        noise = float(rng.lognormal(mean=0.0, sigma=sigma))
        oil = rate * days * noise
        if oil < 1:                                       # below a stripper floor → stop reporting
            break
        # gas tracks oil via the well's GOR (solution-gas behaviour) + its own scatter
        gas_noise = float(rng.lognormal(mean=0.0, sigma=0.08))
        gas_mcf = oil * gor / 1000.0 * gas_noise          # scf/bbl × bbl ÷ 1000 = mcf
        rows.append({
            "well_id": well_id,
            "well_name": meta.name,
            "month": str(per),                            # YYYY-MM
            "oil_bbl": round(oil, 1),
            "gas_mcf": round(gas_mcf, 1),
            "days": days,
        })
    return rows


def build() -> pd.DataFrame:
    all_rows: list[dict] = []
    for i in range(1, N_WELLS + 1):
        all_rows.extend(_well_rows(f"well_{i:03d}"))
    df = pd.DataFrame(all_rows,
                      columns=["well_id", "well_name", "month", "oil_bbl", "gas_mcf", "days"])
    return df.sort_values(["well_id", "month"]).reset_index(drop=True)


if __name__ == "__main__":
    df = build()
    OUT.write_text(df.to_csv(index=False))
    n_wells = df["well_id"].nunique()
    print(f"Wrote {OUT.name}: {n_wells} wells · {len(df):,} well-months "
          f"({df['month'].min()} → {df['month'].max()}).")
