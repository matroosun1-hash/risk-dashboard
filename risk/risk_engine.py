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
from signals.global_macro import calculate_global_macro_score
from regime.regime_model import detect_regime


# Regime별 가중치 승수 테이블
# 각 숫자는 기본 가중치에 곱해지는 배율 (정규화 후 합산)
_REGIME_MULTIPLIERS = {
    "Expansion": {
        "macro": 0.8,
        "liquidity": 0.5,   # 평시 과민반응 억제
        "breadth": 0.8,
        "volatility": 0.6,
        "cross_asset": 1.0,
        "regime": 1.0,
        "global_macro": 1.0,
    },
    "Inflation": {
        "macro": 1.2,
        "liquidity": 0.8,
        "breadth": 1.0,
        "volatility": 1.0,
        "cross_asset": 1.2,
        "regime": 1.0,
        "global_macro": 1.2,
    },
    "Correction": {
        "macro": 1.0,
        "liquidity": 1.3,
        "breadth": 1.2,
        "volatility": 1.2,
        "cross_asset": 1.0,
        "regime": 1.0,
        "global_macro": 1.0,
    },
    "Liquidity Crisis": {
        "macro": 1.0,
        "liquidity": 2.0,   # 쓰나미 조기 감지 최우선 증폭
        "breadth": 1.3,
        "volatility": 1.5,
        "cross_asset": 1.3,
        "regime": 1.0,
        "global_macro": 1.0,
    },
}


def _apply_dynamic_weights(base_weights: dict, regime: str) -> dict:
    """
    HMM 판별 regime에 따라 기본 가중치를 동적으로 조정합니다.
    승수를 곱한 뒤 합이 1.0이 되도록 정규화합니다.
    regime이 Unknown이거나 테이블에 없으면 기본 가중치를 그대로 반환합니다.
    """
    multipliers = _REGIME_MULTIPLIERS.get(regime)
    if multipliers is None:
        return base_weights

    adjusted = {k: base_weights[k] * multipliers.get(k, 1.0) for k in base_weights}
    total = sum(adjusted.values())
    return {k: v / total for k, v in adjusted.items()} if total > 0 else base_weights


def calculate_final_risk(close: pd.DataFrame, config: dict, dynamic_weights: bool = True) -> dict:
    """
    모든 신호를 수집하고 가중 평균으로 최종 리스크 스코어를 계산합니다.
    HMM regime에 따라 각 신호의 가중치를 동적으로 조정합니다.

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
    # 기본 가중치 로드
    weight_cfg = config.get("risk_engine", {}).get("weights", {})
    base_weights = {
        "macro": weight_cfg.get("macro", 0.18),
        "liquidity": weight_cfg.get("liquidity", 0.17),
        "breadth": weight_cfg.get("breadth", 0.15),
        "volatility": weight_cfg.get("volatility", 0.18),
        "cross_asset": weight_cfg.get("cross_asset", 0.12),
        "regime": weight_cfg.get("regime", 0.10),
        "global_macro": weight_cfg.get("global_macro", 0.10),
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

    # 6) Regime Detection (HMM) — 동적 가중치 산정에 먼저 사용
    logger.info("Regime Detection 계산 중...")
    regime = detect_regime(close, config)
    signals["regime"] = regime

    # 7) Global Macro
    logger.info("Global Macro Signal 계산 중...")
    global_macro = calculate_global_macro_score(close, config)
    signals["global_macro"] = global_macro

    # ── 동적 가중치 적용 ───────────────────────────────
    current_regime = regime.get("regime", "Unknown")
    if dynamic_weights:
        # Liquidity Crisis 코로보레이션 필터:
        # HMM이 Crisis로 판별해도 liquidity + volatility 평균이 0.5 미만이면
        # 실제 신호 근거가 부족하므로 Correction으로 강등
        if current_regime == "Liquidity Crisis":
            liq_score = float(signals.get("liquidity", {}).get("score", 0) or 0)
            vol_score = float(signals.get("volatility", {}).get("score", 0) or 0)
            if (liq_score + vol_score) / 2 < 0.5:
                logger.info(
                    f"Crisis corroboration failed "
                    f"(liq={liq_score:.2f}, vol={vol_score:.2f}) → downgraded to Correction"
                )
                current_regime = "Correction"
                # regime 신호 점수도 corroborating signals 평균으로 눌러줌
                signals["regime"] = {
                    **signals["regime"],
                    "score": round((liq_score + vol_score) / 2, 4),
                    "detail": signals["regime"].get("detail", "") + " [corroboration cap]",
                }
        weights = _apply_dynamic_weights(base_weights, current_regime)
        logger.info(f"Dynamic weights applied for regime '{current_regime}'")
    else:
        total = sum(base_weights.values())
        weights = {k: v / total for k, v in base_weights.items()}
        logger.info("Static weights (dynamic disabled)")

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
            "weight": round(weights.get(name, 0), 4),
            "detail": signals[name].get("detail", ""),
        }
        for name in weights.keys()
    }

    return {
        "final_score": round(final_score, 4),
        "signals": signals,
        "signal_summary": signal_summary,
        "regime": regime,
        "detail": f"Final Risk Score: {final_score:.2f} | Regime: {current_regime} | Dynamic weights active",
    }
