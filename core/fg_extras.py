"""Food Guide 결과 위에 얹는 모시고 기능: 맛 뱃지, 아는 맛과 닮은 메뉴, 아이 접시, 부탁 문장, 설명 보강.

Food Guide의 점수·닮은 한식·제한 판정은 바꾸지 않는다. 여기 함수는 이미 받은 값(profile, preferences,
reference_summary, group)과 사람 프로필만 다시 묶으며, 없는 재료나 맛을 만들지 않는다.

설명 줄(taste_line, ko_compare, imagine, good_for, staff_asks, kid_tip)은 Claude 보강(menu2.describe_list)이
성공했을 때만 생긴다. 보강은 백그라운드에서 한 번만 돌고, 실패하면 그 세션에서 다시 시도하지 않는다.
MOSHIGO_ENRICH=0이면 끈다.
"""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import hashlib
import json
import math
import os
import re
import threading
import time

from . import menu2, order, store

MIN_LIKE = 40          # 좋아하는 음식 기준 개인 점수가 이 이상이면 '아는 맛과 닮은 메뉴' 후보
DRINK_TYPES = {"음료", "주류"}
SPICY_WORDS = ("매운", "매콤", "얼얼", "칼칼")
SALTY_WORDS = ("짠", "짭짤")
RAW_WORDS = ("날것", "생식")
COOKED = {"굽기": "구운 요리", "끓이기": "끓인 요리", "날것": "날로 먹는 요리", "볶기": "볶은 요리", "부치기": "부친 요리",
          "삶기": "삶은 요리", "섞기": "버무린 요리", "오래 끓이기": "오래 끓인 요리", "찌기": "찐 요리", "튀기기": "튀긴 요리",
          "튀김": "튀긴 요리", "조림": "조린 요리"}
_BASIS = re.compile(r"좋아하는 음식 ‘(.+?)’ 기준")
_SHARED = (("주재료 공통", "ing"), ("소스·양념 공통", "sauce"), ("조리법 공통", "cook"))


# ---------- 공통 ----------
def _strs(value):
    return [x.strip() for x in value if isinstance(x, str) and x.strip()] if isinstance(value, list) else []


def profile(item):
    p = item.get("profile")
    return p if isinstance(p, dict) and p.get("status", "known") == "known" else {}


def roles(item):
    return set(_strs(profile(item).get("meal_roles")))


def is_drink(item):
    r = roles(item)
    return profile(item).get("food_type") in DRINK_TYPES or bool(r) and r <= DRINK_TYPES


def is_dessert(item):
    r = roles(item)
    return bool(r) and r <= {"디저트"}


def is_food(item):
    """분석에 성공한 먹는 메뉴(음료·주류 제외)."""
    return item.get("status") == "ok" and bool(profile(item)) and not is_drink(item)


def _score(pref):
    s = (pref or {}).get("score")
    if isinstance(s, bool) or not isinstance(s, (int, float)) or not math.isfinite(s) or not 0 <= s <= 100:
        return None
    return float(s)


def pref_of(item, person_id):
    return next((p for p in item.get("preferences") or [] if p.get("id") == person_id), {})


def _ingredients(item):
    p = profile(item)
    return _strs(p.get("main_ingredients")) + _strs(p.get("seasonings"))


def _spicy(item):
    return any(w in t for t in _strs(profile(item).get("taste")) for w in SPICY_WORDS)


def _raw(item):
    return any(w in c for c in _strs(profile(item).get("cooking_methods")) for w in RAW_WORDS)


def _has(item, word):
    """재료 목록에 그 낱말이 있고, 메뉴 이름 자체가 그 재료는 아닐 때 (양파 수프에서 '양파 빼고'는 하지 않는다)."""
    return any(word in i for i in _ingredients(item)) and word not in (item.get("name_ko") or "")


