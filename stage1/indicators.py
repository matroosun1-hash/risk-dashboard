"""
1단계: 하락장 조기탐지 — 10개 지표 계산 모듈

각 지표는 0(정상), 0.5(선행경고), 1(위험 신호) 점수를 반환합니다.
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


def _velocity(series: pd.Series, lookback: int = 10, default=0.0):
    """최근 lookback일간 변화량 (마지막 값 - lookback일 전 값)."""
    clean = series.dropna()
    if len(clean) <= lookback:
        return default
    return float(clean.iloc[-1] - clean.iloc[-lookback])


def check_co_decline(close: pd.DataFrame, period: int = 20) -> dict:
    """
    지표 1: S&P500/나스닥 동반하락
    - score 1.0: SPY, QQQ 모두 20일 수익률 음수
    - score 0.5: 둘 다 +2% 이내이며 10일간 동반 하락 중 (선행 경고)
    - score 0.0: 정상
    """
    try:
        spy_ret = _safe_pct_change(close["SPY"], period, 0)
        qqq_ret = _safe_pct_change(close["QQQ"], period, 0)

        if spy_ret < 0 and qqq_ret < 0:
            score, status = 1, f"동반하락 확정 (SPY {spy_ret:.2%}, QQQ {qqq_ret:.2%})"
        else:
            # 10일간 수익률 추세 (0에 가까워지고 있는지)
            spy_ret_10d = _safe_pct_change(close["SPY"], 10, 0)
            qqq_ret_10d = _safe_pct_change(close["QQQ"], 10, 0)
            both_near_zero = spy_ret < 0.02 and qqq_ret < 0.02
            both_declining = spy_ret_10d < 0 and qqq_ret_10d < 0
            if both_near_zero and both_declining:
                score, status = 0.5, f"동반약세 접근 중 (SPY {spy_ret:.2%}, QQQ {qqq_ret:.2%}, 10일↓)"
            else:
                score, status = 0, f"정상 (SPY {spy_ret:.2%}, QQQ {qqq_ret:.2%})"

        return {
            "name": "S&P500/나스닥 동반하락",
            "score": score,
            "detail": status,
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
    - score 1.0: VIX >= danger (25)
    - score 0.5: VIX >= warning (20)
    - score 0.0: 정상
    """
    try:
        vix = _safe_last(close["^VIX"], 0)

        if vix >= danger:
            score = 1
        elif vix >= warning:
            score = 0.5
        else:
            score = 0

        status = "극도위험" if vix >= extreme else "위험" if vix >= danger else "주의" if vix >= warning else "정상"
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
    지표 3: 데스크로스 (SPY 50일선 < 200일선) + 수렴 속도 선행 감지
    - score 1.0: 데스크로스 확정 (50일 < 200일)
    - score 0.5: 갭이 3% 미만이며 10일간 빠르게 수렴 중
    - score 0.0: 정상
    """
    try:
        spy = close["SPY"].dropna()
        sma_short_series = get_sma(spy, short_period)
        sma_long_series  = get_sma(spy, long_period)

        sma_short = _safe_last(sma_short_series)
        sma_long  = _safe_last(sma_long_series)

        if pd.isna(sma_short) or pd.isna(sma_long):
            return {
                "name": "데스크로스 (SPY)",
                "score": 0,
                "detail": f"데이터 부족 (최소 {long_period}일 필요)",
                "sma_short": sma_short,
                "sma_long": sma_long,
            }

        gap_pct = (sma_short - sma_long) / sma_long

        velocity = 0.0
        if len(sma_short_series.dropna()) > 10 and len(sma_long_series.dropna()) > 10:
            s10 = sma_short_series.dropna().iloc[-10]
            l10 = sma_long_series.dropna().iloc[-10]
            gap_pct_10d = (s10 - l10) / l10
            velocity = gap_pct - gap_pct_10d  # 음수 = 갭이 빠르게 줄어드는 중

        if gap_pct < 0:
            score, status = 1, "데스크로스 확정"
        elif gap_pct < 0.03 and velocity < -0.01:
            score, status = 0.5, f"데스크로스 접근 중 (10일 수렴속도: {velocity:.2%})"
        else:
            score, status = 0, "정상"

        return {
            "name": "데스크로스 (SPY)",
            "score": score,
            "detail": f"50일선: {sma_short:.2f}, 200일선: {sma_long:.2f} | {status}",
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
    지표 4: 장단기금리 역전 (10Y - 3M)
    - score 1.0: 스프레드 < 0 (완전 역전)
    - score 0.5: 스프레드 0~0.5% (역전 임박) AND 10일간 하락 중
    - score 0.0: 정상
    """
    try:
        tnx_series = close["^TNX"].dropna()
        irx_series = close["^IRX"].dropna()
        tnx = _safe_last(tnx_series)
        irx = _safe_last(irx_series)

        if pd.isna(tnx) or pd.isna(irx):
            return {
                "name": "장단기금리 역전",
                "score": 0,
                "detail": f"데이터 없음 (10Y: {tnx}, 3M: {irx})",
                "spread": None,
            }

        spread = tnx - irx

        if spread < 0:
            score, status = 1, "역전 확정"
        elif spread < 0.5:
            # 10일간 스프레드 추세 확인
            if len(tnx_series) > 10 and len(irx_series) > 10:
                common = tnx_series.index.intersection(irx_series.index)
                if len(common) > 10:
                    spread_series = tnx_series.loc[common] - irx_series.loc[common]
                    spread_10d = float(spread_series.iloc[-10])
                    spread_velocity = spread - spread_10d  # 음수 = 스프레드 좁아지는 중
                    if spread_velocity < -0.1:
                        score, status = 0.5, f"역전 임박 (스프레드: {spread:.2f}%, 10일 속도: {spread_velocity:.2f}%p)"
                    else:
                        score, status = 0, f"정상 (스프레드 좁으나 안정적)"
                else:
                    score, status = 0.5, f"역전 임박 (스프레드: {spread:.2f}%)"
            else:
                score, status = 0.5, f"역전 임박 (스프레드: {spread:.2f}%)"
        else:
            score, status = 0, "정상"

        return {
            "name": "장단기금리 역전",
            "score": score,
            "detail": f"10Y: {tnx:.2f}%, 3M: {irx:.2f}%, 스프레드: {spread:.2f}% | {status}",
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
    지표 5: 하이일드 스프레드 (HYG/LQD 비율)
    - score 1.0: 20일 하락률 -2% 이상 (크레딧 위기)
    - score 0.5: 20일 하락률 -0.5% ~ -2% (스프레드 확대 조짐)
    - score 0.0: 정상
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

        if ratio_change < -0.02:
            score, status = 1, f"크레딧 위험 ({ratio_change:.2%})"
        elif ratio_change < -0.005:
            score, status = 0.5, f"스프레드 확대 조짐 ({ratio_change:.2%})"
        else:
            score, status = 0, "정상"

        return {
            "name": "하이일드 스프레드",
            "score": score,
            "detail": f"HYG/LQD {period}일 변화: {ratio_change:.2%} | {status}",
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
    지표 6: SPY 200일선 이탈 + 빠른 접근 선행 감지
    - score 1.0: SPY가 200일선 하회
    - score 0.5: 200일선 위이지만 빠르게 접근 중 (선행 경고)
    - score 0.0: 정상
    """
    try:
        spy = close["SPY"].dropna()
        sma200_series = get_sma(spy, sma_period)
        sma200  = _safe_last(sma200_series)
        current = _safe_last(spy)

        if pd.isna(sma200) or pd.isna(current):
            return {
                "name": "SPY 200일선 이탈",
                "score": 0,
                "detail": f"데이터 부족 (최소 {sma_period}일 필요)",
                "current": current,
                "sma200": sma200,
            }

        gap_pct = (current / sma200 - 1)

        velocity = 0.0
        if len(spy) > 10 and len(sma200_series.dropna()) > 10:
            prev_price = spy.iloc[-10]
            prev_sma   = sma200_series.dropna().iloc[-10]
            gap_pct_10d = (prev_price / prev_sma - 1)
            velocity = gap_pct - gap_pct_10d  # 음수 = 200일선으로 빠르게 접근 중

        if gap_pct < 0:
            score, status = 1, "200일선 하회"
        elif gap_pct < 0.03 and velocity < -0.015:
            score, status = 0.5, f"200일선 빠르게 접근 중 (10일 속도: {velocity:.2%})"
        else:
            score, status = 0, "정상"

        return {
            "name": "SPY 200일선 이탈",
            "score": score,
            "detail": f"SPY: {current:.2f}, 200SMA: {sma200:.2f} ({gap_pct:+.2%}) | {status}",
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
    지표 7: 달러 강세 (UUP)
    - score 1.0: 20일 상승률 > 2% (달러 강세 확정)
    - score 0.5: 20일 상승률 1~2% (달러 강세 조짐)
    - score 0.0: 정상
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

        if uup_ret > threshold:
            score, status = 1, f"달러 강세 확정 ({uup_ret:.2%})"
        elif uup_ret > threshold * 0.5:
            score, status = 0.5, f"달러 강세 조짐 ({uup_ret:.2%})"
        else:
            score, status = 0, "정상"

        return {
            "name": "달러 강세 (UUP)",
            "score": score,
            "detail": f"UUP {period}일 수익률: {uup_ret:.2%} | {status}",
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
    - score 1.0: 20일 하락률 -2% 이상 (폭넓은 하락)
    - score 0.5: 20일 하락률 -0.5% ~ -2% (시장폭 약화 조짐)
    - score 0.0: 정상
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

        if ratio_change < -0.02:
            score, status = 1, f"시장폭 급격히 약화 ({ratio_change:.2%})"
        elif ratio_change < -0.005:
            score, status = 0.5, f"시장폭 약화 조짐 ({ratio_change:.2%})"
        else:
            score, status = 0, "정상"

        return {
            "name": "시장폭 (RSP/SPY)",
            "score": score,
            "detail": f"RSP/SPY {period}일 변화: {ratio_change:.2%} | {status}",
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
    - score 1.0: 20일 하락률 -2% 이상 (소형주 급격 약세)
    - score 0.5: 20일 하락률 -0.5% ~ -2% (소형주 약세 조짐)
    - score 0.0: 정상
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

        if ratio_change < -0.02:
            score, status = 1, f"소형주 급격 약세 ({ratio_change:.2%})"
        elif ratio_change < -0.005:
            score, status = 0.5, f"소형주 약세 조짐 ({ratio_change:.2%})"
        else:
            score, status = 0, "정상"

        return {
            "name": "소형주 약세 (IWM/SPY)",
            "score": score,
            "detail": f"IWM/SPY {period}일 변화: {ratio_change:.2%} | {status}",
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
    지표 10: 채권변동성 (TLT 롤링 표준편차)
    - score 1.0: 변동성 > 임계값 (0.015)
    - score 0.5: 변동성 임계값의 70% ~ 100% (상승 조짐)
    - score 0.0: 정상
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

        if vol > threshold:
            score, status = 1, f"채권변동성 위험 ({vol:.4f})"
        elif vol > threshold * 0.7:
            score, status = 0.5, f"채권변동성 상승 조짐 ({vol:.4f})"
        else:
            score, status = 0, "정상"

        return {
            "name": "채권변동성 (TLT 변동성)",
            "score": score,
            "detail": f"TLT {period}일 변동성: {vol:.4f} (임계: {threshold:.4f}) | {status}",
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
