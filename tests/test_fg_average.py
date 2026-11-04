"""가족 평균은 비교 기준이 있는 사람만으로 낸다. 제한은 그대로 추천에서 막는다. 외부 호출 없음."""
from copy import deepcopy

from core import foodguide_flow
from ui import foodguide

# AppTest 하네스와 외부 호출 차단 fixture(autouse)를 함께 쓴다.
from test_foodguide_ui import capture, isolated_capture, rerun, text  # noqa: F401


PEOPLE = [{"id": "me", "name": "나"}, {"id": "mom", "name": "엄마"},
          {"id": "dad", "name": "아빠"}, {"id": "kid", "name": "아이"}]


def item(**overrides):
    rows = {"me": (80, True, 1), "mom": (60, True, 1), "dad": (40, True, 2), "kid": (None, True, 0)}
    rows.update(overrides)
    return {"status": "ok", "preferences": [{"id": pid, "score": score, "eligible": eligible, "reference_count": count}
                                            for pid, (score, eligible, count) in rows.items()]}


def test_member_without_basis_is_left_out_of_mean_not_zeroed():
    dish = item()
    assert foodguide._menu_rank(dish, PEOPLE, True) == 60
    assert foodguide._group_score(dish, PEOPLE, True) == ("60", "점")
    assert foodguide._no_basis([dish], PEOPLE, True) == [PEOPLE[3]]
    # 연결된 기준 음식이 0개면 숫자가 와도 평균에 넣지 않는다.
    stray = item(kid=(0, True, 0))
    assert foodguide._menu_rank(stray, PEOPLE, True) == 60
    # 기준이 있는 사람의 점수 null(정보 부족)도 그 메뉴에서만 뺀다.
    partial = item(dad=(None, True, 2))
    assert foodguide._menu_rank(partial, PEOPLE, True) == 70
    assert foodguide._no_basis([dish, partial], PEOPLE, True) == [PEOPLE[3]]


def test_restriction_and_unknown_eligibility_still_block_the_dish():
    for overrides, reason in (({"kid": (None, False, 0)}, "제한 확인"), ({"dad": (40, False, 2)}, "제한 확인"),
                              ({"kid": (None, None, 0)}, "점수 없음"), ({"dad": (40, None, 2)}, "확인 필요"),
                              ({"dad": (float("nan"), True, 2)}, "점수 없음")):
        dish = item(**overrides)
        assert foodguide._menu_rank(dish, PEOPLE, True) == -1
        assert foodguide._group_score(dish, PEOPLE, True) == ("—", reason)
    assert foodguide._menu_rank(item(), PEOPLE, False) == -1


def test_nobody_with_basis_gives_no_mean():
    dish = item(me=(None, True, 0), mom=(None, True, 0), dad=(None, True, 0))
    assert foodguide._menu_rank(dish, PEOPLE, True) == -1
    assert foodguide._group_score(dish, PEOPLE, True) == ("—", "점수 없음")
    assert foodguide._no_basis([dish], PEOPLE, True) == PEOPLE


def rescan(at, no_basis, restrict=None):
    """완료된 실제 응답에서 일부 사람의 기준 음식 연결만 없앤 상태로 다시 만든다."""
    report = deepcopy(at.session_state["scan_report"])
    summary = deepcopy(at.session_state["foodguide_summary"])
    for row in report["items"]:
        for pref in row["preferences"]:
            if pref["name"] in no_basis:
                pref.update(score=None, eligible=True)
            if restrict and (row["input_name"], pref["name"]) == restrict:
                pref["eligible"] = False
    for row in summary:
        if row["id"] in no_basis:
            row["unresolved"] += [{"name": food["favorite"], "status": "unresolved", "candidates": []} for food in row["resolved_foods"]]
            row.update(resolved=0, resolved_foods=[])
    ids = {person["id"] for person in at.session_state["scan"]["people"]}
    people = [person for person in at.session_state["people"] if person["id"] in ids]
    scan = foodguide_flow.build_scan(report, people, summary, at.session_state["foodguide_metadata"])
    at.session_state["scan"] = scan
    at.session_state["foodguide_summary"] = summary
    rerun(at)
    cards = [element.value for element in at.markdown if 'class="fg_menu_tile_content"' in element.value]
    return scan, people, cards


