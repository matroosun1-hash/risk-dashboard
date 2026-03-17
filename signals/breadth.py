"""
signals/breadth.py — 시장 폭(Market Breadth) 엔진

시장 내부 구조 붕괴를 탐지합니다.
S&P 500 개별 종목 데이터 대신 섹터 ETF 기반 프록시를 사용합니다.

개선: RSP/SPY 비율 제거 → 섹터 분산 지수로 교체 (SPY 직접 의존 절단)
"""

import pandas as pd
import numpy as np


# S&P 500 직접 수집 대신 11개 섹터 ETF 활용
SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLC", "XLY", "XLP", "XLU", "XLB", "XLRE"]


def _pct_sectors_above_200ma(close: pd.DataFrame) -> float:
    """11개 섹터 ETF 중 200일 이동평균 위에 있는 비율."""
    count_above = 0
    count_total = 0

    for etf in SECTOR_ETFS:
        if etf not in close.columns:
            continue
        series = close[etf].dropna()
        if len(series) < 200:
            continue
        sma200 = series.rolling(200).mean().iloc[-1]
        current = series.iloc[-1]
        count_total += 1
        if current > sma200:
            count_above += 1

    if count_total == 0:
        return 0.5
    return count_above / count_total


def _sector_dispersion(close: pd.DataFrame, period: int = 20) -> float:
    """
    11개 섹터 ETF의 20일 수익률 cross-sectional 표준편차 (섹터 분산 지수).

    해석:
    - 낮음: 모든 섹터 비슷하게 움직임 → 정상
    - 높음: 일부 섹터 급등, 일부 급락 → 시장 내부 균열 → 위험
    - 위기 직전: 방어 섹터만 상승, 나머지 하락 → 분산 극대

    롤링 퍼센타일로 정규화하여 히스토리컬 맥락에서 현재 분산 수준 판단.
    """
    returns = []
    for etf in SECTOR_ETFS:
        if etf not in close.columns:
            continue
        series = close[etf].dropna()
        if len(series) > period:
            ret = float(series.iloc[-1] / series.iloc[-period] - 1)
            returns.append(ret)

    if len(returns) < 5:
        return 0.5

    current_dispersion = np.std(returns)

    # 히스토리컬 분산을 계산하여 롤링 퍼센타일 산출
    # 과거 252일간의 각 시점에서 섹터 분산을 계산
    min_history = 252
    available_etfs = [etf for etf in SECTOR_ETFS if etf in close.columns]
    if len(available_etfs) < 5:
        return 0.5

    # 각 ETF의 rolling period-day return
    ret_df = pd.DataFrame()
    for etf in available_etfs:
        series = close[etf].dropna()
        if len(series) > period:
            ret_df[etf] = series.pct_change(period)

    ret_df = ret_df.dropna()
    if len(ret_df) < min(min_history, 60):
        # 데이터 부족 시 단순 정규화
        score = np.clip(current_dispersion / 0.10, 0, 1)
        return float(score)

    # 각 날짜의 cross-sectional std 계산
    daily_dispersion = ret_df.std(axis=1)

    # 현재 분산의 퍼센타일 위치
    historical = daily_dispersion.iloc[:-1] if len(daily_dispersion) > 1 else daily_dispersion
    rank = float((historical < current_dispersion).sum()) / max(len(historical), 1)

    return float(np.clip(rank, 0, 1))


def _high_low_ratio(close: pd.DataFrame, window: int = 252) -> float:
    """섹터 ETF의 52주(약 252영업일) 신고가/신저가 비율 프록시.
    52주 최고가 근접 = 건강, 52주 최저가 근접 = 위험."""
    highs = 0
    lows = 0

    for etf in SECTOR_ETFS:
        if etf not in close.columns:
            continue
        series = close[etf].dropna()
        if len(series) < window:
            if len(series) < 60:
                continue
            window_actual = len(series)
        else:
            window_actual = window

        high_52w = series.iloc[-window_actual:].max()
        low_52w = series.iloc[-window_actual:].min()
        current = series.iloc[-1]

        # 현재 가격이 고가-저가 범위에서 어디에 있는지
        if high_52w == low_52w:
            continue
        position = (current - low_52w) / (high_52w - low_52w)
        if position > 0.8:
            highs += 1
        elif position < 0.2:
            lows += 1

    total = highs + lows
    if total == 0:
        return 0.5

    # 신저가 많을수록 스코어 높음 (위험)
    return lows / total


def _mcclellan_proxy(close: pd.DataFrame) -> float:
    """McClellan Oscillator 프록시.
    RSP의 19일 EMA - 39일 EMA를 정규화."""
    if "RSP" not in close.columns:
        return 0.5

    rsp = close["RSP"].dropna()
    if len(rsp) < 39:
        return 0.5

    ret = rsp.pct_change().dropna()
    ema19 = ret.ewm(span=19).mean()
    ema39 = ret.ewm(span=39).mean()
    mcclellan = ema19 - ema39

    # 최근값의 히스토리컬 위치 (음수=위험)
    recent = mcclellan.iloc[-1]
    std = mcclellan.std()
    if std == 0:
        return 0.5

    # z-score → 0~1 (음수가 클수록 위험=1)
    z = -recent / std
    score = 1 / (1 + np.exp(-z * 2))  # sigmoid 변환
    return float(score)


def calculate_breadth_score(close: pd.DataFrame, config: dict = None) -> dict:
    """
    시장 폭 종합 스코어를 계산합니다.

    Returns:
        {"score": 0~1, "components": [...], "detail": str}
    """
    components = []

    # 1) % Sectors above 200MA
    pct_above = _pct_sectors_above_200ma(close)
    above_score = 1 - pct_above  # 적을수록 위험
    components.append({
        "name": "섹터 200MA 위 비율",
        "value": f"{pct_above:.0%}",
        "score": above_score,
    })

    # 2) 섹터 분산 지수 (RSP/SPY 교체)
    disp_score = _sector_dispersion(close)
    components.append({
        "name": "섹터 분산 지수",
        "value": f"퍼센타일: {disp_score:.0%}",
        "score": disp_score,
    })

    # 3) High/Low ratio
    hl_score = _high_low_ratio(close)
    components.append({
        "name": "52주 고/저 비율",
        "value": f"신저가 구간 비율: {hl_score:.0%}",
        "score": hl_score,
    })

    # 4) McClellan proxy
    mc_score = _mcclellan_proxy(close)
    if "RSP" in close.columns:
        _rsp = close["RSP"].dropna()
        if len(_rsp) >= 39:
            _ret = _rsp.pct_change().dropna()
            _mc_val = (_ret.ewm(span=19).mean() - _ret.ewm(span=39).mean()).iloc[-1]
            mc_val = f"오실레이터: {_mc_val:+.5f}"
        else:
            mc_val = "데이터 부족"
    else:
        mc_val = "데이터 없음"
    components.append({
        "name": "McClellan 프록시",
        "value": mc_val,
        "score": mc_score,
    })

    # 가중 평균: 200MA(25%) + 섹터분산(30%) + 52주고저(20%) + McClellan(25%)
    weights = [0.25, 0.30, 0.20, 0.25]
    scores = [above_score, disp_score, hl_score, mc_score]
    final_score = sum(s * w for s, w in zip(scores, weights))

    return {
        "score": round(final_score, 4),
        "components": components,
        "detail": f"Breadth Score: {final_score:.2f} ({pct_above:.0%} sectors above 200MA)",
    }
