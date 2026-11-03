"""지금 있는 곳 주변의 실제 식당 (OpenStreetMap, Overpass API).

키가 필요 없고 무료다. 식당의 요리 종류(cuisine 태그)로 대표 메뉴를 붙여서,
자유 식사 화면에서 사람마다 먹을 메뉴와 닮은꼴을 미리 보여 준다.
기다림과 식사 시간은 가게 종류별 어림값이다.
"""
import math
import os
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import httpx

from . import world

ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
             "https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
UA = {"User-Agent": "moshigo-mvp/0.1 (SVC Seoul AI hackathon demo)"}

# 요리 종류 -> (한국어 이름, 대표 메뉴(세계 음식 표의 이름))
CUISINE = {
    "korean": ("한식", ["비빔밥", "된장찌개", "불고기", "김치찌개"]),
    "japanese": ("일식", ["초밥", "라멘", "닭꼬치", "일본 카레"]),
    "sushi": ("초밥", ["초밥"]),
    "ramen": ("라멘", ["라멘"]),
    "chinese": ("중식", ["볶음밥", "딤섬"]),
    "dim_sum": ("딤섬", ["딤섬"]),
    "vietnamese": ("베트남 음식", ["쌀국수"]),
    "thai": ("태국 음식", ["팟타이", "똠얌꿍"]),
    "italian": ("이탈리아 음식", ["토마토 파스타", "크림 파스타", "마르게리타 피자", "리조또"]),
    "pizza": ("피자", ["마르게리타 피자"]),
    "pasta": ("파스타", ["토마토 파스타", "크림 파스타"]),
    "french": ("프랑스 음식", ["비프 스튜", "오믈렛", "감자 그라탱", "크레페"]),
    "crepe": ("크레페", ["크레페"]),
    "burger": ("햄버거", ["햄버거", "감자튀김"]),
    "american": ("미국 음식", ["햄버거", "스테이크", "감자튀김"]),
    "steak_house": ("스테이크", ["스테이크"]),
    "chicken": ("치킨", ["치킨너겟", "감자튀김"]),
    "fried_chicken": ("치킨", ["치킨너겟", "감자튀김"]),
    "mexican": ("멕시코 음식", ["타코"]),
    "seafood": ("해산물", ["해물파전", "연어 스테이크", "홍합탕"]),
    "fish": ("생선 요리", ["생선구이", "연어 스테이크"]),
    "noodle": ("국수", ["칼국수", "쌀국수"]),
    "curry": ("카레", ["일본 카레"]),
    "sandwich": ("샌드위치", ["치즈 토스트"]),
    "breakfast": ("아침 식사", ["오믈렛", "치즈 토스트"]),
    "cake": ("디저트", ["치즈케이크", "푸딩"]),
    "dessert": ("디저트", ["치즈케이크", "푸딩", "크레페"]),
    "bunsik": ("분식", ["떡볶이", "김치찌개", "비빔밥"]),
}
# 가게 종류 -> (이름, 기다림, 식사 시간 어림값)
AMENITY = {"restaurant": ("식당", 10, 45), "fast_food": ("빨리 먹는 집", 5, 20), "cafe": ("카페", 5, 30)}

# 세계 음식 표의 주재료만으로 알 수 없는 재료 (알레르기 확인용, 일반적인 조리법 기준 짐작)
EXTRA = {
    "팟타이": ["견과류", "갑각류", "달걀"], "똠얌꿍": ["갑각류"], "크림 파스타": ["우유"], "치즈케이크": ["우유", "달걀", "밀가루"],
    "푸딩": ["우유"], "리조또": ["우유"], "마르게리타 피자": ["우유"], "라멘": ["돼지고기", "달걀"], "딤섬": ["밀가루", "갑각류"],
    "햄버거": ["밀가루"], "오믈렛": ["우유"], "클램 차우더": ["우유"], "감자 그라탱": ["우유"], "시저 샐러드": ["달걀", "우유"],
    "칼국수": ["조개류"], "해물파전": ["밀가루", "달걀"], "치즈 토스트": ["우유"], "크레페": ["우유", "달걀"], "볶음밥": ["달걀"],
    "비빔밥": ["달걀"], "잡채": ["돼지고기"], "치킨너겟": ["밀가루"], "타코": ["밀가루"], "일본 카레": ["밀가루"],
}
BY_INGREDIENT = {"소고기": ["소고기"], "돼지고기": ["돼지고기"], "닭고기": ["닭고기"], "생선": ["생선"], "조개류": ["조개류"],
                 "해산물": ["갑각류", "조개류"], "달걀": ["달걀"], "밀가루": ["밀가루"], "빵": ["밀가루", "우유"], "치즈": ["우유"]}


