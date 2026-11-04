"""Food Guide 결과 위에 얹은 모시고 기능: 뱃지, 아는 맛과 닮은 메뉴, 아이 접시, 부탁, 설명 보강(실패해도 화면 유지)."""
from copy import deepcopy
import json
from pathlib import Path
import threading
import time

import pytest
from streamlit.testing.v1 import AppTest

from core import fg_extras as fx, foodguide_flow, menu2, order, store, reviews, webmenu, ocr, dish_images, menu_prices, foodguide_images
from ui import screens

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = json.loads((ROOT / "tests/visual/fixtures/foodguide-paris.json").read_text("utf-8"))
QUOTA = "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified workspace API usage limits. You will regain access on 2026-12-01 at 00:00 UTC.'}}"


def people(ids=None):
    group = deepcopy(menu2.DEFAULT_PEOPLE)
    return [p for p in group if ids is None or p["id"] in ids]


def scan(group=None):
    group = group or people()
    ids = {p["id"] for p in group}
    summary = [r for r in BUNDLE["reference_summary"] if r["id"] in ids]
    return foodguide_flow.build_scan(deepcopy(BUNDLE["report"]), group, summary, BUNDLE["metadata"])


def item(s, name):
    return next(i for i in s["items"] if i["name_orig"] == name)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    for module in (store, reviews, webmenu):
        monkeypatch.setattr(module, "DB", tmp_path / "t.sqlite")
    monkeypatch.setattr(fx, "_JOBS", {})
    monkeypatch.setattr(fx, "_DOWN", {"until": 0.0})
    monkeypatch.setattr(fx, "FIRST_WAIT", 2.0)  # 느린 테스트 기계에서도 '바로 실패'를 첫 호출에서 보게
    monkeypatch.setattr(fx, "_describe", fx._describe)  # 하네스가 바꿔도 테스트 끝에 되돌린다
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("MOSHIGO_ENRICH", raising=False)


# ---------- 뱃지 ----------
def test_badges_map_profile_to_four_colors():
    s = scan()
    bourg = item(s, "Bœuf bourguignon")
    assert fx.badges(bourg) == [("t", "감칠맛"), ("a", "고기향"), ("x", "부드러움"), ("t", "짠맛"), ("a", "버섯향"), ("x", "쫄깃함"),
                                ("t", "신맛"), ("a", "와인향"), ("c", "조린 요리")]
    assert fx.badges(bourg, 3) == [("t", "감칠맛"), ("a", "고기향"), ("x", "부드러움"), ("c", "조린 요리")]
    # 모르는 조리법 낱말은 그대로, 음료·디저트에는 조리법 뱃지 없음, 같은 낱말은 한 번만
    assert ("c", "그릴") in fx.badges(item(s, "Steak frites"))
    assert all(c != "c" for c, _ in fx.badges(item(s, "Verre de vin rouge")) + fx.badges(item(s, "Crème brûlée")))
    words = [w for _, w in fx.badges(item(s, "Crème brûlée"))]
    assert len(words) == len(set(words))
    # 프로필이 없거나 분석이 끝나지 않은 메뉴는 뱃지를 만들지 않는다
    assert fx.badges(dict(bourg, status="unknown")) == []
    assert fx.badges(dict(bourg, profile=None)) == []


# ---------- 아는 맛과 닮은 메뉴 ----------
def test_similar_top_spreads_across_people_and_uses_their_own_favorite_words():
    group = people()
    sims = fx.similar_top(scan(group), group, 3)
    assert [r["item"]["name_orig"] for r in sims] == ["Steak haché frites + boule de glace", "Soupe à l'oignon gratinée", "Poulet rôti, gratin dauphinois"]
    assert [r["person"]["id"] for r in sims] == ["jiwoo", "me", "dad"]
    assert sims[0]["line"] == "아이가 좋아하는 함박스테이크 기준 60점"
    # Food Guide가 홍합국으로 연결한 '홍합탕'은 사람이 적은 이름으로, 같은 기준·점수인 사람은 함께
    assert sims[1]["food"] == "홍합탕" and sims[1]["who"] == ["나", "엄마"]
    assert sims[1]["line"].startswith("나와 엄마가 좋아하는 홍합탕")
    assert sims[0]["shared"] == ["소고기", "소금", "후추"]
    assert all(r["score"] >= fx.MIN_LIKE for r in sims)


