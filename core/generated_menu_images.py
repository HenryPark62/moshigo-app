"""승인된 소수 메뉴의 생성 이미지를 저장하고 읽는다. import/조회는 API를 호출하지 않는다."""
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata

from PIL import Image


ASSET_DIR = Path(__file__).resolve().parent / "data" / "generated-menu-images"
PROMPT_VERSION = "foodguide-stage3-v1"
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
HEX = re.compile(r"^[0-9a-f]{64}$")


class GeneratedImageError(ValueError):
    """로그에 공급자 응답·키·원문 예외를 남기지 않는 로컬 오류."""


def _text(value, maximum=200, empty=False):
    if not isinstance(value, str):
        raise GeneratedImageError("음식 설명 형식이 올바르지 않습니다.")
    value = " ".join(unicodedata.normalize("NFC", value).split())
    if len(value) > maximum or (not empty and not value):
        raise GeneratedImageError("음식 설명 길이를 확인해 주세요.")
    return value


def descriptor(item):
    """실제 stage3 prompt에 들어가는 네 필드만 정규화한다."""
    profile = item.get("profile") if isinstance(item, dict) else None
    if not isinstance(profile, dict) or profile.get("status", "known") != "known":
        raise GeneratedImageError("확인된 음식 프로필이 필요합니다.")
    result = {"name": _text(profile.get("name")), "original_name": _text(profile.get("original_name", ""), empty=True)}
    for dest, source in (("ingredients", "main_ingredients"), ("cooking_methods", "cooking_methods")):
        values = profile.get(source, [])
        if not isinstance(values, list) or len(values) > 50:
            raise GeneratedImageError("음식 재료·조리법 형식을 확인해 주세요.")
        result[dest] = [_text(value) for value in values]
    return result


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _generation_key(digest, model):
    return _hash({"descriptor_hash": digest, "model": model, "prompt_version": PROMPT_VERSION,
                  "quality": "low", "size": "1024x1024", "output_format": "png"})


def _date():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_manifest(root):
    path = root / "manifest.json"
    if not path.exists():
        return {"schema_version": 1, "entries": {}}
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise GeneratedImageError("이미지 기록을 확인할 수 없습니다.")
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        raise GeneratedImageError("이미지 기록을 읽을 수 없습니다.") from None
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("entries"), dict) or len(data["entries"]) > 1000:
        raise GeneratedImageError("이미지 기록 형식이 올바르지 않습니다.")
    return data


def _atomic(path, data):
    fd, temporary = tempfile.mkstemp(prefix=".image-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _save_manifest(root, manifest):
    data = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    if len(data) > MAX_MANIFEST_BYTES:
        raise GeneratedImageError("이미지 기록 크기 제한을 초과했습니다.")
    _atomic(root / "manifest.json", data)


def _png(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_IMAGE_BYTES or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise GeneratedImageError("생성 결과가 올바른 PNG가 아닙니다.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "PNG" or image.width * image.height > 20_000_000:
                raise ValueError()
            image.verify()
    except (OSError, ValueError, Image.DecompressionBombError):
        raise GeneratedImageError("생성 PNG를 확인할 수 없습니다.") from None
    return data


def _read_asset(root, key, record):
    if not isinstance(key, str) or not HEX.fullmatch(key) or not isinstance(record, dict) or record.get("state") != "completed":
        return None
    digest = record.get("descriptor_hash")
    if not isinstance(digest, str) or not HEX.fullmatch(digest) or not isinstance(record.get("descriptor"), dict) or _hash(record["descriptor"]) != digest:
        return None
    if record.get("prompt_version") != PROMPT_VERSION or not isinstance(record.get("model"), str) or _generation_key(digest, record["model"]) != key:
        return None
    filename = record.get("file")
    checksum = record.get("sha256")
    if filename != key + ".png" or not isinstance(checksum, str) or not HEX.fullmatch(checksum):
        return None
    path = root / filename
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_IMAGE_BYTES:
        return None
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != checksum:
        return None
    return _png(data)


def get_generated_image(item):
    """고정 디렉터리의 검증된 PNG만 동일 photo dict로 반환한다. 외부 호출 없음."""
    try:
        target = descriptor(item)
        digest = _hash(target)
        root = ASSET_DIR
        if root.is_symlink():
            return None
        records = _read_manifest(root)["entries"]
        for key, record in reversed(list(records.items())):
            if not isinstance(record, dict) or record.get("descriptor_hash") != digest or record.get("descriptor") != target:
                continue
            data = _read_asset(root, key, record)
            if data:
                return {"src": "data:image/png;base64," + base64.b64encode(data).decode(), "label": "AI 생성 이미지",
                        "title": target["name"] + " · AI 생성 참고 이미지, 실제 메뉴와 다를 수 있어요",
                        "author": "", "license": "", "source_url": "", "license_url": ""}
    except (GeneratedImageError, OSError, TypeError, ValueError):
        pass
    return None


def generate_batch(items, generator, *, model, asset_dir=None):
    """CLI용: 최대 2회, 순차 생성. pending/실패 기록은 명시적 정리 전 재시도하지 않는다.

    generator는 정규화된 profile dict 하나를 받아 PNG bytes를 반환한다.
    """
    if not isinstance(items, list) or not 1 <= len(items) <= 2:
        raise GeneratedImageError("한 번에 1~2개 음식만 생성할 수 있습니다.")
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9._:/-]{1,100}", model):
        raise GeneratedImageError("이미지 모델 설정을 확인해 주세요.")
    descriptors = [descriptor(item) for item in items]
    root = Path(asset_dir) if asset_dir is not None else ASSET_DIR
    if root.is_symlink():
        raise GeneratedImageError("이미지 저장 경로를 확인해 주세요.")
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".generation.lock"
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise GeneratedImageError("이미지 생성 작업이 이미 진행 중이거나 중단 기록이 남아 있습니다.") from None
    try:
        os.close(lock_fd)
        manifest = _read_manifest(root)
        results = []
        for desc in descriptors:
            digest = _hash(desc)
            key = _generation_key(digest, model)
            previous = manifest["entries"].get(key)
            if previous is not None:
                try:
                    valid = _read_asset(root, key, previous)
                except (GeneratedImageError, OSError):
                    valid = None
                results.append({"descriptor_hash": digest, "generation_key": key,
                                "state": "reused" if valid else "blocked", "file": key + ".png" if valid else None})
                continue
            record = {"descriptor_hash": digest, "descriptor": desc, "model": model,
                      "prompt_version": PROMPT_VERSION, "quality": "low", "size": "1024x1024", "output_format": "png",
                      "state": "pending", "created_at": _date()}
            manifest["entries"][key] = record
            _save_manifest(root, manifest)  # 유료 요청보다 먼저 기록한다.
            profile = {"name": desc["name"], "original_name": desc["original_name"],
                       "main_ingredients": desc["ingredients"], "cooking_methods": desc["cooking_methods"], "status": "known"}
            try:
                data = _png(generator(profile))
                _atomic(root / (key + ".png"), data)
                record.update(state="completed", file=key + ".png", sha256=hashlib.sha256(data).hexdigest(), completed_at=_date())
            except Exception as error:
                # 응답 유실 뒤에도 공급자에서 비용이 발생했을 수 있다. 예외 문자열은 저장하지 않는다.
                record.update(state="uncertain", completed_at=_date())
                if isinstance(error, GeneratedImageError):
                    record["error"] = str(error)
            _save_manifest(root, manifest)
            results.append({"descriptor_hash": digest, "generation_key": key, "state": record["state"], "file": record.get("file")})
        return results
    finally:
        lock.unlink(missing_ok=True)