DAYS = {"Mo": "월", "Tu": "화", "We": "수", "Th": "목", "Fr": "금", "Sa": "토", "Su": "일", "PH": "공휴일"}


def hours_ko(h):
    """OSM 영업시간(Mo-Fr 09:00-18:00; Sa off)을 우리말로."""
    import re
    h = re.sub(r"\b(Mo|Tu|We|Th|Fr|Sa|Su|PH)\b", lambda m: DAYS[m.group(1)], h or "")
    return h.replace(" off", " 쉬어요").replace("off", "쉬어요").replace("; ", ", ").replace(";", ", ").replace("-", "~")


def dish(food):
    _, vec, ing, cook, aroma, texture = world.WORLD[food]
    return {"name_ko": food, "taste": list(vec), "ingredient": ing, "cooking": cook, "aroma_kw": aroma,
            "contains": sorted(set(BY_INGREDIENT.get(ing, []) + EXTRA.get(food, [])))}


def _dist(a_lat, a_lng, b_lat, b_lng):
    r = 6371000
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b_lng - a_lng) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _overpass(url, q):
    r = httpx.post(url, data={"data": q}, headers=UA, timeout=35)
    r.raise_for_status()
    return r.json().get("elements", [])


def fetch(lat, lng, radius=900, limit=80):
    """Overpass에서 주변 식당, 패스트푸드, 카페를 가져온다. 공개 서버가 느려서 여러 곳에 동시에 묻고 먼저 온 답을 쓴다."""
    q = f"""[out:json][timeout:25];
(node(around:{radius},{lat},{lng})[amenity~"^(restaurant|fast_food|cafe)$"][name];
 way(around:{radius},{lat},{lng})[amenity~"^(restaurant|fast_food|cafe)$"][name];);
out center {limit};"""
    pool = ThreadPoolExecutor(len(ENDPOINTS))
    futs = [pool.submit(_overpass, u, q) for u in ENDPOINTS]
    last, pending = None, set(futs)
    try:
        while pending:
            done, pending = wait(pending, timeout=40, return_when=FIRST_COMPLETED)
            if not done:
                break
            for f in done:
                try:
                    return f.result()
                except Exception as e:  # 다음으로 빨리 끝나는 서버를 기다린다
                    last = e
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    raise RuntimeError(f"Overpass 실패: {last!r}")


# ---------- 카카오 로컬 (한국 안에서, 키가 있을 때) ----------
KAKAO_CAT = [("한식", "korean"), ("일식", "japanese"), ("초밥", "sushi"), ("라멘", "ramen"), ("중식", "chinese"), ("베트남", "vietnamese"),
             ("태국", "thai"), ("이탈리", "italian"), ("피자", "pizza"), ("파스타", "pasta"), ("프랑스", "french"), ("햄버거", "burger"),
             ("패스트푸드", "burger"), ("스테이크", "steak_house"), ("치킨", "chicken"), ("멕시칸", "mexican"), ("해물", "seafood"),
             ("생선", "fish"), ("회", "fish"), ("국수", "noodle"), ("카레", "curry"), ("샌드위치", "sandwich"), ("분식", "bunsik"),
             ("디저트", "dessert"), ("양식", "american")]


def in_korea(lat, lng):
    return 33.0 <= lat <= 38.9 and 124.5 <= lng <= 131.9


def kakao_available():
    return bool(os.environ.get("KAKAO_REST_KEY"))


def fetch_kakao(lat, lng, radius=900, pages=3):
    """카카오 로컬 카테고리 검색(FD6 음식점). 카카오 형식을 Overpass 형식과 같은 모양으로 바꿔 돌려준다."""
    out = []
    for page in range(1, pages + 1):
        r = httpx.get("https://dapi.kakao.com/v2/local/search/category.json", timeout=10,
                      headers={"Authorization": f"KakaoAK {os.environ['KAKAO_REST_KEY']}"},
                      params={"category_group_code": "FD6", "x": lng, "y": lat, "radius": radius, "sort": "distance", "page": page, "size": 15})
        r.raise_for_status()
        js = r.json()
        for d in js.get("documents", []):
            cat = d.get("category_name", "")
            cuisines = [key for word, key in KAKAO_CAT if word in cat]
            out.append({"type": "kakao", "id": d["id"], "lat": float(d["y"]), "lon": float(d["x"]),
                        "tags": {"name": d["place_name"], "amenity": "restaurant", "cuisine": ";".join(cuisines[:2]),
                                 "category": cat.split(" > ")[-1] if cat else "", "url": d.get("place_url", "")}})
        if js.get("meta", {}).get("is_end", True):
            break
    return out


