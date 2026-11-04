"""API 응답의 의미·입력 경로·세션 재개 경계를 확인한다. 외부 호출 없음."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from core import foodguide_flow as flow
from core.foodguide_client import FoodGuideError


PEOPLE = [{"id": "one", "name": "가족", "active": True, "favorites": ["예시 기준 음식"]},
          {"id": "two", "name": "가족", "active": True, "favorites": []}]
SUMMARY = [{"id": "one", "name": "가족", "total": 1, "resolved": 1, "not_applied": ["짠 음식"]},
           {"id": "two", "name": "가족", "total": 0, "resolved": 0, "not_applied": []}]


def report():
    return {"schema_version": "menu-guide-v1", "items": [
        {"input_name": "Menu", "status": "ok", "profile": {"name": "메뉴", "description": "설명", "main_ingredients": ["재료"]},
         "menu_context": {"original_name": "Menu", "korean_name": "메뉴", "price": "12 €", "photo_bbox": [.1, .1, .2, .2]},
         "matches": [{"id": "global", "name": "전역 비교 음식", "score": 80, "coverage": .8}],
         "preferences": [{"name": "one", "score": 73, "eligible": True, "reasons": ["기준 음식과 비교"], "ingredient_check": "직원 확인 필요"},
                         {"name": "two", "score": None, "eligible": False, "reasons": ["재료 미확인"]}],
         "text": "API 설명", "weak_match": False}],
        "group": {"menu_names": ["Menu"], "member_coverage": [{"name": "one", "menu_name": "Menu", "score": 73}],
                  "uncovered_members": ["two"], "text": "각자 메뉴를 고릅니다", "limitations": "인분 미반영"},
        "warnings": ["추정값"], "extraction": {"language": "fr", "items": []}, "result_text": "API 설명"}


def test_global_matches_are_not_personal_favorites_and_null_is_not_zero():
    raw = report()
    scan = flow.build_scan(raw, PEOPLE, SUMMARY)
    item = scan["items"][0]
    assert item["matches"][0]["name"] == "전역 비교 음식"
    assert [p["score"] for p in item["preferences"]] == [73, None]
    assert [p["id"] for p in item["preferences"]] == ["one", "two"]
    assert item["preferences"][1]["eligible"] is False
    assert "match" not in item and "map" not in item and "taste" not in item and "serve_minutes" not in item
    assert scan["combos"] == []
    assert scan["language_code"] == "fr" and scan["menu_language"] == "프랑스어"
    assert scan["group"]["member_coverage"][0]["person_id"] == "one"
    assert scan["group"]["uncovered_members"] == ["가족"]
    assert scan["report"] == raw and scan["report"] is not raw
    assert "짠 음식" in scan["warnings"][-1]


@pytest.mark.parametrize("status", ["unknown", "ambiguous", "error", "insufficient"])
def test_partial_menu_status_remains_visible_without_invented_data(status):
    raw = report()
    raw["items"][0].update(status=status, profile=None, matches=[], preferences=[], menu_context={})
    scan = flow.build_scan(raw, PEOPLE, SUMMARY)
    item = scan["items"][0]
    assert item["status"] == status and item["profile"] is None
    assert item["price"] == "" and item["desc_ko"] == ""
    assert item["preferences"][0]["score"] is None and item["preferences"][0]["eligible"] is None
    assert scan["group"]["menu_ids"] == []


def test_weak_match_is_not_failed_recognition():
    raw = report()
    raw["items"][0].update(weak_match=True, matches=[])
    item = flow.build_scan(raw, PEOPLE, SUMMARY)["items"][0]
    assert item["status"] == "ok" and item["weak_match"] and item["preferences"][0]["score"] == 73


def test_original_description_is_not_mislabeled_as_korean_translation():
    raw = report()
    raw["items"][0]["profile"]["description"] = ""
    raw["items"][0]["menu_context"]["description"] = "mijoté au vin rouge"
    item = flow.build_scan(raw, PEOPLE, SUMMARY)["items"][0]
    assert item["description_original"] == "mijoté au vin rouge"
    assert item["desc_ko"] == "주재료: 재료"


def test_group_cannot_assign_ineligible_person_or_unknown_menu():
    raw = report()
    raw["group"]["member_coverage"] += [{"name": "two", "menu_name": "Menu", "score": 99},
                                         {"name": "one", "menu_name": "other", "score": 99}]
    group = flow.build_scan(raw, PEOPLE, SUMMARY)["group"]
    assert len(group["member_coverage"]) == 1
    assert group["uncovered_members"] == ["가족"]


@pytest.fixture
def fake_service(monkeypatch):
    calls = []
    class FakeClient:
        def __init__(self, config):
            self.config = config
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def run_image(self, data, mime, **kwargs):
            calls.append(("image", data, mime, kwargs))
            return report()
        def run_text(self, menus, preferences, context, **kwargs):
            calls.append(("text", menus, preferences, context, kwargs))
            raw = report()
            raw.pop("extraction")
            return raw
    monkeypatch.setattr(flow, "Client", FakeClient)
    monkeypatch.setattr(flow.store, "take_scan", lambda: True)
    monkeypatch.setattr(flow.Config, "from_env", lambda: SimpleNamespace(base_url="http://127.0.0.1:8000", api_key="test"))
    monkeypatch.setattr(flow.references, "resolve", lambda *args: ([{"name": "one"}, {"name": "two"}], deepcopy(SUMMARY)))
    return calls


def test_image_route_uses_foodguide_and_preserves_session_metadata(fake_service, monkeypatch):
    from core import menu2, ocr
    monkeypatch.setattr(menu2, "read_menu", lambda *_: pytest.fail("legacy vision called"))
    monkeypatch.setattr(ocr, "read", lambda *_: pytest.fail("legacy OCR called"))
    session = {"place": {"name": "Known restaurant", "id": "place"}, "scan_raw": {"old": True}}
    scan = flow.run_image(b"image", "image/jpeg", PEOPLE, session)
    assert fake_service[0][0] == "image"
    assert scan["restaurant"] == "Known restaurant"
    assert session["scan_img"] == b"image" and session["scan_source"] == "foodguide"
    assert "scan_raw" not in session and session["place"] is None
    assert not flow.stale(PEOPLE, session)


def test_refresh_reuses_extracted_text_without_photo_bbox_or_second_ocr(fake_service):
    session = {}
    flow.run_image(b"image", "image/jpeg", PEOPLE, session)
    changed = deepcopy(PEOPLE)
    changed[0]["favorites"] = []
    assert flow.stale(changed, session)
    scan = flow.refresh(changed, session)
    assert [c[0] for c in fake_service] == ["image", "text"]
    assert "photo_bbox" not in fake_service[1][3]["Menu"]
    assert scan["language_code"] == "fr" and session["scan_img"] == b"image"
    assert not flow.stale(changed, session)


def test_refresh_preserves_ai_currency_evidence_without_repeating_ocr(fake_service):
    session = {}
    flow.run_image(b"image", "image/jpeg", PEOPLE, session)
    currency = {"currency_code": "", "currency_source": "inferred", "currency_evidence": "유로(EUR)로 추정"}
    session["scan_report"]["extraction"].update(currency)
    session["scan"] = flow.build_scan(session["scan_report"], PEOPLE)
    for _ in range(2):
        scan = flow.refresh(PEOPLE, session)
        assert scan["currency"] == currency
    assert [c[0] for c in fake_service] == ["image", "text", "text"]


def test_failure_remains_resumable_and_never_falls_back_to_demo(fake_service, monkeypatch):
    def fail(*args, **kwargs):
        raise FoodGuideError("wait_timeout", "아직 처리 중", job_id="a" * 32)
    monkeypatch.setattr(flow.Client, "run_image", fail)
    session = {}
    with pytest.raises(FoodGuideError):
        flow.run_image(b"image", "image/jpeg", PEOPLE, session)
    assert "scan" not in session and session["foodguide_pending"]["image"] == b"image"
    assert session["foodguide_error"]["job_id"] == "a" * 32
    monkeypatch.setattr(flow.Client, "run_image", lambda *a, **kw: report())
    flow.resume(PEOPLE, session)
    assert session["scan"]["provider"] == "foodguide" and "foodguide_error" not in session


def test_invalid_photo_rejected_before_reference_or_provider_call(fake_service):
    with pytest.raises(FoodGuideError, match="15MB"):
        flow.run_image(b"", "image/jpeg", PEOPLE, {})
    assert fake_service == []


def test_web_search_bypasses_claude_description_and_preserves_source(fake_service, monkeypatch):
    from core import webmenu
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-used")
    monkeypatch.setattr(webmenu, "read_web", lambda *_: pytest.fail("old description called"))
    monkeypatch.setattr(webmenu, "find_menu", lambda *_: {"head": {"lines": [{"name_orig": "Menu", "note": "real description", "price": "12 €"}],
                                                                  "language_code": "fr", "restaurant": "Found restaurant"},
                                                         "source": {"kind": "web", "url": "https://example.test/menu"}})
    session = {"scan_img": b"previous"}
    scan = flow.run_web({"name": "restaurant"}, PEOPLE, session)
    assert fake_service[0][0] == "text"
    assert fake_service[0][3]["Menu"]["description"] == "real description"
    assert scan["source"]["url"] == "https://example.test/menu"
    assert scan["language_code"] == "fr" and session["scan_img"] is None


def test_web_duplicate_names_and_limit_are_explicit():
    lines = [{"name_orig": "Menu", "price": "1"}, {"name_orig": "Menu", "price": "2"}]
    lines += [{"name_orig": f"Menu {i}"} for i in range(25)]
    pending = flow._web_input({"head": {"lines": lines}}, {})
    assert len(pending["menus"]) == 20 and pending["context"]["Menu"]["price"] == "1"
    assert len(pending["metadata"]["warnings"]) == 2


def test_failed_web_lookup_does_not_resume_an_older_photo(fake_service, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    session = {"foodguide_pending": {"kind": "image", "image": b"old"}}
    with pytest.raises(FoodGuideError):
        flow.run_web({"name": "new restaurant"}, PEOPLE, session)
    assert session["foodguide_pending"]["kind"] == "web_lookup"
    with pytest.raises(FoodGuideError):
        flow.resume(PEOPLE, session)
    assert fake_service == []


def test_native_mode_is_default_with_explicit_legacy_rollback(monkeypatch):
    monkeypatch.delenv("MOSHIGO_ANALYSIS_PROVIDER", raising=False)
    assert flow.enabled()
    monkeypatch.setenv("MOSHIGO_ANALYSIS_PROVIDER", "legacy")
    assert not flow.enabled()


def test_refresh_preserves_new_photo_pending_instead_of_old_report(fake_service, monkeypatch):
    session = {}
    flow.run_image(b"photo-A", "image/jpeg", PEOPLE, session)
    original = flow.Client.run_image
    def pending(*args, **kwargs):
        raise FoodGuideError("wait_timeout", "대기 중", job_id="b" * 32)
    monkeypatch.setattr(flow.Client, "run_image", pending)
    with pytest.raises(FoodGuideError):
        flow.run_image(b"photo-B", "image/jpeg", PEOPLE, session)
    assert session["scan_report"] and session["foodguide_pending"]["image"] == b"photo-B"
    monkeypatch.setattr(flow.Client, "run_image", original)
    flow.refresh(PEOPLE, session)
    assert [call[0] for call in fake_service] == ["image", "image"]
    assert fake_service[-1][1] == b"photo-B"
    assert session["scan_img"] == b"photo-B"


def test_code_owner_change_invalidates_even_identical_profiles(fake_service):
    session = {"code": "ownerA"}
    flow.run_image(b"image", "image/jpeg", PEOPLE, session)
    session["code"] = "ownerB"
    assert flow.stale(PEOPLE, session)
    session.update(fg_qty_test=2, foodguide_picks={"item": 2}, _fg_ui_error={"code": "failed"})
    flow.clear_analysis(session)
    assert session == {"code": "ownerB"}


def test_daily_gate_charges_new_analysis_but_not_job_resume(fake_service, monkeypatch):
    charged = []
    monkeypatch.setattr(flow.store, "take_scan", lambda: charged.append(1) or True)
    session = {}
    flow.run_image(b"same", "image/jpeg", PEOPLE, session)
    flow.resume(PEOPLE, session)
    assert len(charged) == 1
    flow.restart(session)
    flow.resume(PEOPLE, session)
    assert len(charged) == 2


def test_daily_gate_rejects_before_upstream_requests(fake_service, monkeypatch):
    monkeypatch.setattr(flow.store, "take_scan", lambda: False)
    with pytest.raises(FoodGuideError, match="한도"):
        flow.run_image(b"image", "image/jpeg", PEOPLE, {})
    assert fake_service == []


def test_inflight_result_cannot_repopulate_different_code_session(fake_service, monkeypatch):
    session = {"code": "ownerA"}
    def finish_after_code_change(*args, **kwargs):
        flow.clear_analysis(session)
        session["code"] = "ownerB"
        return report()
    monkeypatch.setattr(flow.Client, "run_image", finish_after_code_change)
    with pytest.raises(FoodGuideError) as error:
        flow.run_image(b"ownerA-photo", "image/jpeg", PEOPLE, session)
    assert error.value.code == "session_changed"
    assert session == {"code": "ownerB"}


def test_reread_clears_completed_photo_job_and_gate_but_keeps_reference_work(monkeypatch):
    reference_job = {"job_id": "r" * 32, "result": {"reference": True}}
    reference_cache = {"foods": {"갈비찜": {"id": "known-food"}}}
    session = {"scan_img": b"saved-jpeg", "foodguide_gate": "previous-charge",
               "foodguide_pending": {"kind": "image", "image": b"saved-jpeg", "mime": "image/jpeg"},
               "foodguide_jobs": {"analysis-image": {"job_id": "i" * 32, "result": report()},
                                  "reference-foods": reference_job,
                                  "analysis-text": {"result": {"previous-text": True}}},
               "foodguide_reference_cache": reference_cache}
    progress = lambda value: None
    observed = []
    def submit(data, mime, people, state, on_progress=None):
        observed.append((data, mime, people, on_progress))
        assert state is session
        assert "analysis-image" not in state["foodguide_jobs"]
        assert "foodguide_gate" not in state
        assert state["foodguide_jobs"]["reference-foods"] is reference_job
        assert state["foodguide_jobs"]["analysis-text"]["result"] == {"previous-text": True}
        assert state["foodguide_reference_cache"] is reference_cache
        return {"new": "photo-result"}
    monkeypatch.setattr(flow, "run_image", submit)
    assert flow.reread_image(PEOPLE, session, progress) == {"new": "photo-result"}
    assert observed == [(b"saved-jpeg", "image/jpeg", PEOPLE, progress)]


def test_reread_pending_unfinished_job_resumes_without_error_or_gate_reset(monkeypatch):
    session = {"scan_img": b"saved-jpeg", "foodguide_gate": "same-charge",
               "foodguide_pending": {"kind": "image", "image": b"saved-jpeg", "mime": "image/jpeg"},
               "foodguide_jobs": {"analysis-image": {"job_id": "i" * 32}}}
    before = deepcopy(session)
    def resume(people, state, on_progress=None):
        assert state == before
        return "same-job"
    monkeypatch.setattr(flow, "resume", resume)
    monkeypatch.setattr(flow, "run_image", lambda *a, **kw: pytest.fail("unfinished job resubmitted"))
    assert flow.reread_image(PEOPLE, session) == "same-job"


def test_reread_saved_input_without_cached_job_resets_gate_for_new_request(monkeypatch):
    session = {"scan_img": b"saved-jpeg", "foodguide_gate": "previous-charge",
               "foodguide_pending": {"kind": "image", "image": b"saved-jpeg", "mime": "image/jpeg"},
               "foodguide_jobs": {"reference-foods": {"result": {"reference": True}}}}
    def submit(data, mime, people, state, on_progress=None):
        assert "foodguide_gate" not in state
        assert state["foodguide_jobs"] == {"reference-foods": {"result": {"reference": True}}}
        return "new-photo-request"
    monkeypatch.setattr(flow, "run_image", submit)
    monkeypatch.setattr(flow, "resume", lambda *a, **kw: pytest.fail("completed saved input resumed"))
    assert flow.reread_image(PEOPLE, session) == "new-photo-request"


@pytest.mark.parametrize("kind", ["image", "text", "web_lookup"])
def test_reread_existing_pending_delegates_resume_without_reset(monkeypatch, kind):
    session = {"scan_img": b"older-photo", "foodguide_pending": {"kind": kind, "image": b"newer-photo"},
               "foodguide_error": {"code": "wait_timeout"}, "foodguide_gate": "keep-charge",
               "foodguide_jobs": {"analysis-image": {"job_id": "n" * 32, "result": report()},
                                  "reference-foods": {"job_id": "r" * 32}}}
    before = deepcopy(session)
    calls = []
    progress = lambda value: None
    def resume(people, state, on_progress=None):
        calls.append((people, on_progress))
        assert state is session and state == before
        return "resumed-pending"
    monkeypatch.setattr(flow, "resume", resume)
    monkeypatch.setattr(flow, "run_image", lambda *a, **kw: pytest.fail("pending photo was resubmitted"))
    assert flow.reread_image(PEOPLE, session, progress) == "resumed-pending"
    assert calls == [(PEOPLE, progress)] and session == before


@pytest.mark.parametrize("photo, expected", [
    (b"\x89PNG\r\n\x1a\nfixture", "image/png"),
    (b"RIFF\x10\x00\x00\x00WEBPfixture", "image/webp"),
    (b"\xff\xd8\xfffixture", "image/jpeg"),
    (b"RIFF\x10\x00\x00\x00WAVEfixture", "image/jpeg"),
])
def test_reread_uses_saved_image_signature_for_mime(monkeypatch, photo, expected):
    calls = []
    def submit(data, mime, people, state, on_progress=None):
        calls.append((data, mime))
        return "submitted"
    monkeypatch.setattr(flow, "run_image", submit)
    assert flow.reread_image(PEOPLE, {"scan_img": photo}) == "submitted"
    assert calls == [(photo, expected)]


@pytest.mark.parametrize("photo", [None, b"", "not-image-bytes"])
def test_reread_without_saved_photo_fails_before_touching_jobs(monkeypatch, photo):
    session = {"scan_img": photo, "foodguide_gate": "keep-charge",
               "foodguide_jobs": {"analysis-image": {"result": report()}}}
    before = deepcopy(session)
    monkeypatch.setattr(flow, "run_image", lambda *a, **kw: pytest.fail("missing photo submitted"))
    with pytest.raises(FoodGuideError) as error:
        flow.reread_image(PEOPLE, session)
    assert error.value.code == "invalid_image"
    assert "사진이 없어요" in error.value.message
    assert session == before
