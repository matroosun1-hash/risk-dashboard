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
    letter-spacing: 1px; color: #aaa; width: 80px; flex-shrink: 0;
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


# ── 데이터 로드 & 계산 (두 모드 공통) ─────────────────────────
with st.spinner("⚡ 퀀트 엔진 로딩 중..."):
    config      = load_config()
    close       = load_data("2y")

if close.empty:
    st.error("데이터 수신 오류")
    st.stop()

risk_result = calculate_final_risk(close, config)
sizing      = calculate_position_sizing(risk_result["final_score"], close, config)
action      = generate_portfolio_action(risk_result, sizing, config)

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

# ── 공통: 시그널 바 HTML ─────────────────────────────────────
signals_html = ""
for sig_name, info in risk_result["signal_summary"].items():
    s = info.get("score", 0)
    color = bar_color(s)
    signals_html += (
        f'<div class="sig-row">'
        f'<span class="sig-name">{sig_name.upper()}</span>'
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
        f'<p class="signals-title">Signal Breakdown</p>'
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

    # 시그널 요약 바
    st.markdown(
        f'<div class="detail-card"><p class="detail-title">Signal Overview (7 signals)</p>'
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

        # 컴포넌트 있는 신호들
        comp_signals = {
            "liquidity":    "Liquidity (유동성 스트레스)",
            "breadth":      "Market Breadth (시장폭)",
            "volatility":   "Volatility (변동성)",
            "cross_asset":  "Cross Asset (교차자산)",
            "global_macro": "Global Macro (글로벌 거시)",
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

        # Regime
        regime = signals.get("regime", {})
        if regime:
            reg_name = regime.get("regime", "Unknown")
            reg_detail = regime.get("detail", "")
            st.markdown("#### Regime Detection (HMM)")
            st.markdown(
                f'<div class="detail-card">'
                f'<span style="font-family:Orbitron;font-size:1rem;color:#4fc3f7;">{reg_name}</span>'
                f'<span style="color:#888;font-size:0.85rem;margin-left:1rem;">{reg_detail}</span>'
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
                    f'<span class="ind-name" style="min-width:80px;">{k.upper()}</span>'
                    f'<div style="flex:1;height:8px;background:rgba(255,255,255,0.07);border-radius:4px;overflow:hidden;">'
                    f'<div style="height:100%;width:{int(v*100)}%;background:{color};border-radius:4px;"></div></div>'
                    f'<span class="ind-score" style="color:{color};">{v:.0%}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.markdown(f'<p class="ts">RISK SCORE: {final_score:.3f} | DATA: {data_date}</p>', unsafe_allow_html=True)
