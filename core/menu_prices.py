"""명시된 단일 메뉴 가격과 일별 기준 환율을 표시한다. 통화를 추측하지 않는다."""
from collections import OrderedDict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from email.utils import parsedate_to_datetime
import math
import re
from threading import RLock
import time

import httpx


CURRENCY_OPTIONS = {
    "": "통화 선택", "EUR": "EUR · 유로", "USD": "USD · 미국 달러", "GBP": "GBP · 영국 파운드",
    "JPY": "JPY · 일본 엔", "CNY": "CNY · 중국 위안", "KRW": "KRW · 대한민국 원",
    "CAD": "CAD · 캐나다 달러", "AUD": "AUD · 호주 달러", "CHF": "CHF · 스위스 프랑",
    "HKD": "HKD · 홍콩 달러", "SGD": "SGD · 싱가포르 달러", "THB": "THB · 태국 바트",
}
SYMBOLS = {"€": "EUR", "£": "GBP", "₩": "KRW", "원": "KRW", "฿": "THB"}
AMBIGUOUS = {"$": {"USD", "CAD", "AUD", "HKD", "SGD", "NZD"}, "¥": {"JPY", "CNY"}, "￥": {"JPY", "CNY"}}
_TOKEN = r"(?:[A-Za-z]{3}|[€£₩฿$¥￥]|원)"
_PRICE = re.compile(rf"^\s*(?P<before>{_TOKEN})?\s*(?P<amount>\d[\d., \u00a0]*?)\s*(?P<after>{_TOKEN})?\s*$")
API_ROOT = "https://api.frankfurter.dev/v2/rate"
CACHE_TTL = 3600
FAILURE_TTL = 60
CACHE_LIMIT = 16
_CACHE = OrderedDict()
_LOCK = RLock()
_BLOCKED_UNTIL = 0.0
_LIVE = object()


def currency_code(extraction):
    """모델이 명시한 ISO 코드만 읽는다. 추정 설명 복구도 단일 대문자 코드로 제한한다."""
    if not isinstance(extraction, dict):
        return ""
    source = extraction.get("currency_source")
    if not isinstance(source, str) or source not in {"printed", "inferred"}:
        return ""
    code = extraction.get("currency_code")
    if isinstance(code, str) and re.fullmatch(r"[A-Z]{3}", code.strip().upper()):
        return code.strip().upper()
    # 누락된 코드만 복구한다. 잘못된 비어 있지 않은 코드나 인쇄 통화는 해석하지 않는다.
    if code is not None and (not isinstance(code, str) or code.strip()):
        return ""
    if extraction.get("currency_source") != "inferred":
        return ""
    evidence = extraction.get("currency_evidence")
    if not isinstance(evidence, str):
        return ""
    candidates = set(re.findall(r"(?<!\w)[A-Z]{3}(?!\w)", evidence))
    return next(iter(candidates)) if len(candidates) == 1 else ""


def _today():
    return datetime.now(timezone.utc).date()


def _amount(raw):
    """소수점 한두 자리 또는 엄격한 세 자리 구분만 허용한다."""
    if " " in raw or "\u00a0" in raw:
        if not re.fullmatch(r"\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d{1,2})?", raw):
            return None
        raw = raw.replace(" ", "").replace("\u00a0", "")
    if len(re.sub(r"\D", "", raw)) > 15:
        return None
    if "." in raw and "," in raw:
        decimal = "." if raw.rfind(".") > raw.rfind(",") else ","
        grouping = "," if decimal == "." else "."
        whole, fraction = raw.rsplit(decimal, 1)
        if not re.fullmatch(r"\d{1,2}", fraction) or not re.fullmatch(rf"\d{{1,3}}(?:{re.escape(grouping)}\d{{3}})+", whole):
            return None
        raw = whole.replace(grouping, "") + "." + fraction
    elif "." in raw or "," in raw:
        separator = "." if "." in raw else ","
        parts = raw.split(separator)
        if len(parts) == 2 and 1 <= len(parts[1]) <= 2 and all(part.isdigit() for part in parts):
            raw = ".".join(parts)
        elif re.fullmatch(rf"[1-9]\d{{0,2}}(?:{re.escape(separator)}\d{{3}})+", raw):
            raw = raw.replace(separator, "")
        else:
            return None
    try:
        value = Decimal(raw)
        return value if value.is_finite() and value >= 0 else None
    except InvalidOperation:
        return None


