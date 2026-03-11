"""
1단계: 하락장 조기탐지 — 종합 점수화 및 Level 판정
"""


def calculate_total_score(indicator_results: list[dict]) -> float:
    """
    모든 지표의 점수를 합산합니다.

    Args:
        indicator_results: indicators.run_all_indicators()의 반환값

    Returns:
        총 점수 (0~10)
    """
    return sum(r["score"] for r in indicator_results)


def determine_level(total_score: float, config: dict) -> dict:
    """
    총 점수를 기반으로 위험 Level을 판정합니다.

    Args:
        total_score: 합산 점수
        config: stage1.levels 설정

    Returns:
        Level 정보 딕셔너리
    """
    levels_cfg = config.get("levels", {})
    l1 = levels_cfg.get("level_1_min", 3)
    l2 = levels_cfg.get("level_2_min", 5)
    l3 = levels_cfg.get("level_3_min", 7)
    l4 = levels_cfg.get("level_4_min", 9)

    if total_score >= l4:
        level = 4
        label = "극도위험"
        emoji = "🔴🔴"
        action = "미국 전량 매도 권고"
        color = "red"
    elif total_score >= l3:
        level = 3
        label = "위험"
        emoji = "🔴"
        action = "비중 축소 권고"
        color = "orangered"
    elif total_score >= l2:
        level = 2
        label = "경고"
        emoji = "🟠"
        action = "신규 매수 자제"
        color = "orange"
    elif total_score >= l1:
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
        "total_score": total_score,
        "max_score": 10,
    }


def format_stage1_report(indicator_results: list[dict], level_info: dict) -> str:
    """
    1단계 분석 결과를 보기 좋은 텍스트로 포맷합니다.
    """
    lines = []
    lines.append("=" * 60)
    lines.append("  📊 1단계: 하락장 조기탐지 결과")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"  종합 Level: {level_info['emoji']} Level {level_info['level']} ({level_info['label']})")
    lines.append(f"  총 점수: {level_info['total_score']:.1f} / {level_info['max_score']}")
    lines.append(f"  권고: {level_info['action']}")
    lines.append("")
    lines.append("-" * 60)
    lines.append(f"  {'#':<4} {'지표':<25} {'점수':>6}  {'상세'}")
    lines.append("-" * 60)

    for i, r in enumerate(indicator_results, 1):
        score_icon = "🔴" if r["score"] >= 1 else "🟡" if r["score"] > 0 else "🟢"
        lines.append(f"  {i:<4} {r['name']:<25} {score_icon} {r['score']:>4.1f}  {r['detail']}")

    lines.append("-" * 60)
    lines.append("")
    return "\n".join(lines)
