"""
[Step 4] 감성 분석기 — 완전 무료 버전
========================================
구성:
  - 네이버 CLOVA Sentiment : 긍정/부정/중립 점수 (월 1,000건 무료)
  - KoNLPy               : 자주 나오는 키워드 추출 (완전 무료)
  - 피부과 전용 규칙       : 항목별 점수 계산 (완전 무료)

사용법:
  pip install konlpy requests

  python 04_analyzer.py

CLOVA API 키 발급:
  1. ncloud.com 접속 → 네이버 계정으로 로그인
  2. 콘솔 → AI·NAVER API → Application 등록
  3. CLOVA Sentiment 선택 → 앱 이름 입력 → 등록
  4. Client ID / Client Secret 복사 → 아래에 입력

※ CLOVA 키 없이도 실행 가능 (키워드 규칙 기반으로만 분석)
"""

import sqlite3
import json
import time
import requests
from datetime import datetime
from collections import Counter

# ──────────────────────────────────────────
# 설정 — CLOVA API 키 입력 (없어도 동작함)
# ──────────────────────────────────────────
CLOVA_CLIENT_ID     = "YOUR_CLOVA_CLIENT_ID"      # ← 입력 (선택사항)
CLOVA_CLIENT_SECRET = "YOUR_CLOVA_CLIENT_SECRET"   # ← 입력 (선택사항)

DB_PATH = "reviews.db"

# ──────────────────────────────────────────
# 피부과 전용 키워드 사전
# ──────────────────────────────────────────
KEYWORD_DICT = {
    "친절도": {
        "긍정": ["친절", "상냥", "따뜻", "배려", "정중", "웃음"],
        "부정": ["불친절", "무뚝뚝", "퉁명", "기계적", "불쾌", "무시"],
    },
    "시술효과": {
        "긍정": ["효과", "만족", "좋아졌", "개선", "탁월", "꼼꼼", "잘해주"],
        "부정": ["효과없", "별로", "실망", "아쉽", "변화없"],
    },
    "청결도": {
        "긍정": ["깨끗", "청결", "위생", "쾌적", "깔끔"],
        "부정": ["더럽", "지저분", "냄새", "불결"],
    },
    "대기시간": {
        "긍정": ["빠르", "대기없", "바로", "즉시", "신속"],
        "부정": ["오래", "기다", "대기", "느리", "1시간", "30분"],
    },
    "상담": {
        "긍정": ["자세한 설명", "설명 잘", "상담 잘", "꼼꼼한 상담", "신뢰", "상세"],
        "부정": ["설명 없", "상담 부족", "불안", "안내 없"],
    },
    "가격": {
        "긍정": ["합리적", "저렴", "가성비", "적당"],
        "부정": ["비싸", "과도", "바가지"],
    },
}


# ──────────────────────────────────────────
# DB 초기화
# ──────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS analysis_results (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_name   TEXT NOT NULL,
            analysis_date TEXT NOT NULL,
            긍정비율         REAL,
            부정비율         REAL,
            중립비율         REAL,
            친절도           REAL,
            시술효과          REAL,
            청결도           REAL,
            대기시간          REAL,
            상담             REAL,
            가격             REAL,
            전체점수          REAL,
            긍정키워드         TEXT,
            부정키워드         TEXT,
            총리뷰수          INTEGER,
            UNIQUE(branch_name, analysis_date)
        )
    """)
    conn.commit()
    conn.close()


def get_all_branches() -> list:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT branch_name FROM naver_reviews ORDER BY branch_name")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_reviews(branch_name: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, content, review_type
        FROM naver_reviews
        WHERE branch_name = ? AND content IS NOT NULL AND length(content) > 5
    """, (branch_name,))
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "content": r[1], "type": r[2]} for r in rows]


# ──────────────────────────────────────────
# CLOVA Sentiment API 호출
# ──────────────────────────────────────────
def call_clova(text: str):
    if CLOVA_CLIENT_ID == "YOUR_CLOVA_CLIENT_ID":
        return None

    url = "https://naveropenapi.apigw.ntruss.com/sentiment-analysis/v1/analyze"
    headers = {
        "X-NCP-APIGW-API-KEY-ID": CLOVA_CLIENT_ID,
        "X-NCP-APIGW-API-KEY":    CLOVA_CLIENT_SECRET,
        "Content-Type":           "application/json",
    }
    try:
        resp = requests.post(url, headers=headers, json={"content": text[:1000]}, timeout=10)
        if resp.status_code == 200:
            doc = resp.json().get("document", {})
            conf = doc.get("confidence", {})
            return {
                "label":    doc.get("sentiment", "neutral"),
                "positive": conf.get("positive", 0) / 100,
                "negative": conf.get("negative", 0) / 100,
                "neutral":  conf.get("neutral",  0) / 100,
            }
    except Exception as e:
        print(f"  ⚠️  CLOVA 오류: {e}")
    return None


