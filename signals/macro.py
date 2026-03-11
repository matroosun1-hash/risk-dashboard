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

    Returns:
        {
            "score": 0~1 float,
            "total_points": 원점수 (0~10),
            "indicators": 각 지표 결과 리스트,
            "level": 기존 Level 정보,
        }
    """
    stage1_cfg = config.get("stage1", {})
    indicators = run_all_indicators(close, stage1_cfg)
    total_points = calculate_total_score(indicators)

    # 0~10 → 0~1 정규화
    score = min(total_points / 10.0, 1.0)

    return {
        "score": score,
        "total_points": total_points,
        "indicators": indicators,
        "detail": f"Macro Score: {score:.2f} ({total_points:.1f}/10)",
    }
