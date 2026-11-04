"""메뉴 사진 영역 → 라이선스를 확인한 대표 사진 → 음식 종류 참고 그림.

외부 검색에는 아래 공개 음식명만 사용한다. 사진·가족 정보·원문 설명은 전송하지 않는다.
"""
import base64
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import html
import io
import json
import math
import re
import threading
import time
import unicodedata
from urllib.parse import urlsplit

import httpx
from PIL import Image, ImageOps


SUCCESS_TTL = 24 * 60 * 60
FAILURE_TTL = 5 * 60
BULK_WAIT_SECONDS = 6
LOOKUP_SECONDS = 5.5
MAX_CACHE = 256
MAX_PENDING = 24
_lock = threading.RLock()
_cache = OrderedDict()
_pending = {}
_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="dish-photo")
_cooldown_until = 0.0

# 검색어는 이 공개 요리명으로만 고정한다. 실제 메뉴 원문은 URL에 넣지 않는다.
ALIASES = {
    "jägerschnitzel": "Jägerschnitzel", "jaegerschnitzel": "Jägerschnitzel", "예거슈니첼": "Jägerschnitzel",
    "schnitzel": "Schnitzel", "슈니첼": "Schnitzel",
    "käsespätzle": "Käsespätzle", "kaesespaetzle": "Käsespätzle", "케제슈페츨레": "Käsespätzle",
    "grüne soße": "Frankfurter Grüne Soße", "grüne sosse": "Frankfurter Grüne Soße", "green sauce": "Frankfurter Grüne Soße",
    "frikadelle": "Frikadeller", "frikadellen": "Frikadeller", "프리카델레": "Frikadeller",
    "currywurst": "Currywurst", "커리부어스트": "Currywurst",
    "schweinshaxe": "Schweinshaxe", "슈바인스학세": "Schweinshaxe",
    "schweinebraten": "Schweinsbraten", "슈바이네브라텐": "Schweinsbraten",
    "leberkäse": "Leberkäse", "leberkaese": "Leberkäse", "레버케제": "Leberkäse",
    "bratwurst": "Bratwurst", "브라트부어스트": "Bratwurst",
    "rump steak": "Rump steak", "rumpsteak": "Rump steak", "럼프 스테이크": "Rump steak",
    "teriyaki salmon": "Salmon as food", "salmon teriyaki": "Salmon as food", "연어 데리야키": "Salmon as food",
    "bœuf bourguignon": "Beef bourguignon", "boeuf bourguignon": "Beef bourguignon", "beef bourguignon": "Beef bourguignon",
    "soupe à l'oignon": "French onion soup", "french onion soup": "French onion soup",
    "escargots": "Escargot", "escargot": "Escargot", "croque-monsieur": "Croque monsieur",
    "crème brûlée": "Crème brûlée", "creme brulee": "Crème brûlée", "tarte tatin": "Tarte Tatin",
    "moules marinières": "Moules marinières", "steak frites": "Steak frites", "quiche lorraine": "Quiche",
    "profiteroles": "Profiterole", "mousse au chocolat": "Chocolate mousse", "감자튀김": "French fries",
}


def _normal(text):
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def public_query(item):
    """알려진 음식 토큰만 식별한다. 미등록 이름은 검색하지 않는다."""
    for value in (item.get("name_orig"), item.get("input_name"), item.get("name_ko")):
        if not isinstance(value, str) or len(value) > 250:
            continue
        text = _normal(value)
        for alias in sorted(ALIASES, key=len, reverse=True):
            if re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text):
                return ALIASES[alias]
    return None


def _url(value, hosts):
    if not isinstance(value, str) or any(c.isspace() for c in value):
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme == "https" and parts.hostname in hosts and not parts.username and not parts.password and parts.port in (None, 443):
            return value
    except ValueError:
        pass
    return None


