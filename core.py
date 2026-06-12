"""Capital Desk core — in-process engine over the vendored component apps.

Adapted from pe-pipeline's ``pipeline_core.py`` (the proven alias loader). Both
component apps are packaged as a top-level ``src`` package, so they can't be
imported normally side by side (the name collides). This module loads each app's
``src`` under a distinct alias via importlib:

    afe      -> apps/afe-copilot/src        (AFE drafting, tracker, variance, docx)
    capital  -> apps/capital-optimizer/src   (backlog economics, MILP allocation)

so the whole capital workflow — authorize (AFE) → program (MILP allocation) →
screen (PDP deal quick-look) — runs in ONE Python process: no subprocesses, no
per-app virtualenvs. The apps are **vendored** as plain directories under
``apps/`` (mirrored byte-identical from their own repos; see VENDORING.md), so a
Streamlit Cloud deploy is a single self-contained clone.

``afe.econ_core`` is the suite-wide economics kernel (effective-annual
discounting: DF(m) = (1+r)^(m/12), so a 10% input means 10% per YEAR). It is
re-exported here as ``econ_core`` — the pipeline_core precedent — so the new
PDP Screener (``src/pdp.py``) and every view discount cash flows with the exact
same convention the AFE Copilot authorizes against and the Capital Optimizer
allocates against.

IMPORTANT: this module stays importable WITHOUT streamlit (no streamlit import
anywhere in it) so product tests and CI can drive it headless. Views add their
own ``st.cache_*`` wrappers on top.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Apps are vendored plain directories under apps/; override for unusual layouts.
APPS_ROOT = Path(os.environ.get("CAPITAL_APPS_ROOT", HERE / "apps"))
APP_DIRS = {
    "afe": APPS_ROOT / "afe-copilot",
    "capital": APPS_ROOT / "capital-optimizer",
}


def _load_pkg(app_dir: Path, alias: str):
    """Load ``app_dir/src`` as a top-level package named ``alias`` so its internal
    relative imports (``from .economics import ...``) resolve under that alias."""
    if alias in sys.modules:
        return sys.modules[alias]
    src = app_dir / "src"
    if not (src / "__init__.py").exists():
        raise FileNotFoundError(
            f"{alias}: missing {src}/__init__.py — the apps are vendored under apps/; "
            f"run from the repo root (or set CAPITAL_APPS_ROOT).")
    spec = importlib.util.spec_from_file_location(
        alias, src / "__init__.py", submodule_search_locations=[str(src)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


# Register both packages under aliases, then import the entry points views use.
_load_pkg(APP_DIRS["afe"], "afe")
_load_pkg(APP_DIRS["capital"], "capital")

# ---- AFE Copilot (authorize) -------------------------------------------------
afe_cost_db = importlib.import_module("afe.cost_db")
afe_economics = importlib.import_module("afe.economics")
afe_models = importlib.import_module("afe.models")
afe_risk_register = importlib.import_module("afe.risk_register")
afe_tracker = importlib.import_module("afe.tracker")
afe_variance = importlib.import_module("afe.variance")
afe_docx_builder = importlib.import_module("afe.docx_builder")
afe_handoff = importlib.import_module("afe.handoff")
afe_drafter = importlib.import_module("afe.drafter")

# ---- Capital Program Optimizer (program) --------------------------------------
capital_projects = importlib.import_module("capital.projects")
capital_economics = importlib.import_module("capital.economics")
capital_optimizer = importlib.import_module("capital.optimizer")
capital_scenarios = importlib.import_module("capital.scenarios")
capital_schedule = importlib.import_module("capital.schedule")

# Suite-wide economics kernel, vendored inside the AFE app and re-exported here so
# the PDP Screener and every view discount with the exact same effective-annual
# convention as the apps they sit on (the pipeline_core precedent).
econ_core = importlib.import_module("afe.econ_core")

AFE_VERSION = "0.6.2"          # afe-copilot (pyproject + CHANGELOG)
CAPITAL_VERSION = importlib.import_module("capital").__version__   # "0.2.3"

# ---- data locations -----------------------------------------------------------
# The realistic 45-project backlog is COMMITTED in the vendored component (13/45
# sub-economic at the $70 deck by design); its generator sits next to it.
BACKLOG_CSV = APP_DIRS["capital"] / "data" / "synthetic" / "projects.csv"
BACKLOG_GENERATOR = APP_DIRS["capital"] / "data" / "synthetic" / "generate.py"

# Product-local runtime state (gitignored via data/state/). The AFE component's
# demo keeps its tracker at <repo>/pipeline.sqlite; we mirror that pattern into a
# product-local path so the vendored component tree stays pristine.
STATE_DIR = HERE / "data" / "state"
TRACKER_DB = STATE_DIR / "tracker.sqlite"

# Real public production data for the PDP Screener (mirrored from
# production-engineer-copilot — see VENDORING.md): Colorado ECMC DJ Basin,
# 28 horizontal wells, per-well monthly oil/gas/water, 2016-2026.
COLORADO_DIR = HERE / "data" / "real" / "colorado"
COLORADO_CSV = COLORADO_DIR / "production.csv"

EXAMPLES_DIR = APP_DIRS["afe"] / "examples"


# ---- bootstrap (regenerate gitignored artifacts on first run) ------------------

def ensure_backlog(log=print) -> Path:
    """The 45-project backlog ships committed inside the vendored component; if it
    is ever missing (e.g. wiped), regenerate it with the component's own generator
    (deterministic seed) — the same first-run behaviour as the component demo."""
    if not BACKLOG_CSV.exists():
        log("Generating the synthetic capital backlog (capital-optimizer)…")
        runpy.run_path(str(BACKLOG_GENERATOR), run_name="__main__")
    return BACKLOG_CSV


def ensure_tracker(log=print) -> Path:
    """Create + seed the product-local AFE tracker (SQLite) on first run.

    Mirrors the AFE component demo (seed_demo_data on a missing DB) at a
    product-local gitignored path, so the pipeline board is populated
    out-of-the-box and user-created AFEs persist across reruns."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not TRACKER_DB.exists():
        log("Seeding the AFE pipeline tracker (12 demo AFEs)…")
        afe_tracker.seed_demo_data(TRACKER_DB)
    return TRACKER_DB


