import os

os.environ.setdefault("MOSHIGO_DB", "/tmp/moshigo-test.db")

from core import menu2  # noqa: E402


def people(**favs):
    out = []
    for p in menu2.DEFAULT_PEOPLE:
        p = dict(p)
        if p["id"] in favs:
            p["favorites"] = favs[p["id"]]
        out.append(p)
    return out


def test_similar_top_strong_matches_spread_across_people():
    s = menu2.demo(menu2.DEFAULT_PEOPLE)
    sims = menu2.similar_top(s, 3)
    assert len(sims) == 3
    assert len({r["item"]["id"] for r in sims}) == 3  # 같은 메뉴는 한 번만
    assert len({r["person"]["id"] for r in sims}) == 3  # 다른 사람 몫이 있으면 한 사람에게 몰리지 않게
    for r in sims:
        it = r["item"]
        assert it["course"] != "drink" and not it["unreadable"]
        x = next(y for y in it["per"] if y["id"] == r["person"]["id"])
        assert x["verdict"] != "피하기" and x["match"]["bars"] >= 2
        assert r["match"] is x["match"]
        assert r["match"]["food"] in r["line"] and r["match"]["level"] in r["line"]
    bars = [r["match"]["bars"] for r in sims]
    assert bars == sorted(bars, reverse=True)  # 더 닮은 것부터


def test_similar_top_demo_picks_and_sentence():
    s = menu2.demo(menu2.DEFAULT_PEOPLE)
    sims = {r["item"]["name_orig"]: r for r in menu2.similar_top(s, 3)}
    assert sims["Bœuf bourguignon"]["line"] == "내가 좋아하는 비프 스튜와 아주 닮았어요"
    assert sims["Steak frites"]["person"]["name"] == "아빠"
    assert "소고기" in sims["Steak frites"]["match"]["shared"]


def test_similar_top_never_suggests_dish_to_avoid():
    # 아빠는 조개류를 못 먹는다: 홍합탕을 좋아해도 홍합찜은 닮은 메뉴로 나오지 않는다
    s = menu2.demo(people(me=[], mom=[], jiwoo=[], dad=["홍합탕"]))
    assert all("Moules" not in r["item"]["name_orig"] for r in menu2.similar_top(s, 3))


def test_similar_top_one_person_fills_with_own_matches():
    s = menu2.demo(people(mom=[], dad=[], me=[]))  # 아이만 좋아하는 음식이 있다
    sims = menu2.similar_top(s, 3)
    assert len(sims) == 3 and {r["person"]["name"] for r in sims} == {"아이"}
    assert len({r["item"]["id"] for r in sims}) == 3


def test_similar_top_shared_fans_named_together():
    s = menu2.demo(people(me=["홍합탕"], mom=["홍합탕"], dad=[], jiwoo=[]))
    sims = menu2.similar_top(s, 3)
    moules = next(r for r in sims if r["item"]["name_orig"].startswith("Moules"))
    assert moules["who"] == ["나", "엄마"]
    assert moules["line"].startswith("나와 엄마가 좋아하는 홍합탕과")


def test_similar_top_empty_without_favorites():
    s = menu2.demo(menu2.START_PEOPLE)
    assert menu2.similar_top(s, 3) == []
