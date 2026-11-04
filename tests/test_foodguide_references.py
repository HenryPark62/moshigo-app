"""선호 음식 연결은 모호한 음식이나 닮은 음식을 임의로 선택하지 않는다."""
from types import SimpleNamespace
import json

import pytest

from core.foodguide_client import FoodGuideError
from core.foodguide_references import resolve, signature


def item(name, *, source="dataset", resolution="canonical", fid="KF0001", status="ok", candidates=None):
    return {"input_name": name, "status": status, "name_resolution": resolution,
            "profile": {"id": fid, "name": name + " 대표형", "source": source},
            "candidates": candidates or [], "matches": [{"id": "WRONG", "name": "다른 음식", "score": 99}]}


class StubClient:
    def __init__(self, items=None, key="private-key", url="https://food.example"):
        self.config = SimpleNamespace(base_url=url, api_key=key)
        self.items = items or {}
        self.calls = []

    def run_text(self, names, preferences, **kwargs):
        self.calls.append((names, preferences, kwargs))
        assert preferences == [] and "menu_context" not in kwargs
        return {"items": [self.items.get(name, item(name)) for name in names], "dataset_sha256": "dataset-version"}


def person(pid="me", name="나", favorites=None, **kwargs):
    return {"id": pid, "name": name, "favorites": favorites or [], **kwargs}


def test_duplicate_display_names_use_unique_person_ids_and_cache():
    client, jobs, cache = StubClient(), {}, {}
    people = [person("one", "가족", ["국"]), person("two", "가족", ["국"])]
    prefs, summaries = resolve(people, client, jobs, cache)
    assert [p["name"] for p in prefs] == ["one", "two"]
    assert [s["name"] for s in summaries] == ["가족", "가족"]
    assert all(p["liked_food_ids"] == ["KF0001"] for p in prefs)
    assert len(client.calls) == 1
    assert client.calls[0][2]["state"] is jobs
    assert client.calls[0][2]["operation_key"].startswith("references:")
    assert resolve(people, client, jobs, cache) == (prefs, summaries)
    assert len(client.calls) == 1
    assert "private-key" not in json.dumps(cache)
    assert set(cache["foods"]["국"]) == {"id", "name", "candidates", "status", "resolution", "dataset_sha"}


@pytest.mark.parametrize("people", [
    [person(str(n)) for n in range(7)], [person("same"), person("same")],
    [person("same"), person(" same ")], [person(favorites=[str(n) for n in range(51)])],
    [person(favorites=["x" * 201])],
])
def test_invalid_people_fail_without_api(people):
    client = StubClient()
    with pytest.raises(FoodGuideError) as error:
        resolve(people, client, {}, {})
    assert error.value.code == "invalid_request" and client.calls == []


def test_only_active_people_count_and_favorites_batch_in_twenty():
    client = StubClient()
    names = [f"음식{n}" for n in range(43)]
    people = [person(favorites=names), *[person(str(n), active=False) for n in range(7)]]
    prefs, summary = resolve(people, client, {}, {})
    assert [len(call[0]) for call in client.calls] == [20, 20, 3]
    assert len(prefs) == 1 and summary[0]["total"] == 43
    assert prefs[0]["liked_food_ids"] == ["KF0001"]


def test_unresolved_never_uses_match_or_ai_id_and_preserves_favorites():
    names = ["추정 음식", "번역 별칭", "미상", "오류", "대표형"]
    items = {
        names[0]: item(names[0], source="ai_estimate"),
        names[1]: item(names[1], resolution="generated_alias"),
        names[2]: item(names[2], source="ai_estimate", status="unknown"),
        names[3]: item(names[3], source="ai_estimate", status="error"),
        names[4]: item(names[4], resolution="dataset_alias", status="insufficient"),
    }
    people = [person(favorites=names)]
    before = json.dumps(people)
    prefs, summary = resolve(people, StubClient(items), {}, {})
    assert prefs[0]["liked_food_ids"] == ["KF0001"]
    assert summary[0]["resolved"] == 1 and summary[0]["total"] == 5
    assert [x["name"] for x in summary[0]["unresolved"]] == names[:4]
    assert [x["status"] for x in summary[0]["unresolved"]] == ["unresolved", "unresolved", "unknown", "error"]
    assert json.dumps(people) == before


