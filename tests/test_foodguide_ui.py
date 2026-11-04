"""실제 API 응답 시드로 Streamlit 화면과 세션 전환을 검증한다. 외부 호출 없음."""
from copy import deepcopy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Widget

from core import foodguide_flow, menu2, ocr, reviews, store, webmenu
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
                         (webmenu, "read_web"), (screens, "geo_block")):
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


def test_recommendation_uses_selected_person_not_global_match():
    at = capture("menu-translated")
    scan = deepcopy(at.session_state["scan"])
    first = scan["items"][0]
    for row in first["preferences"]:
        row.update(score=12.2 if row["id"] == "me" else 87.2, eligible=True)
    first["matches"] = [{"name": "다른 한식", "score": 99.9}]
    at.session_state["scan"] = scan
    rerun(at)
    assert at.selectbox(key="fg_menu_person").value == "me"
    assert at.button(key=f'fg_open_{first["id"]}').label.endswith("12점")
    at.selectbox(key="fg_menu_person").select("mom")
    rerun(at)
    assert at.button(key=f'fg_open_{first["id"]}').label.endswith("87점")
    at.button(key=f'fg_open_{first["id"]}').click()
    rerun(at)
    button(at, "메뉴판으로").click()
    rerun(at)
    assert at.selectbox(key="fg_menu_person").value == "mom"
    assert at.button(key=f'fg_open_{first["id"]}').label.endswith("87점")


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
