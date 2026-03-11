"""
V2 퀀트 리스크 엔진 — 메인 진입점

사용법:
    python main_v2.py              # V2 전체 분석
    python main_v2.py --period 2y  # 2년 데이터
"""

import sys
import logging
from pathlib import Path
import argparse
from datetime import datetime

import yaml
import pandas as pd

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.fetcher import fetch_market_data, get_close_prices
from risk.risk_engine import calculate_final_risk
from risk.position_sizing import calculate_position_sizing
from portfolio.allocator import generate_portfolio_action


def load_config(config_path: str = "config.yaml") -> dict:
    path = PROJECT_ROOT / config_path
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_v2_tickers(config: dict) -> list[str]:
    """V2에 필요한 모든 티커를 수집합니다."""
    v2_cfg = config.get("v2_data", {}).get("tickers", {})
    tickers = set()
    for category_tickers in v2_cfg.values():
        tickers.update(category_tickers)
    # 기존 V1 티커도 포함
    from data.fetcher import get_all_tickers
    tickers.update(get_all_tickers())
    return list(tickers)


def print_header():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print()
    print("╔" + "═" * 58 + "╗")
    print("║   🏛️  Quant Risk Engine V2                                ║")
    print("║   Full Market Risk Engine                                 ║")
    print(f"║   {now}                              ║")
    print("╚" + "═" * 58 + "╝")
    print()


def print_signals(result: dict):
    """신호 결과를 콘솔에 출력합니다."""
    print("\n┌─────────────────────────────────────────────────┐")
    print("│  📡 Signal Breakdown                            │")
    print("├──────────────────┬──────────┬───────────────────┤")
    print("│  Signal          │  Score   │  Weight           │")
    print("├──────────────────┼──────────┼───────────────────┤")

    for name, info in result.get("signal_summary", {}).items():
        score = info.get("score", 0)
        weight = info.get("weight", 0)
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        print(f"│  {name:<16} │  {score:.2f}    │  {bar} {weight:.0%}  │")

    print("├──────────────────┼──────────┼───────────────────┤")
    final = result["final_score"]
    bar = "█" * int(final * 20) + "░" * (20 - int(final * 20))
    print(f"│  FINAL           │  {final:.2f}    │  {bar}       │")
    print("└──────────────────┴──────────┴───────────────────┘")


def print_allocation(action: dict):
    """배분 결과를 출력합니다."""
    alloc = action["allocation"]
    regime = action["regime"]
    risk_level = action["risk_level"]
    risk_icon = action["risk_icon"]

    print(f"\n{risk_icon} Risk Level: {risk_level} | Regime: {regime}")
    print(f"   Final Risk Score: {action['final_score']:.2f}")
    print()
    print("┌─────────────────────────────────────┐")
    print("│  📊 Recommended Allocation          │")
    print("├──────────────┬──────────────────────┤")
    for asset, pct in alloc.items():
        bar = "█" * int(pct * 30)
        print(f"│  {asset:<12} │  {pct:>5.0%}  {bar:<30} │")
    print("└──────────────┴──────────────────────┘")

    print("\n🎯 Actions:")
    for action_text in action["actions"]:
        print(f"   • {action_text}")


def main():
    parser = argparse.ArgumentParser(description="Quant Risk Engine V2")
    parser.add_argument("--period", default="2y", help="데이터 기간 (기본: 2y)")
    parser.add_argument("--config", default="config.yaml", help="설정 파일")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print_header()

    # 설정 로드
    config = load_config(args.config)
    print("⚙️  설정 로드 완료")

    # 데이터 수집 (V2 확장 티커)
    tickers = get_v2_tickers(config)
    print(f"\n📡 데이터 수집 중 ({len(tickers)}개 티커, 기간: {args.period})...")
    close = fetch_market_data(tickers=tickers, period=args.period)

    if close.empty:
        print("❌ 데이터 수집 실패")
        return

    print(f"📅 데이터 범위: {close.index[0].strftime('%Y-%m-%d')} ~ {close.index[-1].strftime('%Y-%m-%d')}")
    print(f"📊 수집 성공: {len(close.columns)}개 티커\n")

    # V2 분석 실행
    print("🔬 V2 Risk Analysis 시작...")
    risk_result = calculate_final_risk(close, config)

    # 포지션 사이징
    sizing = calculate_position_sizing(risk_result["final_score"], close, config)

    # 포트폴리오 행동 권고
    action = generate_portfolio_action(risk_result, sizing, config)

    # 결과 출력
    print_signals(risk_result)
    print_allocation(action)

    print("\n✅ V2 분석 완료\n")


if __name__ == "__main__":
    main()