def _plain(value):
    return html.unescape(re.sub(r"<[^>]*>", "", value))[:300].strip() if isinstance(value, str) else ""


def _cooldown(value):
    global _cooldown_until
    seconds = 60.0
    try:
        seconds = float(value)
        if not math.isfinite(seconds) or seconds < 0:
            seconds = 60.0
    except (TypeError, ValueError):
        try:
            seconds = max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            pass
    with _lock:
        _cooldown_until = max(_cooldown_until, time.monotonic() + max(1, seconds))


def _json(client, host, params, deadline):
    with _lock:
        if time.monotonic() < _cooldown_until:
            return None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    with client.stream("GET", f"https://{host}/w/api.php", params={"action": "query", "format": "json", **params},
                       timeout=min(3, remaining)) as response:
        if response.status_code == 429:
            _cooldown(response.headers.get("Retry-After"))
            return None
        if response.status_code != 200:
            return None
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > 1024 * 1024 or time.monotonic() > deadline:
                return None
            chunks.append(chunk)
        value = json.loads(b"".join(chunks))
        return value if isinstance(value, dict) else None


def _page(data):
    pages = (data or {}).get("query", {}).get("pages", {})
    return next((p for p in pages.values() if isinstance(p, dict)), {}) if isinstance(pages, dict) else {}


def _is_food(page):
    if "disambiguation" in (page.get("pageprops") or {}):
        return False
    categories = page.get("categories") or []
    pattern = r"\b(dishes|foods|soups|stews|salads|desserts|pastries|breads|cheeses|noodles|dumplings|sandwiches|beverages|drinks|confectionery|puddings|sausages|sauces|meat|seafood|cuisine)\b"
    return any(isinstance(c, dict) and re.search(pattern, str(c.get("title", "")).lower()) for c in categories)


def _lookup(query, transport=None):
    """고정 음식 제목만 조회. 모호/비음식 문서는 다른 검색 결과로 대체하지 않는다."""
    if query not in ALIASES.values():
        return None
    deadline = time.monotonic() + LOOKUP_SECONDS
    try:
        with httpx.Client(transport=transport, follow_redirects=False, trust_env=False,
                          headers={"User-Agent": "Moshigo/1.0 (representative food images; Wikimedia API)"}) as client:
            page = _page(_json(client, "en.wikipedia.org", {"prop": "pageimages|categories|pageprops", "cllimit": "50",
                "clshow": "!hidden", "piprop": "name", "pilicense": "free", "redirects": "1", "titles": query}, deadline))
            if not page.get("pageimage") or not _is_food(page):
                return None
            file = _page(_json(client, "commons.wikimedia.org", {"prop": "imageinfo", "titles": "File:" + page["pageimage"],
                "iiprop": "url|extmetadata", "iiurlwidth": "640", "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl|AttributionRequired"}, deadline))
            info = (file.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            license_name = _plain((meta.get("LicenseShortName") or {}).get("value"))
            author = _plain((meta.get("Artist") or {}).get("value"))
            license_url = _url((meta.get("LicenseUrl") or {}).get("value"), {"creativecommons.org"})
            if not re.fullmatch(r"CC BY(?:-SA)? [1-4]\.0|CC0|Public domain", license_name, re.IGNORECASE):
                return None
            if not author or (license_name.upper().startswith("CC BY") and not license_url):
                return None
            src = _url(info.get("thumburl") or info.get("url"), {"upload.wikimedia.org", "thumb.wikimedia.org"})
            source_url = _url(info.get("descriptionurl"), {"commons.wikimedia.org"})
            if not src or not source_url:
                return None
            return {"src": src, "label": "대표 사진", "title": _plain(page.get("title")) or query,
                    "author": author, "license": license_name, "source_url": source_url,
                    "license_url": license_url or source_url}
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError, IndexError):
        return None


