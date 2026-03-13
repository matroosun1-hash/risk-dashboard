"""
대시보드 V2 — System Status Display
📱 폰 모드: 게이지 + 시그널 바 (자동 새로고침 60s)
💻 분석 모드: 상세 지표 + 차트 + 포지션
streamlit run dashboard/app_v2.py
"""

import sys
import io
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import streamlit.components.v1 as stc
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import yaml

from data.fetcher import fetch_market_data
from risk.risk_engine import calculate_final_risk
from risk.position_sizing import calculate_position_sizing
from portfolio.allocator import generate_portfolio_action

st.set_page_config(
    page_title="QUANT RISK // STATUS",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed",
)


def load_config():
    with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@st.cache_data(ttl=1800)
def load_data(period: str):
    from main_v2 import get_v2_tickers
    config = load_config()
    tickers = get_v2_tickers(config)
    return fetch_market_data(tickers=tickers, period=period)


# ── 헬퍼 ──────────────────────────────────────────────────────
def level_name(level: int) -> str:
    return {0: "정상", 1: "주의", 2: "경고", 3: "위험", 4: "극도위험"}.get(level, "")

def action_text(level: int) -> str:
    if level >= 4: return "성장주 전량 매도 · 즉각 대피"
    if level == 3: return "방어 배분 · 현금 확보"
    if level == 2: return "신규 매수 자제 · 포지션 축소"
    if level == 1: return "시장 모니터링 강화"
    return "정상 투자 구간"

def bar_color(score: float) -> str:
    if score >= 0.8: return "#ff2a2a"
    if score >= 0.6: return "#ff9e00"
    if score >= 0.4: return "#fadd00"
    if score >= 0.2: return "#7ecf7e"
    return "#00ff88"

def score_to_level(score: float) -> int:
    if score >= 0.8: return 4
    if score >= 0.6: return 3
    if score >= 0.45: return 2
    if score >= 0.2: return 1
    return 0


# ── CSS ──────────────────────────────────────────────────────
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Inter:wght@400;600;700&display=swap');

* { box-sizing: border-box; }
#MainMenu, header, footer { visibility: hidden; }
.stDeployButton { display: none; }
section[data-testid="stMain"] > div:first-child { padding-top: 0.5rem !important; }

.stApp {
    background-color: #08080c;
    background-image:
        radial-gradient(circle at 15% 50%, rgba(20,10,40,0.4), transparent 25%),
        radial-gradient(circle at 85% 30%, rgba(10,30,40,0.3), transparent 25%);
    font-family: 'Inter', sans-serif;
    color: #e0e0e0;
}

/* ── 폰 모드 레이아웃 ── */
.layout { display: flex; flex-direction: column; gap: 1rem; }

.status-card {
    background: rgba(15,15,22,0.9); border-radius: 20px;
    padding: 2.5rem 2rem; text-align: center;
    backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.06);
}

.signals-card {
    background: rgba(15,15,22,0.9); border-radius: 20px;
    padding: 1.5rem; backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.06);
}

.signals-title {
    font-family: 'Orbitron', sans-serif; font-size: 0.7rem;
    letter-spacing: 3px; color: #666; text-transform: uppercase; margin: 0 0 1rem 0;
}

.sig-row { display: flex; align-items: center; gap: 0.8rem; margin-bottom: 0.7rem; }
.sig-name {
    font-family: 'Orbitron', sans-serif; font-size: 0.65rem;
    letter-spacing: 1px; color: #aaa; width: 120px; flex-shrink: 0;
}
.sig-bar-bg { flex: 1; height: 8px; background: rgba(255,255,255,0.07); border-radius: 4px; overflow: hidden; }
.sig-bar { height: 100%; border-radius: 4px; transition: width 0.6s ease; }
.sig-val { font-size: 0.8rem; font-weight: 700; width: 32px; text-align: right; flex-shrink: 0; }

