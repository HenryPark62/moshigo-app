"""식당 메뉴 불러오기: 가게 홈페이지나 이 가게의 메뉴 페이지에서 실제 메뉴를 찾아, 메뉴판을 찍은 것과 같은 화면으로 보여 준다.

Claude의 웹 열기(web_fetch)와 웹 검색(web_search, 서버 도구)으로 이 식당 페이지를 열고, 그 페이지에 적힌 메뉴만 옮긴다.
홈페이지 주소를 알면 먼저 그 페이지를 열고(싸고 빠르다), 모르거나 메뉴가 없으면 검색한다.
찾지 못했거나 이 식당인지 확실하지 않으면 None. 옮긴 요리 이름이 실제로 연 페이지에 있는지 코드에서 다시 확인하고,
없는 이름은 버린다. 메뉴를 지어내지 않는다.
찾은 목록은 식당마다 SQLite에 저장해서 같은 식당은 다시 찾지 않는다 (못 찾음은 짧게 기억한다).
설명과 사람별 판정(2단계)은 사진과 같은 menu2.describe_list를 쓴다.
"""
import json
import os
import re
import sqlite3
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

from . import menu2

DB = Path(os.environ.get("MOSHIGO_DB", Path(__file__).parent / "data" / "moshigo.db"))
FIND_MODEL = "claude-sonnet-5-5"  # 검색, 열기, 옮기기 (빠르고 싼 모델로 충분하다)
KEEP_FOUND = 14 * 86400           # 찾은 메뉴는 2주 기억
KEEP_MISS = 86400                 # 못 찾음은 하루만 (가게가 홈페이지를 새로 열 수 있다)
TIMEOUT = 70                      # 한 번 묻는 데 쓰는 최대 초
MIN_LINES = 3                     # 페이지에서 확인된 요리가 이보다 적으면 못 찾은 것으로 본다
SEARCHES, FETCHES = 3, 4          # 서버 도구를 쓰는 최대 횟수 (비용과 시간)

FIND_SCHEMA = {"type": "object", "properties": {
    "found": {"type": "boolean", "description": "이 가게의 메뉴를 web_fetch로 연 페이지에서 확인했으면 true"},
    "source_url": {"type": "string", "description": "메뉴를 옮긴 페이지 주소. web_fetch로 연 주소 그대로. 못 찾았으면 빈 문자열"},
    "source_title": {"type": "string", "description": "그 페이지 제목. 모르면 빈 문자열"},
    "restaurant": {"type": "string", "description": "페이지에 적힌 가게 이름"},
    "menu_language": {"type": "string", "description": "메뉴가 적힌 언어. 예: 프랑스어"},
    "language_code": {"type": "string", "description": "BCP 47. 예: fr-FR"},
    "lines": menu2.LIST_SCHEMA["properties"]["lines"]},
    "required": ["found", "source_url", "source_title", "restaurant", "menu_language", "language_code", "lines"], "additionalProperties": False}

FIND_SYSTEM = """너는 식당의 실제 메뉴를 인터넷에서 찾아 옮기는 도우미다. 가족이 지금 이 식당 근처에 있다.
목표: 이름과 주소가 맞는 바로 이 가게의 메뉴를 찾아, 페이지에 적힌 그대로 옮긴다.
순서:
1) 가게 홈페이지나 메뉴 페이지 주소가 있으면 web_fetch로 먼저 연다. 메뉴 링크(Menu, Carte, Speisekarte, メニュー, 菜单, 메뉴 등)가 보이면 따라 연다.
2) 주소가 없거나 홈페이지에 메뉴가 없으면 web_search로 가게 이름과 도시, menu를 함께 찾는다. 가게 공식 사이트, 예약이나 배달 사이트의 이 가게 페이지처럼 메뉴가 글자로 적힌 페이지를 연다.
3) 체인점이면 그 나라 공식 홈페이지의 메뉴를 써도 된다.
규칙:
- web_fetch로 실제로 연 페이지에 글자로 적힌 요리만 적는다. 검색 결과 요약, 기억, 짐작으로 적지 않는다.
- 이름이 같은 다른 도시, 다른 가게의 메뉴는 쓰지 않는다. 주소나 동네가 맞는지 확인한다.
- 찾지 못했거나 이 가게 메뉴인지 확실하지 않으면 found=false, lines는 빈 배열로 둔다. 억지로 채우지 않는다.
- 요리 이름은 페이지 글자 그대로(악센트, 한자, 가나 포함) 적고 번역하지 않는다. 가격은 페이지에 적힌 대로, 없으면 빈 문자열.
- 요리를 먼저 순서대로 빠짐없이 적고, 음료는 대표적인 것 10개까지. 모두 60개까지.
- 오래 헤매지 않는다. 몇 번 찾아도 없으면 found=false."""