def bootstrap(log=print) -> None:
    ensure_backlog(log)
    ensure_tracker(log)


# ---- authorize (AFE) helpers ---------------------------------------------------

def get_tracker():
    """Product-local AFE tracker handle (creates schema if needed)."""
    ensure_tracker(log=lambda *_: None)
    return afe_tracker.AFETracker(TRACKER_DB)


def pipeline_df():
    """The AFE pipeline as a DataFrame (status, days-in-status, approver, risk)."""
    return get_tracker().as_dataframe()


def draft_economics(treatment_cost_usd: float, incremental_rate_bopd: float,
                    uplift_decline_per_yr: float = 0.6,
                    realized_price_per_bbl: float = 70.0,
                    working_interest: float = 1.0,
                    net_revenue_interest: float = 0.80,
                    discount_rate: float = 0.10):
    """The Draft-AFE view's single economics code path — a thin pass-through to
    ``afe.economics.compute_economics`` so the view and the component compute the
    exact same net NPV (pinned by a product test)."""
    return afe_economics.compute_economics(
        treatment_cost_usd, incremental_rate_bopd,
        uplift_decline_per_yr=uplift_decline_per_yr,
        realized_price_per_bbl=realized_price_per_bbl,
        working_interest=working_interest,
        net_revenue_interest=net_revenue_interest,
        discount_rate=discount_rate)


def afe_markdown(diag: dict, working_interest: float = 1.0,
                 net_revenue_interest: float = 0.80,
                 realized_price: float = 70.0) -> str:
    """Deterministic (keyless) AFE markdown from a WellDiagnosis dict."""
    return afe_handoff.render_afe_markdown(
        diag, working_interest=working_interest,
        net_revenue_interest=net_revenue_interest, realized_price=realized_price)


# ---- program (optimizer) helpers ------------------------------------------------

def backlog_csv_text() -> str:
    """The committed backlog CSV as text (the cache key views hash)."""
    return ensure_backlog(log=lambda *_: None).read_text()


def load_backlog() -> list:
    """The committed 45-project backlog as ``capital.projects.Project`` objects."""
    return capital_projects.load_projects(ensure_backlog(log=lambda *_: None))


def optimize_program(econ_df, budget: float, rig_capacity: float | None):
    """Solve the program both ways: exact MILP and the greedy rank-and-cut
    baseline, at the same budget + rig limit. Returns ``(program, greedy)``.

    Raises ``capital.optimizer.InfeasibleProgram`` when no feasible program
    exists — callers must surface that instead of rendering a bogus plan."""
    program = capital_optimizer.optimize(econ_df, budget, rig_capacity)
    greedy = capital_optimizer.greedy_select(econ_df, budget, rig_capacity)
    return program, greedy


# ---- navigation design (single source of truth; app.py builds st.Page from it) --
# section -> list of (page title, view file, material icon)
NAV: dict[str, list[tuple[str, str, str]]] = {
    "Authorize": [
        ("Pipeline Board", "views/authorize_pipeline.py", ":material/approval:"),
        ("Draft AFE", "views/authorize_draft.py", ":material/approval:"),
        ("Variance", "views/authorize_variance.py", ":material/approval:"),
    ],
    "Program": [
        ("Backlog", "views/program_backlog.py", ":material/account_balance:"),
        ("Optimizer", "views/program_optimizer.py", ":material/account_balance:"),
        ("Frontier & Sensitivity", "views/program_frontier.py", ":material/account_balance:"),
    ],
    "Screen": [
        ("PDP Screener", "views/screen_pdp.py", ":material/query_stats:"),
    ],
    "Data": [
        ("Sources & BYOD", "views/data_sources.py", ":material/database:"),
    ],
}