def _parse(price, currency):
    match = _PRICE.fullmatch(price)
    if not match:
        return None, "", False
    value = _amount(match["amount"])
    if value is None:
        return None, "", False
    tokens = [token for token in (match["before"], match["after"]) if token]
    explicit = {SYMBOLS.get(token, token.upper()) for token in tokens if token not in AMBIGUOUS}
    if len(explicit) > 1:
        return None, "", False
    code = next(iter(explicit), currency)
    # 표시 라벨 목록은 지원 통화 제한이 아니다. 실제 환율 지원 여부는 응답으로 확인한다.
    if not re.fullmatch(r"[A-Z]{3}", code):
        return value, "", False
    if any(code not in AMBIGUOUS[token] for token in tokens if token in AMBIGUOUS):
        return value, "", False
    return value, code, bool(explicit)


def _valid_rate(data, currency):
    if not isinstance(data, dict) or data.get("base") != currency or data.get("quote") != "KRW":
        return None
    value = data.get("rate")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None
    day = data.get("date")
    try:
        if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or date.fromisoformat(day) > _today():
            return None
    except ValueError:
        return None
    return {"date": day, "base": currency, "quote": "KRW", "rate": value}


def _retry_seconds(value):
    if not value:
        return FAILURE_TTL
    try:
        seconds = float(value)
        return max(0, seconds) if math.isfinite(seconds) else FAILURE_TTL
    except (TypeError, ValueError):
        try:
            day = parsedate_to_datetime(value)
            if day.tzinfo is None:
                day = day.replace(tzinfo=timezone.utc)
            return max(0, day.timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return FAILURE_TTL


def _rate(currency):
    """한 시간/UTC 날짜 단위 캐시. 429는 전체 통화 요청의 재시도 시각을 지킨다."""
    global _BLOCKED_UNTIL
    key = (currency, _today().isoformat())
    with _LOCK:
        now = time.monotonic()
        cached = _CACHE.get(key)
        if cached and cached[0] > now:
            _CACHE.move_to_end(key)
            return dict(cached[1]) if cached[1] else None
        if now < _BLOCKED_UNTIL:
            return None
        data, ttl = None, FAILURE_TTL
        try:
            response = httpx.get(f"{API_ROOT}/{currency}/KRW", timeout=3.0, follow_redirects=False)
            if response.status_code == 429:
                ttl = _retry_seconds(response.headers.get("Retry-After"))
                _BLOCKED_UNTIL = time.monotonic() + ttl
            elif response.status_code == 200:
                data = _valid_rate(response.json(), currency)
                if data:
                    ttl = CACHE_TTL
        except (httpx.HTTPError, ValueError, TypeError):
            pass
        _CACHE[key] = (time.monotonic() + ttl, data)
        _CACHE.move_to_end(key)
        while len(_CACHE) > CACHE_LIMIT:
            _CACHE.popitem(last=False)
        return dict(data) if data else None


def price_info(price, currency="", *, fx_data=_LIVE):
    """단일 가격 표시. fx_data=dict/None은 네트워크 없는 고정 환율 주입이다."""
    raw = price.strip() if isinstance(price, str) else ""
    context = currency.strip().upper() if isinstance(currency, str) else ""
    result = {"display": raw, "krw": "", "date": "", "currency": "", "notice": "", "status": "unparsed"}
    if not raw:
        return result
    amount, code, explicit = _parse(raw, context)
    if amount is None:
        result["notice"] = "단일 가격을 확인해 주세요."
        return result
    if not code:
        result.update(status="currency_required", notice="통화를 확인해 주세요.")
        return result
    result.update(currency=code, display=raw if explicit else f"{raw} {code}")
    if code == "KRW":
        result["status"] = "krw"
        return result
    data = _rate(code) if fx_data is _LIVE else _valid_rate(fx_data, code)
    if not data:
        result.update(status="unavailable", notice="원화 환산을 지금 확인할 수 없어요.")
        return result
    try:
        won = (amount * Decimal(str(data["rate"]))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        result.update(status="unavailable", notice="원화 환산을 지금 확인할 수 없어요.")
        return result
    result.update(krw=f"약 {won:,.0f}원", date=data["date"], status="converted")
    return result
