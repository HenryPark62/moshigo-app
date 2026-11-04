"""실제 API 응답 시드로 Streamlit 화면과 세션 전환을 검증한다. 외부 호출 없음."""
from copy import deepcopy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Widget

from core import foodguide_flow, menu2, ocr, reviews, store, webmenu, dish_images, menu_prices, foodguide_images
from ui import screens, foodguide


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "scripts/visual_snapshot_app.py"


@pytest.fixture(autouse=True)
def isolated_capture(monkeypatch, tmp_path):
    monkeypatch.setenv("MOSHIGO_SNAPSHOT", "1")
    monkeypatch.setenv("MOSHIGO_CAPTURE_ROOT", str(ROOT))
    monkeypatch.setenv("MOSHIGO_ANALYSIS_PROVIDER", "foodguide")
    monkeypatch.setenv("MOSHIGO_DB", str(tmp_path / "capture.sqlite"))
    for module in (store, reviews, webmenu):
        monkeypatch.setattr(module, "DB", tmp_path / "capture.sqlite")

    # 하네스가 직접 바꾸는 함수도 테스트 종료 시 원래 객체로 복구한다.
    for module, name in ((ocr, "read"), (menu2, "read_menu"), (menu2, "read_menu_text"),
                         (webmenu, "read_web"), (screens, "geo_block"), (dish_images, "_schedule"), (menu_prices, "_rate"), (foodguide_images, "ensure_images"), (foodguide_images, "retry_images")):
        monkeypatch.setattr(module, name, getattr(module, name))
    calls = []

    def no_provider(*args, **kwargs):
        calls.append(True)
        raise AssertionError("UI regression must not call an analysis provider")

    for name in ("run_image", "run_web", "resume", "refresh"):
        monkeypatch.setattr(foodguide_flow, name, no_provider)
    monkeypatch.setattr(webmenu, "find_menu", no_provider)
    yield
    assert not calls


def text(at):
    return "\n".join(str(element.value) for kind in ("markdown", "caption", "info", "warning", "error")
                     for element in getattr(at, kind))


def healthy(at):
    assert not at.exception, [element.message for element in at.exception]
    assert "이 화면을 여는 중에 문제가 생겼어요" not in text(at)


def rerun(at):
    # st.rerun으로 화면이 바뀌면 1.50 테스트 트리에 이전 위젯이 남을 수 있다.
    # 실제 브라우저처럼 Streamlit이 이미 폐기한 위젯만 입력 전송에서 제외한다.
    def prune(block):
        for index, node in list(block.children.items()):
            if isinstance(node, Widget):
                try:
                    at.session_state[node.id]
                except KeyError:
                    del block.children[index]
            elif hasattr(node, "children"):
                prune(node)
    prune(at._tree)
    # Streamlit 1.50 AppTest의 ButtonGroup은 단일 선택 값도 list로 전송한다.
    # pills/segmented_control의 현재 scalar를 frontend와 같은 단일 항목 배열로 보낸다.
    for group in at.button_group:
        if not isinstance(group.value, list):
            group.set_value([] if group.value is None else [group.value])
    at.run(timeout=20)
    healthy(at)
    return at


def capture(case):
    at = AppTest.from_file(str(APP), default_timeout=20)
    at.query_params["case"] = case
    return rerun(at)


def button(at, label):
    return next(widget for widget in at.button if widget.label == label)


@pytest.mark.parametrize("case", ["menu-translated", "menu-original", "menu-people", "dish", "combo-all",
                                  "order", "survey", "simple-menu", "simple-dish", "simple-order"])
def test_native_pages_render_real_fixture(case):
    at = capture(case)
    assert at.session_state["scan"]["provider"] == "foodguide"
    assert "data-capture-ready" in text(at)


def test_editing_favorites_invalidates_menu_group_and_order():
    at = capture("edit-adult")
    at.button_group(key="fav_me_한국").select("갈비찜")
    rerun(at)
    button(at, "저장하기").click()
    rerun(at)
    assert "갈비찜" in next(p for p in at.session_state["people"] if p["id"] == "me")["favorites"]
    assert at.session_state["foodguide_stale"] is True
    assert at.session_state["foodguide_picks"] == {}
    for tab in ("tab_menu", "tab_combo", "tab_order"):
        at.button(key=tab).click()
        rerun(at)
        assert any(widget.label == "현재 입맛으로 다시 비교" for widget in at.button)
        assert "비교 점수" not in text(at)
        assert "직원에게 이 화면을 보여 주세요" not in text(at)


