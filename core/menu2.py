"""가족 메뉴판 도우미: 메뉴판 번역 + 사람별 판정 + 맛 닮은꼴 + 메뉴 조합.

Claude는 메뉴판을 읽고 옮기며, 메뉴마다 맛 수치와 사람별 판정을 짐작한다.
알레르기와 못 먹는 것은 코드에서 다시 확인해 반드시 '피하기'로 만든다. 닮은꼴과 조합은 코드로 계산한다.
"""
import base64
import itertools
import json
import re
from pathlib import Path

from . import world

DATA = Path(__file__).parent / "data"
VERDICTS = ["편히", "조심", "피하기"]
CONTAINS = ["견과류", "우유", "달걀", "밀가루", "갑각류", "조개류", "생선", "돼지고기", "소고기", "닭고기", "버섯", "양파", "날것", "술"]
INGREDIENTS = sorted({v[2] for v in world.WORLD.values()} | {"양고기", "오리고기", "콩"})
COOKING = sorted({v[3] for v in world.WORLD.values()})

DEFAULT_PEOPLE = [
    {"id": "me", "name": "나", "relation": "나", "age": "30대", "likes": ["새로운 맛", "향이 진한"], "favorites": ["쌀국수", "토마토 파스타", "비프 스튜", "홍합탕"],
     "avoid": [], "cannot": [], "allergies": [], "child": None, "active": True},
    {"id": "mom", "name": "엄마", "relation": "부모님", "age": "60대", "sex": "female", "likes": ["담백한", "부드러운"], "favorites": ["갈비찜", "생선구이", "홍합탕"],
     "avoid": ["짠 음식"], "cannot": [], "allergies": [], "child": None, "active": True},
    {"id": "dad", "name": "아빠", "relation": "부모님", "age": "60대", "sex": "male", "likes": ["고기"], "favorites": ["스테이크", "제육볶음"],
     "avoid": [], "cannot": ["조개류"], "allergies": [], "child": None, "active": True},
    {"id": "jiwoo", "name": "지우", "relation": "아이", "age": "6~9살", "likes": ["달큰한", "고소한", "바삭한"], "favorites": ["치즈 토스트", "함박스테이크", "감자튀김", "푸딩"],
     "avoid": [], "cannot": [], "allergies": ["견과류"],
     "child": {"new_food": "망설여요", "pick_out": ["채소가 보이면"], "good": ["치즈", "감자", "빵"]}, "active": True},
]


# 앱을 처음 열면 '나' 한 사람, 입맛은 비어 있다 (DEFAULT_PEOPLE은 테스트와 문서용 예시 가족)
START_PEOPLE = [{"id": "me", "name": "나", "relation": "나", "age": "", "likes": [], "favorites": [], "avoid": [], "cannot": [],
                 "allergies": [], "child": None, "active": True}]


def josa(word, a, b):
    """받침이 있으면 a, 없으면 b. '로/으로'는 ㄹ 받침이면 '로'."""
    ch = re.sub(r"[^가-힣]", "", word)[-1:] or "가"
    jong = (ord(ch) - 0xAC00) % 28
    if b == "로":
        return "로" if jong in (0, 8) else "으로"
    return a if jong else b


def subj(name):
    """'나'는 '내가', 나머지는 이/가."""
    return "내가" if name == "나" else name + josa(name, "이", "가")


def describe(p):
    bits = [f"{p['name']} ({p['relation']}, {p['age']})"]
    if p.get("likes"): bits.append("좋아하는 맛: " + ", ".join(p["likes"]))
    if p.get("favorites"): bits.append("즐겨 먹는 음식: " + ", ".join(p["favorites"]))
    if p.get("avoid"): bits.append("피하고 싶은 것: " + ", ".join(p["avoid"]))
    if p.get("cannot"): bits.append("못 먹는 것: " + ", ".join(p["cannot"]))
    if p.get("allergies"): bits.append("알레르기: " + ", ".join(p["allergies"]))
    c = p.get("child")
    if c:
        bits.append(f"아이. 처음 보는 음식: {c.get('new_food')}. 이럴 땐 골라냄: {', '.join(c.get('pick_out') or [])}. 잘 먹는 재료: {', '.join(c.get('good') or [])}")
    return " / ".join(bits)


