"""
2단계 퀀트 리스크 관리 시스템 — Streamlit 대시보드

사용법:
    streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
import yaml
from datetime import datetime

from data.fetcher import fetch_market_data, get_close_prices, get_ratio
from stage1.indicators import run_all_indicators
from stage1.scorer import calculate_total_score, determine_level
from stage2.rotation import calculate_all_rotations
from stage2.leading import check_all_leading
from stage2.scorer import determine_rotation_level
from action.executor import generate_response


# ─────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🛡️ 퀀트 리스크 관리 시스템",
    page_icon="🛡️",
    layout="centered",
    initial_sidebar_state="collapsed",
)


@st.cache_data(ttl=3600)
def load_data(period: str = "1y"):
    """데이터 수집 (1시간 캐시)"""
    market_data = fetch_market_data(period=period)
    close = get_close_prices(market_data)
    return close


def load_config():
    config_path = PROJECT_ROOT / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────────────────
# 커스텀 CSS
# ─────────────────────────────────────────────────────────
st.markdown("""
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    .stApp {
        font-family: 'Inter', sans-serif;
    }

    .main-header {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        padding: 1.5rem 2rem;
        border-radius: 16px;
        margin-bottom: 1.5rem;
        color: white;
        box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    }

    .main-header h1 {
        margin: 0;
        font-size: 1.8rem;
        font-weight: 800;
        letter-spacing: -0.5px;
    }

    .main-header p {
        margin: 0.3rem 0 0 0;
        opacity: 0.7;
        font-size: 0.9rem;
    }

    .level-card {
        padding: 1.5rem;
        border-radius: 16px;
        text-align: center;
        box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        transition: transform 0.2s;
    }

    .level-card:hover {
        transform: translateY(-2px);
    }

    .level-card h2 {
        margin: 0;
        font-size: 3rem;
        font-weight: 800;
    }

    .level-card p {
        margin: 0.5rem 0 0 0;
        font-weight: 600;
        font-size: 1.1rem;
    }

    .level-0 { background: linear-gradient(135deg, #00b09b, #96c93d); color: white; }
    .level-1 { background: linear-gradient(135deg, #f7971e, #ffd200); color: #333; }
    .level-2 { background: linear-gradient(135deg, #f85032, #e73827); color: white; }
    .level-3 { background: linear-gradient(135deg, #cb2d3e, #ef473a); color: white; }
    .level-4 { background: linear-gradient(135deg, #8e0e00, #1f1c18); color: white; }

    .indicator-table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0 4px;
    }

    .indicator-row {
        background: rgba(255,255,255,0.03);
        border-radius: 8px;
    }

    .indicator-row td {
        padding: 10px 16px;
    }

    .score-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
    }

    .score-0 { background: #e8f5e9; color: #2e7d32; }
    .score-half { background: #fff8e1; color: #f57f17; }
    .score-1 { background: #ffebee; color: #c62828; }

    .action-card {
        background: linear-gradient(135deg, #141e30, #243b55);
        padding: 1.5rem;
        border-radius: 16px;
        color: white;
        margin-top: 1rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    }

    .action-card h3 {
        margin: 0 0 1rem 0;
        font-weight: 700;
    }

    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.05);
        padding: 1rem;
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.08);
    }

    /* ── 지표 행 클래스 ── */
    .ind-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        flex-wrap: nowrap;
    }
    .ind-name   { font-weight: 600; flex: 0 0 auto; }
    .ind-detail { color: #888; font-size: 0.9rem; flex: 1; text-align: center;
                  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .ind-score  { font-weight: 700; flex: 0 0 auto; }

    /* ── 로테이션/선행지표 행 클래스 ── */
    .sig-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
    }
    .sig-left  { flex: 1; min-width: 0; }
    .sig-right { flex: 0 0 auto; font-weight: 700; }

    /* ══════════════════════════════════════
       모바일 반응형 (640px 이하)
    ══════════════════════════════════════ */
    @media (max-width: 640px) {
        /* 모든 Streamlit 컬럼 세로 스택 */
        div[data-testid="stHorizontalBlock"] {
            flex-direction: column !important;
        }
        div[data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
            min-width: 100% !important;
        }

        /* 헤더 축소 */
        .main-header { padding: 1rem 1.2rem; }
        .main-header h1 { font-size: 1.2rem !important; }
        .main-header p  { font-size: 0.8rem !important; }

        /* 레벨 카드 축소 */
        .level-card { padding: 1rem; }
        .level-card h2 { font-size: 2rem !important; }
        .level-card p  { font-size: 0.9rem !important; }

        /* 지표 상세텍스트 숨김 (이름+점수만 표시) */
        .ind-detail { display: none !important; }

        /* 탭 글자 축소 */
        button[data-baseweb="tab"] {
            font-size: 0.72rem !important;
            padding: 0.4rem 0.4rem !important;
        }

        /* 사이드바 overlay 방식 */
        section[data-testid="stSidebar"] {
            position: fixed !important;
            z-index: 999 !important;
        }

        /* 여백 축소 */
        section[data-testid="stMain"] > div:first-child {
            padding-left: 0.8rem !important;
            padding-right: 0.8rem !important;
        }
    }

    @media (max-width: 400px) {
        .main-header h1 { font-size: 1rem !important; }
        .level-card h2  { font-size: 1.6rem !important; }
        button[data-baseweb="tab"] { font-size: 0.65rem !important; }
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────
# 메인 앱
# ─────────────────────────────────────────────────────────
def main():
    # 헤더
    st.markdown("""
    <div class="main-header">
        <h1>🛡️ 퀀트 리스크 관리 시스템</h1>
        <p>2단계 위기 감지 · 섹터 로테이션 탐지 · 대응 권고</p>
    </div>
    """, unsafe_allow_html=True)

    # 사이드바
    with st.sidebar:
        st.markdown("### ⚙️ 설정")
        period = st.selectbox("데이터 기간", ["3mo", "6mo", "1y", "2y"], index=2)

        if st.button("🔄 데이터 새로고침", use_container_width=True):
            st.cache_data.clear()

        st.markdown("---")
        st.markdown("### 🕐 분석 기준일")
        use_today = st.toggle("오늘 (최신 데이터)", value=True)
        if not use_today:
            analysis_date = st.date_input(
                "분석할 날짜 선택",
                value=datetime.now().date(),
                help="이 날짜까지의 데이터로 Level을 계산합니다.",
            )
        else:
            analysis_date = None

        st.markdown("---")
        st.markdown("### 📖 Level별 매매 지침")

        with st.expander("🟢 Level 0 — 정상", expanded=False):
            st.markdown("""
            - 기존 투자 전략 **정상 운영**
            - 신규 매수 **가능**
            - 포트폴리오 리밸런싱 정기 수행
            """)

        with st.expander("🟡 Level 1 — 주의", expanded=False):
            st.markdown("""
            - **모니터링 빈도 강화** (매일 체크)
            - 신규 매수 시 **포지션 축소** (평소 50%)
            - 손절선 타이트하게 조정
            - 현금비중 10~20% 확보
            """)

        with st.expander("🟠 Level 2 — 경고", expanded=False):
            st.markdown("""
            - **성장주 신규 매수 자제**
            - 성장주 포지션 **비중 축소** (30~50%)
            - 방어주/채권 ETF 일부 전환
            - 현금비중 20~30% 확보
            - 손절 도달 종목 즉시 정리
            """)

        with st.expander("🔴 Level 3 — 위험", expanded=False):
            st.markdown("""
            - **성장주 전량 매도** (손절→Sharpe↓→수익률↓)
            - 매도대금 50% → **방어 ETF 분산매수**
            - 나머지 50% → **현금 보유**
            - 🚫 성장주 신규 매수 **전면 차단**
            """)

        with st.expander("🔴🔴 Level 4 — 극도위험", expanded=False):
            st.markdown("""
            - ⚠️ **전량 매도 권고**
            - 70~80% **현금/단기채권** 전환
            - 잔여: **SHY** 또는 **GLD**
            - 모든 신규 매수 **전면 차단**
            - Level 1 이하 확인 전까지 대기
            """)

        st.caption("💡 참고용이며, 최종 판단은 본인에게 있습니다.")

    # 데이터 로드
    config = load_config()

    with st.spinner("📡 시장 데이터 수집 중..."):
        close_full = load_data(period)

    if close_full.empty:
        st.error("데이터 수집에 실패했습니다.")
        return

    # 과거 시점 분석: 선택한 날짜까지 데이터 truncate
    if analysis_date is not None:
        target = pd.Timestamp(analysis_date)
        close = close_full[close_full.index <= target].copy()
        if close.empty:
            st.error(f"{analysis_date} 이전의 데이터가 없습니다. 데이터 기간을 늘려주세요.")
            return
        analysis_label = f"📅 분석 기준일: **{close.index[-1].strftime('%Y-%m-%d')}** (과거 시점)"
        st.info(f"🕐 과거 시점 분석 모드 — {close.index[-1].strftime('%Y-%m-%d')} 기준")
    else:
        close = close_full
        analysis_label = f"📅 분석 기준일: **{close.index[-1].strftime('%Y-%m-%d')}** (최신)"

    data_range = f"{close.index[0].strftime('%Y-%m-%d')} ~ {close.index[-1].strftime('%Y-%m-%d')}"
    st.caption(f"{analysis_label} | 데이터: {data_range} | 티커: {len(close.columns)}개")

    # ─── 1단계 + 2단계 분석 ──────────────────────────────
    stage1_cfg = config.get("stage1", {})
    stage2_cfg = config.get("stage2", {})

    indicators = run_all_indicators(close, stage1_cfg)
    total_score = calculate_total_score(indicators)
    s1_level = determine_level(total_score, stage1_cfg)

    rotation_results = calculate_all_rotations(close, stage2_cfg)
    leading_results = check_all_leading(close, stage2_cfg)
    s2_level = determine_rotation_level(rotation_results, leading_results, stage2_cfg)

    # ─── Level 카드 ──────────────────────────────────────
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        level_class = f"level-{min(s1_level['level'], 4)}"
        st.markdown(f"""
        <div class="level-card {level_class}">
            <p>1단계: 하락장 조기탐지</p>
            <h2>Level {s1_level['level']}</h2>
            <p>{s1_level['label']} ({total_score:.1f}/10점)</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        level_class = f"level-{min(s2_level['level'], 4)}"
        st.markdown(f"""
        <div class="level-card {level_class}">
            <p>2단계: 섹터 로테이션</p>
            <h2>Level {s2_level['level']}</h2>
            <p>{s2_level['label']} (음수쌍: {s2_level['negative_pairs']}/4)</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        max_level = max(s1_level['level'], s2_level['level'])
        level_class = f"level-{min(max_level, 4)}"
        max_label = {0: "정상", 1: "주의", 2: "경고", 3: "위험", 4: "극도위험"}.get(max_level, "")
        st.markdown(f"""
        <div class="level-card {level_class}">
            <p>종합 위험 Level</p>
            <h2>Level {max_level}</h2>
            <p>{max_label}</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ─── 탭 레이아웃 ─────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 1단계: 10개 지표",
        "🔄 2단계: 로테이션",
        "🎯 대응 권고",
        "📈 차트",
    ])

    # ─── 탭 1: 1단계 10개 지표 ───────────────────────────
    with tab1:
        st.markdown("### 📊 10개 거시 지표 현황")

        for i, ind in enumerate(indicators):
            score = ind["score"]
            if score >= 1:
                color = "#ff4444"
                bg = "rgba(255,68,68,0.1)"
                icon = "🔴"
            elif score > 0:
                color = "#ffaa00"
                bg = "rgba(255,170,0,0.1)"
                icon = "🟡"
            else:
                color = "#44bb44"
                bg = "rgba(68,187,68,0.1)"
                icon = "🟢"

            st.markdown(
                f'<div class="ind-row" style="padding:12px 20px; margin:4px 0; '
                f'border-radius:10px; background:{bg}; border-left:4px solid {color};">'
                f'<span class="ind-name">{icon} {i+1}. {ind["name"]}</span>'
                f'<span class="ind-detail">{ind["detail"]}</span>'
                f'<span class="ind-score" style="color:{color};">{score:.1f}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown(f"""
        <div style="text-align:right; margin-top:12px; padding:8px 20px;
                    background:rgba(255,255,255,0.05); border-radius:10px;">
            <strong>총점: {total_score:.1f} / 10</strong>
        </div>
        """, unsafe_allow_html=True)

    # ─── 탭 2: 2단계 로테이션 ────────────────────────────
    with tab2:
        col_rot, col_lead = st.columns(2)

        with col_rot:
            st.markdown("### 🔄 로테이션 쌍 (20일)")
            for r in rotation_results:
                change = r["change"]
                if change is None:
                    color, icon = "#888", "⚪"
                elif r.get("strong_signal"):
                    color, icon = "#ff4444", "🔴"
                elif r.get("signal"):
                    color, icon = "#ffaa00", "🟡"
                else:
                    color, icon = "#44bb44", "🟢"

                change_str = f"{change:+.2%}" if change is not None else "N/A"
                st.markdown(
                    f'<div class="sig-row" style="padding:12px 20px; margin:4px 0; '
                    f'border-radius:10px; background:rgba(255,255,255,0.03); border-left:4px solid {color};">'
                    f'<span class="sig-left"><span style="font-weight:600;">{icon} {r["label"]}</span> '
                    f'<span style="color:#888;">({r["pair"]})</span></span>'
                    f'<span class="sig-right" style="color:{color};">{change_str}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        with col_lead:
            st.markdown("### 📡 선행지표 (7일)")
            for r in leading_results:
                change = r.get("change")
                signal = r.get("signal", False)
                if change is None:
                    color, icon = "#888", "⚪"
                elif signal:
                    color, icon = "#ff4444", "⚠️"
                else:
                    color, icon = "#44bb44", "✅"

                change_str = f"{change:+.2%}" if change is not None else "N/A"
                st.markdown(
                    f'<div class="sig-row" style="padding:12px 20px; margin:4px 0; '
                    f'border-radius:10px; background:rgba(255,255,255,0.03); border-left:4px solid {color};">'
                    f'<span class="sig-left"><span style="font-weight:600;">{icon} {r["label"]}</span> '
                    f'<span style="color:#888;">({r["ticker"]})</span></span>'
                    f'<span class="sig-right" style="color:{color};">{change_str}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ─── 탭 3: 대응 권고 ────────────────────────────────
    with tab3:
        st.markdown("### 🎯 종합 대응 권고")

        holdings = config.get("portfolio", {}).get("holdings", [])
        action_cfg = config.get("action", {})

        response = generate_response(s1_level, s2_level, holdings, close, action_cfg)

        for action in response["actions"]:
            st.markdown(f"**{action}**")

        if response["block_new_buys"]:
            st.error("🚫 성장주 신규 매수 차단 상태")

        if response["sell_list"]:
            st.markdown("#### 매도 우선순위")
            sell_df = pd.DataFrame([
                {
                    "티커": m["ticker"],
                    "현재가": f"${m.get('current_price', 0):.2f}" if m.get('current_price') else "N/A",
                    "손익률": f"{m.get('pnl_pct', 0):.1%}" if m.get('pnl_pct') is not None else "N/A",
                    "사유": m.get("sell_reason", ""),
                }
                for m in response["sell_list"]
            ])
            st.dataframe(sell_df, use_container_width=True, hide_index=True)

        if response["defense_allocation"]:
            alloc = response["defense_allocation"]
            st.markdown("#### 방어 ETF 배분")
            st.markdown(f"- 방어자산 배분: **${alloc['defense_amount']:,.0f}** ({alloc['defense_pct']:.0%})")
            st.markdown(f"- 현금 보유: **${alloc['cash_amount']:,.0f}** ({alloc['cash_pct']:.0%})")

            alloc_df = pd.DataFrame([
                {"카테고리": a["category"], "티커": a["ticker"], "금액": f"${a['amount']:,.0f}"}
                for a in alloc["allocations"]
            ])
            st.dataframe(alloc_df, use_container_width=True, hide_index=True)

        if not holdings:
            st.info("💡 `config.yaml`의 `portfolio.holdings`에 보유 종목을 입력하면 구체적인 매도 권고를 받을 수 있습니다.")

    # ─── 탭 4: 차트 ──────────────────────────────────────
    with tab4:
        st.markdown("### 📈 주요 차트")

        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            # SPY + 200일 이동평균
            if "SPY" in close.columns:
                spy = close["SPY"].dropna()
                sma200 = spy.rolling(200).mean()

                fig = go.Figure()
                fig.add_trace(go.Scatter(x=spy.index, y=spy, name="SPY", line=dict(color="#4fc3f7", width=2)))
                fig.add_trace(go.Scatter(x=sma200.index, y=sma200, name="200일 SMA", line=dict(color="#ff8a65", width=1.5, dash="dash")))
                fig.update_layout(
                    title="SPY & 200일 이동평균",
                    template="plotly_dark",
                    height=350,
                    margin=dict(l=20, r=20, t=50, b=20),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                )
                st.plotly_chart(fig, use_container_width=True)

        with chart_col2:
            # VIX
            if "^VIX" in close.columns:
                vix = close["^VIX"].dropna()
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=vix.index, y=vix, name="VIX", fill="tozeroy", line=dict(color="#ef5350", width=2), fillcolor="rgba(239,83,80,0.2)"))
                fig.add_hline(y=25, line_dash="dash", line_color="yellow", annotation_text="위험 (25)")
                fig.add_hline(y=30, line_dash="dash", line_color="red", annotation_text="극도위험 (30)")
                fig.update_layout(
                    title="VIX 공포지수",
                    template="plotly_dark",
                    height=350,
                    margin=dict(l=20, r=20, t=50, b=20),
                )
                st.plotly_chart(fig, use_container_width=True)

        # 로테이션 비율 차트
        st.markdown("#### 로테이션 쌍 추이")
        pairs_config = stage2_cfg.get("rotation_pairs", [])

        fig_rot = go.Figure()
        colors = ["#4fc3f7", "#ab47bc", "#66bb6a", "#ffa726"]
        for i, pair in enumerate(pairs_config):
            try:
                ratio = get_ratio(close, pair["numerator"], pair["denominator"]).dropna()
                # 정규화 (첫 값 = 100)
                normalized = (ratio / ratio.iloc[0]) * 100
                fig_rot.add_trace(go.Scatter(
                    x=normalized.index, y=normalized,
                    name=f"{pair.get('label', '')} ({pair['numerator']}/{pair['denominator']})",
                    line=dict(color=colors[i % len(colors)], width=2),
                ))
            except Exception:
                pass

        fig_rot.add_hline(y=100, line_dash="dash", line_color="gray", opacity=0.5)
        fig_rot.update_layout(
            title="로테이션 쌍 상대 성과 추이 (정규화 = 100)",
            template="plotly_dark",
            height=400,
            margin=dict(l=20, r=20, t=50, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_rot, use_container_width=True)


if __name__ == "__main__":
    main()