def test_ambiguous_candidate_requires_valid_selection_and_uses_server_name():
    candidates = [{"id": "KF0100", "name": "돼지고기 김치찌개"}, {"id": "KF0101", "name": "참치 김치찌개"}]
    client, jobs, cache = StubClient({"김치찌개": item("김치찌개", source="manual", status="ambiguous", candidates=candidates)}), {}, {}
    p = person(favorites=["김치찌개"])
    prefs, summary = resolve([p], client, jobs, cache)
    assert prefs[0]["liked_food_ids"] == []
    assert summary[0]["unresolved"][0]["candidates"] == candidates
    p["foodguide_refs"] = {"김치찌개": {"id": "WRONG", "name": "잘못된 선택"}}
    assert resolve([p], client, jobs, cache)[0][0]["liked_food_ids"] == []
    p["foodguide_refs"] = {"김치찌개": {"id": "KF0101", "name": "조작된 이름"}}
    prefs, summary = resolve([p], client, jobs, cache)
    assert prefs[0]["liked_food_ids"] == ["KF0101"]
    assert summary[0]["resolved_foods"] == [{"favorite": "김치찌개", **candidates[1]}]
    assert len(client.calls) == 1


def test_limits_and_unsupported_avoid_values_are_explicit():
    p = person(allergies=["우유", "견과류"], cannot=["우유", "술"],
               avoid=["매운 음식", "질긴 것", "짠 음식", "향이 강한 음식"])
    prefs, summary = resolve([p], StubClient(), {}, {})
    assert prefs[0] == {"name": "me", "liked_food_ids": [], "avoid_ingredients": ["우유", "견과류", "술"],
                        "max_chili_heat": 2, "max_chewiness": 2}
    assert summary[0]["not_applied"] == ["짠 음식", "향이 강한 음식"]
    assert summary[0]["total"] == summary[0]["resolved"] == 0


@pytest.mark.parametrize("changed", [{"key": "different-private-key"}, {"url": "https://different.example"}])
def test_cache_is_scoped_to_credentials_and_origin(changed):
    cache, jobs, people = {}, {}, [person(favorites=["국"])]
    first = StubClient()
    resolve(people, first, jobs, cache)
    old_scope = cache["scope"]
    second = StubClient(**changed)
    resolve(people, second, jobs, cache)
    assert len(second.calls) == 1 and cache["scope"] != old_scope
    assert first.calls[0][2]["operation_key"] != second.calls[0][2]["operation_key"]
    assert "private-key" not in json.dumps(cache)


def test_client_failure_propagates_without_caching_missing_food():
    class Broken(StubClient):
        def run_text(self, *_args, **_kwargs):
            raise FoodGuideError("wait_timeout", "대기", job_id="a" * 32)
    cache = {}
    with pytest.raises(FoodGuideError) as error:
        resolve([person(favorites=["국"])], Broken(), {}, cache)
    assert error.value.job_id == "a" * 32 and cache["foods"] == {}


@pytest.mark.parametrize("key,value", [("id", "other"), ("name", "다른 이름"), ("active", False),
    ("favorites", ["국"]), ("foodguide_refs", {"국": {"id": "KF0001", "name": "국"}}),
    ("avoid", ["매운 음식"]), ("cannot", ["술"]), ("allergies", ["우유"]),
    ("child", {"good": ["감자"]}), ("likes", ["고소한"])])
def test_signature_covers_profile_settings(key, value):
    p = person()
    assert signature([p]) != signature([{**p, key: value}])
    assert signature([p]) == signature([dict(reversed(list(p.items())))])