def _schedule(query):
    with _lock:
        now = time.monotonic()
        if query in _cache:
            until, image = _cache[query]
            if until > now:
                _cache.move_to_end(query)
                result = Future()
                result.set_result(image)
                return result
            del _cache[query]
        if query in _pending:
            return _pending[query]
        if now < _cooldown_until or len(_pending) >= MAX_PENDING:
            result = Future()
            result.set_result(None)
            return result
        future = _pool.submit(_lookup, query)
        _pending[query] = future

        def done(task):
            try:
                image = task.result()
            except Exception:
                image = None
            with _lock:
                _pending.pop(query, None)
                _cache[query] = (time.monotonic() + (SUCCESS_TTL if image else FAILURE_TTL), image)
                _cache.move_to_end(query)
                while len(_cache) > MAX_CACHE:
                    _cache.popitem(last=False)
        future.add_done_callback(done)
        return future


def _illustration(item):
    profile = item.get("profile") or {}
    text = str(profile.get("food_type", "")) + " " + str(item.get("name_ko", "")) + " " + str(item.get("name_orig", ""))
    form = "plate"
    for kind, pattern in (("drink", r"음료|주류|커피|차$|coffee|beer"), ("soup", r"국물|커리|수프|찌개|soup|stew"),
                          ("fish", r"생선|해산물|연어|홍합|조개|새우|오징어|문어|salmon|fish|moules|mussel|shrimp"), ("noodles", r"면요리|국수|파스타|spätzle|pasta|noodle"),
                          ("salad", r"샐러드|채소|salad"), ("dessert", r"후식|디저트|케이크|푸딩|tarte|brûlée|dessert"),
                          ("grill", r"고기|튀김|스테이크|슈니첼|schnitzel|wurst|steak|braten|haxe|frikadelle")):
        if re.search(pattern, text, re.I):
            form = kind
            break
    shapes = {
        "plate": '<ellipse cx="120" cy="89" rx="69" ry="43" fill="#fffaf1" stroke="#d6cdbb" stroke-width="3"/><path d="M70 86q48-38 98 0" fill="none" stroke="#c9b58a" stroke-width="5"/>',
        "grill": '<ellipse cx="120" cy="90" rx="80" ry="43" fill="#fffaf1"/><path d="M68 83q0-30 40-29t48 30q-1 32-46 30T68 83" fill="#b8733c"/><path d="m88 64 39 40m-20-47 36 35" stroke="#88502d" stroke-width="5"/><path d="m157 69 27 12m-28 0 25 13m-27-2 20 12" stroke="#e8be65" stroke-width="8"/>',
        "soup": '<ellipse cx="120" cy="79" rx="67" ry="31" fill="#f6f1df"/><path d="M53 79q7 61 67 61t67-61" fill="#cfdfd2"/><ellipse cx="120" cy="79" rx="57" ry="23" fill="#d6a45e"/><path d="m87 75 19 9m20-12 17 11m-32 1 9 10" stroke="#6c8e65" stroke-width="5"/>',
        "fish": '<ellipse cx="120" cy="94" rx="81" ry="43" fill="#fffaf1"/><path d="M65 91q50-60 95-6l28-17-6 38-22-9q-50 48-95-6" fill="#d88e69"/><path d="m96 74 21 32m4-40 21 32" stroke="#f2ccae" stroke-width="5"/>',
        "noodles": '<ellipse cx="120" cy="96" rx="79" ry="43" fill="#fffaf1"/><path d="M72 85q80-50 85 4t-73-3q-6-30 59-13t-1 38q-63 5-30-40" fill="none" stroke="#d9b56b" stroke-width="9"/>',
        "salad": '<ellipse cx="120" cy="100" rx="80" ry="37" fill="#fffaf1"/><ellipse cx="95" cy="82" rx="28" ry="19" fill="#91aa72" transform="rotate(-25 95 82)"/><ellipse cx="142" cy="80" rx="29" ry="20" fill="#a7bb81" transform="rotate(28 142 80)"/><ellipse cx="122" cy="103" rx="32" ry="18" fill="#7f9d69"/><circle cx="95" cy="101" r="11" fill="#d98268"/><circle cx="143" cy="95" r="10" fill="#d98268"/>',
        "dessert": '<ellipse cx="120" cy="121" rx="72" ry="20" fill="#fffaf1"/><path d="m76 108 10-48 63-9 19 57z" fill="#dbb27e"/><path d="m86 60 62-9 7 15-74 10z" fill="#f4dfbe"/><path d="m80 86 80-5" stroke="#a77c5d" stroke-width="8"/><circle cx="124" cy="51" r="9" fill="#b86d62"/>',
        "drink": '<ellipse cx="116" cy="128" rx="58" ry="14" fill="#e0d8c9"/><path d="M77 56h76v57q-4 23-38 23t-38-23z" fill="#fcf7eb"/><ellipse cx="115" cy="56" rx="38" ry="12" fill="#937452"/><path d="M154 70q40 1 16 35h-16" fill="none" stroke="#fcf7eb" stroke-width="10"/>',
    }
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="170" viewBox="0 0 240 170"><rect width="240" height="170" rx="18" fill="#f0ede3"/>' + shapes[form] + '</svg>'
    return {"src": "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode(), "label": "종류 참고 그림",
            "title": "음식 종류 참고 그림 · 실제 메뉴 사진 아님", "author": "", "license": "", "source_url": "", "license_url": ""}


