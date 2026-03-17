"""
tests/correlation_analysis.py — Signal Correlation & Independence Analysis

1. Fetches 2y market data, runs all 7 signals at multiple past dates
2. Computes correlation matrix between the 7 signal scores
3. Flags highly correlated pairs (>0.5)
4. Uses PCA to estimate effective independent signal count
"""

import sys
import os
import io
import warnings

# Windows encoding fix
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.environ["PYTHONIOENCODING"] = "utf-8"

warnings.filterwarnings("ignore")

from pathlib import Path
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

import yaml
import numpy as np
import pandas as pd
import logging

logging.basicConfig(level=logging.WARNING)

from data.fetcher import fetch_market_data
from signals.macro import calculate_macro_score
from signals.liquidity import calculate_liquidity_score
from signals.breadth import calculate_breadth_score
from signals.volatility import calculate_volatility_score
from signals.cross_asset import calculate_cross_asset_score
from signals.global_macro import calculate_global_macro_score
from regime.regime_model import detect_regime
from main_v2 import get_v2_tickers

SIGNAL_NAMES = ["macro", "liquidity", "breadth", "volatility", "cross_asset", "regime", "global_macro"]

SIGNAL_FUNCS = {
    "macro": calculate_macro_score,
    "liquidity": calculate_liquidity_score,
    "breadth": calculate_breadth_score,
    "volatility": calculate_volatility_score,
    "cross_asset": calculate_cross_asset_score,
    "regime": detect_regime,
    "global_macro": calculate_global_macro_score,
}


def compute_signals_at_date(close_all: pd.DataFrame, target_date, config: dict) -> dict:
    """Slice data up to target_date and compute all 7 signals."""
    sliced = close_all[close_all.index <= target_date].copy()
    if len(sliced) < 200:
        return None

    scores = {}
    for name in SIGNAL_NAMES:
        try:
            result = SIGNAL_FUNCS[name](sliced, config)
            score = result.get("score", np.nan)
            if score is None or (isinstance(score, float) and np.isnan(score)):
                score = np.nan
            scores[name] = float(score)
        except Exception as e:
            scores[name] = np.nan
    return scores


