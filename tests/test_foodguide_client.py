"""Food Guide HTTP 경계와 재개 계약. 실제 서버와 모델은 호출하지 않는다."""
import json
from email.parser import BytesParser
from email.policy import default

import httpx
import pytest

from core.foodguide_client import Client, Config, FoodGuideError


JOB = "a" * 32
OTHER = "b" * 32


class Clock:
    def __init__(self):
        self.now = 0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def report(name="수프"):
    return {"schema_version": "menu-guide-v1", "items": [
        {"input_name": name, "status": "ok", "profile": None, "matches": [],
         "preferences": [{"name": "나", "score": None, "eligible": True}], "text": "비교 기준 없음"}],
        "result_text": "비교 기준 없음", "group": {}, "warnings": []}


def accepted(job=JOB, **extra):
    return httpx.Response(202, json={"job_id": job, "status": "queued", **extra})


def complete(value=None, job=JOB):
    return httpx.Response(200, json={"job_id": job, "status": "completed", "result": value or report()})


def client(handler, clock=None, **config):
    clock = clock or Clock()
    return Client(Config("https://food.example", "server-secret", **config),
                  transport=httpx.MockTransport(handler), sleep=clock.sleep, clock=clock)


def run(c, state, **kwargs):
    return c.run_text(["수프"], [{"name": "나"}], state=state, operation_key="scan", **kwargs)


def test_submit_auth_saved_before_poll_and_null_result_reused():
    calls, state = [], {}

    def handler(request):
        calls.append(request)
        assert request.headers["X-API-Key"] == "server-secret"
        assert request.headers["ngrok-skip-browser-warning"] == "1"
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["menus"] == ["수프"] and body["preferences"][0]["liked_food_ids"] == []
            return accepted(status_url="https://attacker.example/steal")
        assert state["scan"]["job_id"] == JOB
        assert str(request.url) == f"https://food.example/v1/jobs/{JOB}"
        return complete()

    with client(handler) as c:
        result = run(c, state)
        assert result["items"][0]["preferences"][0]["score"] is None
        assert run(c, state) == result
    assert [r.method for r in calls] == ["POST", "GET"]
    assert "server-secret" not in json.dumps(state)


def test_timeout_resumes_same_job_without_post():
    calls, state, clock = [], {}, Clock()
    done = False

    def handler(request):
        calls.append(request.method)
        if request.method == "POST":
            return accepted()
        return complete() if done else httpx.Response(200, json={"job_id": JOB, "status": "running"})

    with client(handler, clock) as c:
        with pytest.raises(FoodGuideError) as error:
            run(c, state, max_wait=3)
        assert error.value.code == "wait_timeout" and error.value.job_id == JOB
        done = True
        assert run(c, state)["items"]
    assert calls.count("POST") == 1


def test_changed_request_or_credential_scope_creates_new_job():
    posts, state = [], {}

    def handler(request):
        if request.method == "POST":
            posts.append(json.loads(request.content))
            return accepted()
        return complete(report(posts[-1]["menus"][0]))

    with client(handler) as c:
        run(c, state)
        c.run_text(["밥"], [], state=state, operation_key="scan")
    with Client(Config("https://food.example", "rotated-secret"), transport=httpx.MockTransport(handler)) as c:
        c.run_text(["밥"], [], state=state, operation_key="scan")
    assert len(posts) == 3


def test_failed_http_200_is_safe_and_cached():
    count, state = [], {}

    def handler(request):
        count.append(request.method)
        if request.method == "POST":
            return accepted()
        return httpx.Response(200, json={"job_id": JOB, "status": "failed", "error": {
            "code": "daily_budget_exceeded", "message": "traceback server-secret https://internal.example"}})

    with client(handler) as c:
        for _ in range(2):
            with pytest.raises(FoodGuideError) as error:
                run(c, state)
            assert error.value.code == "daily_budget_exceeded" and error.value.job_id == JOB
            assert "server-secret" not in str(error.value) and "traceback" not in str(error.value)
    assert count == ["POST", "GET"]


@pytest.mark.parametrize("response", [
    {"job_id": "../steal", "status": "queued"},
    {"job_id": JOB, "status": "completed"},
    [],
])
def test_invalid_submission_cannot_be_resubmitted(response):
    calls, state = [], {}

    def handler(request):
        calls.append(request)
        return httpx.Response(202, json=response)

    with client(handler) as c:
        with pytest.raises(FoodGuideError, match="응답"):
            run(c, state)
        with pytest.raises(FoodGuideError) as error:
            run(c, state)
        assert error.value.code == "submission_unknown"
    assert len(calls) == 1