# ---------- 맛 뱃지 ----------
def badges(item, n=None):
    """맛(t)·향(a)·식감(x)을 고르게 섞고 조리법(c) 하나. [(종류, 낱말)]. Food Guide profile에 있는 낱말만."""
    if item.get("status") != "ok":
        return []
    p = profile(item)
    groups = [("t", _strs(p.get("taste"))), ("a", _strs(p.get("aroma"))), ("x", _strs(p.get("texture")))]
    out, seen = [], set()
    for i in range(max((len(words) for _, words in groups), default=0)):
        for cls, words in groups:
            if len(words) > i and words[i] not in seen:
                seen.add(words[i])
                out.append((cls, words[i]))
    if n:
        out = out[:n]
    cooking = _strs(p.get("cooking_methods"))
    if cooking and not is_drink(item) and not is_dessert(item):
        out.append(("c", COOKED.get(cooking[0], cooking[0])))
    return out


# ---------- 좋아하는 음식 ----------
def _favorite_names(scan):
    """사람 id -> {Food Guide 대표 이름: 사람이 적은 이름}. 예: 홍합국 -> 홍합탕."""
    out = {}
    for row in scan.get("reference_summary") or []:
        if isinstance(row, dict):
            out[row.get("id")] = {f.get("name"): f.get("favorite") or f.get("name") for f in row.get("resolved_foods") or []
                                  if isinstance(f, dict) and f.get("name")}
    return out


def basis(pref):
    """'좋아하는 음식 ‘홍합국’ 기준으로 비교했습니다.'에서 비교한 음식 이름."""
    for reason in _strs(pref.get("reasons")):
        m = _BASIS.search(reason)
        if m:
            return m.group(1)
    return None


def shared(pref, n=3):
    """이유 줄 중 '주재료/소스·양념/조리법 공통: a, b'에서 공통인 것. 재료가 먼저."""
    found = {kind: [] for _, kind in _SHARED}
    for reason in _strs(pref.get("reasons")):
        for head, kind in _SHARED:
            if reason.startswith(head) and ":" in reason:
                found[kind] += [w.strip() for w in reason.split(":", 1)[1].split(",") if w.strip()]
    words = found["ing"] + found["sauce"] + [COOKED.get(w, w) for w in found["cook"]]
    return list(dict.fromkeys(words))[:n]


def _liked(item, pref, favorites):
    """좋아하는 음식 기준 점수가 높고 제한 조건을 충족한 경우만 (음식 이름, 점수)."""
    score = _score(pref)
    food = basis(pref)
    if pref.get("eligible") is not True or score is None or score < MIN_LIKE or not food:
        return None
    return favorites.get(pref.get("id"), {}).get(food, food), score


def _names(who):
    return who[0] if len(who) == 1 else (f"{who[0]}{menu2.josa(who[0], '과', '와')} {who[1]}" if len(who) == 2 else f"{who[0]} 등 {len(who)}명")


def similar_top(scan, people, n=3):
    """각자 좋아하는 음식 기준 점수가 높은 메뉴 n개. 되도록 서로 다른 사람 몫으로, 같은 메뉴는 한 번만 (menu2.similar_top과 같은 방식).

    돌려주는 것: [{item, person: {id, name}, food, score, who: [같은 음식·점수인 사람], shared, line}]
    """
    ids = {p["id"] for p in people}
    favorites = _favorite_names(scan)
    cands = []
    for it in scan.get("items") or []:
        if not is_food(it):
            continue
        for pref in it.get("preferences") or []:
            liked = _liked(it, pref, favorites) if pref.get("id") in ids else None
            if liked:
                cands.append((it, pref, *liked))
    cands.sort(key=lambda c: -c[3])
    picked, dishes, persons = [], set(), set()
    for spread in (True, False):  # 먼저 사람마다 하나씩, 자리가 남으면 남은 것 중 점수 순서로
        for it, pref, food, score in cands:
            if len(picked) >= n:
                break
            if it["id"] in dishes or (spread and pref["id"] in persons):
                continue
            picked.append((it, pref, food, score))
            dishes.add(it["id"])
            persons.add(pref["id"])
    picked.sort(key=lambda c: -c[3])
    out = []
    for it, pref, food, score in picked:
        same = [(x, _liked(it, x, favorites)) for x in it.get("preferences") or [] if x.get("id") in ids]
        who = [x["name"] for x, liked in same if liked and liked[0] == food and round(liked[1]) == round(score)] or [pref["name"]]
        out.append({"item": it, "person": {"id": pref["id"], "name": pref["name"]}, "food": food, "score": score,
                    "who": who, "shared": shared(pref),
                    "line": f"{menu2.subj(_names(who))} 좋아하는 {food} 기준 {round(score)}점"})
    return out


