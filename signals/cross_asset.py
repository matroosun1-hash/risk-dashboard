"""
signals/cross_asset.py — 교차자산 리스크 신호 (Cross-Asset Risk Signal)

주식-채권-금-달러-원유-크레딧 간 상관관계 괴리를 탐지합니다.
정상적 상관관계가 깨지면 위험 신호로 판단합니다.

개선: 이진 trigger → 시그모이드 연속 점수. 양극단 분포 해소.
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


def _sigmoid(value: float, center: float, steepness: float = 10.0) -> float:
    """center 근처에서 0→1 점진적 전환 (시그모이드)."""
    return 1.0 / (1.0 + np.exp(-steepness * (value - center)))


def _continuous_divergence_score(
    ret_a: float, dir_a: str,
    ret_b: float, dir_b: str,
    threshold: float = 0.005,
) -> tuple[float, float]:
    """
    연속 괴리 점수를 계산합니다.

    이진 trigger 대신 시그모이드로 0~1 연속 점수 산출.
    두 조건의 점수를 곱하여 교차 스코어 계산.

    Returns: (pair_score, intensity)
    """
    # 각 조건의 방향 일치도 (시그모이드)
    if dir_a == "up":
        score_a = _sigmoid(ret_a, threshold)
    else:
        score_a = _sigmoid(-ret_a, threshold)

    if dir_b == "up":
        score_b = _sigmoid(ret_b, threshold)
    else:
        score_b = _sigmoid(-ret_b, threshold)

    # 교차 곱: 두 조건 모두 강해야 높은 점수
    pair_score = score_a * score_b

    # 강도 보정 (상한 1.5로 축소)
    intensity = (abs(ret_a) + abs(ret_b)) / 2
    intensity_factor = min(intensity / 0.02, 1.5)

    return float(pair_score * intensity_factor), float(intensity)


def calculate_cross_asset_score(close: pd.DataFrame, config: dict = None, period: int = 20) -> dict:
    """
    교차자산 괴리 스코어를 계산합니다.

    Returns:
        {"score": 0~1, "components": [...], "detail": str}
    """
    components = []
    weighted_score = 0.0
    total_weight = 0.0

    for pair in DIVERGENCE_PAIRS:
        ret_a = _get_return(close, pair["asset_a"], period)
        ret_b = _get_return(close, pair["asset_b"], period)

        pair_score, intensity = _continuous_divergence_score(
            ret_a, pair["dir_a"], ret_b, pair["dir_b"]
        )

        total_weight += pair["weight"]
        weighted_score += pair["weight"] * pair_score

        components.append({
            "name": pair["name"],
            "desc": pair["desc"],
            "triggered": pair_score > 0.5,
            "asset_a": f"{pair['asset_a']} {ret_a:+.2%}",
            "asset_b": f"{pair['asset_b']} {ret_b:+.2%}",
            "intensity": intensity,
            "pair_score": round(pair_score, 3),
        })

    # 정규화
    if total_weight > 0:
        final_score = weighted_score / total_weight
    else:
        final_score = 0.0

    triggered_count = sum(1 for c in components if c["triggered"])

    return {
        "score": round(min(final_score, 1.0), 4),
        "components": components,
        "triggered_count": triggered_count,
        "detail": f"Cross-Asset: {final_score:.2f} ({triggered_count}/{len(DIVERGENCE_PAIRS)} divergences)",
    }
