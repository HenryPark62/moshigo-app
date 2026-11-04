"""추천 음식 이미지 작업을 짧게 제출·조회한다. 생성 키와 외부 URL은 다루지 않는다."""
import base64
import hashlib
import io
import re
import time
import uuid

import httpx
from PIL import Image

from .foodguide_client import Client, Config, FoodGuideError
from .generated_menu_images import GeneratedImageError, descriptor, _hash


CACHE_KEY = "fg_auto_images"
CACHE_LIMIT = 32
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_WAIT = 600
REQUEST_SECONDS = 2
POLL_SECONDS = 2
_ID = re.compile(r"[0-9a-f]{32}")
_HASH = re.compile(r"[0-9a-f]{64}")
_STATUSES = {"queued", "running", "completed", "failed"}
FAILED = "이미지를 만들지 못했어요."
WAITING = "이미지를 만들고 있어요."


def _hex(value, pattern):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _scope(config, owner):
    return _hash({"base": config.base_url, "key": hashlib.sha256(config.api_key.encode()).hexdigest(), "owner": owner})


def _failed(entry):
    entry.update(status="failed", photo=None, message=FAILED)


def _transient(entry, error):
    code = getattr(error, "code", "unavailable")
    if code not in {"unavailable", "rate_limited"}:
        _failed(entry)
        return
    attempts = min(entry.get("attempts", 0) + 1, 6)
    delay = min(30, 5 * attempts)
    retry = getattr(error, "retry_after", None)
    if isinstance(retry, (int, float)) and not isinstance(retry, bool) and retry >= 0:
        delay = max(delay, retry)
    entry.update(next_at=time.monotonic() + delay, attempts=attempts,
                 message="요청이 많아 잠시 기다리고 있어요." if code == "rate_limited" else "이미지 서버 연결을 기다리고 있어요.")


