"""
tests/hmm_tuning.py — HMM 파라미터 그리드 서치

평가 지표:
  1. Crisis 감지율: 2020 COVID, 2022 Bear 고점 전후 구간에서 Crisis/Correction 확률 합
  2. Expansion 정확도: 2019 Bull 구간에서 Expansion 확률
  3. Regime 안정성: 전체 기간 일평균 regime 전환 횟수 (낮을수록 좋음)
  4. Log-likelihood: HMM 모델 적합도 (높을수록 좋음)
"""

import sys
import io
import warnings
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import yaml

from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler

from data.fetcher import fetch_market_data
from main_v2 import get_v2_tickers
from regime.regime_model import _prepare_features, _label_states


def load_config():
    with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── 평가 구간 정의 ────────────────────────────────────────────────
CRISIS_PERIODS = [
    ("2020 COVID",   "2020-01-01", "2020-04-30"),
    ("2022 Bear",    "2022-01-01", "2022-06-30"),
]
BULL_PERIODS = [
    ("2019 Bull",    "2019-01-01", "2019-12-31"),
    ("2021 Bull",    "2021-01-01", "2021-09-30"),
]

GRID = {
    "n_components":    [3, 4, 5],
    "covariance_type": ["full", "diag"],
    "window_years":    [None, 10, 5],   # None = 전체 데이터
}


def run_hmm(features_scaled: np.ndarray, n_components: int,
            covariance_type: str, random_state: int = 42):
    model = GaussianHMM(
        n_components=n_components,
        covariance_type=covariance_type,
        n_iter=300,
        random_state=random_state,
        verbose=False,
    )
    model.fit(features_scaled)
    hidden_states = model.predict(features_scaled)
    state_probs   = model.predict_proba(features_scaled)
    score         = model.score(features_scaled)
    return model, hidden_states, state_probs, score


def evaluate(features: pd.DataFrame, features_scaled: np.ndarray,
             model, hidden_states, state_probs, n_components) -> dict:
    """각 평가 지표 계산."""
    state_labels = _label_states(model, features_scaled, n_components, [])

    # regime 시리즈
    regime_series = pd.Series(
        [state_labels.get(s, "Unknown") for s in hidden_states],
        index=features.index
    )

    # 1) Crisis 감지율: 위기 구간에서 Crisis+Correction 확률 평균
    crisis_scores = []
    for name, start, end in CRISIS_PERIODS:
        mask = (features.index >= start) & (features.index <= end)
        if mask.sum() == 0:
            continue
        probs = state_probs[mask]
        # Crisis/Correction에 해당하는 상태 인덱스 찾기
        crisis_idx = [i for i, l in state_labels.items() if l in ("Liquidity Crisis", "Correction")]
        if not crisis_idx:
            continue
        danger_prob = probs[:, crisis_idx].sum(axis=1).mean()
        crisis_scores.append(danger_prob)
    crisis_rate = np.mean(crisis_scores) if crisis_scores else 0.0

    # 2) Expansion 정확도: Bull 구간에서 Expansion 확률 평균
    bull_scores = []
    for name, start, end in BULL_PERIODS:
        mask = (features.index >= start) & (features.index <= end)
        if mask.sum() == 0:
            continue
        probs = state_probs[mask]
        exp_idx = [i for i, l in state_labels.items() if l == "Expansion"]
        if not exp_idx:
            continue
        exp_prob = probs[:, exp_idx].sum(axis=1).mean()
        bull_scores.append(exp_prob)
    expansion_rate = np.mean(bull_scores) if bull_scores else 0.0

    # 3) Regime 안정성: 하루 평균 전환 횟수
    transitions = (regime_series != regime_series.shift()).sum()
    stability   = 1.0 - (transitions / len(regime_series))  # 높을수록 안정

    return {
        "crisis_rate":     round(crisis_rate, 4),
        "expansion_rate":  round(expansion_rate, 4),
        "stability":       round(stability, 4),
    }


