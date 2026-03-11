"""
tests/backtester.py - 과거 위기 시나리오(2008, 2018, 2020, 2022) 백테스트 스크립트
Quant Risk Engine V2
"""

import sys
from pathlib import Path
import pandas as pd
import yaml
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 경고 무시
import warnings
warnings.filterwarnings("ignore")

from data.fetcher import fetch_market_data
from risk.risk_engine import calculate_final_risk
from risk.position_sizing import calculate_position_sizing
from main_v2 import get_v2_tickers

def load_config():
    with open(PROJECT_ROOT / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def run_backtest():
    print("🚀 Quant Risk Engine V2 — Historical Crisis Backtester")
    config = load_config()
    tickers = get_v2_tickers(config)
    
    print(f"📡 데이터 수집 중... (Max Period)")
    close_all = fetch_market_data(tickers=tickers, period="max")
    
    crisis_dates = {
        "2008 Financial Crisis (Lehman)": "2008-09-15",
        "2018 Volmageddon": "2018-02-05",
        "2020 COVID-19 Crash": "2020-03-20",
        "2022 Inflation Bear Market": "2022-06-15",
        "Normal Market (2021 Bull)": "2021-08-02"
    }
    
    # 평가 지표 저장
    results = []

    for name, date_str in crisis_dates.items():
        print(f"\n" + "="*50)
        print(f"🗓️  Testing: {name} ({date_str})")
        
        target_date = pd.Timestamp(date_str)
        close = close_all[close_all.index <= target_date]
        
        if len(close) < 252:
            print(f"⚠️ 데이터 부족 (길이: {len(close)})")
            continue
            
        try:
            risk = calculate_final_risk(close, config)
            sizing = calculate_position_sizing(risk["final_score"], close, config)
            alloc = sizing['allocation']
            
            print(f"Final Risk Score: {risk['final_score']:.2f}")
            print(f"Market Regime:    {risk['regime'].get('regime', 'Unknown')}")
            print(f"Allocation:       Equity {alloc['equity']:.0%} | Treasury {alloc['treasury']:.0%} | Cash {alloc['cash']:.0%} | Gold {alloc['gold']:.0%}")
            
            results.append({
                "Event": name,
                "Date": date_str,
                "Risk Score": risk["final_score"],
                "Regime": risk["regime"].get("regime", "Unknown"),
                "Eq Alloc": f"{alloc['equity']:.0%}"
            })
            
        except Exception as e:
            print(f"❌ Error 시뮬레이션 중단: {e}")

    print("\n" + "="*50)
    print("📊 백테스트 서머리:")
    summary_df = pd.DataFrame(results)
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    run_backtest()
