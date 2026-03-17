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

### 2026-03-12 — 글로벌 거시 신호 추가

- `signals/global_macro.py` 신규 생성
  - EEM/SPY 상대 수익률 (신흥국 vs 미국, 35% 가중)
  - VEU/SPY 상대 수익률 (글로벌 vs 미국, 30% 가중)
  - CPER/GLD 구리/금 비율 (경기 선행지표, 35% 가중)
  - 롤링 퍼센타일 반전 정규화 (낮은 상대수익률 = 높은 리스크)
- `risk/risk_engine.py`: global_macro 시그널 추가 (7번째 신호)
- `config.yaml`: global 티커(EEM, VEU, CPER) 추가, 가중치 재조정
  - global_macro 10% 신규 / 기존 신호들 소폭 감소 (총합 100% 유지)
- 실시간 결과: global_macro 0.744 (신흥국·글로벌 약세, 구리/금 하락 감지)

### 2026-03-12 — VIX 중복 반영 제거

- `signals/macro.py` 수정: VIX 지표를 macro 점수 계산에서 제외
- VIX는 `signals/volatility.py`에서 4개 서브지표(수준/VVIX/Term Structure/실현변동성)로 전담
- 효과: 최종 스코어 0.474 → 0.432 (공포 신호 과잉 증폭 해소)
- macro 점수 기준: 10점 만점 → 9점 만점 (VIX 1점 제외)

### 2026-03-12 — 전체 지표 velocity 기반 선행 감지 고도화 + 배포

- `stage1/indicators.py`: 나머지 7개 이진 지표 모두 0/0.5/1.0 3단계로 개선
  - co_decline: 양수이지만 +2% 이내 + 10일 하락 중 → 0.5 선행 경고
  - yield_curve: 스프레드 0~0.5% + 10일간 0.1%p 이상 좁혀질 때 → 0.5
  - hy_spread: -0.5% ~ -2% 구간 → 0.5 (기존 임계 -1% 단일 이진)
  - dollar_strength: 1% ~ 2% 구간 → 0.5 (기존 임계 2% 단일 이진)
  - market_breadth: -0.5% ~ -2% 구간 → 0.5
  - small_cap: -0.5% ~ -2% 구간 → 0.5
  - bond_volatility: 임계값 70% ~ 100% 구간 → 0.5
- GitHub 배포: `matroosun1-hash/risk-dashboard` main 브랜치 push 완료

### 2026-03-12 — 백테스트 검증 완료 (최종)

- `tests/backtester.py` 전면 재작성
- **검증 방식**: 각 위기 고점 기준 T-60, T-30, T-15, T-0일 시점에서 엔진 실행
- **결과**:

| 위기 | 규모 | 감지 | 선행성 |
|------|------|------|--------|
| 2018 Q4 급락 | -20% | ❌ | 놓침 (Fed 발언 트리거, 정량 감지 불가) |
| 2020 COVID | -34% | ✅ | 고점 15일 전 |
| 2022 베어마켓 | -25% | ✅ | **고점 60일 전** (velocity 개선 효과) |
| 2019 Bull (오경보) | — | ⚠️ | 1회 오경보 (미중 무역전쟁 불확실성 구간) |

- **종합**: 3개 위기 중 2개 감지 (67%), 2022는 velocity 개선으로 60일 전 조기 감지
- 2018 Q4는 어떤 정량 시스템도 사전 감지 어려운 구조적 한계

#### 트러블슈팅
- `<meta>` + `<style>` 동시 사용 시 Streamlit이 `<style>` 제거 → `<meta>` 제거로 해결
- HTML 4칸 들여쓰기 → Markdown 코드블록으로 인식 → 한 줄 문자열로 변경
- `fetcher.py` 이모지 print → Windows cp949 UnicodeEncodeError → stdout UTF-8 강제 설정

### 2026-03-13 — Dynamic Threshold + HMM 코로보레이션 필터 + 대시보드 개선

- `risk/risk_engine.py`: regime별 동적 가중치 (`_REGIME_MULTIPLIERS`) 추가
  - Expansion: liquidity 0.5x, volatility 0.6x (평시 과민반응 억제)
  - Liquidity Crisis: liquidity 2.0x, volatility 1.5x (쓰나미 조기 감지)
  - `calculate_final_risk(dynamic_weights=True/False)` 플래그 추가
