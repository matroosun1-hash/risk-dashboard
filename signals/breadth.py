"""
signals/breadth.py — 시장 폭(Market Breadth) 엔진

시장 내부 구조 붕괴를 탐지합니다.
S&P 500 개별 종목 데이터 대신 섹터 ETF 기반 프록시를 사용합니다.
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


def _rsp_spy_breadth(close: pd.DataFrame, period: int = 20) -> float:
    """RSP/SPY 비율 변화로 시장 폭 측정.
    하락 = 대형주 집중, 상승 = 폭넓은 참여."""
    if "RSP" not in close.columns or "SPY" not in close.columns:
        return 0.5

    ratio = (close["RSP"] / close["SPY"]).dropna()
    if len(ratio) <= period:
        return 0.5

    change = ratio.iloc[-1] / ratio.iloc[-period] - 1
    # -5% ~ +5% 범위를 0~1로 매핑 (음수=나쁨→1, 양수=좋음→0)
    score = np.clip(-change / 0.05 * 0.5 + 0.5, 0, 1)
    return float(score)


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

    # 2) RSP/SPY Breadth
    rsp_score = _rsp_spy_breadth(close)
    components.append({
        "name": "RSP/SPY 시장폭",
        "value": f"score={rsp_score:.2f}",
        "score": rsp_score,
    })

    # 3) High/Low ratio
    hl_score = _high_low_ratio(close)
    components.append({
        "name": "52주 고/저 비율",
        "value": f"score={hl_score:.2f}",
        "score": hl_score,
    })

    # 4) McClellan proxy
    mc_score = _mcclellan_proxy(close)
    components.append({
        "name": "McClellan 프록시",
        "value": f"score={mc_score:.2f}",
        "score": mc_score,
    })

    # 가중 평균
    weights = [0.30, 0.25, 0.20, 0.25]
    scores = [above_score, rsp_score, hl_score, mc_score]
    final_score = sum(s * w for s, w in zip(scores, weights))

    return {
        "score": round(final_score, 4),
        "components": components,
        "detail": f"Breadth Score: {final_score:.2f} ({pct_above:.0%} sectors above 200MA)",
    }
