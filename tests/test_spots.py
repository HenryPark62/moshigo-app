"""둘러볼 곳 종류(볼거리, 공원, 문화, 쇼핑, 여가): OSM 태그 나누기, 순서, 고른 종류만 보여 주기."""
from urllib.parse import parse_qs, urlparse

from core import nearby, plan

LAT, LNG = 37.5665, 126.978


def nomi(cat, typ, name, i, lat=LAT + 0.001, lng=LNG + 0.001, **kw):
    return {"category": cat, "type": typ, "name": name, "osm_type": "node", "osm_id": i, "lat": str(lat), "lon": str(lng),
            "namedetails": kw.get("nd", {}), "extratags": kw.get("et", {})}


def test_osm_tags_map_to_categories():
    res = [[nomi("leisure", "park", "서울광장", 1), nomi("leisure", "garden", "정원", 2), nomi("tourism", "museum", "박물관 A", 3),
            nomi("amenity", "arts_centre", "아트센터", 4), nomi("shop", "mall", "몰", 5), nomi("shop", "department_store", "백화점 A", 6),
            nomi("amenity", "marketplace", "시장 A", 7), nomi("amenity", "cinema", "극장 A", 8), nomi("tourism", "aquarium", "아쿠아", 9),
            nomi("tourism", "attraction", "궁", 10), nomi("tourism", "viewpoint", "전망대", 11), nomi("historic", "castle", "성 A", 12)]]
    got = {s["name"]: (s["kind"], s["group"]) for s in nearby.spots_from_browser(res, LAT, LNG)}
    assert got["서울광장"] == ("공원", "park") and got["정원"][1] == "park"
    assert got["박물관 A"] == ("박물관", "culture") and got["아트센터"][1] == "culture"
    assert {got[n][1] for n in ("몰", "백화점 A", "시장 A")} == {"shop"} and got["시장 A"][0] == "시장"
    assert got["극장 A"] == ("영화관", "play") and got["아쿠아"][1] == "play"
    assert {got[n][1] for n in ("궁", "전망대", "성 A")} == {"sight"}


def test_noise_is_dropped():
    res = [[nomi("historic", "memorial", "명판", 1), nomi("amenity", "theatre", "(주)기획사", 2), nomi("shop", "mall", "7", 3),
            nomi("leisure", "park", "", 4), nomi("leisure", "playground", "", 5), nomi("amenity", "restaurant", "식당", 6),
            nomi("leisure", "park", "먼 공원", 7, lat=LAT + 0.05)],
           {"error": 429}]
    got = nearby.spots_from_browser(res, LAT, LNG)
    assert [s["name"] for s in got] == ["어린이 놀이터"]  # 이름 없는 놀이터만 남긴다


def test_same_place_from_two_queries_once():
    a = nomi("tourism", "museum", "박물관 A", 1)
    got = nearby.spots_from_browser([[a], [dict(a)]], LAT, LNG)
    assert len(got) == 1
    assert nearby.merge_spots(got, [dict(got[0]), {**got[0], "id": "n2"}])[1]["id"] == "n2"


def test_urls_only_for_picked_categories():
    urls = nearby.nominatim_urls(LAT, LNG, "spots", ["shop"])
    assert [parse_qs(urlparse(u).query)["q"][0] for u in urls] == nearby.SPOT_QUERIES["shop"]
    every = nearby.nominatim_urls(LAT, LNG, "spots")
    assert len(every) == sum(len(v) for v in nearby.SPOT_QUERIES.values()) <= 14
    assert len(nearby.nominatim_urls(LAT, LNG, "spots", nearby.default_cats([]))) <= 8


def test_default_cats_follow_people():
    assert nearby.default_cats([{"relation": "부모님"}]) == ["sight", "park", "culture"]
    assert "play" in nearby.default_cats([{"relation": "아이", "child": {}}])


def spot(name, group, kind, d=0.002):
    return {"id": name, "name": name, "lat": LAT + d, "lon": LNG, "kind": kind, "group": group, "hours": ""}


def test_ranking_by_who_comes():
    spots = [spot("놀이터 A", "play", "놀이터"), spot("박물관 A", "culture", "박물관"), spot("백화점 A", "shop", "백화점")]
    kid = nearby.rank_spots(spots, LAT, LNG, [{"relation": "아이", "child": {}}], 1.0)
    old = nearby.rank_spots(spots, LAT, LNG, [{"relation": "부모님"}], 1.0)
    assert kid[0]["name"] == "놀이터 A" and kid[0]["why"] == "아이가 좋아해요"
    assert old[0]["name"] == "박물관 A" and old[-1]["name"] == "놀이터 A"
    assert next(r for r in old if r["group"] == "shop")["why"] == "선물이나 기념품 사기 좋아요"


def test_pick_keeps_only_picked_and_mixes():
    rows = [{**spot(f"공원{i}", "park", "공원"), "score": 2 - i / 100} for i in range(15)]
    rows += [{**spot(f"몰{i}", "shop", "쇼핑몰"), "score": 1 - i / 100} for i in range(5)]
    rows += [{**spot("영화관", "play", "영화관"), "score": 3}]
    got = nearby.pick_spots(rows, ["park", "shop"], 12)
    assert len(got) == 12 and {r["group"] for r in got} == {"park", "shop"}
    assert sum(r["group"] == "shop" for r in got) == 5  # 점수가 낮아도 고른 종류는 자리를 받는다
    assert [r["score"] for r in got] == sorted((r["score"] for r in got), reverse=True)
    assert nearby.pick_spots(rows, ["play"], 12)[0]["name"] == "영화관"
    assert nearby.pick_spots(rows, [], 12) == []


def test_stay_time_by_kind_used_in_plans():
    assert nearby.stay_min({"kind": "영화관", "group": "play"}) == 120
    assert nearby.stay_min({"kind": "쇼핑몰", "group": "shop"}) == nearby.STAY_MIN["shop"]
    assert all(g in nearby.STAY_MIN and g in nearby.SPOT_WHY for g in nearby.CATS)
    o = {"lat": LAT, "lng": LNG}
    rests = [{"id": "r1", "name": "식당", "lat": LAT + 0.001, "lng": LNG, "wait_min": 10, "meal_min": 30, "score": 1.0}]
    movie = [{**spot("영화관", "play", "영화관", 0.001), "lng": LNG, "score": 2.0}]
    ps = plan.make_plans(o, 12 * 60, 14 * 60, rests, movie, 1.0)
    assert ps and all(x["place"]["type"] == "food" for x in ps[0]["stops"])  # 2시간 영화는 2시간 안에 식사와 같이 못 넣는다
