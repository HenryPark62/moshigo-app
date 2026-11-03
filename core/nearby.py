"""지금 있는 곳 주변의 실제 식당 (OpenStreetMap, Overpass API).

키가 필요 없고 무료다. 식당의 요리 종류(cuisine 태그)로 대표 메뉴를 붙여서,
자유 식사 화면에서 사람마다 먹을 메뉴와 닮은꼴을 미리 보여 준다.
기다림과 식사 시간은 가게 종류별 어림값이다.
"""
import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import httpx

from . import burden, world

ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
             "https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
UA = {"User-Agent": "moshigo-mvp/0.1 (+https://moshigo.onrender.com)", "Accept-Language": "ko,en"}
ERRORS = []  # 최근 실패 기록 (개발 확인용 화면에서 보여 준다)


def _err(where, e):
    import time as _t
    ERRORS.append(f"{_t.strftime('%H:%M:%S')} {where}: {e!r}"[:200])
    del ERRORS[:-12]
    print(f"[nearby] {where} 실패: {e!r}")

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
    return burden.haversine_m({"lat": a_lat, "lng": a_lng}, {"lat": b_lat, "lng": b_lng})


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
                                 "category": cat.split(" > ")[-1] if cat else "", "url": d.get("place_url", ""),
                                 "addr": d.get("road_address_name") or d.get("address_name", "")}})
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
                             "cuisine": raw.get("cuisine") or ";".join(cuisines), "opening_hours": pr.get("opening_hours", ""),
                             **web_tags(raw), "addr": pr.get("formatted", "")}})
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
                                 "cuisine": et.get("cuisine", ""), "opening_hours": et.get("opening_hours", ""),
                                 **web_tags(et), "addr": x.get("display_name", "")}})
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
        _err("Nominatim 식당", e)
    return "OpenStreetMap (Overpass)", fetch(lat, lng, radius)


WEB_TAGS = ("website", "contact:website", "website:menu", "menu:url", "contact:menu")


def web_tags(et):
    """OSM 추가 태그 중 가게 홈페이지와 메뉴 페이지 주소만 (식당 메뉴 불러오기에 쓴다)."""
    return {k: et[k] for k in WEB_TAGS if et.get(k)}


def _http(v):
    """태그 값 -> http 주소 하나. 여러 개면 첫 번째, 앞에 https://가 없으면 붙인다."""
    v = (v or "").split(";")[0].strip()
    if not v or " " in v or "." not in v:
        return ""
    return v if v.startswith(("http://", "https://")) else "https://" + v.lstrip("/")


def site_of(t):
    """태그 -> (가게 홈페이지, 메뉴 페이지). 카카오/네이버 지도 장소 페이지는 홈페이지로 치지 않는다."""
    menu = next((u for k in ("website:menu", "menu:url", "contact:menu") if (u := _http(t.get(k)))), "")
    site = next((u for k in ("website", "contact:website", "url") if (u := _http(t.get(k)))
                 and not any(m in u for m in ("place.map.kakao.com", "map.naver.com", "map.kakao.com"))), "")
    return site, menu


def address_of(t):
    """태그 -> 주소 한 줄 (검색할 때 같은 이름의 다른 가게와 구별하려고)."""
    if t.get("addr"):
        return t["addr"]
    parts = [t.get(k, "") for k in ("addr:housenumber", "addr:street", "addr:postcode", "addr:city", "addr:country")]
    return " ".join(p for p in parts if p)


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
            "website": site_of(t)[0], "menu_url": site_of(t)[1], "address": address_of(t),
        })
    return out


