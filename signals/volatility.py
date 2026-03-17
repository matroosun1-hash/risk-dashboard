"""
signals/volatility.py — 변동성 체제(Volatility Regime) 모델

VIX, VVIX 프록시, VIX Term Structure, 실현 변동성을 종합하여
변동성 체제를 분류합니다: Low / Normal / Expansion / Crisis
"""

import pandas as pd
import numpy as np


def _classify_regime(score: float, percentiles: dict) -> str:
    """percentile 기반으로 변동성 체제를 분류합니다."""
    if score >= percentiles.get("crisis", 95) / 100:
        return "Crisis"
    elif score >= percentiles.get("expansion", 80) / 100:
        return "Expansion"
    elif score >= percentiles.get("normal", 50) / 100:
        return "Normal"
    else:
        return "Low"


def calculate_volatility_score(close: pd.DataFrame, config: dict) -> dict:
    """
    변동성 체제를 분석합니다.

    사용 지표:
    1. VIX 수준 (절대값 + percentile)
    2. VVIX 프록시 (VIX 20일 변동성)
    3. VIX Term Structure (^VIX / ^VIX3M)
    4. SPY 실현 변동성 (20일)

    Returns:
        {
            "score": 0~1,
            "regime": "Low" | "Normal" | "Expansion" | "Crisis",
            "components": [...],
            "detail": str,
        }
    """
    vol_cfg = config.get("volatility_regime", {})
    percentile_cfg = vol_cfg.get("percentiles", {"low": 20, "normal": 50, "expansion": 80, "crisis": 95})

    components = []
    scores = []
    weights = []

    # 1) VIX 수준 — percentile 기반 스코어
    if "^VIX" in close.columns:
        vix = close["^VIX"].dropna()
        if len(vix) > 60:
            current_vix = vix.iloc[-1]
            # 롤링 percentile (252일)
            rank = (vix.iloc[:-1] < current_vix).sum() / len(vix.iloc[:-1])
            vix_score = float(rank)
            scores.append(vix_score)
            weights.append(0.35)
            components.append({
                "name": "VIX 수준",
                "value": f"{current_vix:.1f} (pct: {vix_score:.0%})",
                "score": vix_score,
            })

    # 2) VVIX 프록시 — VIX의 20일 변동성 (VIX가 얼마나 급변하는가)
    if "^VIX" in close.columns:
        vix = close["^VIX"].dropna()
        if len(vix) > 20:
            vvix_proxy = vix.pct_change().rolling(20).std().dropna()
            if not vvix_proxy.empty:
                current = vvix_proxy.iloc[-1]
                rank = (vvix_proxy.iloc[:-1] < current).sum() / max(len(vvix_proxy) - 1, 1)
                vvix_score = float(rank)
                scores.append(vvix_score)
                weights.append(0.20)
                components.append({
                    "name": "VVIX 프록시 (VIX 변동성)",
                    "value": f"{current:.4f} (pct: {vvix_score:.0%})",
                    "score": vvix_score,
                })

    # 3) VIX Term Structure — VIX / VIX3M (또는 VXV)
    #    > 1 = backwardation (단기 공포 > 장기) = 위험
    #    < 1 = contango (정상)
    if "^VIX" in close.columns and "^VIX3M" in close.columns:
        vix_spot = close["^VIX"].dropna()
        vix_3m = close["^VIX3M"].dropna()
        common = vix_spot.index.intersection(vix_3m.index)
        if len(common) > 20:
            term_ratio = vix_spot.loc[common] / vix_3m.loc[common]
            term_ratio = term_ratio.dropna()
            current_ratio = term_ratio.iloc[-1]
            # ratio > 1 = backwardation → 위험. 0.8~1.2 범위를 0~1로 매핑
            ts_score = float(np.clip((current_ratio - 0.8) / 0.4, 0, 1))
            scores.append(ts_score)
            weights.append(0.20)
            components.append({
                "name": "VIX Term Structure",
                "value": f"{current_ratio:.3f} ({'Backwardation' if current_ratio > 1 else 'Contango'})",
                "score": ts_score,
            })

    # 4) 금리 실현 변동성 (^TNX 20일 연율화)
    #    SPY 실현변동성 대신 금리 변동성 사용 (SPY 과의존 해소)
    #    금리 변동성은 주식과 독립적인 리스크 차원
    if "^TNX" in close.columns:
        tnx_ret = close["^TNX"].dropna().pct_change().dropna()
        if len(tnx_ret) > 20:
            rv = tnx_ret.rolling(20).std() * np.sqrt(252)  # 연율화
            rv = rv.dropna()
            if not rv.empty:
                current_rv = rv.iloc[-1]
                rank = (rv.iloc[:-1] < current_rv).sum() / max(len(rv) - 1, 1)
                rv_score = float(rank)
                scores.append(rv_score)
                weights.append(0.25)
                components.append({
                    "name": "금리 실현변동성 (^TNX 20d)",
                    "value": f"{current_rv:.1%} (pct: {rv_score:.0%})",
                    "score": rv_score,
                })

    # ── 최종 스코어 ────────────────────────────────────
    if scores:
        total_w = sum(weights)
        final_score = sum(s * w for s, w in zip(scores, weights)) / total_w
    else:
        final_score = 0.5

    regime = _classify_regime(final_score, percentile_cfg)

    return {
        "score": round(final_score, 4),
        "regime": regime,
        "components": components,
        "detail": f"Vol Regime: {regime} (score={final_score:.2f})",
    }