def composite_score(metrics: dict, log_lik: float, n_data: int) -> float:
    """
    종합 점수 (높을수록 좋음):
      crisis_rate 40% + expansion_rate 30% + stability 20% + normalized log-lik 10%
    """
    norm_lik = max(0.0, min(1.0, (log_lik / n_data + 3) / 6))  # [-3,3] → [0,1] 근사
    return (
        0.40 * metrics["crisis_rate"]
        + 0.30 * metrics["expansion_rate"]
        + 0.20 * metrics["stability"]
        + 0.10 * norm_lik
    )


# ── 메인 ─────────────────────────────────────────────────────────
def run_tuning():
    print("=" * 70)
    print("  HMM 파라미터 그리드 서치")
    print("=" * 70)

    config = load_config()
    tickers = get_v2_tickers(config)

    print("\n데이터 수집 중 (max period)...\n")
    close_all = fetch_market_data(tickers=tickers, period="max")

    features_all = _prepare_features(close_all)
    print(f"전체 피처 데이터: {features_all.index[0].date()} ~ {features_all.index[-1].date()} ({len(features_all)}일)\n")

    results = []

    total = (len(GRID["n_components"])
             * len(GRID["covariance_type"])
             * len(GRID["window_years"]))
    done = 0

    print(f"{'#':<4} {'n':>3} {'cov':<6} {'window':<8} {'crisis':>8} {'expansion':>10} {'stability':>10} {'log-lik':>10} {'composite':>10}")
    print("-" * 70)

    for n_comp in GRID["n_components"]:
        for cov in GRID["covariance_type"]:
            for window in GRID["window_years"]:
                done += 1

                # window 적용
                if window is not None:
                    cutoff = features_all.index[-1] - pd.DateOffset(years=window)
                    features = features_all[features_all.index >= cutoff]
                else:
                    features = features_all

                if len(features) < 200:
                    print(f"{done:<4} {n_comp:>3} {cov:<6} {str(window)+'y':<8}  데이터 부족")
                    continue

                scaler = StandardScaler()
                features_scaled = scaler.fit_transform(features.values)

                try:
                    model, hidden_states, state_probs, log_lik = run_hmm(
                        features_scaled, n_comp, cov
                    )
                except Exception as e:
                    print(f"{done:<4} {n_comp:>3} {cov:<6} {str(window)+'y':<8}  오류: {e}")
                    continue

                metrics = evaluate(features, features_scaled, model,
                                   hidden_states, state_probs, n_comp)
                comp    = composite_score(metrics, log_lik, len(features))
                win_str = f"{window}y" if window else "all"

                print(f"{done:<4} {n_comp:>3} {cov:<6} {win_str:<8}"
                      f"  {metrics['crisis_rate']:>7.3f}"
                      f"  {metrics['expansion_rate']:>9.3f}"
                      f"  {metrics['stability']:>9.3f}"
                      f"  {log_lik/len(features):>9.2f}"
                      f"  {comp:>9.3f}")

                results.append({
                    "n": n_comp, "cov": cov, "window": win_str,
                    **metrics, "log_lik_per_day": round(log_lik / len(features), 3),
                    "composite": round(comp, 4),
                })

    # ── 최종 순위 ─────────────────────────────────────────────
    if not results:
        print("\n결과 없음")
        return

    results.sort(key=lambda x: x["composite"], reverse=True)

    print(f"\n\n{'='*70}")
    print("  최종 순위 (composite score 기준)")
    print(f"{'='*70}")
    print(f"{'순위':<5} {'n':>3} {'cov':<6} {'window':<8} {'crisis':>8} {'expansion':>10} {'stability':>10} {'composite':>10}")
    print("-" * 60)
    for rank, r in enumerate(results[:5], 1):
        print(f"{rank:<5} {r['n']:>3} {r['cov']:<6} {r['window']:<8}"
              f"  {r['crisis_rate']:>7.3f}"
              f"  {r['expansion_rate']:>9.3f}"
              f"  {r['stability']:>9.3f}"
              f"  {r['composite']:>9.3f}")

    best = results[0]
    print(f"\n  Best: n_components={best['n']}, covariance_type={best['cov']}, window={best['window']}")
    print(f"        composite={best['composite']:.4f}")


if __name__ == "__main__":
    run_tuning()