def fans(scan, item, people):
    """'이런 분께 맞아요': 좋아하는 음식 기준 점수가 높은 사람. ['홍합탕 좋아하는 엄마']"""
    if not is_food(item):
        return []
    ids = {p["id"] for p in people}
    favorites = _favorite_names(scan)
    out = []
    for pref in item.get("preferences") or []:
        liked = _liked(item, pref, favorites) if pref.get("id") in ids else None
        if liked:
            out.append((liked[0], pref["name"]))
    return [f"{food} 좋아하는 {name}" for food, name in out]


# ---------- 아이 접시 ----------
def child_of(people):
    return next((p for p in people if p.get("child") and p.get("active", True)), None)


def kid_tweaks(item, child):
    """아이 접시로 바꾸는 부탁 (menu2.kid_tweaks의 예전 결과 규칙과 같다). 재료 목록과 아이가 골라내는 것으로만 고른다."""
    if not child or not is_food(item) or is_dessert(item):
        return []
    c = child.get("child") or {}
    out = []
    if "채소가 보이면" in (c.get("pick_out") or []):
        out += [f"{w} 빼고" for w in ("버섯", "양파") if _has(item, w)]
    if _spicy(item):
        out.append("맵지 않게")
    return [k for k in menu2.KID_REQS if k in out]


def kid_backup(scan, child, exclude=None):
    """아이가 안 먹을 때 대신 시킬 메뉴: 아이 개인 점수가 높고(제한 충족), 맵지 않고 날것이 아닌 식사 메뉴.
    아이가 잘 먹는 재료(child.good)가 재료 목록에 보이면 조금 앞으로. 없으면 None."""
    if not child:
        return None
    good = (child.get("child") or {}).get("good") or []
    best = None
    for it in scan.get("items") or []:
        if it["id"] == exclude or not is_food(it) or is_dessert(it) or _spicy(it) or _raw(it):
            continue
        pref = pref_of(it, child["id"])
        score = _score(pref)
        if pref.get("eligible") is not True or score is None or score < MIN_LIKE:
            continue
        text = " ".join(_ingredients(it) + [it.get("name_ko") or ""])
        hits = [g for g in good if g in text]
        rank = score + 5 * len(hits)
        if best is None or rank > best[0]:
            best = (rank, it, hits, score)
    if not best:
        return None
    _, it, hits, score = best
    return {"id": it["id"], "name_ko": it["name_ko"], "name_orig": it["name_orig"], "price": it.get("price") or "",
            "good": hits, "score": score}


def child_menu(scan, child):
    """함께 고를 메뉴(group)에서 아이 몫으로 연결된 메뉴. 없으면 None."""
    if not child:
        return None
    row = next((r for r in (scan.get("group") or {}).get("member_coverage") or [] if r.get("person_id") == child["id"]), None)
    return next((i for i in scan.get("items") or [] if row and i["input_name"] == row.get("menu_name")), None)


# ---------- 부탁 문장 ----------
def dish_requests(item, people, skip=(), asks=()):
    """메뉴 자세히의 '직원에게 부탁하기': 못 먹는 재료·피하는 맛에서 나온 부탁 + 기본 두 개. 4개까지."""
    if not is_food(item):
        return []
    reqs = []
    taste = _strs(profile(item).get("taste"))
    for p in people:
        reqs += [f"{word} 빼고" for word in ("양파", "버섯") if word in (p.get("cannot") or []) and _has(item, word)]
        if "짠 음식" in (p.get("avoid") or []) and any(w in t for t in taste for w in SALTY_WORDS):
            reqs.append("덜 짜게")
        if "매운 음식" in (p.get("avoid") or []) and _spicy(item):
            reqs.append("맵지 않게")
    reqs += ["소스는 따로", "덜 짜게"]
    if any("익" in (a.get("ko") or "") for q in asks for a in q.get("answers") or []):  # 굽기는 직원 질문에서 고른다
        reqs = [r for r in reqs if r != "잘 익혀 주세요"]
    return [r for r in dict.fromkeys(reqs) if r in order.REQUEST_KEYS and r not in skip][:4]


