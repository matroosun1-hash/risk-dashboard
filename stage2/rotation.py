"""
2단계: 섹터 로테이션 탐지 — 4개 상대성과 쌍 추적

4개 쌍의 상대 성과 비율 변화율(20일 기준)을 계산하여
위험자산 → 안전자산 자금 이동을 탐지합니다.
"""

import pandas as pd
import numpy as np
from data.fetcher import get_ratio


def calculate_rotation_pair(
    close: pd.DataFrame,
    numerator: str,
    denominator: str,
    period: int = 20,
) -> dict:
    """
    단일 로테이션 쌍의 상대 성과 변화율을 계산합니다.

    Args:
        close: 종가 DataFrame
        numerator: 분자 티커 (위험자산)
        denominator: 분모 티커 (안전자산)
        period: 비교 기간 (영업일)

    Returns:
        결과 딕셔너리
    """
    try:
        ratio = get_ratio(close, numerator, denominator)

        if len(ratio.dropna()) < period + 1:
            return {
                "pair": f"{numerator}/{denominator}",
                "change": None,
                "current_ratio": None,
                "signal": False,
                "detail": f"데이터 부족 ({len(ratio.dropna())}일 < {period}일)",
            }

        current = ratio.dropna().iloc[-1]
        past = ratio.dropna().iloc[-period]
        change = (current / past) - 1

        return {
            "pair": f"{numerator}/{denominator}",
            "change": change,
            "current_ratio": current,
            "past_ratio": past,
            "signal": change < 0,  # 음수면 위험자산 약세 신호
            "detail": f"{period}일 변화: {change:+.2%} (현재: {current:.4f})",
        }
    except (ValueError, KeyError) as e:
        return {
            "pair": f"{numerator}/{denominator}",
            "change": None,
            "current_ratio": None,
            "signal": False,
            "detail": f"에러: {e}",
        }


def calculate_all_rotations(close: pd.DataFrame, config: dict) -> list[dict]:
    """
    config에 정의된 모든 로테이션 쌍을 계산합니다.

    Args:
        close: 종가 DataFrame
        config: stage2 설정

    Returns:
        로테이션 쌍 결과 리스트
    """
    period = config.get("rotation_period", 20)
    pairs = config.get("rotation_pairs", [])
    threshold = config.get("rotation_threshold", -0.03)

    results = []
    for pair in pairs:
        result = calculate_rotation_pair(
            close,
            pair["numerator"],
            pair["denominator"],
            period,
        )
        # 임계값 적용: 단순 음수가 아니라 threshold 이하인 경우만 강한 신호
        if result["change"] is not None:
            result["strong_signal"] = result["change"] <= threshold
            result["label"] = pair.get("label", result["pair"])
        else:
            result["strong_signal"] = False
            result["label"] = pair.get("label", result["pair"])

        results.append(result)

    return results


def get_rotation_summary(rotation_results: list[dict]) -> dict:
    """
    로테이션 쌍 결과를 요약합니다.

    Returns:
        - negative_count: 음수인 쌍 수
        - strong_count: 임계값 이하인 쌍 수
        - all_negative: 모든 쌍이 음수인지
    """
    valid = [r for r in rotation_results if r["change"] is not None]
    negative_count = sum(1 for r in valid if r["signal"])
    strong_count = sum(1 for r in valid if r.get("strong_signal", False))

    return {
        "total_pairs": len(valid),
        "negative_count": negative_count,
        "strong_count": strong_count,
        "all_negative": negative_count == len(valid) and len(valid) > 0,
    }
