"""식당 메뉴 불러오기: 홈페이지 고르기, 답 확인(지어낸 메뉴 거르기), 저장, 2단계 입력. 네트워크와 API는 부르지 않는다."""
import os

os.environ.setdefault("MOSHIGO_DB", "/tmp/moshigo-test.db")

import pytest  # noqa: E402

from core import menu2, nearby, webmenu  # noqa: E402

PAGE = """# Carte
## Entrées
- Soupe à l'oignon gratinée 12 €
- Œufs mayonnaise 8 €
## Plats
- Bœuf bourguignon, purée maison 26 €
- Steak frites 24 €
"""
PLACE = {"name": "Chez Test", "orig_name": "", "lat": 48.85301, "lng": 2.33702, "website": "https://www.cheztest.fr", "menu_url": "", "address": "Paris 6e"}


def line(name, price="", section="Plats"):
    return {"section_orig": section, "name_orig": name, "price": price, "note": ""}


def answer(lines, url="https://cheztest.fr/carte", found=True):
    return {"found": found, "source_url": url, "source_title": "Carte", "restaurant": "Chez Test", "menu_language": "프랑스어",
            "language_code": "fr-FR", "lines": lines}


GOOD = [line("Soupe à l'oignon gratinée", "12 €", "Entrées"), line("Oeufs mayonnaise", "8 €", "Entrées"),
        line("Bœuf bourguignon, purée maison", "26 €"), line("Steak frites", "24 €")]
PAGES = [{"url": "https://www.cheztest.fr/", "title": "Chez Test", "text": "Bienvenue. Réservez une table."},
         {"url": "https://www.cheztest.fr/carte/", "title": "Carte - Chez Test", "text": PAGE}]


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(webmenu, "DB", tmp_path / "web.db")


# ---------- 홈페이지 고르기 ----------
def test_site_prefers_menu_page_and_cleans_values():
    site, menu = nearby.site_of({"website": "www.cheztest.fr;https://other.fr", "website:menu": "https://cheztest.fr/carte"})
    assert site == "https://www.cheztest.fr" and menu == "https://cheztest.fr/carte"
    assert nearby.site_of({"contact:website": "http://a.fr", "menu:url": "a.fr/menu"}) == ("http://a.fr", "https://a.fr/menu")
    assert nearby.site_of({"name": "x"}) == ("", "")
    assert nearby.site_of({"website": "not a url"}) == ("", "")


def test_kakao_place_page_is_not_a_website():
    assert nearby.site_of({"url": "http://place.map.kakao.com/123"}) == ("", "")
    assert nearby.site_of({"url": "https://www.restaurant.kr"})[0] == "https://www.restaurant.kr"


def test_browser_places_carry_website_and_address():
    res = [[{"osm_id": 1, "category": "amenity", "type": "restaurant", "name": "Chez Test", "lat": "48.853", "lon": "2.337",
             "display_name": "Chez Test, Rue X, Paris", "namedetails": {}, "extratags": {"website": "https://cheztest.fr", "website:menu": "https://cheztest.fr/carte"}}]]
    p = nearby.places_from_browser(res, 48.853, 2.337)[0]
    assert (p["website"], p["menu_url"], p["address"]) == ("https://cheztest.fr", "https://cheztest.fr/carte", "Chez Test, Rue X, Paris")
    q = nearby.to_places([{"type": "node", "id": 2, "lat": 48.85, "lon": 2.33, "tags": {"name": "A", "amenity": "restaurant",
                                                                                    "addr:housenumber": "3", "addr:street": "Rue Y", "addr:city": "Paris"}}], 48.85, 2.33)[0]
    assert q["website"] == "" and q["address"] == "3 Rue Y Paris"


# ---------- 답 확인 ----------
def test_check_builds_phase2_input_and_source():
    got = webmenu.check(answer(GOOD), PAGES, PLACE)
    head = got["head"]
    assert head["is_menu"] and head["restaurant"] == "Chez Test" and head["language_code"] == "fr-FR"
    assert [ln["name_orig"] for ln in head["lines"]] == [g["name_orig"] for g in GOOD]
    assert set(head["lines"][0]) == {"section_orig", "name_orig", "price", "note"}
    src = got["source"]
    assert src["kind"] == "web" and src["url"] == "https://www.cheztest.fr/carte/" and src["own"] and src["site"] == "cheztest.fr"


def test_check_drops_names_not_on_the_page():
    lines = GOOD + [line("Homard thermidor", "58 €")]
    got = webmenu.check(answer(lines), PAGES, PLACE)
    assert "Homard thermidor" not in [ln["name_orig"] for ln in got["head"]["lines"]]
    assert len(got["head"]["lines"]) == 4


