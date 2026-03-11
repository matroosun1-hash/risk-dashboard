"""V2 Pipeline Verification Test"""
import sys, os
sys.path.insert(0, '.')

from main_v2 import load_config, get_v2_tickers
from data.fetcher import fetch_market_data
from risk.risk_engine import calculate_final_risk
from risk.position_sizing import calculate_position_sizing
from portfolio.allocator import generate_portfolio_action

config = load_config()
tickers = get_v2_tickers(config)
print(f"Collecting {len(tickers)} tickers...")
close = fetch_market_data(tickers=tickers, period="2y")
print(f"Tickers: {len(close.columns)}")
print(f"Range: {close.index[0].strftime('%Y-%m-%d')} to {close.index[-1].strftime('%Y-%m-%d')}")
print()

print("Running V2 Analysis...")
risk_result = calculate_final_risk(close, config)
sizing = calculate_position_sizing(risk_result["final_score"], close, config)
action = generate_portfolio_action(risk_result, sizing, config)

print()
print("=== SIGNAL BREAKDOWN ===")
for name, info in risk_result.get("signal_summary", {}).items():
    print(f"  {name:16s}: {info['score']:.3f} (w={info['weight']:.2f})")
print(f"  {'FINAL SCORE':16s}: {risk_result['final_score']:.3f}")

print()
regime = risk_result.get("regime", {})
print(f"Regime: {regime.get('regime', '?')}")
probs = regime.get("probabilities", {})
for r, p in probs.items():
    print(f"  {r}: {p:.1%}")

print()
print(f"Risk Level: {action['risk_level']}")
print(f"Vol: current={sizing.get('current_vol', 0):.1%} target={sizing.get('target_vol', 0):.0%}")
print(f"Allocation:")
for k, v in action["allocation"].items():
    print(f"  {k}: {v:.0%}")
print()
print("Actions:")
for a in action["actions"]:
    print(f"  {a}")

print()
print("TEST OK")
