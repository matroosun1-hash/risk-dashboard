"""
1단계: 하락장 조기탐지 — 10개 지표 계산 모듈

각 지표는 0(정상) 또는 1(위험 신호) 점수를 반환합니다.
모든 지표는 NaN에 안전하게 설계되어 있습니다.
"""

import pandas as pd
import numpy as np
from data.fetcher import get_sma, get_rolling_std, get_ratio


def _safe_last(series: pd.Series, default=np.nan):
    """시리즈에서 마지막 유효값을 안전하게 반환합니다."""
    clean = series.dropna()
    if clean.empty:
        return default
    return clean.iloc[-1]


def _safe_pct_change(series: pd.Series, period: int = 20, default=np.nan):
    """NaN-safe 수익률 계산."""
    clean = series.dropna()
    if len(clean) <= period:
        return default
    return (clean.iloc[-1] / clean.iloc[-period] - 1)


def check_co_decline(close: pd.DataFrame, period: int = 20) -> dict:
    """
    지표 1: S&P500/나스닥 동반하락
    SPY와 QQQ 모두 N일 수익률이 음수이면 신호 발동.
    """
    try:
        spy_ret = _safe_pct_change(close["SPY"], period, 0)
        qqq_ret = _safe_pct_change(close["QQQ"], period, 0)

        triggered = (spy_ret < 0) and (qqq_ret < 0)
        return {
            "name": "S&P500/나스닥 동반하락",
            "score": 1 if triggered else 0,
            "detail": f"SPY {period}일: {spy_ret:.2%}, QQQ: {qqq_ret:.2%}",
            "spy_ret": spy_ret,
            "qqq_ret": qqq_ret,
        }
    except KeyError:
        return {
            "name": "S&P500/나스닥 동반하락",
            "score": 0,
            "detail": "데이터 없음 (SPY 또는 QQQ)",
            "spy_ret": None,
            "qqq_ret": None,
        }


def check_vix(close: pd.DataFrame, warning: float = 20, danger: float = 25, extreme: float = 30) -> dict:
    """
    지표 2: VIX 공포지수
    """
    try:
        vix = _safe_last(close["^VIX"], 0)

        if vix >= danger:
            score = 1
        elif vix >= warning:
            score = 0.5
        else:
            score = 0

        status = "🔴 극도위험" if vix >= extreme else "🟠 위험" if vix >= danger else "🟡 주의" if vix >= warning else "🟢 정상"
        return {
            "name": "VIX 공포지수",
            "score": score,
            "detail": f"VIX: {vix:.1f} ({status})",
            "vix": vix,
        }
    except KeyError:
        return {
            "name": "VIX 공포지수",
            "score": 0,
            "detail": "데이터 없음 (^VIX)",
            "vix": None,
        }


def check_death_cross(close: pd.DataFrame, short_period: int = 50, long_period: int = 200) -> dict:
    """
    지표 3: 데스크로스 (SPY 50일선 < 200일선)
    """
    try:
        spy = close["SPY"].dropna()
        sma_short = _safe_last(get_sma(spy, short_period))
        sma_long = _safe_last(get_sma(spy, long_period))

        if pd.isna(sma_short) or pd.isna(sma_long):
            return {
                "name": "데스크로스 (SPY)",
                "score": 0,
                "detail": f"데이터 부족 (최소 {long_period}일 필요)",
                "sma_short": sma_short,
                "sma_long": sma_long,
            }

        triggered = sma_short < sma_long
        return {
            "name": "데스크로스 (SPY)",
            "score": 1 if triggered else 0,
            "detail": f"50일선: {sma_short:.2f}, 200일선: {sma_long:.2f}",
            "sma_short": sma_short,
            "sma_long": sma_long,
        }
    except KeyError:
        return {
            "name": "데스크로스 (SPY)",
            "score": 0,
            "detail": "데이터 없음 (SPY)",
            "sma_short": None,
            "sma_long": None,
        }