@pytest.mark.parametrize("body", [
    {"job_id": OTHER, "status": "running"},
    {"job_id": JOB, "status": "invented"},
    {"job_id": JOB, "status": "completed"},
    {"job_id": JOB, "status": "completed", "result": {"items": []}},
    {"job_id": JOB, "status": "failed", "error": "traceback"},
])
def test_malformed_poll_preserves_accepted_job(body):
    state = {}
    with client(lambda r: accepted() if r.method == "POST" else httpx.Response(200, json=body)) as c:
        with pytest.raises(FoodGuideError) as error:
            run(c, state)
    assert error.value.code == "invalid_response"
    assert state["scan"]["job_id"] == JOB


def test_redirect_never_followed_or_reposted():
    requests, state = [], {}

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(307, headers={"Location": "https://attacker.example"})

    with client(handler) as c:
        with pytest.raises(FoodGuideError):
            run(c, state)
        with pytest.raises(FoodGuideError) as error:
            run(c, state)
        assert error.value.code == "submission_unknown"
    assert requests == ["https://food.example/v1/jobs/text"]


def test_poll_429_and_transport_retry_respect_delay_and_normalize_progress():
    clock, state, progress, gets = Clock(), {}, [], []

    def handler(request):
        if request.method == "POST":
            return accepted()
        gets.append(request)
        if len(gets) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"}, text="private diagnostic")
        if len(gets) == 2:
            raise httpx.ConnectError("secret endpoint", request=request)
        if len(gets) == 3:
            return httpx.Response(200, json={"job_id": JOB, "status": "running", "progress": {
                "stage": "comparison", "percent": 150, "message": "server-secret"}})
        return complete()

    with client(handler, clock) as c:
        run(c, state, on_progress=progress.append)
    assert clock.sleeps == [7, 2.5, 3.125]
    assert progress[0]["percent"] == 100 and progress[0]["stage"] == "comparison"
    assert "server-secret" not in json.dumps(progress)


def test_submit_transport_uncertainty_never_reposts_until_cleared():
    requests, state = [], {}

    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout("server-secret", request=request)

    with client(handler) as c:
        for _ in range(2):
            with pytest.raises(FoodGuideError) as error:
                run(c, state)
            assert error.value.code == "submission_unknown"
        assert len(requests) == 1
        state.clear()
        with pytest.raises(FoodGuideError):
            run(c, state)
        assert len(requests) == 2


def test_submit_429_may_be_explicitly_retried():
    requests, state = [], {}

    def handler(request):
        requests.append(request.method)
        if len(requests) == 1:
            return httpx.Response(429, headers={"Retry-After": "9"})
        return accepted() if request.method == "POST" else complete()

    with client(handler) as c:
        with pytest.raises(FoodGuideError) as error:
            run(c, state)
        assert error.value.retry_after == 9
        assert len(requests) == 1
        run(c, state)
    assert requests == ["POST", "POST", "GET"]


@pytest.mark.parametrize("url", ["", "http://food.example", "https://user:pass@food.example", "https://food.example?key=x", "https://food.example/#x", "https://food.example/api", "ftp://localhost", "https://food.example:bad"])
def test_config_rejects_unsafe_urls(url):
    with pytest.raises(FoodGuideError) as error:
        Config(url, "secret")
    assert error.value.code == "configuration_error" and "secret" not in str(error.value)


def test_config_from_env_and_local_http(monkeypatch):
    monkeypatch.setenv("FOODGUIDE_API_URL", "http://127.0.0.1:8000/")
    monkeypatch.setenv("FOODGUIDE_API_KEY", "secret")
    monkeypatch.delenv("FOODGUIDE_MAX_WAIT_SECONDS", raising=False)
    cfg = Config.from_env()
    assert cfg.base_url == "http://127.0.0.1:8000" and cfg.max_wait_seconds == 600
    assert "secret" not in repr(cfg)
    monkeypatch.delenv("FOODGUIDE_API_KEY")
    with pytest.raises(FoodGuideError):
        Config.from_env()


