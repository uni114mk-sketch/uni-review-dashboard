"""
[Step 2] 구글 맵 리뷰 수집기 (Google Places API)
==================================================
사용법:
  pip install requests

  1. Google Cloud Console (console.cloud.google.com)에서 프로젝트 생성
  2. "Places API (New)" 활성화
  3. API 키 발급 → 아래 GOOGLE_API_KEY에 입력
  4. python 02_google_scraper.py

비용:
  월 $200 무료 크레딧 제공.
  Place Details 1회 = $0.017 / 43개 지점 × 주 1회 × 4주 ≈ $2.9/월 → 무료 범위 내
"""

import json
import sqlite3
import requests
import time
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────
# 설정
# ──────────────────────────────────────────
GOOGLE_API_KEY = "AIzaSyC75mP62UG__0KG1Ys-pe48ea1cFcYAIBs"   # ← Google API 키 입력

BRANCHES = {
    "강남점":  "ChIJqXgJdQCjfDUR09hdYqbWpWI",   # ← Google Place ID로 교체
    "선릉점":    "ChIJdeBklhGkfDURsuskWRgT5Dk",   # 찾는 법: maps.googleapis.com/maps/api/place/findplacefromtext/json?input=강남피부과&inputtype=textquery&key=YOUR_KEY
    "잠실점":    "ChIJR1VORB2lfDURMtuLFoVTjFI",
    "왕십리점":    "ChIJt5S1RtKjfDUR13EtgO5Se-o",
    "명동점":    "ChIJ_TWSAeajfDUR3YjA1n2R-2g",
    "홍대신촌점":    "ChIJ6eN1Ov6ZfDUR7Il0afHrvZE",
    "영등포점":    "ChIJxab1sbuffDURt2-SPWNKb7Q",
    "마곡점":    "ChIJV9Zg_uedfDURabf2qkGy7qE",
    "건대점":    "ChIJy9moa9-lfDURuVvvP1y-ER8",
    "구로점":    "ChIJsURvGMGffDUR3Lwg8JikUGA",
    "여의도점":    "ChIJhyToqViffDURPKzzt5MJTRk",
    "천호점":    "ChIJE7xDBQClfDURIkUq_Xlr7XI",
    "목동점":    "ChIJacPma82ffDURfFQPg2Lf_Qc",
    "창동점":    "ChIJj8jlBGe5fDURuLV0nwMHxK0",
    "수원점":    "ChIJUzfmbV1DezURDay7-b0O0KA",
    "판교점":    "ChIJZ70wn_qnfDURBjJGS4xdTrM",
    "광교점":    "ChIJI3bTaGpbezURsuz1PgTgVdg",
    "광명점":    "ChIJ-yXf-AFhezURBDjBZ5GOoBQ",
    "산본점":    "ChIJrarEpYZnezURskavQnh__3o",
    "부천점":    "ChIJ6ZNfdu19ezURnvHVEYcErew",
    "일산점":    "ChIJqdtzIAGFfDURuRprxFgRdNc",
    "다산점":    "ChIJpauB_d-3fDURHoI-025hrKk",
    "김포점":    "ChIJL1KoIR-BfDURo7jiL2KaE78",
    "인천검단점":    "ChIJDRM35VGDfDURWyY_cVjTbnU",
    "동탄점":    "ChIJ5RbhuNBHezURKN4rYXMeYWY",
    "평택점":    "ChIJlduGoyo7ezURBVplX_JeSXs",
    "안양점":    "ChIJC9qXcuhhezURVrv7KCRFiaE",
    "부평점":    "ChIJvzqgVOJ9ezURvPy073QHud0",
    "안산점":    "ChIJjXUjk9BvezURuUvtkNMlMk4",
    "의정부점":    "ChIJX2DGB2_HfDURanXEzJb0fUI",
    "시흥배곧점":    "ChIJ63gvZRxxezUR9nYPNhqywb4",
    "분당미금점":    "ChIJuVoGOSlZezURudFpfEb4Sl4",
    "과천점":    "ChIJk1Ug_YdfezURTi1rv9VVKhQ",
    "하남미사점":    "ChIJPchvsNSxfDURH7DJfnhEUGQ",
    "화성봉담점":    "ChIJzypRL-ZrezUR-8ds0xha1vo",
    "경기광주점":    "ChIJI_f1R9irfDURB-wDbflCi6s",
    "천안점":    "ChIJuyACApYnezURbghHzhO6nv8",
    "대전점":    "ChIJQ4IjCvxLZTURo0OOZ9sJGyM",
    "광주점":    "ChIJk7NhPgOJcTURiseA3BTVI-o",
    "목포점":    "ChIJJ2QWAHCxczURXuuY3fMKO4Q",
    "대구점":    "ChIJ9Y2aPdPjZTURIKKEb3dNsJU",
    "부산점":    "ChIJe_vFRRzraDURYQwHRrToBrA",
    "창원점":    "ChIJhwo028rNaDURNyJxzuz9HpE",
}

DB_PATH = "reviews.db"
DELAY_BETWEEN_REQUESTS = 1.0   # API 요청 간 딜레이 (초)


# ──────────────────────────────────────────
# DB 초기화 (01_naver_scraper.py와 동일 DB 공유)
# ──────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # 네이버와 동일 테이블 (source 컬럼으로 구분)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS naver_reviews (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_name TEXT    NOT NULL,
            place_id    TEXT    NOT NULL,
            review_id   TEXT    UNIQUE,
            reviewer    TEXT,
            rating      REAL,
            content     TEXT,
            visit_date  TEXT,
            source      TEXT DEFAULT 'google',
            collected_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.commit()
    conn.close()


