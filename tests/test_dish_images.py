"""대표 사진 검증·캐시·개인 사진 경계를 모의 HTTP로 확인한다."""
import base64
from concurrent.futures import Future, ThreadPoolExecutor
import io
import threading
import time

import httpx
from PIL import Image
import pytest

from core import dish_images as images


@pytest.fixture(autouse=True)
def clean_state():
    with images._lock:
        images._cache.clear()
        images._cooldown_until = 0
    yield
    with images._lock:
        images._cache.clear()
        images._cooldown_until = 0


def wiki_page(**changes):
    return {"query": {"pages": {"1": {"title": "Schnitzel", "pageimage": "Schnitzel.jpg",
        "categories": [{"title": "Category:Meat dishes"}], **changes}}}}


def commons(**changes):
    info = {"thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/Schnitzel.jpg",
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Schnitzel.jpg",
            "extmetadata": {"Artist": {"value": "<a>Photo Author</a>"}, "LicenseShortName": {"value": "CC BY-SA 4.0"},
                            "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"}}, **changes}
    return {"query": {"pages": {"2": {"imageinfo": [info]}}}}


def transport(page=None, file=None, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(request)
        return httpx.Response(200, json=(page or wiki_page()) if request.url.host == "en.wikipedia.org" else file or commons())
    return httpx.MockTransport(handler)


def test_verified_photo_has_credit_and_fixed_query():
    calls = []
    result = images._lookup("Schnitzel", transport(calls=calls))
    assert result["label"] == "대표 사진" and result["author"] == "Photo Author"
    assert result["license"] == "CC BY-SA 4.0"
    assert result["src"].startswith("https://upload.wikimedia.org/")
    assert calls[0].url.params["titles"] == "Schnitzel"
    assert [r.url.host for r in calls] == ["en.wikipedia.org", "commons.wikimedia.org"]


@pytest.mark.parametrize("change", [
    {"thumburl": "http://upload.wikimedia.org/photo.jpg"},
    {"thumburl": "https://upload.wikimedia.org.evil.test/photo.jpg"},
    {"thumburl": "https://user:password@upload.wikimedia.org/photo.jpg"},
    {"thumburl": "https://upload.wikimedia.org:8080/photo.jpg"},
    {"descriptionurl": "https://evil.test/photo"},
    {"extmetadata": {"Artist": {"value": "Author"}, "LicenseShortName": {"value": "All rights reserved"}}},
    {"extmetadata": {"Artist": {"value": ""}, "LicenseShortName": {"value": "CC0"}}},
    {"extmetadata": {"Artist": {"value": "Author"}, "LicenseShortName": {"value": "CC BY 4.0"}}},
])
def test_untrusted_or_unlicensed_photos_rejected(change):
    assert images._lookup("Schnitzel", transport(file=commons(**change))) is None


@pytest.mark.parametrize("page", [wiki_page(pageprops={"disambiguation": ""}), wiki_page(categories=[{"title": "Category:German people"}]), wiki_page(pageimage=None)])
def test_nonfood_missing_or_ambiguous_page_never_searches_another_result(page):
    calls = []
    assert images._lookup("Schnitzel", transport(page=page, calls=calls)) is None
    assert len(calls) == 1


def test_redirect_and_429_do_not_retry_or_follow():
    calls = []
    def redirect(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example"})
    assert images._lookup("Schnitzel", httpx.MockTransport(redirect)) is None
    assert len(calls) == 1
    def limited(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"})
    before = time.monotonic()
    assert images._lookup("Schnitzel", httpx.MockTransport(limited)) is None
    assert images._cooldown_until >= before + 120
    assert images._lookup("Bratwurst", httpx.MockTransport(limited)) is None
    assert len(calls) == 2


def test_invalid_json_and_timeout_fall_back():
    assert images._lookup("Schnitzel", httpx.MockTransport(lambda _: httpx.Response(200, text="bad json"))) is None
    def timed_out(request):
        raise httpx.ReadTimeout("unavailable", request=request)
    assert images._lookup("Schnitzel", httpx.MockTransport(timed_out)) is None


def test_only_generic_alias_is_public_and_unknown_has_no_lookup(monkeypatch):
    assert images.public_query({"name_orig": "Anna's Jägerschnitzel mit Pilzen"}) == "Jägerschnitzel"
    assert images.public_query({"name_orig": "Teriyaki salmon for Alice"}) == "Salmon as food"
    assert images.public_query({"name_orig": "Schnitzelhaus password 123"}) is None
    monkeypatch.setattr(images, "_schedule", lambda *_: pytest.fail("unknown dish queried publicly"))
    result = images.menu_images([{"id": "one", "name_orig": "Alice's secret dish", "name_ko": "특별식"}])
    assert result["one"]["label"] == "종류 참고 그림"
    svg = base64.b64decode(result["one"]["src"].split(",", 1)[1]).decode()
    assert "Alice" not in svg and "<script" not in svg


def test_actual_crop_uses_report_mapping_without_public_request(monkeypatch):
    monkeypatch.setattr(images, "_schedule", lambda *_: pytest.fail("crop triggered public lookup"))
    data = io.BytesIO()
    Image.new("RGB", (200, 100), "red").save(data, "PNG")
    report = {"items": [{"input_name": "Schnitzel", "menu_context": {"photo_bbox": [.1, .1, .7, .9]}}]}
    result = images.menu_images([{"id": "one", "input_name": "Schnitzel"}], report, data.getvalue())["one"]
    assert result["label"] == "메뉴판 사진" and result["src"].startswith("data:image/jpeg;base64,")
    crop = Image.open(io.BytesIO(base64.b64decode(result["src"].split(",", 1)[1])))
    assert crop.size == (120, 80)
    assert images._cache == {}  # 개인 사진은 전역 캐시에 저장하지 않는다.


@pytest.mark.parametrize("box", [[0, 0, 1, 1], [0, 0, .01, .01], [.8, 0, .2, .8], [False, 0, .8, .8], [0, 0, float('nan'), .8]])
def test_invalid_crop_never_exposes_whole_menu(box):
    assert images._crop(Image.new("RGB", (100, 100)), box) is None


def test_cache_reuses_success_and_failure_with_bounded_size(monkeypatch):
    calls = []
    def lookup(query):
        calls.append(query)
        return {"src": "photo"} if query == "Schnitzel" else None
    monkeypatch.setattr(images, "_lookup", lookup)
    monkeypatch.setattr(images, "MAX_CACHE", 2)
    for query in ["Schnitzel", "Schnitzel", "Bratwurst", "Bratwurst"]:
        images._schedule(query).result(timeout=2)
    assert calls == ["Schnitzel", "Bratwurst"]
    now = time.monotonic()
    assert images._cache["Schnitzel"][0] > now + 86000
    assert now < images._cache["Bratwurst"][0] <= now + 300
    images._schedule("Currywurst").result(timeout=2)
    assert len(images._cache) == 2


def test_global_concurrency_is_three_and_duplicate_queries_share_future(monkeypatch):
    gate, started = threading.Event(), threading.Event()
    counter = {"active": 0, "maximum": 0, "calls": 0}
    lock = threading.Lock()
    def lookup(_):
        with lock:
            counter["active"] += 1
            counter["calls"] += 1
            counter["maximum"] = max(counter["maximum"], counter["active"])
            if counter["active"] == 3:
                started.set()
        gate.wait(timeout=2)
        with lock:
            counter["active"] -= 1
        return None
    monkeypatch.setattr(images, "_lookup", lookup)
    futures = [images._schedule(q) for q in ["Schnitzel", "Bratwurst", "Currywurst", "Leberkäse"]]
    assert images._schedule("Schnitzel") is futures[0]
    assert started.wait(timeout=2)
    gate.set()
    for future in futures:
        future.result(timeout=2)
    assert counter["maximum"] == 3 and counter["calls"] == 4


def test_bulk_timeout_returns_fallback_not_waiting_for_photo(monkeypatch):
    pending = Future()
    monkeypatch.setattr(images, "_schedule", lambda _: pending)
    monkeypatch.setattr(images, "BULK_WAIT_SECONDS", .001)
    result = images.menu_images([{"id": "one", "name_orig": "Schnitzel"}])
    assert result["one"]["label"] == "종류 참고 그림"