def test_similar_top_never_uses_restricted_low_or_missing_scores():
    group = people()
    s = scan(group)
    for it in s["items"]:
        for pref in it["preferences"]:
            pref["eligible"] = False if pref["id"] == "jiwoo" else pref["eligible"]
    assert all(r["person"]["id"] != "jiwoo" for r in fx.similar_top(s, group, 3))
    for it in s["items"]:
        for pref in it["preferences"]:
            pref["score"] = None
    assert fx.similar_top(s, group, 3) == []
    # 좋아하는 음식이 연결되지 않은 사람(이유 줄 없음)은 후보가 아니다
    s = scan(group)
    for it in s["items"]:
        for pref in it["preferences"]:
            pref["reasons"] = []
    assert fx.similar_top(s, group, 3) == []


def test_fans_lists_people_whose_favorite_scores_high():
    group = people()
    s = scan(group)
    assert fx.fans(s, item(s, "Bœuf bourguignon"), group) == ["제육볶음 좋아하는 아빠", "함박스테이크 좋아하는 아이"]
    assert fx.fans(s, item(s, "Carafe d'eau"), group) == []


# ---------- 아이 접시 ----------
def test_kid_tweaks_from_ingredients_and_child_profile():
    group = people()
    kid = fx.child_of(group)
    s = scan(group)
    assert fx.kid_tweaks(item(s, "Bœuf bourguignon"), kid) == ["버섯 빼고"]
    assert fx.kid_tweaks(item(s, "Soupe à l'oignon gratinée"), kid) == []  # 양파 수프에서 양파는 빼지 않는다
    assert fx.kid_tweaks(item(s, "Bœuf bourguignon"), None) == []
    assert fx.kid_tweaks(item(s, "Jus de pomme"), kid) == []
    spicy = deepcopy(item(s, "Steak frites"))
    spicy["profile"]["taste"] = ["매운맛", "짠맛"]
    assert fx.kid_tweaks(spicy, kid) == ["맵지 않게"]
    picky = dict(kid, child={"pick_out": [], "good": []})
    assert fx.kid_tweaks(item(s, "Bœuf bourguignon"), picky) == []
    assert set(fx.kid_tweaks(spicy, kid)) <= set(menu2.KID_REQS) <= set(order.REQUEST_KEYS)


def test_kid_backup_picks_childs_best_eligible_meal():
    group = people()
    kid = fx.child_of(group)
    s = scan(group)
    alt = fx.kid_backup(s, kid)
    assert alt["name_orig"] == "Poulet rôti, gratin dauphinois" and alt["good"] == ["치즈", "감자"] and alt["price"] == "19 €"
    assert fx.kid_backup(s, kid, exclude=alt["id"])["name_orig"] == "Steak haché frites + boule de glace"
    assert fx.kid_backup(s, None) is None
    for it in s["items"]:
        if it["name_orig"] in {"Poulet rôti, gratin dauphinois", "Steak haché frites + boule de glace"}:
            fx.pref_of(it, "jiwoo")["eligible"] = False
    assert fx.kid_backup(s, kid)["name_orig"] == "Steak frites"
    for it in s["items"]:
        fx.pref_of(it, "jiwoo")["score"] = 10.0
    assert fx.kid_backup(s, kid) is None  # 점수가 낮으면 억지로 고르지 않는다


def test_order_requests_preselect_kid_plate_and_hurry():
    group = people()
    s = scan(group)
    mine = fx.child_menu(s, fx.child_of(group))
    assert mine["name_orig"] == "Steak haché frites + boule de glace"
    assert fx.order_requests(s, group, {mine["id"]: 1}) == ["아이용 작은 접시"]
    assert fx.order_requests(s, group, {}) == []
    assert fx.order_requests(s, group, {}, hurry=True) == ["빨리 나오는 걸로", "계산서도 같이"]
    assert fx.order_requests(s, people({"me", "mom"}), {mine["id"]: 1}) == []