# ---------- 글자 맞추기 (옮긴 이름이 페이지에 정말 있는지) ----------
def norm(s):
    """대소문자, 악센트, 띄어쓰기, 문장 부호를 무시하고 비교하려고 글자만 남긴다."""
    s = unicodedata.normalize("NFKD", s or "").casefold()
    s = unicodedata.normalize("NFC", "".join(c for c in s if not unicodedata.combining(c)))  # 한글은 다시 붙인다
    s = s.replace("œ", "oe").replace("æ", "ae").replace("ß", "ss")
    return re.sub(r"[\W_]+", "", s)


def seen(name, page):
    """요리 이름이 페이지 글자(norm을 거친 것)에 있으면 True. 이름 전체가 없으면 3글자 넘는 낱말이 모두 있어야 한다."""
    n = norm(name)
    if len(n) < 2:
        return False
    if n in page:
        return True
    words = [norm(w) for w in re.split(r"[\s,/&+()\-–]+", name) if len(norm(w)) >= 3]
    return len(words) >= 2 and all(w in page for w in words)


def url_key(u):
    """주소 비교용: http/https, www, 끝의 /, # 뒤는 무시."""
    p = urlparse((u or "").strip())
    host = (p.netloc or "").lower().removeprefix("www.")
    return host + (p.path or "").rstrip("/") + (f"?{p.query}" if p.query else "")


def host_of(u):
    return (urlparse(u or "").netloc or "").lower().removeprefix("www.")


# ---------- 찾은 결과 -> 2단계 입력 ----------
def check(data, pages, place):
    """Claude 답(data)과 실제로 연 페이지들(pages: [{url, title, text}], PDF는 text=None)을 맞춰 본다.

    돌려주는 것: {"head": LIST_SCHEMA 모양(2단계 입력), "source": {kind, url, title, site, own}} 또는 None.
    - found=false거나 연 페이지가 없으면 None.
    - 메뉴를 옮긴 페이지를 실제로 열었어야 한다. 답한 주소가 연 페이지에 없으면, 이름이 가장 많이 보이는 연 페이지로 본다.
    - 그 페이지 글자에 없는 요리 이름은 버린다. 남은 요리가 MIN_LINES개보다 적거나 절반에 못 미치면 None.
    """
    if not data or not data.get("found") or not pages:
        return None
    lines = []
    for ln in data.get("lines") or []:
        name = (ln.get("name_orig") or "").strip()
        if name:
            lines.append({"section_orig": (ln.get("section_orig") or "").strip(), "name_orig": name,
                          "price": (ln.get("price") or "").strip(), "note": (ln.get("note") or "").strip()})
    if not lines:
        return None
    texts = [p for p in pages if p.get("text")]
    src = {url_key(p["url"]): p for p in pages}.get(url_key(data.get("source_url")))
    if src is None:  # 답한 주소를 열지 않았다: 이름이 가장 많이 보이는 연 페이지를 출처로
        if not texts:
            return None
        src = max(texts, key=lambda p: sum(seen(ln["name_orig"], norm(p["text"])) for ln in lines))
    if src.get("text") is not None:
        # 메뉴가 여러 쪽(전채, 주요리 페이지 등)에 나뉘어 있을 수 있어서, 출처와 같은 사이트에서 연 페이지 글자를 모두 본다
        page = norm(" ".join(p["text"] for p in texts if host_of(p["url"]) == host_of(src["url"])))
        kept = [ln for ln in lines if seen(ln["name_orig"], page)]
    else:  # PDF 메뉴: 글자를 따로 꺼낼 수 없어서, 연 PDF에서 옮긴 것만 믿는다
        kept = lines
    if len(kept) < MIN_LINES or len(kept) < 0.5 * len(lines):
        return None
    site = host_of(src["url"])
    own = bool(site) and any(site == host_of(place.get(k)) for k in ("website", "menu_url"))
    head = {"is_menu": True, "restaurant": (data.get("restaurant") or "").strip() or place.get("name", ""),
            "menu_language": data.get("menu_language") or "", "language_code": data.get("language_code") or "",
            "lines": kept[:menu2.MAX_ITEMS]}
    return {"head": head, "source": {"kind": "web", "url": src["url"], "title": (src.get("title") or data.get("source_title") or "").strip(),
                                     "site": site, "own": own}}


# ---------- 저장 (식당마다) ----------
def _db():
    con = sqlite3.connect(DB)
    con.execute("create table if not exists webmenu (key text primary key, data text, found int, ts real)")
    return con


def key_of(place):
    """같은 식당이면 같은 열쇠: 이름 + 위치(약 100m 단위). 출처(카카오, OSM)마다 id가 달라서 id는 쓰지 않는다."""
    return f"{norm(place.get('orig_name') or place.get('name'))}|{round(float(place['lat']), 3)}|{round(float(place['lng']), 3)}"


def cache_get(key, now=None):
    """(기억이 있는지, 값). 값이 None이면 '못 찾음'을 기억하고 있는 것."""
    now = time.time() if now is None else now
    with _db() as con:
        row = con.execute("select data, found, ts from webmenu where key = ?", (key,)).fetchone()
    if not row or now - row[2] > (KEEP_FOUND if row[1] else KEEP_MISS):
        return False, None
    return True, json.loads(row[0]) if row[1] else None


