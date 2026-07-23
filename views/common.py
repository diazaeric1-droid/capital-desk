"""Shared view helpers — data-source resolution + cached economics.

NOT a page. Views import this for the things every page needs: the global price
deck, the active backlog source (committed 45-project demo vs. BYOD upload), the
active PDP source (real Colorado ECMC vs. BYOD upload), and cache-friendly
wrappers (cached on the CSV TEXT, so a new upload busts the cache naturally).
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import streamlit as st

import core

# Data-source labels (also used by the Data page)
BACKLOG_DEMO_LABEL = "Synthetic 45-project backlog (committed)"
BACKLOG_COLO_LABEL = "Colorado refrac candidates (from real PDP wells)"
BACKLOG_BYOD_LABEL = "Uploaded backlog CSV (this session)"
PDP_SYNTH_LABEL = "Synthetic 100-well Permian fleet (suite-shared)"
PDP_REAL_LABEL = "Colorado ECMC DJ Basin (real public data)"
PDP_BYOD_LABEL = "Uploaded monthly CSV (this session)"

BACKLOG_TEMPLATE = (",".join(core.capital_projects.REQUIRED_CSV_COLUMNS) + "\n"
                    "P001,Well-001,new_drill,Midland-S,9000000,800,1.4,0.9,12,0.75,0.9,30,1\n")


def page_purpose(body_md: str) -> None:
    """Top-of-page "ℹ️ What is this page for?" affordance — PE feedback: the
    per-chart descriptions were praised, but some pages' PURPOSE (what question
    they answer, when to reach for them) wasn't obvious. Every view calls this
    once, right under the masthead/context bar, with plain-PE language. Kept in
    views/common (product-local) — product_theme.py is a vendored presentation
    layer shared with the sibling products and must not drift from here."""
    with st.popover("ℹ️ What is this page for?"):
        st.markdown(body_md)


def deck() -> tuple[float, float, float, str]:
    """(oil_price, nri, discount, context-bar label) from the global sidebar deck."""
    ss = st.session_state
    oil = float(ss.get("oil_price", 70.0))
    nri = float(ss.get("nri", 0.80))
    disc = float(ss.get("discount", 0.10))
    sev = float(ss.get("severance_pct", 7.5)) / 100.0
    return oil, nri, disc, (f"${oil:.0f}/bbl · NRI {nri:.0%} · {disc:.1%} disc · "
                            f"{sev:.1%} sev")


def severance_frac() -> float:
    """Severance + ad valorem as a fraction, from the global deck — shared by the
    AFE net economics (Authorize) and the PDP screen (Screen) so both apply the
    same production-tax drag."""
    return float(st.session_state.get("severance_pct", 7.5)) / 100.0


def net_npv_gross_wellhead_severance(net_npv: float, net_cost: float, oil_price: float,
                                     severance: float, loe_per_bbl: float = 12.0) -> float:
    """Restate an AFE-component net NPV (computed on a post-LOE revenue base) onto the
    **gross-wellhead** severance base the PDP screen uses — severance taxes the gross
    price, LOE is deducted post-tax — so the two engines value a barrel identically.

    ``net_pv = net_npv + net_cost`` is Σ DF·vol·(price − loe)·nri; scaling it by
    (price·(1−sev) − loe)/(price − loe) converts the per-barrel margin to
    (price·(1−sev) − loe)·nri, matching pdp.pv10. (loe defaults to the AFE component's
    fixed $12/bbl opex.)"""
    net_pv = net_npv + net_cost
    if oil_price > loe_per_bbl:
        factor = (oil_price * (1.0 - severance) - loe_per_bbl) / (oil_price - loe_per_bbl)
    else:
        factor = 1.0 - severance
    return net_pv * factor - net_cost


def program_deck() -> str:
    """Context-bar deck label for the Program pages. Each backlog project carries
    its OWN NRI (the backlog CSV's `nri` column), so the global sidebar NRI is NOT
    applied here — it drives Authorize + Screen. Showing "NRI per-project" keeps the
    deck honest instead of implying the sidebar value feeds the program economics."""
    ss = st.session_state
    oil = float(ss.get("oil_price", 70.0))
    disc = float(ss.get("discount", 0.10))
    return f"${oil:.0f}/bbl · {disc:.1%} disc · NRI per-project"


# ---- backlog (Program section) --------------------------------------------------

@st.cache_data(show_spinner="Building refrac candidates from the Colorado fleet…")
def colorado_workover_csv() -> str:
    """Derive a refrac/recompletion backlog from the REAL Colorado PDP wells: fit
    each well's oil decline, model an incremental uplift project (a fraction of its
    current rate, declining steeply), and price a deterministic capex / rig-day / Pc
    off the well's size. Output is the standard backlog CSV schema, so the optimizer
    runs the SAME math on real-well identities as on the synthetic backlog.

    Honest: the well IDENTITIES + decline shapes are real (ECMC); the workover uplift,
    capex, and Pc are modeled assumptions (no operator publishes forward AFE economics).
    """
    from src import pdp
    tidy = pdp.load_pdp_csv(io.StringIO(colorado_csv_text()))
    rows = []
    for idx, (well_id, g) in enumerate(tidy.groupby("well_id", sort=True)):
        t, q = pdp.well_history(g)
        try:
            fit = pdp.fit_well(t, q, well_id=str(well_id))
        except ValueError:
            continue
        rng = np.random.default_rng(4200 + idx)
        # anchor on a ROBUST current rate — the trailing-6-month mean, not the single
        # last observed month (which can be a noisy outlier)
        cur = max(float(np.mean(q[-6:])) if len(q) else fit.current_rate_bopd, 5.0)
        qi_inc = float(cur * rng.uniform(2.0, 3.5))          # refrac bump over current rate
        di_inc = float(rng.uniform(1.1, 1.6))                # refracs decline fast
        b_inc = float(rng.uniform(0.8, 1.1))
        capex = float(rng.uniform(0.9e6, 2.4e6) * (0.6 + qi_inc / 600.0))
        rig_days = int(rng.integers(8, 22))
        pc = float(round(rng.uniform(0.62, 0.85), 3))
        name = (g["well_name"].iloc[0] if "well_name" in g.columns else str(well_id))
        rows.append({
            "project_id": f"CO{idx+1:03d}",
            "name": str(name)[:40],
            "category": "refrac",
            "area": "DJ Basin (Weld Co., CO)",
            "capex_usd": round(capex, 0),
            "qi_bopd": round(qi_inc, 1),
            "di_annual": round(di_inc, 3),
            "b": round(b_inc, 2),
            "opex_per_bbl": round(float(rng.uniform(9.0, 14.0)), 2),
            "nri": round(float(rng.uniform(0.78, 0.82)), 4),
            "pc": pc,
            "rig_days": rig_days,
            "earliest_quarter": int(rng.integers(1, 5)),
        })
    cols = core.capital_projects.REQUIRED_CSV_COLUMNS
    return pd.DataFrame(rows)[cols].to_csv(index=False)


def resolve_backlog() -> tuple[str, str, bool]:
    """(csv_text, source label, is_byod). BYOD upload wins; otherwise the session's
    chosen backlog source (synthetic demo or the Colorado-derived refrac candidates)."""
    byod = st.session_state.get("backlog_csv_text")
    if byod:
        return byod, BACKLOG_BYOD_LABEL, True
    if st.session_state.get("backlog_source") == "colorado":
        return colorado_workover_csv(), BACKLOG_COLO_LABEL, False
    return core.backlog_csv_text(), BACKLOG_DEMO_LABEL, False


def parse_backlog(csv_text: str) -> list:
    """Text → validated list[Project] via the component's own CSV contract.
    Raises ValueError with a readable message on schema problems."""
    return core.capital_projects.projects_from_csv(io.StringIO(csv_text))


@st.cache_data(show_spinner=False)
def econ_frame(csv_text: str, price: float, discount: float) -> pd.DataFrame:
    """Per-project risked economics for the active backlog at the deck."""
    projects = parse_backlog(csv_text)
    return core.capital_economics.economics_frame(projects, price, discount)


def solve_program_uncached(csv_text: str, price: float, discount: float,
                           budget: float, rig_cap: float):
    """(program, greedy) at the deck + constraints. Raises InfeasibleProgram.
    Plain function so multi-solve loops (frontier, price strip) can wrap their
    OWN cache around the whole sweep instead of caching point-by-point."""
    econ = econ_frame(csv_text, price, discount)
    return core.optimize_program(econ, budget, rig_cap)


@st.cache_data(show_spinner="Solving the program (MILP + greedy)…")
def solve_program(csv_text: str, price: float, discount: float,
                  budget: float, rig_cap: float):
    """Cached wrapper over ``solve_program_uncached``."""
    return solve_program_uncached(csv_text, price, discount, budget, rig_cap)


@st.cache_data(show_spinner="Running the program Monte-Carlo…")
def program_montecarlo(csv_text: str, oil: float, discount: float,
                       funded_ids: tuple, price_sd: float = 12.0,
                       n_trials: int = 5000, seed: int = 42,
                       rho: float = 0.0) -> dict | None:
    """Monte-Carlo the FUNDED program's NPV over two real risks the deterministic
    risked-NPV hides: price (Normal(deck, price_sd)) and each project's chance of
    success (Bernoulli(Pc) — a success books its unrisked NPV at the sampled price,
    a failure loses its capex as a dry hole). ``rho`` (0–1) correlates the success
    outcomes via a single-factor Gaussian copula (shared geologic risk): rho=0 is
    independent, higher rho widens the tail (the realistic case on a single-basin
    slate). Marginal P(success)=Pc for any rho, so the MEAN is unchanged. Returns
    P10/P50/P90, mean, P(loss), and the sample array for a histogram.

    Per-project NPV(price) is interpolated from a coarse price grid (each grid point
    is one cached ``econ_frame`` solve), so the whole sweep is a few solves + a
    vectorised draw — not one solve per trial."""
    funded = list(funded_ids)
    if not funded:
        return None
    base = econ_frame(csv_text, oil, discount)
    base = base[base["project_id"].isin(funded)].set_index("project_id")
    base = base.reindex([f for f in funded if f in base.index])
    if base.empty:
        return None
    capex = base["capex_usd"].to_numpy(dtype=float)
    pc = base["pc"].to_numpy(dtype=float)
    grid = np.array(range(40, 101, 5), dtype=float)
    npv_grid = np.zeros((len(base), len(grid)))
    for j, px in enumerate(grid):
        e = econ_frame(csv_text, float(px), discount).set_index("project_id")
        npv_grid[:, j] = e.reindex(base.index)["npv_usd"].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    prices = np.clip(rng.normal(oil, price_sd, n_trials), 1.0, None)
    # success outcomes via a single-factor Gaussian copula: a shared geologic factor
    # Z plus per-project idiosyncratic noise. P(success)=Φ(thr)=Pc for any rho (mean
    # unchanged); rho>0 correlates dry holes → a wider, more honest downside tail.
    from scipy.special import ndtri
    rho = float(min(max(rho, 0.0), 0.95))
    thr = ndtri(np.clip(pc, 1e-6, 1 - 1e-6))[:, None]
    z = rng.standard_normal(n_trials)[None, :]
    eps = rng.standard_normal((len(base), n_trials))
    latent = np.sqrt(rho) * z + np.sqrt(1.0 - rho) * eps
    succ = latent < thr

    def _npv_of_price(g_npv):
        """NPV(price) by interpolation, but LINEARLY EXTRAPOLATED past both grid ends
        (NPV is exactly linear in price) — a flat clamp below $40 would make the P10 /
        P(loss) optimistic exactly at the stressed decks a committee stress-tests."""
        out = np.interp(prices, grid, g_npv)
        lo_slope = (g_npv[1] - g_npv[0]) / (grid[1] - grid[0])
        hi_slope = (g_npv[-1] - g_npv[-2]) / (grid[-1] - grid[-2])
        out = np.where(prices < grid[0], g_npv[0] + lo_slope * (prices - grid[0]), out)
        out = np.where(prices > grid[-1], g_npv[-1] + hi_slope * (prices - grid[-1]), out)
        return out

    totals = np.zeros(n_trials)
    for i in range(len(base)):
        npv_i = _npv_of_price(npv_grid[i])                    # NPV(price) for project i
        totals += np.where(succ[i], npv_i, -capex[i])         # success → NPV, else dry hole
    return {
        "p10": float(np.percentile(totals, 10)),
        "p50": float(np.percentile(totals, 50)),
        "p90": float(np.percentile(totals, 90)),
        "mean": float(totals.mean()),
        "p_loss": float((totals < 0).mean()),
        "samples": totals,
    }


# ---- PDP monthly production (Screen section) -------------------------------------

# ---- live AFE actuals (Pipeline → Variance chain) -------------------------------

def generate_afe_actuals(afe_number: str, intervention: str) -> dict:
    """Deterministic closed-out actuals for an AFE executed from the Pipeline Board —
    each cost-template line ±a small variance, plus one unbudgeted line, so an
    executed AFE flows into the Variance page (closing detect→authorize→reconcile).

    Returns {"afe": [(category, budget)…], "act": [(category, actual)…]}; the
    unbudgeted line appears only in "act" (no budget), exactly like the demo data.
    """
    items = core.afe_cost_db.lookup_cost_template(intervention)
    try:
        seed = int(str(afe_number).split("-")[-1])
    except ValueError:
        seed = 0
    rng = np.random.default_rng(seed)
    afe_lines, act_lines = [], []
    for li in items:
        afe_lines.append((li.category, float(li.total_usd)))
        actual = float(li.total_usd) * (1.0 + float(rng.uniform(-0.08, 0.22)))
        act_lines.append((li.category, round(actual, 0)))
    if rng.random() < 0.6:          # most jobs hit an unbudgeted surprise
        extra = rng.choice(["Fishing", "Rig standby", "Remedial cement"])
        act_lines.append((str(extra), round(float(rng.uniform(8_000, 35_000)), 0)))
    return {"afe": afe_lines, "act": act_lines}


def combined_variance_frames():
    """(afe_df, actuals_df) = the demo closed-out actuals PLUS any AFEs executed from
    the Pipeline Board this session — so the Variance page reflects the live loop."""
    afe_df, actuals_df = core.afe_variance.demo_variance_data()
    live = st.session_state.get("live_actuals", {})
    afe_rows, act_rows = [], []
    for afe, d in live.items():
        afe_rows += [(afe, c, b) for c, b in d.get("afe", [])]
        act_rows += [(afe, c, a) for c, a in d.get("act", [])]
    if afe_rows:
        afe_df = pd.concat([afe_df, pd.DataFrame(
            afe_rows, columns=["afe_number", "category", "line_total_usd"])],
            ignore_index=True)
        actuals_df = pd.concat([actuals_df, pd.DataFrame(
            act_rows, columns=["afe_number", "category", "actual_usd"])],
            ignore_index=True)
    return afe_df, actuals_df


@st.cache_data(show_spinner=False)
def colorado_csv_text() -> str:
    """The real Colorado ECMC slice, renamed to the PDP schema (date → month)."""
    raw = pd.read_csv(core.COLORADO_CSV).rename(columns={"date": "month"})
    return raw.to_csv(index=False)


@st.cache_data(show_spinner=False)
def synth_fleet_csv_text() -> str:
    """The suite-shared 100-well synthetic fleet as monthly PDP-schema oil."""
    return core.ensure_synth_fleet(log=lambda *_: None).read_text()


def resolve_pdp(source_choice: str) -> tuple[str, str, bool]:
    """(csv_text, source label, is_byod) for the PDP screener.

    Three sources: the suite-shared synthetic fleet (default — keeps Capital Desk's
    fleet identity consistent with Operations Center + Engineering Workbench), the
    REAL Colorado ECMC slice, or a BYOD monthly upload. ``is_byod`` flags only the
    upload (used to pick the provenance badge)."""
    if source_choice == PDP_BYOD_LABEL and st.session_state.get("pdp_csv_text"):
        return st.session_state["pdp_csv_text"], PDP_BYOD_LABEL, True
    if source_choice == PDP_REAL_LABEL:
        return colorado_csv_text(), PDP_REAL_LABEL, False
    return synth_fleet_csv_text(), PDP_SYNTH_LABEL, False


@st.cache_data(show_spinner="Fitting declines + valuing wells…")
def screen_table(csv_text: str, price: float, loe: float, nri: float,
                 severance: float, discount: float, econ_limit: float,
                 gas_price: float = 0.0, dmin: float = None,
                 gas_opex: float = 0.0):
    """(per-well table, skipped list) from src.pdp at the given assumptions."""
    from src import pdp
    if dmin is None:
        dmin = pdp.DEFAULT_DMIN_ANNUAL
    tidy = pdp.load_pdp_csv(io.StringIO(csv_text))
    return pdp.screen_wells(tidy, price, loe, nri, severance, discount, econ_limit,
                            gas_price_per_mcf=gas_price, dmin_annual=dmin,
                            gas_opex_per_mcf=gas_opex)


@st.cache_data(show_spinner=False)
def pdp_tidy(csv_text: str) -> pd.DataFrame:
    from src import pdp
    return pdp.load_pdp_csv(io.StringIO(csv_text))


def find_well_production(query: str) -> tuple[str, str, str] | None:
    """Resolve a Draft-AFE well id / name to production history: returns
    ``(csv_text, source_label, matched_well_id)`` from the FIRST source that
    knows the well — BYOD upload (this session), then the suite synthetic fleet,
    then the real Colorado ECMC slice — or None when no source does (the Draft
    AFE page renders an honest empty state, never fabricated history).

    Matching is case-insensitive exact on well_id then well_name
    (``src.pdp.find_well``); the parsed tidy frames are cached on the CSV text
    (``pdp_tidy``), so the lookup is a vectorized compare per rerun, not a
    re-parse of 4,000+ rows."""
    from src import pdp
    q = str(query or "").strip()
    if not q:
        return None
    sources: list[tuple[str, str]] = []
    if st.session_state.get("pdp_csv_text"):
        sources.append((st.session_state["pdp_csv_text"], PDP_BYOD_LABEL))
    sources.append((synth_fleet_csv_text(), PDP_SYNTH_LABEL))
    sources.append((colorado_csv_text(), PDP_REAL_LABEL))
    for csv_text, label in sources:
        try:
            wid = pdp.find_well(pdp_tidy(csv_text), q)
        except ValueError:
            continue          # unparseable BYOD text — skip it, never crash the page
        if wid:
            return csv_text, label, wid
    return None


@st.cache_data(show_spinner=False)
def fit_one_well(csv_text: str, well_id: str, econ_limit: float, dmin: float = None):
    """(t_hist, q_hist, fit, forecast_rates) for ONE well — cached so the drill-down
    doesn't re-run the curve fit on every unrelated rerun (only on well/limit change)."""
    from src import pdp
    if dmin is None:
        dmin = pdp.DEFAULT_DMIN_ANNUAL
    g = pdp_tidy(csv_text)
    g = g[g["well_id"] == well_id]
    t_hist, q_hist = pdp.well_history(g)
    fit = pdp.fit_well(t_hist, q_hist, well_id=well_id)
    fc_rates, _ = pdp.forecast_volumes(fit, econ_limit, dmin_annual=dmin)
    return t_hist, q_hist, fit, fc_rates
