"""
tests/vix_dependency_test.py — VIX Dependency Analysis

Quantifies how much VIX (^VIX, ^VIX3M) influences the final risk score
across all signals in the system.

Method:
1. Fetch 2y market data, run calculate_final_risk() for baseline
2. Replace ^VIX and ^VIX3M with neutral constants, re-run for comparison
3. Measure per-signal and total impact
4. Repeat at multiple past dates to check if VIX dependency varies by regime
"""

import sys
import io
import os

# Windows cp949 encoding fix
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, "C:\\Users\\matro\\Downloads\\위기감지")

import warnings
warnings.filterwarnings("ignore")

import logging
logging.basicConfig(level=logging.WARNING)

import yaml
import numpy as np
import pandas as pd
from pathlib import Path

from data.fetcher import fetch_market_data
from risk.risk_engine import calculate_final_risk
from main_v2 import get_v2_tickers, load_config


def neutralize_vix(close: pd.DataFrame, neutral_vix: float = 15.0) -> pd.DataFrame:
    """Replace ^VIX and ^VIX3M with neutral constant values."""
    modified = close.copy()
    if "^VIX" in modified.columns:
        modified["^VIX"] = neutral_vix
    if "^VIX3M" in modified.columns:
        # VIX3M is typically slightly above VIX in contango; use neutral_vix * 1.05
        modified["^VIX3M"] = neutral_vix * 1.05
    return modified


def run_single_comparison(close: pd.DataFrame, config: dict, label: str = "Current"):
    """Run baseline vs VIX-neutralized and return detailed comparison."""
    # Baseline
    baseline = calculate_final_risk(close, config)

    # VIX-neutralized
    close_no_vix = neutralize_vix(close, neutral_vix=15.0)
    no_vix = calculate_final_risk(close_no_vix, config)

    # Per-signal comparison
    signal_impacts = {}
    for sig_name in baseline.get("signal_summary", {}):
        b_score = baseline["signal_summary"][sig_name]["score"]
        n_score = no_vix["signal_summary"][sig_name]["score"]
        b_weight = baseline["signal_summary"][sig_name]["weight"]
        n_weight = no_vix["signal_summary"][sig_name]["weight"]

        if b_score is None:
            b_score = 0.5
        if n_score is None:
            n_score = 0.5

        signal_impacts[sig_name] = {
            "baseline_score": float(b_score),
            "neutralized_score": float(n_score),
            "score_diff": float(n_score) - float(b_score),
            "baseline_weight": float(b_weight),
            "neutralized_weight": float(n_weight),
            "weighted_impact": (float(n_score) * float(n_weight)) - (float(b_score) * float(b_weight)),
        }

    return {
        "label": label,
        "baseline_final": baseline["final_score"],
        "neutralized_final": no_vix["final_score"],
        "diff": no_vix["final_score"] - baseline["final_score"],
        "baseline_regime": baseline["regime"].get("regime", "Unknown"),
        "neutralized_regime": no_vix["regime"].get("regime", "Unknown"),
        "signal_impacts": signal_impacts,
    }


def print_comparison(result: dict):
    """Pretty-print a single comparison result."""
    print(f"\n{'='*70}")
    print(f"  {result['label']}")
    print(f"{'='*70}")
    print(f"  Baseline final score:     {result['baseline_final']:.4f}")
    print(f"  VIX-neutralized score:    {result['neutralized_final']:.4f}")
    print(f"  Difference:               {result['diff']:+.4f}")
    print(f"  Baseline regime:          {result['baseline_regime']}")
    print(f"  Neutralized regime:       {result['neutralized_regime']}")

    print(f"\n  {'Signal':<16} {'Baseline':>10} {'No-VIX':>10} {'Diff':>10} {'Wt-Impact':>10}")
    print(f"  {'-'*16} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")

    for name, imp in result["signal_impacts"].items():
        vix_flag = ""
        if name == "volatility":
            vix_flag = " ***"
        elif name == "regime":
            vix_flag = " **"
        elif name == "macro":
            vix_flag = " (excluded)"

        print(f"  {name:<16} {imp['baseline_score']:>10.4f} {imp['neutralized_score']:>10.4f} "
              f"{imp['score_diff']:>+10.4f} {imp['weighted_impact']:>+10.4f}{vix_flag}")

    # Effective VIX influence
    if result['baseline_final'] > 0:
        pct_influence = abs(result['diff']) / result['baseline_final'] * 100
    else:
        pct_influence = 0.0
    print(f"\n  VIX effective influence on final score: {pct_influence:.1f}% "
          f"({abs(result['diff']):.4f} / {result['baseline_final']:.4f})")


