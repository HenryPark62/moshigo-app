"""Food Guide 서버 전용 HTTP 클라이언트. 접수한 작업은 다시 제출하지 않고 조회한다."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import ipaddress
import json
import math
import os
import re
import time
from urllib.parse import urlsplit

import httpx


MAX_RESPONSE = 8 * 1024 * 1024
JOB_ID = re.compile(r"^[0-9a-f]{32}$")
STAGES = {"queued": "분석을 기다리고 있어요", "starting": "분석을 준비하고 있어요",
          "ocr": "메뉴를 읽고 있어요", "profiles": "음식 특징을 확인하고 있어요",
          "embeddings": "닮은 음식을 비교하고 있어요", "comparison": "가족 입맛을 비교하고 있어요",
          "completed": "분석을 마쳤어요", "failed": "분석을 완료하지 못했어요"}
ERRORS = {
    "configuration_error": "Food Guide 서버 연결 설정을 확인해 주세요.",
    "invalid_request": "메뉴와 가족 입력의 형식 및 개수를 확인해 주세요.",
    "unauthorized": "Food Guide 서버 인증 설정을 확인해 주세요.",
    "not_found": "분석 작업을 찾을 수 없어요. 작업이 만료되었을 수 있어요.",
    "rate_limited": "분석 요청이 많아요. 잠시 후 다시 확인해 주세요.",
    "queue_full": "분석 대기열이 가득 찼어요. 잠시 후 다시 시도해 주세요.",
    "validation_error": "분석 요청의 메뉴와 가족 정보를 확인해 주세요.",
    "unavailable": "분석 서버에 연결할 수 없어요. 잠시 후 다시 확인해 주세요.",
    "not_configured": "Food Guide 분석 서버 설정을 확인해 주세요.",
    "daily_budget_exceeded": "오늘의 분석 서비스 호출 한도에 도달했어요.",
    "budget_unavailable": "분석 서비스 사용량 설정을 확인할 수 없어요.",
    "interrupted": "서버 재시작으로 분석이 중단되었어요.",
    "analysis_failed": "음식 분석을 완료하지 못했어요.",
    "invalid_response": "분석 서버의 응답을 확인할 수 없어요.",
    "wait_timeout": "분석이 아직 진행 중이에요. 다시 확인하면 같은 작업을 이어서 조회해요.",
    "submission_unknown": "접수 여부를 확인할 수 없어요. 중복 제출을 막기 위해 자동으로 다시 보내지 않아요.",
}


class FoodGuideError(Exception):
    def __init__(self, code, message, retry_after=None, job_id=None):
        super().__init__(message)
        self.code, self.message = code, message
        self.retry_after, self.job_id = retry_after, job_id


def _error(code, **kwargs):
    return FoodGuideError(code, ERRORS[code], **kwargs)


@dataclass(frozen=True)
class Config:
    base_url: str
    api_key: str = field(repr=False)
    max_wait_seconds: float = 600

    def __post_init__(self):
        try:
            parsed = urlsplit(self.base_url)
            host = parsed.hostname
            local = host == "localhost"
            if host and not local:
                try:
                    local = ipaddress.ip_address(host).is_loopback
                except ValueError:
                    pass
            valid = (parsed.scheme == "https" or parsed.scheme == "http" and local)
            valid = valid and bool(host) and not parsed.username and not parsed.password
            valid = valid and not parsed.query and not parsed.fragment and not parsed.path.strip("/")
            valid = valid and parsed.port != 0 and not any(c.isspace() for c in self.base_url)
            valid = valid and bool(self.api_key.strip()) and all(32 <= ord(c) < 127 for c in self.api_key)
            valid = valid and math.isfinite(float(self.max_wait_seconds)) and float(self.max_wait_seconds) > 0
        except (TypeError, ValueError, AttributeError):
            valid = False
        if not valid:
            raise _error("configuration_error")
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        object.__setattr__(self, "max_wait_seconds", float(self.max_wait_seconds))

    @classmethod
    def from_env(cls):
        try:
            return cls(os.environ.get("FOODGUIDE_API_URL", "").strip(),
                       os.environ.get("FOODGUIDE_API_KEY", "").strip(),
                       float(os.environ.get("FOODGUIDE_MAX_WAIT_SECONDS", "600")))
        except (TypeError, ValueError):
            raise _error("configuration_error") from None


def _text(value, limit, empty=False):
    return isinstance(value, str) and len(value) <= limit and (empty or bool(value.strip()))


def _payload(menus, preferences, menu_context):
    if not isinstance(menus, list) or not 1 <= len(menus) <= 20 or not all(_text(n, 200) for n in menus):
        raise _error("invalid_request")
    names = [n.strip() for n in menus]
    if len(set(names)) != len(names) or not isinstance(preferences, list) or len(preferences) > 6:
        raise _error("invalid_request")
    people = []
    for p in preferences:
        if not isinstance(p, dict) or set(p) - {"name", "liked_food_ids", "avoid_ingredients", "max_chili_heat", "max_chewiness"} or not _text(p.get("name"), 100):
            raise _error("invalid_request")
        person = {"name": p["name"].strip()}
        for key in ("liked_food_ids", "avoid_ingredients"):
            values = p.get(key, [])
            if not isinstance(values, list) or len(values) > 50 or not all(_text(v, 200) for v in values):
                raise _error("invalid_request")
            person[key] = list(values)
        for key in ("max_chili_heat", "max_chewiness"):
            value = p.get(key)
            if value is not None and (type(value) is not int or not 0 <= value <= 5):
                raise _error("invalid_request")
            person[key] = value
        people.append(person)
    if len({p["name"] for p in people}) != len(people):
        raise _error("invalid_request")
    context = {} if menu_context is None else menu_context
    if not isinstance(context, dict) or len(context) > 20:
        raise _error("invalid_request")
    for name, metadata in context.items():
        if name not in names or not isinstance(metadata, dict) or set(metadata) - {"original_name", "korean_name", "pronunciation", "description", "price", "confidence"}:
            raise _error("invalid_request")
        for key, value in metadata.items():
            if key == "confidence":
                valid = value is None or type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
            elif key == "price" and value is None:
                valid = True
            else:
                valid = _text(value, 2000 if key == "description" else 100 if key == "price" else 200, empty=True)
            if not valid:
                raise _error("invalid_request")
    return {"menus": names, "preferences": people, "menu_context": context, "scope": "korean", "top_k": 3}


def _score(value, nullable=False):
    return (nullable and value is None) or (type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100)


def _report(value, names=None):
    if not isinstance(value, dict) or value.get("schema_version") != "menu-guide-v1" or not isinstance(value.get("items"), list) or not isinstance(value.get("result_text"), str):
        raise _error("invalid_response")
    if (names is not None and len(value["items"]) != len(names)) or not 1 <= len(value["items"]) <= 20:
        raise _error("invalid_response")
    seen = []
    for item in value["items"]:
        if not isinstance(item, dict) or not _text(item.get("input_name"), 200) or (names is not None and item["input_name"] not in names) or item.get("status") not in ("ok", "unknown", "ambiguous", "error", "insufficient"):
            raise _error("invalid_response")
        seen.append(item["input_name"])
        if item.get("profile") is not None and not isinstance(item["profile"], dict):
            raise _error("invalid_response")
        for key in ("matches", "preferences"):
            rows = item.get(key)
            if not isinstance(rows, list) or len(rows) > (10 if key == "matches" else 6):
                raise _error("invalid_response")
            for row in rows:
                if not isinstance(row, dict) or not _text(row.get("name"), 1000) or "score" not in row or not _score(row["score"], nullable=key == "preferences"):
                    raise _error("invalid_response")
                if key == "preferences" and type(row.get("eligible")) is not bool:
                    raise _error("invalid_response")
                if key == "matches" and not _text(row.get("id"), 200):
                    raise _error("invalid_response")
    if len(set(seen)) != len(seen) or not isinstance(value.get("group", {}), dict) or not isinstance(value.get("warnings", []), list):
        raise _error("invalid_response")
    return value


def _retry_after(value):
    try:
        seconds = float(value)
        return max(0, seconds) if math.isfinite(seconds) else None
    except (ValueError, TypeError):
        try:
            dt = parsedate_to_datetime(value)
            return max(0, (dt - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


class Client:
    def __init__(self, config, transport=None, sleep=time.sleep, clock=time.monotonic):
        self.config, self.sleep, self.clock = config, sleep, clock
        self.http = httpx.Client(transport=transport, follow_redirects=False, trust_env=False,
                                 headers={"X-API-Key": config.api_key, "ngrok-skip-browser-warning": "1"})

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.http.close()

    def _request(self, method, path, deadline, payload=None, image=None):
        if image is None:
            kwargs = {"json": payload} if payload is not None else {}
        else:
            image_bytes, media_type = image
            options = {key: payload[key] for key in ("preferences", "scope", "top_k")}
            extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[media_type]
            kwargs = {"files": {"image": (f"menu.{extension}", image_bytes, media_type)},
                      "data": {"options": json.dumps(options, ensure_ascii=False)}}
        with self.http.stream(method, self.config.base_url + path, **kwargs,
                              timeout=max(.01, min(30, deadline - self.clock()))) as response:
            retry = _retry_after(response.headers.get("Retry-After"))
            if response.status_code >= 300 or response.status_code < 200:
                codes = {401: "unauthorized", 403: "unauthorized", 404: "not_found", 422: "validation_error", 429: "rate_limited"}
                raise _error(codes.get(response.status_code, "unavailable"), retry_after=retry)
            if response.status_code != (202 if method == "POST" else 200):
                raise _error("invalid_response")
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE:
                    raise _error("invalid_response")
                chunks.append(chunk)
            try:
                data = json.loads(b"".join(chunks), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            except (ValueError, UnicodeError):
                raise _error("invalid_response") from None
            if not isinstance(data, dict):
                raise _error("invalid_response")
            return data

    def _progress(self, job, entry, callback):
        raw = job.get("progress")
        if not isinstance(raw, dict):
            return
        stage = raw.get("stage")
        percent = raw.get("percent")
        if not isinstance(stage, str) or stage not in STAGES or type(percent) not in (int, float) or not math.isfinite(percent):
            return
        progress = {"stage": stage, "percent": max(0, min(100, int(percent))), "message": STAGES[stage]}
        entry["progress"] = progress
        if callback:
            callback(dict(progress))

    def run_text(self, menus, preferences, menu_context=None, *, state, operation_key, on_progress=None, max_wait=None):
        payload = _payload(menus, preferences, menu_context)
        return self._run(payload, state=state, operation_key=operation_key, on_progress=on_progress,
                         max_wait=max_wait, names=payload["menus"])

    def run_image(self, image_bytes, media_type="image/jpeg", *, preferences, state, operation_key, on_progress=None, max_wait=None):
        if not isinstance(image_bytes, bytes) or not 0 < len(image_bytes) <= 15 * 1024 * 1024 or media_type not in ("image/jpeg", "image/png", "image/webp"):
            raise _error("invalid_request")
        payload = _payload(["image"], preferences, None)
        payload.pop("menus")
        payload.pop("menu_context")
        payload.update(image_sha256=hashlib.sha256(image_bytes).hexdigest(), media_type=media_type)
        return self._run(payload, state=state, operation_key=operation_key, on_progress=on_progress,
                         max_wait=max_wait, image=(image_bytes, media_type))

    def _run(self, payload, *, state, operation_key, on_progress=None, max_wait=None, names=None, image=None):
        try:
            wait = self.config.max_wait_seconds if max_wait is None else float(max_wait)
            if not math.isfinite(wait) or wait <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            raise _error("invalid_request") from None
        if not isinstance(state, dict) or not _text(operation_key, 1000):
            raise _error("invalid_request")
        scope = hashlib.sha256(self.config.api_key.encode()).hexdigest()
        fingerprint = hashlib.sha256(json.dumps([self.config.base_url, scope, payload], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        entry = state.get(operation_key)
        if not isinstance(entry, dict) or entry.get("fingerprint") != fingerprint:
            entry = state[operation_key] = {"fingerprint": fingerprint}
        if "result" in entry:
            return _report(entry["result"], names)
        if entry.get("uncertain"):
            raise _error("submission_unknown")
        if entry.get("failed"):
            raise _error(entry["failed"] if entry["failed"] in ERRORS else "analysis_failed", job_id=entry.get("job_id"))
        deadline = self.clock() + wait
        job_id = entry.get("job_id")
        if job_id is not None and (not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id)):
            raise _error("invalid_response")
        if job_id is None:
            # 먼저 표시한다. 접수 응답이 유실되면 같은 입력을 자동 재전송하지 않는다.
            entry["uncertain"] = True
            try:
                accepted = self._request("POST", "/v1/jobs/image" if image is not None else "/v1/jobs/text", deadline, payload, image)
            except httpx.HTTPError:
                raise _error("submission_unknown") from None
            except FoodGuideError as error:
                if error.code in {"rate_limited", "unauthorized", "validation_error", "not_found"}:
                    entry.pop("uncertain", None)
                raise
            job_id = accepted.get("job_id")
            if accepted.get("status") != "queued" or not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
                raise _error("invalid_response")
            entry["job_id"] = job_id
            entry.pop("uncertain", None)
        delay = 2.0
        while True:
            if self.clock() >= deadline:
                raise _error("wait_timeout", job_id=job_id)
            pause = delay
            try:
                job = self._request("GET", f"/v1/jobs/{job_id}", deadline)
            except httpx.HTTPError:
                job = None
            except FoodGuideError as error:
                if error.code not in {"rate_limited", "unavailable"}:
                    error.job_id = job_id
                    raise
                pause = max(delay, error.retry_after or 0)
                job = None
            if job is not None:
                if job.get("job_id") != job_id or job.get("status") not in ("queued", "running", "completed", "failed"):
                    raise _error("invalid_response", job_id=job_id)
                self._progress(job, entry, on_progress)
                if job["status"] == "completed":
                    try:
                        result = _report(job.get("result"), names)
                    except FoodGuideError as error:
                        error.job_id = job_id
                        raise
                    entry["result"] = result
                    return result
                if job["status"] == "failed":
                    raw_error = job.get("error")
                    if not isinstance(raw_error, dict) or not isinstance(raw_error.get("code"), str):
                        raise _error("invalid_response", job_id=job_id)
                    code = raw_error["code"] if raw_error["code"] in ERRORS else "analysis_failed"
                    entry["failed"] = code
                    raise _error(code, job_id=job_id)
            remaining = deadline - self.clock()
            if remaining <= 0 or pause >= remaining:
                raise _error("wait_timeout", job_id=job_id)
            self.sleep(pause)
            delay = min(5, delay * 1.25)
