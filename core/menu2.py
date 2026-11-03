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
# 아이 접시로 바꾸는 부탁 (order.REQUEST_KEYS 중 한 접시에 쓰는 것만)
KID_REQS = ["맵지 않게", "소스는 따로", "버섯 빼고", "양파 빼고", "잘 익혀 주세요", "덜 짜게", "아이용 작은 접시"]
SPICY = world.AXES.index("spicy")

DEFAULT_PEOPLE = [
    {"id": "me", "name": "나", "relation": "나", "age": "30대", "likes": ["새로운 맛", "향이 진한"], "favorites": ["쌀국수", "토마토 파스타", "비프 스튜", "홍합탕"],
     "avoid": [], "cannot": [], "allergies": [], "child": None, "active": True},
    {"id": "mom", "name": "엄마", "relation": "부모님", "age": "60대", "sex": "female", "likes": ["담백한", "부드러운"], "favorites": ["갈비찜", "생선구이", "홍합탕"],
     "avoid": ["짠 음식"], "cannot": [], "allergies": [], "child": None, "active": True},
    {"id": "dad", "name": "아빠", "relation": "부모님", "age": "60대", "sex": "male", "likes": ["고기"], "favorites": ["스테이크", "제육볶음"],
     "avoid": [], "cannot": ["조개류"], "allergies": [], "child": None, "active": True},
    {"id": "jiwoo", "name": "아이", "relation": "아이", "age": "6~9살", "likes": ["달큰한", "고소한", "바삭한"], "favorites": ["치즈 토스트", "함박스테이크", "감자튀김", "푸딩"],
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
    pair = {"type": "object", "properties": {"orig": {"type": "string", "description": "메뉴판 언어로 짧게. 예: À point"},
                                             "ko": {"type": "string", "description": "예: 미디엄(속이 분홍색이에요)"}},
            "required": ["orig", "ko"], "additionalProperties": False}
    ask = {"type": "object", "properties": {"q_orig": {"type": "string", "description": "직원이 실제로 하는 말, 메뉴판 언어로. 예: Quelle cuisson ?"},
                                            "q_ko": {"type": "string", "description": "직원 말을 그대로 옮긴 뜻. 예: 굽기는 어떻게 해 드릴까요?"},
                                            "answers": {"type": "array", "items": pair, "description": "그 질문에 바로 고르는 대답 2~4개"}},
           "required": ["q_orig", "q_ko", "answers"], "additionalProperties": False}
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
            "taste_line": {"type": "string", "description": "어떤 맛인지 한 줄. 예: 신맛이 또렷하고 매콤한 새우 수프예요"},
            "ko_compare": {"type": "string", "description": "한국 음식에 빗대어 한 줄. 예: 매운 해물탕보다 신맛과 허브 향이 훨씬 강해요"},
            "imagine": {"type": "string", "description": "먹을 때 떠올릴 맛 포인트 2~3개를 쉼표로. 예: 레몬그라스 향, 깔끔한 국물, 입안에 남는 새콤함"},
            "good_for": {"type": "array", "items": {"type": "string"}, "description": "이런 분께 맞아요 1~2개, '~분'으로 끝나게. 예: 새콤한 국물이 궁금한 분"},
            "local_popular": {"type": "boolean", "description": "그 나라를 대표하는 요리면 true. 메뉴판 전체에서 2~3개까지만"},
            "kids_only": {"type": "boolean", "description": "어린이 메뉴처럼 아이만 시킬 수 있으면 true"},
            "chef_pick": {"type": "boolean"}, "serve_minutes": {"type": "integer"}, "share_ok": {"type": "boolean"},
            "people": {"type": "array", "items": person},
            "staff_asks": {"type": "array", "items": ask, "description": "이 요리를 시키면 직원이 거의 꼭 되묻는 질문. 대부분 빈 배열, 많아야 2개"},
            "kid_tweaks": {"type": "array", "items": {"type": "string", "enum": KID_REQS},
                           "description": "가족에 아이가 있을 때만. 아이가 먹게 주문할 때 부탁할 것 0~3개. 빼면 요리가 안 되는 재료는 넣지 않는다"},
            "kid_tip": {"type": "string", "description": "가족에 아이가 있을 때만. 아이 접시에 덜어 주는 법 한 문장, kid_tweaks와 겹치지 않게. 예: 고기와 감자만 덜어 주세요. 아니면 빈 문자열"},
        },
        "required": ["section_orig", "section_ko", "name_orig", "reading", "name_ko", "price", "desc_ko", "glossary", "unreadable", "course", "contains",
                     "ingredient", "cooking", *[f"t_{a}" for a in world.AXES], "taste_kw", "aroma_kw", "texture_kw",
                     "taste_line", "ko_compare", "imagine", "good_for", "local_popular", "kids_only", "chef_pick", "serve_minutes", "share_ok", "people", "staff_asks", "kid_tweaks", "kid_tip"],
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
   아이가 있으면 kid_tweaks와 kid_tip을 채우고, 아이 판정이 피하기면 비운다.
   어린이 메뉴(kids_only)는 아이만 판정한다. 이유는 그 사람 기준 한 줄. 건강이나 병 이야기는 하지 않고 입맛과 취향으로 말한다. 아이는 '버섯이 보여요. 고기만 덜어 주세요'처럼 행동으로 말한다.
5) 말투: 해요체, 짧고 담백하게. 광고나 블로그 같은 말(풍미 가득, 완벽한, 환상적인, 일품, 선사, 어우러져, ~를 추천드립니다), 느낌표, 이모지는 쓰지 않는다.
   맛은 아는 말로 구체적으로 쓴다 (예: '짭짤하고 버터 맛이 진해요').
   ko_compare는 한국 사람이 아는 음식 하나에 빗대고 무엇이 다른지 말한다. 음료는 taste_line만 쓰고 나머지는 비워 둔다.
   staff_asks는 이 요리를 시키면 직원이 거의 꼭 되묻는 선택만 (스테이크 굽기, 곁들임이나 소스 고르기, 매운 정도, 크기, 맛 고르기). 대부분 빈 배열.
   answers는 그 질문에 고르는 대답만 넣고 부탁이나 되묻는 말(빼 주세요, 뭐예요?)은 넣지 않는다. 세트 메뉴처럼 메뉴판에서 다시 고르는 것은 넣지 않는다.
