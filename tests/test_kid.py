"""아이 접시 도우미: 아이 접시로 바꾸는 부탁, 안 먹을 때 대신 시킬 메뉴."""
import json

from core import menu2, order, world

KID = next(p for p in menu2.DEFAULT_PEOPLE if p.get("child"))


def scan():
    return menu2.demo(menu2.DEFAULT_PEOPLE)


def item(s, name_orig):
    return next(i for i in s["items"] if i["name_orig"] == name_orig)


def test_kid_requests_are_order_requests():
    assert set(menu2.KID_REQS) <= set(order.REQUEST_KEYS)
    kid = menu2._schema(["아이"])["properties"]["items"]["items"]["properties"]["kid_tweaks"]
    assert kid["items"]["enum"] == menu2.KID_REQS


def test_demo_has_kid_fields():
    raw = json.loads((menu2.DATA / "demo_paris.json").read_text("utf-8"))
    assert all("kid_tweaks" in i and "kid_tip" in i for i in raw["items"])
    s = scan()
    bourg = item(s, "Bœuf bourguignon")
    assert "버섯 빼고" in bourg["kid_tweaks"] and bourg["kid_tip"]
    assert item(s, "Escargots de Bourgogne (6)")["kid_tweaks"] == []
    assert all(i["kid_tweaks"] == [] and i["kid_tip"] == "" for i in s["items"] if i["course"] == "drink")


def test_no_child_no_kid_fields():
    s = menu2.demo([p for p in menu2.DEFAULT_PEOPLE if not p.get("child")])
    assert all(i["kid_tweaks"] == [] and i["kid_tip"] == "" for i in s["items"])


def spicy_item(spicy, **kw):
    taste = [0.3] * len(world.AXES)
    taste[menu2.SPICY] = spicy
    return {"name_ko": "닭고기 카레", "contains": ["닭고기", "양파"], "taste": taste, **kw}


def test_tweaks_add_not_spicy_and_keep_order():
    assert menu2.kid_tweaks(spicy_item(0.7, kid_tweaks=["아이용 작은 접시"]), KID) == ["맵지 않게", "아이용 작은 접시"]
    assert menu2.kid_tweaks(spicy_item(0.1, kid_tweaks=[]), KID) == []
    picky = dict(KID, child=dict(KID["child"], pick_out=["매우면"]))
    assert menu2.kid_tweaks(spicy_item(0.3, kid_tweaks=[]), picky) == ["맵지 않게"]
    assert menu2.kid_tweaks(spicy_item(0.1, kid_tweaks=["모르는 부탁"]), KID) == []
    assert menu2.kid_tweaks(spicy_item(0.9, kid_tweaks=[]), None) == []


def test_old_scan_without_field_guesses_from_contains():
    # 예전에 읽은 메뉴: 채소를 골라내는 아이면 보이는 버섯, 양파를 빼 달라고 한다. 이름에 들어간 재료는 빼지 않는다.
    old = spicy_item(0.0, contains=["소고기", "버섯", "양파"], name_ko="양파 수프")
    assert menu2.kid_tweaks(old, KID) == ["버섯 빼고"]


def test_kid_backup_prefers_kids_menu_then_good_foods():
    s = scan()
    b = menu2.kid_backup(s, KID)
    assert b["name_orig"] == "Steak haché frites + boule de glace" and b["kids_only"]
    b2 = menu2.kid_backup(s, KID, exclude=b["id"])
    assert b2["name_orig"] == "Croque-monsieur, salade" and set(b2["good"]) >= {"치즈", "빵"}
    for x in (b, b2):
        it = next(i for i in s["items"] if i["id"] == x["id"])
        assert {p["id"]: p for p in it["per"]}[KID["id"]]["verdict"] == "편히" and it["course"] != "dessert"


def test_kid_backup_skips_spicy_and_none_without_child():
    s = scan()
    for i in s["judged"]:
        i["taste"][menu2.SPICY] = 0.8
    assert menu2.kid_backup(s, KID) is None
    assert menu2.kid_backup(scan(), None) is None
