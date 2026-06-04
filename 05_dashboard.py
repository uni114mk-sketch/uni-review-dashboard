"""
[Step 5] 웹 대시보드
=====================
수집 및 분석된 데이터를 웹 브라우저에서 시각화합니다.

사용법:
  pip install streamlit plotly

  streamlit run 05_dashboard.py

실행 후 브라우저에서 http://localhost:8501 접속
"""

import sqlite3
import json
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

DB_PATH = "reviews.db"

# ──────────────────────────────────────────
# 페이지 설정
# ──────────────────────────────────────────
st.set_page_config(
    page_title="피부과 리뷰 분석 대시보드",
    page_icon="🏥",
    layout="wide",
)

st.markdown("""
<style>
  .metric-card {
    background: #f8f9fa;
    border-radius: 12px;
    padding: 1rem 1.25rem;
    border: 1px solid #e9ecef;
  }
  .alert-card {
    background: #fff5f5;
    border-radius: 12px;
    padding: 1rem 1.25rem;
    border: 1px solid #fed7d7;
  }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────
# 데이터 로드
# ──────────────────────────────────────────
@st.cache_data(ttl=60)
def load_analysis():
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("""
            SELECT * FROM analysis_results
            ORDER BY 전체점수 DESC
        """, conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_reviews(branch_name=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        query = "SELECT * FROM naver_reviews"
        if branch_name:
            query += f" WHERE branch_name = '{branch_name}'"
        query += " ORDER BY collected_at DESC LIMIT 200"
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_scores():
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("SELECT * FROM survey_scores", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


# ──────────────────────────────────────────
# 사이드바
# ──────────────────────────────────────────
with st.sidebar:
    st.title("🏥 리뷰 분석")
    st.caption("피부과 마케팅 대시보드")
    st.divider()

    df_analysis = load_analysis()

    if df_analysis.empty:
        st.warning("분석 데이터가 없습니다.\n\n`python 04_analyzer.py`를 먼저 실행해주세요.")
        st.stop()

    branches = ["전체"] + list(df_analysis["branch_name"].unique())
    selected = st.selectbox("지점 선택", branches)

    st.divider()
    st.caption(f"마지막 분석: {df_analysis['analysis_date'].max()}")
    if st.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()


# ──────────────────────────────────────────
# 전체 보기
# ──────────────────────────────────────────
if selected == "전체":
    st.title("📊 전체 지점 현황")

    # 상단 요약 지표
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("총 지점 수", f"{len(df_analysis)}개")
    with c2:
        avg = df_analysis["전체점수"].mean()
        st.metric("평균 전체점수", f"{avg:.1f}점")
    with c3:
        danger = len(df_analysis[df_analysis["전체점수"] < 50])
        st.metric("주의 지점", f"{danger}개", delta=f"-{danger}" if danger > 0 else "0", delta_color="inverse")
    with c4:
        total_reviews = load_reviews()
        st.metric("총 수집 리뷰", f"{len(total_reviews):,}건")

    st.divider()

    col_left, col_right = st.columns([1.5, 1])

    with col_left:
        st.subheader("지점별 전체점수 순위")
        fig = px.bar(
            df_analysis.sort_values("전체점수"),
            x="전체점수",
            y="branch_name",
            orientation="h",
            color="전체점수",
            color_continuous_scale=["#E24B4A", "#EF9F27", "#639922"],
            range_color=[0, 100],
            labels={"branch_name": "", "전체점수": "점수"},
            height=max(300, len(df_analysis) * 36),
        )
        fig.update_layout(
            coloraxis_showscale=False,
            margin=dict(l=10, r=10, t=10, b=10),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        fig.add_vline(x=50, line_dash="dash", line_color="#E24B4A", opacity=0.5, annotation_text="주의선(50)")
        fig.add_vline(x=70, line_dash="dash", line_color="#EF9F27", opacity=0.5, annotation_text="양호선(70)")
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.subheader("항목별 전체 평균")
        항목들 = ["친절도", "시술효과", "청결도", "대기시간", "상담", "가격"]
        avg_scores = {}
        for 항목 in 항목들:
            if 항목 in df_analysis.columns:
                val = df_analysis[항목].dropna().mean()
                if not pd.isna(val):
                    avg_scores[항목] = round(val, 1)

        if avg_scores:
            fig2 = go.Figure(go.Bar(
                x=list(avg_scores.values()),
                y=list(avg_scores.keys()),
                orientation="h",
                marker_color=["#E24B4A" if v < 50 else "#EF9F27" if v < 70 else "#639922"
                               for v in avg_scores.values()],
            ))
            fig2.update_layout(
                xaxis_range=[0, 100],
                margin=dict(l=10, r=10, t=10, b=10),
                height=300,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig2, use_container_width=True)

        # 긍정/부정 전체 평균
        st.subheader("전체 긍정/부정 비율")
        avg_pos = df_analysis["긍정비율"].mean()
        avg_neg = df_analysis["부정비율"].mean()
        fig3 = go.Figure(go.Pie(
            labels=["긍정", "부정", "중립"],
            values=[avg_pos, avg_neg, max(0, 100 - avg_pos - avg_neg)],
            hole=0.5,
            marker_colors=["#639922", "#E24B4A", "#888780"],
        ))
        fig3.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            height=220,
            showlegend=True,
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig3, use_container_width=True)

    st.divider()

    # 주의 지점 알림
    danger_branches = df_analysis[df_analysis["전체점수"] < 50]
    if not danger_branches.empty:
        st.subheader("🚨 주의 지점")
        for _, row in danger_branches.iterrows():
            neg_kw = json.loads(row.get("부정키워드") or "[]")
            st.error(
                f"**{row['branch_name']}** — 전체점수 {row['전체점수']:.0f}점  |  "
                f"긍정 {row['긍정비율']:.0f}% / 부정 {row['부정비율']:.0f}%  |  "
                f"부정 키워드: {', '.join(neg_kw) if neg_kw else '없음'}"
            )

    # 전체 데이터 테이블
    st.subheader("전체 데이터 테이블")
    display_cols = ["branch_name", "전체점수", "긍정비율", "부정비율",
                    "친절도", "시술효과", "청결도", "대기시간", "총리뷰수"]
    display_cols = [c for c in display_cols if c in df_analysis.columns]
    st.dataframe(
        df_analysis[display_cols].rename(columns={"branch_name": "지점명"}),
        use_container_width=True,
        hide_index=True,
    )


# ──────────────────────────────────────────
# 지점별 상세 보기
# ──────────────────────────────────────────
else:
    row = df_analysis[df_analysis["branch_name"] == selected].iloc[0]
    st.title(f"📍 {selected} 상세 분석")
    st.caption(f"분석일: {row['analysis_date']}  |  총 리뷰: {int(row['총리뷰수'])}건")

    # 상단 지표
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        score = row["전체점수"]
        color = "normal" if score >= 70 else "off"
        st.metric("전체점수", f"{score:.0f}점")
    with c2:
        st.metric("긍정 비율", f"{row['긍정비율']:.0f}%")
    with c3:
        st.metric("부정 비율", f"{row['부정비율']:.0f}%",
                  delta=f"-{row['부정비율']:.0f}%", delta_color="inverse")
    with c4:
        st.metric("총 리뷰 수", f"{int(row['총리뷰수'])}건")

    st.divider()
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("항목별 점수")
        항목들 = ["친절도", "시술효과", "청결도", "대기시간", "상담", "가격"]
        scores = {h: row.get(h) for h in 항목들 if pd.notna(row.get(h))}
        if scores:
            fig = go.Figure(go.Bar(
                x=list(scores.values()),
                y=list(scores.keys()),
                orientation="h",
                marker_color=["#E24B4A" if v < 50 else "#EF9F27" if v < 70 else "#639922"
                               for v in scores.values()],
                text=[f"{v:.0f}점" for v in scores.values()],
                textposition="outside",
            ))
            fig.update_layout(
                xaxis_range=[0, 115],
                margin=dict(l=10, r=10, t=10, b=10),
                height=300,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("긍정 / 부정 비율")
        fig2 = go.Figure(go.Pie(
            labels=["긍정", "부정", "중립"],
            values=[
                row["긍정비율"],
                row["부정비율"],
                max(0, 100 - row["긍정비율"] - row["부정비율"])
            ],
            hole=0.5,
            marker_colors=["#639922", "#E24B4A", "#888780"],
        ))
        fig2.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            height=280,
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig2, use_container_width=True)

        # 키워드
        pos_kw = json.loads(row.get("긍정키워드") or "[]")
        neg_kw = json.loads(row.get("부정키워드") or "[]")
        if pos_kw:
            st.success(f"👍 긍정 키워드: **{', '.join(pos_kw)}**")
        if neg_kw:
            st.error(f"👎 부정 키워드: **{', '.join(neg_kw)}**")

    st.divider()

    # 리뷰 원문
    st.subheader("리뷰 원문")
    tab1, tab2 = st.tabs(["👍 긍정 리뷰", "👎 부정 리뷰"])
    reviews = load_reviews(selected)

    with tab1:
        pos_reviews = reviews[reviews["review_type"] == "positive"]
        if pos_reviews.empty:
            st.info("긍정 리뷰가 없습니다.")
        for _, r in pos_reviews.head(20).iterrows():
            with st.container():
                st.markdown(f"> {r['content']}")
                st.caption(f"출처: {r.get('source', '-')}  |  수집일: {r.get('collected_at', '-')[:10]}")
                st.divider()

    with tab2:
        neg_reviews = reviews[reviews["review_type"] == "negative"]
        if neg_reviews.empty:
            st.info("부정 리뷰가 없습니다.")
        for _, r in neg_reviews.head(20).iterrows():
            with st.container():
                st.markdown(f"> {r['content']}")
                st.caption(f"출처: {r.get('source', '-')}  |  수집일: {r.get('collected_at', '-')[:10]}")
                st.divider()
