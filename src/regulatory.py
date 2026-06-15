"""Regulatory Filing drafter — the product's fourth module (deterministic).

Maps data the product already holds onto the key fields of two common upstream
filings, as a **draft worksheet** an operator's regulatory analyst reviews before
transcribing into the official form:

* **Colorado ECMC Form 7** — Operator's Monthly Report of Production, built from a
  well's monthly oil / gas / water / producing-days row (the PDP Screen data).
* **Texas RRC Form W-3** — Plugging Record, built from a P&A AFE in the pipeline
  (operator, well, API, estimated cost, proposed plug date).

Honest framing: these are field-mapping worksheets, NOT certified e-file payloads.
Field names track the public forms; always reconcile against the current official
form revision before submitting. Pure functions, no Streamlit — the view renders.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FilingDraft:
    form: str                      # short form id, e.g. "CO ECMC Form 7"
    title: str                     # human title
    jurisdiction: str              # "Colorado ECMC" | "Texas RRC"
    fields: list[tuple[str, str]]  # ordered (label, value) rows of the worksheet
    notes: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", "",
                 f"**Form:** {self.form}  |  **Jurisdiction:** {self.jurisdiction}",
                 "",
                 "> DRAFT WORKSHEET — field mapping for review, not a certified filing.",
                 "", "| Field | Value |", "|---|---|"]
        lines += [f"| {label} | {value} |" for label, value in self.fields]
        if self.notes:
            lines += ["", "## Notes"] + [f"- {n}" for n in self.notes]
        return "\n".join(lines)


def _fmt_num(x, unit: str = "") -> str:
    try:
        return f"{float(x):,.0f}{(' ' + unit) if unit else ''}"
    except (TypeError, ValueError):
        return "—"


def co_form7_production(*, month: str, operator: str, well_name: str, api: str,
                        field_name: str, oil_bbl, gas_mcf, water_bbl, days,
                        formation: str = "") -> FilingDraft:
    """Colorado ECMC Form 7 (Operator's Monthly Report of Production) worksheet from
    a single well-month of production."""
    rows = [
        ("Reporting period (month)", str(month)),
        ("Operator", operator or "—"),
        ("Well name", well_name or "—"),
        ("API number", api or "—"),
        ("Field / area", field_name or "—"),
        ("Formation / pool", formation or "—"),
        ("Oil produced (bbl)", _fmt_num(oil_bbl, "bbl")),
        ("Gas produced (mcf)", _fmt_num(gas_mcf, "mcf")),
        ("Water produced (bbl)", _fmt_num(water_bbl, "bbl")),
        ("Days produced", _fmt_num(days)),
    ]
    try:
        gor = (float(gas_mcf) * 1000.0 / float(oil_bbl)) if float(oil_bbl) > 0 else 0.0
        rows.append(("Gas-oil ratio (scf/bbl)", _fmt_num(gor, "scf/bbl")))
    except (TypeError, ValueError):
        pass
    return FilingDraft(
        form="CO ECMC Form 7",
        title=f"Monthly Production Report — {well_name or api} ({month})",
        jurisdiction="Colorado ECMC",
        fields=rows,
        notes=[
            "Volumes carry straight from the reported monthly production row.",
            "Reconcile operator number, API-10/14, and pool code against the well's "
            "ECMC record before filing; Form 7 is due by the 28th of the following month.",
        ],
    )


def tx_w3_plugging(*, afe_number: str, well_id: str, api: str, operator: str,
                   field_name: str, estimated_cost_usd: float, plug_date: str,
                   total_depth_ft: int | None = None) -> FilingDraft:
    """Texas RRC Form W-3 (Plugging Record) worksheet from a P&A AFE."""
    td = f"{total_depth_ft:,} ft (est.)" if total_depth_ft else "— (enter TD)"
    rows = [
        ("Source AFE", afe_number or "—"),
        ("Operator", operator or "—"),
        ("Well ID / number", well_id or "—"),
        ("API number", api or "—"),
        ("Field / lease", field_name or "—"),
        ("Proposed plugging date", plug_date or "—"),
        ("Total depth", td),
        ("Estimated plugging cost", f"${estimated_cost_usd:,.0f}"
         if estimated_cost_usd else "—"),
        ("Cement plugs (schedule)", "Surface, intermediate, and across each "
         "open/perforated interval per Statewide Rule 14"),
    ]
    return FilingDraft(
        form="TX RRC Form W-3",
        title=f"Plugging Record (draft) — {well_id} [{afe_number}]",
        jurisdiction="Texas RRC",
        fields=rows,
        notes=[
            "Cost and well identity carry from the approved P&A AFE.",
            "Plug depths, cement volumes, and cementer details must come from the "
            "actual plugging program; Statewide Rule 14 governs plug placement.",
            "File W-3 within 30 days of plugging; a W-3A notice precedes the work.",
        ],
    )