def test_simple_target_remains_active_when_group_profile_is_inactive():
    at = capture("simple-menu")
    people = deepcopy(at.session_state["people"])
    next(p for p in people if p["id"] == "mom")["active"] = False
    at.session_state["people"] = people
    rerun(at)
    assert at.session_state["simple"] == "mom"
    assert not any(widget.label == "현재 입맛으로 다시 비교" for widget in at.button)
    assert "엄마" in text(at) and "추천 점수" in text(at)
    # 화면이 그룹 프로필 자체를 변경하지 않아야 한다.
    assert next(p for p in at.session_state["people"] if p["id"] == "mom")["active"] is False


def test_ambiguous_reference_can_change_and_reset_after_resolution():
    at = capture("edit-parent")
    key = "fg_reference_mom_갈비찜"
    choices = at.session_state["foodguide_reference_cache"]["foods"]["갈비찜"]["candidates"]
    first, second = choices[:2]
    at.selectbox(key=key).select(first["id"])
    rerun(at)
    button(at, "저장하기").click()
    rerun(at)
    mom = next(p for p in at.session_state["people"] if p["id"] == "mom")
    assert mom["foodguide_refs"]["갈비찜"] == first
    assert next(p for p in store.load("vis234") if p["id"] == "mom")["foodguide_refs"]["갈비찜"] == first

    # 완료된 재비교 응답의 요약 상태를 시드하되, 편집·저장은 실제 위젯으로 한다.
    summary = deepcopy(at.session_state["foodguide_summary"])
    row = next(row for row in summary if row["id"] == "mom")
    row["unresolved"] = [item for item in row["unresolved"] if item["name"] != "갈비찜"]
    row["resolved_foods"].append({"favorite": "갈비찜", **first})
    row["resolved"] += 1
    at.session_state["foodguide_summary"] = summary
    at.button(key="edit_mom").click()
    rerun(at)
    assert first["name"] in at.selectbox(key=key).options
    assert second["name"] in at.selectbox(key=key).options
    at.selectbox(key=key).select(second["id"])
    rerun(at)
    button(at, "저장하기").click()
    rerun(at)
    assert next(p for p in at.session_state["people"] if p["id"] == "mom")["foodguide_refs"]["갈비찜"] == second
    at.button(key="edit_mom").click()
    rerun(at)
    at.selectbox(key=key).select("")
    rerun(at)
    button(at, "저장하기").click()
    rerun(at)
    assert "갈비찜" not in next(p for p in at.session_state["people"] if p["id"] == "mom")["foodguide_refs"]


def test_loading_other_code_clears_previous_analysis_even_for_identical_people():
    at = capture("people")
    store.save("abc234", deepcopy(at.session_state["people"]))
    at.session_state["foodguide_jobs"] = {"analysis-image": {"job_id": "a" * 32}}
    at.session_state["foodguide_pending"] = {"kind": "image", "image": b"old-photo"}
    at.session_state["fg_old_selection"] = "old"
    at.text_input(key="load_code").set_value("abc234")
    button(at, "불러오기").click()
    rerun(at)
    state = at.session_state.filtered_state
    assert state["code"] == "abc234"
    for key in ("scan", "scan_report", "scan_img", "foodguide_jobs", "foodguide_pending", "foodguide_picks", "picks", "fg_old_selection"):
        assert key not in state


@pytest.mark.parametrize("reference_count, expected", [(0, "점수 없음"), (1, "점수 없음")])
def test_null_personal_score_is_not_displayed_as_zero(reference_count, expected):
    at = capture("simple-menu")
    scan = deepcopy(at.session_state["scan"])
    for item in scan["items"]:
        for person in item["preferences"]:
            person["score"] = None
            person["reference_count"] = reference_count
    at.session_state["scan"] = scan
    rerun(at)
    assert expected in text(at)
    assert "0점" not in text(at)