def cache_put(key, value, now=None):
    with _db() as con:
        con.execute("insert into webmenu (key, data, found, ts) values (?, ?, ?, ?) on conflict(key) do update set "
                    "data = excluded.data, found = excluded.found, ts = excluded.ts",
                    (key, json.dumps(value, ensure_ascii=False) if value else "", int(bool(value)), time.time() if now is None else now))


# ---------- Claude에게 묻기 ----------
def ask_text(place):
    rows = [("식당", place.get("name")), ("원래 이름", place.get("orig_name")), ("주소", place.get("address")),
            ("위치", f"위도 {place['lat']:.5f}, 경도 {place['lng']:.5f}" if place.get("lat") is not None else ""),
            ("가게 홈페이지", place.get("website")), ("메뉴 페이지", place.get("menu_url")), ("지도 페이지", place.get("url"))]
    known = "\n".join(f"{k}: {v}" for k, v in rows if v)
    first = "메뉴 페이지와 홈페이지를 먼저 열어 보세요." if place.get("website") or place.get("menu_url") else "홈페이지 주소는 몰라요. 검색해서 찾아 주세요."
    return f"{known}\n\n이 식당의 메뉴를 찾아 옮겨 주세요. {first}"


def _client():
    import anthropic

    return anthropic.Anthropic(timeout=TIMEOUT, max_retries=1)


def ask(place, say):
    """Claude가 검색하고 열어 본 뒤 답한다. 돌려주는 것: (답 JSON, 실제로 연 페이지들)."""
    tools = [{"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": FETCHES, "max_content_tokens": 20000, "allowed_callers": ["direct"]},
             {"type": "web_search_20260209", "name": "web_search", "max_uses": SEARCHES, "allowed_callers": ["direct"]}]
    messages = [{"role": "user", "content": ask_text(place)}]
    pages, msg, start = [], None, time.time()
    for _ in range(3):  # 서버 쪽 반복 한도에 걸리면(pause_turn) 이어서 묻는다
        with _client().beta.messages.stream(model=FIND_MODEL, max_tokens=12000, system=FIND_SYSTEM, messages=messages, tools=tools,
                                            output_config={"effort": "low", "format": {"type": "json_schema", "schema": FIND_SCHEMA}}) as stream:
            for ev in stream:
                if ev.type == "content_block_start" and getattr(ev.content_block, "type", "") == "server_tool_use":
                    say("이 식당 메뉴를 검색하는 중이에요" if ev.content_block.name == "web_search" else "메뉴 페이지를 여는 중이에요")
            msg = stream.get_final_message()
        for b in msg.content:
            if b.type == "web_fetch_tool_result" and getattr(b.content, "type", "") == "web_fetch_result":
                doc = b.content.content
                pages.append({"url": b.content.url, "title": doc.title or "", "text": doc.source.data if doc.source.type == "text" else None})
        if msg.stop_reason != "pause_turn" or time.time() - start > TIMEOUT:
            break
        messages = messages[:1] + [{"role": "assistant", "content": msg.content}]
    if msg.stop_reason in ("refusal", "max_tokens", "pause_turn"):
        print(f"[webmenu] stop_reason={msg.stop_reason}")
        return None, pages
    texts = [b.text for b in msg.content if b.type == "text"]
    try:
        return json.loads(texts[-1]), pages
    except (IndexError, ValueError):
        return None, pages


def find_menu(place, progress=None, asker=None):
    """이 식당 메뉴 목록 {head, source} 또는 None. 저장된 결과가 있으면 다시 찾지 않는다.
    asker는 테스트용 (place, say) -> (답, 연 페이지들)."""
    say = progress or (lambda *_: None)
    key = key_of(place)
    hit, value = cache_get(key)
    if hit:
        return value
    say("이 식당 메뉴를 찾는 중이에요")
    try:
        data, pages = (asker or ask)(place, say)
    except Exception as e:  # 네트워크나 API 오류는 기억하지 않는다 (다음에 다시 찾는다)
        print(f"[webmenu] 실패: {e!r}")
        from .nearby import _err
        _err("메뉴 불러오기", e)  # ?dev=1 화면에서 보이게
        return None
    got = check(data, pages, place)
    cache_put(key, got)
    found = f"찾음 {got['source']['url']} ({len(got['head']['lines'])}개)" if got else "못 찾음"
    print(f"[webmenu] {place.get('name')}: {found} (연 페이지 {len(pages)}곳)")
    return got


def read_web(place, people, progress=None, asker=None):
    """식당 -> 메뉴판을 찍은 것과 같은 결과(raw, menu2.enrich 전). 못 찾으면 None. raw['source']에 출처."""
    got = find_menu(place, progress, asker)
    if not got:
        return None
    raw = menu2.describe_list(got["head"], people, progress)
    if not [i for i in raw.get("items") or [] if not i.get("unreadable")]:
        return None
    raw["source"] = got["source"]
    return raw
