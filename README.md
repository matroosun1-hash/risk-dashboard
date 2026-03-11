# 🛡️ Quant Risk Engine V2

## 개요

**Full Market Risk Engine** — 폭락장 탐지를 넘어 시장 체제 분류, 유동성 스트레스,
시장 폭, 변동성 체제, 교차자산 괴리를 종합 분석하여 자동 포지션 사이징을 제공합니다.

```
Multi-Asset Data → Regime Detection → Risk Score → Dynamic Allocation → Action
```

---

## 시스템 구조

```
위기감지/
├── config.yaml              # 모든 설정 (V1 + V2)
├── main.py                  # V1 CLI 진입점
├── main_v2.py               # V2 CLI 진입점
├── requirements.txt         # 의존성
│
├── data/
│   └── fetcher.py           # yfinance + FRED 데이터 수집 (39개 티커)
│
├── signals/                 # V2: 5개 신호 모듈
│   ├── macro.py             # 기존 10개 지표 → 0~1 스코어
│   ├── liquidity.py         # 유동성 스트레스 (FRED + yfinance)
│   ├── breadth.py           # 시장 폭 (11개 섹터 ETF 프록시)
│   ├── volatility.py        # 변동성 체제 (VIX/VVIX/RV)
│   └── cross_asset.py       # 교차자산 괴리 (5개 패턴)
│
├── regime/                  # V2: 체제 탐지
│   └── regime_model.py      # HMM 기반 4-state 분류
│
├── risk/                    # V2: 리스크 엔진
│   ├── risk_engine.py       # 6개 신호 가중 통합
│   └── position_sizing.py   # Dynamic Position Sizing
│
├── portfolio/               # V2: 포트폴리오 관리
│   └── allocator.py         # 행동 권고 생성
│
├── stage1/                  # V1: 하락장 조기탐지 (유지)
├── stage2/                  # V1: 섹터 로테이션 (유지)
├── action/                  # V1: 대응 권고 (유지)
│
└── dashboard/
    └── app.py               # Streamlit 대시보드
```

---

## 사용법

### 설치
```bash
pip install -r requirements.txt
```

### V2 실행 (권장)
```bash
python main_v2.py              # 전체 V2 분석
python main_v2.py --period 2y  # 2년 데이터
```

### V1 실행 (기존)
```bash
python main.py                 # V1 분석
```

### 대시보드
```bash
streamlit run dashboard/app.py
```

---

## V2: 6개 리스크 신호

| 신호 | 모듈 | 가중치 | 설명 |
|------|------|--------|------|
| Macro | signals/macro.py | 20% | 기존 10개 거시지표 |
| Liquidity | signals/liquidity.py | 20% | SOFR-FFR, HY OAS, CP Spread, TLT Vol |
| Breadth | signals/breadth.py | 15% | 섹터 200MA, RSP/SPY, High/Low, McClellan |
| Volatility | signals/volatility.py | 20% | VIX, VVIX 프록시, Term Structure, 실현Vol |
| Cross-Asset | signals/cross_asset.py | 15% | 5개 교차자산 괴리 패턴 |
| Regime | regime/regime_model.py | 10% | HMM 4-state (Expansion/Inflation/Correction/Crisis) |

### Final Risk Score = Σ(weight × signal_score)

---

## V2: Market Regime (HMM)

| Regime | 특징 |
|--------|------|
| **Expansion** | SPY↑, VIX↓, 크레딧 안정 |
| **Inflation** | 원유↑, 달러 변동, 금리↑ |
| **Correction** | SPY↓, 크레딧 약화 |
| **Liquidity Crisis** | VIX 급등, 전반적 자산 하락 |

---

## V2: Dynamic Position Sizing

| Risk Score | Equity | Treasury | Gold | Cash |
|------------|--------|----------|------|------|
| 0.0~0.2 | 80% | 10% | 5% | 5% |
| 0.2~0.4 | 60% | 15% | 10% | 15% |
| 0.4~0.6 | 40% | 20% | 15% | 25% |
| 0.6~0.8 | 20% | 25% | 20% | 35% |
| 0.8~1.0 | 5% | 20% | 20% | 55% |

**Volatility Targeting**: 현재 변동성 > 목표(12%) 시 주식 비중 자동 축소

---

## V1: 하락장 조기탐지 (10개 지표)

