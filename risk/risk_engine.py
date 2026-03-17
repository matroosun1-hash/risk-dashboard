"""
risk/risk_engine.py — Multi-Signal Risk Aggregation Engine

모든 신호를 통합하여 최종 Risk Score(0~1)를 계산합니다.
가중 앙상블(Weighted Ensemble) 방식을 사용합니다.

개선: 개별 신호 에러 격리 — 하위 모듈 실패 시에도 나머지 신호로 계속 작동.
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

# 신호 함수 매핑 (에러 격리를 위한 일괄 처리용)
_SIGNAL_FUNCS = {
    "macro": calculate_macro_score,
    "liquidity": calculate_liquidity_score,
    "breadth": calculate_breadth_score,
    "volatility": calculate_volatility_score,
    "cross_asset": calculate_cross_asset_score,
    "regime": detect_regime,
    "global_macro": calculate_global_macro_score,
}

# 신호 실행 순서 (regime을 먼저 계산해야 동적 가중치 적용 가능)
_SIGNAL_ORDER = ["macro", "liquidity", "breadth", "volatility", "cross_asset", "regime", "global_macro"]


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


def _safe_call_signal(name: str, close: pd.DataFrame, config: dict) -> tuple[dict, bool]:
    """
    신호 함수를 에러 격리하여 호출합니다.
    실패 시 중립값(0.5)을 반환하고 에러 플래그를 설정합니다.

    Returns: (result_dict, has_error)
    """
    func = _SIGNAL_FUNCS.get(name)
    if func is None:
        return {"score": 0.5, "detail": f"Unknown signal: {name}", "components": []}, True

    try:
        result = func(close, config)
        return result, False
    except Exception as e:
        logger.warning(f"Signal '{name}' failed: {e}")
        return {"score": 0.5, "detail": f"ERROR: {e}", "components": []}, True


def calculate_final_risk(close: pd.DataFrame, config: dict, dynamic_weights: bool = True) -> dict:
    """
    모든 신호를 수집하고 가중 평균으로 최종 리스크 스코어를 계산합니다.
    HMM regime에 따라 각 신호의 가중치를 동적으로 조정합니다.

    개별 신호 실패 시 에러 격리: 중립값(0.5) 대체 + 가중치 0.5배 패널티.

    Returns:
        {
            "final_score": 0~1,
            "signals": { signal_name: {score, detail, ...} },
            "regime": { regime 결과 },
            "errors": [실패한 신호 이름],
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
    error_signals = set()

    # ── 신호 수집 (에러 격리) ─────────────────────────
    for name in _SIGNAL_ORDER:
        logger.info(f"{name} Signal 계산 중...")
        result, has_error = _safe_call_signal(name, close, config)
        signals[name] = result
        if has_error:
            error_signals.add(name)

    regime = signals.get("regime", {"regime": "Unknown", "probabilities": {}, "score": 0.5})

    # ── 동적 가중치 적용 ───────────────────────────────
    current_regime = regime.get("regime", "Unknown")
    if dynamic_weights:
        # Liquidity Crisis 코로보레이션 필터
        if current_regime == "Liquidity Crisis":
            liq_score = float(signals.get("liquidity", {}).get("score", 0) or 0)
            vol_score = float(signals.get("volatility", {}).get("score", 0) or 0)
            if (liq_score + vol_score) / 2 < 0.5:
                logger.info(
                    f"Crisis corroboration failed "
                    f"(liq={liq_score:.2f}, vol={vol_score:.2f}) → downgraded to Correction"
                )
                current_regime = "Correction"
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

    # ── 에러 신호 가중치 패널티 ────────────────────────
    if error_signals:
        for name in error_signals:
            if name in weights:
                weights[name] *= 0.5  # 불확실성 패널티
        # 재정규화
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

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
        "errors": list(error_signals),
        "detail": f"Final Risk Score: {final_score:.2f} | Regime: {current_regime} | Dynamic weights active",
    }