def test_check_is_none_when_not_found_or_unsure():
    assert webmenu.check(answer([], found=False), PAGES, PLACE) is None
    assert webmenu.check(None, PAGES, PLACE) is None
    assert webmenu.check(answer(GOOD), [], PLACE) is None  # 연 페이지가 없으면 믿지 않는다
    # 대부분 페이지에 없는 이름이면 (지어냈을 수 있다) 버린다
    made_up = GOOD[:2] + [line(n) for n in ("Homard thermidor", "Canard à l'orange", "Sole meunière", "Tarte Tatin")]
    assert webmenu.check(answer(made_up), PAGES, PLACE) is None
    # 확인된 요리가 너무 적으면 못 찾은 것으로
    assert webmenu.check(answer(GOOD[:2]), PAGES, PLACE) is None


def test_check_uses_fetched_page_when_answer_url_was_not_opened():
    got = webmenu.check(answer(GOOD, url="https://elsewhere.com/menu"), PAGES, PLACE)
    assert got["source"]["url"] == "https://www.cheztest.fr/carte/"


def test_check_other_site_is_not_own_and_pdf_is_trusted_as_opened():
    pages = [{"url": "https://www.thefork.fr/chez-test", "title": "Chez Test - TheFork", "text": PAGE}]
    got = webmenu.check(answer(GOOD, url="https://www.thefork.fr/chez-test"), pages, PLACE)
    assert not got["source"]["own"] and got["source"]["site"] == "thefork.fr"
    pdf = [{"url": "https://cheztest.fr/menu.pdf", "title": "", "text": None}]
    assert webmenu.check(answer(GOOD, url="https://cheztest.fr/menu.pdf"), pdf, PLACE)["source"]["own"]


def test_seen_ignores_accents_case_and_spaces():
    page = webmenu.norm("BŒUF BOURGUIGNON — purée maison / 꼬들 목살 17,000원")
    assert webmenu.seen("Boeuf bourguignon", page)
    assert webmenu.seen("꼬들목살", page)
    assert not webmenu.seen("Coq au vin", page)


# ---------- 저장 ----------
def test_cache_hit_miss_and_expiry():
    key = webmenu.key_of(PLACE)
    assert key == webmenu.key_of(dict(PLACE, lat=48.85304, id="other-source-id"))  # 출처가 달라도 같은 식당
    assert webmenu.cache_get(key) == (False, None)
    webmenu.cache_put(key, {"head": {"lines": []}}, now=1000)
    assert webmenu.cache_get(key, now=1000 + 86400 * 13) == (True, {"head": {"lines": []}})
    assert webmenu.cache_get(key, now=1000 + webmenu.KEEP_FOUND + 1) == (False, None)
    webmenu.cache_put(key, None, now=1000)  # 못 찾음은 짧게
    assert webmenu.cache_get(key, now=1000 + 3600) == (True, None)
    assert webmenu.cache_get(key, now=1000 + webmenu.KEEP_MISS + 1) == (False, None)


def test_find_menu_asks_once_then_uses_cache():
    calls = []

    def asker(place, say):
        calls.append(place["name"])
        return answer(GOOD), PAGES

    a = webmenu.find_menu(PLACE, asker=asker)
    b = webmenu.find_menu(PLACE, asker=asker)
    assert a == b and len(calls) == 1
    miss = dict(PLACE, name="Nowhere", lat=1.0, lng=1.0)
    assert webmenu.find_menu(miss, asker=lambda p, s: (answer([], found=False), [])) is None
    assert webmenu.find_menu(miss, asker=lambda p, s: pytest.fail("못 찾음도 기억해야 한다")) is None


def test_errors_are_not_cached():
    def boom(place, say):
        raise TimeoutError("slow")

    assert webmenu.find_menu(PLACE, asker=boom) is None
    assert webmenu.cache_get(webmenu.key_of(PLACE)) == (False, None)


def test_read_web_feeds_phase2_and_marks_source(monkeypatch):
    seen_asks = []

    def fake_stream(system, content, schema, max_tokens, model=None):
        seen_asks.append(content[0]["text"])
        return {"items": [dict(menu2._bare(line("Steak frites", "24 €")), unreadable=False)]}

    monkeypatch.setattr(menu2, "_stream", fake_stream)
    raw = webmenu.read_web(PLACE, menu2.DEFAULT_PEOPLE, asker=lambda p, s: (answer(GOOD), PAGES))
    assert raw["source"]["kind"] == "web" and raw["source"]["url"].endswith("/carte/")
    assert raw["is_menu"] and raw["restaurant"] == "Chez Test"
    asks = "\n".join(seen_asks)  # 3개씩 나눠 동시에 보내므로 순서는 정해져 있지 않다
    assert "Steak frites | 24 €" in asks and "Entrées" in asks  # 페이지에서 옮긴 묶음, 이름, 가격이 2단계로
    assert webmenu.read_web(dict(PLACE, name="None", lat=2.0), menu2.DEFAULT_PEOPLE, asker=lambda p, s: (None, [])) is None