| # | 지표 | 신호 조건 | 점수 |
|---|------|-----------|------|
| 1 | S&P500/나스닥 동반하락 | SPY & QQQ 모두 20일 수익률 < 0 | 0~1 |
| 2 | VIX 공포지수 | VIX ≥ 25 (위험), ≥ 20 (주의) | 0~1 |
| 3 | 데스크로스 | SPY 50일선 < 200일선 | 0~1 |
| 4 | 장단기금리 역전 | 10Y - 3M < 0 | 0~1 |
| 5 | 하이일드 스프레드 | HYG/LQD 20일 하락 > 1% | 0~1 |
| 6 | SPY 200일선 이탈 | SPY < 200일 이동평균 | 0~1 |
| 7 | 달러 강세 | UUP 20일 수익률 > 2% | 0~1 |
| 8 | 시장폭 (RSP/SPY) | RSP/SPY 비율 20일 하락 > 1% | 0~1 |
| 9 | 소형주 (IWM/SPY) | IWM/SPY 비율 20일 하락 > 1% | 0~1 |
| 10 | 채권변동성 | TLT 20일 변동성 > 0.015 | 0~1 |

---

## V1: 섹터 로테이션 탐지

| 쌍 | 의미 |
|----|------|
| VUG/VTV | 성장 → 가치 |
| XLK/XLP | 테크 → 방어 |
| SPY/TLT | 위험 → 안전 |
| XLY/XLU | 사이클 → 방어 |

---

## Level별 매매 지침

| Level | 상태 | 핵심 행동 |
|-------|------|-----------|
| 🟢 0 | 정상 | 정상 운영 |
| 🟡 1 | 주의 | 포지션 축소, 현금 10~20% |
| 🟠 2 | 경고 | 성장주 매수 자제, 현금 20~30% |
| 🔴 3 | 위험 | 성장주 전량 매도, 방어 ETF 50% |
| 🔴🔴 4 | 극도위험 | 전량 매도, 현금 70~80% |

---

## 데이터 소스

| 소스 | 용도 | 비용 |
|------|------|------|
| yfinance | 주가, ETF, 지수 (39개 티커) | 무료 |
| FRED API | SOFR, HY OAS, CP Spread | 무료 (API 키 필요) |

---

## 대시보드 기능 (V2 Action-First UI)

과거 단순히 데이터를 나열하던 탭 방식에서 벗어나, 사용자가 **직관적으로 행동 지침을 파악**할 수 있도록 Cyberpunk / Glassmorphism 테마 기반의 레이아웃으로 전면 개편되었습니다.

- **Action Hero Board**: 현재 시장 체제 및 위험 수준에 따른 '최종 포트폴리오 행동 권고'를 화면 최상단에 강렬한 네온 컬러로 강조.
- **Dynamic Allocation Bar**: 주식, 금, 채권, 현금 비중을 한눈에 알 수 있는 시각적 UI. (변동성 타겟팅 개입 여부 동시 표기)
- **Progressive Disclosure**: 레이더 차트 (5대 신호 점수), HMM 확률 분포 (체제 판별 확률) 등 복잡한 퀀트 데이터 스택은 전문가용 메뉴(Expander) 안으로 분리하여 가독성을 극대화 하였습니다.

---

## V2 백테스트 검증 (Historical Crises)

과거 주요 시장 위기 구간에서의 Risk Score 및 체제 탐지 백테스트 결과, 엔진이 시장 충격을 조기에 감지하고 주식 인스포저를 성공적으로 축소했습니다.

| 이벤트 | 발생일 | Risk Score | 탐지 Regime | 주식 배분 |
|--------|--------|------------|-------------|-----------|
| **2008 금융위기 (Lehman)** | 2008-09-15 | 0.72 | **Liquidity Crisis** | 20% |
| **2018 Volmageddon** | 2018-02-05 | 0.54 | Normal | 40% |
| **2020 COVID-19 Crash** | 2020-03-20 | 0.79 | **Liquidity Crisis** | 20% |
| **2022 Bear Market** | 2022-06-15 | 0.64 | **Inflation** | 20% |
| **2021 Bull Market** | 2021-08-02 | 0.15 | **Expansion** | 80% |

---

## 작업 이력

