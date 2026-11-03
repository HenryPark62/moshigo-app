"""지금 있는 곳 주변의 실제 식당 (OpenStreetMap, Overpass API).

키가 필요 없고 무료다. 식당의 요리 종류(cuisine 태그)로 대표 메뉴를 붙여서,
자유 식사 화면에서 사람마다 먹을 메뉴와 닮은꼴을 미리 보여 준다.
기다림과 식사 시간은 가게 종류별 어림값이다.
"""
import math
import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import httpx

from . import world

ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
             "https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
UA = {"User-Agent": "moshigo-mvp/0.1 (+https://moshigo.onrender.com)", "Accept-Language": "ko,en"}

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
# 요리 종류 태그가 없을 때 가게 이름으로 짐작 (앞에 있는 것이 먼저)
NAME_HINTS = [
    (["쌀국수", "pho", "phở", "베트남"], "vietnamese"), (["팟타이", "태국", "thai"], "thai"),
    (["스시", "초밥", "sushi", "참치", "오마카세"], "sushi"), (["라멘", "ramen", "라면"], "ramen"),
    (["돈까스", "돈카츠", "우동", "이자카야", "덮밥", "규동", "일식"], "japanese"),
    (["반점", "짬뽕", "짜장", "마라", "훠궈", "딤섬", "중식", "중화"], "chinese"),
    (["피자", "pizza", "pizzeria"], "pizza"), (["파스타", "pasta", "trattoria", "이탈리"], "italian"),
    (["버거", "burger", "맥도날드", "롯데리아", "mcdonald"], "burger"), (["치킨", "chicken", "통닭"], "chicken"),
    (["스테이크", "steak"], "steak_house"), (["타코", "taco", "멕시"], "mexican"), (["크레페", "crêpe", "creperie", "crêperie"], "crepe"),
    (["bistro", "bistrot", "brasserie", "비스트로"], "french"), (["샌드위치", "sandwich", "subway", "써브웨이"], "sandwich"),
    (["김밥", "떡볶이", "분식"], "bunsik"), (["칼국수", "국수", "냉면", "noodle"], "noodle"), (["카레", "curry"], "curry"),
    (["횟집", "수산", "해물", "조개", "seafood"], "seafood"),
    (["국밥", "찌개", "갈비", "삼겹", "고기", "불고기", "한정식", "백반", "순대", "곰탕", "설렁탕", "해장국", "보쌈", "족발", "닭갈비",
      "비빔밥", "한식", "식당", "밥집"], "korean"),
]


def guess_cuisine(name):
    n = (name or "").lower()
    for words, key in NAME_HINTS:
        if any(w in n for w in words):
            return key
    return None


# 가게 종류 -> (이름, 기다림, 식사 시간 어림값)
AMENITY = {"restaurant": ("식당", 12, 40), "fast_food": ("빨리 먹는 집", 5, 20), "cafe": ("카페", 5, 30)}
# 요리 종류 -> (주문하고 나오기까지, 먹는 시간) 분. 가게 종류보다 이것을 먼저 쓴다 (치킨은 패스트푸드로 등록돼도 튀기는 데 오래 걸린다)
COOK = {
    "chicken": (20, 30), "fried_chicken": (20, 30), "steak_house": (20, 45), "seafood": (20, 45), "fish": (20, 40),
    "french": (15, 45), "sushi": (15, 40), "pizza": (15, 35), "pasta": (15, 40), "italian": (15, 45), "american": (15, 35),
    "dim_sum": (15, 40), "korean": (12, 40), "japanese": (12, 40), "chinese": (12, 40), "thai": (12, 35), "mexican": (10, 30),
    "ramen": (10, 25), "vietnamese": (8, 25), "noodle": (8, 25), "curry": (8, 25), "bunsik": (7, 20), "crepe": (8, 25),
    "breakfast": (10, 30), "burger": (5, 20), "sandwich": (5, 20), "cake": (3, 25), "dessert": (3, 25),
}

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


# ---------- Nominatim (OpenStreetMap 검색, 키 없음, 빠름) ----------
_NOMI_LOCK = threading.Lock()
_NOMI_LAST = [0.0]


def _nominatim(q, lat, lng, d):
    with _NOMI_LOCK:  # 사용 정책: 1초에 한 번
        gap = time.time() - _NOMI_LAST[0]
        if gap < 1.05:
            time.sleep(1.05 - gap)
        _NOMI_LAST[0] = time.time()
    r = httpx.get("https://nominatim.openstreetmap.org/search", headers=UA, timeout=15, params={
        "q": q, "format": "jsonv2", "limit": 50, "extratags": 1, "namedetails": 1, "bounded": 1,
        "viewbox": f"{lng - d},{lat + d},{lng + d},{lat - d}"})
    r.raise_for_status()
    return r.json()