# ---------- 주변 둘러볼 곳 (볼거리, 공원, 문화, 쇼핑, 여가) ----------
CATS = {"sight": "볼거리", "park": "공원", "culture": "문화", "shop": "쇼핑", "play": "여가"}  # 묶음 -> 화면 이름 (칩 순서)
SPOT_KIND = {  # (분류, 종류) -> (한국어 이름, 묶음)
    # 기념 명판(historic=memorial)과 공연장(amenity=theatre)은 기획사, 동호회까지 섞여 너무 많아서 뺀다
    ("tourism", "attraction"): ("볼거리", "sight"), ("historic", "monument"): ("기념물", "sight"), ("historic", "castle"): ("성", "sight"),
    ("tourism", "viewpoint"): ("전망 좋은 곳", "sight"),
    ("leisure", "park"): ("공원", "park"), ("leisure", "garden"): ("정원", "park"), ("leisure", "nature_reserve"): ("자연 공원", "park"),
    ("tourism", "museum"): ("박물관", "culture"), ("tourism", "gallery"): ("미술관", "culture"), ("amenity", "arts_centre"): ("문화 공간", "culture"),
    ("shop", "mall"): ("쇼핑몰", "shop"), ("shop", "department_store"): ("백화점", "shop"), ("amenity", "marketplace"): ("시장", "shop"),
    ("leisure", "playground"): ("놀이터", "play"), ("amenity", "cinema"): ("영화관", "play"), ("tourism", "zoo"): ("동물원", "play"),
    ("tourism", "aquarium"): ("아쿠아리움", "play"), ("tourism", "theme_park"): ("놀이공원", "play"), ("leisure", "water_park"): ("워터파크", "play"),
}
# 묶음별 Nominatim 검색어. 브라우저가 1.1초에 하나씩 부르므로 사용자가 고른 묶음만 묻는다
SPOT_QUERIES = {"sight": ["attraction", "viewpoint", "monument"], "park": ["park", "garden"], "culture": ["museum", "gallery"],
                "shop": ["mall", "department store", "marketplace"], "play": ["playground", "cinema", "aquarium"]}
# 카카오 카테고리 코드 -> (기본 이름, 기본 묶음, 이 코드로 찾을 수 있는 묶음). 카테고리 이름을 보고 다시 나눈다
KAKAO_SPOT = {"AT4": ("볼거리", "sight", ("sight", "park", "play")), "CT1": ("문화 공간", "culture", ("culture", "play")),
              "MT1": ("대형마트", "shop", ("shop",))}
KAKAO_KEYWORD = {"shop": ["백화점", "전통시장"], "play": ["놀이터"]}  # 카테고리 코드가 따로 없는 곳은 검색어로
KAKAO_WORDS = [("테마파크", "play"), ("놀이", "play"), ("아쿠아리움", "play"), ("동물원", "play"), ("영화", "play"), ("공원", "park"),
               ("백화점", "shop"), ("시장", "shop"), ("쇼핑", "shop")]


def default_cats(people):
    """처음 보여 줄 묶음. 아이가 있으면 문화 대신 여가."""
    kid = any(p.get("child") or p.get("relation") == "아이" for p in people)
    return ["sight", "park", "play" if kid else "culture"]


def _named(name):
    """찾아갈 수 있는 이름인지 (숫자만 있는 출입구 번호, 회사 이름은 뺀다)."""
    return bool(name) and any(c.isalpha() for c in name) and "(주)" not in name and "㈜" not in name


def spot_of(x):
    """Nominatim 결과 하나 -> 둘러볼 곳. 모르는 종류거나 이름이 없으면 None."""
    key = (x.get("category"), x.get("type"))
    if key not in SPOT_KIND:
        return None
    kind, group = SPOT_KIND[key]
    nd, et = x.get("namedetails") or {}, x.get("extratags") or {}
    name = nd.get("name:ko") or x.get("name") or nd.get("name")
    if not _named(name):
        if kind != "놀이터":  # 이름 없는 공원, 전망대는 찾아가기 어렵다
            return None
        name = "어린이 놀이터"
    return {"id": f"{(x.get('osm_type') or 'n')[0]}{x.get('osm_id')}", "name": name, "lat": float(x["lat"]), "lon": float(x["lon"]),
            "kind": kind, "group": group, "hours": et.get("opening_hours", "")}