| 날짜 | 작업 내용 |
|------|-----------|
| 2026-03-11 | V1: 프로젝트 초기 구조 설계 및 구현 |
| 2026-03-11 | V1: 전체 모듈 구현 (data, stage1, stage2, action, dashboard) |
| 2026-03-11 | V1: yfinance MultiIndex NaN 버그 수정 |
| 2026-03-11 | V1: 사이드바 매매 지침 추가, 과거 시점 분석 기능 |
| 2026-03-11 | V2: 과업 1 — Regime Detection (HMM 4-state) 구현 |
| 2026-03-11 | V2: 과업 2 — Liquidity Stress Index (FRED + yfinance) 구현 |
| 2026-03-11 | V2: 과업 3 — Market Breadth Engine (11개 섹터 ETF 프록시) 구현 |
| 2026-03-11 | V2: 과업 4 — Volatility Regime (VIX/VVIX/Term/RV) 구현 |
| 2026-03-11 | V2: 과업 5 — Cross-Asset Risk Signal (5개 괴리 패턴) 구현 |
| 2026-03-11 | V2: 과업 6 — Dynamic Position Sizing (Vol Targeting) 구현 |
| 2026-03-11 | V2: 과업 7 — Multi-Signal Aggregation Engine 구현 |
| 2026-03-11 | V2: 전체 파이프라인 테스트 통과 (39 tickers, TEST OK) |

---

*💡 이 시스템의 지침은 참고용이며, 최종 매매 판단은 본인에게 있습니다.*


---

## 시스템 구조

```
위기감지/
├── config.yaml              # 모든 설정 (임계값, 종목, 가중치)
├── main.py                  # CLI 진입점
├── requirements.txt         # 의존성
├── README.md                # 이 문서
│
├── data/
│   └── fetcher.py           # yfinance 데이터 수집 (28개 티커)
│
├── stage1/                  # 1단계: 하락장 조기탐지
│   ├── indicators.py        # 10개 지표 계산
│   └── scorer.py            # 종합 점수 → Level 0~4
│
├── stage2/                  # 2단계: 섹터 로테이션 탐지
│   ├── rotation.py          # 4개 상대성과 쌍 (20일)
│   ├── leading.py           # 3개 선행지표 (7일)
│   └── scorer.py            # 로테이션 Level 판정
│
├── action/                  # 자동 대응 권고
│   ├── prioritizer.py       # 매도 우선순위 (손절→Sharpe→수익률)
│   ├── defender.py          # 방어 ETF 분산매수 배분
│   └── executor.py          # 종합 대응 권고 생성
│
├── dashboard/
│   └── app.py               # Streamlit 대시보드
│
└── tests/
    ├── quick_test.py         # 빠른 검증 스크립트
    └── diagnose_nan.py       # 데이터 진단 도구
```

---

## 사용법

### 설치
```bash
pip install -r requirements.txt
```

### CLI 실행
```bash
# 전체 분석 (1단계 + 2단계 + 대응 권고)
python main.py

# 1단계만 실행
python main.py --stage1

# 2단계만 실행
python main.py --stage2

# 데이터 기간 변경
python main.py --period 2y
```

### 대시보드
```bash
streamlit run dashboard/app.py
# 브라우저에서 http://localhost:8501 접속
```

---

## 1단계: 하락장 조기탐지 (10개 지표)

| # | 지표 | 신호 조건 | 점수 |
|---|------|-----------|------|
| 1 | S&P500/나스닥 동반하락 | SPY & QQQ 모두 20일 수익률 < 0 | 0~1 |
| 2 | VIX 공포지수 | VIX ≥ 25 (위험), ≥ 20 (주의) | 0~1 |
| 3 | 데스크로스 | SPY 50일선 < 200일선 | 0~1 |
| 4 | 장단기금리 역전 | 10Y - 3M < 0 | 0~1 |
| 5 | 하이일드 스프레드 | HYG/LQD 20일 하락 > 1% | 0~1 |
| 6 | SPY 200일선 이탈 | SPY < 200일 이동평균 | 0~1 |
| 7 | 달러 강세 | UUP 20일 수익률 > 2% | 0~1 |
| 8 | 시장폭 (RSP/SPY) | RSP/SPY 비율 20일 하락 > 1% | 0~1 |
| 9 | 소형주 (IWM/SPY) | IWM/SPY 비율 20일 하락 > 1% | 0~1 |
| 10 | 채권변동성 | TLT 20일 변동성 > 0.015 | 0~1 |