def test_simple_menu_only_exposes_requested_fields_and_opens_detail():
    at = capture("menu-translated")
    first = at.session_state["scan"]["items"][0]
    content = text(at)
    assert first["name_ko"] in content and first["price"] in content
    if first["reading"]:
        assert first["reading"] in content
    assert "추천 점수" in content
    for unwanted in ("주재료:", "조리법:", "찍은 메뉴판 보기", "비교 기준 확인", "편집 추정값", "안전 판정"):
        assert unwanted not in content
    assert not at.button_group
    at.button(key=f'fg_open_{first["id"]}').click()
    rerun(at)
    assert at.session_state["dish_id"] == first["id"]
    assert any(expander.label == "분석 정보" for expander in at.expander)


def test_recommendation_averages_every_active_person_and_keeps_individual_rows():
    at = capture("menu-translated")
    scan = deepcopy(at.session_state["scan"])
    first = scan["items"][0]
    assert len(first["preferences"]) == 4
    for item in scan["items"]:
        item["status"] = "ok"
        item["profile"] = dict(item.get("profile") or {}, status="known", meal_roles=["주요리"], unknown_fields=[])
        for row in item["preferences"]:
            row.update(score=0, eligible=True)
    for row in first["preferences"]:
        row["score"] = 12.2 if row["id"] == "me" else 87.2
    for row in scan["items"][1]["preferences"]:
        row["score"] = 90 if row["id"] == "me" else 50
    first["matches"] = [{"name": "다른 한식", "score": 99.9}]
    before = deepcopy(scan)
    at.session_state["scan"] = scan
    rerun(at)
    assert not at.selectbox
    assert at.button(key=f'fg_open_{first["id"]}').label.endswith("68점")
    assert "나: 12" in text(at) and "엄마: 87" in text(at)
    cards = [element.value for element in at.markdown if 'class="fg_menu_tile_content"' in element.value]
    # 나의 점수는 12.2 < 90이지만 가족 평균은 68.45 > 60이므로 순위가 뒤집힌다.
    assert first["name_ko"] in cards[0]
    assert scan["items"][1]["name_ko"] in cards[1]
    assert at.session_state["scan"] == before
    at.button(key=f'fg_open_{first["id"]}').click()
    rerun(at)
    button(at, "메뉴판으로").click()
    rerun(at)
    assert not at.selectbox
    assert at.button(key=f'fg_open_{first["id"]}').label.endswith("68점")


def test_top_two_use_raw_group_means_stable_ties_and_exclude_any_restriction():
    at = capture("menu-translated")
    scan = deepcopy(at.session_state["scan"])
    for item in scan["items"]:
        item["status"] = "ok"
        item["profile"] = dict(item.get("profile") or {}, status="known", meal_roles=["주요리"], unknown_fields=[])
        for row in item["preferences"]:
            row.update(score=None, eligible=True)
    for index, value in enumerate([44.1, 44.4, 99.9, 44.3, 44.4]):
        for row in scan["items"][index]["preferences"]:
            row.update(score=value, eligible=True)
    next(p for p in scan["items"][2]["preferences"] if p["id"] == "mom")["eligible"] = False
    before = deepcopy(scan)
    at.session_state["scan"] = scan
    rerun(at)
    cards = [element.value for element in at.markdown if 'class="fg_menu_tile_content"' in element.value]
    for position, source_index in enumerate([1, 4, 3, 0]):
        assert scan["items"][source_index]["name_ko"] in cards[position]
    assert sum('class="fg_recommend_badge"' in card for card in cards) == 2
    restricted = next(card for card in cards if scan["items"][2]["name_ko"] in card)
    assert 'class="fg_recommend_badge"' not in restricted
    assert at.button(key=f'fg_open_{scan["items"][2]["id"]}').label.endswith("—제한 확인")
    assert at.session_state["scan"] == before
    at.session_state["foodguide_stale"] = True
    rerun(at)
    assert 'class="fg_recommend_badge"' not in text(at)


