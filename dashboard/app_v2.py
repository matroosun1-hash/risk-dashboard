"""
대시보드 V2 — System Status Display
세로: 레벨 + 액션만 / 가로: 레벨 + 6개 시그널 함께 표시
streamlit run dashboard/app_v2.py
"""

import sys
import io
from pathlib import Path

# Windows cp949 환경에서 이모지 포함 print 충돌 방지
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
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


# ── CSS ──────────────────────────────────────────────────────────
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Inter:wght@400;600;700&display=swap');

* { box-sizing: border-box; }

/* Streamlit 기본 UI 숨김 */
#MainMenu, header, footer { visibility: hidden; }
.stDeployButton { display: none; }
section[data-testid="stMain"] > div:first-child {
    padding-top: 0.5rem !important;
}

.stApp {
    background-color: #08080c;
    background-image:
        radial-gradient(circle at 15% 50%, rgba(20,10,40,0.4), transparent 25%),
        radial-gradient(circle at 85% 30%, rgba(10,30,40,0.3), transparent 25%);
    font-family: 'Inter', sans-serif;
    color: #e0e0e0;
}

/* ── 전체 레이아웃 컨테이너 ── */
.layout {
    display: flex;
    flex-direction: column;
    gap: 1rem;
}

/* ── A안: 시스템 상태 카드 ── */
.status-card {
    background: rgba(15,15,22,0.9);
    border-radius: 20px;
    padding: 2.5rem 2rem;
    text-align: center;
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.06);
}
.status-label {
    font-family: 'Orbitron', sans-serif;
    font-size: 0.75rem;
    letter-spacing: 3px;
    color: #666;
    text-transform: uppercase;
    margin: 0 0 0.8rem 0;
}
.status-level {
    font-family: 'Orbitron', sans-serif;
    font-size: 5rem;
    font-weight: 900;
    line-height: 1;
    margin: 0;
}
.status-name {
    font-size: 1.4rem;
    font-weight: 700;
    margin: 0.4rem 0 0 0;
}
.status-score {
    font-size: 0.9rem;
    color: #888;
    margin: 0.3rem 0 1.2rem 0;
}
.status-action {
    font-size: 1rem;
    font-weight: 600;
    line-height: 1.5;
    padding: 0.8rem 1rem;
    border-radius: 10px;
    background: rgba(255,255,255,0.04);
}

/* ── B안: 시그널 카드 ── */
.signals-card {
    background: rgba(15,15,22,0.9);
    border-radius: 20px;
    padding: 1.5rem;
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.06);
}
.signals-title {
    font-family: 'Orbitron', sans-serif;
    font-size: 0.7rem;
    letter-spacing: 3px;
    color: #666;
    text-transform: uppercase;
    margin: 0 0 1rem 0;
}
.sig-row {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    margin-bottom: 0.7rem;
}
.sig-name {
    font-family: 'Orbitron', sans-serif;
    font-size: 0.65rem;
    letter-spacing: 1px;
    color: #aaa;
    width: 80px;
    flex-shrink: 0;
}
.sig-bar-bg {
    flex: 1;
    height: 8px;
    background: rgba(255,255,255,0.07);
    border-radius: 4px;
    overflow: hidden;
}
.sig-bar {
    height: 100%;
    border-radius: 4px;
    transition: width 0.6s ease;
}
.sig-val {
    font-size: 0.8rem;
    font-weight: 700;
    width: 32px;
    text-align: right;
    flex-shrink: 0;
}

/* ── 컬러 테마 ── */
.c4 { color: #ff2a2a; border-bottom: 3px solid #ff2a2a;
      box-shadow: 0 8px 30px -8px rgba(255,42,42,0.4); }
.c3 { color: #ff9e00; border-bottom: 3px solid #ff9e00;
      box-shadow: 0 8px 30px -8px rgba(255,158,0,0.4); }
.c2 { color: #fadd00; border-bottom: 3px solid #fadd00;
      box-shadow: 0 8px 30px -8px rgba(250,221,0,0.3); }