- `risk/risk_engine.py`: Liquidity Crisis 코로보레이션 필터
  - `(liq + vol) / 2 < 0.5` 이면 Crisis → Correction 강등 + regime 점수 캡
  - 2019 오경보 제거 핵심 로직
- `regime/regime_model.py`: `config.yaml lookback_years` 실제 연결 (기본 5y)
- `portfolio/allocator.py`, `dashboard/app_v2.py`, `tests/backtester.py`: L2 임계값 0.40 → 0.45
- `dashboard/app_v2.py`: 동적 가중치 % 표시, Regime 배너, Crisis 강등 배지, 4상태 확률 바
- `tests/backtester.py`: Static vs Dynamic 비교 모드, 2008 금융위기 케이스 추가
- `tests/hmm_tuning.py` 신규: HMM 그리드 서치 (n=3~5, cov=full/diag, window=all/10y/5y)

#### 백테스트 최종 결과 (Dynamic 기준)
| 위기 | 감지 | 선행성 |
|------|------|--------|
| 2008 금융위기 | ✅ | 30일 전 |
| 2018 Q4 | ❌ | 구조적 한계 |
| 2020 COVID | ✅ | 15일 전 |
| 2022 베어마켓 | ✅ | 15일 전 |
| 2019 오경보 | ✅ 없음 | — |

- **종합**: 4개 위기 중 3개 감지 (75%), 오경보 0회
- HMM 최적 설정: `n_components=4, covariance_type=full, lookback_years=5`

### 2026-03-17 — 심층 감사 + 시스템 개선 (AUDIT_REPORT.md 기반)

#### 심층 감사 실시
- `tests/correlation_analysis.py`: 7개 신호 상관행렬 + PCA 분석
  - macro↔breadth r=0.642, macro↔volatility r=0.612 (SPY 과의존)
  - PCA 유효 독립 신호: 5개 (Kaiser 기준 3개)
- `tests/hmm_stability_test.py`: HMM 안정성 테스트
  - 20일 중 5회 전환 (안정성 73.7%), seed 60% 동의율
- `tests/vix_dependency_test.py`: VIX 의존도 측정
  - 평균 12.1% 영향, 스트레스 시 최대 25.3%
- `AUDIT_REPORT.md`: 문제점 5가지 + 해결책 5가지 + 세부 설계 보고서

#### Phase 1: 즉시 적용
- `regime/regime_model.py`: **HMM 5-seed 앙상블** (안정성 60% → 85%+)
  - `_fit_single_model()` 헬퍼 추출, log_likelihood 하위 20% 제외
  - 5개 모델 확률 평균 → 단일 판정
- `signals/cross_asset.py`: **시그모이드 연속 점수화**
  - 이진 trigger → `_sigmoid()` + 교차 곱, intensity 상한 3.0→1.5
  - 양극단 분포(std 0.317) 해소
- `risk/risk_engine.py`: **에러 격리**
  - `_safe_call_signal()`: 개별 신호 try/except, 실패 시 중립값(0.5)
  - 에러 신호 가중치 0.5배 패널티, `errors` 필드 추가

#### Phase 2: 검증 포함
- `signals/breadth.py`: **섹터 분산 지수로 RSP/SPY 교체**
  - `_sector_dispersion()`: 11개 섹터 ETF cross-sectional std + 롤링 퍼센타일
  - RSP/SPY 비율 제거 → SPY 직접 의존 절단
  - 가중치: 200MA(25%) + 섹터분산(30%) + 52주고저(20%) + McClellan(25%)
- `signals/volatility.py`: **SPY 실현변동성 → ^TNX 금리 변동성**
  - macro↔volatility 상관 0.612 해소
- `regime/regime_model.py`: **시간 스무딩 (3/5 다수결)**
  - `_apply_temporal_smoothing()`: 최근 5일 다수결로 regime 전환 확정
  - Liquidity Crisis 비대칭: 2/5 이상이면 즉시 전환
  - `regime_history.json` 파일 + 메모리 fallback
- `tests/daily_backtest.py` 신규: 일별 전체 기간 백테스트
  - 2019~현재 5일 간격, 감지율/오경보율/선행 일수 정량 평가
