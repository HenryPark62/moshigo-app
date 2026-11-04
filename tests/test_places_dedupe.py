"""주변 식당 목록에 같은 식당이 두 번 나오지 않는지."""
import json
from pathlib import Path

from core import burden, nearby

LAT, LNG = 48.8606, 2.3376
M = 1 / 111_195  # 위도 1m (도)


def el(id_, name, dlat_m=0.0, typ="node", **tags):
    return {"type": typ, "id": id_, "lat": LAT + dlat_m * M, "lon": LNG, "tags": {"name": name, "amenity": "restaurant", **tags}}


def nomi(osm_id, name, dlat_m=0.0, osm_type="node", **extra):
    return {"osm_type": osm_type, "osm_id": osm_id, "category": "amenity", "type": "restaurant", "name": name,
            "lat": str(LAT + dlat_m * M), "lon": str(LNG), "display_name": f"{name}, Paris", "namedetails": {}, "extratags": extra}


def names(places):
    return sorted(p["name"] for p in places)


def test_name_key_ignores_case_accents_punctuation_and_spaces():
    assert nearby.name_key("McDonald’s") == nearby.name_key("MCDONALD'S") == nearby.name_key("mc donalds")
    assert nearby.name_key("Café de Flore") == nearby.name_key("cafe de flore")
    assert nearby.name_key("맥도날드 ") == nearby.name_key("맥도날드")
    assert nearby.name_key("McDonald's") != nearby.name_key("McDonald's Opéra")
    assert nearby.name_key("ข้าว") != nearby.name_key("ขาว")  # 태국어 성조 부호는 지우지 않는다


def test_node_and_way_of_same_restaurant_become_one():
    # 서울 명동 맥도날드: 건물(way)과 점(node)이 7m 떨어져 따로 올라와 있었다
    els = [el(13995187771, "맥도날드", 0, cuisine="burger"),
           el(355606433, "맥도날드", 7, typ="way", cuisine="burger", website="https://www.mcdonalds.co.kr/", building="yes")]
    got = nearby.to_places(els, LAT, LNG)
    assert len(got) == 1
    assert got[0]["id"] == "osmw355606433" and got[0]["website"] == "https://www.mcdonalds.co.kr/"


def test_same_name_20m_apart_merged_case_insensitive():
    got = nearby.to_places([el(1, "La sandwicheria"), el(2, "La Sandwicheria", 20)], LAT, LNG)
    assert len(got) == 1


def test_same_chain_400m_apart_kept():
    got = nearby.to_places([el(1, "McDonald's", cuisine="burger"), el(2, "McDonald's", 400, cuisine="burger")], LAT, LNG)
    assert len(got) == 2
    assert burden.haversine_m(got[0], got[1]) > nearby.SAME_PLACE_M


def test_different_names_at_same_spot_kept():
    got = nearby.to_places([el(1, "McDonald's"), el(2, "McDonald's Opéra"), el(3, "Le Fumoir")], LAT, LNG)
    assert names(got) == ["Le Fumoir", "McDonald's", "McDonald's Opéra"]


def test_richer_record_kept_and_gaps_filled():
    poor = el(1, "Chez Test", 0)
    rich = el(2, "Chez Test", 15, cuisine="french", opening_hours="Mo-Fr 12:00-14:00", **{"website:menu": "https://cheztest.fr/carte"})
    extra = el(3, "Chez Test", 5, **{"addr:street": "Rue X", "addr:city": "Paris"})
    got = nearby.to_places([poor, rich, extra], LAT, LNG)
    assert len(got) == 1
    p = got[0]
    assert p["id"] == "osmn2" and p["note"].startswith("영업시간") and p["menu_url"] == "https://cheztest.fr/carte" and p["dishes"]
    assert p["address"] == "Rue X Paris"  # 남긴 쪽에 없던 주소는 다른 기록에서 채운다
    assert "_tags" not in p


def test_korean_and_original_name_match():
    a = el(1, "Starbucks")
    b = el(2, "Starbucks", 10, **{"name:ko": "스타벅스"})
    got = nearby.to_places([a, b], LAT, LNG)
    assert len(got) == 1 and got[0]["name"] == "스타벅스" and got[0]["orig_name"] == "Starbucks"


def test_exact_id_duplicates_dropped():
    p = nearby.to_places([el(1, "A")], LAT, LNG)[0]
    assert len(nearby.dedupe_places([p, dict(p), dict(p, name="A (copy)")])) == 1


def test_browser_path_duplicates_across_queries():
    # "restaurant"와 "fast food" 두 검색어 결과에 같은 가게가 같이 나오거나, 점과 건물로 따로 나온다
    q1 = [nomi(10, "Mister Garden"), nomi(11, "Le Fumoir", 200), nomi(12, "Burger Shop", 30)]
    q2 = [nomi(10, "Mister Garden"), nomi(12, "Burger Shop", 30, osm_type="way", website="https://burger.fr"),
          nomi(13, "burger shop", 32), nomi(14, "Mister Garden", 500)]
    got = nearby.places_from_browser([q1, q2, {"error": 429}], LAT, LNG)
    assert names(got) == ["Burger Shop", "Le Fumoir", "Mister Garden", "Mister Garden"]
    burger = next(p for p in got if p["name"] == "Burger Shop")
    assert burger["id"] == "osmnw12" and burger["website"] == "https://burger.fr"


def test_node_and_way_with_same_number_are_different_objects():
    # 점과 건물은 번호가 따로 매겨져서 같은 번호가 다른 가게일 수 있다
    got = nearby.places_from_browser([[nomi(7, "A"), nomi(7, "B", 300, osm_type="way")]], LAT, LNG)
    assert names(got) == ["A", "B"]


def test_example_snapshot_has_no_duplicates():
    snap = json.loads((Path(nearby.__file__).parent / "data" / "examples" / "paris_near.json").read_text("utf-8"))
    assert len(nearby.dedupe_places(snap["places"])) == len(snap["places"])
    assert len({p["id"] for p in snap["places"]}) == len(snap["places"])
