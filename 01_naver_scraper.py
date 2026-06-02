"""
[Step 1] 네이버 플레이스 리뷰 수집기
======================================
사용법:
  pip install playwright
  playwright install chromium

  python 01_naver_scraper.py

설정:
  아래 BRANCHES 딕셔너리에 지점명과 네이버 플레이스 ID를 입력하세요.
  플레이스 ID 찾는 법: 네이버 지도에서 지점 검색 →
  URL의 숫자 부분 (예: map.naver.com/v5/entry/place/12345678 → ID는 12345678)
"""

import asyncio
import json
import sqlite3
import time
import random
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# ──────────────────────────────────────────
# 설정: 지점명과 네이버 플레이스 ID 입력
# ──────────────────────────────────────────
BRANCHES = {
    "강남점":  "1380019560",   # ← 실제 플레이스 ID로 교체
    "선릉점":    "11824279",
    "잠실점":    "32811697",
    "왕십리점":    "35978118",
    "명동점":    "1528320866",
    "홍대신촌점":    "37191986",
    "영등포점":    "1344800595",
    "마곡점":    "1876125206",
    "건대점":    "1673849098",
    "구로점":    "1956327823",
    "여의도점":    "2039367298",
    "천호점":    "1745821822",
    "목동점":    "1671998280",
    "창동점":    "2088950489",
    "수원점":    "31357745",
    "판교점":    "19759020",
    "광교점":    "36459230",
    "광명점":    "1272941044",
    "산본점":    "1034968463",
    "부천점":    "1205197562",
    "일산점":    "1143822491",
    "다산점":    "1141558661",
    "김포점":    "1004278834",
    "인천검단점":    "1972573916",
    "동탄점":    "1038492092",
    "평택점":    "1030321220",
    "안양점":    "1748810288",
    "부평점":    "1423653907",
    "안산점":    "1885575644",
    "의정부점":    "1080757415",
    "시흥배곧점":    "1110806334",
    "분당미금점":    "2063670518",
    "과천점":    "2075168322",
    "하남미사점":    "2011887103",
    "화성봉담점":    "2070376316",
    "경기광주점":    "2043187950",
    "천안점":    "1945459743",
    "대전점":    "1766981596",
    "광주점":    "1900027173",
    "목포점":    "1282048809",
    "대구점":    "1546398821",
    "부산점":    "1321788535",
    "창원점":    "1465131782",
    
    # 나머지 지점 동일한 형식으로 추가...
}

MAX_REVIEWS_PER_BRANCH = 50   # 지점당 최대 수집 리뷰 수
DELAY_MIN = 2.0               # 요청 간 최소 딜레이 (초) — 서버 부하 방지
DELAY_MAX = 4.0               # 요청 간 최대 딜레이 (초)
DB_PATH = "reviews.db"        # SQLite DB 파일 경로