def _schema(names):
    person = {"type": "object", "properties": {"name": {"type": "string", "enum": names}, "verdict": {"type": "string", "enum": VERDICTS},
                                               "reason": {"type": "string", "description": "편히가 아니면 한 줄 이유. 편히면 빈 문자열"}},
              "required": ["name", "verdict", "reason"], "additionalProperties": False}
    item = {
        "type": "object",
        "properties": {
            "section_orig": {"type": "string"}, "section_ko": {"type": "string", "description": "예: 먼저 먹는 요리, 주요리, 후식"},
            "name_orig": {"type": "string"}, "reading": {"type": "string", "description": "원래 이름을 한글로 소리 나는 대로"},
            "name_ko": {"type": "string", "description": "뜻을 옮긴 한국어 이름"}, "price": {"type": "string"},
            "desc_ko": {"type": "string", "description": "어떤 음식인지 쉬운 한 문장"},
            "glossary": {"type": "array", "items": {"type": "object", "properties": {"term": {"type": "string"}, "meaning": {"type": "string"}},
                                                     "required": ["term", "meaning"], "additionalProperties": False},
                         "description": "메뉴판에 자주 나오지만 사전으로 알기 어려운 요리 용어"},
            "unreadable": {"type": "boolean"},
            "course": {"type": "string", "enum": ["starter", "main", "side", "dessert", "drink"]},
            "contains": {"type": "array", "items": {"type": "string", "enum": CONTAINS}},
            "ingredient": {"type": "string", "enum": INGREDIENTS}, "cooking": {"type": "string", "enum": COOKING},
            **{f"t_{a}": {"type": "number", "description": "0~1"} for a in world.AXES},
            "taste_kw": {"type": "array", "items": {"type": "string"}}, "aroma_kw": {"type": "array", "items": {"type": "string"}, "description": "'~ 향'으로 끝나게"},
            "texture_kw": {"type": "array", "items": {"type": "string"}},
            "kids_only": {"type": "boolean", "description": "어린이 메뉴처럼 아이만 시킬 수 있으면 true"},
            "chef_pick": {"type": "boolean"}, "serve_minutes": {"type": "integer"}, "share_ok": {"type": "boolean"},
            "people": {"type": "array", "items": person},
        },
        "required": ["section_orig", "section_ko", "name_orig", "reading", "name_ko", "price", "desc_ko", "glossary", "unreadable", "course", "contains",
                     "ingredient", "cooking", *[f"t_{a}" for a in world.AXES], "taste_kw", "aroma_kw", "texture_kw", "kids_only", "chef_pick", "serve_minutes", "share_ok", "people"],
        "additionalProperties": False,
    }
    return {"type": "object", "properties": {
        "is_menu": {"type": "boolean", "description": "음식점 메뉴판(요리 이름이나 가격 목록)이면 true. 음식 사진, 풍경, 영수증, 간판만 있으면 false"},
        "restaurant": {"type": "string", "description": "가게 이름. 모르면 빈 문자열"},
        "menu_language": {"type": "string", "description": "예: 프랑스어"}, "language_code": {"type": "string", "description": "BCP 47. 예: fr-FR"},
        "items": {"type": "array", "items": item}},
        "required": ["is_menu", "restaurant", "menu_language", "language_code", "items"], "additionalProperties": False}