def means(scan, ids):
    out = {}
    for row in scan["items"]:
        scores = [p["score"] for p in row["preferences"] if p["id"] in ids]
        if foodguide._is_meal(row) and all(p["eligible"] is True for p in row["preferences"]):
            out[row["id"]] = sum(scores) / len(scores)
    return out


def test_partial_family_keeps_ranking_badges_and_names_who_was_left_out():
    at = capture("menu-translated")
    scan, people, cards = rescan(at, {"jiwoo"})
    expected = means(scan, {"me", "mom", "dad"})
    top = sorted(expected, key=lambda iid: -expected[iid])[:2]
    names = {row["id"]: row["name_ko"] for row in scan["items"]}
    assert [names[iid] in cards[index] for index, iid in enumerate(top)] == [True, True]
    assert sum('class="fg_recommend_badge"' in card for card in cards) == 2
    assert "3명 평균 점수" in cards[0] and "아이: —" in cards[0]
    assert at.button(key=f"fg_open_{top[0]}").label.endswith(f"{round(expected[top[0]])}점")
    page = text(at)
    assert "구성원 3명 평균" in page
    assert "아이는 좋아하는 음식이 비교 기준에 없어서 평균에서 뺐어요." in page
    edit = at.button(key="fg_basis_edit_jiwoo")
    assert edit.label == "아이 좋아하는 음식 고르기"
    edit.click()
    rerun(at)
    assert at.session_state["view"] == "edit" and at.session_state["edit_id"] == "jiwoo"


def test_partial_family_restriction_is_never_recommended():
    at = capture("menu-translated")
    scan, _, _ = rescan(at, {"jiwoo"})
    best = max(means(scan, {"me", "mom", "dad"}).items(), key=lambda pair: pair[1])[0]
    best_input = next(row["input_name"] for row in scan["items"] if row["id"] == best)
    scan, _, cards = rescan(at, {"jiwoo"}, restrict=(best_input, "mom"))
    name = next(row["name_ko"] for row in scan["items"] if row["id"] == best)
    card = next(card for card in cards if name in card)
    assert 'class="fg_recommend_badge"' not in card
    assert cards.index(card) >= 2
    assert at.button(key=f"fg_open_{best}").label.endswith("—제한 확인")
    assert sum('class="fg_recommend_badge"' in card for card in cards) == 2


def test_nobody_with_basis_keeps_menu_order_and_shows_note():
    at = capture("menu-translated")
    scan, _, cards = rescan(at, {"me", "mom", "dad", "jiwoo"})
    assert all(row["name_ko"] in cards[index] for index, row in enumerate(scan["items"]))
    assert all('class="fg_recommend_badge"' not in card for card in cards)
    assert all("평균 추천 점수" in card for card in cards)
    assert "나, 엄마, 아빠, 아이는 좋아하는 음식이 비교 기준에 없어서 추천 점수를 못 냈어요." in text(at)
    assert "구성원 4명" in text(at) and "명 평균" not in text(at)


def test_simple_mode_without_basis_shows_note_and_no_score():
    at = capture("simple-menu")
    _, people, cards = rescan(at, {"mom"})
    assert [person["id"] for person in people] == ["mom"]
    assert all('class="fg_recommend_badge"' not in card for card in cards)
    assert all("추천 점수" in card and "명 평균" not in card for card in cards)
    assert "엄마는 좋아하는 음식이 비교 기준에 없어서 추천 점수를 못 냈어요." in text(at)


def test_combo_does_not_list_member_without_basis_as_uncovered():
    at = capture("combo-all")
    rescan(at, {"jiwoo"})
    page = text(at)
    assert "아이는 좋아하는 음식이 비교 기준에 없어서 입맛 비교에서 뺐어요." in page
    assert "충분히 맞추지 못한 사람" not in page


def test_full_family_shows_no_note():
    at = capture("menu-translated")
    assert "비교 기준에 없어서" not in text(at)
    assert not any(widget.key and widget.key.startswith("fg_basis_edit_") for widget in at.button)
