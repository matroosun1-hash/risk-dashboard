"""
tests/daily_backtest.py — 일별 전체 기간 백테스트

기존 4시점 스팟 체크의 한계를 극복하기 위한 일별 연속 백테스트.
매 영업일마다 risk score를 계산하여 감지율, 오경보율, 선행 일수 정량 평가.

FRED 없는 모드로 실행 (yfinance만 사용).
"""

import sys
import io
import os
import warnings
from pathlib import Path
from datetime import datetime

# Windows cp949 인코딩 대응
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

# FRED 환경 변수 제거 (백테스트에서 FRED 사용 차단)
os.environ.pop("FRED_API_KEY", None)

import pandas as pd
import numpy as np
import yaml

from data.fetcher import fetch_market_data
from risk.risk_engine import calculate_final_risk
from main_v2 import get_v2_tickers


def load_config():
    with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # FRED 비활성화 (백테스트용)
    cfg["fred"] = {"api_key": ""}
    return cfg


def score_to_level(score: float) -> int:
    if score >= 0.8: return 4
    if score >= 0.6: return 3
    if score >= 0.45: return 2
    if score >= 0.2: return 1
    return 0


LEVEL_NAMES = {0: "정상", 1: "주의", 2: "경고", 3: "위험", 4: "극도위험"}

# ── 위기 구간 정의 ──────────────────────────────────────
CRISIS_PERIODS = {
    "2020_COVID": {
        "peak": "2020-02-19",
        "trough": "2020-03-23",
        "label": "2020 COVID 폭락",
        "drawdown": "-34%",
    },
    "2022_Bear": {
        "peak": "2022-01-04",
        "trough": "2022-10-12",
        "label": "2022 인플레이션 베어",
        "drawdown": "-25%",
    },
}

# 선행 감지 윈도우 (위기 시작 N 영업일 전부터 감시)
LEAD_WINDOW = 60

# 백테스트 시작일 (충분한 히스토리 확보)
BACKTEST_START = "2019-06-01"


