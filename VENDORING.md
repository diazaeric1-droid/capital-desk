# Vendoring record

Capital Desk vendors its component apps as **plain directories** under `apps/`
(the pe-pipeline pattern) so a Streamlit Cloud deploy is a single self-contained
clone — no submodules, no per-app virtualenvs. `core.py` loads each app's `src/`
package under a distinct alias via `importlib`
(`afe` ← afe-copilot, `capital` ← capital-optimizer).

Component repos are read-only sources: **nothing inside `apps/` is ever edited.**

## What was vendored

| Source repo | Version | Vendored at | Import alias | Transformation |
|---|---|---|---|---|
| `afe-copilot` | v0.6.2 (pyproject + CHANGELOG) | `apps/afe-copilot/` | `afe` | **None — byte-identical** |
| `capital-optimizer` | v0.2.3 | `apps/capital-optimizer/` | `capital` | **None — byte-identical** |

Both packages already use package-relative imports throughout `src/`
(`from .economics import …`), so **no import rewriting was required** — the
alias loader resolves them as-is. (Only the components' `demo/app.py` files use
absolute `from src.x import y` imports; those demos are not loaded by Capital
Desk — their functionality is re-implemented in `views/` against the alias.)

Copy exclusions (cache/junk only, never source): `.git`, `.venv`,
`__pycache__`, `.pytest_cache`, `*.egg-info`, `htmlcov`, `.ruff_cache`.

Verified with:

```bash
diff -r ../afe-copilot        apps/afe-copilot        -x .git -x .venv -x __pycache__ -x .pytest_cache -x '*.egg-info' -x htmlcov -x .ruff_cache -x pipeline.sqlite -x drafts
diff -r ../capital-optimizer  apps/capital-optimizer  -x .git -x .venv -x __pycache__ -x .pytest_cache -x '*.egg-info' -x htmlcov -x .ruff_cache
```

Both return no differences.

Note: `afe-copilot/src/__init__.py` carries `__version__ = "0.6.1"` while its
`pyproject.toml` and CHANGELOG say 0.6.2 — an upstream inconsistency, vendored
as-is (byte-identical wins). Capital Desk cites v0.6.2 per pyproject/CHANGELOG.

## Data mirrors

| Data | Source | Mirrored at | Provenance |
|---|---|---|---|
| Colorado ECMC monthly production (28 DJ Basin wells, 2016–2026) | `production-engineer-copilot/data/real/colorado/` (production.csv + README.md + fetch_colorado.py) | `data/real/colorado/` | **REAL public data** — Colorado ECMC (formerly COGCC) records, redistributable; rebuildable via `fetch_colorado.py` |
| 45-project capital backlog | committed inside the vendored component | `apps/capital-optimizer/data/synthetic/projects.csv` | Synthetic (defensible Permian ranges; 13/45 sub-economic at the $70 deck); generator beside it |

Verified with `diff -r ../production-engineer-copilot/data/real/colorado data/real/colorado` — identical.

## Presentation layer (byte-identical copies at repo root)

| File | Copied from |
|---|---|
| `product_theme.py` | `_shared/product_theme.py` |
| `theme.py` | `well-gas-lift-advisor/demo/theme.py` |
| `fleet_registry.py` | `well-gas-lift-advisor/demo/fleet_registry.py` |
| `.streamlit/config.toml` | `well-gas-lift-advisor/.streamlit/config.toml` |

## Shared economics kernel

`afe.econ_core` (vendored inside afe-copilot) is the suite-wide DCF kernel.
`core.py` re-exports it as `econ_core` — the pipeline_core precedent — and the
new PDP Screener (`src/pdp.py`) discounts **only** through it, so all three
modules use one effective-annual convention: `DF(m) = (1+r)^(m/12)`
(`discount_factors([12], 0.10) == 1.10` exactly, pinned by a product test).

## Runtime artifacts (gitignored, regenerated on first run)

- `data/state/tracker.sqlite` — the AFE pipeline tracker, seeded with 12 demo
  AFEs by `core.ensure_tracker()` (mirrors the AFE demo's first-run seeding at a
  product-local path).
- `apps/capital-optimizer/data/synthetic/projects.csv` ships **committed**; if
  ever deleted, `core.ensure_backlog()` regenerates it with the component's own
  generator.