# ---------- Geoapify (전 세계, OpenStreetMap 기반, 키가 있을 때) ----------
def geoapify_available():
    return bool(os.environ.get("GEOAPIFY_KEY"))


def fetch_geoapify(lat, lng, radius=900, limit=80):
    r = httpx.get("https://api.geoapify.com/v2/places", timeout=12, params={
        "categories": "catering.restaurant,catering.fast_food,catering.cafe", "filter": f"circle:{lng},{lat},{radius}",
        "bias": f"proximity:{lng},{lat}", "limit": limit, "apiKey": os.environ["GEOAPIFY_KEY"]})
    r.raise_for_status()
    out = []
    for f in r.json().get("features", []):
        pr = f.get("properties", {})
        if not pr.get("name"):
            continue
        cats = pr.get("categories", [])
        amen = "fast_food" if any(c.startswith("catering.fast_food") for c in cats) else "cafe" if any(c.startswith("catering.cafe") for c in cats) else "restaurant"
        cuisines = sorted({c.split(".")[2] for c in cats if c.count(".") >= 2 and c.startswith("catering.")})
        raw = (pr.get("datasource") or {}).get("raw") or {}
        out.append({"type": "geoapify", "id": pr.get("place_id", "")[:24], "lat": pr["lat"], "lon": pr["lon"],
                    "tags": {"name": pr["name"], "name:ko": raw.get("name:ko", ""), "amenity": amen,
                             "cuisine": raw.get("cuisine") or ";".join(cuisines), "opening_hours": pr.get("opening_hours", "")}})
    return out


def find(lat, lng, radius=900):
    """주변 식당 원본과 출처 이름. 한국 안이면 카카오(키가 있을 때), 다음은 Geoapify(키가 있을 때), 마지막으로 Overpass."""
    if kakao_available() and in_korea(lat, lng):
        try:
            return "카카오맵", fetch_kakao(lat, lng, radius)
        except Exception as e:
            print(f"[nearby] 카카오 실패: {e!r}")
    if geoapify_available():
        try:
            return "OpenStreetMap (Geoapify)", fetch_geoapify(lat, lng, radius)
        except Exception as e:
            print(f"[nearby] Geoapify 실패: {e!r}")
    return "OpenStreetMap", fetch(lat, lng, radius)


def to_places(elements, lat, lng):
    """Overpass 결과 -> 자유 식사 계산용 식당 목록."""
    out = []
    for el in elements:
        t = el.get("tags", {})
        la = el.get("lat") or (el.get("center") or {}).get("lat")
        lo = el.get("lon") or (el.get("center") or {}).get("lon")
        if la is None or lo is None:
            continue
        amen = AMENITY.get(t.get("amenity"), AMENITY["restaurant"])
        cuisines = [c.strip().lower() for c in (t.get("cuisine") or "").split(";") if c.strip()]
        label, foods = None, []
        for c in cuisines:
            if c in CUISINE:
                label = label or CUISINE[c][0]
                foods += [f for f in CUISINE[c][1] if f not in foods]
        if not foods and t.get("amenity") == "cafe":
            label, foods = "카페", ["치즈케이크", "크레페"]
        if not label and t.get("category"):
            label = t["category"]
        name = t.get("name:ko") or t.get("name")
        sub = t.get("name") if t.get("name:ko") and t.get("name") != t.get("name:ko") else ""
        out.append({
            "id": f"osm{el.get('type', 'n')[0]}{el.get('id')}", "name": name, "orig_name": sub,
            "kind": label or amen[0], "lat": la, "lng": lo, "wait_min": amen[1], "meal_min": amen[2],
            "price": "", "note": ("영업시간: " + hours_ko(t["opening_hours"])) if t.get("opening_hours") else "", "url": t.get("url", ""),
            "dishes": [dish(f) for f in foods[:4]], "distance_m": round(_dist(lat, lng, la, lo)),
        })
    return out
