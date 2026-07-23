"""Round-2 workflow/guidance coverage: next_step handoffs, the SPE exceedance
relabel, the shared type-typical uplift map, the well_label formatter, the
product-local example diagnosis, and the widget-owned-key hygiene pins."""
from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


# ---- SPE exceedance convention (display-level relabel, math untouched) ---------

def test_program_montecarlo_p10_is_the_high_case(booted):
    """Portfolio convention pin: Pxx = probability of exceedance — the LARGER NPV
    percentile is labeled P10 (upside), the smaller P90 (downside)."""
    from views import common
    core = booted
    txt = core.backlog_csv_text()
    econ = core.capital_economics.economics_frame(core.load_backlog(), 70.0, 0.10)
    prog, _ = core.optimize_program(econ, 60e6, 170.0)
    mc = common.program_montecarlo(txt, 70.0, 0.10, tuple(sorted(prog.selected_ids)))
    assert mc["p10"] > mc["p90"], "SPE exceedance: p10 must be the high case"
    assert mc["p10"] >= mc["p50"] >= mc["p90"]


def test_methods_page_carries_the_suite_convention_sentence():
    src = (ROOT / "views/about_methods.py").read_text()
    assert ("Pxx = probability of exceedance — P10 is the high case, "
            "P90 the low case") in src


def test_draft_and_optimizer_label_downside_as_p90():
    """The 10th-percentile engine outputs must be DISPLAYED as P90 (downside)."""
    draft = (ROOT / "views/authorize_draft.py").read_text()
    opt = (ROOT / "views/program_optimizer.py").read_text()
    assert "P90 Gross NPV (Downside)" in draft and "P10 Gross NPV (Upside)" in draft
    assert "P10 Gross NPV (Downside)" not in draft   # the pre-round-2 mislabel
    assert "P90 NPV (Downside)" in opt and "P10 NPV (Upside)" in opt
    assert "P10 NPV (Downside)" not in opt


# ---- shared helpers -------------------------------------------------------------

def test_well_label_formats_suite_ids_and_passes_through_others(booted):
    from views import common
    lbl = common.well_label("well_017")
    assert lbl.startswith("well_017 · ") and "(" in lbl        # name + lift
    assert common.well_label("05-123-40438") == "05-123-40438"  # Colorado API raw
    assert common.well_label("MY-BYOD-1") == "MY-BYOD-1"


def test_typical_uplift_single_source(booted):
    """The Pipeline Board and the Draft AFE anchor caption share ONE uplift map
    (views/common.py) — the board module must not re-define the literals."""
    from views import common
    pipe_src = (ROOT / "views/authorize_pipeline.py").read_text()
    assert "common.TYPICAL_UPLIFT_BOPD" in pipe_src
    assert '"esp_swap": 150.0' not in pipe_src          # no second copy of the map
    draft_src = (ROOT / "views/authorize_draft.py").read_text()
    assert "common.TYPICAL_UPLIFT_BOPD" in draft_src
    assert common.TYPICAL_UPLIFT_BOPD["esp_swap"] == 150.0


def test_next_step_degrades_to_caption_without_page_registry(booted):
    """Outside st.navigation (bare AppTest), next_step must render the guidance
    as a caption — never crash; unknown paths also degrade honestly."""
    script = (
        f"import sys; sys.path.insert(0, {str(ROOT)!r})\n"
        "from views import common\n"
        "common.next_step('views/authorize_draft.py', '→ Build the AFE (Draft AFE)',\n"
        "                 help='carry the prose')\n"
        "common.next_step('views/does_not_exist.py', '→ Nowhere (Nope)')\n"
    )
    at = AppTest.from_string(script, default_timeout=120)
    at.run()
    assert not at.exception
    captions = " ".join(c.value for c in at.caption)
    assert "→ Build the AFE (Draft AFE)" in captions and "carry the prose" in captions
    assert "→ Nowhere (Nope)" in captions


def test_every_seam_has_a_next_step_call():
    """Every seam of the capital loop carries a clickable handoff (CD-WO-1) —
    no bold page names without a link."""
    seams = {
        "views/authorize_draft.py": "views/authorize_pipeline.py",
        "views/authorize_pipeline.py": "views/authorize_variance.py",
        "views/authorize_variance.py": "views/authorize_draft.py",
        "views/program_backlog.py": "views/program_optimizer.py",
        "views/program_optimizer.py": "views/program_frontier.py",
        "views/screen_pdp.py": "views/authorize_draft.py",
        "views/file_regulatory.py": "views/authorize_draft.py",
    }
    for view, target in seams.items():
        src = (ROOT / view).read_text()
        assert "common.next_step(" in src, f"{view}: no next_step handoff"
        assert target in src, f"{view}: handoff does not target {target}"


# ---- widget-owned-key hygiene (the OC production-crash class) -------------------

def test_screener_does_not_own_or_prewrite_well_id():
    """screen_pdp must use the index= pattern: no selectbox keyed 'well_id', and
    no pre-widget ss['well_id'] fallback write above one (AppTest cannot catch
    this class at runtime — pin it in source)."""
    src = (ROOT / "views/screen_pdp.py").read_text()
    assert 'key="well_id"' not in src
    assert "index=_idx" in src


def test_pipeline_cache_tokens_are_hashed():
    """st.cache_data EXCLUDES underscore-prefixed args from the cache key — a
    `_token` parameter pins the first tracker read forever and the board goes
    stale after Advance/Submit. Pin the non-underscore signature."""
    src = (ROOT / "views/authorize_pipeline.py").read_text()
    assert "def _pipeline(token: int)" in src
    assert "def _pipeline(_token" not in src
    assert "def _events(afe_number: str, token: int)" in src


# ---- product-local example diagnosis (the out-of-the-box trend path) ------------

def test_product_example_diagnosis_resolves_end_to_end(booted):
    """The shipped example must validate as a diagnosis AND resolve to bundled
    production history, so the trend panel works out-of-the-box (the vendored
    ED-xxxH examples deliberately do not)."""
    core = booted
    p = core.PRODUCT_EXAMPLES_DIR / "well_diagnosis_well_017.json"
    assert p.exists()
    payload = json.loads(p.read_text())
    diag = core.afe_models.AFEDiagnosis.from_pe_copilot(payload)
    assert diag.well_id == "well_017"
    assert diag.intervention in core.afe_cost_db.COST_TEMPLATES
    from src import pdp
    import io
    tidy = pdp.load_pdp_csv(io.StringIO(core.SYNTH_FLEET_CSV.read_text()))
    assert pdp.find_well(tidy, "well_017") == "well_017"
