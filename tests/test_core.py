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
    assert {x["name"]: x for x in salad["per"]}["아이"]["verdict"] == "피하기"
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
    assert f["slowest"] == "아이"
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
    assert marks["아이"]["dish"] != "팟타이"  # 팟타이에는 땅콩(견과류)이 들어가서 아이에게는 빼야 한다
    assert all(m.get("unknown") for m in freemeal.person_marks([], menu2.DEFAULT_PEOPLE))
    f = freemeal.plan(menu2.DEFAULT_PEOPLE, "12:10", "13:30", 10, {"name": "여기", "lat": 48.8838, "lng": 2.3437}, places)
    assert f["meet"]["name"] == "여기" and len(f["restaurants"]) == 3


def test_menu_item_ids_are_unique_even_without_latin_letters():
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
        assert len(card["requests"]) == len(order.REQUEST_KEYS) and card["note"] is None
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


def test_cook_time_by_food_and_rush_hour():
    from core import nearby
    els = [{"type": "node", "id": 1, "lat": 37.567, "lon": 126.979, "tags": {"name": "BBQ치킨", "amenity": "fast_food"}},
           {"type": "node", "id": 2, "lat": 37.567, "lon": 126.979, "tags": {"name": "McDonald's", "amenity": "fast_food", "cuisine": "burger"}}]
    pl = {p["name"]: p for p in nearby.to_places(els, 37.5665, 126.978)}
    assert pl["BBQ치킨"]["wait_min"] == 20 and pl["McDonald's"]["wait_min"] == 5  # 치킨은 패스트푸드로 등록돼도 튀기는 시간
    calm = freemeal.plan(menu2.DEFAULT_PEOPLE, "15:00", "16:30", 10, {"name": "x", "lat": 37.5665, "lng": 126.978}, list(pl.values()))
    rush = freemeal.plan(menu2.DEFAULT_PEOPLE, "12:10", "13:40", 10, {"name": "x", "lat": 37.5665, "lng": 126.978}, list(pl.values()))
    w = lambda f, n: next(r["wait_min"] for r in f["restaurants"] if r["name"] == n)
    assert rush["peak"] and not calm["peak"] and w(rush, "BBQ치킨") > w(calm, "BBQ치킨")


def test_plan_fits_time_window():
    from core import plan
    o = {"lat": 37.5665, "lng": 126.978}
    rests = [{"id": "r1", "name": "국수집", "type": "food", "lat": 37.567, "lng": 126.979, "wait_min": 10, "meal_min": 30, "sitdown": True, "score": 1.0},
             {"id": "r2", "name": "버거집", "type": "food", "lat": 37.5655, "lng": 126.977, "wait_min": 5, "meal_min": 20, "sitdown": False, "score": 0.5}]
    spots = [{"id": "s1", "name": "광장", "type": "spot", "group": "park", "lat": 37.5663, "lng": 126.9779, "score": 1.0}]
    ps = plan.make_plans(o, 12 * 60, 14 * 60, rests, spots, 1.0)
    assert ps
    for p in ps:
        assert p["finish"] <= 14 * 60 - 10 and sum(x["place"]["type"] == "food" for x in p["stops"]) == 1
        assert all(a["leave"] <= b["arrive"] for a, b in zip(p["stops"], p["stops"][1:]))
    assert any(x["place"]["type"] == "spot" for x in ps[0]["stops"])  # 시간이 넉넉하면 둘러볼 곳도 넣는다
    assert plan.make_plans(o, 12 * 60, 12 * 60 + 30, rests, spots, 1.0) == []  # 30분으로는 못 다녀옴


def test_free_meal_past_midnight():
    d = freemeal.plan(menu2.DEFAULT_PEOPLE, "23:15", "00:25", 10, {"name": "x", "lat": 37.5665, "lng": 126.978}, [])
    assert d["left_min"] == 70


def test_menu_guide_fields():
    s = menu2.demo(menu2.DEFAULT_PEOPLE)
    beef = next(i for i in s["items"] if i["name_orig"] == "Bœuf bourguignon")
    assert beef["ko_compare"] and beef["imagine"] and beef["good_for"]
    assert sum(i["local_popular"] for i in s["items"]) <= 3
    from ui.common import badges
    h = badges(beef)
    assert 'class="bd t"' in h and 'class="bd a"' in h and "오래 끓인 요리" in h


def test_staff_asks():
    s = menu2.demo(menu2.DEFAULT_PEOPLE)
    assert all("staff_asks" in i for i in s["items"])
    steak = next(i for i in s["items"] if i["name_orig"] == "Steak frites")
    q = steak["staff_asks"][0]
    assert q["q_orig"] and q["q_ko"] and len(q["answers"]) >= 2 and all(a["orig"] and a["ko"] for a in q["answers"])
    assert menu2._bare({"section_orig": "", "name_orig": "x", "price": ""})["staff_asks"] == []
    item = menu2._schema(["나"])["properties"]["items"]["items"]
    assert "staff_asks" in item["required"] and item["properties"]["staff_asks"]["items"]["additionalProperties"] is False


def test_streamed_lines_parser_handles_split_chunks():
    from core.menu2 import _Lines
    src = json.dumps({"is_menu": True, "restaurant": 'A "q" {x}', "menu_language": "프랑스어", "language_code": "fr",
                      "lines": [{"section_orig": "S", "name_orig": 'Croque {m} "x"', "price": "9", "note": ""},
                                {"section_orig": "S", "name_orig": "B", "price": "1", "note": "a}b"}]}, ensure_ascii=False)
    for step in (1, 5, 13):
        p, out = _Lines(), []
        for i in range(0, len(src), step):
            out += p.feed(src[i:i + step])
        assert [o["name_orig"] for o in out] == ['Croque {m} "x"', "B"]


def test_llm_down_is_not_blamed_on_the_photo():
    from ui.screens import llm_down
    assert llm_down(Exception("Error code: 400 - You have reached your specified workspace API usage limits."))
    assert llm_down(Exception("overloaded_error"))
    assert not llm_down(ValueError("Expecting value: line 1 column 1"))