def test_dish_requests_follow_profiles_and_skip_kid_requests():
    group = people()
    s = scan(group)
    bourg = item(s, "Bœuf bourguignon")
    assert fx.dish_requests(bourg, group) == ["덜 짜게", "소스는 따로"]  # 엄마가 짠 음식을 피해요
    onion = dict(group[0], cannot=["양파", "버섯"])
    assert fx.dish_requests(bourg, [onion]) == ["버섯 빼고", "소스는 따로", "덜 짜게"]
    assert fx.dish_requests(bourg, [onion], skip=["버섯 빼고"]) == ["소스는 따로", "덜 짜게"]  # 아이 접시에 이미 있는 부탁
    assert fx.dish_requests(item(s, "Soupe à l'oignon gratinée"), [onion]) == ["소스는 따로", "덜 짜게"]  # 양파 수프에서 양파는 빼지 않는다
    assert fx.dish_requests(item(s, "Verre de vin rouge"), group) == []


# ---------- 설명 보강 ----------
def raw_items(head):
    return [{"name_orig": line["name_orig"], "unreadable": False, "taste_line": f'{line["name_orig"]} 맛', "ko_compare": "", "imagine": "",
             "good_for": ["고기 좋아하는 분", " ", "셋째"], "kid_tip": "고기만 덜어 주세요.",
             "staff_asks": [{"q_orig": "Quelle cuisson ?", "q_ko": "굽기는요?", "answers": [{"orig": "À point", "ko": "미디엄"}, {"orig": "Bien cuit", "ko": "잘 익혀"}]},
                            {"q_orig": "Sauce ?", "q_ko": "소스는요?", "answers": [{"orig": "Poivre", "ko": "후추"}]}]}
            for line in head["lines"]]


def test_pick_keeps_only_matching_names_and_valid_fields():
    head = fx.head_for(scan())
    raw = raw_items(head)[:2] + [{"name_orig": "Not on this menu", "taste_line": "x"}, {"name_orig": "steak  FRITES", "taste_line": "공백·대소문자"}]
    got = fx.pick(raw, head, has_child=True)
    assert set(got) == {"Soupe à l'oignon gratinée", "Escargots de Bourgogne (6)", "Steak frites"}
    soup = got["Soupe à l'oignon gratinée"]
    assert "ko_compare" not in soup and soup["good_for"] == ["고기 좋아하는 분", "셋째"]
    assert [q["q_orig"] for q in soup["staff_asks"]] == ["Quelle cuisson ?"]  # 대답이 하나뿐인 질문은 뺀다
    assert "kid_tip" not in fx.pick(raw, head, has_child=False)["Soupe à l'oignon gratinée"]


def test_quota_error_is_remembered_and_never_raises(monkeypatch):
    calls = []

    def quota(head, group):
        calls.append(1)
        raise Exception(QUOTA)

    monkeypatch.setattr(fx, "_describe", quota)
    group, session = people(), {}
    s = scan(group)
    assert fx.status(s, group, session) == ("failed", {})
    assert session["fg_enrich_down"] is True and calls == [1]
    # 같은 세션은 다시 부르지 않고, 다른 세션도 잠시 쉬는 동안은 부르지 않는다
    for _ in range(3):
        assert fx.status(s, group, session)[0] == "failed"
    other = {}
    assert fx.status(scan(people({"me"})), people({"me"}), other) == ("failed", {})
    assert other["fg_enrich_down"] is True and calls == [1]


def test_other_failures_stop_for_that_menu_only(monkeypatch):
    calls = []

    def broken(head, group):
        calls.append(1)
        raise RuntimeError("llm stop_reason=refusal")

    monkeypatch.setattr(fx, "_describe", broken)
    group, session = people(), {}
    s = scan(group)
    assert fx.status(s, group, session)[0] == "failed"
    assert fx.status(s, group, session)[0] == "failed" and calls == [1]
    assert "fg_enrich_down" not in session


def test_unexpected_internal_error_is_swallowed(monkeypatch):
    monkeypatch.setattr(fx, "cache_key", lambda *a: (_ for _ in ()).throw(ValueError("boom")))
    assert fx.status(scan(), people(), {}) == ("failed", {})