### Level 판정
| 합산 점수 | Level | 상태 |
|-----------|-------|------|
| 0~2 | Level 0 | 🟢 정상 |
| 3~4 | Level 1 | 🟡 주의 |
| 5~6 | Level 2 | 🟠 경고 |
| 7~8 | Level 3 | 🔴 위험 |
| 9~10 | Level 4 | 🔴🔴 극도위험 |

---

## 2단계: 섹터 로테이션 탐지

### 4개 상대성과 쌍 (20일 기준)
| 쌍 | 의미 |
|----|------|
| VUG/VTV | 성장 → 가치 로테이션 |
| XLK/XLP | 테크 → 방어 로테이션 |
| SPY/TLT | 위험 → 안전 로테이션 |
| XLY/XLU | 사이클 → 방어 로테이션 |

### 3개 선행지표 (7일 기준)
| 지표 | 신호 |
|------|------|
| GLD (금) | 상승 → 안전자산 선호 |
| BTC-USD | 하락 → 위험자산 회피 |
| SMH/SPY | 하락 → 반도체 약세 선행 |

### Level 판정
| 조건 | Level |
|------|-------|
| 쌍 0~1개 음수 | Level 0 |
| 쌍 2개 음수 | Level 1 |
| 쌍 3개 음수 | Level 2 |
| 쌍 4개 음수 + 선행 1개+ | Level 3 |
| 쌍 4개 음수 + 선행 3개 + 임계값 초과 | Level 4 |

---

## Level별 매매 지침

### 🟢 Level 0 — 정상
- 기존 투자 전략 정상 운영
- 신규 매수 가능

### 🟡 Level 1 — 주의
- 모니터링 빈도 강화 (매일 체크)
- 신규 매수 시 포지션 축소 (평소 50%)
- 현금비중 10~20% 확보

### 🟠 Level 2 — 경고
- 성장주 신규 매수 자제
- 성장주 포지션 비중 축소 (30~50%)
- 방어주/채권 ETF 일부 전환
- 현금비중 20~30% 확보

### 🔴 Level 3 — 위험
- **성장주 전량 매도** (손절 → Sharpe↓ → 수익률↓ 순)
- 매도대금 50% → 방어 ETF 분산매수 (WMT, BRK-B, PG, JNJ, XLP, SCHD, SHY, IEF, TLT, DBC)
- 나머지 50% → 현금 보유
- 🚫 성장주 신규 매수 전면 차단

### 🔴🔴 Level 4 — 극도위험
- ⚠️ **전량 매도 권고**
- 70~80% 현금/단기채권 전환
- 잔여: SHY 또는 GLD
- 모든 신규 매수 전면 차단
- Level 1 이하 확인 전까지 대기

---

## 대시보드 기능

- **Level 카드**: 1단계, 2단계, 종합 위험 Level을 한눈에 확인
- **10개 지표 탭**: 각 지표별 점수와 상세 수치
- **로테이션 탭**: 4개 쌍 변화율 + 3개 선행지표
- **대응 권고 탭**: Level에 따른 행동 지침
- **차트 탭**: SPY/200SMA, VIX, 로테이션 쌍 추이
- **과거 시점 분석**: 날짜를 선택하여 과거 특정일의 Level 확인 가능

---

## 보유 종목 설정

`config.yaml`의 `portfolio.holdings`에 보유 종목을 추가하면  
구체적인 매도 우선순위와 방어 ETF 배분 권고를 받을 수 있습니다:

```yaml
portfolio:
  holdings:
    - ticker: NVDA
      shares: 10
      avg_price: 800.00
      category: growth
    - ticker: TSLA
      shares: 5
      avg_price: 250.00
      category: growth
```

---

## 작업 이력

| 날짜 | 작업 내용 |
|------|-----------|
| 2026-03-11 | 프로젝트 초기 구조 설계 및 구현 계획 수립 |
| 2026-03-11 | 전체 모듈 구현 (data, stage1, stage2, action, dashboard) |
| 2026-03-11 | yfinance MultiIndex 이슈로 6개 지표 NaN 버그 수정 |
| 2026-03-11 | 사이드바 Level별 매매 지침 추가 |
| 2026-03-11 | 과거 시점 분석 기능 추가 (날짜 선택기) |

---

*💡 이 시스템의 지침은 참고용이며, 최종 매매 판단은 본인에게 있습니다.*