.c1 { color: #fadd00; border-bottom: 3px solid #fadd00; }
.c0 { color: #00ff88; border-bottom: 3px solid #00ff88;
      box-shadow: 0 8px 30px -8px rgba(0,255,136,0.3); }

.ts {
    text-align: center;
    color: #444;
    font-size: 0.72rem;
    margin-top: 0.5rem;
    font-family: 'Orbitron', sans-serif;
    letter-spacing: 1px;
}

/* ══ 세로 모드: A안만 ══ */
@media (orientation: portrait) {
    .signals-card { display: none; }
    .status-level { font-size: 5rem; }
}

/* ══ 가로 모드: A+B 나란히 ══ */
@media (orientation: landscape) {
    .layout {
        flex-direction: row;
        align-items: stretch;
    }
    .status-card  { flex: 1; padding: 1.5rem 1.2rem; }
    .signals-card { flex: 1; display: block; }
    .status-level { font-size: 3.5rem; }
    .status-name  { font-size: 1.1rem; }
    .status-action{ font-size: 0.9rem; }
}

/* ══ 데스크탑: 나란히 (1024px+) ══ */
@media (min-width: 1024px) {
    .layout { flex-direction: row; align-items: stretch; }
    .status-card  { flex: 1; }
    .signals-card { flex: 1; display: block !important; }
    .status-level { font-size: 5rem; }
}
</style>
""", unsafe_allow_html=True)


# ── 색상/텍스트 헬퍼 ─────────────────────────────────────────────
def level_class(level: int) -> str:
    return f"c{min(level, 4)}"

def level_name(level: int) -> str:
    return {0:"정상", 1:"주의", 2:"경고", 3:"위험", 4:"극도위험"}.get(level, "")

def action_text(level: int) -> str:
    if level >= 4: return "🚨 성장주 전량 매도 · 즉각 대피"
    if level == 3: return "🛡️ 방어 배분 · 현금 확보"
    if level == 2: return "⚠️ 신규 매수 자제 · 포지션 축소"
    if level == 1: return "👀 시장 모니터링 강화"
    return "✅ 정상 투자 구간"

def bar_color(score: float) -> str:
    if score >= 0.8: return "#ff2a2a"
    if score >= 0.6: return "#ff9e00"
    if score >= 0.4: return "#fadd00"
    if score >= 0.2: return "#7ecf7e"
    return "#00ff88"


# ── 메인 ─────────────────────────────────────────────────────────
with st.spinner("⚡ 퀀트 엔진 로딩 중..."):
    config = load_config()
    close  = load_data("2y")

if close.empty:
    st.error("데이터 수신 오류")
    st.stop()

risk_result  = calculate_final_risk(close, config)
sizing       = calculate_position_sizing(risk_result["final_score"], close, config)
action       = generate_portfolio_action(risk_result, sizing, config)

final_score  = risk_result["final_score"]
level_map    = {"극도위험":4, "위험":3, "경고":2, "주의":1, "정상":0}
level        = level_map.get(action.get("risk_level", "정상"), 0)
lc           = level_class(level)
data_date    = close.index[-1].strftime("%Y-%m-%d")

# ── 시그널 데이터 ──
signals_html = ""
for name, info in risk_result["signal_summary"].items():
    score = info.get("score", 0)
    pct   = int(score * 100)
    color = bar_color(score)
    signals_html += (
        f'<div class="sig-row">'
        f'<span class="sig-name">{name.upper()}</span>'
        f'<div class="sig-bar-bg"><div class="sig-bar" style="width:{pct}%;background:{color};"></div></div>'
        f'<span class="sig-val" style="color:{color};">{score:.2f}</span>'
        f'</div>'
    )

# ── 게이지 차트 ──
gauge_colors = {0:"#00ff88", 1:"#fadd00", 2:"#fadd00", 3:"#ff9e00", 4:"#ff2a2a"}
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

# ── 렌더링: 게이지만 ──
st.plotly_chart(fig_gauge, use_container_width=True)

# ── 시그널 브레이크다운 ──
st.markdown(
    f'<div class="signals-card">'
    f'<p class="signals-title">📡 Signal Breakdown</p>'
    f'{signals_html}'
    f'</div>',
    unsafe_allow_html=True,
)

st.markdown(f'<p class="ts">DATA: {data_date} // 30MIN CACHE</p>', unsafe_allow_html=True)

if st.button("🔄 새로고침", use_container_width=True):
    st.cache_data.clear()
    st.rerun()