def main():
    print("=" * 70)
    print("  VIX DEPENDENCY ANALYSIS")
    print("  Quantifying VIX influence on the risk engine")
    print("=" * 70)

    # Load config & fetch data
    config = load_config()
    tickers = get_v2_tickers(config)

    print(f"\nFetching 2y data for {len(tickers)} tickers...")
    close = fetch_market_data(tickers=tickers, period="2y")

    if close.empty:
        print("ERROR: Data fetch failed")
        return

    print(f"Data range: {close.index[0].strftime('%Y-%m-%d')} to {close.index[-1].strftime('%Y-%m-%d')}")
    print(f"Tickers: {len(close.columns)}")

    # Check VIX presence
    vix_present = "^VIX" in close.columns
    vix3m_present = "^VIX3M" in close.columns
    print(f"\n^VIX in data: {vix_present}")
    print(f"^VIX3M in data: {vix3m_present}")
    if vix_present:
        vix_series = close["^VIX"].dropna()
        print(f"Current VIX: {vix_series.iloc[-1]:.2f}")
        print(f"VIX median (2y): {vix_series.median():.2f}")
        print(f"VIX mean (2y): {vix_series.mean():.2f}")

    # ── Part 1: Current date comparison ──────────────────────────────
    print("\n" + "#" * 70)
    print("  PART 1: CURRENT DATE - BASELINE vs VIX-NEUTRALIZED")
    print("#" * 70)

    current_result = run_single_comparison(close, config, "Current Date (latest)")
    print_comparison(current_result)

    # ── Part 2: VIX channel breakdown ────────────────────────────────
    print("\n" + "#" * 70)
    print("  PART 2: VIX INFLUENCE CHANNELS")
    print("#" * 70)

    channels = {
        "volatility": "3 of 4 sub-indicators use ^VIX directly (VIX level 35%, VVIX proxy 20%, term structure 20%)",
        "regime": "^VIX is one of 6 HMM features (vix_level); also used for state labeling (Crisis = highest VIX mean)",
        "macro": "VIX EXCLUDED from macro score (handled by volatility signal)",
        "liquidity": "Does NOT use VIX",
        "breadth": "Does NOT use VIX",
        "cross_asset": "Does NOT use VIX",
        "global_macro": "Does NOT use VIX",
    }

    print("\n  VIX usage by signal:")
    for sig, desc in channels.items():
        imp = current_result["signal_impacts"].get(sig, {})
        diff = imp.get("score_diff", 0.0)
        print(f"    {sig:<16}: {desc}")
        print(f"    {'':16}  Score change when VIX neutralized: {diff:+.4f}")

    # ── Part 3: Historical rolling analysis ──────────────────────────
    print("\n" + "#" * 70)
    print("  PART 3: HISTORICAL ANALYSIS (every 10 business days, 100 days)")
    print("#" * 70)

    total_days = len(close)
    offsets = list(range(0, min(101, total_days - 252), 10))  # need at least 252 days of history

    historical_results = []
    for offset in offsets:
        if offset == 0:
            subset = close
            date_label = close.index[-1].strftime('%Y-%m-%d')
        else:
            subset = close.iloc[:-offset]
            date_label = subset.index[-1].strftime('%Y-%m-%d')

        if len(subset) < 252:
            continue

        result = run_single_comparison(subset, config, f"T-{offset} ({date_label})")
        result["offset"] = offset
        result["date"] = date_label
        if vix_present and "^VIX" in subset.columns:
            result["vix_level"] = float(subset["^VIX"].dropna().iloc[-1])
        else:
            result["vix_level"] = None
        historical_results.append(result)

    # Print historical summary table
    print(f"\n  {'Offset':<8} {'Date':<12} {'VIX':>6} {'Baseline':>10} {'No-VIX':>10} "
          f"{'Diff':>8} {'Influence%':>10} {'Regime':<20}")
    print(f"  {'-'*8} {'-'*12} {'-'*6} {'-'*10} {'-'*10} {'-'*8} {'-'*10} {'-'*20}")

    for r in historical_results:
        vix_str = f"{r['vix_level']:.1f}" if r['vix_level'] else "N/A"
        if r['baseline_final'] > 0:
            influence_pct = abs(r['diff']) / r['baseline_final'] * 100
        else:
            influence_pct = 0.0
        print(f"  T-{r['offset']:<5} {r['date']:<12} {vix_str:>6} {r['baseline_final']:>10.4f} "
              f"{r['neutralized_final']:>10.4f} {r['diff']:>+8.4f} {influence_pct:>9.1f}% "
              f"{r['baseline_regime']:<20}")

    # ── Part 4: Summary Statistics ───────────────────────────────────
    print("\n" + "#" * 70)
    print("  PART 4: SUMMARY STATISTICS")
    print("#" * 70)

    if historical_results:
        diffs = [r['diff'] for r in historical_results]
        abs_diffs = [abs(d) for d in diffs]
        influences = []
        for r in historical_results:
            if r['baseline_final'] > 0:
                influences.append(abs(r['diff']) / r['baseline_final'] * 100)

        print(f"\n  Over {len(historical_results)} sample dates:")
        print(f"    Mean absolute score change:    {np.mean(abs_diffs):.4f}")
        print(f"    Max absolute score change:     {np.max(abs_diffs):.4f}")
        print(f"    Min absolute score change:     {np.min(abs_diffs):.4f}")
        print(f"    Std of score change:           {np.std(diffs):.4f}")

        if influences:
            print(f"\n    Mean VIX influence (%):        {np.mean(influences):.1f}%")
            print(f"    Max VIX influence (%):         {np.max(influences):.1f}%")
            print(f"    Min VIX influence (%):         {np.min(influences):.1f}%")

        # Per-signal average impact
        print(f"\n  Average per-signal impact of VIX neutralization:")
        all_signals = list(historical_results[0]["signal_impacts"].keys())
        for sig in all_signals:
            avg_diff = np.mean([abs(r["signal_impacts"][sig]["score_diff"]) for r in historical_results])
            avg_wt_imp = np.mean([abs(r["signal_impacts"][sig]["weighted_impact"]) for r in historical_results])
            print(f"    {sig:<16}: avg |score_diff| = {avg_diff:.4f}, avg |weighted_impact| = {avg_wt_imp:.4f}")

        # Correlation: VIX level vs influence
        if all(r['vix_level'] is not None for r in historical_results) and len(historical_results) > 2:
            vix_levels = [r['vix_level'] for r in historical_results]
            corr = np.corrcoef(vix_levels, abs_diffs)[0, 1]
            print(f"\n  Correlation between VIX level and |score change|: {corr:.3f}")
            if abs(corr) > 0.5:
                print(f"    -> Strong: VIX dependency {'increases' if corr > 0 else 'decreases'} "
                      f"when VIX is higher")
            elif abs(corr) > 0.3:
                print(f"    -> Moderate correlation")
            else:
                print(f"    -> Weak: VIX dependency is relatively stable across market conditions")

    # ── Theoretical max influence ────────────────────────────────────
    print(f"\n  Theoretical VIX influence channels:")
    vol_weight = config.get("risk_engine", {}).get("weights", {}).get("volatility", 0.18)
    regime_weight = config.get("risk_engine", {}).get("weights", {}).get("regime", 0.10)
    print(f"    Volatility signal weight: {vol_weight:.0%}")
    print(f"      -> VIX sub-indicators: 75% of volatility (VIX level 35% + VVIX 20% + term structure 20%)")
    print(f"      -> Theoretical max via volatility: {vol_weight * 0.75:.1%} of final score")
    print(f"    Regime signal weight: {regime_weight:.0%}")
    print(f"      -> VIX is 1 of 6 HMM features (~17%), but also drives state labeling")
    print(f"      -> Theoretical max via regime: {regime_weight:.0%} (indirect, hard to bound)")
    print(f"    Regime also affects dynamic weight multipliers (can shift all weights)")
    print(f"    Total theoretical maximum VIX influence: ~{(vol_weight * 0.75 + regime_weight) * 100:.0f}%+ "
          f"(with dynamic weight cascading effects)")

    print(f"\n{'='*70}")
    print(f"  ANALYSIS COMPLETE")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