GROUP_PEOPLE = [{"id": "me", "name": "나"}, {"id": "mom", "name": "엄마"},
                {"id": "dad", "name": "아빠"}, {"id": "kid", "name": "아이"}]


def test_group_mean_uses_ids_all_people_and_ignores_nonparticipants():
    item = {"status": "ok", "preferences": [
        {"id": "kid", "score": 0, "eligible": True},
        {"id": "inactive", "score": 100, "eligible": True},
        {"id": "dad", "score": 40, "eligible": True},
        {"id": "me", "score": 100, "eligible": True},
        {"id": "mom", "score": 20, "eligible": True}], "matches": [{"score": 99}]}
    before = deepcopy(item)
    assert foodguide._group_score(item, GROUP_PEOPLE, True) == ("40", "점")
    assert foodguide._menu_rank(item, GROUP_PEOPLE, True) == 40
    assert foodguide._group_score(item, [GROUP_PEOPLE[-1]], True) == ("0", "점")
    assert foodguide._menu_rank(item, [GROUP_PEOPLE[-1]], True) == 0
    assert item == before


@pytest.mark.parametrize("problem", ["missing", "null", "restricted", "eligibility_unknown", "nan", "infinity", "boolean", "too_high", "negative", "status_unknown", "stale"])
def test_incomplete_group_never_drops_member_to_inflate_recommendation(problem):
    item = {"status": "ok", "preferences": [{"id": p["id"], "score": 99, "eligible": True} for p in GROUP_PEOPLE]}
    target = item["preferences"][-1]
    if problem == "missing":
        item["preferences"].pop()
    elif problem == "restricted":
        target["eligible"] = False
    elif problem == "eligibility_unknown":
        target["eligible"] = None
    elif problem == "status_unknown":
        item["status"] = "unknown"
    elif problem != "stale":
        target["score"] = {"null": None, "nan": float("nan"), "infinity": float("inf"),
                           "boolean": True, "too_high": 101, "negative": -1}[problem]
    fresh = problem != "stale"
    score, note = foodguide._group_score(item, GROUP_PEOPLE, fresh)
    assert score == "—" and note
    assert foodguide._menu_rank(item, GROUP_PEOPLE, fresh) == -1


def test_group_rank_keeps_fractional_mean_instead_of_rounded_headline():
    first = {"status": "ok", "preferences": [{"id": "me", "score": 44, "eligible": True}, {"id": "mom", "score": 44.2, "eligible": True}]}
    second = deepcopy(first)
    second["preferences"][1]["score"] = 44.8
    people = GROUP_PEOPLE[:2]
    assert foodguide._group_score(first, people, True) == foodguide._group_score(second, people, True) == ("44", "점")
    assert foodguide._menu_rank(first, people, True) == pytest.approx(44.1)
    assert foodguide._menu_rank(second, people, True) == pytest.approx(44.4)


@pytest.mark.parametrize("detected_code", ["EUR", ""])
def test_detected_currency_is_used_for_bare_prices_and_inference_is_labeled(detected_code):
    at = capture("menu-translated")
    scan = deepcopy(at.session_state["scan"])
    scan["report"]["extraction"].update(currency_code=detected_code, currency_source="inferred", currency_evidence="메뉴판의 지역 음식과 가격 형식에서 유로(EUR)로 추정")
    scan["items"][0]["price"] = "14,90"
    at.session_state["scan"] = scan
    rerun(at)
    assert "14,90 EUR" in text(at)
    assert "약 22,377원" in text(at)
    assert "추정 통화" not in text(at)
    assert "AI 추정" in text(at)


@pytest.mark.parametrize("score,eligible,status,fresh,expected", [
    (0, True, "ok", True, ("0", "점")),
    (98, False, "ok", True, ("—", "제한 확인")),
    (None, True, "ok", True, ("—", "점수 없음")),
    (98, True, "unknown", True, ("—", "확인 필요")),
    (98, True, "ok", False, ("—", "확인 필요")),
])
def test_recommendation_never_fakes_missing_or_restricted_scores(score, eligible, status, fresh, expected):
    item = {"status": status, "preferences": [{"id": "me", "score": score, "eligible": eligible}], "matches": [{"score": 100}]}
    assert foodguide._menu_score(item, "me", fresh) == expected


