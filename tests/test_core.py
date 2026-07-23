"""Core loader, bootstrap, and navigation-design tests."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_aliases_import(booted):
    """Both vendored apps load under their aliases; key entry points resolve."""
    core = booted
    assert "afe" in sys.modules and "capital" in sys.modules
    assert core.afe_cost_db.total_estimate("acid_stimulation") > 0
    assert callable(core.capital_optimizer.optimize)
    assert core.capital_projects.REQUIRED_CSV_COLUMNS[0] == "project_id"
    assert core.AFE_VERSION == "0.6.2"
    assert core.CAPITAL_VERSION == "0.2.3"


def test_econ_core_reachable_and_effective_annual_lock(booted):
    """Invariant (d): the suite's effective-annual discounting lock.

    DF(12 months) at 10% must be EXACTLY 1.10 — i.e. a 10% input means 10% per
    year ((1+r)^(m/12)), not the 10.47% that monthly compounding would imply."""
    core = booted
    assert core.econ_core is sys.modules["afe.econ_core"]
    df = core.econ_core.discount_factors([12], 0.10)
    assert float(df[0]) == 1.10


def test_core_importable_without_streamlit(root):
    """core.py (and the whole alias-loaded component stack) must import headless."""
    code = (
        "import sys; sys.modules['streamlit'] = None\n"   # any 'import streamlit' now fails
        "import core\n"
        "assert core.econ_core.DAYS_PER_MONTH > 30\n"
        "print('OK')\n"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=root,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "OK" in out.stdout


def test_bootstrap_regenerates_tracker(booted):
    """The gitignored tracker DB reseeds itself (12 demo AFEs) when missing."""
    core = booted
    if core.TRACKER_DB.exists():
        core.TRACKER_DB.unlink()
    core.ensure_tracker(log=lambda *_: None)
    assert core.TRACKER_DB.exists()
    df = core.pipeline_df()
    assert len(df) == 12
    assert {"afe_number", "status", "required_approver",
            "days_in_status"} <= set(df.columns)


def test_backlog_committed_and_realistic(booted):
    """The 45-project backlog ships committed, loads through the component's own
    loader, and keeps its honest framing: 13 of 45 sub-economic at the $70 deck."""
    core = booted
    assert core.BACKLOG_CSV.exists()
    projects = core.load_backlog()
    assert len(projects) == 45
    econ = core.capital_economics.economics_frame(projects, 70.0, 0.10)
    assert int((econ["risked_npv_usd"] <= 0).sum()) == 13


def test_navigation_matches_design(booted):
    """The page map is the product design: 5 sections, 10 pages, a DISTINCT
    material icon per page (no emoji, no repeated per-section icon), and every
    view file exists."""
    core = booted
    assert list(core.NAV) == ["Authorize", "Program", "Screen", "File", "Data"]
    titles = {sec: [t for t, _p, _i in pages] for sec, pages in core.NAV.items()}
    assert titles["Authorize"] == ["Pipeline Board", "Draft AFE", "Variance"]
    assert titles["Program"] == ["Backlog", "Optimizer", "Frontier & Sensitivity"]
    assert titles["Screen"] == ["PDP Screener"]
    assert titles["File"] == ["Regulatory Filing"]
    assert titles["Data"] == ["Sources & BYOD", "Methods & Limitations"]
    expected_icons = {
        "Pipeline Board": ":material/approval:",
        "Draft AFE": ":material/edit_document:",
        "Variance": ":material/difference:",
        "Backlog": ":material/list_alt:",
        "Optimizer": ":material/tune:",
        "Frontier & Sensitivity": ":material/ssid_chart:",
        "PDP Screener": ":material/query_stats:",
        "Regulatory Filing": ":material/description:",
        "Sources & BYOD": ":material/database:",
        "Methods & Limitations": ":material/fact_check:",
    }
    seen_icons = []
    for _sec, pages in core.NAV.items():
        for title, path, icon in pages:
            assert (ROOT / path).exists(), f"missing view file for {title}: {path}"
            assert icon == expected_icons[title], f"{title}: unexpected icon {icon}"
            assert icon.startswith(":material/")  # no emoji in nav
            seen_icons.append(icon)
    assert len(seen_icons) == len(set(seen_icons)), "nav icons must be distinct"