SYSTEM = """너는 가족 여행 메뉴판 도우미 '모시고'다. 가족이 해외 식당 메뉴판을 찍었다.
0) 사진이 메뉴판이 아니면 is_menu=false, items는 빈 배열로 둔다.
1) 메뉴판을 순서와 묶음(전채, 주요리, 후식 등) 그대로 읽고 한국어로 옮긴다. 요리 이름은 소리 나는 대로(reading) 두고 뜻(name_ko)을 함께 적는다. 음료는 course=drink로 둔다.
2) 흐려서 못 읽은 줄은 unreadable=true, desc_ko에 '직원에게 물어봐 주세요'.
3) 메뉴마다 맛 수치 8개(t_salty 짠맛, t_sweet 단맛, t_spicy 매운맛, t_sour 신맛, t_umami 감칠맛, t_aroma 향의 세기, t_oily 기름진 정도, t_soft 부드러움)를 일반적인 조리법으로 짐작한다.
4) 사람마다 판정한다. 편히: 그 사람 입맛에 잘 맞음 / 조심: 덜어 내거나 부탁하면 됨, 또는 아이가 처음 보는 음식이라 망설일 수 있음 / 피하기: 알레르기, 못 먹는 것, 입맛과 정반대.
   어린이 메뉴(kids_only)는 아이만 판정한다. 이유는 그 사람 기준 한 줄. 건강이나 병 이야기는 하지 않고 입맛과 취향으로 말한다. 아이는 '버섯이 보여요. 고기만 덜어 주세요'처럼 행동으로 말한다.
5) 말투: 해요체, 짧고 담백하게. 광고나 블로그 같은 말(풍미 가득, 완벽한, 환상적인, 일품, 선사, 어우러져, ~를 추천드립니다), 느낌표, 이모지는 쓰지 않는다.
   맛은 아는 말로 구체적으로 쓴다 (예: '짭짤하고 버터 맛이 진해요').
6) 가족:
{people}"""


def _call(content, people):
    import anthropic

    names = [p["name"] for p in people]
    client = anthropic.Anthropic()
    with client.beta.messages.stream(
        model="claude-opus-5-5",
        max_tokens=32000,
        system=SYSTEM.format(people="\n".join("- " + describe(p) for p in people)),
        messages=[{"role": "user", "content": content}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": _schema(names)}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    ) as stream:
        response = stream.get_final_message()
    if response.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"llm stop_reason={response.stop_reason}")
    return json.loads(next(b.text for b in response.content if b.type == "text"))


def read_menu_text(ocr, people):
    """CLOVA OCR 줄 -> 번역, 설명, 사람별 판정. '(?)'는 OCR이 확신하지 못한 글자다."""
    text = "\n".join(f"{i + 1:02d} | {ln['text']}" + (" [흐림]" if ln["low"] else "") for i, ln in enumerate(ocr["lines"]))
    return _call([{"type": "text", "text": (
        "아래는 메뉴판 사진을 OCR로 읽은 글자예요. 위에서 아래 순서이고 한 줄이 한 행이에요. "
        "OCR이 악센트(é, è, ô 등)를 빠뜨리거나 글자를 틀렸을 수 있으니 요리 이름으로 바로잡아 name_orig에 적어 주세요. "
        "'(?)'나 [흐림]이 붙은 줄은 확실하지 않아요. 요리 이름을 짐작할 수 없으면 unreadable=true로 두세요. "
        "가게 이름, 설명 줄, 가격 줄은 해당 메뉴에 합쳐 주세요.\n\n" + text)}], people)


def read_menu(image_bytes, media_type, people):
    """OCR 키가 없을 때: 사진을 바로 읽는다."""
    return _call([
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64.standard_b64encode(image_bytes).decode()}},
        {"type": "text", "text": "이 메뉴판을 옮기고 가족마다 판정해 주세요."}], people)


def _hard_rules(item, p):
    """알레르기와 못 먹는 것은 Claude 판정과 상관없이 피하기."""
    hits = [a for a in p.get("allergies") or [] if a in item["contains"]]
    if hits:
        return "allergy", hits, f"{'·'.join(hits)} 알레르기가 있어요. {'·'.join(hits)}{josa(hits[-1], '이', '가')} 들어가요"
    hits = [c for c in p.get("cannot") or [] if c in item["contains"] or c == item.get("ingredient")]
    if hits:
        return "cannot", hits, f"{'·'.join(hits)}{josa(hits[-1], '을', '를')} 못 먹어요"
    return None