@pytest.mark.parametrize("eligible", [True, False])
def test_generated_asset_lookup_only_overrides_two_top_cards(monkeypatch, eligible):
    import httpx
    from core import generated_menu_images

    at = capture("menu-translated")
    scan = deepcopy(at.session_state["scan"])
    for index, item in enumerate(scan["items"]):
        item["status"] = "ok"
        item["profile"] = dict(item.get("profile") or {}, status="known", meal_roles=["주요리"], unknown_fields=[])
        score = {1: 95, 3: 90}.get(index, 10)
        for row in item["preferences"]:
            row.update(score=score, eligible=eligible)
    expected_ids = {scan["items"][1]["id"], scan["items"][3]["id"]} if eligible else {item["id"] for item in scan["items"][:2]}
    asset_calls, network_calls = [], []

    def photo(item_id, kind):
        return {"src": f"https://assets.example.test/{kind}-{item_id}.png",
                "label": "생성 자산 확인" if kind == "generated" else "기존 대체 이미지",
                "title": kind, "author": "", "license": "", "source_url": "", "license_url": ""}

    def lookup(item):
        asset_calls.append(item["id"])
        return photo(item["id"], "generated")

    def forbidden_request(*args, **kwargs):
        network_calls.append(True)
        raise AssertionError("Rendering stored generated assets must not generate or request images")

    monkeypatch.setattr(generated_menu_images, "get_generated_image", lookup)
    monkeypatch.setattr(dish_images, "menu_images", lambda items, **kwargs: {item["id"]: photo(item["id"], "fallback") for item in items})
    monkeypatch.setattr(httpx, "get", forbidden_request)
    monkeypatch.setattr(httpx.Client, "send", forbidden_request)
    at.session_state["scan"] = scan
    rerun(at)
    assert len(asset_calls) == len(expected_ids)
    assert set(asset_calls) == expected_ids
    assert not network_calls
    cards = [element.value for element in at.markdown if 'class="fg_menu_tile_content"' in element.value]
    assert len(cards) == len(scan["items"])
    assert sum("생성 자산 확인" in card for card in cards) == len(expected_ids)
    assert all("생성 자산 확인" in card for card in cards[:2])
    assert all("생성 자산 확인" not in card for card in cards[2:])
    if not eligible:
        # 점수 없는 동률은 원문 순서다. AI 이미지가 추천 자격을 만들지는 않는다.
        assert all(scan["items"][index]["name_ko"] in cards[index] for index in range(2))
        assert all('class="fg_recommend_badge"' not in card for card in cards)
        assert all(at.button(key=f'fg_open_{item["id"]}').label.endswith("—제한 확인") for item in scan["items"][:2])
    for item in scan["items"]:
        card = next(card for card in cards if item["name_ko"] in card)
        kind = "generated" if item["id"] in expected_ids else "fallback"
        expected = photo(item["id"], kind)
        assert expected["src"] in card and expected["label"] in card
        if kind == "fallback":
            assert "생성 자산 확인" not in card


@pytest.mark.parametrize("profile, expected", [
    ({"meal_roles": ["주식"]}, True),
    ({"status": "known", "meal_roles": ["주요리", "곁들임"]}, True),
    ({"status": "unknown", "meal_roles": ["주요리"]}, False),
    ({"status": "known", "meal_roles": ["주요리"], "unknown_fields": ["meal_roles"]}, False),
    ({"status": "known", "meal_roles": ["양념"]}, False),
    ({"status": "known", "meal_roles": ["음료"]}, False),
    ({"status": "known", "meal_roles": ["후식"]}, False),
    ({"status": "known"}, False),
    ({"meal_roles": []}, False),
    (None, False),
])
def test_meal_recommendation_requires_known_meal_roles_not_name(profile, expected):
    # 같은 '소스' 이름도 역할 정보에 따라 판단해야 한다.
    item = {"name_ko": "소스 곁들인 주요리", "profile": profile}
    assert foodguide._is_meal(item) is expected