def check_yield_curve(close: pd.DataFrame) -> dict:
    """
    지표 4: 장단기금리 역전 (10Y - 3M < 0)
    """
    try:
        tnx = _safe_last(close["^TNX"])
        irx = _safe_last(close["^IRX"])

        if pd.isna(tnx) or pd.isna(irx):
            return {
                "name": "장단기금리 역전",
                "score": 0,
                "detail": f"데이터 없음 (10Y: {tnx}, 3M: {irx})",
                "spread": None,
            }

        spread = tnx - irx
        triggered = spread < 0
        return {
            "name": "장단기금리 역전",
            "score": 1 if triggered else 0,
            "detail": f"10Y: {tnx:.2f}%, 3M: {irx:.2f}%, 스프레드: {spread:.2f}%",
            "spread": spread,
        }
    except KeyError:
        return {
            "name": "장단기금리 역전",
            "score": 0,
            "detail": "데이터 없음 (^TNX 또는 ^IRX)",
            "spread": None,
        }


def check_hy_spread(close: pd.DataFrame, period: int = 20) -> dict:
    """
    지표 5: 하이일드 스프레드
    HYG/LQD 비율이 N일간 하락 → 크레딧 리스크 확대
    """
    try:
        ratio = get_ratio(close, "HYG", "LQD")
        ratio_change = _safe_pct_change(ratio, period)

        if pd.isna(ratio_change):
            return {
                "name": "하이일드 스프레드",
                "score": 0,
                "detail": f"데이터 부족 (최소 {period}일 필요)",
                "ratio_change": None,
            }

        triggered = ratio_change < -0.01
        return {
            "name": "하이일드 스프레드",
            "score": 1 if triggered else 0,
            "detail": f"HYG/LQD {period}일 변화: {ratio_change:.2%}",
            "ratio_change": ratio_change,
        }
    except (ValueError, KeyError):
        return {
            "name": "하이일드 스프레드",
            "score": 0,
            "detail": "데이터 없음 (HYG 또는 LQD)",
            "ratio_change": None,
        }


def check_spy_below_200sma(close: pd.DataFrame, sma_period: int = 200) -> dict:
    """
    지표 6: SPY 200일선 이탈
    """
    try:
        spy = close["SPY"].dropna()
        sma200 = _safe_last(get_sma(spy, sma_period))
        current = _safe_last(spy)

        if pd.isna(sma200) or pd.isna(current):
            return {
                "name": "SPY 200일선 이탈",
                "score": 0,
                "detail": f"데이터 부족 (최소 {sma_period}일 필요)",
                "current": current,
                "sma200": sma200,
            }

        triggered = current < sma200
        pct_diff = (current / sma200 - 1)
        return {
            "name": "SPY 200일선 이탈",
            "score": 1 if triggered else 0,
            "detail": f"SPY: {current:.2f}, 200SMA: {sma200:.2f} ({pct_diff:+.2%})",
            "current": current,
            "sma200": sma200,
        }
    except KeyError:
        return {
            "name": "SPY 200일선 이탈",
            "score": 0,
            "detail": "데이터 없음 (SPY)",
            "current": None,
            "sma200": None,
        }


def check_dollar_strength(close: pd.DataFrame, period: int = 20, threshold: float = 0.02) -> dict:
    """
    지표 7: 달러 강세
    UUP(달러 ETF)의 N일 수익률이 임계값 이상이면 신호 발동.
    """
    try:
        uup_ret = _safe_pct_change(close["UUP"], period)

        if pd.isna(uup_ret):
            return {
                "name": "달러 강세 (UUP)",
                "score": 0,
                "detail": "데이터 부족",
                "uup_ret": None,
            }

        triggered = uup_ret > threshold
        return {
            "name": "달러 강세 (UUP)",
            "score": 1 if triggered else 0,
            "detail": f"UUP {period}일 수익률: {uup_ret:.2%} (임계: {threshold:.2%})",
            "uup_ret": uup_ret,
        }
    except KeyError:
        return {
            "name": "달러 강세 (UUP)",
            "score": 0,
            "detail": "데이터 없음 (UUP)",
            "uup_ret": None,
        }


