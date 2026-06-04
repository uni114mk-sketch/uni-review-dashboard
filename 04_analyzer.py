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
        "긍정": [
            # 직원 전체
            "친절", "친절해", "친절하고", "친절합니다", "친절하다", "친절했",
            "상냥", "상냥하", "따뜻", "따뜻하", "배려", "배려해주",
            "정중", "웃으며", "웃음", "밝게", "밝은", "활기",
            "친절한 직원", "직원이 친절", "간호사가 친절", "선생님이 친절",
            "응대가 좋", "응대가 친절", "응대 좋았", "응대 훌륭",
            "기분 좋", "기분좋", "편안하게", "편안한 분위기",
            "상냥하게", "매너", "매너가 좋", "고객응대", "서비스가 좋",
            "서비스 좋", "서비스가 훌륭", "최고의 서비스",
            "재방문", "재방문할", "또 오고", "또 방문", "단골",
            "추천", "추천합니다", "강추", "적극 추천",
        ],
        "부정": [
            "불친절", "불친절해", "불친절하", "불친절했",
            "무뚝뚝", "퉁명", "퉁명스럽", "기계적", "차갑게",
            "불쾌", "불쾌했", "기분 나쁨", "기분이 나빴",
            "무시", "무시당", "무시하는", "하대",
            "직원이 불친절", "간호사가 불친절", "응대가 불친절",
            "응대가 나쁘", "응대 별로", "서비스가 나쁘",
            "서비스 별로", "태도가 나쁘", "태도 불량",
            "비추", "비추천", "실망스러운 서비스",
        ],
    },
    "시술효과": {
        "긍정": [
            # 효과 관련
            "효과", "효과적", "효과가 좋", "효과 좋", "효과 있",
            "효과 만점", "효과 탁월", "효과 최고",
            "만족", "만족해", "만족합니다", "만족스럽", "대만족",
            "좋아졌", "좋아지고", "나아졌", "나아지고", "개선",
            "개선됐", "개선되었", "피부가 좋아", "피부 좋아",
            "탁월", "훌륭", "완벽", "최고", "대박",
            "꼼꼼", "꼼꼼하게", "꼼꼼히", "섬세", "섬세하게",
            "잘해주", "잘해줬", "잘 해주", "실력이 좋",
            "원장님이 실력", "실력있", "전문적", "전문성",
            "결과가 좋", "결과 만족", "결과 훌륭",
            "피부가 깨끗", "피부 개선", "트러블 없어",
            "레이저 효과", "보톡스 효과", "필러 효과",
            "시술 후 만족", "시술 잘", "시술이 좋",
        ],
        "부정": [
            "효과없", "효과 없", "효과가 없", "효과 없어",
            "별로", "별로다", "별로였", "별로예요",
            "실망", "실망했", "실망스럽", "크게 실망",
            "아쉽", "아쉬웠", "아쉬움", "기대 이하",
            "변화없", "변화 없", "달라진 게 없", "그대로",
            "효과 모르겠", "효과 의문", "돈이 아깝",
            "재발", "다시 생겼", "피부가 나빠", "트러블 생",
            "부작용", "붓기", "흉터", "멍이", "자국이",
            "피부 트러블", "시술 후 트러블",
        ],
    },
    "청결도": {
        "긍정": [
            "깨끗", "깨끗해", "깨끗하고", "깨끗합니다",
            "청결", "청결해", "청결하고", "청결합니다",
            "위생", "위생적", "위생관리", "위생이 철저",
            "쾌적", "쾌적하고", "쾌적한 환경",
            "깔끔", "깔끔해", "깔끔하고", "깔끔합니다",
            "정돈", "정돈된", "정리가 잘", "깔끔하게 정리",
            "시설이 좋", "시설 좋", "시설이 깨끗", "인테리어 좋",
            "인테리어가 예쁘", "인테리어 예쁘", "내부가 깔끔",
        ],
        "부정": [
            "더럽", "더러워", "더러운", "더러웠",
            "지저분", "지저분해", "지저분하고",
            "냄새", "냄새가", "악취", "냄새났",
            "불결", "불결해", "비위생적", "위생이 불량",
            "청결하지 않", "청결하지 못", "청결 문제",
            "시설이 낡", "시설이 오래", "시설이 노후",
            "관리가 안", "관리가 부실",
        ],
    },
    "대기시간": {
        "긍정": [
            "빠르", "빠르게", "빠른 처리", "빠른 진료",
            "대기없", "대기 없", "대기 없이", "대기 없었",
            "바로", "바로 안내", "바로 들어가", "즉시",
            "신속", "신속하게", "신속한 처리",
            "기다리지 않", "기다림 없", "오래 안 기다",
            "예약 시간에 맞춰", "예약 잘 지켜", "시간 잘 지켜",
            "대기가 짧", "짧게 기다", "금방",
        ],
        "부정": [
            "오래", "오래 기다", "오래 기다렸", "오랫동안",
            "기다", "기다렸", "기다려야", "기다리는",
            "대기", "대기 시간", "대기가 너무", "대기가 길",
            "느리", "느렸", "진료가 늦", "처리가 늦",
            "1시간", "2시간", "30분 이상", "40분", "50분",
            "한참", "한참을 기다", "예약 시간 안 지켜",
            "예약이 의미없", "예약해도 기다", "예약 무시",
            "오랜 대기", "긴 대기", "대기가 심",
        ],
    },
    "상담": {
        "긍정": [
            "자세한 설명", "설명 잘", "설명을 잘", "상담 잘",
            "꼼꼼한 상담", "꼼꼼하게 설명", "상세한 설명",
            "신뢰", "신뢰가 가", "신뢰가 생", "믿음직",
            "상세", "상세하게", "자세히",
            "설명이 친절", "친절하게 설명", "이해하기 쉽게",
            "궁금한 점", "궁금증을 해결", "질문에 잘 답",
            "원장님이 직접", "원장님이 자세히", "의사선생님이 친절",
            "상담이 만족", "상담이 좋았", "상담 후 신뢰",
            "전문적인 상담", "전문성 있는 상담",
            "피부 상태 설명", "시술 설명", "부작용 설명",
        ],
        "부정": [
            "설명 없", "설명이 없", "설명 안 해줘", "안내 없",
            "상담 부족", "상담이 부실", "상담이 짧았",
            "불안", "불안했", "불안하게",
            "설명이 부족", "설명 부족", "이해가 안 되게",
            "질문 무시", "질문에 답 안", "무성의한 상담",
            "형식적인 상담", "대충 설명", "급하게 끝냈",
            "원장님이 바빠 보여", "바쁜 듯", "성의없이",
        ],
    },
    "가격": {
        "긍정": [
            "합리적", "합리적인 가격", "가격이 합리적",
            "저렴", "저렴해", "저렴한 편", "가격이 저렴",
            "가성비", "가성비 좋", "가성비 최고",
            "적당", "적당한 가격", "가격이 적당",
            "부담없", "부담 없", "부담이 없", "가격이 부담없",
            "착한 가격", "가격이 착해", "저렴한 가격",
            "이벤트", "할인", "프로모션", "쿠폰",
            "가격 대비", "금액 대비", "돈값",
        ],
        "부정": [
            "비싸", "비쌌", "비싼 편", "가격이 비싸",
            "과도", "과도한 비용", "과도한 가격",
            "바가지", "바가지 씌워", "바가지 요금",
            "부담", "부담스럽", "가격이 부담", "비용이 부담",
            "너무 비싸", "많이 비싸", "지나치게 비싸",
            "돈 아깝", "돈이 아깝", "가격 대비 별로",
            "가성비 나쁘", "가성비 최악", "비용이 과해",
            "추가 비용", "추가 요금", "예상보다 비쌌",
        ],
    },
    "예약편의": {
        "긍정": [
            "예약 편리", "예약이 쉽", "예약이 간편",
            "예약 시스템 좋", "앱 편리", "온라인 예약 편리",
            "예약 잘 됨", "예약이 잘", "예약 잡기 쉽",
            "전화 연결 잘", "전화 응대 좋",
        ],
        "부정": [
            "예약이 어렵", "예약하기 힘들", "예약이 안 됨",
            "전화 안 받", "전화 연결 안", "전화 통화 어렵",
            "예약 취소", "예약이 복잡", "예약 시스템 불편",
            "콜센터 연결 안", "대기 중 끊김",
        ],
    },
    "주차편의": {
        "긍정": [
            "주차 편리", "주차 넓", "주차 공간 넓",
            "주차하기 편", "주차가 편리", "주차 여유",
            "발렛", "주차 요원", "주차 안내",
        ],
        "부정": [
            "주차 불편", "주차 어렵", "주차 공간 없",
            "주차 공간 부족", "주차 협소", "주차가 힘들",
            "주차 못", "주차 자리 없", "주차 문제",
            "주차비 비싸", "주차 요금 비싸",
        ],
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
            예약편의          REAL,
            주차편의          REAL,
            전체점수          REAL,
            긍정키워드         TEXT,
            부정키워드         TEXT,
            총리뷰수          INTEGER,
            UNIQUE(branch_name, analysis_date)
        )
    """)
    for col in ["예약편의", "주차편의"]:
        try:
            cur.execute(f"ALTER TABLE analysis_results ADD COLUMN {col} REAL")
        except Exception:
            pass
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

    # review_type 컬럼 존재 여부 확인
    cur.execute("PRAGMA table_info(naver_reviews)")
    columns = [row[1] for row in cur.fetchall()]

    if "review_type" in columns:
        cur.execute("""
            SELECT id, content, review_type
            FROM naver_reviews
            WHERE branch_name = ? AND content IS NOT NULL AND length(content) > 5
        """, (branch_name,))
        rows = cur.fetchall()
        conn.close()
        return [{"id": r[0], "content": r[1], "type": r[2]} for r in rows]
    else:
        cur.execute("""
            SELECT id, content
            FROM naver_reviews
            WHERE branch_name = ? AND content IS NOT NULL AND length(content) > 5
        """, (branch_name,))
        rows = cur.fetchall()
        conn.close()
        return [{"id": r[0], "content": r[1], "type": "unknown"} for r in rows]


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

    for 항목 in ["친절도", "시술효과", "청결도", "대기시간", "상담", "가격", "예약편의", "주차편의"]:
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
        "친절도":  item_scores.get("친절도"),
        "시술효과": item_scores.get("시술효과"),
        "청결도":  item_scores.get("청결도"),
        "대기시간": item_scores.get("대기시간"),
        "상담":    item_scores.get("상담"),
        "가격":    item_scores.get("가격"),
        "예약편의": item_scores.get("예약편의"),
        "주차편의": item_scores.get("주차편의"),
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
           친절도, 시술효과, 청결도, 대기시간, 상담, 가격, 예약편의, 주차편의,
           전체점수, 긍정키워드, 부정키워드, 총리뷰수)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
