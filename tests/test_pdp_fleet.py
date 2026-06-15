"""The suite-shared 100-well synthetic fleet (the PDP Screener's default source)
is committed, schema-valid, deterministic, shares the fleet-registry identity used
by the sibling products, and screens into a realistic — fully fit-able — PDP table.
"""
from __future__ import annotations

import importlib.util
import io

import pytest


def _tidy(core):
    from src import pdp
    return pdp.load_pdp_csv(io.StringIO(core.SYNTH_FLEET_CSV.read_text()))


def test_synth_fleet_committed_and_schema_valid(booted):
    core = booted
    from src import pdp
    assert core.SYNTH_FLEET_CSV.exists(), "fleet_pdp.csv must be committed for instant cold-start"
    tidy = _tidy(core)
    for col in pdp.REQUIRED_PDP_COLUMNS:
        assert col in tidy.columns
    assert tidy["well_id"].nunique() == 100


def test_synth_fleet_fits_with_realistic_heterogeneity(booted):
    core = booted
    from src import pdp
    table, skipped = pdp.screen_wells(_tidy(core), 70.0, 12.0, 0.80, 0.075, 0.10)
    assert len(table) == 100 and not skipped          # every well fits (none dropped)
    assert table["r_squared"].median() >= 0.85        # clean MAJORITY, not all
    # heterogeneity: a real fleet is a mix of models, fit qualities, and values —
    # not 100 identical perfect declines.
    assert set(table["model"]) == {"exponential", "hyperbolic"}
    assert (table["r_squared"] < 0.5).sum() >= 1      # ≥1 low-confidence well to flag
    assert table["pv10_usd"].min() >= 0
    assert table["pv10_usd"].max() > 3 * max(table["pv10_usd"].median(), 1)
    assert table["n_months"].min() >= pdp.MIN_FIT_POINTS


def test_synth_fleet_shares_registry_identity(booted):
    core = booted
    import fleet_registry
    tidy = _tidy(core)
    ids = set(tidy["well_id"])
    assert {"well_001", "well_013", "well_100"} <= ids
    # the well_name carried in the data matches the shared registry identity
    name = tidy.loc[tidy["well_id"] == "well_013", "well_name"].iloc[0]
    assert name == fleet_registry.get("well_013").name


def test_synth_fleet_regenerates_byte_identical(booted):
    """The committed CSV equals a fresh deterministic regeneration (no wall-clock)."""
    core = booted
    spec = importlib.util.spec_from_file_location(
        "gen_pdp_fleet", core.SYNTH_FLEET_GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    regenerated = mod.build().to_csv(index=False)
    assert regenerated == core.SYNTH_FLEET_CSV.read_text()


def test_gas_adds_value_and_oil_only_is_backward_compatible(booted):
    """Gas at a positive price lifts total PV10 above oil-only; gas_price=0 reproduces
    the oil-only number exactly (so the oil-only contract is unchanged)."""
    core = booted
    from src import pdp
    tidy = _tidy(core)
    assert "gas_mcf" in tidy.columns
    oil_only, _ = pdp.screen_wells(tidy, 70.0, 12.0, 0.80, 0.075, 0.10)
    with_gas, _ = pdp.screen_wells(tidy, 70.0, 12.0, 0.80, 0.075, 0.10,
                                   gas_price_per_mcf=3.0)
    assert with_gas["pv10_usd"].sum() > oil_only["pv10_usd"].sum()
    assert (with_gas["pv10_gas_usd"] >= 0).all()
    # oil component is identical whether or not gas is priced
    assert with_gas["pv10_oil_usd"].sum() == pytest.approx(oil_only["pv10_usd"].sum(), rel=1e-9)
    # BOE ≥ BOPD (gas is additive on an energy basis)
    assert (with_gas["current_boepd"] >= with_gas["current_bopd"]).all()


def test_severance_reduces_pv10_monotonically(booted):
    """Higher severance lowers net PV10 (a real tax drag, not cosmetic)."""
    from src import pdp
    tidy = _tidy(booted)
    lo, _ = pdp.screen_wells(tidy, 70.0, 12.0, 0.80, 0.00, 0.10)
    hi, _ = pdp.screen_wells(tidy, 70.0, 12.0, 0.80, 0.15, 0.10)
    assert hi["pv10_usd"].sum() < lo["pv10_usd"].sum()


def test_terminal_decline_caps_high_b_eur_and_spares_exponential(booted):
    """Dmin (modified-hyperbolic) trims a fat-tailed high-b hyperbolic well's EUR but
    leaves an exponential well untouched — the standard terminal-decline guard."""
    from src import pdp
    hyp = pdp.WellFit("H", "hyperbolic", 800.0, 1.4, 1.2, 0.0, 0.99, 36, 35.0, 120.0)
    eur_no = pdp.remaining_eur(hyp, dmin_annual=0.0)
    eur_dmin = pdp.remaining_eur(hyp, dmin_annual=0.08)
    assert eur_dmin < eur_no                                  # terminal decline trims EUR
    exp = pdp.WellFit("E", "exponential", 500.0, 0.5, 0.0, 0.0, 0.99, 24, 23.0, 150.0)
    assert pdp.remaining_eur(exp, dmin_annual=0.0) == pytest.approx(
        pdp.remaining_eur(exp, dmin_annual=0.08), rel=1e-9)   # exponential unaffected


def test_resolve_pdp_defaults_to_synthetic(booted):
    """The default/synthetic label resolves to the synthetic fleet; the real label
    resolves to Colorado — the source toggle is honest about provenance."""
    from views import common
    synth_text, synth_label, synth_byod = common.resolve_pdp(common.PDP_SYNTH_LABEL)
    assert synth_label == common.PDP_SYNTH_LABEL and not synth_byod
    assert "well_013" in synth_text
    real_text, real_label, real_byod = common.resolve_pdp(common.PDP_REAL_LABEL)
    assert real_label == common.PDP_REAL_LABEL and not real_byod
    assert real_text != synth_text
