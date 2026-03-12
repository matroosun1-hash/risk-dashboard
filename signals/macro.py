"""
signals/macro.py — 기존 Stage1 지표를 0~1 스코어로 변환

기존 10개 지표 점수(0~10)를 0~1 범위로 정규화합니다.
"""

import pandas as pd
import numpy as np
from stage1.indicators import run_all_indicators
from stage1.scorer import calculate_total_score


def calculate_macro_score(close: pd.DataFrame, config: dict) -> dict:
    """
    기존 Stage1 10개 지표를 실행하고 0~1 스코어로 변환합니다.

    VIX 지표는 signals/volatility.py에서 전담하므로 macro에서 제외합니다.
    (중복 반영으로 인한 공포 신호 과잉 증폭 방지)

    Returns:
        {
            "score": 0~1 float,
            "total_points": 원점수 (0~9),
            "indicators": 각 지표 결과 리스트 (VIX 제외),
        }
    """
    stage1_cfg = config.get("stage1", {})
    all_indicators = run_all_indicators(close, stage1_cfg)

    # VIX 지표 제외 (volatility 모듈 전담)
    indicators = [ind for ind in all_indicators if "VIX" not in ind["name"]]

    total_points = sum(ind["score"] for ind in indicators)
    max_points = len(indicators)  # 9

    # 0~9 → 0~1 정규화
    score = min(total_points / max_points, 1.0) if max_points > 0 else 0.0

    return {
        "score": round(score, 4),
        "total_points": total_points,
        "indicators": indicators,
        "detail": f"Macro Score: {score:.2f} ({total_points:.1f}/{max_points}, VIX 제외)",
    }
