"""
signals/liquidity.py — 유동성 스트레스 지수 (Liquidity Stress Index)

FRED API + yfinance 기반으로 유동성 위기 조기 탐지.
각 지표를 롤링 percentile로 정규화 후 가중 평균 → 0~1 스코어.
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# FRED는 선택적 의존성
try:
    from fredapi import Fred
    FRED_AVAILABLE = True
except ImportError:
    FRED_AVAILABLE = False


def _rolling_percentile(series: pd.Series, window: int = 252) -> pd.Series:
    """롤링 윈도우 내에서의 percentile 위치 (0~1)."""
    def pct_rank(x):
        if len(x) < 2:
            return 0.5
        return (x.values < x.values[-1]).sum() / (len(x) - 1)
    return series.rolling(window=window, min_periods=60).apply(pct_rank, raw=False)


def _fetch_fred_series(fred: object, series_id: str, start: str = None) -> pd.Series:
    """FRED에서 시계열 데이터를 안전하게 가져옵니다."""
    try:
        data = fred.get_series(series_id, observation_start=start)
        return data.dropna()
    except Exception as e:
        print(f"  ⚠️ FRED {series_id}: {e}")
        return pd.Series(dtype=float)


def calculate_liquidity_score(close: pd.DataFrame, config: dict) -> dict:
    """
    유동성 스트레스 지수를 계산합니다.

    사용 지표:
    1. SOFR-FFR Spread (FRED) — 단기자금 시장 스트레스
    2. Commercial Paper Spread (FRED) — 기업 단기 차입 스트레스
    3. HY OAS (FRED) — 고수익채 스프레드
    4. HYG/LQD 비율 변화 (yfinance) — 크레딧 리스크
    5. TLT 실현변동성 (yfinance) — 채권 시장 변동성

    Returns:
        {"score": 0~1, "components": [...], "detail": str}
    """
    fred_cfg = config.get("fred", {})
    api_key = os.environ.get("FRED_API_KEY", fred_cfg.get("api_key", ""))

    components = []
    scores = []
    weights = []

    # ── FRED 기반 지표 ─────────────────────────────────
    fred = None
    if FRED_AVAILABLE and api_key:
        try:
            fred = Fred(api_key=api_key)
            start_date = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")

            # 1) SOFR - EFFR 스프레드
            sofr = _fetch_fred_series(fred, "SOFR", start_date)
            effr = _fetch_fred_series(fred, "EFFR", start_date)
            if not sofr.empty and not effr.empty:
                spread = (sofr - effr).dropna()
                if not spread.empty:
                    pct = _rolling_percentile(spread.abs())
                    val = pct.dropna().iloc[-1] if not pct.dropna().empty else 0.5
                    scores.append(val)
                    weights.append(0.25)
                    components.append({
                        "name": "SOFR-FFR Spread",
                        "value": f"{spread.iloc[-1]:.4f}",
                        "score": val,
                        "source": "FRED",
                    })

            # 2) HY OAS (ICE BofA High Yield)
            hy_oas = _fetch_fred_series(fred, "BAMLH0A0HYM2", start_date)
            if not hy_oas.empty:
                pct = _rolling_percentile(hy_oas)
                val = pct.dropna().iloc[-1] if not pct.dropna().empty else 0.5
                scores.append(val)
                weights.append(0.25)
                components.append({
                    "name": "HY OAS (ICE BofA)",
                    "value": f"{hy_oas.iloc[-1]:.2f}%",
                    "score": val,
                    "source": "FRED",
                })

            # 3) Commercial Paper Spread
            cp = _fetch_fred_series(fred, "DCPF3M", start_date)
            tb = _fetch_fred_series(fred, "DTB3", start_date)
            if not cp.empty and not tb.empty:
                cp_spread = (cp - tb).dropna()
                if not cp_spread.empty:
                    pct = _rolling_percentile(cp_spread)
                    val = pct.dropna().iloc[-1] if not pct.dropna().empty else 0.5
                    scores.append(val)
                    weights.append(0.15)
                    components.append({
                        "name": "CP Spread (3M)",
                        "value": f"{cp_spread.iloc[-1]:.4f}",
                        "score": val,
                        "source": "FRED",
                    })

        except Exception as e:
            print(f"  ⚠️ FRED 연결 실패: {e}")

    # ── yfinance 기반 지표 (항상 가용) ──────────────────
    # 4) HYG/LQD 비율 — 크레딧 스트레스
    if "HYG" in close.columns and "LQD" in close.columns:
        ratio = (close["HYG"] / close["LQD"]).dropna()
        if len(ratio) > 20:
            ratio_ret = ratio.pct_change(20).dropna()
            # 하락할수록 스트레스 → 음수를 양수 스코어로 변환
            pct = _rolling_percentile(-ratio_ret)  # 반전
            val = pct.dropna().iloc[-1] if not pct.dropna().empty else 0.5
            scores.append(val)
            weights.append(0.20)
            components.append({
                "name": "HYG/LQD 크레딧",
                "value": f"{ratio_ret.iloc[-1]:.2%}",
                "score": val,
                "source": "yfinance",
            })

    # 5) TLT 실현 변동성 — 채권 변동성
    if "TLT" in close.columns:
        tlt_vol = close["TLT"].dropna().pct_change().rolling(20).std().dropna()
        if not tlt_vol.empty:
            pct = _rolling_percentile(tlt_vol)
            val = pct.dropna().iloc[-1] if not pct.dropna().empty else 0.5
            scores.append(val)
            weights.append(0.15)
            components.append({
                "name": "TLT 변동성",
                "value": f"{tlt_vol.iloc[-1]:.4f}",
                "score": val,
                "source": "yfinance",
            })

    # ── 최종 스코어 ────────────────────────────────────
    if scores:
        total_weight = sum(weights)
        final_score = sum(s * w for s, w in zip(scores, weights)) / total_weight
    else:
        final_score = 0.5  # 데이터 없으면 중립

    return {
        "score": round(final_score, 4),
        "components": components,
        "detail": f"Liquidity Stress: {final_score:.2f} ({len(components)} indicators)",
    }
