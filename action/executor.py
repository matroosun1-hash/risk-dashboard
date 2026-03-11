"""
자동 대응 — 종합 대응 권고 생성

1단계 + 2단계 Level에 따라 최종 권고를 생성합니다.
"""

from action.prioritizer import prioritize_sell, format_priority_report
from action.defender import generate_defense_allocation, format_defense_report


def generate_response(
    stage1_level: dict,
    stage2_level: dict,
    holdings: list[dict],
    close,
    action_config: dict,
) -> dict:
    """
    종합 대응 권고를 생성합니다.

    Args:
        stage1_level: stage1 Level 정보
        stage2_level: stage2 Level 정보
        holdings: 보유 종목 리스트
        close: 종가 DataFrame
        action_config: action 설정

    Returns:
        종합 대응 딕셔너리
    """
    s1_level = stage1_level["level"]
    s2_level = stage2_level["level"]

    # 최고 위험 레벨 결정
    max_level = max(s1_level, s2_level)

    response = {
        "stage1_level": s1_level,
        "stage2_level": s2_level,
        "max_level": max_level,
        "actions": [],
        "sell_list": [],
        "defense_allocation": None,
        "block_new_buys": False,
    }

    # Level별 대응
    if s1_level >= 4:
        # 1단계 Level 4: 전량 매도 권고
        response["actions"].append("🚨 [1단계 Level 4] 전량 매도 권고")
        response["sell_list"] = prioritize_sell(
            holdings, close, action_config.get("stop_loss_pct", -0.10), target_category=None
        )
        response["block_new_buys"] = True

    if s2_level >= 3:
        # 2단계 Level 3/4: 성장주 매도 + 방어 전환
        response["actions"].append(f"🚨 [2단계 Level {s2_level}] 성장주 전량 매도 + 방어 ETF 전환")

        if not response["sell_list"]:  # 1단계에서 이미 전량 매도가 아닌 경우
            response["sell_list"] = prioritize_sell(
                holdings, close, action_config.get("stop_loss_pct", -0.10), target_category="growth"
            )

        # 매도 예상 총액 계산
        sell_total = sum(
            (m.get("current_price", 0) or 0) * (m.get("shares", 0) or 0)
            for m in response["sell_list"]
        )

        if sell_total > 0:
            response["defense_allocation"] = generate_defense_allocation(
                sell_total, action_config
            )

        response["block_new_buys"] = True

    elif s2_level == 2:
        response["actions"].append("⚠️ [2단계 Level 2] 성장주 비중 축소 권고")
        # 성장주 중 가장 위험한 것만 매도 권고
        response["sell_list"] = prioritize_sell(
            holdings, close, action_config.get("stop_loss_pct", -0.10), target_category="growth"
        )

    elif s2_level == 1:
        response["actions"].append("🟡 [2단계 Level 1] 모니터링 강화")

    if max_level == 0:
        response["actions"].append("🟢 정상: 기존 전략 유지")

    return response


def format_response_report(response: dict) -> str:
    """종합 대응 권고를 보기 좋은 텍스트로 포맷합니다."""
    lines = []
    lines.append("=" * 60)
    lines.append("  🎯 종합 대응 권고")
    lines.append("=" * 60)
    lines.append("")

    # 종합 Level 표시
    max_level = response["max_level"]
    level_colors = {0: "🟢", 1: "🟡", 2: "🟠", 3: "🔴", 4: "🔴🔴"}
    lines.append(f"  최고 위험 Level: {level_colors.get(max_level, '')} Level {max_level}")
    lines.append(f"  (1단계: Level {response['stage1_level']}, 2단계: Level {response['stage2_level']})")
    lines.append("")

    # 대응 사항
    for action in response["actions"]:
        lines.append(f"  {action}")
    lines.append("")

    # 매도 우선순위
    if response["sell_list"]:
        lines.append(format_priority_report(response["sell_list"]))

    # 방어 ETF 배분
    if response["defense_allocation"]:
        lines.append(format_defense_report(response["defense_allocation"]))

    # 신규 매수 차단
    if response["block_new_buys"]:
        lines.append("  🚫 성장주 신규 매수 차단 중")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)
