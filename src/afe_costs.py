"""Editable AFE cost line items — product-layer rollup over the benchmark templates.

PE feedback (CD3): *"Couldn't figure out how to edit costs for AFE?"* — costs were
a fixed benchmark template rendered read-only inside an expander. This module
seeds an editable line-item frame from the vendored template (``afe.cost_db``)
and re-rolls direct / contingency / total and the tangible-vs-intangible (IDC)
split from WHATEVER the user edited, reproducing ``cost_db.cost_rollup``'s
arithmetic exactly at the unedited seed state (pinned by a product test — same
left-to-right summation, same ``round(pct · direct)`` contingency, same pro-rata
class split). Pure functions, no streamlit; the vendored cost_db stays untouched.
"""
from __future__ import annotations

import pandas as pd

from core import afe_cost_db  # vendored benchmark templates (read-only)

LINE_COLUMNS = ["category", "description", "qty", "unit", "unit_cost_usd",
                "tangible", "vendor"]


def seed_lines(intervention: str) -> pd.DataFrame:
    """The benchmark template's DIRECT lines (contingency excluded — it is
    computed, never typed) as an editable frame: one row per line item with a
    boolean ``tangible`` flag from the vendored cost-class rules."""
    items = [li for li in afe_cost_db.lookup_cost_template(intervention)
             if li.category != "Contingency"]
    return pd.DataFrame(
        [{"category": li.category, "description": li.description,
          "qty": float(li.qty), "unit": li.unit,
          "unit_cost_usd": float(li.unit_cost_usd),
          "tangible": li.cost_class == "tangible",
          "vendor": li.vendor or ""} for li in items],
        columns=LINE_COLUMNS)


def default_contingency_pct(intervention: str) -> float:
    """The vendored per-intervention contingency fraction (0.10 / 0.15)."""
    return float(afe_cost_db.CONTINGENCY_PCT[intervention])


def sanitize_lines(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce an edited frame back to a valid line set. A dynamic-row data editor
    can hand back None/NaN in any cell: bad or negative qty / unit cost become 0
    (a typo must never produce a negative AFE that routes to the wrong authority
    tier), blank categories are labelled, ``tangible`` becomes a real bool."""
    out = df.copy()
    for col in LINE_COLUMNS:
        if col not in out.columns:
            out[col] = False if col == "tangible" else (
                0.0 if col in ("qty", "unit_cost_usd") else "")
    for col in ("qty", "unit_cost_usd"):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).clip(lower=0.0)
    out["tangible"] = out["tangible"].fillna(False).astype(bool)
    for col in ("category", "description", "unit", "vendor"):
        out[col] = out[col].fillna("").astype(str)
    out.loc[out["category"].str.strip() == "", "category"] = "(uncategorized)"
    return out[LINE_COLUMNS]


def rollup_from_lines(df: pd.DataFrame, contingency_pct: float) -> dict:
    """Roll edited line items up exactly the way ``cost_db.cost_rollup`` does:

    * direct = Σ qty·unit_cost (left-to-right, template order)
    * contingency = round(pct · direct)   (the vendored ``_contingency_line``)
    * tangible / intangible split contingency pro-rata by the direct tangible share

    Returns the vendored keys (direct, contingency, total, tangible, intangible)
    plus ``by_category``: an insertion-ordered {category: direct $} for the
    waterfall, built from the EDITED frame — never the template.
    """
    df = sanitize_lines(df)
    totals = [float(q) * float(c) for q, c in zip(df["qty"], df["unit_cost_usd"])]
    direct = sum(totals)
    contingency = float(round(contingency_pct * direct))
    tangible_direct = sum(t for t, tan in zip(totals, df["tangible"]) if tan)
    intangible_direct = direct - tangible_direct
    t_frac = (tangible_direct / direct) if direct else 0.0
    by_category: dict[str, float] = {}
    for cat, tot in zip(df["category"], totals):
        by_category[cat] = by_category.get(cat, 0.0) + tot
    return {
        "direct": direct,
        "contingency": contingency,
        "total": direct + contingency,
        "tangible": tangible_direct + contingency * t_frac,
        "intangible": intangible_direct + contingency * (1 - t_frac),
        "by_category": by_category,
    }
