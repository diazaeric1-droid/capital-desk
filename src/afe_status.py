"""AFE status-journey helpers — the Pipeline Board's per-AFE stepper (CD4).

PE feedback: *"Not very intuitive to go through the AFEs once made and see exactly
what its status is and what is remaining to get it approved."* Pure functions over
the vendored tracker's REAL state machine (``afe.tracker.STATUS_ORDER``:
draft → engineering_review → finance_review → approved → executed, with
``rejected`` as a terminal OFF-path branch). There is no separate "closed-out"
stage in the tracker — actual-vs-AFE close-out reconciliation lives on the
Variance page, so the stepper shows the machine as it truly is, never an
invented stage. No streamlit.
"""
from __future__ import annotations

import pandas as pd

DONE = "done"
CURRENT = "current"
UPCOMING = "upcoming"


def is_on_path(status: str, status_order: list[str]) -> bool:
    """True when the status sits on the draft→executed path (i.e. not a terminal
    off-path state like 'rejected' or an unknown/legacy status)."""
    return status in status_order


def stage_states(status: str, status_order: list[str]) -> list[tuple[str, str]]:
    """[(stage, DONE|CURRENT|UPCOMING)] over the full path. Never raises: an
    off-path status (e.g. 'rejected') returns every stage UPCOMING — the caller
    renders the terminal marker separately (the 0.4.1 non-advanceable guard,
    preserved by design)."""
    if status in status_order:
        i = status_order.index(status)
        return [(s, DONE if j < i else CURRENT if j == i else UPCOMING)
                for j, s in enumerate(status_order)]
    return [(s, UPCOMING) for s in status_order]


def whats_remaining(status: str, required_approver: str) -> str:
    """The explicit "what's remaining to get this approved" line, in plain PE
    language, from the tracker's real machine + the $-routed approver."""
    if status == "draft":
        return (f"engineering review → finance review → approval. Final sign-off "
                f"required: **{required_approver}** (routed by the AFE's $ value).")
    if status == "engineering_review":
        return (f"finance review → approval. Final sign-off required: "
                f"**{required_approver}**.")
    if status == "finance_review":
        return (f"approval — sign-off by **{required_approver}** is the last gate.")
    if status == "approved":
        return "fully approved — execution is all that remains."
    if status == "executed":
        return ("complete — nothing pending; actual-vs-AFE close-out lives on the "
                "Variance page.")
    if status == "rejected":
        return "terminal — nothing pending. Re-draft and resubmit to reopen the ask."
    return (f"'{status}' is not on the tracked review path — nothing to advance "
            "here.")


def stage_durations(events_df: pd.DataFrame) -> dict[str, float]:
    """Realized days spent in each COMPLETED stage, from the immutable event log
    (``afe_events``: ts ISO strings, from_status, to_status — any row order).

    A stage's duration = time between the event that entered it (to_status) and
    the event that left it (from_status); stages entered but never left (the
    current one) are excluded. Empty dict on no events / no completed stages —
    the seeded demo AFEs carry only their creation event, so durations appear
    once an AFE is advanced live."""
    if events_df is None or events_df.empty or "ts" not in events_df.columns:
        return {}
    ev = events_df.copy()
    ev["_ts"] = pd.to_datetime(ev["ts"], errors="coerce")
    ev = ev.dropna(subset=["_ts"]).sort_values("_ts", kind="stable")
    entered: dict[str, pd.Timestamp] = {}
    out: dict[str, float] = {}
    for _, r in ev.iterrows():
        frm = r.get("from_status")
        if isinstance(frm, str) and frm in entered:
            days = (r["_ts"] - entered.pop(frm)).total_seconds() / 86400.0
            out[frm] = out.get(frm, 0.0) + max(days, 0.0)
        to = r.get("to_status")
        if isinstance(to, str) and to:
            entered[to] = r["_ts"]
    return out