@pytest.mark.parametrize("menus,prefs,context", [
    (["a"] * 21, [], None), ([" a", "a"], [], None), ([""], [], None),
    (["a"], [{"name": "x"}] * 7, None), (["a"], [{"name": "x"}, {"name": " x "}], None),
    (["a"], [{"name": "x", "max_chili_heat": True}], None),
    (["a"], [], {"a": {"description": "x" * 2001}}),
])
def test_request_limits_fail_before_network(menus, prefs, context):
    def handler(_):
        pytest.fail("invalid input reached network")
    with client(handler) as c:
        with pytest.raises(FoodGuideError) as error:
            c.run_text(menus, prefs, context, state={}, operation_key="scan")
    assert error.value.code == "invalid_request"


def test_response_size_bound(monkeypatch):
    monkeypatch.setattr("core.foodguide_client.MAX_RESPONSE", 30)
    with client(lambda _: httpx.Response(202, content=b"x" * 31)) as c:
        with pytest.raises(FoodGuideError) as error:
            run(c, {})
    assert error.value.code == "invalid_response"


def test_image_multipart_and_resume_without_second_upload():
    photo, calls, state, clock = b"\xff\xd8\xffimage-private-bytes", [], {}, Clock()
    done = False

    def handler(request):
        calls.append(request.method)
        if request.method == "POST":
            assert request.url.path == "/v1/jobs/image"
            content_type = request.headers["content-type"]
            assert content_type.startswith("multipart/form-data; boundary=")
            message = BytesParser(policy=default).parsebytes(
                b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + request.content)
            parts = {p.get_param("name", header="content-disposition"): p for p in message.iter_parts()}
            assert parts["image"].get_content_type() == "image/jpeg"
            assert parts["image"].get_payload(decode=True) == photo
            options = json.loads(parts["options"].get_payload(decode=True))
            assert options == {"scope": "korean", "top_k": 3, "preferences": [{"name": "나", "liked_food_ids": [],
                "avoid_ingredients": [], "max_chili_heat": None, "max_chewiness": None}]}
            return accepted()
        assert state["photo"]["job_id"] == JOB
        return complete() if done else httpx.Response(200, json={"job_id": JOB, "status": "running"})

    with client(handler, clock) as c:
        with pytest.raises(FoodGuideError) as error:
            c.run_image(photo, preferences=[{"name": "나"}], state=state, operation_key="photo", max_wait=1)
        assert error.value.code == "wait_timeout"
        done = True
        result = c.run_image(photo, preferences=[{"name": "나"}], state=state, operation_key="photo")
        assert result["items"][0]["input_name"] == "수프"
        assert c.run_image(photo, preferences=[{"name": "나"}], state=state, operation_key="photo") == result
    assert calls == ["POST", "GET", "GET"]
    assert "image-private-bytes" not in json.dumps(state)


@pytest.mark.parametrize("photo,mime", [(b"", "image/jpeg"), (b"photo", "image/heic"),
                                        ("not bytes", "image/png"), (b"x" * (15 * 1024 * 1024 + 1), "image/webp")])
def test_invalid_image_fails_before_upload(photo, mime):
    def handler(_):
        pytest.fail("invalid image reached network")
    with client(handler) as c:
        with pytest.raises(FoodGuideError) as error:
            c.run_image(photo, mime, preferences=[], state={}, operation_key="photo")
    assert error.value.code == "invalid_request"


def test_malformed_progress_ignored_and_nonstring_status_rejected():
    calls = []

    def handler(request):
        if request.method == "POST":
            return accepted()
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"job_id": JOB, "status": "running", "progress": {"stage": [], "percent": 1}})
        return httpx.Response(200, json={"job_id": JOB, "status": []})

    with client(handler) as c:
        with pytest.raises(FoodGuideError) as error:
            run(c, {})
    assert error.value.code == "invalid_response"


@pytest.mark.parametrize("failure", ["connect", "ngrok_offline"])
def test_unreachable_server_is_unavailable_not_uncertain(failure):
    """서버에 닿지 못한 제출은 '접수 불확실'이 아니라 '연결할 수 없음'이고, 다음에 다시 보낼 수 있다."""
    def handler(request):
        if failure == "connect":
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(404, text="ERR_NGROK_3200")
    state = {}
    with client(handler) as c, pytest.raises(FoodGuideError) as error:
        run(c, state)
    assert error.value.code == "unavailable"
    assert not any(entry.get("uncertain") for entry in state.values())
