"""
regime/regime_model.py — Market Regime Detection (HMM)

Hidden Markov Model을 사용하여 시장 상태를 자동 분류합니다:
  - Expansion (확장)
  - Inflation (인플레이션)
  - Correction (조정)
  - Liquidity Crisis (유동성 위기)
"""

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

try:
    from hmmlearn.hmm import GaussianHMM
    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False

from sklearn.preprocessing import StandardScaler


def _prepare_features(close: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """HMM 피처를 준비합니다."""
    features = pd.DataFrame(index=close.index)

    # 1) SPY 20일 수익률
    if "SPY" in close.columns:
        features["spy_return"] = close["SPY"].pct_change(period)

    # 2) VIX 수준
    if "^VIX" in close.columns:
        features["vix"] = close["^VIX"]

    # 3) Yield Spread — ^TNX(10Y) - ^FVX(5Y), fallback으로 ^TNX(10Y) - ^IRX(3M)
    if "^TNX" in close.columns and "^FVX" in close.columns:
        features["yield_spread"] = close["^TNX"] - close["^FVX"]
    elif "^TNX" in close.columns and "^IRX" in close.columns:
        features["yield_spread"] = close["^TNX"] - close["^IRX"]

    # 4) Credit Spread (HYG/LQD 비율 변화)
    if "HYG" in close.columns and "LQD" in close.columns:
        ratio = close["HYG"] / close["LQD"]
        features["credit"] = ratio.pct_change(period)

    # 5) Dollar 변화율
    for dollar_ticker in ["DX-Y.NYB", "UUP"]:
        if dollar_ticker in close.columns:
            features["dollar"] = close[dollar_ticker].pct_change(period)
            break

    # 6) Oil 변화율
    for oil_ticker in ["CL=F", "DBC"]:
        if oil_ticker in close.columns:
            features["oil"] = close[oil_ticker].pct_change(period)
            break

    return features.dropna()


def _label_states(model, features_scaled: np.ndarray, n_states: int,
                  labels: list[str]) -> dict[int, str]:
    """
    HMM이 발견한 상태를 의미 있는 라벨에 매핑합니다.
    각 상태의 평균 피처값을 기반으로 판별합니다.
    """
    means = model.means_  # (n_states, n_features)

    # spy_return(col 0)이 큰 순서로 정렬
    state_spy_mean = means[:, 0] if means.shape[1] > 0 else np.zeros(n_states)
    state_vix_mean = means[:, 1] if means.shape[1] > 1 else np.zeros(n_states)

    # 규칙 기반 매핑
    state_labels = {}
    used = set()

    # Crisis = VIX 가장 높은 상태
    crisis_state = int(np.argmax(state_vix_mean))
    state_labels[crisis_state] = "Liquidity Crisis"
    used.add(crisis_state)

    # Expansion = SPY 수익률 가장 높은 상태 (Crisis 제외)
    remaining_spy = [(i, state_spy_mean[i]) for i in range(n_states) if i not in used]
    expansion_state = max(remaining_spy, key=lambda x: x[1])[0]
    state_labels[expansion_state] = "Expansion"
    used.add(expansion_state)

    # Correction = SPY 수익률 가장 낮은 상태 (사용된 것 제외)
    remaining_spy = [(i, state_spy_mean[i]) for i in range(n_states) if i not in used]
    if remaining_spy:
        correction_state = min(remaining_spy, key=lambda x: x[1])[0]
        state_labels[correction_state] = "Correction"
        used.add(correction_state)

    # Inflation = 남는 상태
    for i in range(n_states):
        if i not in used:
            state_labels[i] = "Inflation"

    return state_labels


def detect_regime(close: pd.DataFrame, config: dict) -> dict:
    """
    HMM을 사용하여 현재 시장 체제를 탐지합니다.

    Args:
        close: 종가 DataFrame
        config: regime 설정

    Returns:
        {
            "regime": str (Expansion/Inflation/Correction/Liquidity Crisis),
            "probabilities": dict (각 체제별 확률),
            "score": float (위험 수준 0~1),
            "detail": str,
        }
    """
    regime_cfg = config.get("regime", {})
    n_states = regime_cfg.get("n_states", 4)
    labels = regime_cfg.get("labels", ["Expansion", "Inflation", "Correction", "Liquidity Crisis"])

    if not HMM_AVAILABLE:
        return {
            "regime": "Unknown",
            "probabilities": {},
            "score": 0.5,
            "detail": "HMM 미설치 (pip install hmmlearn)",
        }

    # 피처 준비
    features = _prepare_features(close)
    if len(features) < 100:
        return {
            "regime": "Unknown",
            "probabilities": {},
            "score": 0.5,
            "detail": f"데이터 부족 ({len(features)}일, 최소 100일 필요)",
        }

    # 스케일링
    scaler = StandardScaler()
    features_scaled = scaler.fit_transform(features.values)

    # HMM 학습
    try:
        model = GaussianHMM(
            n_components=n_states,
            covariance_type="full",
            n_iter=200,
            random_state=42,
            verbose=False,
        )
        model.fit(features_scaled)

        # 전체 시퀀스에 대한 상태 예측
        hidden_states = model.predict(features_scaled)
        state_probs = model.predict_proba(features_scaled)

        # 현재 상태
        current_state = hidden_states[-1]
        current_probs = state_probs[-1]

        # 상태 라벨링
        state_labels = _label_states(model, features_scaled, n_states, labels)
        current_regime = state_labels.get(current_state, "Unknown")

        # 확률 딕셔너리
        probabilities = {}
        for state_idx, label in state_labels.items():
            probabilities[label] = float(current_probs[state_idx])

        # 위험 스코어 (Crisis + Correction 확률 기반)
        risk_score = (
            probabilities.get("Liquidity Crisis", 0) * 1.0
            + probabilities.get("Correction", 0) * 0.7
            + probabilities.get("Inflation", 0) * 0.3
            + probabilities.get("Expansion", 0) * 0.0
        )

        return {
            "regime": current_regime,
            "probabilities": probabilities,
            "score": round(min(risk_score, 1.0), 4),
            "detail": f"Regime: {current_regime} (prob={probabilities.get(current_regime, 0):.0%})",
        }

    except Exception as e:
        return {
            "regime": "Unknown",
            "probabilities": {},
            "score": 0.5,
            "detail": f"HMM 오류: {e}",
        }
