"""Shared view helpers — data-source resolution + cached economics.

NOT a page. Views import this for the things every page needs: the global price
deck, the active backlog source (committed 45-project demo vs. BYOD upload), the
active PDP source (real Colorado ECMC vs. BYOD upload), and cache-friendly
wrappers (cached on the CSV TEXT, so a new upload busts the cache naturally).
"""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

import core

# Data-source labels (also used by the Data page)
BACKLOG_DEMO_LABEL = "Synthetic 45-project backlog (committed)"
BACKLOG_BYOD_LABEL = "Uploaded backlog CSV (this session)"
PDP_REAL_LABEL = "Colorado ECMC DJ Basin (real public data)"
PDP_BYOD_LABEL = "Uploaded monthly CSV (this session)"

BACKLOG_TEMPLATE = (",".join(core.capital_projects.REQUIRED_CSV_COLUMNS) + "\n"
                    "P001,Well-001,new_drill,Midland-S,9000000,800,1.4,0.9,12,0.75,0.9,30,1\n")


def deck() -> tuple[float, float, float, str]:
    """(oil_price, nri, discount, context-bar label) from the global sidebar deck."""
    ss = st.session_state
    oil = float(ss.get("oil_price", 70.0))
    nri = float(ss.get("nri", 0.80))
    disc = float(ss.get("discount", 0.10))
    return oil, nri, disc, f"${oil:.0f}/bbl · NRI {nri:.0%} · {disc:.1%} disc"


# ---- backlog (Program section) --------------------------------------------------

def resolve_backlog() -> tuple[str, str, bool]:
    """(csv_text, source label, is_byod) — BYOD upload wins when present."""
    byod = st.session_state.get("backlog_csv_text")
    if byod:
        return byod, BACKLOG_BYOD_LABEL, True
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


# ---- PDP monthly production (Screen section) -------------------------------------

@st.cache_data(show_spinner=False)
def colorado_csv_text() -> str:
    """The real Colorado ECMC slice, renamed to the PDP schema (date → month)."""
    raw = pd.read_csv(core.COLORADO_CSV).rename(columns={"date": "month"})
    return raw.to_csv(index=False)


def resolve_pdp(source_choice: str) -> tuple[str, str, bool]:
    """(csv_text, source label, is_byod) for the PDP screener."""
    if source_choice == PDP_BYOD_LABEL and st.session_state.get("pdp_csv_text"):
        return st.session_state["pdp_csv_text"], PDP_BYOD_LABEL, True
    return colorado_csv_text(), PDP_REAL_LABEL, False


@st.cache_data(show_spinner="Fitting declines + valuing wells…")
def screen_table(csv_text: str, price: float, loe: float, nri: float,
                 severance: float, discount: float, econ_limit: float):
    """(per-well table, skipped list) from src.pdp at the given assumptions."""
    from src import pdp
    tidy = pdp.load_pdp_csv(io.StringIO(csv_text))
    return pdp.screen_wells(tidy, price, loe, nri, severance, discount, econ_limit)


@st.cache_data(show_spinner=False)
def pdp_tidy(csv_text: str) -> pd.DataFrame:
    from src import pdp
    return pdp.load_pdp_csv(io.StringIO(csv_text))
