"""src/afe_status.py invariants — the Pipeline Board stepper (PE feedback CD4)."""
from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture(scope="module")
def afe_status(booted):
    from src import afe_status as _st
    return _st


@pytest.fixture(scope="module")
def order(booted):
    return list(booted.afe_tracker.STATUS_ORDER)


def test_stage_states_cover_every_tracked_status(afe_status, order):
    """Every on-path status yields exactly one CURRENT stage, DONE before it,
    UPCOMING after it — over the tracker's REAL machine."""
    for i, status in enumerate(order):
        states = afe_status.stage_states(status, order)
        assert [s for s, _ in states] == order
        assert states[i] == (status, afe_status.CURRENT)
        assert all(st == afe_status.DONE for _, st in states[:i])
        assert all(st == afe_status.UPCOMING for _, st in states[i + 1:])
        assert afe_status.is_on_path(status, order)


def test_rejected_and_unknown_never_raise(afe_status, order):
    """The 0.4.1 regression (STATUS_ORDER.index crash on 'rejected') must stay
    dead: off-path statuses return a full non-CURRENT path and are flagged."""
    for status in ("rejected", "cancelled", "??weird??"):
        states = afe_status.stage_states(status, order)
        assert [s for s, _ in states] == order
        assert all(st == afe_status.UPCOMING for _, st in states)
        assert not afe_status.is_on_path(status, order)


def test_whats_remaining_names_the_gate(afe_status, order):
    """The 'what's remaining' line names the routed approver while an approval is
    still pending, and goes quiet once the approval gate is passed."""
    for status in ("draft", "engineering_review", "finance_review"):
        txt = afe_status.whats_remaining(status, "Operations Manager")
        assert "Operations Manager" in txt
    assert "approval" in afe_status.whats_remaining("finance_review", "VP / Asset Manager")
    assert "execution" in afe_status.whats_remaining("approved", "VP / Asset Manager")
    assert "Variance" in afe_status.whats_remaining("executed", "VP / Asset Manager")
    rej = afe_status.whats_remaining("rejected", "VP / Asset Manager")
    assert "terminal" in rej and "VP" not in rej
    # unknown status: honest, non-crashing text
    assert "not on the tracked" in afe_status.whats_remaining("cancelled", "PE")


def test_stage_durations_from_event_log(afe_status):
    """Realized days per completed stage from an afe_events-shaped frame
    (newest-first, ISO ts) — the current (unfinished) stage is excluded."""
    ev = pd.DataFrame([   # newest first, like tracker.events()
        {"ts": "2026-07-20T09:00:00", "from_status": "engineering_review",
         "to_status": "finance_review", "actor": None, "note": None},
        {"ts": "2026-07-15T09:00:00", "from_status": "draft",
         "to_status": "engineering_review", "actor": None, "note": None},
        {"ts": "2026-07-13T09:00:00", "from_status": None,
         "to_status": "draft", "actor": "Senior PE", "note": "created"},
    ])
    d = afe_status.stage_durations(ev)
    assert d["draft"] == pytest.approx(2.0)
    assert d["engineering_review"] == pytest.approx(5.0)
    assert "finance_review" not in d          # entered, never left


def test_stage_durations_degenerate_inputs(afe_status):
    """Empty / creation-only logs (all 12 seeded demo AFEs) yield no durations."""
    assert afe_status.stage_durations(pd.DataFrame()) == {}
    assert afe_status.stage_durations(None) == {}
    only_created = pd.DataFrame([{"ts": "2026-07-01T08:00:00", "from_status": None,
                                  "to_status": "draft", "actor": None, "note": None}])
    assert afe_status.stage_durations(only_created) == {}
