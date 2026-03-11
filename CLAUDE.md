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

## Work Log

> 새로운 작업을 할 때마다 아래에 날짜와 내용을 추가할 것.

### 2026-03-12 — 모바일 최적화 + Streamlit Cloud 배포
- `dashboard/app.py`: 모바일 반응형 CSS 추가 (media query, 컬럼 세로 스택, 지표 행 HTML 클래스화)
- `dashboard/app_v2.py`: 상시 표시 전용으로 전면 재작성
  - 게이지 차트 (Plotly) + 6개 시그널 바 (HTML/CSS)
  - 세로: 게이지만 / 가로: 게이지 + 시그널 나란히
  - Streamlit 기본 UI 숨김 (`#MainMenu, header, footer`)
  - 60초 자동 새로고침 (`time.sleep(60)` + `st.rerun()`)
  - Windows cp949 인코딩 충돌 수정 (stdout UTF-8 강제)
- `.gitignore` 생성
- GitHub 배포: `matroosun1-hash/risk-dashboard` (Public)
- Streamlit Cloud 배포: `dashboard/app_v2.py` 메인 파일로 설정
- 배포 URL: https://appv2pythisfiledoesnotexistappurloptionalrisk-dashboard-buuvtz.streamlit.app/

### 2026-03-12 — 후행성 개선: 속도 기반 선행 감지

- `stage1/indicators.py` — `check_death_cross()`, `check_spy_below_200sma()` 수정
- **방식**: 이탈 확정(score 1.0) 외에 수렴 속도가 빠를 때 선행 경고(score 0.5) 추가
  - 갭이 3% 이내 + 10일간 수렴속도 > 임계값 → 0.5점 선행 경고
  - 데스크로스: velocity < -1%/10d, SPY 200일선: velocity < -1.5%/10d
- 테스트 결과: SPY 200일선 지표가 실시간으로 0.5 선행 경고 발동 확인 (675 → 655, 3% 이내)

#### 트러블슈팅
- `<meta>` + `<style>` 동시 사용 시 Streamlit이 `<style>` 제거 → `<meta>` 제거로 해결
- HTML 4칸 들여쓰기 → Markdown 코드블록으로 인식 → 한 줄 문자열로 변경
- `fetcher.py` 이모지 print → Windows cp949 UnicodeEncodeError → stdout UTF-8 강제 설정