def order_requests(scan, people, quantities, hurry=False):
    """주문 카드를 처음 열 때 미리 골라 둘 부탁: 자유식이면 빨리·계산서, 아이 몫 메뉴를 담았으면 그 메뉴의 아이 부탁과 작은 접시."""
    out = ["빨리 나오는 걸로", "계산서도 같이"] if hurry else []
    child = child_of(people)
    mine = child_menu(scan, child)
    if mine and quantities.get(mine["id"]):
        out += kid_tweaks(mine, child) + ["아이용 작은 접시"]
    return [r for r in order.REQUEST_KEYS if r in out]


# ---------- Claude 설명 보강 ----------
FIELDS = ("taste_line", "ko_compare", "imagine", "good_for", "staff_asks", "kid_tip")
COOLDOWN = 30 * 60      # 한도·크레딧·인증 문제면 이 시간 동안 어느 세션도 다시 부르지 않는다
FIRST_WAIT = 0.5        # 바로 실패하는 경우(한도 초과 400)는 첫 화면에서 정리한다. 성공을 기다리지는 않는다
_POOL = ThreadPoolExecutor(2, thread_name_prefix="fg-enrich")
_JOBS = {}              # key -> {"future", "started"}
_LOCK = threading.Lock()
_DOWN = {"until": 0.0}
DOWN_WORDS = ("usage limit", "credit", "overloaded", "rate_limit", "ratelimit", "apiconnection", "authentication", "permission")


def enabled():
    return os.environ.get("MOSHIGO_ENRICH", "1").strip() != "0" and bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def llm_down(e):
    """ui.screens.llm_down과 같은 기준: 메뉴 탓이 아니라 API 쪽(사용 한도, 크레딧, 과부하, 연결, 인증) 문제인지."""
    t = f"{type(e).__name__} {e}".lower()
    return any(w in t for w in DOWN_WORDS)


def head_for(scan):
    """describe_list에 넘길 메뉴 목록 (LIST_SCHEMA 모양). 메뉴판 원문 이름·가격·설명만."""
    lines = [{"section_orig": "", "name_orig": i["name_orig"], "price": i.get("price") or "", "note": i.get("description_original") or ""}
             for i in scan.get("items") or [] if i.get("name_orig")]
    return {"is_menu": True, "restaurant": scan.get("restaurant") or "", "menu_language": scan.get("menu_language") or "",
            "language_code": scan.get("language_code") or "", "lines": lines}


def _family(people):
    base = {"relation": "", "age": "", "likes": [], "favorites": [], "avoid": [], "cannot": [], "allergies": [], "child": None}
    return [{**base, **{k: v for k, v in p.items() if v is not None or k == "child"}} for p in people]