def _photo(result, digest, name):
    if not isinstance(result, dict) or result.get("schema_version") != "food-image-v1" or result.get("descriptor_hash") != digest:
        raise ValueError("invalid image result")
    encoded, checksum = result.get("image_base64"), result.get("sha256")
    if result.get("mime_type") != "image/png" or not _hex(checksum, _HASH):
        raise ValueError("invalid image format")
    model = result.get("model")
    if not isinstance(model, str) or not 0 < len(model) <= 200:
        raise ValueError("invalid model")
    if not isinstance(encoded, str) or not 0 < len(encoded) <= 4 * ((MAX_IMAGE_BYTES + 2) // 3):
        raise ValueError("image too large")
    data = base64.b64decode(encoded, validate=True)
    if not 0 < len(data) <= MAX_IMAGE_BYTES or not data.startswith(b"\x89PNG\r\n\x1a\n") or hashlib.sha256(data).hexdigest() != checksum:
        raise ValueError("invalid image content")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "PNG" or image.width * image.height > 20_000_000:
                raise ValueError("invalid image dimensions")
            image.verify()
    except (OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise ValueError("invalid PNG") from error
    return {"src": "data:image/png;base64," + base64.b64encode(data).decode(), "label": "AI 생성 이미지",
            "title": name + " · AI 생성 참고 이미지, 실제 메뉴와 다를 수 있어요", "author": "", "license": "",
            "source_url": "", "license_url": ""}


def _poll(client, entry):
    payload = client._request("GET", "/v1/food-images/" + entry["image_id"], client.clock() + REQUEST_SECONDS)
    if payload.get("image_id") != entry["image_id"] or payload.get("status") not in _STATUSES:
        raise ValueError("image job mismatch")
    if "descriptor_hash" in payload and payload["descriptor_hash"] != entry["descriptor_hash"]:
        raise ValueError("descriptor mismatch")
    if payload["status"] == "failed":
        _failed(entry)
    elif payload["status"] == "completed":
        entry.update(photo=_photo(payload.get("result"), entry["descriptor_hash"], entry["descriptor"]["name"]),
                     status="completed", message="")
    else:
        entry.update(next_at=time.monotonic() + POLL_SECONDS, attempts=0, message=WAITING)


def _submit(client, entries):
    request = {"dishes": [entry["descriptor"] for entry in entries]}
    token = entries[0].get("retry_token")
    if token:
        request["retry_token"] = token
    payload = client._request("POST", "/v1/food-images", client.clock() + REQUEST_SECONDS, request)
    rows = payload.get("images")
    if not isinstance(rows, list) or len(rows) != len(entries):
        raise ValueError("invalid image acceptance")
    expected = {entry["descriptor_hash"] for entry in entries}
    found, image_ids = {}, set()
    for row in rows:
        if not isinstance(row, dict) or not _hex(row.get("image_id"), _ID) or row.get("status") not in _STATUSES:
            raise ValueError("invalid image job")
        digest = row.get("descriptor_hash")
        if not _hex(digest, _HASH) or digest not in expected or digest in found or row["image_id"] in image_ids:
            raise ValueError("invalid image descriptor")
        found[digest] = row
        image_ids.add(row["image_id"])
    for entry in entries:
        row = found[entry["descriptor_hash"]]
        entry.update(image_id=row["image_id"], next_at=time.monotonic() + POLL_SECONDS, attempts=0)
        if row["status"] == "failed":
            _failed(entry)


def _item_ids(items):
    if not isinstance(items, (list, tuple)) or not 1 <= len(items) <= 2:
        raise ValueError("추천 이미지 메뉴는 한 번에 1~2개만 요청할 수 있어요.")
    ids = [item.get("id") if isinstance(item, dict) else None for item in items]
    if any(not isinstance(iid, str) or not iid for iid in ids) or len(set(ids)) != len(ids):
        raise ValueError("메뉴 식별자를 확인해 주세요.")
    return ids


def ensure_images(items, session):
    """1~2개 메뉴의 현재 이미지 상태를 반환한다. 호출당 제출/조회 1회씩, sleep 없음.

    반환: {item_id: {status: pending|completed|failed, photo: dict|None, message: 안전한 안내}}.
    완료/실패 결과는 캐시하며 일시 연결 오류만 다음 호출에서 재시도한다.
    """
    ids = _item_ids(items)
    output = {iid: {"status": "failed", "photo": None, "message": FAILED} for iid in ids}
    try:
        config = Config.from_env()
    except FoodGuideError:
        return output
    owner = session.get("code", "")
    scope = _scope(config, owner)
    cache = session.get(CACHE_KEY)
    if not isinstance(cache, dict):
        cache = {}
        session[CACHE_KEY] = cache
    selected = {}
    for item in items:
        try:
            description = descriptor(item)
        except (GeneratedImageError, TypeError, ValueError):
            continue
        digest = _hash(description)
        key = scope + ":" + digest
        entry = cache.pop(key, None)
        if not isinstance(entry, dict):
            entry = {"descriptor": description, "descriptor_hash": digest, "status": "pending", "photo": None,
                     "message": WAITING, "started_at": time.monotonic(), "next_at": 0, "attempts": 0}
        cache[key] = entry
        selected[item["id"]] = entry
    while len(cache) > CACHE_LIMIT:
        del cache[next(iter(cache))]
    waits = session.setdefault("fg_auto_image_wait", {})
    while len(waits) > CACHE_LIMIT:
        del waits[next(iter(waits))]

    def backoff(error):
        if getattr(error, "code", "") == "rate_limited":
            delay = getattr(error, "retry_after", None)
            waits[scope] = time.monotonic() + max(5, delay or 0)
            while len(waits) > CACHE_LIMIT:
                del waits[next(iter(waits))]

    due = []
    for entry in selected.values():
        if entry["status"] != "pending":
            continue
        if time.monotonic() - entry["started_at"] >= MAX_WAIT:
            _failed(entry)
        elif time.monotonic() >= max(entry["next_at"], waits.get(scope, 0)) and not any(old is entry for old in due):
            due.append(entry)
    if due:
        with Client(config) as client:
            new = [entry for entry in due if not entry.get("image_id")]
            batches = {}
            for entry in new:
                batches.setdefault(entry.get("retry_token", ""), []).append(entry)
            for batch in batches.values():
                if time.monotonic() < waits.get(scope, 0):
                    break
                try:
                    _submit(client, batch)
                except (FoodGuideError, httpx.HTTPError) as error:
                    backoff(error)
                    for entry in batch:
                        _transient(entry, error)
                except (ValueError, TypeError):
                    for entry in batch:
                        _failed(entry)
            for entry in due:
                if entry in new or time.monotonic() < waits.get(scope, 0):
                    continue
                try:
                    _poll(client, entry)
                except (FoodGuideError, httpx.HTTPError) as error:
                    backoff(error)
                    _transient(entry, error)
                except (ValueError, TypeError):
                    _failed(entry)
    if session.get(CACHE_KEY) is not cache or session.get("code", "") != owner:
        return output
    for iid, entry in selected.items():
        output[iid] = {"status": entry["status"], "photo": dict(entry["photo"]) if entry["photo"] else None, "message": entry["message"]}
    return output


def retry_images(items, session):
    """명시적 다시 만들기 클릭 전용. 실패 항목만 같은 클릭 토큰으로 재접수한다."""
    _item_ids(items)
    try:
        config = Config.from_env()
    except FoodGuideError:
        return ensure_images(items, session)
    cache = session.get(CACHE_KEY) or {}
    scope = _scope(config, session.get("code", ""))
    token = uuid.uuid4().hex
    for item in items:
        try:
            digest = _hash(descriptor(item))
        except (GeneratedImageError, TypeError, ValueError):
            continue
        entry = cache.get(scope + ":" + digest)
        if not isinstance(entry, dict) or entry.get("status") != "failed":
            continue
        entry.update(status="pending", photo=None, message=WAITING, started_at=time.monotonic(),
                     next_at=0, attempts=0, retry_token=token)
        entry.pop("image_id", None)
    return ensure_images(items, session)