def test_enrichment_runs_in_background_then_is_cached(monkeypatch):
    gate, calls = threading.Event(), []

    def slow(head, group):
        calls.append([p["name"] for p in group])
        gate.wait(5)
        return {"items": raw_items(head)}

    monkeypatch.setattr(fx, "FIRST_WAIT", 0.05)
    monkeypatch.setattr(fx, "_describe", slow)
    group, session = people(), {}
    s = scan(group)
    assert fx.status(s, group, session) == ("pending", {})
    assert fx.status(s, group, session)[0] == "pending" and len(calls) == 1  # 같은 메뉴는 한 번만
    gate.set()
    for _ in range(100):
        state, data = fx.status(s, group, session)
        if state != "pending":
            break
        time.sleep(0.02)
    assert state == "done" and data["Bœuf bourguignon"]["taste_line"] == "Bœuf bourguignon 맛"
    assert fx.extra_for(item(s, "Bœuf bourguignon"), data)["kid_tip"] == "고기만 덜어 주세요."
    # 새 세션·서버 재시작 뒤에도 SQLite에서 바로 꺼낸다
    monkeypatch.setattr(fx, "_JOBS", {})
    assert fx.status(s, group, {})[0] == "done" and len(calls) == 1


def test_enrichment_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(fx, "_describe", lambda *a: pytest.fail("must not call"))
    monkeypatch.setenv("MOSHIGO_ENRICH", "0")
    assert fx.status(scan(), people(), {}) == ("off", {})
    monkeypatch.delenv("MOSHIGO_ENRICH")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert fx.status(scan(), people(), {}) == ("off", {})


def test_strict_describe_list_raises_instead_of_bare_items(monkeypatch):
    def quota(*args, **kwargs):
        raise Exception(QUOTA)

    monkeypatch.setattr(menu2, "_stream", quota)
    head = fx.head_for(scan())
    with pytest.raises(Exception, match="usage limits"):
        menu2.describe_list(head, people(), strict=True)
    # 기존 경로(웹 메뉴)는 그대로 이름만 남긴다
    assert all(i["unreadable"] for i in menu2.describe_list(head, people())["items"])


# ---------- 실제 화면 (스냅숏 하네스, 외부 호출 없음) ----------
APP = ROOT / "scripts/visual_snapshot_app.py"


@pytest.fixture
def harness(monkeypatch, tmp_path):
    monkeypatch.setenv("MOSHIGO_SNAPSHOT", "1")
    monkeypatch.setenv("MOSHIGO_CAPTURE_ROOT", str(ROOT))
    monkeypatch.setenv("MOSHIGO_ANALYSIS_PROVIDER", "foodguide")
    monkeypatch.setenv("FOODGUIDE_API_URL", "https://foodguide.test")
    monkeypatch.setenv("MOSHIGO_DB", str(tmp_path / "t.sqlite"))
    for module, name in ((ocr, "read"), (menu2, "read_menu"), (menu2, "read_menu_text"), (webmenu, "read_web"), (screens, "geo_block"),
                         (dish_images, "_schedule"), (menu_prices, "_rate"), (foodguide_images, "ensure_images"), (foodguide_images, "retry_images")):
        monkeypatch.setattr(module, name, getattr(module, name))

    def run(case):
        at = AppTest.from_file(str(APP), default_timeout=20)
        at.query_params["case"] = case
        at.run(timeout=20)
        assert not at.exception, [e.message for e in at.exception]
        return at, "\n".join(str(e.value) for kind in ("markdown", "caption", "info", "warning", "error") for e in getattr(at, kind))
    return run


def test_screens_without_enrichment_still_show_rule_based_features(harness):
    at, page = harness("menu-translated")
    assert "아는 맛과 닮은 메뉴" in page and "아이가 좋아하는 함박스테이크 기준 60점" in page
    assert 'class="bd t"' in page
    at, page = harness("dish")
    assert "아이 접시로 바꾸려면" in page and "직원에게 부탁하기" in page and "안 먹으면 대신" in page
    assert "어떤 맛?" not in page and "직원이 물어볼 수 있어요" not in page  # 보강이 막히면 그 줄만 없다
    assert "usage" not in page.lower() and "오류" not in page
    assert at.session_state["fg_enrich"]


def test_screens_show_enrichment_when_cached(harness):
    group = people()
    s = scan(group)
    head = fx.head_for(s)
    fx._save(fx.cache_key(s, group), fx.pick(raw_items(head), head, True))
    at, page = harness("dish")
    assert "어떤 맛?" in page and "Bœuf bourguignon 맛" in page
    assert "고기만 덜어 주세요." in page and "직원이 물어볼 수 있어요" in page and "Quelle cuisson ?" in page
    at, page = harness("order")
    assert "Quelle cuisson ?" in page
