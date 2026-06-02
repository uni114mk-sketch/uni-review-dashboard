"""
[Step 3] 만족도 설문 엑셀 임포터 (지점별 xls 파일 → DB 통합)
=============================================================
파일 구조:
  - 테이블1: 항목별 점수 (친절도, 데스크, 상담실장, 원장님 등)
  - 테이블2: 텍스트 리뷰 (7. 좋은 점 / 8. 불편한 점)

사용법:
  pip install pandas xlrd lxml html5lib

  # 파일 하나
  python 03_excel_importer.py --file 강남점.xls

  # 폴더 안 전체 xls 파일 한 번에
  python 03_excel_importer.py --folder ./지점데이터/

  # 지점명을 파일명에서 자동 추출 (기본값)
  # 또는 직접 지정
  python 03_excel_importer.py --file 강남점.xls --branch 강남본점
"""

import sqlite3
import argparse
import re
from pathlib import Path
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    print("pip install pandas xlrd lxml html5lib 을 먼저 실행해주세요.")
    import sys; sys.exit(1)

DB_PATH = "reviews.db"


# ──────────────────────────────────────────
# DB 초기화
# ──────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 텍스트 리뷰 테이블
    cur.execute("""
        CREATE TABLE IF NOT EXISTS naver_reviews (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_name  TEXT NOT NULL,
            place_id     TEXT NOT NULL DEFAULT 'manual',
            review_id    TEXT UNIQUE,
            reviewer     TEXT,
            rating       REAL,
            content      TEXT,
            review_type  TEXT,        -- 'positive' / 'negative'
            visit_date   TEXT,
            source       TEXT DEFAULT 'survey',
            collected_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 점수 테이블 (항목별 집계용)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS survey_scores (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_name  TEXT NOT NULL,
            survey_date  TEXT,
            항목          TEXT,
            점수          REAL,
            collected_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(branch_name, survey_date, 항목)
        )
    """)

    conn.commit()
    conn.close()


# ──────────────────────────────────────────
# 점수 테이블 파싱 (테이블 0)
# ──────────────────────────────────────────
def parse_scores(table: pd.DataFrame, branch_name: str, survey_date: str) -> list[dict]:
    scores = []
    for _, row in table.iterrows():
        질문 = str(row.get('질문', '')).strip()
        평점_raw = str(row.get('평점.1', '') or row.get('평점', '')).strip()

        if not 질문 or 질문 in ['전체', 'nan']:
            continue

        # "93 점" → 93.0
        nums = re.findall(r'[\d.]+', 평점_raw)
        점수 = float(nums[0]) if nums else None

        if 점수 is not None:
            scores.append({
                'branch_name': branch_name,
                'survey_date': survey_date,
                '항목': 질문,
                '점수': 점수,
            })
    return scores


# ──────────────────────────────────────────
# 텍스트 리뷰 파싱 (테이블 1)
# ──────────────────────────────────────────
def parse_reviews(table: pd.DataFrame, branch_name: str) -> list[dict]:
    reviews = []
    cols = list(table.columns)

    # 컬럼 0 = 좋은 점, 컬럼 2 = 불편한 점 (구조 고정)
    good_col = cols[0]
    bad_col  = cols[2] if len(cols) > 2 else None

    for _, row in table.iterrows():
        # 좋은 점
        good = str(row.get(good_col, '')).strip()
        if good and good.lower() not in ['nan', '없음', '없습니다', '없어요', '-', '']:
            reviews.append({
                'branch_name': branch_name,
                'content':     good,
                'review_type': 'positive',
                'review_id':   f"survey_{branch_name}_pos_{hash(good) % 10**8}",
            })

        # 불편한 점
        if bad_col:
            bad = str(row.get(bad_col, '')).strip()
            if bad and bad.lower() not in ['nan', '없음', '없습니다', '없어요', '-', '']:
                reviews.append({
                    'branch_name': branch_name,
                    'content':     bad,
                    'review_type': 'negative',
                    'review_id':   f"survey_{branch_name}_neg_{hash(bad) % 10**8}",
                })

    return reviews


# ──────────────────────────────────────────
# DB 저장
# ──────────────────────────────────────────
def save_scores(scores: list[dict]) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    saved = 0
    for s in scores:
        try:
            cur.execute("""
                INSERT OR IGNORE INTO survey_scores (branch_name, survey_date, 항목, 점수)
                VALUES (?, ?, ?, ?)
            """, (s['branch_name'], s['survey_date'], s['항목'], s['점수']))
            if cur.rowcount:
                saved += 1
        except Exception as e:
            print(f"  ⚠️  점수 저장 실패: {e}")
    conn.commit()
    conn.close()
    return saved


