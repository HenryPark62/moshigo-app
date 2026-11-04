"""이미지 작업의 식별·재개·안전한 내용 검증. HTTP는 모두 MockTransport다."""
import base64
from copy import deepcopy
import hashlib
import io
import json
from types import SimpleNamespace

import httpx
from PIL import Image
import pytest

from core import foodguide_images as images
from core.foodguide_client import Client as HTTPClient, Config
from core.generated_menu_images import descriptor, _hash


ITEM = {"id": "dish-1", "profile": {"status": "known", "name": "스테이크", "original_name": "Steak",
                                    "main_ingredients": ["소고기"], "cooking_methods": ["굽기"]}}
ID = "a" * 32


@pytest.fixture
def service(monkeypatch):
    state = SimpleNamespace(now=100.0, calls=[], handler=None)
    config = Config("https://food.example", "private-api-key")
    monkeypatch.setattr(images.Config, "from_env", lambda: config)
    monkeypatch.setattr(images.time, "monotonic", lambda: state.now)
    def dispatch(request):
        state.calls.append(request)
        assert request.headers["X-API-Key"] == "private-api-key"
        assert request.headers["ngrok-skip-browser-warning"] == "1"
        assert request.url.host == "food.example"
        assert all(value <= 2 for value in request.extensions["timeout"].values())
        return state.handler(request)
    monkeypatch.setattr(images, "Client", lambda conf: HTTPClient(conf, transport=httpx.MockTransport(dispatch), clock=lambda: state.now,
                                                                 sleep=lambda _: pytest.fail("image polling must not sleep")))
    return state


def accepted(item=ITEM, image_id=ID, status="queued"):
    return {"images": [{"image_id": image_id, "status": status, "descriptor_hash": _hash(descriptor(item))}]}


def result(item=ITEM):
    output = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(output, format="PNG")
    data = output.getvalue()
    return {"schema_version": "food-image-v1", "descriptor_hash": _hash(descriptor(item)), "mime_type": "image/png",
            "image_base64": base64.b64encode(data).decode(), "sha256": hashlib.sha256(data).hexdigest(), "model": "image-model"}


def completed(item=ITEM, image_id=ID):
    return {"image_id": image_id, "status": "completed", "result": result(item)}


def test_submit_poll_complete_cache_and_authenticated_bounded_paths(service):
    service.handler = lambda request: httpx.Response(202, json=accepted()) if request.method == "POST" else httpx.Response(200, json=completed())
    session = {"code": "owner"}
    assert images.ensure_images([ITEM], session)[ITEM["id"]]["status"] == "pending"
    assert json.loads(service.calls[0].content) == {"dishes": [descriptor(ITEM)]}
    images.ensure_images([ITEM], session)
    assert len(service.calls) == 1
    service.now += 2
    image = images.ensure_images([ITEM], session)[ITEM["id"]]
    assert image["status"] == "completed" and image["photo"]["src"].startswith("data:image/png;base64,")
    assert image["photo"]["label"] == "AI 생성 이미지" and image["photo"]["source_url"] == ""
    service.now += 1000
    assert images.ensure_images([ITEM], session)[ITEM["id"]] == image
    assert [r.url.path for r in service.calls] == ["/v1/food-images", f"/v1/food-images/{ID}"]
    assert "private-api-key" not in json.dumps(session)


def test_two_descriptors_match_by_hash_not_response_order(service):
    second = deepcopy(ITEM)
    second.update(id="dish-2")
    second["profile"]["name"] = "밥"
    second_id = "b" * 32
    def handle(request):
        if request.method == "POST":
            return httpx.Response(202, json={"images": [accepted(second, second_id)["images"][0], accepted()["images"][0]]})
        return httpx.Response(200, json=completed(second, second_id) if request.url.path.endswith(second_id) else completed())
    service.handler = handle
    session = {}
    images.ensure_images([ITEM, second], session)
    service.now += 2
    output = images.ensure_images([ITEM, second], session)
    assert output["dish-1"]["photo"]["title"].startswith("스테이크")
    assert output["dish-2"]["photo"]["title"].startswith("밥")
    assert len(service.calls) == 3


def test_repeated_descriptor_is_submitted_once_for_two_local_items(service):
    second = {**ITEM, "id": "same-food-second-id"}
    service.handler = lambda request: httpx.Response(202, json=accepted())
    output = images.ensure_images([ITEM, second], {})
    assert all(row["status"] == "pending" for row in output.values())
    assert len(json.loads(service.calls[0].content)["dishes"]) == 1