def merge_spots(old, new):
    """같은 곳은 한 번만 (먼저 찾은 것을 남긴다)."""
    seen = {o["id"] for o in old}
    return old + [n for n in new if n["id"] not in seen and not seen.add(n["id"])]


def _kakao_spots(lat, lng, radius, groups):
    hdr = {"Authorization": f"KakaoAK {os.environ['KAKAO_REST_KEY']}"}
    calls = [("category", {"category_group_code": code}, kind, group) for code, (kind, group, serves) in KAKAO_SPOT.items()
             if set(serves) & set(groups)]
    calls += [("keyword", {"query": w}, w, None) for g in groups for w in KAKAO_KEYWORD.get(g, [])]
    out = []
    for path, extra, kind, group in calls:
        r = httpx.get(f"https://dapi.kakao.com/v2/local/search/{path}.json", timeout=10, headers=hdr,
                      params={**extra, "x": lng, "y": lat, "radius": radius, "sort": "distance", "size": 15})
        r.raise_for_status()
        for d in r.json().get("documents", []):
            cat = d.get("category_name", "")
            g = next((g for w, g in KAKAO_WORDS if w in cat), group)
            if g is None:  # 검색어로 찾았는데 가게 이름에만 그 말이 들어간 곳 (시장 안 식당 등)
                continue
            out.append({"id": f"k{d['id']}", "name": d["place_name"], "lat": float(d["y"]), "lon": float(d["x"]),
                        "kind": cat.split(" > ")[-1] or kind, "group": g, "hours": ""})
    return out


def fetch_spots(lat, lng, radius=1200, groups=None):
    """주변 둘러볼 곳 원본: 카카오(한국, 키) > Nominatim > Overpass. [{id, name, lat, lon, kind, group, hours}]"""
    groups = [g for g in (groups or CATS) if g in CATS]
    if kakao_available() and in_korea(lat, lng):
        try:
            out = merge_spots([], _kakao_spots(lat, lng, radius, groups))
            if out:
                return "카카오맵", out
        except Exception as e:
            print(f"[nearby] 카카오 장소 실패: {e!r}")
    d = radius / 111000 * 1.1
    res = []
    for q in (q for g in groups for q in SPOT_QUERIES[g]):
        try:
            res.append(_nominatim(q, lat, lng, d))
        except Exception as e:
            _err(f"Nominatim {q}", e)
    if res:
        return "OpenStreetMap", spots_from_browser(res, lat, lng, radius)
    try:  # 서버(클라우드) 주소에서 Nominatim이 막히면 Overpass로
        out = fetch_spots_overpass(lat, lng, radius)
    except Exception as e:
        _err("Overpass 장소", e)
        raise
    return "OpenStreetMap", [o for o in out if _dist(lat, lng, o["lat"], o["lon"]) <= radius * 1.2]


