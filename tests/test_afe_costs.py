"""src/afe_costs.py invariants — editable cost lines (PE feedback CD3).

The load-bearing claim: at the UNEDITED seed state the product-layer rollup is
exactly ``cost_db.cost_rollup`` (every intervention, every key), so making the
lines editable changed nothing until the user actually edits.
"""
from __future__ import annotations

import pandas as pd
import pytest

ROLLUP_KEYS = ("direct", "contingency", "total", "tangible", "intangible")


@pytest.fixture(scope="module")
def afe_costs(booted):
    from src import afe_costs as _ac
    return _ac


def test_seed_rollup_matches_component_for_every_intervention(afe_costs, booted):
    """Unedited seed lines + benchmark contingency == cost_db.cost_rollup exactly,
    for all 8 interventions."""
    core = booted
    for intervention in core.afe_cost_db.COST_TEMPLATES:
        seed = afe_costs.seed_lines(intervention)
        assert list(seed.columns) == afe_costs.LINE_COLUMNS
        assert "Contingency" not in set(seed["category"])
        mine = afe_costs.rollup_from_lines(
            seed, afe_costs.default_contingency_pct(intervention))
        theirs = core.afe_cost_db.cost_rollup(intervention)
        for key in ROLLUP_KEYS:
            assert mine[key] == theirs[key], (intervention, key)
        # the by_category breakdown reconciles to the direct total
        assert sum(mine["by_category"].values()) == pytest.approx(mine["direct"])


def test_edits_flow_through_rollup(afe_costs):
    """Repricing, adding, and removing lines all change the rollup coherently."""
    seed = afe_costs.seed_lines("scale_treatment")
    base = afe_costs.rollup_from_lines(seed, 0.10)

    # reprice a line up
    up = seed.copy()
    up.loc[0, "unit_cost_usd"] = float(up.loc[0, "unit_cost_usd"]) + 10_000.0
    r_up = afe_costs.rollup_from_lines(up, 0.10)
    assert r_up["direct"] == base["direct"] + 10_000.0
    assert r_up["total"] > base["total"]

    # add a tangible line
    add = pd.concat([seed, pd.DataFrame([{
        "category": "Wellhead valve", "description": "replacement", "qty": 1.0,
        "unit": "lump", "unit_cost_usd": 20_000.0, "tangible": True,
        "vendor": "Cameron"}])], ignore_index=True)
    r_add = afe_costs.rollup_from_lines(add, 0.10)
    assert r_add["direct"] == base["direct"] + 20_000.0
    assert r_add["tangible"] > base["tangible"]
    assert "Wellhead valve" in r_add["by_category"]

    # remove a line
    r_rm = afe_costs.rollup_from_lines(seed.iloc[1:], 0.10)
    assert r_rm["direct"] < base["direct"]

    # tangible + intangible always reconcile to the total
    for r in (base, r_up, r_add, r_rm):
        assert r["tangible"] + r["intangible"] == pytest.approx(r["total"])


def test_edit_can_flip_required_approver_tier(afe_costs, booted):
    """Crossing $250k via an edit must re-route the AFE to the next authority
    tier — the Draft AFE 'Routes To' KPI reads the EDITED total."""
    core = booted
    seed = afe_costs.seed_lines("scale_treatment")
    base_total = afe_costs.rollup_from_lines(seed, 0.10)["total"]
    assert 50_000 < base_total <= 250_000
    assert core.afe_tracker.required_approver(base_total) == "Engineering Manager"
    big = seed.copy()
    big.loc[0, "unit_cost_usd"] = 250_000.0        # CTU blowout crosses the tier
    big_total = afe_costs.rollup_from_lines(big, 0.10)["total"]
    assert big_total > 250_000
    assert core.afe_tracker.required_approver(big_total) == "Operations Manager"


def test_sanitize_defends_against_editor_garbage(afe_costs):
    """Dynamic-row editors hand back None/NaN/negatives — the rollup must clamp
    them (a typo must never produce a negative AFE total or crash)."""
    dirty = pd.DataFrame([
        {"category": None, "description": None, "qty": None, "unit": None,
         "unit_cost_usd": None, "tangible": None, "vendor": None},
        {"category": "Rig", "description": "x", "qty": -3.0, "unit": "day",
         "unit_cost_usd": -18_000.0, "tangible": False, "vendor": ""},
        {"category": "Acid", "description": "y", "qty": "2", "unit": "lump",
         "unit_cost_usd": "1000", "tangible": True, "vendor": "MC"},
    ])
    r = afe_costs.rollup_from_lines(dirty, 0.10)
    assert r["direct"] == 2000.0                    # only the valid line counts
    assert r["total"] >= r["direct"] >= 0.0
    assert "(uncategorized)" in r["by_category"]


def test_empty_lines_zero_rollup(afe_costs):
    """Deleting every line is a valid (if odd) state: all-zero rollup, no crash."""
    empty = afe_costs.seed_lines("paraffin_treatment").iloc[0:0]
    r = afe_costs.rollup_from_lines(empty, 0.10)
    assert r["direct"] == r["contingency"] == r["total"] == 0.0
    assert r["tangible"] == r["intangible"] == 0.0