def enrich(raw, people):
    """Claude 결과에 규칙 판정, 닮은꼴, 맛 지도를 더한다."""
    active = [p for p in people if p.get("active", True)]
    items = []
    for idx, it in enumerate(raw["items"]):
        it = dict(it)
        it["taste"] = [float(it.pop(f"t_{a}")) for a in world.AXES]
        given = {g["name"]: g for g in it.pop("people", [])}
        per = []
        for p in active if not it.get("kids_only") else [p for p in active if p.get("child")]:
            g = given.get(p["name"], {"verdict": "조심", "reason": "판정이 없어요. 직원에게 확인해 주세요"})
            v, reason, rule = g["verdict"], g["reason"], None
            forced = _hard_rules(it, p)
            if forced:
                v, reason, rule = "피하기", forced[2], {"kind": forced[0], "what": forced[1]}
            m = world.best_match(it, p.get("favorites") or [])
            per.append({"id": p["id"], "name": p["name"], "verdict": v, "reason": "" if v == "편히" else reason, "rule": rule, "match": m})
        it["per"] = per
        if not per:
            continue
        ok = sum(1 for x in per if x["verdict"] == "편히")
        bad = sum(1 for x in per if x["verdict"] == "피하기")
        it["group"] = "all" if ok == len(per) else ("none" if bad == len(per) else "some")
        best = max((x for x in per if x["match"]), key=lambda x: x["match"]["score"], default=None)
        if best:
            fans = [x["name"] for x in per if x["match"] and x["match"]["food"] == best["match"]["food"]]
            who = fans[0] if len(fans) == 1 else (f"{fans[0]}{josa(fans[0], '과', '와')} {fans[1]}" if len(fans) == 2 else f"{fans[0]} 등 {len(fans)}명")
            it["headline"] = f"{subj(who)} 좋아하는 {best['match']['food']}{josa(best['match']['food'], '과', '와')} {best['match']['level']}"
        else:
            it["headline"] = None
        it["map"] = world.taste_map(it, [dict(x["match"], who=[x["name"]]) for x in per if x["match"]])
        # 순번을 붙여 항상 겹치지 않게 (한글, 일본어 이름은 영문자가 없어서 '750g'처럼 같은 값이 될 수 있다)
        slug = re.sub(r"[^a-z0-9]+", "-", it["name_orig"].lower()).strip("-")[:30]
        it["id"] = f"{slug or 'item'}-{idx}"
        items.append(it)
    order = {"all": 0, "some": 1, "none": 2}
    return {**{k: v for k, v in raw.items() if k != "items"}, "items": items,
            "judged": sorted([i for i in items if i["course"] != "drink" and not i["unreadable"]], key=lambda i: (order[i["group"]], -sum(x["verdict"] == "편히" for x in i["per"]))),
            "people": [{"id": p["id"], "name": p["name"]} for p in active]}


def demo(people):
    raw = json.loads((DATA / "demo_paris.json").read_text("utf-8"))
    names = {p["name"] for p in people}
    for it in raw["items"]:  # 데모 결과에 없는 사람은 '조심'으로
        it["people"] = [g for g in it["people"] if g["name"] in names]
    return enrich(raw, people)


# ---------- 메뉴 조합 ----------
SCORE = {"편히": 1.0, "조심": 0.55}


def _score(item, x):
    if x["verdict"] == "피하기":
        return None
    s = SCORE[x["verdict"]]
    if x["match"]:
        s += 0.25 * x["match"]["bars"] + 0.2 * x["match"]["score"]  # 같은 단계면 더 닮은 쪽
    return round(s, 3)


