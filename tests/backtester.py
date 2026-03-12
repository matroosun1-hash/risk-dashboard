"""
tests/backtester.py — 과거 위기 선행 감지 백테스트

검증 방식:
- 각 위기의 고점(Peak) 기준 T-60, T-30, T-15, T-0일 시점에서 엔진 실행
- 언제 처음 Level 2+ 경고가 발동됐는지 측정 (선행성 검증)
- 이후 30일 SPY 실제 수익률과 비교 (정확성 검증)
- 2019 bull market에서 오경보 발동 여부 확인 (오경보 검증)
"""

import sys
import io
import warnings
from pathlib import Path

# Windows cp949 인코딩 대응
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np
import yaml

from data.fetcher import fetch_market_data
from risk.risk_engine import calculate_final_risk
from main_v2 import get_v2_tickers


def load_config():
    with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def score_to_level(score: float) -> int:
    if score >= 0.8: return 4
    if score >= 0.6: return 3
    if score >= 0.4: return 2
    if score >= 0.2: return 1
    return 0


LEVEL_NAMES = {0: "정상", 1: "주의", 2: "경고", 3: "위험", 4: "극도위험"}


# ── 위기 시나리오 정의 ──────────────────────────────────────────
# peak: 시장 고점 (하락 시작 직전)
# label: 사건명
CRISES = [
    {
        "label": "2018 Q4 급락",
        "peak": "2018-09-20",
        "note": "미중 무역전쟁, Fed 긴축. SPY -20% (3개월)",
    },
    {
        "label": "2020 COVID 폭락",
        "peak": "2020-02-19",
        "note": "코로나19 팬데믹. SPY -34% (33일)",
    },
    {
        "label": "2022 인플레이션 베어",
        "peak": "2022-01-04",
        "note": "Fed 급격 금리인상. SPY -25% (9개월)",
    },
    {
        "label": "2019 Bull (오경보 체크)",
        "peak": "2019-07-26",
        "note": "강세장 중반. 경고 발동 시 오경보.",
    },
]

# 각 고점 기준 몇 일 전에 체크할지
CHECK_OFFSETS = [60, 30, 15, 0]


def run_engine_at(close_all: pd.DataFrame, date_str: str, config: dict) -> dict | None:
    """특정 날짜까지의 데이터로 엔진 실행."""
    target = pd.Timestamp(date_str)
    close = close_all[close_all.index <= target]
    if len(close) < 252:
        return None
    try:
        result = calculate_final_risk(close, config)
        return result
    except Exception as e:
        print(f"  [오류] {date_str}: {e}")
        return None


def get_spy_forward_return(close_all: pd.DataFrame, date_str: str, days: int = 30) -> float | None:
    """date_str 이후 days일간 SPY 수익률."""
    if "SPY" not in close_all.columns:
        return None
    target = pd.Timestamp(date_str)
    future = close_all[close_all.index > target]["SPY"].dropna()
    if len(future) < days:
        return None
    return float(future.iloc[days - 1] / future.iloc[0] - 1)


def business_days_before(date_str: str, offset: int) -> str:
    """영업일 기준 offset일 이전 날짜."""
    target = pd.Timestamp(date_str)
    result = target - pd.offsets.BDay(offset)
    return result.strftime("%Y-%m-%d")


# ── 메인 ────────────────────────────────────────────────────────
def run_backtest():
    print("=" * 60)
    print("  Quant Risk Engine V2 — 선행 감지 백테스트")
    print("=" * 60)

    config = load_config()
    tickers = get_v2_tickers(config)

    print("\n데이터 수집 중 (max period)... 약 1~2분 소요\n")
    close_all = fetch_market_data(tickers=tickers, period="max")

    all_results = []

    for crisis in CRISES:
        label = crisis["label"]
        peak  = crisis["peak"]
        note  = crisis["note"]

        print(f"\n{'='*60}")
        print(f"[{label}]  고점: {peak}")
        print(f"  {note}")
        print(f"{'='*60}")
        print(f"{'날짜':<12} {'T-일':>5} {'Score':>7} {'Level':>8} {'30일 SPY':>9}")
        print(f"{'-'*50}")

        first_warning_day = None  # 처음 Level 2 경고 발동 시점

        for offset in CHECK_OFFSETS:
            check_date = business_days_before(peak, offset)
            result = run_engine_at(close_all, check_date, config)

            if result is None:
                print(f"{check_date:<12} {'T-'+str(offset):>5}  {'데이터부족':>16}")
                continue

            score = result["final_score"]
            level = score_to_level(score)
            fwd   = get_spy_forward_return(close_all, check_date, 30)
            fwd_str = f"{fwd:+.1%}" if fwd is not None else "N/A"

            flag = ""
            if level >= 2 and first_warning_day is None:
                first_warning_day = (offset, check_date)
                flag = " ◀ 첫 경고"

            print(f"{check_date:<12} {'T-'+str(offset):>5}  {score:.3f}  "
                  f"L{level} {LEVEL_NAMES[level]:<6}  {fwd_str:>8}{flag}")

            all_results.append({
                "위기": label,
                "날짜": check_date,
                "T-일": offset,
                "Score": round(score, 3),
                "Level": level,
                "30일SPY": fwd_str,
            })

        if first_warning_day:
            offset, date = first_warning_day
            print(f"\n  → 첫 Level 2 경고: 고점 {offset}일 전 ({date})")
        else:
            print(f"\n  → Level 2 이상 경고 없음")

    # ── 최종 요약 ──────────────────────────────────────────────
    print(f"\n\n{'='*60}")
    print("  백테스트 요약")
    print(f"{'='*60}")

    crisis_results = [r for r in all_results if "오경보" not in r["위기"]]
    bull_results   = [r for r in all_results if "오경보" in r["위기"]]

    print("\n[위기 감지 성능]")
    for crisis in CRISES:
        if "오경보" in crisis["label"]:
            continue
        label = crisis["label"]
        rows = [r for r in all_results if r["위기"] == label]
        warnings_fired = [r for r in rows if r["Level"] >= 2]
        if warnings_fired:
            earliest = max(r["T-일"] for r in warnings_fired)
            print(f"  {label:<22} → 고점 {earliest:>2}일 전 첫 경고 발동")
        else:
            print(f"  {label:<22} → 경고 미발동 (놓침)")

    print("\n[오경보 체크 — 2019 Bull Market]")
    bull_warnings = [r for r in bull_results if r["Level"] >= 2]
    if bull_warnings:
        print(f"  ⚠️  오경보 발동 {len(bull_warnings)}회 (총 {len(bull_results)}회 체크)")
    else:
        print(f"  ✅ 오경보 없음 (총 {len(bull_results)}회 체크, 모두 Level 1 이하)")


if __name__ == "__main__":
    run_backtest()