def save_reviews(reviews: list[dict]) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    saved = 0
    for r in reviews:
        try:
            cur.execute("""
                INSERT OR IGNORE INTO naver_reviews
                  (branch_name, review_id, content, review_type, source)
                VALUES (?, ?, ?, ?, 'survey')
            """, (r['branch_name'], r['review_id'], r['content'], r['review_type']))
            if cur.rowcount:
                saved += 1
        except Exception as e:
            print(f"  ⚠️  리뷰 저장 실패: {e}")
    conn.commit()
    conn.close()
    return saved


# ──────────────────────────────────────────
# 파일 1개 처리
# ──────────────────────────────────────────
def process_file(filepath: str, branch_name: str = "") -> dict:
    path = Path(filepath)

    # 지점명: 직접 지정 없으면 파일명에서 자동 추출
    # 예: "satisfaction_강남점.xls" → "강남점"
    if not branch_name:
        branch_name = re.sub(r'^satisfaction_', '', path.stem)

    survey_date = datetime.now().strftime('%Y-%m')
    print(f"\n📂 처리 중: {path.name} → 지점명: [{branch_name}]")

    try:
        tables = pd.read_html(str(path), encoding='utf-8')
    except Exception:
        try:
            tables = pd.read_html(str(path), encoding='cp949')
        except Exception as e:
            print(f"  ❌ 파일 읽기 실패: {e}")
            return {'scores': 0, 'reviews': 0}

    scores_saved  = 0
    reviews_saved = 0

    for i, table in enumerate(tables):
        cols = [str(c) for c in table.columns]

        # 점수 테이블 감지 (컬럼에 '질문', '평점' 포함)
        if any('질문' in c for c in cols) and any('평점' in c for c in cols):
            scores = parse_scores(table, branch_name, survey_date)
            scores_saved = save_scores(scores)
            print(f"  ✅ 점수 {scores_saved}개 항목 저장")

        # 리뷰 테이블 감지 (컬럼에 '좋' 또는 '불편' 포함)
        elif any('좋' in c or '불편' in c for c in cols):
            reviews = parse_reviews(table, branch_name)
            reviews_saved = save_reviews(reviews)
            print(f"  ✅ 텍스트 리뷰 {reviews_saved}건 저장 (좋은점/불편한점)")

    return {'scores': scores_saved, 'reviews': reviews_saved}


# ──────────────────────────────────────────
# 결과 미리보기
# ──────────────────────────────────────────
def preview_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("\n" + "="*50)
    print("📊 지점별 수집 현황")
    print("="*50)

    cur.execute("""
        SELECT branch_name,
               COUNT(*) as 리뷰수,
               SUM(CASE WHEN review_type='positive' THEN 1 ELSE 0 END) as 긍정,
               SUM(CASE WHEN review_type='negative' THEN 1 ELSE 0 END) as 부정
        FROM naver_reviews WHERE source='survey'
        GROUP BY branch_name ORDER BY 리뷰수 DESC
    """)
    print(f"\n{'지점명':<12} {'총리뷰':>6} {'긍정':>5} {'부정':>5}")
    print("-"*32)
    for row in cur.fetchall():
        print(f"{row[0]:<12} {row[1]:>6} {row[2]:>5} {row[3]:>5}")

    print("\n📈 항목별 평균 점수 (전 지점)")
    print("-"*40)
    cur.execute("""
        SELECT 항목, ROUND(AVG(점수),1) as 평균점수, COUNT(*) as 지점수
        FROM survey_scores
        GROUP BY 항목 ORDER BY 평균점수 DESC
    """)
    for row in cur.fetchall():
        bar = "█" * int(row[1] / 10)
        print(f"{row[0][:20]:<22} {row[1]:>5}점  {bar}")

    conn.close()


# ──────────────────────────────────────────
# 메인
# ──────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='만족도 설문 엑셀 임포터')
    parser.add_argument('--file',   help='xls 파일 경로 (단일)')
    parser.add_argument('--folder', help='xls 파일들이 있는 폴더 경로')
    parser.add_argument('--branch', default='', help='지점명 직접 지정 (--file 사용 시)')
    args = parser.parse_args()

    if not args.file and not args.folder:
        print("사용법:")
        print("  python 03_excel_importer.py --file 강남점.xls")
        print("  python 03_excel_importer.py --folder ./지점데이터/")
        return

    init_db()
    total = {'scores': 0, 'reviews': 0}

    if args.file:
        result = process_file(args.file, args.branch)
        total['scores']  += result['scores']
        total['reviews'] += result['reviews']

    elif args.folder:
        folder = Path(args.folder)
        files = list(folder.glob('*.xls')) + list(folder.glob('*.xlsx'))
        if not files:
            print(f"❌ {folder} 폴더에 xls/xlsx 파일이 없습니다.")
            return
        print(f"📁 {len(files)}개 파일 발견")
        for f in sorted(files):
            result = process_file(str(f))
            total['scores']  += result['scores']
            total['reviews'] += result['reviews']

    print(f"\n{'='*50}")
    print(f"✅ 전체 완료 — 점수 {total['scores']}항목 / 리뷰 {total['reviews']}건 저장")
    preview_db()


if __name__ == "__main__":
    main()
