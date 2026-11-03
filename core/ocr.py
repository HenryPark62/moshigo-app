"""메뉴판 글씨 읽기: 네이버 CLOVA OCR (General, V2).

POST {CLOVA_OCR_URL} (콘솔의 General 호출 주소), 헤더 X-OCR-SECRET.
응답의 fields 를 lineBreak 기준으로 줄로 묶고, 확신도가 낮은 글자는 표시해서 다음 단계(설명 만들기)에 넘긴다.
"""
import base64
import io
import os
import time
import uuid

import httpx

LOW = 0.6  # 이보다 낮으면 흐린 글자로 본다


def available():
    return bool(os.environ.get("CLOVA_OCR_URL") and os.environ.get("CLOVA_OCR_SECRET"))


def _format(data):
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return None


def to_jpeg(data, max_side=2000):
    """HEIC 등 다른 형식이나 너무 큰 사진은 JPEG로 바꾼다."""
    from PIL import Image

    im = Image.open(io.BytesIO(data))
    im = im.convert("RGB")
    im.thumbnail((max_side, max_side))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=88)
    return out.getvalue()


def read(data):
    """사진 바이트 -> {"lines": [{"text", "conf", "low"}], "words": n}"""
    fmt = _format(data)
    if fmt is None or len(data) > 8_000_000:
        data, fmt = to_jpeg(data), "jpg"
    body = {
        "version": "V2",
        "requestId": uuid.uuid4().hex,
        "timestamp": int(time.time() * 1000),
        "images": [{"format": fmt, "name": "menu", "data": base64.b64encode(data).decode()}],
    }
    r = httpx.post(os.environ["CLOVA_OCR_URL"], json=body, timeout=30,
                   headers={"X-OCR-SECRET": os.environ["CLOVA_OCR_SECRET"], "Content-Type": "application/json"})
    r.raise_for_status()
    img = r.json()["images"][0]
    if img.get("inferResult") != "SUCCESS":
        raise RuntimeError(f"OCR {img.get('inferResult')}: {img.get('message')}")
    return group(img.get("fields") or [])


def group(fields):
    lines, cur = [], []
    for f in fields:
        cur.append(f)
        if f.get("lineBreak", True):
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        words = [w["inferText"] + ("(?)" if w.get("inferConfidence", 1) < LOW else "") for w in ln]
        conf = min(w.get("inferConfidence", 1) for w in ln)
        out.append({"text": " ".join(words), "conf": round(conf, 2), "low": conf < LOW})
    return {"lines": out, "words": len(fields)}