6) 가족:
{people}"""


LIST_SCHEMA = {"type": "object", "properties": {
    "is_menu": {"type": "boolean", "description": "음식점 메뉴판(요리 이름이나 가격 목록)이면 true. 음식 사진, 풍경, 영수증, 간판만 있으면 false"},
    "restaurant": {"type": "string", "description": "가게 이름. 모르면 빈 문자열"},
    "menu_language": {"type": "string", "description": "예: 프랑스어"}, "language_code": {"type": "string", "description": "BCP 47. 예: fr-FR"},
    "lines": {"type": "array", "items": {"type": "object", "properties": {
        "section_orig": {"type": "string"}, "name_orig": {"type": "string"}, "price": {"type": "string"},
        "note": {"type": "string", "description": "메뉴판에 이 메뉴 아래 적힌 설명(원문 그대로, 없으면 빈 문자열)"}},
        "required": ["section_orig", "name_orig", "price", "note"], "additionalProperties": False}}},
    "required": ["is_menu", "restaurant", "menu_language", "language_code", "lines"], "additionalProperties": False}
LIST_SYSTEM = """메뉴판에 적힌 메뉴를 위에서 아래, 왼쪽에서 오른쪽 순서대로 빠짐없이 적는다. 음료도 적는다.
요리 이름은 원래 글자 그대로(악센트, 한자, 가나 포함) 적고, 번역하지 않는다. 흐려서 못 읽은 줄은 name_orig에 읽은 만큼 적는다.
메뉴판이 아니면 is_menu=false, lines는 빈 배열."""
CHUNK = 6         # 한 번에 설명을 만드는 메뉴 수 (나눠서 동시에 만든다)
LIST_MODEL = "claude-opus-5-5"     # 1단계: 메뉴 이름 빠짐없이 (사진 읽기는 가장 정확한 모델로)
DESC_MODEL = "claude-sonnet-5-5"   # 2단계: 글자만 보고 설명과 판정 (빠른 모델)
MAX_ITEMS = 60    # 너무 긴 메뉴판은 앞쪽부터 이만큼만


def _client():
    import anthropic

    return anthropic.Anthropic()


def _stream(system, content, schema, max_tokens, model=LIST_MODEL):
    with _client().beta.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    ) as stream:
        response = stream.get_final_message()
    if response.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"llm stop_reason={response.stop_reason}")
    return json.loads(next(b.text for b in response.content if b.type == "text"))


def _read(source, people, progress=None):
    """1단계: 메뉴 이름 목록만 빠르게 뽑는다. 2단계: 12개씩 나눠 동시에 번역, 설명, 판정을 만든다.
    메뉴가 많은 메뉴판(수십 개)도 출력 한도에 걸리지 않고, 걸리는 시간도 메뉴 수와 덜 상관있다."""
    from concurrent.futures import ThreadPoolExecutor

    say = progress or (lambda *_: None)
    say("메뉴 이름을 찾는 중이에요")
    head = _stream(LIST_SYSTEM, source + [{"type": "text", "text": "이 메뉴판의 메뉴를 순서대로 적어 주세요."}], LIST_SCHEMA, 16000, LIST_MODEL)
    lines = head.get("lines") or []
    if not head.get("is_menu", True) or not lines:
        return {**{k: head.get(k, "") for k in ("restaurant", "menu_language", "language_code")}, "is_menu": False, "items": []}
    cut = len(lines) > MAX_ITEMS
    lines = lines[:MAX_ITEMS]
    groups = [lines[i:i + CHUNK] for i in range(0, len(lines), CHUNK)]
    say(f"메뉴 {len(lines)}개를 찾았어요. 무슨 맛인지 적는 중이에요")
    system = SYSTEM.format(people="\n".join("- " + describe(p) for p in people))
    schema = _schema([p["name"] for p in people])

    def one(group):
        listing = "\n".join(f"{i + 1:02d} | {g['section_orig']} | {g['name_orig']} | {g['price']}" + (f" | {g['note']}" if g["note"] else "")
                            for i, g in enumerate(group))
        ask = [{"type": "text", "text": f"{lang} 메뉴판에서 읽은 아래 {len(group)}개 메뉴만, 이 순서 그대로 하나씩 옮기고 판정해 주세요. "
                                         f"다른 메뉴는 넣지 마세요.\n(번호 | 묶음 | 이름 | 가격 | 메뉴판 설명)\n{listing}"}]
        for _ in range(2):  # 한 번 실패하면 한 번 더
            try:
                return _stream(system, ask, schema, 8000, DESC_MODEL).get("items") or []
            except Exception as e:  # 한 번 더 해 보고, 그래도 안 되면 이 묶음은 이름만 남긴다
                err = e
        print(f"[menu2] 묶음 실패: {err!r}")
        return [_bare(g) for g in group]

    lang = head.get("menu_language") or ""
    with ThreadPoolExecutor(min(10, len(groups))) as pool:
        parts = list(pool.map(one, groups))
    items = [it for part in parts for it in part]
    out = {"is_menu": True, "restaurant": head.get("restaurant", ""), "menu_language": head.get("menu_language", ""),
           "language_code": head.get("language_code", ""), "items": items}
    if cut:
        out["note"] = f"메뉴가 많아서 앞쪽 {MAX_ITEMS}개만 옮겼어요. 나머지는 해당 부분을 가까이서 다시 찍어 주세요."
    return out


def _bare(g):
    """설명을 만들지 못한 메뉴: 이름과 가격만 보여 준다."""
    return {"section_orig": g["section_orig"], "section_ko": g["section_orig"], "name_orig": g["name_orig"], "reading": "", "name_ko": g["name_orig"],
            "price": g["price"], "desc_ko": "설명을 만들지 못했어요. 직원에게 물어봐 주세요.", "glossary": [], "unreadable": True, "course": "main",
            "contains": [], "ingredient": INGREDIENTS[0], "cooking": COOKING[0], **{f"t_{a}": 0.5 for a in world.AXES},
            "taste_kw": [], "aroma_kw": [], "texture_kw": [], "taste_line": "", "ko_compare": "", "imagine": "", "good_for": [], "local_popular": False, "kids_only": False, "chef_pick": False, "serve_minutes": 15, "share_ok": False, "people": [], "staff_asks": [], "kid_tweaks": [], "kid_tip": ""}


def read_menu_text(ocr, people, progress=None):
    """CLOVA OCR 줄 -> 번역, 설명, 사람별 판정. '(?)'는 OCR이 확신하지 못한 글자다."""
    text = "\n".join(f"{i + 1:02d} | {ln['text']}" + (" [흐림]" if ln["low"] else "") for i, ln in enumerate(ocr["lines"]))
    return _read([{"type": "text", "text": (
        "아래는 메뉴판 사진을 OCR로 읽은 글자예요. 위에서 아래 순서이고 한 줄이 한 행이에요. "
        "OCR이 악센트(é, è, ô 등)를 빠뜨리거나 글자를 틀렸을 수 있으니 요리 이름으로 바로잡아 주세요. "
        "'(?)'나 [흐림]이 붙은 줄은 확실하지 않아요. 가게 이름, 설명 줄, 가격 줄은 해당 메뉴에 합쳐 주세요.\n\n" + text)}], people, progress)


def read_menu(image_bytes, media_type, people, progress=None):
    """OCR 키가 없을 때: 사진을 바로 읽는다."""
    return _read([{"type": "image", "source": {"type": "base64", "media_type": media_type,
                                                "data": base64.standard_b64encode(image_bytes).decode()}}], people, progress)


def _hard_rules(item, p):
    """알레르기와 못 먹는 것은 Claude 판정과 상관없이 피하기."""
    hits = [a for a in p.get("allergies") or [] if a in item["contains"]]
    if hits:
        return "allergy", hits, f"{'·'.join(hits)} 알레르기가 있어요. {'·'.join(hits)}{josa(hits[-1], '이', '가')} 들어가요"
    hits = [c for c in p.get("cannot") or [] if c in item["contains"] or c == item.get("ingredient")]
    if hits:
        return "cannot", hits, f"{'·'.join(hits)}{josa(hits[-1], '을', '를')} 못 먹어요"
    return None


def kid_tweaks(item, child):
    """아이 접시로 바꾸는 부탁. Claude가 고른 것에 매운맛 규칙을 더한다.
    예전에 읽은 메뉴(kid_tweaks 없음)는 재료와 아이가 골라내는 것으로 짐작한다."""
    if not child:
        return []
    c = child.get("child") or {}
    given = item.get("kid_tweaks")
    out = [k for k in given or [] if k in KID_REQS]
    contains = item.get("contains") or []
    if given is None and "채소가 보이면" in (c.get("pick_out") or []):  # 예전 결과(필드 없음)는 재료로 짐작
        out += [f"{w} 빼고" for w in ("버섯", "양파") if w in contains and w not in item.get("name_ko", "")]
    taste = item.get("taste")
    spicy = taste[SPICY] if taste else float(item.get("t_spicy") or 0)
    if spicy > 0.4 or (spicy > 0.2 and "매우면" in (c.get("pick_out") or [])):
        out.append("맵지 않게")
    return [k for k in KID_REQS if k in out]


def enrich(raw, people):
    """Claude 결과에 규칙 판정, 닮은꼴, 맛 지도를 더한다."""
    active = [p for p in people if p.get("active", True)]
    child = next((p for p in active if p.get("child")), None)
    items = []
    for idx, it in enumerate(raw["items"]):
        it = dict(it)
        it["taste"] = [float(it.pop(f"t_{a}")) for a in world.AXES]
        it["staff_asks"] = [dict(q, answers=q["answers"][:4]) for q in it.get("staff_asks") or [] if len(q.get("answers") or []) >= 2][:2]
        it["kid_tweaks"] = kid_tweaks(it, child) if it["course"] != "drink" else []
        it["kid_tip"] = (it.get("kid_tip") or "").strip() if child and it["course"] != "drink" else ""
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
    pops = [i for i in items if i.get("local_popular") and i["course"] != "drink"]  # 나눠서 만들면 많아지므로 3개까지만
    for i in items:
        i["local_popular"] = i in pops[:3]
    order = {"all": 0, "some": 1, "none": 2}
    return {**{k: v for k, v in raw.items() if k != "items"}, "items": items,
            "judged": sorted([i for i in items if i["course"] != "drink" and not i["unreadable"]], key=lambda i: (order[i["group"]], -sum(x["verdict"] == "편히" for x in i["per"]))),
            "people": [{"id": p["id"], "name": p["name"]} for p in active]}


def similar_top(scan, n=3):
    """각자 좋아하는 음식과 많이 닮은 메뉴 n개. 되도록 서로 다른 사람 몫으로, 같은 메뉴는 한 번만.

    돌려주는 것: [{item, person: {id, name}, match, who: [같은 음식으로 닮은 사람들], line}]
    """
    cands = []
    for it in scan["items"]:
        if it["course"] == "drink" or it.get("unreadable"):
            continue
        for x in it.get("per") or []:
            m = x.get("match")
            if m and m["bars"] >= 2 and x["verdict"] != "피하기":
                cands.append((it, x))
    cands.sort(key=lambda c: (-c[1]["match"]["bars"], c[1]["verdict"] != "편히", -c[1]["match"]["score"]))
    picked, dishes, persons = [], set(), set()
    for spread in (True, False):  # 먼저 사람마다 하나씩, 자리가 남으면 남은 것 중 센 순서로
        for it, x in cands:
            if len(picked) >= n:
                break
            if it["id"] in dishes or (spread and x["id"] in persons):
                continue
            picked.append((it, x))
            dishes.add(it["id"])
            persons.add(x["id"])
    picked.sort(key=lambda c: (-c[1]["match"]["bars"], c[1]["verdict"] != "편히", -c[1]["match"]["score"]))
    out = []
    for it, x in picked:
        m = x["match"]
        who = [y["name"] for y in it["per"] if y.get("match") and y["match"]["food"] == m["food"] and y["match"]["bars"] >= 2 and y["verdict"] != "피하기"]
        names = who[0] if len(who) == 1 else (f"{who[0]}{josa(who[0], '과', '와')} {who[1]}" if len(who) == 2 else f"{who[0]} 등 {len(who)}명")
        out.append({"item": it, "person": {"id": x["id"], "name": x["name"]}, "verdict": x["verdict"], "match": m, "who": who,
                    "line": f"{subj(names)} 좋아하는 {m['food']}{josa(m['food'], '과', '와')} {m['level']}"})
    return out


def demo(people):
    raw = json.loads((DATA / "demo_paris.json").read_text("utf-8"))
    names = {p["name"] for p in people}
    for it in raw["items"]:  # 데모 결과에 없는 사람은 '조심'으로
        it["people"] = [g for g in it["people"] if g["name"] in names]
    return enrich(raw, people)


# ---------- 아이가 안 먹을 때 ----------
PLAIN = {"굽기", "튀기기", "삶기", "찌기", "부치기"}
MEAT = {"소고기", "닭고기", "돼지고기", "양고기", "오리고기"}


def kid_backup(scan, child, exclude=None):
    """아이가 안 먹을 때 대신 시킬 메뉴 하나: 아이 판정이 편히이고, 잘 먹는 재료가 보이고,
    맵지 않고 익숙하게 익힌 것. 어린이 메뉴가 있으면 먼저. 없으면 None."""
    if not child:
        return None
    good = (child.get("child") or {}).get("good") or []
    best = None
    for it in scan["judged"]:
        if it["id"] == exclude or it["course"] not in ("main", "starter", "side"):
            continue
        x = next((x for x in it["per"] if x["id"] == child["id"]), None)
        if not x or x["verdict"] != "편히" or it["cooking"] == "날것" or "날것" in it["contains"] or it["taste"][SPICY] > 0.3:
            continue
        text = f'{it["name_ko"]} {it.get("desc_ko", "")}'
        hits = [g for g in good if g in text or g == it.get("ingredient") or (g == "고기" and it.get("ingredient") in MEAT)
                or (g == "달걀" and "달걀" in it["contains"])]
        score = (2 if it.get("kids_only") else 0) + len(hits) + (0.5 if it["cooking"] in PLAIN else 0) \
            - it["taste"][SPICY] - 0.3 * it["taste"][world.AXES.index("aroma")] + (0.2 * x["match"]["bars"] if x["match"] else 0)
        if best is None or score > best[0]:
            best = (score, it, hits)
    if not best:
        return None
    _, it, hits = best
    return {**_brief(it), "kids_only": bool(it.get("kids_only")), "good": hits}


# ---------- 메뉴 조합 ----------
SCORE = {"편히": 1.0, "조심": 0.55}


def apply_feedback(scan, fb):
    """먹어 본 사람들의 설문(reviews.feedback)을 메뉴에 붙이고, 같은 묶음 안에서 반응이 좋은 메뉴를 앞으로."""
    for it in scan["items"]:
        f = fb.get(it["name_orig"])
        it["fb"] = f
        it["boost"] = f["boost"] if f else 0.0
    order = {"all": 0, "some": 1, "none": 2}
    scan["judged"].sort(key=lambda i: (order[i["group"]], -(sum(x["verdict"] == "편히" for x in i["per"]) + 2 * i.get("boost", 0))))
    return scan


def _score(item, x):
    if x["verdict"] == "피하기":
        return None
    s = SCORE[x["verdict"]] + item.get("boost", 0)  # 먹어 본 사람들 반응
    if x["match"]:
        s += 0.25 * x["match"]["bars"] + 0.2 * x["match"]["score"]  # 같은 단계면 더 닮은 쪽
    return round(s, 3)


def combos(scan, people):
    """사람마다 내 메뉴 하나 + 다 같이 나눠 먹을 후식. 가장 덜 맞는 사람의 점수가 가장 높은 조합을 먼저."""
    judged = scan["judged"]
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
                "why": _why(plates, scan) + (" 먹어 본 사람들이 다시 추천받고 싶다고 한 메뉴를 앞에 두었어요."
                                             if any(it.get("boost", 0) > 0.03 for _, it, _ in pick) else ""),
                "why_lines": _why_lines(plates, scan, any(it.get("boost", 0) > 0.03 for _, it, _ in pick))}

    out = [package("all", mains, title="모두 만족", note=f"{len(ids)}명 모두 입에 맞는 조합")]
    local = next((i for i in mains if i.get("chef_pick")), None) or next((i for i in mains if not any(x["match"] for x in i["per"])), None)
    if local:
        explore.update(p["id"] for p in people if p.get("active", True) and "새로운 맛" in (p.get("likes") or []))
        out.append(package("local", [m for m in mains if m is not local], extra_share=local, title="현지 맛 도전",
                           note=f"현지 메뉴 {local['name_ko']} 하나를 같이 나눠 먹는 조합"))
    explore.clear()
    fast = [m for m in mains if m["serve_minutes"] <= 15]
    out.append(package("fast", fast or mains, title="빨리 나와요", note="15분 안에 나오는 메뉴만"))
    return [o for o in out if o]


def _brief(i):
    return {k: i[k] for k in ("id", "name_orig", "reading", "name_ko", "price", "course", "serve_minutes")}


def _price(p):
    m = re.search(r"\d+(?:[.,]\d+)?", p or "")
    return float(m.group().replace(",", ".")) if m else 0.0


def _why_lines(plates, scan, boosted=False):
    """고른 이유를 사람마다 한 줄씩 (화면용)."""
    out = []
    for pl in plates:
        m = pl["match"]
        out.append((pl["person"]["name"], pl["item"]["name_ko"], f"{m['food']}{josa(m['food'], '과', '와')} 닮음" if m else "입맛에 맞음"))
    blocked = []
    for i in scan["judged"]:
        for x in i["per"]:
            r = x.get("rule")
            if r:
                t = f"{x['name']}: {'·'.join(r['what'])} {'알레르기' if r['kind'] == 'allergy' else '못 먹음'}"
                if t not in blocked:
                    blocked.append(t)
    return {"plates": out, "blocked": blocked, "boosted": boosted}


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
