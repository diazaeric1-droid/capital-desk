"""Capital Desk — the capital meeting in one product.

Authorize the work (AFE pipeline + drafting), optimize the program (MILP capital
allocation), screen the deal (PDP quick-look on real Colorado data). Built on the
vendored component apps loaded in-process by ``core.py``; this file owns ONLY the
product chrome: page config, the global price-deck sidebar, and navigation.
"""
from __future__ import annotations

import streamlit as st

import product_theme as pt
import core

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
ss.setdefault("data_source", "Bundled demo data")
ss.setdefault("anthropic_key", "")    # BYOK, session-only — never stored

# ---- global sidebar: the price deck every module prices against ----------------
with st.sidebar:
    st.markdown("**Price Deck**")
    st.slider("Oil price ($/bbl)", 30.0, 120.0, step=1.0, key="oil_price")
    st.slider("NRI (revenue share)", 0.50, 1.00, step=0.01, key="nri")
    st.slider("Discount rate (effective-annual)", 0.05, 0.25, step=0.005,
              key="discount",
              help="The suite convention: DF(m) = (1+r)^(m/12). A 10% input means "
                   "10% per YEAR — not the 10.47% that monthly compounding implies.")
    st.slider("Severance + ad valorem (%)", 0.0, 15.0, step=0.5,
              key="severance_pct",
              help="Production-tax drag on net revenue. Applied to BOTH the AFE net "
                   "economics (Authorize) and the PDP screen (Screen) so the two value "
                   "barrels the same way. ~4.6% TX severance; ~7–8% all-in with ad valorem.")
    st.text_input("Anthropic API key (optional)", type="password",
                  key="anthropic_key",
                  help="Bring your own key — session-only, never stored. Powers the "
                       "LLM AFE narrative; every number on every page is "
                       "deterministic and needs no key.")
    st.divider()
    pt.product_switcher("capital")

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