# ──────────────────────────────────────────
# 키워드 추출
# ──────────────────────────────────────────
def extract_keywords(reviews: list) -> tuple:
    all_text = " ".join([r["content"] for r in reviews])
    pos_counter = Counter()
    neg_counter = Counter()

    for 항목, kws in KEYWORD_DICT.items():
        for kw in kws["긍정"]:
            cnt = all_text.count(kw)
            if cnt > 0:
                pos_counter[kw] += cnt
        for kw in kws["부정"]:
            cnt = all_text.count(kw)
            if cnt > 0:
                neg_counter[kw] += cnt

    # KoNLPy 추가 분석 (설치된 경우)
    try:
        from konlpy.tag import Okt
        okt = Okt()
        nouns = okt.nouns(all_text)
        stopwords = {"병원", "시술", "방문", "정말", "너무", "진짜", "것", "거"}
        noun_counts = Counter([n for n in nouns if len(n) >= 2 and n not in stopwords])
        pos_texts = " ".join([r["content"] for r in reviews if r.get("type") == "positive"])
        neg_texts = " ".join([r["content"] for r in reviews if r.get("type") == "negative"])
        for noun, cnt in noun_counts.most_common(20):
            if pos_texts.count(noun) >= 2 and pos_texts.count(noun) > neg_texts.count(noun):
                pos_counter[noun] += pos_texts.count(noun)
            elif neg_texts.count(noun) >= 2 and neg_texts.count(noun) > pos_texts.count(noun):
                neg_counter[noun] += neg_texts.count(noun)
    except Exception:
        pass

    return [k for k, _ in pos_counter.most_common(5)], [k for k, _ in neg_counter.most_common(5)]


# ──────────────────────────────────────────
# 항목별 점수 계산 (규칙 기반)
# ──────────────────────────────────────────
def calc_item_scores(reviews: list) -> dict:
    scores = {}
    all_texts = [r["content"] for r in reviews]
    for 항목, kws in KEYWORD_DICT.items():
        pos = sum(text.count(kw) for text in all_texts for kw in kws["긍정"])
        neg = sum(text.count(kw) for text in all_texts for kw in kws["부정"])
        total = pos + neg
        scores[항목] = round((pos / total) * 100, 1) if total > 0 else None
    return scores