def fetch_spots_overpass(lat, lng, radius=1200, limit=200):
    """Overpass에서 모든 묶음을 한 번에. 공개 서버 여러 곳에 동시에 묻는다."""
    a = f"(around:{radius},{lat},{lng})"
    sel = (f'(nwr{a}[leisure~"^(park|garden|nature_reserve|playground|water_park)$"];'
           f'nwr{a}[tourism~"^(museum|gallery|attraction|viewpoint|zoo|aquarium|theme_park)$"];'
           f'nwr{a}[historic~"^(monument|castle)$"][name];'
           f'nwr{a}[amenity~"^(arts_centre|cinema|marketplace)$"][name];'
           f'nwr{a}[shop~"^(mall|department_store)$"][name];);')
    q = f"[out:json][timeout:25];{sel}out center {limit};"
    pool = ThreadPoolExecutor(len(ENDPOINTS))
    futs = [pool.submit(_overpass, u, q) for u in ENDPOINTS]
    els, pending = None, set(futs)
    try:
        while pending and els is None:
            done, pending = wait(pending, timeout=40, return_when=FIRST_COMPLETED)
            if not done:
                break
            for f in done:
                try:
                    els = f.result()
                    break
                except Exception as e:
                    _err("Overpass 장소 서버", e)
                    continue
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    if els is None:
        raise RuntimeError("Overpass 장소 실패")
    out = []
    for el in els:
        t = el.get("tags", {})
        key = next(((k, t[k]) for k in ("leisure", "tourism", "historic", "amenity", "shop") if (k, t.get(k)) in SPOT_KIND), None)
        la = el.get("lat") or (el.get("center") or {}).get("lat")
        lo = el.get("lon") or (el.get("center") or {}).get("lon")
        if not key or la is None:
            continue
        sp = spot_of({"category": key[0], "type": key[1], "osm_type": el.get("type"), "osm_id": el.get("id"), "lat": la, "lon": lo,
                      "name": t.get("name"), "namedetails": {"name:ko": t.get("name:ko")}, "extratags": t})
        if sp:
            out.append(sp)
    return out


STAY_MIN = {"sight": 20, "park": 30, "culture": 45, "shop": 40, "play": 40}  # 머무는 시간 어림값 (분, 자유식과 추천 플랜 계산용)
STAY_KIND = {"전망 좋은 곳": 15, "기념물": 10, "놀이터": 30, "시장": 30, "영화관": 120}


def stay_min(sp):
    return STAY_KIND.get(sp.get("kind"), STAY_MIN[sp["group"]])


SPOT_WHY = {  # 묶음 -> (어른끼리, 아이와 함께)
    "sight": ("천천히 둘러보기 좋아요", "사진 찍기 좋아요"), "park": ("쉬어 가기 좋아요", "뛰어놀기 좋아요"),
    "culture": ("실내라 날씨와 상관없어요", "실내라 날씨와 상관없어요"), "shop": ("선물이나 기념품 사기 좋아요", "구경할 거리가 많아요"),
    "play": ("같이 즐기기 좋아요", "아이가 좋아해요"),
}
KIND_WHY = {"전망 좋은 곳": "앉아서 경치 보기 좋아요", "시장": "현지 먹거리를 구경하기 좋아요", "영화관": "앉아서 쉬어 가기 좋아요",
            "놀이터": "아이와 같이 가기 좋아요"}  # 어른끼리 갈 때 종류별로 더 맞는 말


def _bonus(sp, kid, elder):
    if "놀이터" in sp["kind"]:
        return 1.2 if kid else -0.5
    if sp["kind"] == "전망 좋은 곳":
        return 0.3 + 0.3 * elder
    return {"sight": 0.5, "park": 0.6 + 0.4 * (kid or elder), "culture": 0.4 + 0.5 * elder, "shop": 0.4, "play": 0.4 + 0.6 * kid}[sp["group"]]


def rank_spots(spots, lat, lng, people, speed):
    """같이 가는 사람에 맞춰 순서: 아이가 있으면 놀이터와 공원, 부모님이 있으면 공원과 문화를 앞에."""
    kid = any(p.get("child") or p.get("relation") == "아이" for p in people)
    elder = any(p.get("relation") == "부모님" for p in people)
    rows = []
    for sp in spots:
        walk = burden.walk_min(_dist(lat, lng, sp["lat"], sp["lon"]), speed)
        why = SPOT_WHY[sp["group"]][1] if kid else KIND_WHY.get(sp["kind"], SPOT_WHY[sp["group"]][0])
        if sp["group"] == "park" and kid and elder:
            why = "아이는 뛰어놀고, 부모님은 쉬어 가기 좋아요"
        hours = ("영업시간: " + hours_ko(sp["hours"])) if sp.get("hours") else ""
        rows.append({**sp, "lng": sp["lon"], "walk_min": walk, "why": why, "note": hours, "score": _bonus(sp, kid, elder) - walk / 15})
    rows.sort(key=lambda r: -r["score"])
    out, names = [], set()
    for r in rows:  # 같은 이름은 하나만
        if r["name"] in names:
            continue
        names.add(r["name"])
        out.append(r)
    return out