def main():
    print("=" * 70)
    print("  SIGNAL CORRELATION & INDEPENDENCE ANALYSIS")
    print("=" * 70)

    # Load config
    with open("config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Fetch data
    tickers = get_v2_tickers(config)
    print(f"\nFetching 2y data for {len(tickers)} tickers...")
    close_all = fetch_market_data(tickers=tickers, period="2y")
    if close_all.empty:
        print("ERROR: Data fetch failed")
        return

    print(f"Data range: {close_all.index[0].strftime('%Y-%m-%d')} to {close_all.index[-1].strftime('%Y-%m-%d')}")
    print(f"Tickers fetched: {len(close_all.columns)}")

    # Generate target dates: every 5 business days for last 250 days
    all_dates = close_all.index
    # We need at least 200 days of history, so start from index 200+
    min_start_idx = 200
    if len(all_dates) < min_start_idx + 50:
        print("ERROR: Not enough data points")
        return

    # Take dates from the last 250 trading days, every 5 days
    end_idx = len(all_dates) - 1
    start_idx = max(min_start_idx, end_idx - 250)
    sample_indices = list(range(start_idx, end_idx + 1, 5))
    target_dates = [all_dates[i] for i in sample_indices]

    print(f"\nSimulating signals at {len(target_dates)} dates (every 5 bdays, last ~250 days)")
    print(f"Date range: {target_dates[0].strftime('%Y-%m-%d')} to {target_dates[-1].strftime('%Y-%m-%d')}")
    print()

    # Collect scores
    records = []
    for i, dt in enumerate(target_dates):
        dt_str = dt.strftime('%Y-%m-%d')
        scores = compute_signals_at_date(close_all, dt, config)
        if scores is not None:
            scores["date"] = dt
            records.append(scores)
            valid = sum(1 for v in scores.values() if isinstance(v, float) and not np.isnan(v))
            print(f"  [{i+1:3d}/{len(target_dates)}] {dt_str}  signals={valid}/7  "
                  f"scores=[{', '.join(f'{scores[s]:.3f}' for s in SIGNAL_NAMES if not np.isnan(scores.get(s, np.nan)))}]")
        else:
            print(f"  [{i+1:3d}/{len(target_dates)}] {dt_str}  SKIPPED (insufficient data)")

    if len(records) < 10:
        print("ERROR: Too few valid data points for correlation analysis")
        return

    df = pd.DataFrame(records).set_index("date")
    print(f"\nCollected {len(df)} valid observations")

    # Drop columns that are all NaN
    valid_signals = [s for s in SIGNAL_NAMES if df[s].notna().sum() >= 10]
    dropped = [s for s in SIGNAL_NAMES if s not in valid_signals]
    if dropped:
        print(f"WARNING: Dropping signals with insufficient data: {dropped}")
    df_valid = df[valid_signals].dropna()
    print(f"Complete observations (no NaN): {len(df_valid)}")

    if len(df_valid) < 10:
        print("ERROR: Too few complete observations")
        return

    # =========================================================================
    # PART 1: Correlation Matrix
    # =========================================================================
    print("\n" + "=" * 70)
    print("  CORRELATION MATRIX")
    print("=" * 70)

    corr = df_valid.corr()
    print()

    # Pretty print
    header = "              " + "  ".join(f"{s:>12}" for s in valid_signals)
    print(header)
    print("-" * len(header))
    for sig in valid_signals:
        row = f"{sig:<14}"
        for sig2 in valid_signals:
            val = corr.loc[sig, sig2]
            row += f"  {val:>12.3f}"
        print(row)

    # =========================================================================
    # PART 2: High Correlation Pairs (>0.5)
    # =========================================================================
    print("\n" + "=" * 70)
    print("  HIGH CORRELATION PAIRS (|r| > 0.5)")
    print("=" * 70)

    flagged = []
    for i, s1 in enumerate(valid_signals):
        for j, s2 in enumerate(valid_signals):
            if j <= i:
                continue
            r = corr.loc[s1, s2]
            if abs(r) > 0.5:
                flagged.append((s1, s2, r))

    if flagged:
        print(f"\n  Found {len(flagged)} pair(s) with |correlation| > 0.5:\n")
        for s1, s2, r in sorted(flagged, key=lambda x: -abs(x[2])):
            direction = "POSITIVE" if r > 0 else "NEGATIVE"
            print(f"    {s1:>14} <-> {s2:<14}  r = {r:+.3f}  ({direction})")
            print(f"      -> These signals may be partially redundant")
    else:
        print("\n  No pairs with |correlation| > 0.5 found.")
        print("  All signals appear reasonably independent.")

    # Also show moderate correlations (0.3-0.5)
    print(f"\n  Moderate correlations (0.3 < |r| <= 0.5):")
    moderate = []
    for i, s1 in enumerate(valid_signals):
        for j, s2 in enumerate(valid_signals):
            if j <= i:
                continue
            r = corr.loc[s1, s2]
            if 0.3 < abs(r) <= 0.5:
                moderate.append((s1, s2, r))
    if moderate:
        for s1, s2, r in sorted(moderate, key=lambda x: -abs(x[2])):
            print(f"    {s1:>14} <-> {s2:<14}  r = {r:+.3f}")
    else:
        print("    None")

    # =========================================================================
    # PART 3: PCA — Effective Independent Signals
    # =========================================================================
    print("\n" + "=" * 70)
    print("  PCA ANALYSIS — EFFECTIVE INDEPENDENT SIGNALS")
    print("=" * 70)

    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA

    X = df_valid[valid_signals].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    pca = PCA()
    pca.fit(X_scaled)

    eigenvalues = pca.explained_variance_
    explained_ratio = pca.explained_variance_ratio_
    cumulative = np.cumsum(explained_ratio)

    print(f"\n  {'Component':<12} {'Eigenvalue':>12} {'Var Explained':>15} {'Cumulative':>12}")
    print("  " + "-" * 55)
    for i in range(len(valid_signals)):
        marker = " <-- 90%" if i > 0 and cumulative[i-1] < 0.9 <= cumulative[i] else ""
        if i == 0 and cumulative[0] >= 0.9:
            marker = " <-- 90%"
        print(f"  PC{i+1:<9} {eigenvalues[i]:>12.4f} {explained_ratio[i]:>14.1%} {cumulative[i]:>11.1%}{marker}")

    # Count components for 90% variance
    n_components_90 = int(np.searchsorted(cumulative, 0.9) + 1)
    n_components_80 = int(np.searchsorted(cumulative, 0.8) + 1)
    n_components_95 = int(np.searchsorted(cumulative, 0.95) + 1)

    print(f"\n  Components for 80% variance: {n_components_80}")
    print(f"  Components for 90% variance: {n_components_90}")
    print(f"  Components for 95% variance: {n_components_95}")
    print(f"  Total signals:               {len(valid_signals)}")

    # Effective number using Kaiser criterion (eigenvalue > 1)
    kaiser_count = int((eigenvalues > 1.0).sum())
    print(f"\n  Kaiser criterion (eigenvalue > 1): {kaiser_count} components")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)

    avg_abs_corr = np.mean([abs(corr.loc[s1, s2])
                            for i, s1 in enumerate(valid_signals)
                            for j, s2 in enumerate(valid_signals)
                            if j > i])

    print(f"""
  Total signals:                   {len(valid_signals)}
  Effective independent (90% var): {n_components_90}
  Kaiser criterion (eigenval > 1): {kaiser_count}
  Mean |correlation| (off-diag):   {avg_abs_corr:.3f}
  High correlation pairs (>0.5):   {len(flagged)}

  Interpretation:
    - If effective signals ~ total signals: good diversity, signals capture different risks
    - If effective signals << total signals: redundancy exists, consider merging or reweighting
    - Mean |correlation| < 0.3: excellent independence
    - Mean |correlation| 0.3-0.5: moderate overlap
    - Mean |correlation| > 0.5: significant redundancy
""")

    # Descriptive stats of each signal over time
    print("=" * 70)
    print("  SIGNAL DESCRIPTIVE STATISTICS (over sampled dates)")
    print("=" * 70)
    desc = df_valid[valid_signals].describe().T[["mean", "std", "min", "25%", "50%", "75%", "max"]]
    print()
    print(desc.to_string(float_format=lambda x: f"{x:.3f}"))
    print()


if __name__ == "__main__":
    main()
