"""
자동 대응 — 매도 우선순위 결정

보유 종목의 매도 순서를 결정합니다:
1순위: 손절 도달 종목 (매입가 대비 -10% 이하)
2순위: Sharpe Ratio 낮은 순
3순위: 수익률 낮은 순
"""

import pandas as pd
import numpy as np


def calculate_holding_metrics(
    holding: dict,
    close: pd.DataFrame,
    period: int = 60,
) -> dict:
    """
    보유 종목의 성과 지표를 계산합니다.

    Args:
        holding: {"ticker": str, "shares": int, "avg_price": float, "category": str}
        close: 종가 DataFrame
        period: Sharpe Ratio 계산 기간

    Returns:
        지표 딕셔너리
    """
    ticker = holding["ticker"]
    avg_price = holding.get("avg_price", 0)
    shares = holding.get("shares", 0)
    category = holding.get("category", "unknown")

    if ticker not in close.columns:
        return {
            **holding,
            "current_price": None,
            "pnl_pct": None,
            "pnl_value": None,
            "sharpe": None,
            "available": False,
        }

    current_price = close[ticker].dropna().iloc[-1]
    pnl_pct = (current_price / avg_price - 1) if avg_price > 0 else 0
    pnl_value = (current_price - avg_price) * shares

    # Sharpe Ratio 계산 (무위험수익률 = 0 가정, 일봉 기준)
    returns = close[ticker].pct_change().dropna().tail(period)
    if len(returns) > 10:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0
    else:
        sharpe = 0

    return {
        **holding,
        "current_price": current_price,
        "pnl_pct": pnl_pct,
        "pnl_value": pnl_value,
        "sharpe": sharpe,
        "available": True,
    }


def prioritize_sell(
    holdings: list[dict],
    close: pd.DataFrame,
    stop_loss_pct: float = -0.10,
    target_category: str | None = "growth",
) -> list[dict]:
    """
    매도 우선순위를 결정합니다.

    우선순위:
    1. 손절 도달 종목 (pnl_pct <= stop_loss_pct)
    2. Sharpe Ratio 낮은 순
    3. 수익률 낮은 순

    Args:
        holdings: 보유 종목 리스트
        close: 종가 DataFrame
        stop_loss_pct: 손절 기준 (기본 -10%)
        target_category: 매도 대상 카테고리 (None이면 전체)

    Returns:
        우선순위로 정렬된 종목 리스트 (매도 추천 순)
    """
    # 지표 계산
    metrics = [calculate_holding_metrics(h, close) for h in holdings]
    metrics = [m for m in metrics if m["available"]]

    # 카테고리 필터
    if target_category:
        metrics = [m for m in metrics if m.get("category") == target_category]

    if not metrics:
        return []

    # 우선순위 분류
    stop_loss_hits = []
    others = []

    for m in metrics:
        if m["pnl_pct"] is not None and m["pnl_pct"] <= stop_loss_pct:
            m["sell_reason"] = f"🛑 손절 도달 ({m['pnl_pct']:.1%})"
            m["priority"] = 1
            stop_loss_hits.append(m)
        else:
            others.append(m)

    # 손절 종목은 PnL 낮은 순
    stop_loss_hits.sort(key=lambda x: x["pnl_pct"] or 0)

    # 나머지: Sharpe 낮은 순 → 수익률 낮은 순
    others.sort(key=lambda x: (x["sharpe"] or 0, x["pnl_pct"] or 0))
    for m in others:
        m["sell_reason"] = f"📉 Sharpe: {m['sharpe']:.2f}, PnL: {m['pnl_pct']:.1%}" if m['sharpe'] is not None else "정보 부족"
        m["priority"] = 2

    return stop_loss_hits + others


def format_priority_report(prioritized: list[dict]) -> str:
    """매도 우선순위를 보기 좋은 텍스트로 포맷합니다."""
    if not prioritized:
        return "  매도 대상 종목이 없습니다.\n"

    lines = []
    lines.append("  ── 매도 우선순위 ──")
    for i, m in enumerate(prioritized, 1):
        lines.append(
            f"    {i}. {m['ticker']:<8} "
            f"| 현재가: ${m['current_price']:.2f} "
            f"| PnL: {m['pnl_pct']:+.1%} "
            f"| {m['sell_reason']}"
        )
    lines.append("")
    return "\n".join(lines)
