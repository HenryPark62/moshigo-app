import json
import os

os.environ["MOSHIGO_DB"] = "/tmp/moshigo-test.db"

from core import freemeal, menu2, ocr, order, reviews, store, world  # noqa: E402


def scan():
    s = menu2.demo(menu2.DEFAULT_PEOPLE)
    s["combos"] = menu2.combos(s, menu2.DEFAULT_PEOPLE)
    return s


def test_ocr_fields_grouped_into_lines_and_low_confidence_marked():
    o = ocr.group([{"inferText": "Steak", "inferConfidence": .98, "lineBreak": False},
                   {"inferText": "frites", "inferConfidence": .97, "lineBreak": False},
                   {"inferText": "24", "inferConfidence": .99, "lineBreak": True},
                   {"inferText": "Plat", "inferConfidence": .4, "lineBreak": True}])
    assert [l["text"] for l in o["lines"]] == ["Steak frites 24", "Plat(?)"]
    assert o["lines"][1]["low"] and not o["lines"][0]["low"]


def test_allergy_and_cannot_always_avoid():
    s = scan()
    salad = next(i for i in s["items"] if i["name_orig"] == "Salade de chèvre chaud")
    moules = next(i for i in s["items"] if i["name_orig"].startswith("Moules"))
    assert {x["name"]: x for x in salad["per"]}["지우"]["verdict"] == "피하기"
    assert {x["name"]: x for x in moules["per"]}["아빠"]["verdict"] == "피하기"


def test_similarity_from_each_persons_foods():
    s = scan()
    per = {x["name"]: x for x in next(i for i in s["items"] if i["name_orig"] == "Bœuf bourguignon")["per"]}
    assert per["엄마"]["match"]["food"] == "갈비찜" and per["나"]["match"]["food"] == "비프 스튜"
    # 주재료가 다르면 '조금'까지만
    assert world.similarity({"taste": [.55, .1, 0, 0, .55, .3, .55, .35], "ingredient": "빵", "cooking": "굽기"}, "생선구이")[0] <= 0.62


def test_combos_and_order_card():
    s = scan()
    assert [c["kind"] for c in s["combos"]] == ["all", "local", "fast"]
    for c in s["combos"]:
        assert all(p["verdict"] != "피하기" for p in c["plates"])
    lines = [{"item_id": p["item"]["id"], "count": 1} for p in s["combos"][0]["plates"]]
    card = order.card(s, menu2.DEFAULT_PEOPLE, lines, ["소스는 따로"])
    assert card["first"][0].startswith("Mon enfant est allergique") and "La sauce à part" in card["text"]


def test_free_meal_time_budget():
    f = freemeal.plan(menu2.DEFAULT_PEOPLE, "12:10", "13:30", 10)
    assert f["slowest"] == "지우"
    assert any(r["fits"] for r in f["restaurants"]) and not all(r["fits"] for r in f["restaurants"])


def test_people_saved_by_code_and_survey_feeds_caution():
    if os.path.exists("/tmp/moshigo-test.db"):
        os.remove("/tmp/moshigo-test.db")
    code = store.new_code()
    store.save(code, [{"id": "me", "name": "나", "favorites": ["라멘"]}])
    assert store.load(code)[0]["favorites"] == ["라멘"]
    for _ in range(3):
        reviews.save("Chez Paulette", "Steak frites", True, 4, ["매운맛"], True, "후추 소스가 매워요")
    assert "매운맛" in reviews.caution("Steak frites")
    rv = reviews.reviews("Steak frites", "Chez Paulette")
    assert rv["here"][0]["kind"] == "user"