def fetch_nominatim(lat, lng, radius=900):
    d = radius / 111000 * 1.1
    out, seen = [], set()
    for q in ("restaurant", "fast food"):
        for x in _nominatim(q, lat, lng, d):
            nd, et = x.get("namedetails") or {}, x.get("extratags") or {}
            name = x.get("name") or nd.get("name")
            if not name or x.get("osm_id") in seen:
                continue
            seen.add(x.get("osm_id"))
            out.append({"type": "nominatim", "id": x.get("osm_id"), "lat": float(x["lat"]), "lon": float(x["lon"]),
                        "tags": {"name": name, "name:ko": nd.get("name:ko", ""), "amenity": x.get("type", "restaurant"),
                                 "cuisine": et.get("cuisine", ""), "opening_hours": et.get("opening_hours", "")}})
    return [e for e in out if _dist(lat, lng, e["lat"], e["lon"]) <= radius * 1.2]


def find(lat, lng, radius=900):
    """주변 식당 원본과 출처 이름. 카카오(한국, 키) > Geoapify(키) > Nominatim(무료, 빠름) > Overpass(무료, 느림)."""
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
    try:
        got = fetch_nominatim(lat, lng, radius)
        if got:
            return "OpenStreetMap", got
    except Exception as e:
        print(f"[nearby] Nominatim 실패: {e!r}")
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
        if not any(c in CUISINE for c in cuisines):
            g = guess_cuisine(t.get("name:ko") or "") or guess_cuisine(t.get("name") or "")
            if g:
                cuisines.append(g)
        label, foods = None, []
        for c in cuisines:
            if c in CUISINE:
                label = label or CUISINE[c][0]
                foods += [f for f in CUISINE[c][1] if f not in foods]
        if not foods and t.get("amenity") == "cafe":
            label, foods = "카페", ["치즈케이크", "크레페"]
        if not label and t.get("category"):
            label = t["category"]
        first = next((c for c in cuisines if c in COOK), None)
        cook, meal = COOK[first] if first else (amen[1], amen[2])
        if first == "burger" and t.get("amenity") != "fast_food":  # 수제 버거집은 체인보다 오래 걸린다
            cook, meal = 15, 30
        name = t.get("name:ko") or t.get("name")
        sub = t.get("name") if t.get("name:ko") and t.get("name") != t.get("name:ko") else ""
        out.append({
            "id": f"osm{el.get('type', 'n')[0]}{el.get('id')}", "name": name, "orig_name": sub,
            "kind": label or amen[0], "lat": la, "lng": lo, "wait_min": cook, "meal_min": meal, "sitdown": t.get("amenity") != "fast_food" and first not in ("burger", "sandwich"),
            "price": "", "note": ("영업시간: " + hours_ko(t["opening_hours"])) if t.get("opening_hours") else "", "url": t.get("url", ""),
            "dishes": [dish(f) for f in foods[:4]], "distance_m": round(_dist(lat, lng, la, lo)),
        })
    return out


# ---------- 주변 둘러볼 곳 (공원, 박물관, 볼거리, 놀이터, 전망대) ----------
SPOT_KIND = {  # (분류, 종류) -> (한국어 이름, 묶음)
    ("leisure", "park"): ("공원", "park"), ("leisure", "garden"): ("정원", "park"), ("leisure", "nature_reserve"): ("자연 공원", "park"),
    ("tourism", "museum"): ("박물관", "museum"), ("tourism", "gallery"): ("미술관", "museum"), ("amenity", "arts_centre"): ("문화 공간", "museum"),
    ("tourism", "attraction"): ("볼거리", "sight"), ("historic", "monument"): ("기념물", "sight"), ("historic", "castle"): ("성", "sight"),
    ("historic", "memorial"): ("기념물", "sight"), ("tourism", "viewpoint"): ("전망 좋은 곳", "view"),
    ("leisure", "playground"): ("놀이터", "play"), ("tourism", "zoo"): ("동물원", "play"), ("tourism", "aquarium"): ("아쿠아리움", "play"),
    ("tourism", "theme_park"): ("놀이공원", "play"),
}
SPOT_QUERIES = ["park", "museum", "attraction", "playground", "viewpoint", "gallery"]
KAKAO_SPOT = {"AT4": ("볼거리", "sight"), "CT1": ("문화 공간", "museum")}


