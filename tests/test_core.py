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
