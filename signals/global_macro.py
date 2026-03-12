"""
signals/global_macro.py — 글로벌 거시 리스크 신호

미국 단일 의존 문제 보완. 글로벌 위험선호/회피 흐름을 감지합니다.

사용 지표:
1. EEM/SPY 상대 수익률 — 신흥국 vs 미국 (글로벌 위험선호 지표)
2. VEU/SPY 상대 수익률 — 미국 제외 전세계 vs 미국 (글로벌 주식 브레드스)
3. CPER/GLD 비율 추세  — 구리/금 비율 (글로벌 경기 선행지표)

해석:
- 신흥국·글로벌 주식이 미국 대비 약세 → 글로벌 위험회피 신호
- 구리/금 비율 하락 → 경기 둔화 선행 신호 (구리는 산업, 금은 안전자산)
"""

import pandas as pd
import numpy as np


def _rolling_percentile_inv(series: pd.Series, window: int = 252) -> pd.Series:
    """
    롤링 percentile (반전): 값이 낮을수록 높은 리스크 스코어.
    수익률이 낮을수록(나쁠수록) 위험 신호가 강해지도록 반전.
    """
    def inv_rank(x):
        if len(x) < 2:
            return 0.5
        return 1.0 - (x.values < x.values[-1]).sum() / (len(x) - 1)
    return series.rolling(window=window, min_periods=60).apply(inv_rank, raw=False)


def _relative_return(close: pd.DataFrame, ticker_a: str, ticker_b: str, period: int = 20) -> pd.Series | None:
    """ticker_a의 ticker_b 대비 상대 수익률 시계열."""
    if ticker_a not in close.columns or ticker_b not in close.columns:
        return None
    a = close[ticker_a].dropna()
    b = close[ticker_b].dropna()
    common = a.index.intersection(b.index)
    if len(common) < period + 60:
        return None
    ratio = a.loc[common] / b.loc[common]
    return ratio.pct_change(period)


def calculate_global_macro_score(close: pd.DataFrame, config: dict = None) -> dict:
    """
    글로벌 거시 리스크 스코어를 계산합니다.

    Returns:
        {"score": 0~1, "components": [...], "detail": str}
    """
    components = []
    scores = []
    weights = []

    # 1) EEM/SPY 상대 수익률 — 신흥국 약세 = 글로벌 위험회피
    rel_eem = _relative_return(close, "EEM", "SPY", period=20)
    if rel_eem is not None:
        pct = _rolling_percentile_inv(rel_eem)
        val = float(pct.dropna().iloc[-1]) if not pct.dropna().empty else 0.5
        current_val = float(rel_eem.dropna().iloc[-1]) if not rel_eem.dropna().empty else 0.0
        scores.append(val)
        weights.append(0.35)
        components.append({
            "name": "신흥국 상대강도 (EEM/SPY)",
            "value": f"{current_val:+.2%}",
            "score": round(val, 3),
            "note": "음수 = 신흥국 약세 = 글로벌 위험회피",
        })

    # 2) VEU/SPY 상대 수익률 — 글로벌 주식 약세
    rel_veu = _relative_return(close, "VEU", "SPY", period=20)
    if rel_veu is not None:
        pct = _rolling_percentile_inv(rel_veu)
        val = float(pct.dropna().iloc[-1]) if not pct.dropna().empty else 0.5
        current_val = float(rel_veu.dropna().iloc[-1]) if not rel_veu.dropna().empty else 0.0
        scores.append(val)
        weights.append(0.30)
        components.append({
            "name": "글로벌 주식 상대강도 (VEU/SPY)",
            "value": f"{current_val:+.2%}",
            "score": round(val, 3),
            "note": "음수 = 글로벌 주식 약세",
        })

    # 3) CPER/GLD 비율 추세 — 구리/금 비율 (경기 선행지표)
    if "CPER" in close.columns and "GLD" in close.columns:
        copper_gold = (close["CPER"] / close["GLD"]).dropna()
        if len(copper_gold) > 80:
            cg_ret = copper_gold.pct_change(20)
            pct = _rolling_percentile_inv(cg_ret)
            val = float(pct.dropna().iloc[-1]) if not pct.dropna().empty else 0.5
            current_val = float(cg_ret.dropna().iloc[-1]) if not cg_ret.dropna().empty else 0.0
            scores.append(val)
            weights.append(0.35)
            components.append({
                "name": "구리/금 비율 (CPER/GLD)",
                "value": f"{current_val:+.2%}",
                "score": round(val, 3),
                "note": "하락 = 경기 둔화 선행 신호",
            })

    # ── 최종 스코어 ─────────────────────────────────────
    if scores:
        total_w = sum(weights)
        final_score = sum(s * w for s, w in zip(scores, weights)) / total_w
    else:
        final_score = 0.5  # 데이터 없으면 중립

    return {
        "score": round(final_score, 4),
        "components": components,
        "detail": f"Global Macro: {final_score:.2f} ({len(components)} indicators)",
    }
