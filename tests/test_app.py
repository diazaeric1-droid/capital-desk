"""UI render coverage — the app shell and every view execute without exceptions."""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]

# the session-state contract app.py establishes (plus page-local extras)
CONTRACT = {
    "oil_price": 70.0,
    "nri": 0.80,
    "discount": 0.10,
    "well_id": "",
    "data_source": "Bundled demo data",
    "anthropic_key": "",
    "budget_mm": 60,
    "rig_cap": 170,
}

# view -> (min KPI metrics, min dataframes): a silent early st.stop() fails here
VIEWS = {
    "views/authorize_pipeline.py": (4, 3),
    "views/authorize_draft.py": (8, 2),
    "views/authorize_variance.py": (4, 1),
    "views/program_backlog.py": (4, 1),
    "views/program_optimizer.py": (5, 2),
    "views/program_frontier.py": (0, 0),   # two charts, no tables
    "views/screen_pdp.py": (4, 1),
    "views/file_regulatory.py": (0, 1),    # regulatory worksheet (Form 7 default)
    "views/data_sources.py": (0, 0),       # provenance + uploaders
}


def _no_exception(at: AppTest, label: str) -> None:
    assert not at.exception, (
        f"{label} raised: " + "; ".join(str(e.value) for e in at.exception))


def test_app_smoke(booted):
    """Full app boots: setup, sidebar deck, navigation, default page render."""
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=600)
    at.run()
    _no_exception(at, "app.py")
    # the global deck exists with its defaults
    assert at.session_state["oil_price"] == 70.0
    assert at.session_state["nri"] == 0.80
    assert at.session_state["discount"] == 0.10


@pytest.mark.parametrize("view", list(VIEWS), ids=[Path(v).stem for v in VIEWS])
def test_view_renders_clean(view, booted):
    """Each page executes end-to-end (MILP solves included) with zero exceptions,
    zero st.error banners, and its expected content actually on screen."""
    at = AppTest.from_file(str(ROOT / view), default_timeout=600)
    for k, v in CONTRACT.items():
        at.session_state[k] = v
    at.run()
    _no_exception(at, view)
    if view == "views/authorize_variance.py":
        # the >10% overrun supplement banner is DESIGNED st.error content —
        # the demo actuals deliberately trip the policy; assert it fires.
        assert any("Supplemental AFE required" in e.value for e in at.error)
    else:
        assert not at.error, f"{view} rendered st.error: {[e.value for e in at.error]}"
    min_metrics, min_dfs = VIEWS[view]
    assert len(at.metric) >= min_metrics, f"{view}: missing KPI metrics"
    assert len(at.dataframe) >= min_dfs, f"{view}: missing data tables"
    assert len(at.markdown) > 0, f"{view}: rendered no content at all"


def test_optimizer_view_shows_honest_uplift(booted):
    """The Optimizer page renders the real $4.4MM/+3.1% framing at the default
    $60MM / 170 rig-day constraints — never an inflated headline."""
    at = AppTest.from_file(str(ROOT / "views/program_optimizer.py"),
                           default_timeout=600)
    for k, v in CONTRACT.items():
        at.session_state[k] = v
    at.run()
    _no_exception(at, "optimizer")
    success_text = " ".join(s.value for s in at.success)
    assert "+$4.4MM" in success_text or "$4.4MM (+3.1%)" in success_text or \
        "4.4MM" in success_text
