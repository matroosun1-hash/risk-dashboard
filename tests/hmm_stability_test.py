"""
HMM Regime Detection Stability Test

Tests:
1. Temporal stability: Run detect_regime() on last 20 business days (removing 1 day at a time)
   and track regime label changes.
2. Initialization sensitivity: Run HMM with 5 different random_state values on the same data
   and compare results.
"""

import sys
import io
import os
import warnings

# Windows cp949 encoding fix
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
os.environ["PYTHONIOENCODING"] = "utf-8"

warnings.filterwarnings("ignore")

sys.path.insert(0, "C:\\Users\\matro\\Downloads\\위기감지")

import yaml
import numpy as np
import pandas as pd
from data.fetcher import fetch_market_data
from main_v2 import get_v2_tickers
from regime.regime_model import detect_regime, _prepare_features

from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler


def load_config():
    with open("C:\\Users\\matro\\Downloads\\위기감지\\config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_temporal_stability_test(close: pd.DataFrame, config: dict):
    """Test 1: Remove 1 day at a time from the end, track regime changes."""
    print("=" * 70)
    print("  TEST 1: Temporal Stability (last 20 business days)")
    print("  Removing 1 day at a time from the end of the data")
    print("=" * 70)
    print()

    results = []
    dates = close.index[-20:]

    for i in range(20):
        # Slice data up to dates[i] (inclusive)
        end_date = dates[i]
        sliced = close.loc[:end_date]
        result = detect_regime(sliced, config)

        regime = result["regime"]
        score = result["score"]
        probs = result.get("probabilities", {})

        # Format probabilities
        prob_str = "  ".join(f"{k[:4]}={v:.2f}" for k, v in sorted(probs.items()))

        results.append({
            "date": end_date.strftime("%Y-%m-%d"),
            "regime": regime,
            "score": score,
            "probabilities": probs,
        })

        print(f"  {end_date.strftime('%Y-%m-%d')}  |  {regime:<20s}  |  score={score:.4f}  |  {prob_str}")

    # Count transitions
    transitions = 0
    for i in range(1, len(results)):
        if results[i]["regime"] != results[i - 1]["regime"]:
            transitions += 1

    print()
    print(f"  Regime transitions in 20 days: {transitions}")
    print(f"  Stability ratio: {1 - transitions / 19:.1%} (lower transitions = more stable)")
    print()

    return results, transitions


def run_random_state_sensitivity_test(close: pd.DataFrame, config: dict):
    """Test 2: Run HMM with different random_state values on the same data."""
    print("=" * 70)
    print("  TEST 2: Random State Sensitivity")
    print("  Same data, 5 different random_state initializations")
    print("=" * 70)
    print()

    regime_cfg = config.get("regime", {})
    n_states = regime_cfg.get("n_states", 4)
    labels = regime_cfg.get("labels", ["Expansion", "Inflation", "Correction", "Liquidity Crisis"])

    # Prepare features (replicate regime_model.py logic)
    features_full = _prepare_features(close)
    lookback_years = regime_cfg.get("lookback_years", None)
    if lookback_years is not None:
        cutoff = features_full.index[-1] - pd.DateOffset(years=lookback_years)
        features = features_full[features_full.index >= cutoff]
    else:
        features = features_full

    if len(features) < 100:
        print(f"  ERROR: Not enough data ({len(features)} rows, need 100+)")
        return [], 0

    scaler = StandardScaler()
    features_scaled = scaler.fit_transform(features.values)

    random_states = [42, 0, 123, 7, 999]
    results = []

    for rs in random_states:
        try:
            model = GaussianHMM(
                n_components=n_states,
                covariance_type="full",
                n_iter=200,
                random_state=rs,
                verbose=False,
            )
            model.fit(features_scaled)

            hidden_states = model.predict(features_scaled)
            state_probs = model.predict_proba(features_scaled)

            current_state = hidden_states[-1]
            current_probs = state_probs[-1]

            # Label states using means
            means = model.means_
            state_vix_mean = means[:, 1] if means.shape[1] > 1 else np.zeros(n_states)
            state_spy_mean = means[:, 0] if means.shape[1] > 0 else np.zeros(n_states)

            state_labels = {}
            used = set()

            crisis_state = int(np.argmax(state_vix_mean))
            state_labels[crisis_state] = "Liquidity Crisis"
            used.add(crisis_state)

            remaining = [(j, state_spy_mean[j]) for j in range(n_states) if j not in used]
            expansion_state = max(remaining, key=lambda x: x[1])[0]
            state_labels[expansion_state] = "Expansion"
            used.add(expansion_state)

            remaining = [(j, state_spy_mean[j]) for j in range(n_states) if j not in used]
            if remaining:
                correction_state = min(remaining, key=lambda x: x[1])[0]
                state_labels[correction_state] = "Correction"
                used.add(correction_state)

            for j in range(n_states):
                if j not in used:
                    state_labels[j] = "Inflation"

            current_regime = state_labels.get(current_state, "Unknown")

            probabilities = {}
            for state_idx, label in state_labels.items():
                probabilities[label] = float(current_probs[state_idx])

            risk_score = (
                probabilities.get("Liquidity Crisis", 0) * 1.0
                + probabilities.get("Correction", 0) * 0.7
                + probabilities.get("Inflation", 0) * 0.3
                + probabilities.get("Expansion", 0) * 0.0
            )

            prob_str = "  ".join(f"{k[:4]}={v:.2f}" for k, v in sorted(probabilities.items()))
            print(f"  random_state={rs:<5d}  |  {current_regime:<20s}  |  score={risk_score:.4f}  |  {prob_str}")

            # Also track last 5 states for sequence comparison
            last5_regimes = [state_labels.get(s, "?") for s in hidden_states[-5:]]

            results.append({
                "random_state": rs,
                "regime": current_regime,
                "score": round(risk_score, 4),
                "probabilities": probabilities,
                "log_likelihood": model.score(features_scaled),
                "last5": last5_regimes,
            })

        except Exception as e:
            print(f"  random_state={rs:<5d}  |  ERROR: {e}")
            results.append({"random_state": rs, "regime": "Error", "score": -1})

    # Analyze agreement
    regimes = [r["regime"] for r in results if r["regime"] != "Error"]
    unique_regimes = set(regimes)
    majority = max(set(regimes), key=regimes.count) if regimes else "N/A"
    agreement = regimes.count(majority) / len(regimes) if regimes else 0

    print()
    print(f"  Unique regimes across 5 seeds: {unique_regimes}")
    print(f"  Majority regime: {majority} ({regimes.count(majority)}/5 agree)")
    print(f"  Agreement ratio: {agreement:.0%}")
    print()

    # Print last-5-day state sequences
    print("  Last 5 days state sequence by random_state:")
    for r in results:
        if "last5" in r:
            seq = " -> ".join(r["last5"])
            print(f"    rs={r['random_state']:<5d}:  {seq}")

    print()
    return results, agreement


def main():
    print()
    print("*" * 70)
    print("  HMM Regime Detection Stability Test")
    print("*" * 70)
    print()

    config = load_config()
    tickers = get_v2_tickers(config)
    print(f"Fetching market data ({len(tickers)} tickers, period=2y)...")
    close = fetch_market_data(tickers=tickers, period="2y")

    if close.empty:
        print("ERROR: Failed to fetch data.")
        return

    print(f"Data range: {close.index[0].strftime('%Y-%m-%d')} ~ {close.index[-1].strftime('%Y-%m-%d')}")
    print(f"Tickers fetched: {len(close.columns)}")
    print()

    # Test 1: Temporal stability
    temporal_results, transitions = run_temporal_stability_test(close, config)

    # Test 2: Random state sensitivity
    rs_results, agreement = run_random_state_sensitivity_test(close, config)

    # Summary
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print()
    print(f"  Temporal stability:")
    print(f"    - Regime flips in 20 consecutive days: {transitions}")
    print(f"    - Stability: {'STABLE' if transitions <= 2 else 'MODERATE' if transitions <= 5 else 'UNSTABLE'}")
    print()
    print(f"  Initialization sensitivity:")
    print(f"    - Agreement across 5 random seeds: {agreement:.0%}")
    print(f"    - Sensitivity: {'LOW (good)' if agreement >= 0.8 else 'MODERATE' if agreement >= 0.6 else 'HIGH (bad)'}")
    print()

    if transitions <= 2 and agreement >= 0.8:
        print("  OVERALL: HMM regime detection is STABLE.")
    elif transitions <= 5 and agreement >= 0.6:
        print("  OVERALL: HMM regime detection has MODERATE stability.")
        print("  Consider: ensemble averaging, longer lookback, or regime smoothing.")
    else:
        print("  OVERALL: HMM regime detection is UNSTABLE.")
        print("  Recommendations:")
        print("    1. Apply temporal smoothing (e.g., require N consecutive days in new regime)")
        print("    2. Ensemble multiple random seeds and take majority vote")
        print("    3. Increase lookback_years to give HMM more training data")
        print("    4. Reduce n_states from 4 to 3 for fewer ambiguous boundaries")
    print()


if __name__ == "__main__":
    main()