def fetch_spots(lat, lng, radius=1200):
    """주변 둘러볼 곳 원본: 카카오(한국, 키) > Nominatim. [{name, lat, lon, kind, group, hours}]"""
    out = []
    if kakao_available() and in_korea(lat, lng):
        try:
            for code, (kind, group) in KAKAO_SPOT.items():
                r = httpx.get("https://dapi.kakao.com/v2/local/search/category.json", timeout=10,
                              headers={"Authorization": f"KakaoAK {os.environ['KAKAO_REST_KEY']}"},
                              params={"category_group_code": code, "x": lng, "y": lat, "radius": radius, "sort": "distance", "size": 15})
                r.raise_for_status()
                for d in r.json().get("documents", []):
                    cat = d.get("category_name", "")
                    g, k = ("park", "공원") if "공원" in cat else (group, cat.split(" > ")[-1] or kind)
                    out.append({"name": d["place_name"], "lat": float(d["y"]), "lon": float(d["x"]), "kind": k, "group": g, "hours": ""})
            if out:
                return "카카오맵", out
        except Exception as e:
            print(f"[nearby] 카카오 장소 실패: {e!r}")
    d = radius / 111000 * 1.1
    seen = set()
    for q in SPOT_QUERIES:
        try:
            res = _nominatim(q, lat, lng, d)
        except Exception as e:
            print(f"[nearby] Nominatim {q} 실패: {e!r}")
            continue
        for x in res:
            key = (x.get("category"), x.get("type"))
            if key not in SPOT_KIND or x.get("osm_id") in seen:
                continue
            seen.add(x.get("osm_id"))
            kind, group = SPOT_KIND[key]
            nd, et = x.get("namedetails") or {}, x.get("extratags") or {}
            name = nd.get("name:ko") or x.get("name") or nd.get("name")
            if not name:
                if group != "play":  # 이름 없는 공원, 전망대는 찾아가기 어렵다
                    continue
                name = "어린이 놀이터"
            out.append({"name": name, "lat": float(x["lat"]), "lon": float(x["lon"]), "kind": kind, "group": group,
                        "hours": et.get("opening_hours", "")})
    return "OpenStreetMap", [o for o in out if _dist(lat, lng, o["lat"], o["lon"]) <= radius * 1.2]


STAY_MIN = {"park": 30, "museum": 45, "sight": 20, "view": 15, "play": 30}  # 머무는 시간 어림값 (자유식 시간 계산용)
SPOT_WHY = {
    "park": ("쉬어 가기 좋아요", "뛰어놀기 좋아요"), "museum": ("실내라 날씨와 상관없어요", "볼거리가 많아요"),
    "sight": ("천천히 둘러보기 좋아요", "사진 찍기 좋아요"), "view": ("앉아서 경치 보기 좋아요", "사진 찍기 좋아요"),
    "play": ("아이와 같이 가기 좋아요", "아이가 좋아해요"),
}


def rank_spots(spots, lat, lng, people, speed):
    """같이 가는 사람에 맞춰 순서: 아이가 있으면 놀이터와 공원, 부모님이 있으면 공원과 박물관을 앞에."""
    kid = any(p.get("child") or p.get("relation") == "아이" for p in people)
    elder = any(p.get("relation") == "부모님" for p in people)
    bonus = {"park": 0.6 + 0.4 * (kid or elder), "museum": 0.4 + 0.5 * elder, "sight": 0.5, "view": 0.3 + 0.3 * elder,
             "play": (1.2 if kid else -0.5)}
    rows = []
    for sp in spots:
        dist = _dist(lat, lng, sp["lat"], sp["lon"])
        walk = max(1, round(dist * 1.3 / speed / 60))
        why = SPOT_WHY[sp["group"]][1 if kid and sp["group"] in ("park", "play") else 0]
        if sp["group"] == "park" and kid and elder:
            why = "아이는 뛰어놀고, 부모님은 쉬어 가기 좋아요"
        hours = ("영업시간: " + hours_ko(sp["hours"])) if sp.get("hours") else ""
        rows.append({**sp, "lng": sp["lon"], "walk_min": walk, "why": why, "note": hours, "score": bonus[sp["group"]] - walk / 15})
    rows.sort(key=lambda r: -r["score"])
    out, names = [], set()
    for r in rows:  # 같은 이름은 하나만
        if r["name"] in names:
            continue
        names.add(r["name"])
        out.append(r)
    return out