def pick_spots(rows, groups, n=12):
    """고른 묶음의 곳만 n곳. 점수 순서를 따르되 한 묶음이 자리를 다 차지하지 않게 묶음마다 먼저 몇 곳씩 담고 남는 자리를 채운다."""
    rows = [r for r in rows if r["group"] in groups]
    base = max(1, n // max(1, len(set(groups))))
    first, rest, per = [], [], {}
    for r in rows:
        per[r["group"]] = per.get(r["group"], 0) + 1
        (first if per[r["group"]] <= base else rest).append(r)
    out = first[:n] + rest[:max(0, n - len(first))]
    return sorted(out, key=lambda r: -r["score"])


# ---------- 휴대폰 브라우저가 직접 묻기 ----------
# 서버(Render 무료)는 여러 앱이 같은 주소를 나눠 써서 Nominatim이 '너무 많은 요청(429)'으로 막는다.
# 사용자 휴대폰에서 직접 물으면 사람마다 주소가 달라 막히지 않는다. 서버는 받은 결과를 정리만 한다.
FOOD_QUERIES = ["restaurant", "fast food"]


def nominatim_urls(lat, lng, kind="food", groups=None):
    """kind: food(식당, 900m) / spots(둘러볼 곳, 1200m, groups 묶음만). 브라우저가 차례로 부를 주소."""
    from urllib.parse import urlencode

    radius = 900 if kind == "food" else 1200
    d = radius / 111000 * 1.1
    qs = FOOD_QUERIES if kind == "food" else [q for g in (groups or CATS) for q in SPOT_QUERIES.get(g, [])]
    return [("https://nominatim.openstreetmap.org/search?" + urlencode({
        "q": q, "format": "jsonv2", "limit": 50, "extratags": 1, "namedetails": 1, "bounded": 1,
        "accept-language": "ko,en", "viewbox": f"{lng - d},{lat + d},{lng + d},{lat - d}"})) for q in qs]


def places_from_browser(results, lat, lng, radius=900):
    """브라우저가 받아 온 Nominatim 결과 목록 -> 식당 목록 (to_places와 같은 모양)."""
    out, seen = [], set()
    for res in results or []:
        if not isinstance(res, list):
            continue
        for x in res:
            nd, et = x.get("namedetails") or {}, x.get("extratags") or {}
            name = x.get("name") or nd.get("name")
            if not name or x.get("osm_id") in seen or x.get("category") != "amenity":
                continue
            seen.add(x.get("osm_id"))
            out.append({"type": "nominatim", "id": x.get("osm_id"), "lat": float(x["lat"]), "lon": float(x["lon"]),
                        "tags": {"name": name, "name:ko": nd.get("name:ko", ""), "amenity": x.get("type", "restaurant"),
                                 "cuisine": et.get("cuisine", ""), "opening_hours": et.get("opening_hours", ""),
                                 **web_tags(et), "addr": x.get("display_name", "")}})
    els = [e for e in out if _dist(lat, lng, e["lat"], e["lon"]) <= radius * 1.2]
    return to_places(els, lat, lng)


def spots_from_browser(results, lat, lng, radius=1200):
    """브라우저(또는 서버)가 받아 온 Nominatim 결과 목록 -> 둘러볼 곳 목록."""
    out = []
    for res in results or []:
        if isinstance(res, list):
            out = merge_spots(out, [sp for sp in map(spot_of, res) if sp])
    return [o for o in out if _dist(lat, lng, o["lat"], o["lon"]) <= radius * 1.2]


def server_keys():
    """키가 있는 서비스(카카오, Geoapify)는 서버에서 부른다 (키를 브라우저에 보내지 않기 위해)."""
    return kakao_available() or geoapify_available()
