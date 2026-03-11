"""
portfolio/allocator.py — 포트폴리오 배분 및 실행 권고 (V2)

Risk Score와 Position Sizing 결과를 종합하여
구체적인 매매 행동 권고를 생성합니다.
"""

import pandas as pd


def generate_portfolio_action(risk_result: dict, sizing_result: dict, config: dict) -> dict:
    """
    최종 포트폴리오 행동 권고를 생성합니다.

    Args:
        risk_result: risk_engine.calculate_final_risk() 결과
        sizing_result: position_sizing.calculate_position_sizing() 결과
        config: 전체 설정

    Returns:
        {
            "final_score": float,
            "regime": str,
            "allocation": dict,
            "actions": list[str],
            "risk_level": str,
            "detail": str,
        }
    """
    final_score = risk_result["final_score"]
    regime = risk_result.get("regime", {}).get("regime", "Unknown")
    allocation = sizing_result["allocation"]

    # 리스크 레벨 판정
    if final_score >= 0.8:
        risk_level = "극도위험"
        risk_icon = "🔴🔴"
    elif final_score >= 0.6:
        risk_level = "위험"
        risk_icon = "🔴"
    elif final_score >= 0.4:
        risk_level = "경고"
        risk_icon = "🟠"
    elif final_score >= 0.2:
        risk_level = "주의"
        risk_icon = "🟡"
    else:
        risk_level = "정상"
        risk_icon = "🟢"

    # 행동 권고 생성
    actions = []

    if final_score >= 0.8:
        actions.append("⚠️ 주식 포지션 전량 정리 권고")
        actions.append("현금 및 단기채권 위주로 전환")
        actions.append("🚫 모든 신규 매수 차단")
    elif final_score >= 0.6:
        actions.append("성장주 포지션 대폭 축소 (70% 이상)")
        actions.append("방어 ETF 비중 확대 (TLT, GLD, SHY)")
        actions.append("🚫 성장주 신규 매수 차단")
    elif final_score >= 0.4:
        actions.append("성장주 비중 축소 고려 (30~50%)")
        actions.append("방어 자산 일부 편입")
        actions.append("손절선 타이트하게 조정")
    elif final_score >= 0.2:
        actions.append("모니터링 빈도 강화")
        actions.append("신규 매수 시 포지션 크기 축소")
    else:
        actions.append("정상 운영. 기존 전략 유지")

    # Regime 특화 권고
    if regime == "Liquidity Crisis":
        actions.append("⚡ 유동성 위기 감지 — 현금 비중 최대화")
    elif regime == "Inflation":
        actions.append("📈 인플레이션 체제 — 원자재/TIPS 고려")
    elif regime == "Correction":
        actions.append("📉 조정 체제 — 방어적 포지셔닝 유지")

    # Volatility targeting 메모
    if sizing_result.get("vol_adjusted"):
        current_vol = sizing_result.get("current_vol", 0)
        target_vol = sizing_result.get("target_vol", 0.12)
        actions.append(
            f"📊 Vol Target 조정: 현재 {current_vol:.1%} > 목표 {target_vol:.0%}"
        )

    return {
        "final_score": final_score,
        "regime": regime,
        "risk_level": risk_level,
        "risk_icon": risk_icon,
        "allocation": allocation,
        "base_allocation": sizing_result.get("base_allocation", allocation),
        "actions": actions,
        "signals": risk_result.get("signal_summary", {}),
        "detail": f"{risk_icon} Risk: {final_score:.2f} | {risk_level} | Regime: {regime}",
    }