def check_market_breadth(close: pd.DataFrame, period: int = 20) -> dict:
    """
    지표 8: 시장폭 (RSP/SPY 비율)
    """
    try:
        ratio = get_ratio(close, "RSP", "SPY")
        ratio_change = _safe_pct_change(ratio, period)

        if pd.isna(ratio_change):
            return {
                "name": "시장폭 (RSP/SPY)",
                "score": 0,
                "detail": "데이터 부족",
                "ratio_change": None,
            }

        triggered = ratio_change < -0.01
        return {
            "name": "시장폭 (RSP/SPY)",
            "score": 1 if triggered else 0,
            "detail": f"RSP/SPY {period}일 변화: {ratio_change:.2%}",
            "ratio_change": ratio_change,
        }
    except (ValueError, KeyError):
        return {
            "name": "시장폭 (RSP/SPY)",
            "score": 0,
            "detail": "데이터 없음 (RSP 또는 SPY)",
            "ratio_change": None,
        }


def check_small_cap(close: pd.DataFrame, period: int = 20) -> dict:
    """
    지표 9: 소형주 약세 (IWM/SPY 비율)
    """
    try:
        ratio = get_ratio(close, "IWM", "SPY")
        ratio_change = _safe_pct_change(ratio, period)

        if pd.isna(ratio_change):
            return {
                "name": "소형주 약세 (IWM/SPY)",
                "score": 0,
                "detail": "데이터 부족",
                "ratio_change": None,
            }

        triggered = ratio_change < -0.01
        return {
            "name": "소형주 약세 (IWM/SPY)",
            "score": 1 if triggered else 0,
            "detail": f"IWM/SPY {period}일 변화: {ratio_change:.2%}",
            "ratio_change": ratio_change,
        }
    except (ValueError, KeyError):
        return {
            "name": "소형주 약세 (IWM/SPY)",
            "score": 0,
            "detail": "데이터 없음 (IWM 또는 SPY)",
            "ratio_change": None,
        }


def check_bond_volatility(close: pd.DataFrame, period: int = 20, threshold: float = 0.015) -> dict:
    """
    지표 10: 채권변동성 (MOVE 지수 대체)
    TLT의 일일수익률 롤링 표준편차로 채권시장 변동성을 측정합니다.
    """
    try:
        tlt_returns = close["TLT"].dropna().pct_change()
        vol = _safe_last(get_rolling_std(tlt_returns, period))

        if pd.isna(vol):
            return {
                "name": "채권변동성 (TLT 변동성)",
                "score": 0,
                "detail": "데이터 부족",
                "volatility": None,
            }

        triggered = vol > threshold
        return {
            "name": "채권변동성 (TLT 변동성)",
            "score": 1 if triggered else 0,
            "detail": f"TLT {period}일 변동성: {vol:.4f} (임계: {threshold:.4f})",
            "volatility": vol,
        }
    except KeyError:
        return {
            "name": "채권변동성 (TLT 변동성)",
            "score": 0,
            "detail": "데이터 없음 (TLT)",
            "volatility": None,
        }


def run_all_indicators(close: pd.DataFrame, config: dict) -> list[dict]:
    """
    10개 지표를 모두 실행하고 결과를 반환합니다.
    """
    results = [
        check_co_decline(close, config.get("co_decline_period", 20)),
        check_vix(close, config.get("vix_warning", 20), config.get("vix_danger", 25), config.get("vix_extreme", 30)),
        check_death_cross(close, config.get("death_cross_sma_short", 50), config.get("death_cross_sma_long", 200)),
        check_yield_curve(close),
        check_hy_spread(close, config.get("hy_spread_period", 20)),
        check_spy_below_200sma(close, config.get("spy_sma_period", 200)),
        check_dollar_strength(close, config.get("uup_period", 20), config.get("uup_threshold", 0.02)),
        check_market_breadth(close, config.get("market_breadth_period", 20)),
        check_small_cap(close, config.get("small_cap_period", 20)),
        check_bond_volatility(close, config.get("bond_vol_period", 20), config.get("bond_vol_threshold", 0.015)),
    ]
    return results
