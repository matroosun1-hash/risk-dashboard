"""
signals/cross_asset.py — 교차자산 리스크 신호 (Cross-Asset Risk Signal)

주식-채권-금-달러-원유-크레딧 간 상관관계 괴리를 탐지합니다.
정상적 상관관계가 깨지면 위험 신호로 판단합니다.
"""

import pandas as pd
import numpy as np


# 괴리 패턴 정의: (Asset A 방향, Asset B 방향) → 위험 신호
DIVERGENCE_PAIRS = [
    {
        "name": "주식↑ + 크레딧↓",
        "desc": "주가 상승하나 크레딧 악화 → 거품 경고",
        "asset_a": "SPY", "dir_a": "up",
        "asset_b": "HYG", "dir_b": "down",
        "weight": 0.25,
    },
    {
        "name": "주식↓ + 달러↑",
        "desc": "위험회피 (risk-off) 신호",
        "asset_a": "SPY", "dir_a": "down",
        "asset_b": "UUP", "dir_b": "up",
        "weight": 0.20,
    },
    {
        "name": "채권↑ + 금↑",
        "desc": "안전자산 동시 선호 → 위기 경계",
        "asset_a": "TLT", "dir_a": "up",
        "asset_b": "GLD", "dir_b": "up",
        "weight": 0.20,
    },
    {
        "name": "주식↑ + 금↑",
        "desc": "불확실성 하에서의 동시 상승 → 인플레이션 또는 불안",
        "asset_a": "SPY", "dir_a": "up",
        "asset_b": "GLD", "dir_b": "up",
        "weight": 0.15,
    },
    {
        "name": "크레딧↓ + 채권↑",
        "desc": "크레딧 스트레스 + 안전자산 선호",
        "asset_a": "HYG", "dir_a": "down",
        "asset_b": "TLT", "dir_b": "up",
        "weight": 0.20,
    },
]


def _get_return(close: pd.DataFrame, ticker: str, period: int = 20) -> float:
    """N일 수익률을 안전하게 계산합니다."""
    if ticker not in close.columns:
        return 0.0
    series = close[ticker].dropna()
    if len(series) <= period:
        return 0.0
    return float(series.iloc[-1] / series.iloc[-period] - 1)


def _check_divergence(ret_a: float, dir_a: str, ret_b: float, dir_b: str,
                       threshold: float = 0.005) -> tuple[bool, float]:
    """괴리 패턴이 발생했는지 확인합니다.
    Returns: (triggered, intensity)"""
    cond_a = (ret_a > threshold) if dir_a == "up" else (ret_a < -threshold)
    cond_b = (ret_b > threshold) if dir_b == "up" else (ret_b < -threshold)

    if cond_a and cond_b:
        intensity = (abs(ret_a) + abs(ret_b)) / 2
        return True, intensity
    return False, 0.0


def calculate_cross_asset_score(close: pd.DataFrame, config: dict = None, period: int = 20) -> dict:
    """
    교차자산 괴리 스코어를 계산합니다.

    Returns:
        {"score": 0~1, "components": [...], "detail": str}
    """
    components = []
    triggered_weight = 0.0
    total_weight = 0.0

    for pair in DIVERGENCE_PAIRS:
        ret_a = _get_return(close, pair["asset_a"], period)
        ret_b = _get_return(close, pair["asset_b"], period)

        triggered, intensity = _check_divergence(
            ret_a, pair["dir_a"], ret_b, pair["dir_b"]
        )

        total_weight += pair["weight"]
        if triggered:
            # 강도에 따라 가중 (최소 1.0, 최대 3.0)
            intensity_multiplier = np.clip(intensity / 0.02, 1.0, 3.0)
            triggered_weight += pair["weight"] * intensity_multiplier

        components.append({
            "name": pair["name"],
            "desc": pair["desc"],
            "triggered": triggered,
            "asset_a": f"{pair['asset_a']} {ret_a:+.2%}",
            "asset_b": f"{pair['asset_b']} {ret_b:+.2%}",
            "intensity": intensity,
        })

    # 정규화
    if total_weight > 0:
        final_score = triggered_weight / total_weight
    else:
        final_score = 0.0

    triggered_count = sum(1 for c in components if c["triggered"])

    return {
        "score": round(min(final_score, 1.0), 4),
        "components": components,
        "triggered_count": triggered_count,
        "detail": f"Cross-Asset: {final_score:.2f} ({triggered_count}/{len(DIVERGENCE_PAIRS)} divergences)",
    }
