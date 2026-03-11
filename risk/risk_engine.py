"""
risk/risk_engine.py — Multi-Signal Risk Aggregation Engine

모든 신호를 통합하여 최종 Risk Score(0~1)를 계산합니다.
가중 앙상블(Weighted Ensemble) 방식을 사용합니다.
"""

import logging
import pandas as pd
import numpy as np

from signals.macro import calculate_macro_score

logger = logging.getLogger(__name__)
from signals.liquidity import calculate_liquidity_score
from signals.breadth import calculate_breadth_score
from signals.volatility import calculate_volatility_score
from signals.cross_asset import calculate_cross_asset_score
from regime.regime_model import detect_regime


def calculate_final_risk(close: pd.DataFrame, config: dict) -> dict:
    """
    모든 신호를 수집하고 가중 평균으로 최종 리스크 스코어를 계산합니다.

    Args:
        close: 종가 DataFrame
        config: 전체 설정 딕셔너리

    Returns:
        {
            "final_score": 0~1,
            "signals": { signal_name: {score, detail, ...} },
            "regime": { regime 결과 },
            "detail": str,
        }
    """
    # 가중치 로드
    weight_cfg = config.get("risk_engine", {}).get("weights", {})
    weights = {
        "macro": weight_cfg.get("macro", 0.20),
        "liquidity": weight_cfg.get("liquidity", 0.20),
        "breadth": weight_cfg.get("breadth", 0.15),
        "volatility": weight_cfg.get("volatility", 0.20),
        "cross_asset": weight_cfg.get("cross_asset", 0.15),
        "regime": weight_cfg.get("regime", 0.10),
    }

    signals = {}

    # 1) Macro Score (기존 Stage1)
    logger.info("Macro Signal 계산 중...")
    macro = calculate_macro_score(close, config)
    signals["macro"] = macro

    # 2) Liquidity Stress
    logger.info("Liquidity Signal 계산 중...")
    liquidity = calculate_liquidity_score(close, config)
    signals["liquidity"] = liquidity

    # 3) Market Breadth
    logger.info("Breadth Signal 계산 중...")
    breadth = calculate_breadth_score(close, config)
    signals["breadth"] = breadth

    # 4) Volatility Regime
    logger.info("Volatility Signal 계산 중...")
    vol = calculate_volatility_score(close, config)
    signals["volatility"] = vol

    # 5) Cross-Asset
    logger.info("Cross-Asset Signal 계산 중...")
    cross = calculate_cross_asset_score(close, config)
    signals["cross_asset"] = cross

    # 6) Regime Detection (HMM)
    logger.info("Regime Detection 계산 중...")
    regime = detect_regime(close, config)
    signals["regime"] = regime

    # ── 가중 평균 계산 ─────────────────────────────────
    weighted_sum = 0.0
    total_weight = 0.0

    for name, weight in weights.items():
        score = signals.get(name, {}).get("score", 0.5)
        if pd.isna(score):
            score = 0.5
        weighted_sum += float(score) * weight
        total_weight += weight

    final_score = weighted_sum / total_weight if total_weight > 0 else 0.5

    # ── 결과 포맷 ──────────────────────────────────────
    signal_summary = {
        name: {
            "score": signals[name].get("score", 0),
            "weight": weights.get(name, 0),
            "detail": signals[name].get("detail", ""),
        }
        for name in weights.keys()
    }

    return {
        "final_score": round(final_score, 4),
        "signals": signals,
        "signal_summary": signal_summary,
        "regime": regime,
        "detail": f"Final Risk Score: {final_score:.2f} | Regime: {regime.get('regime', 'Unknown')}",
    }