def _crop(image, box):
    if not isinstance(box, (list, tuple)) or len(box) != 4 or any(type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= 1 for n in box):
        return None
    left, top, right, bottom = box
    if right <= left or bottom <= top or (right - left) * (bottom - top) > .85:
        return None
    width, height = image.size
    if (right - left) * width < 20 or (bottom - top) * height < 20:
        return None
    crop = image.crop((round(left * width), round(top * height), round(right * width), round(bottom * height))).convert("RGB")
    crop.thumbnail((480, 480))
    out = io.BytesIO()
    crop.save(out, format="JPEG", quality=85)
    return {"src": "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode(), "label": "메뉴판 사진",
            "title": "메뉴판에서 인식한 음식 사진 영역", "author": "", "license": "", "source_url": "", "license_url": ""}


def menu_images(items, report=None, image_bytes=None):
    """item id → {src,label,title,author,license,source_url,license_url}.

    최대 20개, 공개 사진 조회 3개 동시 실행·총 대기 6초. 늦은 결과는 다음 화면에서
    메모리 캐시로 재사용한다. 사용자 사진 crop은 이 호출에서만 만들고 저장하지 않는다.
    """
    items = list(items)[:20]
    metadata = {}
    for row in (report or {}).get("items", []):
        if isinstance(row, dict):
            metadata[row.get("input_name")] = row.get("menu_context") or {}
    image = None
    if isinstance(image_bytes, bytes) and len(image_bytes) <= 15 * 1024 * 1024:
        try:
            candidate = Image.open(io.BytesIO(image_bytes))
            if candidate.width * candidate.height <= 20_000_000:
                image = ImageOps.exif_transpose(candidate)
        except (OSError, ValueError, Image.DecompressionBombError):
            pass
    out, futures = {}, {}
    for item in items:
        iid = item["id"]
        context = item.get("menu_context") or metadata.get(item.get("input_name"), {})
        actual = _crop(image, context.get("photo_bbox")) if image is not None and isinstance(context, dict) else None
        if actual:
            out[iid] = actual
            continue
        out[iid] = _illustration(item)
        query = public_query(item)
        if query:
            futures[iid] = _schedule(query)
    if futures:
        wait(set(futures.values()), timeout=BULK_WAIT_SECONDS)
    for iid, future in futures.items():
        if future.done():
            try:
                photo = future.result()
            except Exception:
                photo = None
            if photo:
                out[iid] = dict(photo)
    return out