# ──────────────────────────────────────────
# 결과 출력
# ──────────────────────────────────────────
def print_result(branch_name: str, result: dict):
    print(f"\n{'='*52}")
    print(f"  📍 {branch_name}  |  리뷰 {result['총리뷰수']}건")
    print(f"{'='*52}")

    pos = result.get("긍정비율") or 0
    neg = result.get("부정비율") or 0
    print(f"  😊 긍정  {'█' * int(pos/10):<10} {pos:.0f}%")
    print(f"  😞 부정  {'█' * int(neg/10):<10} {neg:.0f}%")
    print()

    for 항목 in ["친절도", "시술효과", "청결도", "대기시간", "상담", "가격"]:
        점수 = result.get(항목)
        if 점수 is None:
            continue
        bar  = "█" * int(점수 // 10)
        빈칸  = "░" * (10 - int(점수 // 10))
        icon = "🔴" if 점수 < 50 else "🟡" if 점수 < 70 else "🟢"
        print(f"  {icon} {항목:<6} {bar}{빈칸} {점수:.0f}점")

    긍정kw = json.loads(result.get("긍정키워드") or "[]")
    부정kw = json.loads(result.get("부정키워드") or "[]")
    if 긍정kw:
        print(f"\n  👍 긍정 키워드: {', '.join(긍정kw)}")
    if 부정kw:
        print(f"  👎 부정 키워드: {', '.join(부정kw)}")


def print_summary():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT branch_name, 전체점수, 긍정비율, 부정비율, 총리뷰수
        FROM analysis_results ORDER BY 전체점수 DESC
    """)
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return

    print(f"\n\n{'='*58}")
    print(f"  📊 전체 지점 비교 순위")
    print(f"{'='*58}")
    print(f"  {'순위':<4} {'지점명':<12} {'전체점수':>6} {'긍정%':>6} {'부정%':>6} {'리뷰수':>6}")
    print(f"  {'-'*50}")
    for i, row in enumerate(rows, 1):
        icon = "🔴" if (row[1] or 0) < 50 else "🟡" if (row[1] or 0) < 70 else "🟢"
        print(f"  {icon} {i:<3} {row[0]:<12} {row[1] or 0:>6.0f} {row[2] or 0:>6.0f} {row[3] or 0:>6.0f} {row[4] or 0:>6}")


# ──────────────────────────────────────────
# 지점 분석
# ──────────────────────────────────────────
def analyze_branch(branch_name: str, analysis_date: str):
    reviews = get_reviews(branch_name)
    if not reviews:
        print(f"  ⏭️  {branch_name}: 리뷰 없음")
        return

    print(f"  🔍 {branch_name}: {len(reviews)}건 분석 중...")

    # CLOVA 감성 점수
    pos_scores, neg_scores = [], []
    clova_on = CLOVA_CLIENT_ID != "YOUR_CLOVA_CLIENT_ID"

    if clova_on:
        for r in reviews:
            res = call_clova(r["content"])
            if res:
                pos_scores.append(res["positive"])
                neg_scores.append(res["negative"])
            time.sleep(0.1)
    else:
        for r in reviews:
            if r["type"] == "positive":
                pos_scores.append(1.0); neg_scores.append(0.0)
            elif r["type"] == "negative":
                pos_scores.append(0.0); neg_scores.append(1.0)
            else:
                pos_scores.append(0.4); neg_scores.append(0.3)

    긍정비율 = round((sum(pos_scores) / len(pos_scores)) * 100, 1) if pos_scores else 0
    부정비율 = round((sum(neg_scores) / len(neg_scores)) * 100, 1) if neg_scores else 0

    item_scores  = calc_item_scores(reviews)
    긍정kw, 부정kw = extract_keywords(reviews)

    valid = [v for v in item_scores.values() if v is not None]
    전체점수 = round(긍정비율 * 0.5 + (sum(valid)/len(valid) if valid else 50) * 0.5, 1)

    result = {
        "branch_name": branch_name, "analysis_date": analysis_date,
        "긍정비율": 긍정비율, "부정비율": 부정비율, "중립비율": round(100-긍정비율-부정비율, 1),
        "친절도": item_scores.get("친절도"), "시술효과": item_scores.get("시술효과"),
        "청결도": item_scores.get("청결도"), "대기시간": item_scores.get("대기시간"),
        "상담": item_scores.get("상담"), "가격": item_scores.get("가격"),
        "전체점수": 전체점수,
        "긍정키워드": json.dumps(긍정kw, ensure_ascii=False),
        "부정키워드": json.dumps(부정kw, ensure_ascii=False),
        "총리뷰수": len(reviews),
    }

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO analysis_results
          (branch_name, analysis_date, 긍정비율, 부정비율, 중립비율,
           친절도, 시술효과, 청결도, 대기시간, 상담, 가격,
           전체점수, 긍정키워드, 부정키워드, 총리뷰수)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, tuple(result.values()))
    conn.commit()
    conn.close()

    print_result(branch_name, result)


# ──────────────────────────────────────────
# 메인
# ──────────────────────────────────────────
def main():
    init_db()
    branches = get_all_branches()

    if not branches:
        print("❌ 분석할 리뷰가 없습니다.")
        print("   먼저 03_excel_importer.py 를 실행해서 리뷰를 등록해주세요.")
        return

    analysis_date = datetime.now().strftime('%Y-%m-%d')
    clova_on = CLOVA_CLIENT_ID != "YOUR_CLOVA_CLIENT_ID"

    print(f"\n🚀 감성 분석 시작 — {len(branches)}개 지점")
    print(f"   분석 방식: {'CLOVA API + 키워드 규칙' if clova_on else '키워드 규칙 기반 (완전 무료)'}")
    print(f"   분석 일자: {analysis_date}\n")

    for branch in branches:
        analyze_branch(branch, analysis_date)

    print_summary()
    print(f"\n✅ 분석 완료! 결과가 DB에 저장되었습니다.")
    print(f"   다음 단계: python 05_dashboard.py 로 대시보드 확인\n")


if __name__ == "__main__":
    main()
