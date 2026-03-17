# 위기감지 시스템 심층 감사 보고서

**작성일**: 2026-03-14
**대상**: Quant Risk Engine V2 (7-Signal Ensemble + HMM Regime Detection)
**방법론**: 실제 2년 시장 데이터 기반 정량 분석 (상관관계, 안정성, 의존도 테스트)

---

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [테스트 방법론](#2-테스트-방법론)
3. [발견된 문제점](#3-발견된-문제점)
   - P1: SPY 단일 자산 과의존
   - P2: HMM Regime 불안정
   - P3: Cross-Asset 양극단 분포
   - P4: 백테스트 방법론 한계
   - P5: 운영 안정성 부족
4. [개선 계획](#4-개선-계획)
   - S1: 신호 직교화 (Decorrelation)
   - S2: HMM 앙상블 + 시간 스무딩
   - S3: Cross-Asset 연속 점수화
   - S4: 일별 전체 기간 백테스트
   - S5: 운영 견고성 강화
5. [세부 설계](#5-세부-설계)
6. [우선순위 및 로드맵](#6-우선순위-및-로드맵)
7. [부록: 원시 테스트 결과](#7-부록-원시-테스트-결과)

---

## 1. 시스템 개요

### 현재 아키텍처

```
44개 티커 (yfinance + FRED)
    ↓
7개 신호 모듈 (각 0~1 스코어)
    ├── macro      (18%) — Stage1 9개 지표 → 정규화
    ├── liquidity  (17%) — FRED 3개 + yfinance 2개
    ├── breadth    (15%) — 섹터 ETF 4개 프록시
    ├── volatility (18%) — VIX 수준/VVIX/Term Structure/실현변동성
    ├── cross_asset(12%) — 5개 괴리 패턴
    ├── regime     (10%) — HMM 4-state (위험 확률)
    └── global_macro(10%) — EEM·VEU·CPER 글로벌 흐름
    ↓
HMM Regime → 동적 가중치 조정
    ↓
가중 평균 → 최종 Risk Score (0~1)
    ↓
5단계 레벨 → 포지션 사이징 → 행동 권고
```

### 현재 성과 (백테스트 기준)

| 위기 | 감지 여부 | 선행성 |
|------|-----------|--------|
| 2008 금융위기 | O | 30일 전 |
| 2018 Q4 급락 | X | 구조적 한계 |
| 2020 COVID | O | 15일 전 |
| 2022 베어마켓 | O | 60일 전 |
| 2019 오경보 | O (제거) | 코로보레이션 필터 |

**4위기 중 3개 감지 (75%), 오경보 0회**

---

## 2. 테스트 방법론

3가지 독립적 정량 테스트를 실시했습니다.

### 테스트 A: 신호 간 상관관계 분석
- **방법**: 250 영업일간 5일 간격으로 51개 시점에서 7개 신호 스코어 수집
- **분석**: 피어슨 상관행렬 + PCA 주성분 분석
- **스크립트**: `tests/correlation_analysis.py`

### 테스트 B: HMM 안정성 테스트
- **방법 1**: 최근 20 영업일간 데이터를 1일씩 추가하며 regime 변화 추적
- **방법 2**: 동일 데이터에 random_state 5개 (42, 0, 123, 7, 999) 적용
- **스크립트**: `tests/hmm_stability_test.py`

### 테스트 C: VIX 의존도 측정
- **방법**: ^VIX를 중립값(15.0)으로 고정 후 최종 스코어 변화 측정
- **범위**: 100 영업일간 10일 간격, 11개 시점
- **스크립트**: `tests/vix_dependency_test.py`

---

## 3. 발견된 문제점

### P1: SPY 단일 자산 과의존 (심각도: 높음)

#### 증거

**상관행렬** (51개 시점, 250일 기간):

| | macro | liquidity | breadth | volatility | cross_asset | regime | global_macro |
|---|---|---|---|---|---|---|---|
| **macro** | 1.000 | 0.315 | **0.642** | **0.612** | 0.175 | 0.441 | 0.377 |
| **liquidity** | | 1.000 | 0.057 | 0.205 | 0.430 | 0.014 | 0.180 |
| **breadth** | | | 1.000 | 0.055 | 0.158 | 0.168 | 0.433 |
| **volatility** | | | | 1.000 | -0.057 | 0.315 | 0.217 |
| **cross_asset** | | | | | 1.000 | 0.127 | 0.021 |
| **regime** | | | | | | 1.000 | 0.177 |
| **global_macro** | | | | | | | 1.000 |

**높은 상관 쌍 (|r| > 0.5)**:
- macro ↔ breadth: **r = 0.642** — SPY/QQQ/RSP/IWM 기반 지표끼리 동조
- macro ↔ volatility: **r = 0.612** — SPY 수익률·변동성이 동시에 반응

**PCA 분석**:
- 90% 분산 설명에 필요한 성분 수: **5개** (7개 중)
- Kaiser 기준 (고유값 > 1): **3개**만 유효
- 제1 주성분이 분산의 **37%** 설명 → SPY 기반 공통 요인

#### 문제의 본질

macro(18%) + breadth(15%) + volatility(18%) = **51%**가 SPY 파생 데이터에 기반.
SPY가 빠지면 3개가 동시에 경보 → **분산 효과가 환상**.
실질적으로 "7개 독립 신호"가 아니라 "3~5개 반독립 신호".

#### 기술적 원인

| 신호 | SPY 의존 경로 |
|------|-------------|
| macro | SPY/QQQ 동반하락, SPY 200일선, SPY 데스크로스 (3개 지표) |
| breadth | RSP/**SPY** 비율, 섹터 ETF (SPY 구성종목) |
| volatility | **SPY** 실현변동성 (25% 가중치) |
| regime | **SPY** 수익률이 HMM 6개 피처 중 1개 |

---

### P2: HMM Regime 불안정 (심각도: 높음)

#### 증거

**시간 안정성 테스트** (20 연속 영업일):

```
2026-02-22  Inflation
2026-02-23  Expansion       ← 전환 1
2026-02-24  Inflation       ← 전환 2
2026-02-25  Inflation
2026-02-26  Inflation
...
2026-03-05  Inflation
2026-03-06  Correction      ← 전환 3
2026-03-07  Correction
...
2026-03-10  Expansion       ← 전환 4 (1일짜리)
2026-03-11  Correction      ← 전환 5
2026-03-12  Correction
2026-03-13  Correction
```

- **20일간 5회 전환** (안정성 73.7%)
- 3/10 Expansion은 **1일짜리** — 다음 날 바로 Correction으로 복귀

**초기화 민감도** (동일 데이터, random_state 변경):

| random_state | Regime | Score |
|---|---|---|
| 42 | Correction | 0.70 |
| 0 | Correction | 0.70 |
| **123** | **Expansion** | **0.00** |
| 7 | Correction | 0.70 |
| **999** | **Inflation** | **0.32** |

- **5개 중 3개만 동의** (60%)
- seed=123은 완전 반대 (Expansion, score 0.00)

#### 문제의 본질

HMM이 **동적 가중치의 기반**인데 이 기반이 불안정.

**연쇄 영향 시나리오**:
1. 어제: Correction → liquidity 가중치 1.3배 → 최종 스코어 0.53
2. 오늘: 데이터 1일 추가 → Expansion → liquidity 0.5배 → 최종 스코어 ~0.38
3. **스코어가 0.15 급변** (L2 → L1 전환 가능)

#### 기술적 원인

1. **매 실행마다 재학습** (`model.fit()`): 데이터 1일 차이로 전체 상태 할당 변경
2. **EM 알고리즘 로컬 옵티마**: 초기화에 따라 다른 수렴점 도달
3. **확률 분포 극단화**: 거의 100% or 0% 확률 → 점진적 전환 없이 급변
4. **in-sample 학습+예측**: 같은 데이터로 학습하고 예측 → 과적합 경향

---

### P3: Cross-Asset 양극단 분포 (심각도: 중간)

#### 증거

**51개 시점 통계**:

| 통계 | 값 |
|------|-----|
| 평균 | 0.342 |
| 표준편차 | **0.317** (매우 큼) |
| 최솟값 | 0.000 |
| 25% | 0.000 |
| 중앙값 | 0.283 |
| 75% | 0.450 |
| 최댓값 | 1.000 |

- **25% 시점에서 스코어 = 0.000** (완전 무반응)
- 최댓값 1.000 도달 빈번 → **0 or 1 양극단**
- 표준편차/평균 = 0.93 (변동계수) — 극도로 불안정한 분포

#### 문제의 본질

5개 이진 패턴 중 trigger 여부만 판단 → **연속적 위험도 측정 불가**.
"주식↑ + 크레딧↓"가 0.5% 넘으면 trigger, 0.49%면 0 → **절벽 효과(cliff effect)**.

또한 `intensity_multiplier`가 최대 3.0까지 → `triggered_weight`가 `total_weight` 초과 가능 → `min(1.0)` 클램핑으로 **1.0에 자주 도달**.

#### 기술적 원인

```python
# 현재 코드 (cross_asset.py:62)
cond_a = (ret_a > threshold) if dir_a == "up" else (ret_a < -threshold)
cond_b = (ret_b > threshold) if dir_b == "up" else (ret_b < -threshold)
# → 이진: True or False. 중간이 없음.

# intensity_multiplier: 1.0~3.0 범위
intensity_multiplier = np.clip(intensity / 0.02, 1.0, 3.0)
# → 강도가 조금만 높아도 3.0 상한에 도달
```

---

### P4: 백테스트 방법론 한계 (심각도: 중간)

#### 현재 한계

| 문제 | 설명 |
|------|------|
| **4시점 스팟 체크** | T-60, T-30, T-15, T-0만 확인. 일별 연속 경보 패턴 미측정 |
| **오경보 측정 불완전** | 2019 1시점만 체크. 전체 기간 오경보 총 횟수/지속일 미측정 |
| **생존자 편향** | XLRE(2015~), XLC(2018~) 등 과거 미존재 ETF 포함 |
| **Look-ahead bias** | yfinance adjusted close는 사후 배당/분할 조정 소급 적용 |
| **통계적 유의성 없음** | 4위기, 4시점 = 16개 데이터포인트로 "75% 감지" 주장 |

---

### P5: 운영 안정성 부족 (심각도: 낮음~중간)

| 항목 | 현재 상태 | 위험 |
|------|-----------|------|
| **데이터 소스** | yfinance 무료 API | rate limit, 장중 지연, 장기 안정성 불확실 |
| **FRED 의존** | 없으면 liquidity 2개 지표로 축소 | 신뢰도 편차 |
| **에러 전파** | 하위 모듈 실패 시 전체 실패 가능 | `calculate_final_risk()`에 글로벌 try/except 없음 |
| **유닛 테스트** | 없음 | 코드 변경 시 사이드 이펙트 감지 불가 |
| **알림 체계** | 없음 | L2 도달해도 대시보드 직접 확인해야 인지 |

---

## 4. 개선 계획

### S1: 신호 직교화 (Decorrelation) — P1 해결

#### 목표
macro-breadth-volatility 클러스터의 상관성을 줄여 실질 독립 신호 수를 5→6개 이상으로 개선

#### 접근법: 데이터 소스 분리

현재 macro·breadth·volatility가 모두 SPY에서 파생되는 구조적 문제를 **데이터 소스 다각화**로 해결.

**변경 대상**:

| 신호 | 현재 SPY 의존 지표 | 변경 방향 |
|------|-------------------|-----------|
| macro | SPY/QQQ 동반하락 | 유지 (핵심 지표) |
| macro | SPY 200일선 이탈 | 유지 (핵심 지표) |
| macro | 데스크로스 (SPY) | 유지 (핵심 지표) |
| **breadth** | RSP/SPY 비율 | **섹터 분산 지수로 교체** |
| **volatility** | SPY 실현변동성 (25%) | **채권 실현변동성로 교체** (TLT vol) |
| **regime** | SPY 수익률 (HMM 피처) | 유지 (regime은 시장 상태 판단이므로 SPY 필수) |

**핵심 변경 1: breadth 독립화**
- RSP/SPY 비율 → **섹터 간 수익률 분산(cross-sectional dispersion)** 으로 교체
- 11개 섹터 ETF의 20일 수익률 표준편차: 높으면 섹터 양극화 = 위험
- SPY 절대 방향과 무관하게 "시장 내부 균열" 측정

**핵심 변경 2: volatility의 SPY 실현변동성 교체**
- SPY 실현변동성 → 이미 VIX가 SPY 변동성을 반영하므로 **제거 or 비중 축소**
- 대안: **고수익채 변동성 (HYG realized vol)** 또는 **금리 변동성 (^TNX realized vol)**
- 크레딧·금리 시장의 변동성은 SPY와 독립적 리스크 차원

#### 예상 효과
- macro ↔ breadth 상관: 0.642 → **0.3 이하** (SPY 공통 요인 제거)
- macro ↔ volatility 상관: 0.612 → **0.4 이하** (SPY 실현변동성 제거)
- PCA 유효 신호: 5개 → **6개**

---

### S2: HMM 앙상블 + 시간 스무딩 — P2 해결

#### 목표
regime 판정의 일관성을 73.7% → 90% 이상으로 개선

#### 접근법 2-A: 다중 시드 앙상블 (Multi-Seed Ensemble)

```
현재:  random_state=42 → 단일 모델 결과

변경:  random_state=[42, 0, 7, 13, 99] → 5개 모델 학습
       → 각 모델의 상태 확률 평균
       → 앙상블 확률로 regime 판정
```

**세부 설계**:
1. 5개 random_state로 GaussianHMM 독립 학습
2. 각 모델의 `predict_proba()` 결과를 **확률 평균**
3. 평균 확률에서 최대값의 regime을 현재 상태로 판정
4. log_likelihood가 하위 20%인 모델은 **제외** (수렴 실패 필터)

**이점**:
- seed=123 같은 이상치가 5개 중 1개 → 결과에 20%만 영향
- 확률이 "거의 100%"에서 "70~80%"로 완화 → 점진적 전환 가능

#### 접근법 2-B: 시간 스무딩 (Temporal Smoothing)

```
현재:  오늘 HMM 결과 = 오늘 regime (즉시 반영)

변경:  최근 N일 regime 결과의 다수결
       → N일 연속 새 regime이어야 전환 확정
```

**세부 설계**:
1. 최근 5 영업일의 HMM 결과를 버퍼에 저장
2. **3/5 다수결**: 5일 중 3일 이상 같은 regime → 전환 확정
3. 미달 시 이전 regime 유지
4. 단, **Liquidity Crisis는 즉시 반영** (위기 감지 지연 방지)
   - 2/5 이상이면 Crisis로 즉시 전환 (비대칭 규칙)

**이점**:
- 1일짜리 Expansion 뒤집힘 제거
- 위기는 즉시 반응, 안정은 점진적 전환 → 비대칭 설계

#### 접근법 2-C: 모델 저장 + 증분 예측 (장기 개선)

```
현재:  매 실행 → fit() + predict() (학습+예측 동시)

변경:  주 1회 fit() → 모델 pickle 저장
       매 실행 → predict()만 (저장된 모델 로드)
```

**세부 설계**:
1. `regime/saved_model.pkl`에 학습된 HMM + scaler 저장
2. 매 실행 시 저장 모델 로드 → `predict_proba()`만 실행
3. 매주 일요일 또는 데이터 250일 누적 시 재학습
4. 재학습 시 이전 모델과 결과 비교 → 급변 시 경고 로그

**이점**:
- 실행 속도 개선 (fit 제거)
- 일관성: 같은 모델로 연속 예측 → 데이터 1일 차이로 뒤집히지 않음
- 과적합 감소: 학습 데이터와 예측 데이터 분리

---

### S3: Cross-Asset 연속 점수화 — P3 해결

#### 목표
양극단 분포(0 or 1)를 연속적 그래디언트(0.0~1.0)로 변환

#### 접근법: 이진 → 연속 점수 + 시그모이드

**현재**:
```python
# 패턴 trigger 여부만 판단 (이진)
if cond_a and cond_b:
    triggered = True
    intensity = (abs(ret_a) + abs(ret_b)) / 2
```

**변경**:
```python
# 각 조건의 "얼마나 가까운지"를 연속 점수로 계산
def _continuous_score(ret, direction, threshold=0.005):
    """수익률의 방향 일치도를 0~1 연속 점수로."""
    if direction == "up":
        # 양수일수록 높은 점수, threshold 근처에서 0.5
        return 1 / (1 + np.exp(-10 * (ret - threshold)))  # sigmoid
    else:
        return 1 / (1 + np.exp(10 * (ret + threshold)))   # 반전 sigmoid

# 두 조건의 점수를 곱하여 교차 스코어
pair_score = score_a * score_b * intensity_factor
```

**세부 설계**:

1. **시그모이드 연속화**: threshold 근처에서 0→1 급변 대신 점진적 전환
   - `sigmoid_steepness = 10`: threshold ±0.2% 구간에서 0.12~0.88 범위
   - 조정 가능한 파라미터로 config.yaml에 노출

2. **교차 곱**: 두 조건의 점수를 곱함
   - A=0.8, B=0.9 → 0.72 (높은 일치)
   - A=0.3, B=0.9 → 0.27 (한쪽만 일치)
   - 이진 AND보다 미묘한 차이 포착 가능

3. **intensity 정규화**: 상한 3.0 제거
   - 수익률 크기를 퍼센타일 기반으로 정규화 (252일 롤링)
   - 평시 1%가 위기 시 1%와 다른 의미를 가짐을 반영

4. **"주식↑ + 금↑" 패턴 조건부 가중치**:
   - 인플레이션 regime일 때 가중치 0.15 → 0.05로 축소 (정상적 현상)
   - regime 정보를 cross_asset에 전달하는 인터페이스 추가

#### 예상 효과
- 표준편차 0.317 → **0.15~0.20** (분포 정상화)
- 25%ile = 0.000 → **0.05~0.15** (최소값 상승)
- 최댓값 1.000 도달 빈도 감소

---

### S4: 일별 전체 기간 백테스트 — P4 해결

#### 목표
4시점 스팟 체크 → 전체 기간 일별 스캔으로 통계적 유의성 확보

#### 접근법: 롤링 윈도우 백테스트

**세부 설계**:

```
기간: 2007-01-01 ~ 2026-03-13 (약 4,800 영업일)
방법: 매 영업일마다 calculate_final_risk() 실행
      → 일별 risk_score, level 시계열 생성
```

**측정 지표**:

| 지표 | 설명 | 목표 |
|------|------|------|
| **감지율 (Recall)** | 정의된 위기 구간 중 L2+ 경보가 발동된 비율 | > 70% |
| **선행 일수** | 위기 고점 대비 첫 L2 경보까지의 영업일 | > 15일 |
| **오경보율 (FPR)** | 비위기 구간에서 L2+ 경보 발동 비율 | < 5% |
| **오경보 횟수** | 비위기 구간에서 L2+ 경보 총 발동 횟수 | < 연 2회 |
| **경보 지속일** | L2+ 경보가 연속 유지된 평균 일수 | > 5일 (진짜), < 3일 (오경보) |
| **Risk-Adjusted 수익률** | 경보 시 주식 축소 전략의 Sharpe ratio | > Buy&Hold |

**위기 구간 정의**:
```
2007-10-09 ~ 2009-03-09: 2008 금융위기 (SPY -57%)
2018-09-20 ~ 2018-12-24: 2018 Q4 급락 (SPY -20%)
2020-02-19 ~ 2020-03-23: 2020 COVID (SPY -34%)
2022-01-04 ~ 2022-10-12: 2022 베어마켓 (SPY -25%)
그 외: 비위기 (정상) 구간
```

**구현 방식**:
1. `period="max"`로 전체 데이터 로드 (1993~현재)
2. 매일 `close[:date]`로 슬라이스 → 엔진 실행
3. FRED API 호출 불가하므로 **FRED 없는 liquidity** (yfinance 2개만) 사용
4. 결과를 CSV로 저장 → 사후 분석
5. **병렬 처리**: 날짜별 독립이므로 `multiprocessing` 가능

**실행 시간 예상**:
- 4,800일 × ~0.5초/일 = **약 40분**
- HMM fit 포함 시 ~2초/일 = **약 2.5시간**
- HMM 모델 캐싱(주 1회 재학습 시뮬레이션)으로 단축 가능

---

### S5: 운영 견고성 강화 — P5 해결

#### 5-A: 에러 격리 (Error Isolation)

**현재**: 하위 모듈 1개 실패 → 전체 `calculate_final_risk()` 실패
**변경**: 각 신호 모듈을 try/except로 격리, 실패 시 중립값(0.5) 대체 + 경고

```python
# risk_engine.py 변경
for name, func in signal_functions.items():
    try:
        signals[name] = func(close, config)
    except Exception as e:
        logger.warning(f"Signal {name} failed: {e}")
        signals[name] = {"score": 0.5, "detail": f"ERROR: {e}", "error": True}
        # 에러 신호는 가중치 절반으로 축소
        error_signals.add(name)
```

#### 5-B: 데이터 검증 레이어

**변경**: fetcher.py에 데이터 품질 검증 추가
- 필수 티커 누락 감지: SPY, ^VIX 없으면 명시적 경고
- 가격 이상치 필터: 1일 ±50% 변동은 데이터 오류로 간주
- 주말/공휴일 데이터 중복 제거

#### 5-C: 유닛 테스트 프레임워크

**범위**: 각 신호 모듈 + risk_engine + position_sizing

```python
# tests/test_signals.py 구조
def test_macro_score_range():
    """macro score가 0~1 범위인지"""

def test_macro_missing_ticker():
    """SPY 없을 때 graceful degradation"""

def test_volatility_neutral_vix():
    """VIX=15일 때 volatility score ~ 0.5"""

def test_risk_engine_all_signals_fail():
    """모든 신호 실패 시 0.5 반환"""

def test_position_sizing_boundaries():
    """score 0.0, 0.5, 1.0에서 정상 배분"""
```

---

## 5. 세부 설계

### 5.1 breadth 독립화: 섹터 분산 지수

**파일**: `signals/breadth.py` — `_sector_dispersion()` 추가

```python
def _sector_dispersion(close: pd.DataFrame, period: int = 20) -> float:
    """
    11개 섹터 ETF의 20일 수익률 표준편차 (cross-sectional dispersion).
    높을수록 섹터 양극화 → 시장 내부 균열 → 위험.

    해석:
    - 정상: 모든 섹터 비슷하게 움직임 → 분산 낮음
    - 위험: 일부 섹터 급등, 일부 급락 → 분산 높음
    - 위기 직전: 방어 섹터만 상승, 나머지 하락 → 분산 극대
    """
    returns = {}
    for etf in SECTOR_ETFS:
        if etf in close.columns:
            series = close[etf].dropna()
            if len(series) > period:
                returns[etf] = float(series.iloc[-1] / series.iloc[-period] - 1)

    if len(returns) < 5:
        return 0.5

    dispersion = np.std(list(returns.values()))

    # 252일 롤링 퍼센타일로 정규화
    # (히스토리컬 맥락에서 현재 분산이 어느 수준인지)
    # → 별도 롤링 계산 필요 (구현 시)

    return dispersion  # 퍼센타일 정규화 후 반환
```

**가중치 변경** (breadth 내부):
- 현재: 200MA(30%) + RSP/SPY(25%) + 52주고저(20%) + McClellan(25%)
- 변경: 200MA(25%) + **섹터분산(30%)** + 52주고저(20%) + McClellan(25%)
- RSP/SPY 제거 → SPY 직접 의존 절단

### 5.2 HMM 앙상블 구현

**파일**: `regime/regime_model.py` — `detect_regime()` 수정

```python
def detect_regime(close, config):
    # ... (기존 피처 준비 동일)

    # 5개 시드 앙상블
    seeds = [42, 0, 7, 13, 99]
    all_probs = []
    valid_models = []

    for seed in seeds:
        model = GaussianHMM(n_components=n_states, covariance_type="full",
                           n_iter=200, random_state=seed)
        model.fit(features_scaled)

        ll = model.score(features_scaled)
        state_probs = model.predict_proba(features_scaled)
        state_labels = _label_states(model, features_scaled, n_states, labels)

        # 확률을 라벨 기준으로 재배열
        labeled_probs = {}
        for state_idx, label in state_labels.items():
            labeled_probs[label] = float(state_probs[-1][state_idx])

        all_probs.append(labeled_probs)
        valid_models.append(ll)

    # log_likelihood 하위 20% 제외
    ll_threshold = np.percentile(valid_models, 20)
    filtered_probs = [p for p, ll in zip(all_probs, valid_models) if ll >= ll_threshold]

    # 확률 평균
    ensemble_probs = {}
    for label in labels:
        ensemble_probs[label] = np.mean([p.get(label, 0) for p in filtered_probs])

    # 정규화
    total = sum(ensemble_probs.values())
    ensemble_probs = {k: v/total for k, v in ensemble_probs.items()}

    current_regime = max(ensemble_probs, key=ensemble_probs.get)
    # ... (이하 동일)
```

### 5.3 시간 스무딩 구현

**파일**: `regime/regime_model.py` — 스무딩 레이어 추가

```python
# 최근 N일 결과를 파일에 저장하여 시계열 추적
HISTORY_FILE = PROJECT_ROOT / "regime" / "regime_history.json"

def _apply_temporal_smoothing(current_regime, current_probs, n_days=5, crisis_threshold=2):
    """
    최근 N일의 regime 결과를 기반으로 다수결 스무딩.
    Liquidity Crisis는 비대칭 규칙 적용 (즉시 반영).
    """
    history = _load_history()  # JSON에서 최근 N-1일 로드
    history.append({"regime": current_regime, "probs": current_probs, "date": today})
    history = history[-n_days:]  # 최근 N일만 유지
    _save_history(history)

    # Liquidity Crisis 비대칭 규칙
    crisis_count = sum(1 for h in history if h["regime"] == "Liquidity Crisis")
    if crisis_count >= crisis_threshold:
        return "Liquidity Crisis"

    # 일반 다수결 (3/5)
    regime_counts = Counter(h["regime"] for h in history)
    majority_regime, count = regime_counts.most_common(1)[0]

    if count >= 3:  # 5일 중 3일 이상
        return majority_regime
    else:
        # 미달 시 이전 confirmed regime 유지
        return history[-2]["confirmed_regime"] if len(history) > 1 else current_regime
```

### 5.4 Cross-Asset 연속 점수화

**파일**: `signals/cross_asset.py` — 전면 개편

```python
def _sigmoid_score(value, center, steepness=10):
    """center 근처에서 0→1 점진적 전환."""
    return 1 / (1 + np.exp(-steepness * (value - center)))

def _continuous_divergence_score(ret_a, dir_a, ret_b, dir_b, threshold=0.005):
    """
    연속 괴리 점수 (0~1).
    이진 trigger 대신 시그모이드 연속 점수.
    """
    if dir_a == "up":
        score_a = _sigmoid_score(ret_a, threshold)
    else:
        score_a = _sigmoid_score(-ret_a, threshold)

    if dir_b == "up":
        score_b = _sigmoid_score(ret_b, threshold)
    else:
        score_b = _sigmoid_score(-ret_b, threshold)

    # 교차 곱: 두 조건 모두 강해야 높은 점수
    pair_score = score_a * score_b

    # 강도 보정 (퍼센타일 기반 — 구현 시 롤링 추가)
    intensity = (abs(ret_a) + abs(ret_b)) / 2
    intensity_norm = min(intensity / 0.03, 1.5)  # 상한 1.5 (기존 3.0에서 축소)

    return pair_score * intensity_norm
```

### 5.5 일별 백테스트 엔진

**파일**: `tests/daily_backtest.py` — 신규

```python
"""
일별 전체 기간 백테스트
- 2010-01-01 ~ 현재 (FRED 없는 모드)
- 매 영업일 risk score 계산
- 오경보율, 감지율, 선행 일수, Sharpe ratio 측정
"""

CRISIS_PERIODS = {
    "2018_Q4":  ("2018-09-20", "2018-12-24"),
    "2020_COVID": ("2020-02-19", "2020-03-23"),
    "2022_Bear": ("2022-01-04", "2022-10-12"),
}

# 위기 시작 N일 전부터를 "선행 감지 구간"으로 정의
LEAD_WINDOW = 60  # 위기 시작 60일 전부터 감시

def run_daily_backtest():
    close = fetch_market_data(tickers=tickers, period="max")

    results = []
    for date in business_days(start, end):
        sliced = close[:date]
        if len(sliced) < 252:
            continue

        score = calculate_final_risk(sliced, config, dynamic_weights=True)
        level = score_to_level(score["final_score"])

        results.append({
            "date": date,
            "score": score["final_score"],
            "level": level,
            "regime": score["regime"]["regime"],
        })

    df = pd.DataFrame(results)

    # 측정 지표 계산
    for crisis_name, (peak, trough) in CRISIS_PERIODS.items():
        # 감지율: 위기 구간 중 L2+ 비율
        crisis_mask = (df.date >= peak) & (df.date <= trough)
        recall = (df[crisis_mask].level >= 2).mean()

        # 선행 일수: peak 전 첫 L2 발동 시점
        lead_start = pd.Timestamp(peak) - pd.offsets.BDay(LEAD_WINDOW)
        lead_mask = (df.date >= lead_start) & (df.date < peak)
        lead_scores = df[lead_mask]
        first_l2 = lead_scores[lead_scores.level >= 2]
        lead_days = (pd.Timestamp(peak) - first_l2.date.iloc[0]).days if len(first_l2) > 0 else 0

    # 오경보: 비위기 구간에서 L2+ 발동 횟수
    non_crisis_mask = ~any_crisis_mask
    false_alarms = count_consecutive_l2_blocks(df[non_crisis_mask])

    # 전략 Sharpe: L2 시 equity 0.4, 아니면 0.8
    ...
```

---

## 6. 우선순위 및 로드맵

### Phase 1: 즉시 적용 (1~2일)

| 작업 | 대상 파일 | 난이도 | 영향도 |
|------|-----------|--------|--------|
| **S2-A: HMM 앙상블** | `regime/regime_model.py` | 중 | **높음** — 안정성 60%→85%+ |
| **S3: cross_asset 연속화** | `signals/cross_asset.py` | 중 | **중** — 분포 정상화 |
| **S5-A: 에러 격리** | `risk/risk_engine.py` | 낮 | **중** — 운영 안정성 |

### Phase 2: 검증 포함 (3~5일)

| 작업 | 대상 파일 | 난이도 | 영향도 |
|------|-----------|--------|--------|
| **S1: breadth 독립화** | `signals/breadth.py` | 중 | **높음** — 상관 0.64→0.3 |
| **S1: volatility SPY 제거** | `signals/volatility.py` | 낮 | **중** — 상관 0.61→0.4 |
| **S2-B: 시간 스무딩** | `regime/regime_model.py` | 중 | **높음** — 1일 뒤집힘 제거 |
| **S4: 일별 백테스트** | `tests/daily_backtest.py` | 높 | **높음** — 신뢰도 검증 |

### Phase 3: 장기 개선 (1~2주)

| 작업 | 대상 파일 | 난이도 | 영향도 |
|------|-----------|--------|--------|
| **S2-C: 모델 저장** | `regime/regime_model.py` | 중 | 중 — 일관성 + 속도 |
| **S5-C: 유닛 테스트** | `tests/test_*.py` | 중 | 중 — 유지보수성 |
| **텔레그램 알림** | `alerts/telegram.py` | 중 | 중 — 운영 완성도 |

### 의존성 그래프

```
S5-A (에러 격리) ─────────────────────→ 즉시 적용 가능
S2-A (HMM 앙상블) ──→ S2-B (시간 스무딩) ──→ S2-C (모델 저장)
S3 (cross_asset 연속화) ──────────────→ 즉시 적용 가능
S1 (신호 직교화) ──→ S4 (일별 백테스트로 효과 검증)
```

---

## 7. 부록: 원시 테스트 결과

### A. 상관관계 분석 원시 데이터

- **샘플 크기**: 51개 시점 (2025-07-06 ~ 2026-03-13, 5영업일 간격)
- **모든 시점에서 7/7 신호 수집 성공**
- **FRED rate limit**: 14번째 시점부터 FRED API 제한 → liquidity 점수에 영향 (yfinance 지표만으로 계산)

**신호 기술통계**:

| 신호 | 평균 | 표준편차 | 최소 | 중앙값 | 최대 |
|------|------|----------|------|--------|------|
| macro | 0.126 | 0.124 | 0.000 | 0.056 | 0.444 |
| liquidity | 0.411 | 0.106 | 0.182 | 0.375 | 0.694 |
| breadth | 0.299 | 0.112 | 0.103 | 0.285 | 0.527 |
| volatility | 0.397 | 0.189 | 0.118 | 0.358 | 0.774 |
| cross_asset | 0.342 | **0.317** | 0.000 | 0.283 | 1.000 |
| regime | 0.100 | **0.213** | 0.000 | 0.000 | 0.999 |
| global_macro | 0.463 | 0.175 | 0.166 | 0.442 | 0.861 |

**PCA 고유값**:

| 성분 | 고유값 | 설명 분산 | 누적 |
|------|--------|-----------|------|
| PC1 | 2.639 | 37.0% | 37.0% |
| PC2 | 1.334 | 18.7% | 55.6% |
| PC3 | 1.107 | 15.5% | 71.2% |
| PC4 | 0.880 | 12.3% | 83.5% |
| PC5 | 0.655 | 9.2% | 92.6% |
| PC6 | 0.415 | 5.8% | 98.5% |
| PC7 | 0.111 | 1.5% | 100% |

### B. HMM 안정성 원시 데이터

**20일 시계열** (전체 확률 포함):

| 날짜 | Regime | Expansion | Inflation | Correction | Crisis |
|------|--------|-----------|-----------|------------|--------|
| 02-22 | Inflation | 0.00 | 1.00 | 0.00 | 0.00 |
| 02-23 | Expansion | 1.00 | 0.00 | 0.00 | 0.00 |
| 02-24 | Inflation | 0.00 | 1.00 | 0.00 | 0.00 |
| 02-25 | Inflation | 0.00 | 1.00 | 0.00 | 0.00 |
| 02-26~03-05 | Inflation | 0.00 | 1.00 | 0.00 | 0.00 |
| 03-06 | Correction | 0.00 | 0.00 | 1.00 | 0.00 |
| 03-07~03-09 | Correction | 0.00 | 0.00 | 1.00 | 0.00 |
| 03-10 | Expansion | 1.00 | 0.00 | 0.00 | 0.00 |
| 03-11~03-13 | Correction | 0.00 | 0.00 | 1.00 | 0.00 |

**주목**: 모든 확률이 0.00 or 1.00 — HMM이 "확신"하지만 매일 뒤집힘.

### C. VIX 의존도 원시 데이터

| 시점 | VIX | 기본 스코어 | VIX 중립 스코어 | 차이 | 영향도% |
|------|-----|-------------|----------------|------|---------|
| T-0 | 27.3 | 0.531 | 0.412 | -0.119 | 22.4% |
| T-10 | 25.6 | 0.530 | 0.404 | -0.126 | 23.7% |
| T-20 | 23.4 | 0.473 | 0.361 | -0.112 | 23.6% |
| T-30 | 22.8 | 0.430 | 0.321 | -0.109 | 25.3% |
| T-40 | 19.9 | 0.343 | 0.296 | -0.047 | 13.6% |
| T-50 | 17.7 | 0.276 | 0.257 | -0.019 | 6.8% |
| T-60 | 16.8 | 0.253 | 0.232 | -0.021 | 8.3% |
| T-70 | 17.2 | 0.212 | 0.181 | -0.031 | 14.7% |
| T-80 | 15.6 | 0.195 | 0.185 | -0.010 | 5.2% |
| T-90 | 14.8 | 0.182 | 0.180 | -0.002 | 1.1% |
| T-100 | 14.2 | 0.160 | 0.159 | -0.001 | 0.5% |

**VIX 수준 ↔ 영향도 상관계수: 0.951** (매우 강한 양의 상관)

---

*이 보고서의 테스트 스크립트는 `tests/` 디렉토리에 저장되어 재현 가능합니다.*
- `tests/correlation_analysis.py`
- `tests/hmm_stability_test.py`
- `tests/vix_dependency_test.py`
