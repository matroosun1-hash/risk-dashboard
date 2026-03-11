"""
2단계: 섹터 로테이션 탐지 — 3개 선행지표 확인

7일 기준으로 확인:
- GLD (금): 상승 → 안전자산 선호 신호
- BTC-USD (비트코인): 하락 → 위험자산 회피 신호
- SMH/SPY (반도체 상대강도): 하락 → 기술주 약세 선행 신호
"""

import pandas as pd
import numpy as np
from data.fetcher import get_ratio


def check_leading_indicator(
    close: pd.DataFrame,
    ticker: str,
    period: int = 7,
    signal_direction: str = "negative",
    reference: str | None = None,
    label: str = "",
) -> dict:
    """
    선행지표 하나를 확인합니다.

    Args:
        close: 종가 DataFrame
        ticker: 확인할 티커
        period: 비교 기간
        signal_direction: "positive"(상승이 신호) 또는 "negative"(하락이 신호)
        reference: 상대비교 기준 티커 (예: SMH의 경우 SPY)
        label: 표시 라벨

    Returns:
        결과 딕셔너리
    """
    try:
        if reference:
            # 상대강도 계산
            ratio = get_ratio(close, ticker, reference)
            series = ratio
            display_name = f"{ticker}/{reference}"
        else:
            series = close[ticker]
            display_name = ticker

        if len(series.dropna()) < period + 1:
            return {
                "label": label or display_name,
                "ticker": display_name,
                "change": None,
                "signal": False,
                "detail": "데이터 부족",
            }

        current = series.dropna().iloc[-1]
        past = series.dropna().iloc[-period]
        change = (current / past) - 1

        if signal_direction == "positive":
            signal = change > 0
        else:
            signal = change < 0

        direction_label = "상승" if change > 0 else "하락"
        signal_icon = "⚠️" if signal else "✅"

        return {
            "label": label or display_name,
            "ticker": display_name,
            "change": change,
            "signal": signal,
            "detail": f"{signal_icon} {period}일 {direction_label}: {change:+.2%}",
        }
    except (ValueError, KeyError) as e:
        return {
            "label": label or ticker,
            "ticker": ticker,
            "change": None,
            "signal": False,
            "detail": f"에러: {e}",
        }


def check_all_leading(close: pd.DataFrame, config: dict) -> list[dict]:
    """
    config에 정의된 모든 선행지표를 확인합니다.

    Args:
        close: 종가 DataFrame
        config: stage2 설정

    Returns:
        선행지표 결과 리스트
    """
    period = config.get("leading_period", 7)
    indicators = config.get("leading_indicators", [])

    results = []
    for ind in indicators:
        result = check_leading_indicator(
            close,
            ticker=ind["ticker"],
            period=period,
            signal_direction=ind.get("signal", "negative"),
            reference=ind.get("reference"),
            label=ind.get("label", ""),
        )
        results.append(result)

    return results


def get_leading_summary(leading_results: list[dict]) -> dict:
    """선행지표 결과를 요약합니다."""
    valid = [r for r in leading_results if r["change"] is not None]
    signal_count = sum(1 for r in valid if r["signal"])

    return {
        "total": len(valid),
        "signal_count": signal_count,
        "all_confirmed": signal_count == len(valid) and len(valid) > 0,
    }