@pytest.mark.parametrize("meal_count", [1, 2])
def test_meals_precede_high_scoring_condiments_and_badges_match_available_meals(meal_count):
    at = capture("menu-translated")
    scan = deepcopy(at.session_state["scan"])
    scan["items"] = scan["items"][:8]
    roles = [["양념"], ["음료"], ["후식"], ["주요리"], ["주식"] if meal_count == 2 else ["곁들임"], ["주요리"], [], ["주요리"]]
    scores = [100, 99, 98, 60, 55, 97, 96, 95]
    for index, item in enumerate(scan["items"]):
        item["status"] = "ok"
        item["profile"] = dict(item.get("profile") or {}, status="known", meal_roles=roles[index], unknown_fields=[])
        item["name_ko"] = f"검증 메뉴 {index}"
        for row in item["preferences"]:
            row.update(score=scores[index], eligible=True)
    scan["items"][0]["name_ko"] = "스테이크 소스"
    scan["items"][3]["name_ko"] = "소스 곁들인 스테이크"
    scan["items"][5]["profile"]["unknown_fields"] = ["meal_roles"]
    scan["items"][6]["profile"].pop("meal_roles")
    scan["items"][7]["profile"]["status"] = "unknown"
    before = deepcopy(scan)
    at.session_state["scan"] = scan
    rerun(at)
    cards = [element.value for element in at.markdown if 'class="fg_menu_tile_content"' in element.value]
    order = [3, 4, 0, 1, 2, 5, 6, 7] if meal_count == 2 else [3, 0, 1, 2, 5, 6, 7, 4]
    assert len(cards) == 8
    for position, index in enumerate(order):
        assert scan["items"][index]["name_ko"] in cards[position]
    assert sum('class="fg_recommend_badge"' in card for card in cards) == meal_count
    assert all('class="fg_recommend_badge"' in card for card in cards[:meal_count])
    assert all('class="fg_recommend_badge"' not in card for card in cards[meal_count:])
    people = [p for p in at.session_state["people"] if p.get("active", True)]
    for item, score in zip(scan["items"], scores):
        # 식사 우선순위는 원래 평균 점수 자체를 깎거나 올리지 않는다.
        assert foodguide._menu_rank(item, people, True) == score
        assert foodguide._group_score(item, people, True) == (str(score), "점")
        assert at.button(key=f'fg_open_{item["id"]}').label.endswith(f"{score}점")
    assert at.session_state["scan"] == before


def _automatic_image_scene(at):
    scan = deepcopy(at.session_state["scan"])
    for index, item in enumerate(scan["items"]):
        item["status"] = "ok"
        item["profile"] = dict(item.get("profile") or {}, status="known", meal_roles=["주요리"], unknown_fields=[])
        for row in item["preferences"]:
            row.update(score={1: 95, 3: 90}.get(index, 10), eligible=True)
    at.session_state["scan"] = scan
    return scan, [scan["items"][1], scan["items"][3]]


def _automatic_photo(item_id, kind="remote"):
    return {"src": f"https://assets.example.test/{kind}-{item_id}.png", "label": "AI 생성 이미지" if kind != "fallback" else "기존 참고 그림",
            "title": kind, "author": "", "license": "", "source_url": "", "license_url": ""}


def _menu_cards(at):
    return [element.value for element in at.markdown if 'class="fg_menu_tile_content"' in element.value]


