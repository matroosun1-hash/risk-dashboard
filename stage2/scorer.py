"""
2단계: 섹터 로테이션 탐지 — 종합 Level 판정

로테이션 쌍 결과 + 선행지표 결과를 종합하여 Level 0~4 판정.
"""

from stage2.rotation import get_rotation_summary
from stage2.leading import get_leading_summary


def determine_rotation_level(
    rotation_results: list[dict],
    leading_results: list[dict],
    config: dict,
) -> dict:
    """
    로테이션 종합 Level을 판정합니다.

    판정 기준:
    - Level 0: 쌍 0~1개 음수
    - Level 1: 쌍 2개 음수
    - Level 2: 쌍 3개 음수
    - Level 3: 쌍 4개 음수 + 선행 1개 이상 확인
    - Level 4: 쌍 4개 음수 + 선행 3개 모두 확인 + 임계값 초과

    Args:
        rotation_results: rotation.calculate_all_rotations() 반환값
        leading_results: leading.check_all_leading() 반환값
        config: stage2 설정

    Returns:
        Level 정보 딕셔너리
    """
    rot_summary = get_rotation_summary(rotation_results)
    lead_summary = get_leading_summary(leading_results)

    neg_count = rot_summary["negative_count"]
    strong_count = rot_summary["strong_count"]
    lead_signals = lead_summary["signal_count"]
    all_confirmed = lead_summary["all_confirmed"]

    # Level 판정
    if neg_count >= 4 and all_confirmed and strong_count >= 3:
        level = 4
        label = "극도위험"
        emoji = "🔴🔴"
        action = "성장주 전량 매도 + 방어 ETF 전환 + 신규 매수 차단"
        color = "red"
    elif neg_count >= 4 and lead_signals >= 1:
        level = 3
        label = "위험"
        emoji = "🔴"
        action = "성장주 전량 매도 + 방어 ETF 50% 전환 + 신규 매수 차단"
        color = "orangered"
    elif neg_count >= 3:
        level = 2
        label = "경고"
        emoji = "🟠"
        action = "성장주 비중 축소 권고"
        color = "orange"
    elif neg_count >= 2:
        level = 1
        label = "주의"
        emoji = "🟡"
        action = "모니터링 강화"
        color = "gold"
    else:
        level = 0
        label = "정상"
        emoji = "🟢"
        action = "정상 운영"
        color = "green"

    return {
        "level": level,
        "label": label,
        "emoji": emoji,
        "action": action,
        "color": color,
        "negative_pairs": neg_count,
        "strong_pairs": strong_count,
        "leading_signals": lead_signals,
        "leading_all_confirmed": all_confirmed,
    }


def format_stage2_report(
    rotation_results: list[dict],
    leading_results: list[dict],
    level_info: dict,
) -> str:
    """
    2단계 분석 결과를 보기 좋은 텍스트로 포맷합니다.
    """
    lines = []
    lines.append("=" * 60)
    lines.append("  🔄 2단계: 섹터 로테이션 탐지 결과")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"  종합 Level: {level_info['emoji']} Level {level_info['level']} ({level_info['label']})")
    lines.append(f"  음수 쌍: {level_info['negative_pairs']}/4, 선행 신호: {level_info['leading_signals']}/3")
    lines.append(f"  권고: {level_info['action']}")
    lines.append("")

    # 로테이션 쌍 상세
    lines.append("  ── 로테이션 쌍 (20일 기준) ──")
    for r in rotation_results:
        icon = "🔴" if r.get("strong_signal") else "🟡" if r.get("signal") else "🟢"
        change_str = f"{r['change']:+.2%}" if r["change"] is not None else "N/A"
        lines.append(f"    {icon} {r['label']:<12} ({r['pair']}): {change_str}")

    lines.append("")

    # 선행지표 상세
    lines.append("  ── 선행지표 (7일 기준) ──")
    for r in leading_results:
        lines.append(f"    {r['detail']:<50} [{r['label']}]")

    lines.append("-" * 60)
    lines.append("")
    return "\n".join(lines)