@pytest.mark.parametrize("stage", ["submit", "poll"])
def test_terminal_failure_is_safe_and_never_automatically_retried(service, stage):
    def handle(request):
        if request.method == "POST":
            return httpx.Response(202, json=accepted(status="failed" if stage == "submit" else "queued"))
        return httpx.Response(200, json={"image_id": ID, "status": "failed", "error": {"code": "failed", "message": "secret provider failure"}})
    service.handler = handle
    session = {}
    images.ensure_images([ITEM], session)
    service.now += 2
    output = images.ensure_images([ITEM], session)
    assert output[ITEM["id"]] == {"status": "failed", "photo": None, "message": images.FAILED}
    count = len(service.calls)
    service.now += 30
    images.ensure_images([ITEM], session)
    assert len(service.calls) == count
    assert "secret" not in json.dumps(session)


def test_unknown_post_loss_retries_idempotent_request_after_backoff(service):
    def handle(request):
        if len(service.calls) == 1:
            raise httpx.ReadTimeout("provider secret")
        return httpx.Response(202, json=accepted())
    service.handler = handle
    session = {}
    assert images.ensure_images([ITEM], session)[ITEM["id"]]["status"] == "pending"
    service.now += 4
    images.ensure_images([ITEM], session)
    assert len(service.calls) == 1
    service.now += 1
    images.ensure_images([ITEM], session)
    assert len(service.calls) == 2 and service.calls[0].content == service.calls[1].content
    assert "provider secret" not in json.dumps(session)


def test_rate_limit_applies_to_new_descriptors_and_honors_retry_after(service):
    service.handler = lambda request: httpx.Response(429, headers={"Retry-After": "20"})
    session = {}
    images.ensure_images([ITEM], session)
    second = deepcopy(ITEM)
    second["profile"]["name"] = "다른 요리"
    service.now += 19
    images.ensure_images([second], session)
    assert len(service.calls) == 1
    service.now += 1
    images.ensure_images([second], session)
    assert len(service.calls) == 2


def test_running_job_times_out_after_ten_minutes_without_sleep(service):
    service.handler = lambda request: httpx.Response(202, json=accepted())
    session = {}
    images.ensure_images([ITEM], session)
    service.now += 600
    assert images.ensure_images([ITEM], session)[ITEM["id"]]["status"] == "failed"
    assert len(service.calls) == 1