@pytest.mark.parametrize("has_static", [False, True])
def test_automatic_top_images_pending_then_complete_keep_order_and_means(monkeypatch, has_static):
    import httpx
    from core import generated_menu_images

    at = capture("menu-translated")
    scan, top = _automatic_image_scene(at)
    static_id = top[0]["id"] if has_static else None
    missing = [item["id"] for item in top if item["id"] != static_id]
    calls, phase = [], {"value": "pending"}

    def ensure(items, session):
        calls.append([item["id"] for item in items])
        return {item["id"]: {"status": phase["value"], "photo": _automatic_photo(item["id"]) if phase["value"] == "completed" else None,
                              "message": ""} for item in items}

    monkeypatch.setattr(generated_menu_images, "get_generated_image", lambda item: _automatic_photo(item["id"], "static") if item["id"] == static_id else None)
    monkeypatch.setattr(foodguide_images, "ensure_images", ensure)
    monkeypatch.setattr(dish_images, "menu_images", lambda items, **kwargs: {item["id"]: _automatic_photo(item["id"], "fallback") for item in items})
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **kw: pytest.fail("UI image test made a real HTTP request"))
    rerun(at)
    cards = _menu_cards(at)
    assert calls and all(ids == missing for ids in calls)
    for index, item in enumerate(top):
        assert item["name_ko"] in cards[index]
        assert at.button(key=f'fg_open_{item["id"]}').label.endswith(f'{95 if index == 0 else 90}점')
        if item["id"] in missing:
            assert "AI 이미지 생성 중" in cards[index]
            assert "fg_image_wait" in cards[index]
            assert "<img " not in cards[index] and "data:image/svg" not in cards[index]
            assert "AI 생성 이미지" not in cards[index]
    assert all("fallback-" in card for card in cards[2:])
    order_before = [widget.key for widget in at.button if widget.key and widget.key.startswith("fg_open_")]
    phase["value"] = "completed"
    rerun(at)
    assert [widget.key for widget in at.button if widget.key and widget.key.startswith("fg_open_")] == order_before
    for index, item in enumerate(top):
        card = _menu_cards(at)[index]
        kind = "static" if item["id"] == static_id else "remote"
        assert _automatic_photo(item["id"], kind)["src"] in card
        assert "AI 생성 이미지" in card and "AI 이미지 생성 중" not in card
        assert at.button(key=f'fg_open_{item["id"]}').label.endswith(f'{95 if index == 0 else 90}점')
    assert at.session_state["scan"] == scan

    # 취향을 바꾸면 이전 추천 이미지 조회를 멈추고 다시 비교하도록 안내한다.
    calls.clear()
    people = deepcopy(at.session_state["people"])
    next(person for person in people if person["id"] == "me")["favorites"].append("갈비찜")
    at.session_state["people"] = people
    rerun(at)
    assert calls == []
    assert any(widget.label == "현재 입맛으로 다시 비교" for widget in at.button)
    assert all("remote-" not in card and "static-" not in card for card in _menu_cards(at))


def test_automatic_image_retry_button_only_retries_failed_partner(monkeypatch):
    import httpx
    from core import generated_menu_images

    at = capture("menu-translated")
    scan, top = _automatic_image_scene(at)
    completed_id, failed_id = [item["id"] for item in top]
    retries, phase = [], {"failed": "failed"}

    def ensure(items, session):
        output = {}
        for item in items:
            status = "completed" if item["id"] == completed_id else phase["failed"]
            output[item["id"]] = {"status": status, "photo": _automatic_photo(item["id"]) if status == "completed" else None, "message": ""}
        return output

    def retry(items, session):
        retries.append([item["id"] for item in items])
        phase["failed"] = "pending"
        return ensure(items, session)

    monkeypatch.setattr(generated_menu_images, "get_generated_image", lambda item: None)
    monkeypatch.setattr(foodguide_images, "ensure_images", ensure)
    monkeypatch.setattr(foodguide_images, "retry_images", retry)
    monkeypatch.setattr(dish_images, "menu_images", lambda items, **kwargs: {item["id"]: _automatic_photo(item["id"], "fallback") for item in items})
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **kw: pytest.fail("UI image test made a real HTTP request"))
    rerun(at)
    assert "AI 이미지 생성 실패" in _menu_cards(at)[1]
    completed_src = _automatic_photo(completed_id)["src"]
    assert completed_src in _menu_cards(at)[0]
    at.button(key="fg_retry_images").click()
    rerun(at)
    assert retries == [[failed_id]]
    assert completed_src in _menu_cards(at)[0]
    assert "AI 이미지 생성 중" in _menu_cards(at)[1]
    # AppTest는 fragment rerun 전 버튼 노드를 남기므로 실제 위젯 상태 제거를 확인한다.
    assert "fg_retry_images" not in at.session_state.filtered_state
    phase["failed"] = "completed"
    rerun(at)
    assert _automatic_photo(failed_id)["src"] in _menu_cards(at)[1]
    assert retries == [[failed_id]] and at.session_state["scan"] == scan