def cache_key(scan, people):
    """메뉴판 글자 + 가족 설명이 같으면 같은 보강 결과를 쓴다."""
    head = head_for(scan)
    raw = json.dumps([1, head["language_code"], head["lines"], [menu2.describe(p) for p in _family(people)]],
                     ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _norm(text):
    return re.sub(r"\s+", " ", text or "").strip().casefold()


def pick(raw_items, head, has_child):
    """Claude 결과에서 보강할 줄만 골라 메뉴판 원문 이름에 붙인다. 이름이 맞지 않으면 버린다 (다른 메뉴에 붙이지 않는다)."""
    lookup = {_norm(line["name_orig"]): line["name_orig"] for line in head["lines"]}
    out = {}
    for it in raw_items or []:
        name = lookup.get(_norm(it.get("name_orig") if isinstance(it, dict) else ""))
        if not name or name in out or it.get("unreadable"):
            continue
        extra = {f: it[f].strip() for f in ("taste_line", "ko_compare", "imagine", "kid_tip") if isinstance(it.get(f), str) and it[f].strip()}
        good = _strs(it.get("good_for"))[:2]
        if good:
            extra["good_for"] = good
        asks = []
        for q in it.get("staff_asks") or []:
            if not isinstance(q, dict) or not all(isinstance(q.get(k), str) and q[k].strip() for k in ("q_orig", "q_ko")):
                continue
            answers = [{"orig": a["orig"].strip(), "ko": a["ko"].strip()} for a in q.get("answers") or []
                       if isinstance(a, dict) and isinstance(a.get("orig"), str) and isinstance(a.get("ko"), str) and a["orig"].strip() and a["ko"].strip()]
            if len(answers) >= 2:
                asks.append({"q_orig": q["q_orig"].strip(), "q_ko": q["q_ko"].strip(), "answers": answers[:4]})
        if asks:
            extra["staff_asks"] = asks[:2]
        if not has_child:
            extra.pop("kid_tip", None)
        if extra:
            out[name] = extra
    return out


def _describe(head, people):
    return menu2.describe_list(head, people, strict=True)


def _db():
    con = store._db()
    con.execute("create table if not exists fg_enrich (key text primary key, data text, updated real)")
    return con


def _load(key):
    try:
        with _db() as con:
            row = con.execute("select data from fg_enrich where key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None
    except Exception as e:  # 캐시를 못 읽어도 화면은 그대로
        print(f"[fg_extras] 캐시 읽기 실패: {e!r}"[:200])
        return None


def _save(key, data):
    try:
        with _db() as con:
            con.execute("insert into fg_enrich (key, data, updated) values (?, ?, ?) on conflict(key) do update set data = excluded.data, updated = excluded.updated",
                        (key, json.dumps(data, ensure_ascii=False), time.time()))
    except Exception as e:
        print(f"[fg_extras] 캐시 저장 실패: {e!r}"[:200])


def _work(key, head, people):
    raw = _describe(head, people)
    data = pick((raw or {}).get("items"), head, bool(child_of(people)))
    _save(key, data)
    return data


def _submit(key, head, people):
    with _LOCK:
        now = time.time()
        for k in [k for k, job in _JOBS.items() if job["future"].done() and now - job["started"] > 600]:
            del _JOBS[k]
        job = _JOBS.get(key)
        if job is None:
            job = _JOBS[key] = {"future": _POOL.submit(_work, key, head, people), "started": now}
        return job


def status(scan, people, session, start=True):
    """('off'|'idle'|'pending'|'done'|'failed', {원문 이름: 보강 줄}). 화면을 막지 않으며 예외를 올리지 않는다.

    세션: fg_enrich[key] = {status, items}, fg_enrich_down = True(이 세션에서는 더 부르지 않음).
    """
    try:
        if not enabled() or scan.get("provider") != "foodguide" or not scan.get("items"):
            return "off", {}
        key = cache_key(scan, people)
        records = session.setdefault("fg_enrich", {})
        rec = records.get(key)
        if rec and rec.get("status") in ("done", "failed"):
            return rec["status"], rec.get("items") or {}
        if session.get("fg_enrich_down"):
            return "failed", {}
        job = _JOBS.get(key)
        if job is None:
            cached = _load(key)
            if cached is not None:
                records[key] = {"status": "done", "items": cached}
                return "done", cached
            if time.time() < _DOWN["until"]:
                session["fg_enrich_down"] = True
                return "failed", {}
            if not start:
                return "idle", {}
            job = _submit(key, head_for(scan), _family(people))
            with contextlib.suppress(Exception):  # 아직 진행 중이면 TimeoutError
                job["future"].exception(timeout=FIRST_WAIT)
        future = job["future"]
        if not future.done():
            records[key] = {"status": "pending", "started": job["started"]}
            return "pending", {}
        error = future.exception()
        if error is None:
            records[key] = {"status": "done", "items": future.result()}
            return "done", records[key]["items"]
        print(f"[fg_extras] 설명 보강 실패: {error!r}"[:300])
        records[key] = {"status": "failed", "items": {}}
        if llm_down(error):
            session["fg_enrich_down"] = True
            _DOWN["until"] = max(_DOWN["until"], time.time() + COOLDOWN)
        return "failed", {}
    except Exception as e:  # 보강은 덤이다. 어떤 이유로도 Food Guide 화면을 깨뜨리지 않는다
        print(f"[fg_extras] 상태 확인 실패: {e!r}"[:300])
        return "failed", {}


def extra_for(item, data):
    return data.get(item.get("name_orig")) or {}
