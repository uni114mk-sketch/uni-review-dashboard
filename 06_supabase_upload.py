"""
[Step 6] Supabase 연동 — DB 초기화 및 데이터 업로드
=====================================================
로컬 reviews.db 데이터를 Supabase로 업로드합니다.

사용법:
  pip install supabase

  1. config.py에 SUPABASE_URL, SUPABASE_KEY 입력
  2. python 06_supabase_upload.py
"""

import sqlite3
import json
from config import SUPABASE_URL, SUPABASE_KEY
from supabase import create_client

DB_PATH = "reviews.db"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ──────────────────────────────────────────
# Supabase 테이블 생성 SQL 출력
# (Supabase SQL Editor에서 직접 실행)
# ──────────────────────────────────────────
def print_create_table_sql():
    print("""
=== Supabase SQL Editor에서 아래 SQL을 실행하세요 ===
(Supabase → 왼쪽 메뉴 SQL Editor → New query → 붙여넣기 → Run)

-- 리뷰 테이블
CREATE TABLE IF NOT EXISTS reviews (
    id           BIGSERIAL PRIMARY KEY,
    branch_name  TEXT NOT NULL,
    place_id     TEXT DEFAULT 'manual',
    review_id    TEXT UNIQUE,
    reviewer     TEXT,
    rating       REAL,
    content      TEXT,
    review_type  TEXT,
    visit_date   TEXT,
    source       TEXT DEFAULT 'manual',
    collected_at TIMESTAMP DEFAULT NOW()
);

-- 분석 결과 테이블
CREATE TABLE IF NOT EXISTS analysis_results (
    id            BIGSERIAL PRIMARY KEY,
    branch_name   TEXT NOT NULL,
    analysis_date TEXT NOT NULL,
    긍정비율        REAL,
    부정비율        REAL,
    중립비율        REAL,
    친절도          REAL,
    시술효과         REAL,
    청결도          REAL,
    대기시간         REAL,
    상담            REAL,
    가격            REAL,
    전체점수         REAL,
    긍정키워드        TEXT,
    부정키워드        TEXT,
    총리뷰수         INTEGER,
    UNIQUE(branch_name, analysis_date)
);

-- 설문 점수 테이블
CREATE TABLE IF NOT EXISTS survey_scores (
    id           BIGSERIAL PRIMARY KEY,
    branch_name  TEXT NOT NULL,
    survey_date  TEXT,
    항목           TEXT,
    점수           REAL,
    collected_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(branch_name, survey_date, 항목)
);

=====================================================
""")


# ──────────────────────────────────────────
# 로컬 DB → Supabase 업로드
# ──────────────────────────────────────────
def upload_reviews():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM naver_reviews LIMIT 1000")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        print("  ⏭️  업로드할 리뷰 없음")
        return

    # id 컬럼 제거 (Supabase가 자동 생성)
    for r in rows:
        r.pop("id", None)

    # 100개씩 배치 업로드
    batch_size = 100
    uploaded = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        try:
            supabase.table("reviews").upsert(batch, on_conflict="review_id").execute()
            uploaded += len(batch)
            print(f"  ✅ 리뷰 {uploaded}/{len(rows)}건 업로드")
        except Exception as e:
            print(f"  ❌ 업로드 실패: {e}")

    print(f"  🎉 리뷰 총 {uploaded}건 Supabase 업로드 완료")


def upload_analysis():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM analysis_results")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        print("  ⏭️  업로드할 분석 결과 없음")
        return

    for r in rows:
        r.pop("id", None)

    try:
        supabase.table("analysis_results").upsert(
            rows, on_conflict="branch_name,analysis_date"
        ).execute()
        print(f"  🎉 분석 결과 {len(rows)}건 Supabase 업로드 완료")
    except Exception as e:
        print(f"  ❌ 분석 결과 업로드 실패: {e}")


def upload_scores():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM survey_scores")
        rows = [dict(r) for r in cur.fetchall()]
    except Exception:
        rows = []
    conn.close()

    if not rows:
        print("  ⏭️  업로드할 점수 데이터 없음")
        return

    for r in rows:
        r.pop("id", None)

    try:
        supabase.table("survey_scores").upsert(
            rows, on_conflict="branch_name,survey_date,항목"
        ).execute()
        print(f"  🎉 점수 데이터 {len(rows)}건 Supabase 업로드 완료")
    except Exception as e:
        print(f"  ❌ 점수 업로드 실패: {e}")


# ──────────────────────────────────────────
# 메인
# ──────────────────────────────────────────
def main():
    if SUPABASE_URL == "YOUR_SUPABASE_URL":
        print("⚠️  config.py에 SUPABASE_URL과 SUPABASE_KEY를 입력해주세요.")
        return

    print_create_table_sql()

    input("위 SQL을 Supabase에서 실행했으면 Enter를 누르세요...")

    print("\n🚀 Supabase 업로드 시작")
    upload_reviews()
    upload_analysis()
    upload_scores()
    print("\n✅ 모든 데이터 업로드 완료!")
    print("   이제 05_dashboard.py를 Supabase 버전으로 교체하세요.")


if __name__ == "__main__":
    main()