# ──────────────────────────────────────────
# DB 초기화
# ──────────────────────────────────────────
def init_db():
    """SQLite DB 및 테이블 생성"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS naver_reviews (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_name TEXT    NOT NULL,
            place_id    TEXT    NOT NULL,
            review_id   TEXT    UNIQUE,          -- 중복 방지용
            reviewer    TEXT,
            rating      REAL,
            content     TEXT,
            visit_date  TEXT,
            source      TEXT DEFAULT 'naver',
            collected_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.commit()
    conn.close()
    print("✅ DB 초기화 완료:", DB_PATH)


def save_reviews(reviews: list[dict]):
    """리뷰 리스트를 DB에 저장 (중복 자동 무시)"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    saved = 0
    for r in reviews:
        try:
            cur.execute("""
                INSERT OR IGNORE INTO naver_reviews
                  (branch_name, place_id, review_id, reviewer, rating, content, visit_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                r["branch_name"],
                r["place_id"],
                r.get("review_id", ""),
                r.get("reviewer", ""),
                r.get("rating"),
                r.get("content", ""),
                r.get("visit_date", ""),
            ))
            if cur.rowcount:
                saved += 1
        except Exception as e:
            print(f"  ⚠️  저장 실패: {e}")
    conn.commit()
    conn.close()
    return saved


# ──────────────────────────────────────────
# 네이버 플레이스 리뷰 스크래퍼
# ──────────────────────────────────────────
async def scrape_branch(page, branch_name: str, place_id: str) -> list[dict]:
    """
    네이버 플레이스 모바일 페이지에서 리뷰를 수집합니다.
    m.place.naver.com 은 내부 JSON API를 호출하므로
    네트워크 요청을 인터셉트해 직접 파싱합니다.
    """
    reviews = []
    api_data_store = []  # 인터셉트된 API 응답 저장

    # ── 내부 API 응답 인터셉트 설정 ──
    async def handle_response(response):
        if "graphql" in response.url or "visitorReview" in response.url:
            try:
                body = await response.json()
                api_data_store.append(body)
            except Exception:
                pass

    page.on("response", handle_response)

    url = f"https://m.place.naver.com/hospital/{place_id}/review/visitor"
    print(f"  📍 {branch_name} ({place_id}) 접속 중...")

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(random.uniform(1.5, 2.5))

        # ── 리뷰 더보기 반복 클릭 (최대 MAX_REVIEWS까지) ──
        collected = 0
        click_count = 0
        max_clicks = MAX_REVIEWS_PER_BRANCH // 10  # 한 번에 약 10개씩 로드

        while click_count < max_clicks:
            # 현재 페이지의 리뷰 파싱
            review_items = await page.query_selector_all(
                "li.pui__X35jYm, li[class*='ReviewItem'], div[class*='review_item']"
            )

            if not review_items:
                # 셀렉터가 변경된 경우 대체 셀렉터 시도
                review_items = await page.query_selector_all(
                    "li[data-v-app] > div, .reviewer_info, [class*='pui__']"
                )

            for item in review_items:
                try:
                    # 텍스트 내용 추출
                    content_el = await item.query_selector(
                        "[class*='ReviewContent'], [class*='review_text'], span.pui__xtsQN"
                    )
                    content = ""
                    if content_el:
                        content = (await content_el.inner_text()).strip()
                    elif await item.inner_text():
                        content = (await item.inner_text()).strip()[:500]

                    # 별점 추출
                    rating_el = await item.query_selector(
                        "[class*='Rating'], [class*='star'], em.pui__"
                    )
                    rating_text = ""
                    if rating_el:
                        rating_text = (await rating_el.inner_text()).strip()

                    # 작성자 추출
                    author_el = await item.query_selector(
                        "[class*='reviewer'], [class*='author'], span.pui__"
                    )
                    author = ""
                    if author_el:
                        author = (await author_el.inner_text()).strip()

                    if content and len(content) > 5:
                        review_id = f"{place_id}_{hash(content) % 10**8}"
                        reviews.append({
                            "branch_name": branch_name,
                            "place_id":    place_id,
                            "review_id":   review_id,
                            "reviewer":    author,
                            "rating":      _parse_rating(rating_text),
                            "content":     content,
                            "visit_date":  "",
                        })
                        collected += 1

                except Exception:
                    continue

            # API 인터셉트 데이터에서도 추출 시도
            for data in api_data_store:
                extracted = _extract_from_api(data, branch_name, place_id)
                reviews.extend(extracted)
            api_data_store.clear()

            # 중복 제거
            seen = set()
            unique = []
            for r in reviews:
                if r["review_id"] not in seen:
                    seen.add(r["review_id"])
                    unique.append(r)
            reviews = unique

            if len(reviews) >= MAX_REVIEWS_PER_BRANCH:
                break

            # 더보기 버튼 클릭
            more_btn = await page.query_selector(
                "a.pui__load_more, button[class*='more'], a[class*='more_btn']"
            )
            if not more_btn:
                break

            await more_btn.click()
            await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
            click_count += 1

    except Exception as e:
        print(f"  ❌ {branch_name} 스크래핑 오류: {e}")

    # 이벤트 핸들러 해제
    page.remove_listener("response", handle_response)

    print(f"  ✅ {branch_name}: {len(reviews)}건 수집")
    return reviews[:MAX_REVIEWS_PER_BRANCH]


def _parse_rating(text: str) -> float | None:
    """별점 텍스트에서 숫자 추출"""
    if not text:
        return None
    import re
    nums = re.findall(r"[\d.]+", text)
    if nums:
        val = float(nums[0])
        if val > 5:
            val = val / 10  # 10점 만점인 경우 변환
        return min(5.0, max(1.0, val))
    return None


def _extract_from_api(data: dict, branch_name: str, place_id: str) -> list[dict]:
    """인터셉트된 내부 API JSON에서 리뷰 데이터 추출"""
    reviews = []
    if not isinstance(data, dict):
        return reviews

    # 네이버 플레이스 내부 API 구조 탐색 (구조는 변경될 수 있음)
    candidates = []

    def find_reviews(obj, depth=0):
        if depth > 8 or not obj:
            return
        if isinstance(obj, list):
            for item in obj:
                find_reviews(item, depth + 1)
        elif isinstance(obj, dict):
            # 리뷰 항목으로 보이는 키 탐색
            if any(k in obj for k in ["body", "reviewBody", "reviewContent", "text"]):
                candidates.append(obj)
            for v in obj.values():
                find_reviews(v, depth + 1)

    find_reviews(data)

    for item in candidates:
        content = (
            item.get("body") or
            item.get("reviewBody") or
            item.get("reviewContent") or
            item.get("text", "")
        )
        if not content or len(str(content)) < 5:
            continue
        rating = item.get("rating") or item.get("score") or item.get("starScore")
        author = item.get("author") or item.get("writerNickname") or ""
        review_id = str(item.get("id") or item.get("reviewId") or hash(content) % 10**8)

        reviews.append({
            "branch_name": branch_name,
            "place_id":    place_id,
            "review_id":   f"{place_id}_{review_id}",
            "reviewer":    str(author),
            "rating":      float(rating) if rating else None,
            "content":     str(content)[:1000],
            "visit_date":  str(item.get("visitDate") or item.get("visitYearMonth") or ""),
        })

    return reviews


# ──────────────────────────────────────────
# 메인 실행
# ──────────────────────────────────────────
async def main():
    init_db()
    total_saved = 0
    start_time = time.time()

    print(f"\n🚀 네이버 플레이스 리뷰 수집 시작 ({len(BRANCHES)}개 지점)")
    print(f"   수집 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    async with async_playwright() as p:
        # headless=False 로 바꾸면 브라우저 화면이 보입니다 (디버깅용)
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = await browser.new_context(
            # 모바일 User-Agent 설정 (네이버 플레이스는 모바일 페이지가 더 안정적)
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                "Mobile/15E148 Safari/604.1"
            ),
            viewport={"width": 390, "height": 844},
            locale="ko-KR",
        )
        page = await context.new_page()

        for branch_name, place_id in BRANCHES.items():
            reviews = await scrape_branch(page, branch_name, place_id)
            if reviews:
                saved = save_reviews(reviews)
                total_saved += saved
                print(f"     💾 DB 저장: {saved}건 (신규)\n")

            # 지점 간 딜레이 (서버 부하 방지)
            await asyncio.sleep(random.uniform(DELAY_MIN * 1.5, DELAY_MAX * 1.5))

        await browser.close()

    elapsed = time.time() - start_time
    print(f"\n{'='*50}")
    print(f"✅ 수집 완료!")
    print(f"   총 저장 리뷰: {total_saved}건")
    print(f"   소요 시간: {elapsed:.1f}초")
    print(f"   DB 위치: {Path(DB_PATH).absolute()}")
    print(f"{'='*50}\n")

    # 결과 미리보기 출력
    _preview_db()


def _preview_db():
    """수집된 데이터 미리보기"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("📊 수집 결과 미리보기:")
    cur.execute("""
        SELECT branch_name, COUNT(*) as cnt
        FROM naver_reviews
        GROUP BY branch_name
        ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    for branch, cnt in rows:
        print(f"   {branch}: {cnt}건")

    print("\n📝 최신 리뷰 샘플 (3건):")
    cur.execute("""
        SELECT branch_name, rating, substr(content, 1, 80) as preview
        FROM naver_reviews
        ORDER BY collected_at DESC LIMIT 3
    """)
    for row in cur.fetchall():
        print(f"   [{row[0]}] ★{row[1] or '?'} — {row[2]}...")

    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