def combos(scan, people):
    """사람마다 내 메뉴 하나 + 다 같이 나눠 먹을 후식. 가장 덜 맞는 사람의 점수가 가장 높은 조합을 먼저."""
    judged = [i for i in scan["judged"]]
    mains = [i for i in judged if i["course"] in ("main", "starter")]
    desserts = [i for i in judged if i["course"] == "dessert"]
    ids = [p["id"] for p in scan["people"]]

    explore = set()

    def cand(pid, pool, k=6):
        out = []
        for it in pool:
            x = next((x for x in it["per"] if x["id"] == pid), None)
            s = _score(it, x) if x else None
            if s is not None and pid in explore:  # 새로운 맛을 좋아하는 사람은 처음 보는 맛을 먼저
                s = SCORE[x["verdict"]] + (0.6 if not x["match"] else 0.1 if x["match"]["bars"] == 1 else 0)
            if s is not None:
                out.append((s, it, x))
        return sorted(out, key=lambda t: -t[0])[:k]

    def best_assign(pool):
        cands = [cand(pid, pool) for pid in ids]
        if any(not c for c in cands):
            return None
        best = None
        for pick in itertools.product(*cands):
            names = [p[1]["id"] for p in pick]
            key = (round(min(p[0] for p in pick), 1), len(set(names)), sum(p[0] for p in pick))
            if best is None or key > best[0]:
                best = (key, pick)
        return best[1]

    def shared_dessert():
        scored = []
        for it in desserts:
            vs = [x["verdict"] for x in it["per"]]
            if "피하기" in vs:
                continue
            scored.append((vs.count("편히"), it))
        return max(scored, key=lambda t: t[0])[1] if scored else None

    def package(kind, pool, extra_share=None, title="", note=""):
        pick = best_assign(pool)
        if not pick:
            return None
        plates = [{"person": next(p for p in scan["people"] if p["id"] == pid), "item": _brief(it), "verdict": x["verdict"],
                   "match": x["match"], "reason": x["reason"],
                   "alts": [{"item": _brief(a), "verdict": ax["verdict"], "match": ax["match"], "reason": ax["reason"]}
                            for _, a, ax in cand(pid, pool, 5) if a is not it][:3]}
                  for pid, (s, it, x) in zip(ids, pick)]
        share = [d for d in [extra_share, shared_dessert()] if d]
        chosen = [p[1] for p in pick] + share
        ok = sum(1 for p in plates if p["verdict"] == "편히")
        price = sum(_price(i["price"]) * (len(ids) // 2 if i in share and i["course"] == "dessert" else 1) for i in chosen)
        return {"kind": kind, "title": title, "note": note, "plates": plates,
                "share": [{"item": _brief(d), "count": max(1, len(ids) // 2) if d["course"] == "dessert" else 1,
                           "who": [x["name"] for x in d["per"] if x["verdict"] != "피하기"]} for d in share],
                "summary": {"happy": ok, "people": len(ids), "minutes": max(i["serve_minutes"] for i in chosen),
                            "price": round(price, 2) if price else None},
                "why": _why(plates, scan)}

    out = [package("all", mains, title="모두 만족", note=f"이렇게 시키면 {len(ids)}명 모두 맛있게 먹어요")]
    local = next((i for i in mains if i.get("chef_pick")), None) or next((i for i in mains if not any(x["match"] for x in i["per"])), None)
    if local:
        explore.update(p["id"] for p in people if p.get("active", True) and "새로운 맛" in (p.get("likes") or []))
        out.append(package("local", [m for m in mains if m is not local], extra_share=local, title="현지 맛 도전",
                           note=f"{local['name_ko']}{josa(local['name_ko'], '을', '를')} 다 같이 맛보고, 새로운 맛을 좋아하는 사람은 처음 보는 메뉴로"))
    explore.clear()
    fast = [m for m in mains if m["serve_minutes"] <= 15]
    out.append(package("fast", fast or mains, title="빨리 나와요", note="15분 안에 나오는 메뉴로 골랐어요"))
    return [o for o in out if o]


def _brief(i):
    return {k: i[k] for k in ("id", "name_orig", "reading", "name_ko", "price", "course", "serve_minutes")}


def _price(p):
    m = re.search(r"\d+(?:[.,]\d+)?", p or "")
    return float(m.group().replace(",", ".")) if m else 0.0


def _why(plates, scan):
    lines = []
    for pl in plates:
        name, it = pl["person"]["name"], pl["item"]["name_ko"]
        if pl["match"]:
            lines.append(f"{name}{josa(name, '은', '는')} 좋아하는 {pl['match']['food']}{josa(pl['match']['food'], '과', '와')} 닮은 {it}")
        else:
            lines.append(f"{name}{josa(name, '은', '는')} 입맛에 맞는 {it}")
    text = ", ".join(lines) + josa(lines[-1], "", "로") + " 골랐어요."
    blocked = {}
    for i in scan["judged"]:
        for x in i["per"]:
            if x.get("rule"):
                what = "·".join(x["rule"]["what"])
                blocked[(x["name"], what)] = (f"{x['name']}의 {what} 알레르기" if x["rule"]["kind"] == "allergy"
                                              else f"{subj(x['name'])} 못 먹는 {what}").replace("나의", "내")
    if blocked:
        text += " " + ", ".join(blocked.values()) + "에 걸리는 메뉴는 그 사람 후보에서 뺐어요."
    return text
