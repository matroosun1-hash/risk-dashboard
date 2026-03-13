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
    if score >= 0.45: return 2
    if score >= 0.2: return 1
    return 0


LEVEL_NAMES = {0: "정상", 1: "주의", 2: "경고", 3: "위험", 4: "극도위험"}


# ── 위기 시나리오 정의 ──────────────────────────────────────────
# peak: 시장 고점 (하락 시작 직전)
# label: 사건명
CRISES = [
    {
        "label": "2008 금융위기",
        "peak": "2007-10-09",
        "note": "서브프라임 모기지. SPY -57% (17개월)",
    },
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


def run_engine_at(close_all: pd.DataFrame, date_str: str, config: dict,
                  dynamic_weights: bool = True) -> dict | None:
    """특정 날짜까지의 데이터로 엔진 실행."""
    target = pd.Timestamp(date_str)
    close = close_all[close_all.index <= target]
    if len(close) < 252:
        return None
    try:
        result = calculate_final_risk(close, config, dynamic_weights=dynamic_weights)
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

    all_results = {True: [], False: []}  # dynamic → True, static → False

    for crisis in CRISES:
        label = crisis["label"]
        peak  = crisis["peak"]
        note  = crisis["note"]

        print(f"\n{'='*70}")
        print(f"[{label}]  고점: {peak}")
        print(f"  {note}")
        print(f"{'='*70}")
        print(f"{'날짜':<12} {'T-일':>5}  {'Static':>13}  {'Dynamic':>13}  {'차이':>7}  {'30일SPY':>9}")
        print(f"{'-'*70}")

        first_warning = {True: None, False: None}

        for offset in CHECK_OFFSETS:
            check_date = business_days_before(peak, offset)
            r_static  = run_engine_at(close_all, check_date, config, dynamic_weights=False)
            r_dynamic = run_engine_at(close_all, check_date, config, dynamic_weights=True)

            if r_static is None or r_dynamic is None:
                print(f"{check_date:<12} {'T-'+str(offset):>5}  {'데이터부족':>30}")
                continue

            s_score = r_static["final_score"]
            d_score = r_dynamic["final_score"]
            s_level = score_to_level(s_score)
            d_level = score_to_level(d_score)
            diff    = d_score - s_score
            regime  = r_dynamic["regime"].get("regime", "?")[:12]
            fwd     = get_spy_forward_return(close_all, check_date, 30)
            fwd_str = f"{fwd:+.1%}" if fwd is not None else "N/A"

            flags = ""
            if d_level >= 2 and first_warning[True] is None:
                first_warning[True] = (offset, check_date)
                flags += " ◀D"
            if s_level >= 2 and first_warning[False] is None:
                first_warning[False] = (offset, check_date)
                flags += " ◀S"

            diff_str = f"{diff:+.3f}"
            print(f"{check_date:<12} {'T-'+str(offset):>5}"
                  f"  {s_score:.3f} L{s_level}"
                  f"  {d_score:.3f} L{d_level}"
                  f"  {diff_str:>7}"
                  f"  {fwd_str:>8}  [{regime}]{flags}")

            for dyn in (True, False):
                res = r_dynamic if dyn else r_static
                all_results[dyn].append({
                    "위기": label,
                    "날짜": check_date,
                    "T-일": offset,
                    "Score": round(res["final_score"], 3),
                    "Level": score_to_level(res["final_score"]),
                    "30일SPY": fwd_str,
                })

        print()
        for dyn, tag in ((True, "Dynamic"), (False, "Static")):
            if first_warning[dyn]:
                o, d = first_warning[dyn]
                print(f"  [{tag}] 첫 L2 경고: 고점 {o}일 전 ({d})")
            else:
                print(f"  [{tag}] Level 2 이상 경고 없음")

    # ── 최종 요약 ──────────────────────────────────────────────
    print(f"\n\n{'='*70}")
    print("  백테스트 요약 — Static vs Dynamic 비교")
    print(f"{'='*70}")

    print(f"\n{'위기':<24} {'Static 선행':>12} {'Dynamic 선행':>13} {'개선':>8}")
    print(f"{'-'*60}")
    for crisis in CRISES:
        if "오경보" in crisis["label"]:
            continue
        lbl = crisis["label"]
        for dyn, tag in ((False, "static"), (True, "dynamic")):
            rows = [r for r in all_results[dyn] if r["위기"] == lbl]
            fired = [r for r in rows if r["Level"] >= 2]
            if dyn:
                d_lead = max(r["T-일"] for r in fired) if fired else None
            else:
                s_lead = max(r["T-일"] for r in fired) if fired else None

        s_str = f"{s_lead}일 전" if s_lead else "놓침"
        d_str = f"{d_lead}일 전" if d_lead else "놓침"
        if s_lead is not None and d_lead is not None:
            imp = f"+{d_lead - s_lead}일" if d_lead > s_lead else (f"{d_lead - s_lead}일" if d_lead < s_lead else "동일")
        elif d_lead is not None:
            imp = "신규감지"
        elif s_lead is not None:
            imp = "감지손실"
        else:
            imp = "-"
        print(f"  {lbl:<22} {s_str:>12} {d_str:>13} {imp:>8}")

    print(f"\n[오경보 체크 — 2019 Bull Market]")
    for dyn, tag in ((False, "Static "), (True, "Dynamic")):
        bull = [r for r in all_results[dyn] if "오경보" in r["위기"]]
        fired = [r for r in bull if r["Level"] >= 2]
        if fired:
            print(f"  [{tag}] ⚠  오경보 {len(fired)}회 / {len(bull)}회 체크")
        else:
            print(f"  [{tag}] ✅ 오경보 없음 ({len(bull)}회 체크)")


if __name__ == "__main__":
    run_backtest()