def save_reviews(reviews: list[dict]) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    saved = 0
    for r in reviews:
        try:
            cur.execute("""
                INSERT OR IGNORE INTO naver_reviews
                  (branch_name, place_id, review_id, reviewer, rating, content, visit_date, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["branch_name"], r["place_id"], r["review_id"],
                r.get("reviewer", ""), r.get("rating"),
                r.get("content", ""), r.get("visit_date", ""), "google"
            ))
            if cur.rowcount:
                saved += 1
        except Exception as e:
            print(f"  ⚠️  저장 실패: {e}")
    conn.commit()
    conn.close()
    return saved


# ──────────────────────────────────────────
# Google Place ID 자동 검색 도우미
# ──────────────────────────────────────────
def find_place_id(branch_name: str) -> str | None:
    """
    지점명으로 Google Place ID를 자동 검색합니다.
    BRANCHES 딕셔너리에 Place ID가 없을 때 사용하세요.
    """
    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        "input": f"{branch_name} 피부과",
        "inputtype": "textquery",
        "fields": "place_id,name,formatted_address",
        "language": "ko",
        "key": GOOGLE_API_KEY,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        candidates = data.get("candidates", [])
        if candidates:
            place = candidates[0]
            print(f"  🔍 '{branch_name}' → {place.get('name')} ({place.get('formatted_address')})")
            print(f"      Place ID: {place.get('place_id')}")
            return place.get("place_id")
    except Exception as e:
        print(f"  ❌ Place ID 검색 실패: {e}")
    return None


# ──────────────────────────────────────────
# 구글 맵 리뷰 수집
# ──────────────────────────────────────────
def fetch_google_reviews(branch_name: str, place_id: str) -> list[dict]:
    """
    Google Places API (New)로 리뷰를 가져옵니다.
    최대 5개의 최신 리뷰 반환 (Google API 정책 제한).
    """
    if not place_id or place_id.startswith("ChIJxxx"):
        print(f"  ⏭️  {branch_name}: Place ID 미설정, 건너뜀")
        return []

    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "displayName,rating,reviews,userRatingCount",
        "Accept-Language": "ko",
    }

    reviews = []
    try:
        resp = requests.get(url, headers=headers, timeout=15)

        if resp.status_code == 403:
            print(f"  ❌ API 키 오류 또는 Places API 미활성화 (403)")
            return []
        if resp.status_code != 200:
            print(f"  ❌ API 오류 ({resp.status_code}): {resp.text[:200]}")
            return []

        data = resp.json()
        raw_reviews = data.get("reviews", [])

        print(f"  📍 {branch_name}: 전체 평점 {data.get('rating', '?')}★, 리뷰 {data.get('userRatingCount', 0)}개 중 최근 {len(raw_reviews)}개 수집")

        for r in raw_reviews:
            # 리뷰 텍스트 (언어별로 여러 개 있는 경우 한국어 우선)
            text_obj = r.get("originalText") or r.get("text") or {}
            content = text_obj.get("text", "") if isinstance(text_obj, dict) else str(text_obj)

            # 작성자
            author_attr = r.get("authorAttribution") or {}
            author = author_attr.get("displayName", "") if isinstance(author_attr, dict) else ""

            # 별점
            rating = r.get("rating")

            # 작성 시간
            publish_time = r.get("publishTime") or r.get("relativePublishTimeDescription", "")

            if not content:
                continue

            reviews.append({
                "branch_name": branch_name,
                "place_id":    place_id,
                "review_id":   f"g_{place_id}_{hash(content) % 10**8}",
                "reviewer":    author,
                "rating":      float(rating) if rating else None,
                "content":     content[:1000],
                "visit_date":  str(publish_time),
            })

    except requests.exceptions.ConnectionError:
        print(f"  ❌ {branch_name}: 네트워크 연결 오류")
    except Exception as e:
        print(f"  ❌ {branch_name} 오류: {e}")

    return reviews


# ──────────────────────────────────────────
# 메인 실행
# ──────────────────────────────────────────
def main():
    init_db()

    if GOOGLE_API_KEY == "YOUR_GOOGLE_API_KEY_HERE":
        print("⚠️  GOOGLE_API_KEY를 설정해주세요.")
        print("   Google Cloud Console → API 및 서비스 → 사용자 인증 정보 → API 키 생성")
        print("   활성화 필요: Places API (New)\n")
        print("   [테스트용] Place ID 자동 검색 기능도 포함되어 있습니다:")
        print("   find_place_id('강남본점') 함수를 호출하면 Place ID를 자동으로 찾아줍니다.\n")
        return

    total_saved = 0
    start = time.time()

    print(f"\n🚀 구글 맵 리뷰 수집 시작 ({len(BRANCHES)}개 지점)")
    print(f"   수집 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    for branch_name, place_id in BRANCHES.items():
        reviews = fetch_google_reviews(branch_name, place_id)
        if reviews:
            saved = save_reviews(reviews)
            total_saved += saved
            print(f"     💾 DB 저장: {saved}건 (신규)\n")

        time.sleep(DELAY_BETWEEN_REQUESTS)

    elapsed = time.time() - start
    print(f"\n{'='*50}")
    print(f"✅ 구글 맵 수집 완료!")
    print(f"   총 저장 리뷰: {total_saved}건")
    print(f"   소요 시간: {elapsed:.1f}초")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
# 02_google_scraper.py 맨 아래에 추가 # (GOOGLE_API_KEY는 이미 입력되어 있어야 함) if __name__ == "__main__": # 찾고 싶은 지점명을 아래에 입력 branches_to_find = [ "강남 ○○피부과", "판교 ○○피부과", "홍대 ○○피부과", ] for name in branches_to_find: find_place_id(name)
