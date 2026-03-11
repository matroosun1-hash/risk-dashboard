# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run V2 analysis (recommended)
python main_v2.py
python main_v2.py --period 2y

# Run V1 legacy analysis
python main.py
python main.py --stage1
python main.py --stage2
python main.py --period 2y

# Launch Streamlit dashboard
streamlit run dashboard/app.py

# Run tests
python tests/quick_test.py
python tests/test_v2.py
python tests/backtester.py
python tests/diagnose_nan.py   # debug NaN issues in signals
```

**FRED API key required** for liquidity signals. Set `FRED_API_KEY` environment variable before running.

## Architecture

This is a **dual-version quant risk management system** for detecting market crises.

### V1: Two-Stage Early Warning (Legacy)
- `stage1/` — 10 macroeconomic crash indicators (VIX, death cross, yield curve, breadth, etc.) → 0-10 score
- `stage2/` — Sector rotation detection via relative performance pairs
- `action/` — Automated trading recommendations based on combined scores
- Entry point: `main.py`

### V2: Six-Signal Risk Engine (Recommended)
- Entry point: `main_v2.py`
- Pipeline: `data/fetcher.py` downloads 39 tickers → 6 signal modules compute scores → `risk/risk_engine.py` aggregates → `risk/position_sizing.py` generates allocation

**Signal weights** (configured in `config.yaml` under `risk_engine.weights`):
| Signal | Weight | Module |
|--------|--------|--------|
| Macro | 20% | `signals/macro.py` (wraps V1 Stage 1) |
| Liquidity | 20% | `signals/liquidity.py` (FRED + yfinance) |
| Volatility | 20% | `signals/volatility.py` |
| Breadth | 15% | `signals/breadth.py` |
| Cross-Asset | 15% | `signals/cross_asset.py` |
| Regime | 10% | `signals/volatility.py` + `regime/regime_model.py` |

**Risk score → position sizing** lookup table (5 tiers, 0.0–1.0 → Equity/Treasury/Gold/Cash %):
- Defined in `config.yaml` under `position_sizing.allocation_table`
- Applied with volatility targeting (12% target) in `risk/position_sizing.py`

**HMM Regime Detection** (`regime/regime_model.py`):
- 4-state Gaussian HMM using 6 features: SPY return, VIX, yield spread, credit spread, dollar, oil
- States auto-labeled: Expansion / Inflation / Correction / Liquidity Crisis

### Dashboard
- `dashboard/app.py` — V1 Streamlit UI (cyberpunk theme, glassmorphism)
- `dashboard/app_v2.py` — V2 Streamlit UI

### Configuration
All system parameters live in `config.yaml`:
- Ticker universes, signal thresholds, HMM parameters, FRED series IDs, weight overrides
- V1 and V2 settings are in separate top-level keys

### Data Fetching
`data/fetcher.py` uses yfinance with fallback logic for MultiIndex column variations. All signals receive a single DataFrame of OHLCV data and must handle missing tickers gracefully.