def test_nearby_places_get_dishes_and_allergy_rules():
    from core import nearby
    els = [{"type": "node", "id": 1, "lat": 48.884, "lon": 2.344, "tags": {"name": "Pho 13", "amenity": "restaurant", "cuisine": "vietnamese"}},
           {"type": "node", "id": 2, "lat": 48.885, "lon": 2.345, "tags": {"name": "Thai Wok", "amenity": "restaurant", "cuisine": "thai"}},
           {"type": "node", "id": 3, "lat": 48.886, "lon": 2.346, "tags": {"name": "Le Bar", "amenity": "restaurant"}}]
    places = nearby.to_places(els, 48.8838, 2.3437)
    assert places[0]["dishes"][0]["name_ko"] == "쌀국수" and places[2]["dishes"] == []
    marks = {m["name"]: m for m in freemeal.person_marks(places[1]["dishes"], menu2.DEFAULT_PEOPLE)}
    assert marks["지우"]["dish"] != "팟타이"  # 팟타이에는 땅콩(견과류)이 들어가서 지우에게는 빼야 한다
    assert all(m.get("unknown") for m in freemeal.person_marks([], menu2.DEFAULT_PEOPLE))
    f = freemeal.plan(menu2.DEFAULT_PEOPLE, "12:10", "13:30", 10, {"name": "여기", "lat": 48.8838, "lng": 2.3437}, places)
    assert f["meet"]["name"] == "여기" and len(f["restaurants"]) == 3


def test_menu_item_ids_are_unique_even_without_latin_letters():
    base = {k: v for k, v in menu2.demo(menu2.DEFAULT_PEOPLE)["items"][0].items()}
    raw = json.loads((menu2.DATA / "demo_paris.json").read_text("utf-8"))
    one = raw["items"][0]
    raw["items"] = [dict(one, name_orig="갈비 750g"), dict(one, name_orig="목살 750g"), dict(one, name_orig="냉면"), dict(one, name_orig="비빔냉면")]
    ids = [i["id"] for i in menu2.enrich(raw, menu2.DEFAULT_PEOPLE)["items"]]
    assert len(set(ids)) == len(ids) == 4, ids


def test_order_card_speaks_the_menu_language():
    s = scan()
    fam = [dict(menu2.DEFAULT_PEOPLE[0], cannot=["술"]), menu2.DEFAULT_PEOPLE[3]]
    expect = {"ja-JP": "アレルギー", "zh-CN": "过敏", "zh-HK": "過敏", "th-TH": "แพ้", "de-DE": "Allergie", "it-IT": "allergia",
              "es-ES": "alergia", "vi-VN": "dị ứng", "ko-KR": "알레르기", "fr-FR": "allergique", "en-US": "allergic"}
    for code, word in expect.items():
        card = order.card(dict(s, language_code=code), fam, [], list(order.REQUEST_KEYS))
        assert word in card["first"][0], (code, card["first"])
        assert len(card["requests"]) == 7 and card["note"] is None
    assert "drink" in order.card(dict(s, language_code="en"), fam, [], [])["first"][1]
    assert order.card(dict(s, language_code="nl-NL"), fam, [], [])["note"]  # 없는 언어는 영어와 안내


def test_survey_feedback_moves_liked_menus_up():
    if os.path.exists("/tmp/moshigo-test.db"):
        os.remove("/tmp/moshigo-test.db")
    for _ in range(4):
        reviews.save("Chez Paulette", "Croque-monsieur, salade", True, 5, [], True, "")
        reviews.save("Chez Paulette", "Poulet rôti, gratin dauphinois", True, 2, [], False, "")
    fb = reviews.feedback(["Croque-monsieur, salade", "Poulet rôti, gratin dauphinois", "Escargots de Bourgogne (6)"])
    assert fb["Croque-monsieur, salade"]["boost"] > 0 > fb["Poulet rôti, gratin dauphinois"]["boost"]
    assert "Escargots de Bourgogne (6)" not in fb
    s = menu2.apply_feedback(menu2.demo(menu2.DEFAULT_PEOPLE), fb)
    croque = next(i for i in s["items"] if i["name_orig"].startswith("Croque"))
    assert croque["fb"]["again"] == 100 and croque["boost"] > 0
