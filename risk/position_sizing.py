"""
risk/position_sizing.py — Dynamic Position Sizing

Risk Score에 기반한 자산 배분 비율을 결정합니다.
Volatility Targeting과 기본 매핑 테이블 두 가지 방식을 지원합니다.
"""

import pandas as pd
import numpy as np


def get_allocation_from_table(risk_score: float, config: dict) -> dict:
    """
    Risk Score → 자산 배분 매핑 테이블에서 배분 비율을 반환합니다.

    Args:
        risk_score: 0~1
        config: position_sizing 설정

    Returns:
        {"equity": float, "treasury": float, "gold": float, "cash": float}
    """
    ps_cfg = config.get("position_sizing", {})
    alloc_map = ps_cfg.get("allocation_map", [])

    if not alloc_map:
        # 기본 매핑
        alloc_map = [
            {"risk_max": 0.2, "equity": 0.80, "treasury": 0.10, "gold": 0.05, "cash": 0.05},
            {"risk_max": 0.4, "equity": 0.60, "treasury": 0.15, "gold": 0.10, "cash": 0.15},
            {"risk_max": 0.6, "equity": 0.40, "treasury": 0.20, "gold": 0.15, "cash": 0.25},
            {"risk_max": 0.8, "equity": 0.20, "treasury": 0.25, "gold": 0.20, "cash": 0.35},
            {"risk_max": 1.0, "equity": 0.05, "treasury": 0.20, "gold": 0.20, "cash": 0.55},
        ]

    for tier in alloc_map:
        if risk_score <= tier["risk_max"]:
            return {
                "equity": tier["equity"],
                "treasury": tier["treasury"],
                "gold": tier["gold"],
                "cash": tier["cash"],
            }

    # risk_score > 1 (극단)
    return alloc_map[-1]


def volatility_target_adjustment(
    base_allocation: dict,
    current_vol: float,
    target_vol: float = 0.12,
) -> dict:
    """
    Volatility Targeting: 현재 변동성이 목표보다 높으면 주식 비중 축소.

    Args:
        base_allocation: 기본 배분
        current_vol: 현재 연율화 변동성
        target_vol: 목표 변동성 (기본 12%)

    Returns:
        조정된 배분 딕셔너리
    """
    if current_vol <= 0 or target_vol <= 0:
        return base_allocation

    # 변동성 비율 계산
    vol_ratio = target_vol / current_vol
    vol_ratio = np.clip(vol_ratio, 0.1, 1.0)  # 레버리지 확대 방지: 목표보다 낮아도 비중 증가 안함

    adjusted = base_allocation.copy()
    original_equity = adjusted["equity"]

    # 주식 비중만 변동성 비율로 조정
    adjusted["equity"] = round(original_equity * vol_ratio, 4)

    # 차이분을 현금으로 이동
    diff = original_equity - adjusted["equity"]
    adjusted["cash"] = round(adjusted["cash"] + diff, 4)

    # 정규화 (합계 = 1)
    total = sum(adjusted.values())
    if total > 0:
        adjusted = {k: round(v / total, 4) for k, v in adjusted.items()}

    return adjusted


def calculate_position_sizing(
    risk_score: float,
    close: pd.DataFrame,
    config: dict,
) -> dict:
    """
    Risk Score 기반으로 최종 포지션 사이징을 계산합니다.

    Returns:
        {
            "allocation": {"equity": %, "treasury": %, "gold": %, "cash": %},
            "base_allocation": 원본 (vol targeting 전),
            "vol_adjusted": bool,
            "current_vol": float,
            "target_vol": float,
            "detail": str,
        }
    """
    ps_cfg = config.get("position_sizing", {})
    target_vol = ps_cfg.get("target_volatility", 0.12)

    # 1) 테이블에서 기본 배분 결정
    base = get_allocation_from_table(risk_score, config)

    # 2) Volatility Targeting 조정
    current_vol = None
    vol_adjusted = False

    if "SPY" in close.columns:
        spy_ret = close["SPY"].dropna().pct_change().dropna()
        if len(spy_ret) > 20:
            current_vol = float(spy_ret.rolling(20).std().iloc[-1] * np.sqrt(252))

    if current_vol is not None and current_vol > 0:
        allocation = volatility_target_adjustment(base, current_vol, target_vol)
        vol_adjusted = (allocation["equity"] != base["equity"])
    else:
        allocation = base

    return {
        "allocation": allocation,
        "base_allocation": base,
        "vol_adjusted": vol_adjusted,
        "current_vol": current_vol,
        "target_vol": target_vol,
        "risk_score": risk_score,
        "detail": (
            f"Equity: {allocation['equity']:.0%} | "
            f"Treasury: {allocation['treasury']:.0%} | "
            f"Gold: {allocation['gold']:.0%} | "
            f"Cash: {allocation['cash']:.0%}"
        ),
    }