/* ── 사용자 모드 ── */
.detail-card {
    background: rgba(15,15,22,0.9); border-radius: 16px;
    padding: 1.2rem 1.5rem; margin-bottom: 0.8rem;
    border: 1px solid rgba(255,255,255,0.06);
}
.detail-title {
    font-family: 'Orbitron', sans-serif; font-size: 0.65rem;
    letter-spacing: 2px; color: #666; text-transform: uppercase; margin: 0 0 0.8rem 0;
}
.ind-row {
    display: flex; align-items: center; gap: 0.6rem;
    padding: 0.5rem 0.8rem; margin: 3px 0; border-radius: 8px; font-size: 0.88rem;
}
.ind-name { font-weight: 600; flex: 0 0 auto; }
.ind-detail { color: #888; font-size: 0.82rem; flex: 1; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ind-score { font-weight: 700; flex: 0 0 auto; }

.ts {
    text-align: center; color: #444; font-size: 0.72rem;
    margin-top: 0.5rem; font-family: 'Orbitron', sans-serif; letter-spacing: 1px;
}

/* ══ 폰 세로: 시그널 숨김 ══ */
@media (orientation: portrait) { .signals-card { display: none; } }

/* ══ 폰 가로: 나란히 ══ */
@media (orientation: landscape) {
    .layout { flex-direction: row; align-items: stretch; }
    .status-card  { flex: 1; padding: 1.5rem 1.2rem; }
    .signals-card { flex: 1; display: block; }
}

/* ══ 데스크탑 ══ */
@media (min-width: 1024px) {
    .layout { flex-direction: row; align-items: stretch; }
    .status-card  { flex: 1; }
    .signals-card { flex: 1; display: block !important; }
}
</style>
""", unsafe_allow_html=True)


# ── 모드 선택 (query param 기반 — 새로고침 후에도 유지) ────────
mode = st.query_params.get("mode", "phone")

c1, c2, _ = st.columns([1, 1, 5])
with c1:
    if st.button("📱 폰 모드", use_container_width=True,
                 type="primary" if mode == "phone" else "secondary"):
        st.query_params["mode"] = "phone"
        st.rerun()
with c2:
    if st.button("💻 분석 모드", use_container_width=True,
                 type="primary" if mode == "user" else "secondary"):
        st.query_params["mode"] = "user"
        st.rerun()


def calc_score_history(close: pd.DataFrame, days: int = 60) -> pd.Series:
    """
    과거 N일간의 일별 리스크 프록시 점수를 빠르게 계산합니다.
    VIX 퍼센타일, 크레딧 스트레스, SPY vs 200MA, 달러 강세 4개 지표 가중 평균.
    """
    idx = close.index
    result = pd.Series(index=idx, dtype=float)

    # 1) VIX 252일 롤링 퍼센타일 (가중 35%)
    if "^VIX" in close.columns:
        vix = close["^VIX"].dropna()
        vix_pct = vix.rolling(252, min_periods=60).rank(pct=True)
        result = vix_pct.reindex(idx) * 0.35

    # 2) HYG/LQD 20일 변화 → 0~1 (가중 25%)
    if "HYG" in close.columns and "LQD" in close.columns:
        ratio = (close["HYG"] / close["LQD"]).dropna()
        change = ratio.pct_change(20)
        # 하락(-5%~0%)을 0~1로 매핑
        credit_score = np.clip(-change / 0.05, 0, 1)
        result = result.add(credit_score.reindex(idx).fillna(0) * 0.25, fill_value=0)

    # 3) SPY vs 200MA 거리 → 0~1 (가중 25%)
    if "SPY" in close.columns:
        spy = close["SPY"].dropna()
        sma200 = spy.rolling(200, min_periods=100).mean()
        gap = (spy - sma200) / sma200  # 양수=위 / 음수=아래
        # -10%~0% 구간을 0~1로 매핑 (아래로 내려갈수록 위험)
        spy_score = np.clip(-gap / 0.10, 0, 1)
        result = result.add(spy_score.reindex(idx).fillna(0.5) * 0.25, fill_value=0)

    # 4) 달러 20일 변화 → 0~1 (가중 15%)
    for dollar in ["UUP", "DX-Y.NYB"]:
        if dollar in close.columns:
            uup = close[dollar].dropna()
            uup_chg = uup.pct_change(20)
            dollar_score = np.clip(uup_chg / 0.04, 0, 1)
            result = result.add(dollar_score.reindex(idx).fillna(0) * 0.15, fill_value=0)
            break

    result = result.clip(0, 1)
    # 오늘 실제 점수로 마지막 값 보정
    return result.dropna().tail(days)


# ── 데이터 로드 & 계산 (두 모드 공통) ─────────────────────────
with st.spinner("⚡ 퀀트 엔진 로딩 중..."):
    config      = load_config()
    close       = load_data("2y")

if close.empty:
    st.error("데이터 수신 오류")
    st.stop()

risk_result  = calculate_final_risk(close, config)
sizing       = calculate_position_sizing(risk_result["final_score"], close, config)
action       = generate_portfolio_action(risk_result, sizing, config)
score_history = calc_score_history(close, days=60)
# 마지막 값을 실제 엔진 점수로 보정
if not score_history.empty:
    score_history.iloc[-1] = risk_result["final_score"]

final_score = risk_result["final_score"]
level       = score_to_level(final_score)
data_date   = close.index[-1].strftime("%Y-%m-%d")
signals     = risk_result.get("signals", {})

# ── 공통: 게이지 차트 ────────────────────────────────────────
gauge_colors = {0: "#00ff88", 1: "#fadd00", 2: "#fadd00", 3: "#ff9e00", 4: "#ff2a2a"}
fig_gauge = go.Figure(go.Indicator(
    mode="gauge+number",
    value=final_score,
    number={"font": {"color": "#e0e0e0", "family": "Orbitron"}, "suffix": ""},
    gauge={
        "axis": {"range": [0, 1], "tickwidth": 1, "tickcolor": "rgba(255,255,255,0.2)"},
        "bar": {"color": gauge_colors.get(level, "#e0e0e0"), "thickness": 0.25},
        "bgcolor": "rgba(0,0,0,0)",
        "borderwidth": 0,
        "steps": [
            {"range": [0.0, 0.2], "color": "rgba(0,255,136,0.25)"},
            {"range": [0.2, 0.4], "color": "rgba(250,221,0,0.25)"},
            {"range": [0.4, 0.6], "color": "rgba(255,158,0,0.25)"},
            {"range": [0.6, 0.8], "color": "rgba(255,42,42,0.25)"},
            {"range": [0.8, 1.0], "color": "rgba(100,0,0,0.5)"},
        ],
    }
))
fig_gauge.update_layout(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=260,
    margin=dict(t=20, b=0, l=20, r=20),
)

# ── 신호명 한국어 번역 ────────────────────────────────────────
SIG_KO = {
    "macro":        "거시경제",
    "liquidity":    "유동성",
    "breadth":      "시장폭",
    "volatility":   "변동성",
    "cross_asset":  "교차자산",
    "regime":       "시장국면",
    "global_macro": "글로벌거시",
}

REGIME_KO = {
    "Expansion":       "확장",
    "Inflation":       "인플레이션",
    "Correction":      "조정",
    "Liquidity Crisis":"유동성위기",
    "Unknown":         "미확인",
}

ALLOC_KO = {
    "equity":   "주식",
    "treasury": "국채",
    "gold":     "금",
    "cash":     "현금",
}

# ── 공통: 시그널 바 HTML ─────────────────────────────────────
signals_html = ""
for sig_name, info in risk_result["signal_summary"].items():
    s = info.get("score", 0)
    w = info.get("weight", 0)
    color = bar_color(s)
    ko = SIG_KO.get(sig_name, "")
    label = f'{sig_name.upper()}<span style="color:#666;font-size:0.6rem;margin-left:3px;">({ko})</span>'
    signals_html += (
        f'<div class="sig-row">'
        f'<span class="sig-name">{label}'
        f'<span style="color:#555;font-size:0.58rem;margin-left:4px;">{w:.0%}</span></span>'
        f'<div class="sig-bar-bg"><div class="sig-bar" style="width:{int(s*100)}%;background:{color};"></div></div>'
        f'<span class="sig-val" style="color:{color};">{s:.2f}</span>'
        f'</div>'
    )


# ══════════════════════════════════════════════════════════════
# 📱 폰 모드
# ══════════════════════════════════════════════════════════════
if mode == "phone":
    st.plotly_chart(fig_gauge, use_container_width=True)

    st.markdown(
        f'<div class="signals-card">'
        f'<p class="signals-title">Signal Breakdown (신호 분석)</p>'
        f'{signals_html}'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown(f'<p class="ts">DATA: {data_date} // AUTO REFRESH 60s</p>', unsafe_allow_html=True)

    # JS 자동 새로고침 (60초, query param 유지)
    stc.html('<script>setTimeout(() => window.location.reload(), 60000);</script>', height=0)


# ══════════════════════════════════════════════════════════════
# 💻 분석 모드
# ══════════════════════════════════════════════════════════════
else:
    # 새로고침 버튼
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()

    # 게이지
    st.plotly_chart(fig_gauge, use_container_width=True)

    # 레벨 요약
    lc = gauge_colors.get(level, "#e0e0e0")
    st.markdown(
        f'<div style="text-align:center;margin-bottom:1.5rem;">'
        f'<span style="font-family:Orbitron;font-size:1.6rem;color:{lc};font-weight:900;">'
        f'L{level} {level_name(level)}</span>'
        f'<br><span style="color:#888;font-size:0.9rem;">{action_text(level)}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── 레벨 추이 차트 (60일) ────────────────────────────────
    if not score_history.empty:
        fig_hist = go.Figure()

        # 배경 레벨 구간
        level_bands = [
            (0.0,  0.2,  "rgba(0,255,136,0.06)",  "정상"),
            (0.2,  0.45, "rgba(250,221,0,0.06)",   "주의"),
            (0.45, 0.6,  "rgba(255,158,0,0.08)",   "경고"),
            (0.6,  0.8,  "rgba(255,42,42,0.08)",   "위험"),
            (0.8,  1.0,  "rgba(100,0,0,0.15)",     "극도위험"),
        ]
        for y0, y1, color, label in level_bands:
            fig_hist.add_hrect(y0=y0, y1=y1, fillcolor=color, line_width=0,
                               annotation_text=label,
                               annotation_position="left",
                               annotation_font=dict(size=9, color="rgba(255,255,255,0.3)"))

        # L2 임계선
        fig_hist.add_hline(y=0.45, line_dash="dot", line_color="rgba(255,158,0,0.5)",
                           line_width=1)

        # 점수 선
        colors_line = [bar_color(s) for s in score_history.values]
        fig_hist.add_trace(go.Scatter(
            x=score_history.index,
            y=score_history.values,
            mode="lines",
            line=dict(color="#4fc3f7", width=2),
            fill="tozeroy",
            fillcolor="rgba(79,195,247,0.07)",
            name="Risk Score",
            hovertemplate="%{x|%m/%d}<br>Score: %{y:.3f}<extra></extra>",
        ))

        # 현재 점수 마커
        fig_hist.add_trace(go.Scatter(
            x=[score_history.index[-1]],
            y=[score_history.values[-1]],
            mode="markers",
            marker=dict(size=10, color=bar_color(score_history.values[-1]),
                        line=dict(width=2, color="white")),
            name="현재",
            hovertemplate="현재: %{y:.3f}<extra></extra>",
        ))

        fig_hist.update_layout(
            title=dict(text="리스크 레벨 추이 (최근 60일)", font=dict(size=13, color="#aaa")),
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=220,
            margin=dict(l=40, r=20, t=40, b=20),
            yaxis=dict(range=[0, 1], tickvals=[0, 0.2, 0.45, 0.6, 0.8, 1.0],
                       tickfont=dict(size=10)),
            xaxis=dict(tickfont=dict(size=10)),
            showlegend=False,
        )
        st.plotly_chart(fig_hist, use_container_width=True)

    # ── Regime 배너 ──────────────────────────────────────────
    regime_info   = risk_result.get("regime", {})
    hmm_regime    = regime_info.get("regime", "Unknown")
    regime_detail = risk_result.get("signals", {}).get("regime", {}).get("detail", "")
    corroborated  = "[corroboration cap]" in regime_detail

    regime_colors = {
        "Expansion":       "#44bb44",
        "Inflation":       "#fadd00",
        "Correction":      "#ff9e00",
        "Liquidity Crisis":"#ff2a2a",
    }
    rc = regime_colors.get(hmm_regime, "#888")
    corr_badge = (
        '<span style="background:rgba(255,170,0,0.2);color:#ffaa00;'
        'font-size:0.7rem;padding:2px 8px;border-radius:10px;margin-left:8px;">'
        '⚠ Crisis 강등됨</span>'
        if corroborated else ""
    )
    st.markdown(
        f'<div class="detail-card" style="margin-bottom:0.5rem;padding:0.8rem 1.2rem;">'
        f'<span style="color:#666;font-size:0.7rem;letter-spacing:2px;font-family:Orbitron;">REGIME(시장국면)&nbsp;&nbsp;</span>'
        f'<span style="font-family:Orbitron;font-size:0.95rem;color:{rc};font-weight:700;">{hmm_regime}({REGIME_KO.get(hmm_regime,"")})</span>'
        f'{corr_badge}'
        f'<span style="color:#555;font-size:0.75rem;margin-left:12px;">→ 동적 가중치 적용중</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # 시그널 요약 바
    st.markdown(
        f'<div class="detail-card"><p class="detail-title">Signal Overview(신호 개요) — score / weight(%)</p>'
        f'{signals_html}</div>',
        unsafe_allow_html=True,
    )

    # ── 탭 ──────────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["📊 상세 지표", "📈 차트", "💼 포지션 배분"])

    # ── 탭 1: 신호 상세 ──────────────────────────────────
    with tab1:
        # Macro: Stage1 10개 지표
        macro_sig = signals.get("macro", {})
        indicators = macro_sig.get("indicators", [])
        if indicators:
            st.markdown("#### Macro — Stage1 지표 (VIX 제외 9개)")
            for ind in indicators:
                sc = ind.get("score", 0)
                if sc >= 1:
                    color, bg, icon = "#ff4444", "rgba(255,68,68,0.1)", "🔴"
                elif sc > 0:
                    color, bg, icon = "#ffaa00", "rgba(255,170,0,0.1)", "🟡"
                else:
                    color, bg, icon = "#44bb44", "rgba(68,187,68,0.1)", "🟢"
                st.markdown(
                    f'<div class="ind-row" style="background:{bg};border-left:4px solid {color};">'
                    f'<span class="ind-name">{icon} {ind["name"]}</span>'
                    f'<span class="ind-detail">{ind.get("detail","")}</span>'
                    f'<span class="ind-score" style="color:{color};">{sc:.1f}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # 컴포넌트 있는 신호들 (score/value/note 구조)
        comp_signals = {
            "liquidity":    "Liquidity(유동성 스트레스)",
            "breadth":      "Market Breadth(시장폭)",
            "volatility":   "Volatility(변동성)",
            "global_macro": "Global Macro(글로벌 거시)",
        }
        for key, label in comp_signals.items():
            sig = signals.get(key, {})
            sub = sig.get("components", [])
            if not sub:
                continue
            st.markdown(f"#### {label}")
            for comp in sub:
                sc = comp.get("score", 0)
                color = bar_color(sc)
                val  = comp.get("value", "")
                note = comp.get("note", "")
                st.markdown(
                    f'<div class="ind-row" style="background:rgba(255,255,255,0.03);border-left:4px solid {color};">'
                    f'<span class="ind-name" style="color:{color};">{comp.get("name","")}</span>'
                    f'<span class="ind-detail">{val}&nbsp;&nbsp;{note}</span>'
                    f'<span class="ind-score" style="color:{color};">{sc:.2f}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # Cross-Asset (별도 구조: triggered/intensity/asset_a/asset_b/desc)
        cross_sig = signals.get("cross_asset", {})
        cross_comps = cross_sig.get("components", [])
        if cross_comps:
            st.markdown("#### Cross Asset(교차자산 괴리)")
            for comp in cross_comps:
                triggered = comp.get("triggered", False)
                intensity = comp.get("intensity", 0.0)
                color = "#ff4444" if triggered else "#44bb44"
                bg    = "rgba(255,68,68,0.08)" if triggered else "rgba(255,255,255,0.02)"
                icon  = "🔴" if triggered else "🟢"
                asset_a = comp.get("asset_a", "")
                asset_b = comp.get("asset_b", "")
                desc    = comp.get("desc", "")
                intensity_str = f"강도: {intensity:.3f}" if triggered else "미발동"
                st.markdown(
                    f'<div class="ind-row" style="background:{bg};border-left:4px solid {color};">'
                    f'<span class="ind-name" style="color:{color};">{icon} {comp.get("name","")}</span>'
                    f'<span class="ind-detail">{asset_a} / {asset_b}&nbsp;&nbsp;{desc}</span>'
                    f'<span class="ind-score" style="color:{color};font-size:0.78rem;">{intensity_str}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # Regime
        regime = signals.get("regime", {})
        if regime:
            reg_name   = regime.get("regime", "Unknown")
            reg_detail = regime.get("detail", "")
            reg_probs  = regime.get("probabilities", {})
            is_capped  = "[corroboration cap]" in reg_detail
            rc2        = regime_colors.get(reg_name, "#888")
            st.markdown("#### Regime Detection(시장국면 감지) — HMM")

            # 확률 바
            prob_html = ""
            for rname, rprob in sorted(reg_probs.items(), key=lambda x: -x[1]):
                rc3 = regime_colors.get(rname, "#888")
                prob_html += (
                    f'<div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:4px;">'
                    f'<span style="font-size:0.75rem;color:#aaa;width:150px;">{rname}({REGIME_KO.get(rname,"")})</span>'
                    f'<div style="flex:1;height:6px;background:rgba(255,255,255,0.07);border-radius:3px;overflow:hidden;">'
                    f'<div style="height:100%;width:{rprob*100:.1f}%;background:{rc3};border-radius:3px;"></div></div>'
                    f'<span style="font-size:0.78rem;font-weight:700;color:{rc3};width:40px;text-align:right;">{rprob:.0%}</span>'
                    f'</div>'
                )

            cap_note = (
                '<div style="margin-top:0.6rem;padding:0.4rem 0.8rem;background:rgba(255,170,0,0.1);'
                'border-radius:6px;color:#ffaa00;font-size:0.78rem;">'
                '⚠ Corroboration filter(교차검증): Liquidity(유동성)/Volatility(변동성) 신호 부족 → 가중치 Correction(조정)으로 강등'
                '</div>'
            ) if is_capped else ""

            st.markdown(
                f'<div class="detail-card">'
                f'<span style="font-family:Orbitron;font-size:1rem;color:{rc2};font-weight:700;">{reg_name}</span>'
                f'<span style="color:#888;font-size:0.82rem;margin-left:1rem;">{reg_detail.replace("[corroboration cap]","").strip()}</span>'
                f'<div style="margin-top:0.8rem;">{prob_html}</div>'
                f'{cap_note}'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── 탭 2: 차트 ───────────────────────────────────────
    with tab2:
        ch1, ch2 = st.columns(2)

        with ch1:
            if "SPY" in close.columns:
                spy = close["SPY"].dropna()
                sma200 = spy.rolling(200).mean()
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=spy.index, y=spy, name="SPY", line=dict(color="#4fc3f7", width=2)))
                fig.add_trace(go.Scatter(x=sma200.index, y=sma200, name="200일 SMA", line=dict(color="#ff8a65", width=1.5, dash="dash")))
                fig.update_layout(
                    title="SPY & 200일 SMA", template="plotly_dark", height=300,
                    margin=dict(l=20, r=20, t=40, b=20),
                    legend=dict(orientation="h", y=1.02),
                )
                st.plotly_chart(fig, use_container_width=True)

        with ch2:
            if "^VIX" in close.columns:
                vix = close["^VIX"].dropna()
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=vix.index, y=vix, name="VIX", fill="tozeroy",
                                         line=dict(color="#ef5350", width=2), fillcolor="rgba(239,83,80,0.2)"))
                fig.add_hline(y=25, line_dash="dash", line_color="yellow", annotation_text="위험(25)")
                fig.add_hline(y=30, line_dash="dash", line_color="red",    annotation_text="극도(30)")
                fig.update_layout(
                    title="VIX 공포지수", template="plotly_dark", height=300,
                    margin=dict(l=20, r=20, t=40, b=20),
                )
                st.plotly_chart(fig, use_container_width=True)

        # HYG/LQD 크레딧 스프레드
        if "HYG" in close.columns and "LQD" in close.columns:
            ratio = (close["HYG"] / close["LQD"]).dropna()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=ratio.index, y=ratio, name="HYG/LQD",
                                      line=dict(color="#ab47bc", width=2)))
            fig.update_layout(
                title="HYG/LQD (하이일드/투자등급 — 크레딧 스트레스)",
                template="plotly_dark", height=250,
                margin=dict(l=20, r=20, t=40, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)

        # EEM/SPY 신흥국 상대강도
        if "EEM" in close.columns and "SPY" in close.columns:
            eem_spy = (close["EEM"] / close["SPY"]).dropna()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=eem_spy.index, y=eem_spy, name="EEM/SPY",
                                      line=dict(color="#66bb6a", width=2)))
            fig.update_layout(
                title="EEM/SPY (신흥국 상대강도 — 글로벌 위험선호)",
                template="plotly_dark", height=250,
                margin=dict(l=20, r=20, t=40, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── 탭 3: 포지션 배분 ────────────────────────────────
    with tab3:
        alloc = sizing.get("allocation", {})
        if alloc:
            st.markdown("#### 권장 포지션 배분")
            alloc_items = sorted(
                [(k, v) for k, v in alloc.items() if isinstance(v, (int, float))],
                key=lambda x: x[1], reverse=True,
            )
            for k, v in alloc_items:
                color = bar_color(v) if k == "equity" else "#4fc3f7"
                st.markdown(
                    f'<div class="ind-row" style="background:rgba(255,255,255,0.03);">'
                    f'<span class="ind-name" style="min-width:110px;">{k.upper()}<span style="color:#666;font-size:0.75rem;margin-left:4px;">({ALLOC_KO.get(k,"")})</span></span>'
                    f'<div style="flex:1;height:8px;background:rgba(255,255,255,0.07);border-radius:4px;overflow:hidden;">'
                    f'<div style="height:100%;width:{int(v*100)}%;background:{color};border-radius:4px;"></div></div>'
                    f'<span class="ind-score" style="color:{color};">{v:.0%}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.markdown(f'<p class="ts">RISK SCORE: {final_score:.3f} | DATA: {data_date}</p>', unsafe_allow_html=True)
