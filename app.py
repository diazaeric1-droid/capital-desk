"""Capital Desk — the capital meeting in one product.

Authorize the work (AFE pipeline + drafting), optimize the program (MILP capital
allocation), screen the deal (PDP quick-look on real Colorado data). Built on the
vendored component apps loaded in-process by ``core.py``; this file owns ONLY the
product chrome: page config, the global price-deck sidebar, and navigation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# --- warm-container module self-heal -----------------------------------------------
# Streamlit Cloud reuses the Python process across redeploys, so a cached OLD copy of
# one of OUR modules in sys.modules (or a stale .pyc) can lack symbols added in a newer
# commit -> AttributeError at run (e.g. views.common.combined_variance_frames). Drop our
# bytecode and evict every product-owned module so the imports below + the view pages
# reload from THIS commit's source. Gated once per session (Streamlit re-runs the whole
# script on every interaction; re-evicting each time would re-run the alias loader for
# no benefit). A fresh session after a redeploy heals cleanly. Skipped under pytest,
# where modules are already fresh from source and evicting would break the cross-test
# module-identity invariants.
if "pytest" not in sys.modules and not st.session_state.get("_capital_healed"):
    import shutil as _sh_heal
    for _pyc in HERE.rglob("__pycache__"):
        _sh_heal.rmtree(_pyc, ignore_errors=True)
    _OWN = ("core", "product_theme", "theme", "fleet_registry",
            "afe", "capital", "views", "src")
    for _m in list(sys.modules):
        if any(_m == p or _m.startswith(p + ".") for p in _OWN):
            sys.modules.pop(_m, None)
    st.session_state["_capital_healed"] = True

import product_theme as pt  # noqa: E402
import core  # noqa: E402  (re-loads the afe/capital aliases)

# Page config + theme CSS — FIRST, exactly once. Views never call set_page_config.
pt.setup_product("capital")

# Regenerate gitignored runtime artifacts (AFE tracker DB; backlog if wiped).
core.bootstrap(log=lambda *_a, **_k: None)

# ---- session-state contract (every view reads these; set ONLY here) -----------
ss = st.session_state
ss.setdefault("oil_price", 70.0)      # realized oil price, $/bbl
ss.setdefault("nri", 0.80)            # net revenue interest (revenue share)
ss.setdefault("discount", 0.10)       # effective-annual discount rate
ss.setdefault("severance_pct", 7.5)   # severance + ad valorem (%), AFE + PDP alike
ss.setdefault("well_id", "")          # PDP screener drill-down selection
ss.setdefault("anthropic_key", "")    # BYOK, session-only — never stored

# ---- global sidebar: switcher on top, then the price deck every module prices
# against. Deck controls are EXACT TYPED number_inputs (round-1 PE feedback: a
# $68.50 deck must be enterable, not slider-approximated); portfolio-standard
# ranges/labels so a deck quoted in a sibling product reproduces here.
with st.sidebar:
    pt.product_switcher("capital")
    st.markdown("**Price Deck**")
    from views import common as _common   # canonical NRI help string (product-local)
    st.number_input("Oil price ($/bbl)", 0.0, 500.0, step=5.0, key="oil_price",
                    help="Realized oil price every module prices against — type an "
                         "exact deck (e.g. 68.50). Drives Authorize, Program, and "
                         "Screen alike.")
    st.number_input("NRI (net revenue interest)", 0.0, 1.0, step=0.01, key="nri",
                    help=_common.NRI_HELP)
    st.number_input("Discount rate (effective-annual)", 0.0, 1.0, step=0.005,
                    key="discount",
                    help="The suite convention: DF(m) = (1+r)^(m/12). A 10% input means "
                         "10% per YEAR — not the 10.47% that monthly compounding implies.")
    st.number_input("Severance + ad valorem (%)", 0.0, 15.0, step=0.5,
                    key="severance_pct",
                    help="Production-tax drag on net revenue. Applied to BOTH the AFE net "
                         "economics (Authorize) and the PDP screen (Screen) so the two value "
                         "barrels the same way. ~4.6% TX severance; ~7–8% all-in with ad valorem.")
    st.text_input("Anthropic API key (optional)", type="password",
                  key="anthropic_key",
                  help="Bring your own key — session-only, never stored. Powers the "
                       "LLM AFE narrative; every number on every page is "
                       "deterministic and needs no key.")

# ---- navigation (built from core.NAV — the single source of truth) -------------
_first = True
nav_spec: dict[str, list[st.Page]] = {}
for section, pages in core.NAV.items():
    entries = []
    for title, path, icon in pages:
        entries.append(st.Page(path, title=title, icon=icon, default=_first))
        _first = False
    nav_spec[section] = entries

st.navigation(nav_spec).run()