def run_daily_backtest():
    print("=" * 70)
    print("  일별 전체 기간 백테스트")
    print("=" * 70)

    config = load_config()
    tickers = get_v2_tickers(config)

    print(f"\n데이터 수집 중 (max period)... 약 1~2분 소요\n")
    close_all = fetch_market_data(tickers=tickers, period="max")

    if close_all.empty:
        print("ERROR: 데이터 수집 실패")
        return

    print(f"데이터 범위: {close_all.index[0].strftime('%Y-%m-%d')} ~ {close_all.index[-1].strftime('%Y-%m-%d')}")
    print(f"티커 수: {len(close_all.columns)}")

    # 백테스트 시작점
    start_date = pd.Timestamp(BACKTEST_START)
    all_dates = close_all.index[close_all.index >= start_date]

    # 5일 간격으로 샘플링 (전체 일별은 너무 느림)
    sample_dates = all_dates[::5]
    print(f"\n백테스트 기간: {sample_dates[0].strftime('%Y-%m-%d')} ~ {sample_dates[-1].strftime('%Y-%m-%d')}")
    print(f"샘플 수: {len(sample_dates)}개 (5 영업일 간격)")
    print()

    # ── 일별 스코어 계산 ────────────────────────────────
    results = []
    total = len(sample_dates)

    for i, date in enumerate(sample_dates):
        sliced = close_all[close_all.index <= date]
        if len(sliced) < 252:
            continue

        try:
            result = calculate_final_risk(sliced, config, dynamic_weights=True)
            score = result["final_score"]
            level = score_to_level(score)
            regime = result.get("regime", {}).get("regime", "Unknown")

            results.append({
                "date": date,
                "score": score,
                "level": level,
                "regime": regime,
            })

            if (i + 1) % 50 == 0 or i == total - 1:
                print(f"  [{i+1:4d}/{total}] {date.strftime('%Y-%m-%d')}  "
                      f"score={score:.3f}  L{level}  {regime}")

        except Exception as e:
            print(f"  [{i+1:4d}/{total}] {date.strftime('%Y-%m-%d')}  ERROR: {e}")

    if not results:
        print("ERROR: 결과 없음")
        return

    df = pd.DataFrame(results)
    df.set_index("date", inplace=True)

    # CSV 저장
    csv_path = PROJECT_ROOT / "tests" / "backtest_results.csv"
    df.to_csv(csv_path)
    print(f"\n결과 저장: {csv_path}")

    # ── 위기별 분석 ─────────────────────────────────────
    print(f"\n{'='*70}")
    print("  위기별 감지 분석")
    print(f"{'='*70}")

    for crisis_id, crisis in CRISIS_PERIODS.items():
        peak = pd.Timestamp(crisis["peak"])
        trough = pd.Timestamp(crisis["trough"])
        label = crisis["label"]

        print(f"\n[{label}] 고점: {crisis['peak']}, 저점: {crisis['trough']}, 하락폭: {crisis['drawdown']}")
        print("-" * 60)

        # 위기 구간 중 L2+ 비율 (감지율)
        crisis_mask = (df.index >= peak) & (df.index <= trough)
        crisis_data = df[crisis_mask]
        if len(crisis_data) > 0:
            recall = (crisis_data["level"] >= 2).mean()
            avg_score = crisis_data["score"].mean()
            print(f"  위기 구간 감지율: {recall:.0%} (L2+ 비율)")
            print(f"  위기 구간 평균 스코어: {avg_score:.3f}")
        else:
            recall = 0
            print(f"  위기 구간 데이터 없음")

        # 선행 감지 (고점 전 LEAD_WINDOW일)
        lead_start = peak - pd.offsets.BDay(LEAD_WINDOW)
        lead_mask = (df.index >= lead_start) & (df.index < peak)
        lead_data = df[lead_mask]

        if len(lead_data) > 0:
            first_l2 = lead_data[lead_data["level"] >= 2]
            if len(first_l2) > 0:
                first_date = first_l2.index[0]
                lead_days = (peak - first_date).days
                print(f"  첫 L2 경고: 고점 {lead_days}일 전 ({first_date.strftime('%Y-%m-%d')})")
            else:
                print(f"  선행 구간 L2 경고 없음")
        else:
            print(f"  선행 구간 데이터 없음")

    # ── 오경보 분석 ─────────────────────────────────────
    print(f"\n{'='*70}")
    print("  오경보 분석")
    print(f"{'='*70}")

    # 위기가 아닌 구간 식별
    crisis_dates = set()
    for crisis in CRISIS_PERIODS.values():
        peak = pd.Timestamp(crisis["peak"])
        trough = pd.Timestamp(crisis["trough"])
        lead_start = peak - pd.offsets.BDay(LEAD_WINDOW)
        mask = (df.index >= lead_start) & (df.index <= trough)
        crisis_dates.update(df.index[mask].tolist())

    non_crisis = df[~df.index.isin(crisis_dates)]

    if len(non_crisis) > 0:
        l2_false = non_crisis[non_crisis["level"] >= 2]
        false_alarm_pct = len(l2_false) / len(non_crisis)
        print(f"\n  비위기 구간: {len(non_crisis)}개 샘플")
        print(f"  L2+ 오경보 횟수: {len(l2_false)}회")
        print(f"  오경보율: {false_alarm_pct:.1%}")

        # 오경보 블록 (연속 L2+) 세기
        if len(l2_false) > 0:
            print(f"\n  오경보 발생 시점:")
            # 연속 블록 카운트
            blocks = []
            current_block_start = None
            prev_date = None
            for date in l2_false.index:
                if prev_date is None or (date - prev_date).days > 10:
                    if current_block_start is not None:
                        blocks.append((current_block_start, prev_date))
                    current_block_start = date
                prev_date = date
            if current_block_start is not None:
                blocks.append((current_block_start, prev_date))

            for start, end in blocks:
                block_data = l2_false[(l2_false.index >= start) & (l2_false.index <= end)]
                avg_score = block_data["score"].mean()
                print(f"    {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}"
                      f"  ({len(block_data)}회, avg={avg_score:.3f})")

            print(f"\n  오경보 블록 수: {len(blocks)}개")
    else:
        print("  비위기 구간 데이터 없음")

    # ── 전체 통계 요약 ──────────────────────────────────
    print(f"\n{'='*70}")
    print("  전체 통계 요약")
    print(f"{'='*70}")
    print(f"\n  총 샘플 수: {len(df)}")
    print(f"  기간: {df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"\n  레벨 분포:")
    for level in range(5):
        count = (df["level"] == level).sum()
        pct = count / len(df)
        bar = "#" * int(pct * 50)
        print(f"    L{level} ({LEVEL_NAMES[level]}): {count:4d}회 ({pct:5.1%}) {bar}")
    print(f"\n  평균 스코어: {df['score'].mean():.3f}")
    print(f"  스코어 표준편차: {df['score'].std():.3f}")
    print(f"  최대 스코어: {df['score'].max():.3f}")
    print(f"  최소 스코어: {df['score'].min():.3f}")

    # Regime 분포
    print(f"\n  Regime 분포:")
    for regime in df["regime"].unique():
        count = (df["regime"] == regime).sum()
        pct = count / len(df)
        print(f"    {regime}: {count}회 ({pct:.1%})")


if __name__ == "__main__":
    run_daily_backtest()