@pytest.mark.parametrize("mutation", ["id", "descriptor", "sha", "mime", "base64", "not_png", "huge", "schema", "png_structure"])
def test_malformed_completion_never_becomes_an_image(service, mutation):
    payload = completed()
    data = payload["result"]
    if mutation == "id": payload["image_id"] = "b" * 32
    elif mutation == "descriptor": data["descriptor_hash"] = "f" * 64
    elif mutation == "sha": data["sha256"] = "f" * 64
    elif mutation == "mime": data["mime_type"] = "image/svg+xml"
    elif mutation == "base64": data["image_base64"] = "not-valid-base64!"
    elif mutation == "schema": data["schema_version"] = "other"
    elif mutation == "huge": data["image_base64"] = "A" * (4 * ((images.MAX_IMAGE_BYTES + 2) // 3) + 4)
    else:
        raw = b"not PNG" if mutation == "not_png" else b"\x89PNG\r\n\x1a\ninvalid chunks"
        data["image_base64"] = base64.b64encode(raw).decode()
        data["sha256"] = hashlib.sha256(raw).hexdigest()
    service.handler = lambda request: httpx.Response(202, json=accepted()) if request.method == "POST" else httpx.Response(200, json=payload)
    session = {}
    images.ensure_images([ITEM], session)
    service.now += 2
    output = images.ensure_images([ITEM], session)[ITEM["id"]]
    assert output["status"] == "failed" and output["photo"] is None


@pytest.mark.parametrize("mutation", ["descriptor", "id", "missing", "status"])
def test_invalid_acceptance_does_not_follow_arbitrary_urls(service, mutation):
    payload = accepted()
    row = payload["images"][0]
    row["status_url"] = "https://attacker.invalid/image"
    if mutation == "descriptor": row["descriptor_hash"] = "0" * 64
    elif mutation == "id": row["image_id"] = "../../leak"
    elif mutation == "missing": payload["images"] = []
    else: row["status"] = "unrecognized"
    service.handler = lambda request: httpx.Response(202, json=payload)
    session = {}
    assert images.ensure_images([ITEM], session)[ITEM["id"]]["status"] == "failed"
    service.now += 5
    images.ensure_images([ITEM], session)
    assert len(service.calls) == 1


def test_scope_descriptor_changes_and_cache_limit_prevent_old_attachment(service, monkeypatch):
    service.handler = lambda request: httpx.Response(202, json={"images": [
        {"image_id": ID, "status": "queued", "descriptor_hash": _hash(d)} for d in json.loads(request.content)["dishes"]]})
    monkeypatch.setattr(images, "CACHE_LIMIT", 2)
    session = {"code": "first"}
    images.ensure_images([ITEM], session)
    session["code"] = "second"
    images.ensure_images([ITEM], session)
    changed = deepcopy(ITEM)
    changed["profile"]["name"] = "새 음식"
    images.ensure_images([changed], session)
    assert len(service.calls) == 3 and len(session[images.CACHE_KEY]) == 2
    monkeypatch.setattr(images.Config, "from_env", lambda: Config("https://food.example", "new-key"))
    # transport도 새 자격 증명을 확인하도록 교체한다.
    monkeypatch.setattr(images, "Client", lambda conf: HTTPClient(conf, transport=httpx.MockTransport(lambda request: httpx.Response(202, json=accepted())), clock=lambda: service.now))
    assert images.ensure_images([ITEM], session)[ITEM["id"]]["status"] == "pending"
    assert len(session[images.CACHE_KEY]) == 2


def test_owner_switch_during_response_does_not_return_old_photo(service):
    session = {"code": "first"}
    def handle(request):
        if request.method == "POST":
            return httpx.Response(202, json=accepted())
        session.clear()
        session["code"] = "second"
        return httpx.Response(200, json=completed())
    service.handler = handle
    images.ensure_images([ITEM], session)
    service.now += 2
    assert images.ensure_images([ITEM], session)[ITEM["id"]]["photo"] is None
    assert session == {"code": "second"}


@pytest.mark.parametrize("items", [[], [ITEM, ITEM], [ITEM, ITEM, ITEM], [None]])
def test_input_cardinality_and_ids_rejected_without_request(service, items):
    with pytest.raises(ValueError):
        images.ensure_images(items, {})
    assert not service.calls


def test_explicit_retry_preserves_nonce_after_lost_post_and_never_auto_retries_failed(service):
    posted = []
    def handle(request):
        if request.method == "GET":
            return httpx.Response(200, json=completed())
        payload = json.loads(request.content)
        posted.append(payload)
        if len(posted) == 1:
            assert "retry_token" not in payload
            return httpx.Response(202, json=accepted(status="failed"))
        assert len(payload["retry_token"]) == 32
        if len(posted) == 2:
            raise httpx.ReadTimeout("lost retry acknowledgement")
        return httpx.Response(202, json=accepted())
    service.handler = handle
    session = {}
    assert images.ensure_images([ITEM], session)[ITEM["id"]]["status"] == "failed"
    images.ensure_images([ITEM], session)
    assert len(posted) == 1
    assert images.retry_images([ITEM], session)[ITEM["id"]]["status"] == "pending"
    images.retry_images([ITEM], session)  # 이미 진행 중이면 토큰을 바꾸지 않는다.
    assert len(posted) == 2
    service.now += 5
    images.ensure_images([ITEM], session)
    assert posted[1] == posted[2]
    service.now += 2
    assert images.ensure_images([ITEM], session)[ITEM["id"]]["status"] == "completed"
    images.retry_images([ITEM], session)
    assert len(posted) == 3


def test_retry_resubmits_only_failed_item_not_completed_partner(service):
    second = deepcopy(ITEM)
    second["id"] = "dish-2"
    second["profile"]["name"] = "밥"
    second_id = "b" * 32
    posted = []
    def handle(request):
        if request.method == "GET":
            return httpx.Response(200, json=completed())
        payload = json.loads(request.content)
        posted.append(payload)
        if len(posted) == 1:
            return httpx.Response(202, json={"images": [accepted()["images"][0], accepted(second, second_id, "failed")["images"][0]]})
        return httpx.Response(202, json=accepted(second, second_id, "failed"))
    service.handler = handle
    session = {}
    images.ensure_images([ITEM, second], session)
    service.now += 2
    states = images.ensure_images([ITEM, second], session)
    assert states[ITEM["id"]]["status"] == "completed" and states[second["id"]]["status"] == "failed"
    images.retry_images([ITEM, second], session)
    assert posted[1]["dishes"] == [descriptor(second)]
    first_token = posted[1]["retry_token"]
    images.ensure_images([ITEM, second], session)
    assert len(posted) == 2
    images.retry_images([ITEM, second], session)
    assert posted[2]["retry_token"] != first_token
    assert posted[2]["dishes"] == [descriptor(second)]
