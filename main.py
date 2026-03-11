"""
2단계 퀀트 리스크 관리 시스템 — 메인 진입점

사용법:
    python main.py              # 전체 분석 실행
    python main.py --stage1     # 1단계만 실행
    python main.py --stage2     # 2단계만 실행
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime

import yaml
import pandas as pd

# 프로젝트 루트를 Python path에 추가
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.fetcher import fetch_market_data, get_close_prices
from stage1.indicators import run_all_indicators
from stage1.scorer import calculate_total_score, determine_level, format_stage1_report
from stage2.rotation import calculate_all_rotations
from stage2.leading import check_all_leading
from stage2.scorer import determine_rotation_level, format_stage2_report
from action.executor import generate_response, format_response_report


def load_config(config_path: str = "config.yaml") -> dict:
    """설정 파일을 로드합니다."""
    path = PROJECT_ROOT / config_path
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def print_header():
    """시스템 헤더를 출력합니다."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print()
    print("╔" + "═" * 58 + "╗")
    print("║   🛡️  2단계 퀀트 리스크 관리 시스템                       ║")
    print("║   Quantitative Risk Management System v1.0               ║")
    print(f"║   {now}                              ║")
    print("╚" + "═" * 58 + "╝")
    print()


def run_stage1(close: pd.DataFrame, config: dict) -> dict:
    """1단계: 하락장 조기탐지를 실행합니다."""
    stage1_cfg = config.get("stage1", {})

    # 10개 지표 계산
    indicator_results = run_all_indicators(close, stage1_cfg)

    # 종합 점수 및 Level 판정
    total_score = calculate_total_score(indicator_results)
    level_info = determine_level(total_score, stage1_cfg)

    # 결과 출력
    report = format_stage1_report(indicator_results, level_info)
    print(report)

    return {
        "indicators": indicator_results,
        "total_score": total_score,
        "level": level_info,
    }


def run_stage2(close: pd.DataFrame, config: dict) -> dict:
    """2단계: 섹터 로테이션 탐지를 실행합니다."""
    stage2_cfg = config.get("stage2", {})

    # 4개 로테이션 쌍 계산
    rotation_results = calculate_all_rotations(close, stage2_cfg)

    # 3개 선행지표 확인
    leading_results = check_all_leading(close, stage2_cfg)

    # 종합 Level 판정
    level_info = determine_rotation_level(rotation_results, leading_results, stage2_cfg)

    # 결과 출력
    report = format_stage2_report(rotation_results, leading_results, level_info)
    print(report)

    return {
        "rotation": rotation_results,
        "leading": leading_results,
        "level": level_info,
    }


def run_action(
    stage1_result: dict,
    stage2_result: dict,
    close: pd.DataFrame,
    config: dict,
) -> dict:
    """종합 대응 권고를 생성합니다."""
    action_cfg = config.get("action", {})
    holdings = config.get("portfolio", {}).get("holdings", [])

    response = generate_response(
        stage1_level=stage1_result["level"],
        stage2_level=stage2_result["level"],
        holdings=holdings,
        close=close,
        action_config=action_cfg,
    )

    report = format_response_report(response)
    print(report)

    return response


def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(description="2단계 퀀트 리스크 관리 시스템")
    parser.add_argument("--stage1", action="store_true", help="1단계만 실행")
    parser.add_argument("--stage2", action="store_true", help="2단계만 실행")
    parser.add_argument("--period", default="1y", help="데이터 기간 (기본: 1y)")
    parser.add_argument("--config", default="config.yaml", help="설정 파일 경로")
    args = parser.parse_args()

    # 둘 다 지정 안 하면 전체 실행
    run_s1 = args.stage1 or (not args.stage1 and not args.stage2)
    run_s2 = args.stage2 or (not args.stage1 and not args.stage2)

    print_header()

    # 설정 로드
    config = load_config(args.config)
    print("⚙️  설정 로드 완료")

    # 데이터 수집
    print(f"\n📡 시장 데이터 수집 중 (기간: {args.period})...")
    market_data = fetch_market_data(period=args.period)
    close = get_close_prices(market_data)
    print(f"📅 데이터 범위: {close.index[0].strftime('%Y-%m-%d')} ~ {close.index[-1].strftime('%Y-%m-%d')}")
    print(f"📊 수집 티커: {len(close.columns)}개\n")

    # 1단계 실행
    stage1_result = None
    if run_s1:
        stage1_result = run_stage1(close, config)

    # 2단계 실행
    stage2_result = None
    if run_s2:
        stage2_result = run_stage2(close, config)

    # 종합 대응 (둘 다 실행한 경우)
    if stage1_result and stage2_result:
        run_action(stage1_result, stage2_result, close, config)

    print("\n✅ 분석 완료\n")


if __name__ == "__main__":
    main()
