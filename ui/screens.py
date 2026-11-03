"""화면들. 휴대폰 한 칸 기준."""
import base64
import json
import os

import streamlit as st
import streamlit.components.v1 as components

from core import freemeal, menu2, nearby, ocr, order, reviews, store, world
from .common import ALLERGENS, E, VCLASS, VMARK, chips, go, josa, level, marks, md, momo, nav

RELATIONS = ["나", "부모님", "아이", "배우자", "친구", "가족"]
AGES = ["3~5살", "6~9살", "10대", "20대", "30대", "40대", "50대", "60대", "70대", "80대 이상"]
LIKES = ["담백한", "부드러운", "고기", "국물", "달큰한", "고소한", "바삭한", "매콤한", "새콤한", "향이 진한", "새로운 맛"]
AVOID = ["짠 음식", "매운 음식", "기름진 음식", "향이 강한 것", "단 음식", "질긴 것"]
CANNOT = ["돼지고기", "소고기", "조개류", "갑각류", "생선", "날것", "술", "버섯", "양파"]
ALLERGY = ["견과류", "우유", "달걀", "밀가루", "갑각류", "조개류", "생선"]
NEW_FOOD = ["잘 먹어요", "망설여요", "싫어해요"]
PICK_OUT = ["채소가 보이면", "매우면", "향이 세면", "모양이 낯설면"]
GOOD = ["치즈", "감자", "빵", "밥", "면", "고기", "달걀"]
DEMO_IMG = menu2.DATA / "paris_menu.jpg"
EXAMPLE_IDS = {"mom", "dad", "jiwoo"}  # 예전 버전이 넣어 두던 예시 가족


def clean_examples(people):
    """예전 버전이 넣어 둔 예시 가족과 예시 입맛을 손대지 않았으면 지운다 (고친 사람은 그대로 둔다)."""
    base = {p["id"]: {k: v for k, v in p.items() if k != "active"} for p in menu2.DEFAULT_PEOPLE}
    same = lambda p: {k: v for k, v in p.items() if k != "active"} == base.get(p["id"])
    out = []
    for p in people:
        if p["id"] in EXAMPLE_IDS and same(p):
            continue
        if p["id"] == "me" and same(p):
            p = dict(menu2.START_PEOPLE[0], active=p.get("active", True))
        out.append(p)
    return out or [dict(menu2.START_PEOPLE[0])]
NICK_REL = {"엄마": "부모님", "아빠": "부모님", "어머니": "부모님", "아버지": "부모님", "어머님": "부모님", "아버님": "부모님",
            "할머니": "가족", "할아버지": "가족", "동생": "가족", "형": "가족", "누나": "가족", "오빠": "가족", "언니": "가족",
            "아들": "아이", "딸": "아이", "아이": "아이", "남편": "배우자", "아내": "배우자", "와이프": "배우자", "친구": "친구"}


def active():
    return [p for p in st.session_state.people if p.get("active", True)]


def save_people(people):
    st.session_state.people = people
    store.save(st.session_state.code, people)
    if st.session_state.get("scan_raw"):
        rejudge()


def rejudge():
    act = active()
    scan = menu2.enrich(st.session_state.scan_raw, act)
    scan["combos"] = menu2.combos(scan, act)
    st.session_state.scan = scan
    st.session_state.picks = {}


def _set(**kw):
    for k, v in kw.items():
        st.session_state[k] = v


def _swap(key, pid, opts):
    """접시 바꾸기: 고르는 즉시 반영해서 위의 접시 목록과 금액이 바로 바뀌게."""
    picks = st.session_state.setdefault("picks", {})
    i = st.session_state.get(key, 0)
    if i == 0:
        picks.pop(pid, None)
    else:
        o = opts[i]
        picks[pid] = {"item": o["item"], "verdict": o["verdict"], "match": o["match"], "reason": o["reason"]}


def title(h, sub=None):
    md(f'<div class="h1">{E(h)}</div>' + (f'<div class="sub">{E(sub)}</div>' if sub else ""))


# ---------------- 시작 ----------------
def start():
    md(f'<div class="hero">{momo(84)}<div class="h1">처음 보는 메뉴판,<br>무슨 맛인지 미리 그려 드려요</div>'
       '<div class="sub">메뉴판을 찍으면 우리말로 옮기고,<br>같이 먹는 사람마다 아는 음식에 빗대어 알려 드려요.</div></div>')
    s = st.session_state
    md('<div class="sec">오늘 누구랑 먹어요?</div>')
    with st.container(key="choices"):
        st.button("**혼자**  \n내 입맛 기준으로 봐요", type="primary" if s.get("alone") is True else "secondary", width="stretch", on_click=_set, kwargs={"alone": True})
        st.button("**여럿이**  \n가족, 친구마다 따로 봐요. 아이 입맛도요", type="primary" if s.get("alone") is False else "secondary", width="stretch", on_click=_set, kwargs={"alone": False})
        md('<div class="sec">어떤 여행이에요?</div>')
        st.button("**자유여행**  \n한식당 없는 동네에서도 고를 수 있게", type="primary" if s.get("trip") == "free" else "secondary", width="stretch", on_click=_set, kwargs={"trip": "free"})
        st.button("**패키지 자유 식사**  \n모이는 시간 안에 다녀올 식당부터", type="primary" if s.get("trip") == "package" else "secondary", width="stretch", on_click=_set, kwargs={"trip": "package"})
    if st.button("시작하기", type="primary", width="stretch", disabled=s.get("alone") is None or not s.get("trip")):
        if s.alone:  # 혼자: 나만 오늘 같이 (다른 사람은 지우지 않고 숨긴다)
            people = [dict(p, active=p["id"] == "me" or p["relation"] == "나") for p in s.people]
        else:  # 여럿이: 모두 오늘 같이
            people = [dict(p, active=True) for p in s.people]
        save_people(people)
        go("scan" if s.alone and s.trip == "free" else ("free" if s.alone else "people"))


# ---------------- 사람 ----------------
def person_card(p):
    facts = ""
    if p.get("favorites"):
        facts += f'<dt>즐겨 먹는 음식</dt><dd>{chips(p["favorites"], "kw food")}</dd>'
    else:
        facts += '<dt>즐겨 먹는 음식</dt><dd><span class="kw care">아직 안 골랐어요. 고치기에서 골라 주세요</span></dd>'
    if p.get("likes"):
        facts += f'<dt>좋아하는 맛</dt><dd>{chips(p["likes"])}</dd>'
    bad = [f"{a} 알레르기" for a in p.get("allergies") or []] + [f"{c} 못 먹음" for c in p.get("cannot") or []]
    care = [f"{a} 피하기" for a in p.get("avoid") or []]
    if bad or care:
        tags = "".join('<span class="kw bad">' + E(x) + "</span>" for x in bad) + "".join('<span class="kw care">' + E(x) + "</span>" for x in care)
        facts += f'<dt>빼야 하는 것</dt><dd><div class="chips">{tags}</div></dd>'
    c = p.get("child")
    if c:
        facts += (f'<dt>아이 입맛</dt><dd><div class="chips"><span class="kw">처음 보는 음식: {E(c.get("new_food", ""))}</span>'
                  + "".join(f'<span class="kw care">{E(x)} 골라내요</span>' for x in c.get("pick_out") or [])
                  + (f'<span class="kw">잘 먹는 재료: {E(", ".join(c.get("good") or []))}</span>' if c.get("good") else "") + "</div></dd>")
    meta = " · ".join(x for x in [p["relation"] if p["relation"] != p["name"] else "", p.get("age", "")] if x)
    off = "" if p.get("active", True) else ' style="opacity:.55"'
    md(f'<div class="card"{off}><div class="row" style="align-items:center;justify-content:flex-start">'
       f'<span class="av">{E(p["name"][:1])}</span><div><div class="name">{E(p["name"])}</div><div class="reading">{E(meta)}</div></div>'
       f'<span style="margin-left:auto" class="tag {"good" if p.get("active", True) else ""}">{"오늘 같이" if p.get("active", True) else "오늘은 빠져요"}</span></div>'
       f'<dl class="dl" style="font-size:13px;grid-template-columns:86px 1fr">{facts}</dl></div>')


def people():
    s = st.session_state
    alone = s.get("alone") is True
    # 혼자로 들어오면 오늘 같이 먹는 사람(처음엔 나만)만 보여 준다
    shown = [p for p in s.people if p.get("active", True)] if alone else s.people
    if alone:
        title("내 입맛", "같이 먹는 사람이 생기면 아래 '사람 추가하기'로 넣어 주세요.")
    else:
        title("같이 먹는 사람", "사람마다 아는 음식이 달라요. 그 음식에 빗대어 맛을 알려 드려요.")
        if len(shown) == 1:
            md('<div class="card sunbox small"><div>같이 먹는 사람을 <b>사람 추가하기</b>로 넣어 주세요. 엄마, 아빠, 동생처럼 별명을 직접 쓰면 돼요.</div></div>')
    empty = [p["name"] for p in shown if not p.get("favorites")]
    if empty:
        who = "내" if empty == ["나"] else f'<b>{E(", ".join(empty))}</b>의'
        md(f'<div class="card soft small"><div>{who} 즐겨 먹는 음식을 골라 주세요. 그 음식에 빗대어 처음 보는 메뉴의 맛을 알려 드려요.</div></div>')
    for i, p in enumerate(shown):
        person_card(p)
        with st.container(key=f"pair_p{i}"):
            btns = ["edit"] + ([] if alone or len(shown) == 1 else ["act"]) + ([] if p["id"] == "me" else ["del"])
            cols = dict(zip(btns, st.columns(len(btns))))
            cols["edit"].button("고치기", key=f"edit{i}", width="stretch", on_click=nav, args=('edit',), kwargs={"edit_id": p['id']})
            if "act" in cols:
                cols["act"].button("오늘 빼기" if p.get("active", True) else "오늘 같이", key=f"act{i}", width="stretch",
                                   on_click=lambda pid=p["id"]: save_people([dict(x, active=not x.get("active", True)) if x["id"] == pid else x for x in st.session_state.people]))
            if "del" in cols:
                cols["del"].button("지우기", key=f"del{i}", width="stretch",
                                   on_click=lambda pid=p["id"]: save_people([x for x in st.session_state.people if x["id"] != pid]))
    st.button("사람 추가하기", icon=":material/person_add:", width="stretch", on_click=nav, args=('edit',), kwargs={"edit_id": None})
    n = len(active())
    nxt = "자유 식사 식당 보기" if s.get("trip") == "package" else "메뉴판 찍기"
    st.button(f"{n}명 기준으로 {nxt}", type="primary", width="stretch", disabled=n == 0, on_click=nav, args=('free' if s.get('trip') == 'package' else 'menu' if s.get('scan') else 'scan',))
    md(f'<div class="card soft"><div class="small"><b>내 코드 {E(s.code)}</b> · 입맛은 이 코드로 이 앱에 저장돼요. '
       '로그인은 없어요. 이 브라우저가 기억하고, 다른 휴대폰에서는 아래에 코드를 넣으면 같은 목록을 불러와요.</div></div>')
    with st.expander("다른 기기에서 쓰던 코드 불러오기"):
        code = st.text_input("코드 6자리", max_chars=6, key="load_code").strip().lower()
        if st.button("불러오기", disabled=len(code) != 6):
            got = store.load(code)
            if got is None:
                st.error("이 코드로 저장된 입맛이 없어요.")
            else:
                s.code, s.people, s.cookie_set = code, got, False
                st.rerun()


def edit():
    s = st.session_state
    orig = next((p for p in s.people if p["id"] == s.get("edit_id")), None)
    p = dict(orig) if orig else {"id": "", "name": "", "relation": "", "age": "", "likes": [], "favorites": [], "avoid": [],
                                 "cannot": [], "allergies": [], "child": None, "active": True}
    st.button("← 목록으로", type="tertiary", on_click=nav, args=('people',))
    title(f"{p['name']} 입맛 고치기" if orig else "사람 추가하기", None if orig else "별명은 편하게 불러요. 엄마, 아빠, 동생처럼 직접 써 주세요.")
    k = p["id"] or "new"
    name = st.text_input("별명", p["name"], max_chars=10, placeholder="예: 엄마, 아빠, 동생", key=f"nm_{k}")
    rel = st.pills("관계 · 고르지 않으면 별명을 보고 정해요", RELATIONS, default=p["relation"] if p["relation"] in RELATIONS else None, key=f"rel_{k}")
    age = st.pills("나이대", AGES, default=p.get("age") if p.get("age") in AGES else None, key=f"age_{k}")
    md('<div class="sec">즐겨 먹는 음식 <span class="n">맛을 빗댈 기준이에요. 나라 상관없이 골라 주세요</span></div>')
    fav = []
    countries = []
    for food, v in world.WORLD.items():
        if v[0] not in countries:
            countries.append(v[0])
    for c in countries:
        opts = [f for f, v in world.WORLD.items() if v[0] == c]
        fav += st.pills(c, opts, selection_mode="multi", default=[f for f in p["favorites"] if f in opts], key=f"fav_{k}_{c}") or []
    likes = st.pills("좋아하는 맛", LIKES, selection_mode="multi", default=[x for x in p["likes"] if x in LIKES], key=f"lk_{k}")
    avoid = st.pills("되도록 피하고 싶은 맛", AVOID, selection_mode="multi", default=[x for x in p["avoid"] if x in AVOID], key=f"av_{k}")
    cannot = st.pills("못 먹는 것 · 이 재료가 든 메뉴는 꼭 빼요", CANNOT, selection_mode="multi", default=[x for x in p["cannot"] if x in CANNOT], key=f"cn_{k}")
    allergies = st.pills("알레르기 · 주문 카드 맨 위에 적어요", ALLERGY, selection_mode="multi", default=[x for x in p["allergies"] if x in ALLERGY], key=f"al_{k}")
    child = None
    if rel == "아이":
        c = p.get("child") or {"new_food": "망설여요", "pick_out": [], "good": []}
        md('<div class="sec">아이 입맛</div>')
        nf = st.pills("처음 보는 음식은", NEW_FOOD, default=c["new_food"], key=f"nf_{k}")
        po = st.pills("이럴 때 골라내요", PICK_OUT, selection_mode="multi", default=c["pick_out"], key=f"po_{k}")
        gd = st.pills("잘 먹는 재료", GOOD, selection_mode="multi", default=c["good"], key=f"gd_{k}")
        child = {"new_food": nf or "망설여요", "pick_out": po or [], "good": gd or []}
    if st.button("저장하기", type="primary", width="stretch", disabled=not name.strip()):
        nick = name.strip()
        new = dict(p, name=nick, relation=rel or NICK_REL.get(nick, "가족"), age=age or "", favorites=fav, likes=likes or [], avoid=avoid or [],
                   cannot=cannot or [], allergies=allergies or [], child=child,
                   sex={"엄마": "female", "어머니": "female", "아빠": "male", "아버지": "male"}.get(nick, p.get("sex")), active=True)
        if new["relation"] == "아이" and not new["child"]:
            new["child"] = {"new_food": "망설여요", "pick_out": [], "good": []}
        if orig:
            save_people([new if x["id"] == p["id"] else x for x in s.people])
        else:
            new["id"] = "p" + store.new_code()
            save_people(s.people + [new])
        go("people")


# ---------------- 찍기 ----------------
def scan():
    s = st.session_state
    title("메뉴판을 찍어 주세요", "글씨가 다 보이게 한 장씩 찍으면 잘 읽어요. 어느 나라 말이든 괜찮아요.")
    if s.get("place"):
        md(f'<div class="card sunbox small"><div><b>{E(s.place["name"])}</b>에서 찍는 메뉴판이에요.</div></div>')
    warn = s.pop("scan_warn", None)
    if warn:
        st.warning(warn)
    up = st.file_uploader("메뉴판 사진", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed")
    if up is not None:
        st.image(up.getvalue(), width="stretch")
        if st.button("이 사진으로 읽기", type="primary", width="stretch"):
            run_scan(up.getvalue(), up.type or "image/jpeg")
    if s.get("dev") and st.button("예시 메뉴판 보기 (개발 확인용)", width="stretch"):
        run_scan(None, None)
    md('<div class="sec">아직 식당을 고르지 못했다면</div>')
    st.button("주변 식당 찾기", icon=":material/map:", width="stretch", on_click=nav, args=('nearby',))
    act = active()
    md('<div class="sec">이 사람들 기준으로 볼게요</div>')
    empty = [p["name"] for p in act if not p.get("favorites")]
    if empty:
        who = "내" if empty == ["나"] else f'<b>{E(", ".join(empty))}</b>의'
        md(f'<div class="card sunbox small"><div>{who} 즐겨 먹는 음식을 먼저 골라 두면, 처음 보는 메뉴를 아는 음식에 빗대어 알려 드려요.</div></div>')
    md('<div class="card soft">' + "".join(
        f'<div class="small"><b>{E(p["name"])}</b> <span class="muted">{E(", ".join(p.get("favorites", [])[:3]))}</span>'
        + (f' <span class="kw bad">{E(", ".join([a + " 알레르기" for a in p.get("allergies", [])] + [c + " 못 먹음" for c in p.get("cannot", [])]))}</span>'
           if p.get("allergies") or p.get("cannot") else "") + "</div>" for p in act) + "</div>")
    st.button("사람 바꾸기", width="stretch", on_click=nav, args=('people',))


NOT_MENU = "올린 사진이 메뉴판이 맞는지 다시 한번 확인해 주세요."


def run_scan(data, mime):
    s = st.session_state
    act = active()
    raw, note, source = None, None, "demo"
    if data is not None and not store.take_scan():
        go("scan", scan_warn="오늘 사진 읽기 횟수를 다 썼어요. 내일 다시 해 주세요.")
    if data is not None:
        if not ocr.available() and not os.environ.get("ANTHROPIC_API_KEY"):
            go("scan", scan_warn="사진 읽기가 아직 연결되지 않았어요. 잠시 뒤 다시 해 주세요.")
        with st.status("메뉴판을 읽고 있어요", expanded=True) as box:
            try:
                if ocr.available():
                    box.write("글씨를 따는 중이에요")
                    o = ocr.read(data)
                    if len(o["lines"]) < 2:  # 글씨가 거의 없으면 메뉴판이 아닐 가능성이 크다
                        box.update(label="메뉴판을 찾지 못했어요", state="error")
                        go("scan", scan_warn=NOT_MENU)
                    box.write(f"{len(o['lines'])}줄을 읽었어요. 메뉴마다 무슨 맛인지 적는 중이에요 (1분쯤 걸려요)")
                    raw, source = menu2.read_menu_text(o, act), "ocr"
                else:
                    box.write("메뉴를 읽고 무슨 맛인지 적는 중이에요 (1분쯤 걸려요)")
                    raw, source = menu2.read_menu(ocr.to_jpeg(data, 1600), "image/jpeg", act), "vision"
            except Exception as e:
                if type(e).__name__ in ("StopException", "RerunException"):
                    raise
                print(f"[scan] 실패: {e!r}")
                box.update(label="읽지 못했어요", state="error")
                go("scan", scan_warn="사진을 읽지 못했어요. 글씨가 잘 보이게 다시 찍어 주세요.")
            if raw is not None and (raw.get("is_menu") is False or not [i for i in raw.get("items", []) if not i.get("unreadable")]):
                box.update(label="메뉴판을 찾지 못했어요", state="error")
                go("scan", scan_warn=NOT_MENU)
            box.update(label="다 읽었어요", state="complete")
    if raw is None:
        raw = json.loads((menu2.DATA / "demo_paris.json").read_text("utf-8"))
        data, source = DEMO_IMG.read_bytes(), "demo"
    elif s.get("place") and not raw.get("restaurant"):
        raw["restaurant"] = s.place["name"]
    s.scan_raw, s.scan_img, s.scan_note, s.scan_source = raw, data, note, source
    s.place = None  # 고른 식당은 이번 메뉴판에만 쓴다
    rejudge()
    go("menu", menu_mode_w="번역만", combo_w=None)


# ---------------- 메뉴판 ----------------
def menu():
    s = st.session_state
    scan = s.scan
    md(f'<div style="margin-top:10px"><span class="pill ink">{E(scan.get("menu_language") or "외국어")} → 한국어</span></div>'
       f'<div class="h1">{E(scan.get("restaurant") or "메뉴판")}</div>'
       f'<div class="sub">메뉴 {len(scan["items"])}개를 옮겼어요. 메뉴를 누르면 무슨 맛인지 자세히 보여 드려요.</div>')
    if s.get("scan_note"):
        st.info(s.scan_note)
    with st.expander("찍은 메뉴판 보기"):
        st.image(s.scan_img, width="stretch")
        st.button("다른 메뉴판 찍기", icon=":material/photo_camera:", width="stretch", on_click=nav, args=('scan',))
    if not s.get("menu_mode_w"):
        s.menu_mode_w = "번역만"
    mode = st.segmented_control("보기", ["번역만", "원문과 함께", "누가 먹을까"], key="menu_mode_w", label_visibility="collapsed") or "번역만"
    if mode == "누가 먹을까":
        groups = [("all", "모두 편히 먹어요", "누가 먹어도 괜찮아요"), ("some", "몇 명만 괜찮아요", "사람마다 달라요. 이유를 확인해 주세요"),
                  ("none", "모두 피하는 게 좋아요", "")]
        for g, t, hint in groups:
            items = [i for i in scan["judged"] if i["group"] == g]
            if items:
                md(f'<div class="sec">{t} <span class="n">{len(items)}개</span></div>' + (f'<div class="note">{hint}</div>' if hint else ""))
                for it in items:
                    row(it, mode)
    else:
        sec = None
        for it in scan["items"]:
            if it["section_ko"] != sec:
                sec = it["section_ko"]
                md(f'<div class="sec">{E(sec)}' + (f' <span class="n"><i>{E(it["section_orig"])}</i></span>' if mode == "원문과 함께" else "") + "</div>")
            row(it, mode)
    best = scan["combos"][0] if scan["combos"] else None
    if best:
        st.button(f"{best['summary']['people']}명이 같이 먹을 조합 보기", type="primary", width="stretch", on_click=nav, args=('combo',))


def row(it, mode):
    if it["unreadable"]:
        md(f'<div class="card soft" style="border-style:dashed"><div class="row"><div><div class="name">{E(it["name_orig"] if mode == "원문과 함께" else it["name_ko"])}</div>'
           f'<div class="desc">글씨가 흐려서 못 읽었어요. 직원에게 물어봐 주세요.</div></div><span class="price">{E(it["price"])}</span></div></div>')
        return
    with st.container(key=f"mrow_{it['id']}_{mode}"):
        head = ""
        if mode == "원문과 함께":
            head += f'<div class="orig">{E(it["name_orig"])}</div>'
        tags = (' <span class="tag sun">가게 추천</span>' if it.get("chef_pick") else "") + (' <span class="tag">어린이 메뉴</span>' if it.get("kids_only") else "")
        body = f'<div class="name">{E(it["name_ko"])}{tags}</div>'
        if mode == "원문과 함께":
            body += f'<div class="reading">{E(it["reading"])}</div>'
        body += f'<div class="desc">{E(it["desc_ko"])}</div>'
        if mode == "원문과 함께" and it["glossary"]:
            body += '<div class="chips">' + "".join(f'<span class="gl"><b>{E(g["term"])}</b>{E(g["meaning"])}</span>' for g in it["glossary"]) + "</div>"
        if mode == "누가 먹을까" and it.get("headline"):
            body += f'<div class="like">{E(it["headline"])}</div>'
        al = [c for c in it["contains"] if c in ALLERGENS]
        if al and mode != "누가 먹을까":
            body += chips([f"{a} 들어 있어요" for a in al], "kw care")
        tail = marks(it["per"], reasons=mode == "누가 먹을까") if it["course"] != "drink" else ""  # 표시 줄은 카드 전체 폭으로
        md(f'<div class="row"><div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:4px">{head}{body}</div><span class="price">{E(it["price"])}</span></div>{tail}')
        if it["course"] != "drink":
            st.button("무슨 맛인지 보기 ›", key=f"open_{it['id']}_{mode}", on_click=nav, args=('dish',), kwargs={"dish_id": it['id']})


# ---------------- 메뉴 자세히 ----------------
def taste_map(points):
    W, H, pad = 300, 190, 24
    xs, ys = [p["x"] for p in points], [p["y"] for p in points]
    # 점들이 몰려 있으면 보이는 범위를 좁혀서 차이가 보이게 한다 (최소 폭 0.3)
    def rng(v):
        lo, hi = min(v), max(v)
        mid, half = (lo + hi) / 2, max(0.15, (hi - lo) / 2 + 0.06)
        return mid - half, mid + half
    (x0, x1), (y0, y1) = rng(xs), rng(ys)
    X = lambda x: pad + 14 + (x - x0) / (x1 - x0) * (W - pad * 2 - 28)
    Y = lambda y: H - pad - 14 - (y - y0) / (y1 - y0) * (H - pad * 2 - 20)
    me, foods = points[0], [p for p in points if p["kind"] == "food"]
    svg = (f'<svg viewBox="0 0 {W} {H}" style="width:100%;max-width:380px"><rect x="{pad}" y="8" width="{W - pad * 2}" height="{H - pad - 8}" rx="10" fill="#f7f8f4" stroke="#dce2da"/>'
           ''
           f'<text x="{pad}" y="{H - 6}" font-size="10" fill="#5e6a63">← 더 담백해요</text><text x="{W - pad}" y="{H - 6}" text-anchor="end" font-size="10" fill="#5e6a63">더 진해요 →</text>'
           f'<text x="{pad + 6}" y="22" font-size="10" fill="#5e6a63">↑ 더 부드러워요</text>')
    for p in foods:
        svg += f'<line x1="{X(me["x"])}" y1="{Y(me["y"])}" x2="{X(p["x"])}" y2="{Y(p["y"])}" stroke="#b9c2b7" stroke-width="1.5"/>'
    for i, p in enumerate(foods):
        svg += (f'<circle cx="{X(p["x"])}" cy="{Y(p["y"])}" r="9" fill="#ffc94a" stroke="#22302a" stroke-width="1.5"/>'
                f'<text x="{X(p["x"])}" y="{Y(p["y"]) + 4}" text-anchor="middle" font-size="10" font-weight="800" fill="#22302a">{i + 1}</text>')
    svg += f'<circle cx="{X(me["x"])}" cy="{Y(me["y"])}" r="7" fill="#2f7a50" stroke="#22302a" stroke-width="2"/></svg>'
    legend = '<div class="small" style="display:flex;flex-direction:column;gap:4px"><div><span class="vm v-easy" style="width:14px;height:14px"></span> 이 메뉴</div>'
    for i, p in enumerate(foods):
        legend += f'<div><span class="vm" style="background:#ffc94a;color:#22302a;width:16px;height:16px;font-size:10px">{i + 1}</span> {E(p["name"])} <span class="muted">· {E(", ".join(p.get("who", [])))}</span></div>'
    return svg + legend + "</div>"


def speak_block(lines, voice, height):
    """현지어 문장을 읽어 주는 작은 상자 (브라우저 음성 합성)."""
    rows = "".join(f'<div class="r"><button onclick="say({i})" aria-label="읽어 주기">▶</button><div><b>{E(l[2] if len(l) > 2 else l[0])}</b><span>{E(l[1])}</span></div></div>'
                   for i, l in enumerate(lines))
    components.html(
        '<style>body{margin:0;font-family:"Noto Sans KR",sans-serif;color:#22302a}.r{display:flex;gap:10px;align-items:center;padding:8px 0;border-bottom:1px dashed #dce2da}'
        '.r:last-child{border-bottom:0}button{width:40px;height:40px;flex-shrink:0;border-radius:50%;border:0;background:#ffc94a;font-size:14px;cursor:pointer}'
        'b{display:block;font-size:16px}span{font-size:12px;color:#5e6a63}</style>' + rows +
        f'<script>const T={json.dumps([l[0] for l in lines], ensure_ascii=False)};function say(i){{speechSynthesis.cancel();'
        f'const u=new SpeechSynthesisUtterance(T[i]);u.lang="{voice}";u.rate=.9;speechSynthesis.speak(u)}}</script>', height=height)


REQ_FROM_REASON = [("버섯", "버섯 빼고"), ("양파", "양파 빼고"), ("소스", "소스는 따로"), ("짭", "덜 짜게"), ("짜", "덜 짜게"), ("익혀", "잘 익혀 주세요")]


def dish():
    s = st.session_state
    scan = s.scan
    it = next((i for i in scan["items"] if i["id"] == s.get("dish_id")), None)
    if not it:
        go("menu")
    st.button("← 메뉴판으로", type="tertiary", on_click=nav, args=('menu',))
    tags = ' <span class="tag sun">가게 추천</span>' if it.get("chef_pick") else ""
    md(f'<div class="small muted">{E(it["section_ko"])} · {E(it["price"])}</div><div class="h1">{E(it["name_ko"])}{tags}</div>'
       f'<div class="reading" style="font-size:14px"><i>{E(it["name_orig"])}</i> · {E(it["reading"])}</div>')
    kws = [("맛", it["taste_kw"]), ("향", it["aroma_kw"]), ("식감", it["texture_kw"])]
    md('<div class="chips">' + "".join(f'<span class="kw">{E(w)}</span>' for _, l in kws for w in l) + "</div>")

    ok = [x for x in it["per"] if x["verdict"] == "편히"]
    fans = [x for x in it["per"] if x["match"] and x["match"]["bars"] >= 2]
    who = ", ".join(f'{x["match"]["food"]} 좋아하는 {x["name"]}' for x in fans) or (", ".join(x["name"] for x in ok) if ok else "")
    taste_line = it["desc_ko"]
    if it["taste_kw"]:
        taste_line += f' {", ".join(it["taste_kw"])} 맛이에요.'
    if it["aroma_kw"]:
        taste_line += f' {", ".join(it["aroma_kw"])}이 나요.'
    dl = f'<dt>맛 설명</dt><dd>{E(taste_line)}</dd>'
    if it.get("headline"):
        dl += f'<dt>아는 맛</dt><dd>{E(it["headline"])}</dd>'
    if who:
        dl += f'<dt>이런 분께</dt><dd>{E(who)}</dd>'
    md(f'<div class="card"><dl class="dl">{dl}</dl></div>')
    warn = reviews.caution(it["name_orig"])
    if warn:
        md(f'<div class="card warnbox small">{E(warn)}</div>')

    if it["course"] != "drink":
        md('<div class="sec">사람마다 아는 맛으로</div>')
        for x in it["per"]:
            m = x["match"]
            h = f'<div class="plike {VCLASS[x["verdict"]]}"><div class="head"><span class="vm">{VMARK[x["verdict"]]}</span><b>{E(x["name"])}</b>'
            if m:
                h += f'<span>좋아하는 <b>{E(m["food"])}</b>{josa(m["food"], "과", "와")} {E(m["level"])}{level(m["bars"])}</span></div>'
            else:
                h += '<span class="muted">즐겨 먹는 음식 중엔 닮은 게 없어요. 새로운 맛이에요</span></div>'
            if x["verdict"] != "편히":
                h += f'<div style="{"color:var(--warn);font-weight:700" if x["verdict"] == "피하기" else ""}">{E(x["reason"])}</div>'
            if m:
                if m["shared"]:
                    h += '<div class="chips"><span class="small muted">같은 점</span>' + "".join(f'<span class="kw same">{E(w)}</span>' for w in m["shared"]) + "</div>"
                h += f'<div class="muted">{E(m["difference"])}</div>'
            md(h + "</div>")
        if len(it["map"]) > 1:
            md('<div class="sec">맛 지도</div><div class="card">' + taste_map(it["map"]) +
               '<div class="note">가까울수록 비슷한 맛이에요. 짠맛, 감칠맛, 기름진 정도를 가로에, 부드러운 정도를 세로에 놓았어요.</div></div>')

    if st.toggle("상세보기", key=f"more_{it['id']}"):
        p = (f'{it["name_ko"]}({it["reading"]}){josa(it["reading"], "은", "는")} {it["desc_ko"]}'
             + (f' 맛은 {", ".join(it["taste_kw"])} 편이에요.' if it["taste_kw"] else "")
             + (f' {", ".join(it["aroma_kw"])}이 나요.' if it["aroma_kw"] else "")
             + (f' 먹어 보면 {", ".join(it["texture_kw"])} 식감이에요.' if it["texture_kw"] else "")
             + f' 주문하고 {it["serve_minutes"]}분쯤이면 나와요.' + (" 가운데 두고 나눠 먹기 좋아요." if it["share_ok"] else ""))
        gl = "".join(f'<li><i>{E(g["term"])}</i>: {E(g["meaning"])}</li>' for g in it["glossary"])
        md(f'<div class="card soft" style="font-size:15px;line-height:1.75"><div>{E(p)}</div>' + (f'<ul style="margin:0;padding-left:18px;font-size:14px">{gl}</ul>' if gl else "")
           + (f'<div class="note">들어간 재료(짐작): {E(", ".join(it["contains"]))}. 메뉴판에 없는 재료가 있을 수 있어요.</div>' if it["contains"] else "") + "</div>")

    # 후기: 이 식당 먼저, 없으면 같은 메뉴
    rv = reviews.reviews(it["name_orig"], scan.get("restaurant", ""))
    md(f'<div class="sec">후기 <span class="n">{rv["count"]}개' + (f' · ★ {rv["avg"]}' if rv["avg"] else "") + "</span></div>")
    if rv["count"]:
        h = '<div class="card">'
        for label, lst in [("이 식당", rv["here"]), ("같은 메뉴", rv["other"])]:
            for r in lst[:3]:
                src = "이용자"
                h += (f'<div class="rv"><span class="tag {"good" if label == "이 식당" else ""}">{label}</span><div style="flex:1">{E(r["text"])}'
                      f'<div class="note">{src} 후기 · {E(r["date"])}</div></div><span class="st">★ {r["stars"]}</span></div>')
        md(h + '</div><div class="note">이 식당 후기를 먼저, 없으면 다른 식당의 같은 메뉴 후기를 보여 드려요.</div>')
    else:
        md('<div class="card soft small muted">아직 후기가 없어요. 먹어 보고 처음으로 남겨 주세요.</div>')

    # 같이 먹기 좋은 메뉴
    best = scan["combos"][0] if scan["combos"] else None
    if best:
        others = [p["item"] for p in best["plates"]] + [d["item"] for d in best["share"]]
        others = [o for i, o in enumerate(others) if o["id"] != it["id"] and o["id"] not in [x["id"] for x in others[:i]]][:3]
        if others:
            md('<div class="sec">같이 먹기 좋은 메뉴</div>' + chips([o["name_ko"] for o in others], "kw food"))

    # 요청 문장
    reqs = []
    for x in it["per"]:
        for k, r in REQ_FROM_REASON:
            if k in (x["reason"] or "") and r not in reqs:
                reqs.append(r)
    for r in ["소스는 따로", "덜 짜게"]:
        if r not in reqs:
            reqs.append(r)
    lang = (scan.get("language_code") or "fr").split("-")[0]
    col = 0 if lang == "fr" else 1
    md('<div class="sec">직원에게 부탁하기 <span class="n">누르면 읽어 줘요</span></div>')
    speak_block([(order.REQUESTS[r][col], r) for r in reqs[:4] if r in order.REQUESTS], "fr-FR" if lang == "fr" else "en-US", 60 * min(4, len(reqs)) + 8)

    if it["course"] != "drink":
        md('<div class="sec">보여 주기</div>')
        with st.container(key="pair_show"):
            cols = st.columns(len(it["per"]))
            for c, x in zip(cols, it["per"]):
                if c.button(x["name"], key=f"show_{x['id']}", width="stretch"):
                    show_dialog(it, x)
    st.button("먹어 봤어요 · 짧은 설문", width="stretch", on_click=nav, args=('survey',))


@st.dialog("이 사람에게 보여 주기")
def show_dialog(it, x):
    m = x["match"]
    line = (f'{E(x["name"])}, 이건 <b>{E(m["food"])}</b>{josa(m["food"], "이랑", "랑")} {E(m["level"])}.' if m
            else f'처음 먹어 보는 맛이에요. {E(", ".join(it["taste_kw"]))} 맛이에요.')
    md(f'<div style="text-align:center;display:flex;flex-direction:column;gap:12px;align-items:center">'
       f'<span class="vm {VCLASS[x["verdict"]]}" style="width:52px;height:52px;font-size:26px">{VMARK[x["verdict"]]}</span>'
       f'<div class="h2d" style="font-size:30px">{E(it["name_ko"])}</div><div style="font-size:22px;line-height:1.5">{line}</div>'
       + (f'<div style="font-size:18px;color:var(--muted)">{E(m["difference"])}</div>' if m else "")
       + (f'<div style="font-size:18px;color:var(--warn)">{E(x["reason"])}</div>' if x["verdict"] != "편히" else "") + "</div>")


# ---------------- 설문 ----------------
def survey():
    s = st.session_state
    it = next((i for i in s.scan["items"] if i["id"] == s.get("dish_id")), None)
    st.button("← 메뉴로", type="tertiary", on_click=nav, args=('dish',))
    title("먹어 보니 어땠어요?", f"{it['name_ko']} · 남겨 주신 답은 다음에 이 메뉴를 보는 사람에게 알려 줘요.")
    with st.form("survey"):
        ordered = st.segmented_control("이 메뉴를 실제로 시켰나요?", ["네", "아니요"], default="네")
        imagine = st.segmented_control("설명을 보고 맛이 잘 그려졌나요? (1 전혀 ~ 5 아주 잘)", [1, 2, 3, 4, 5], default=4)
        stronger = st.pills("예상보다 강했던 맛", reviews.STRONG, selection_mode="multi")
        again = st.segmented_control("다음에도 이렇게 추천받고 싶나요?", ["네", "아니요"], default="네")
        who = st.pills("누가 먹었나요?", [p["name"] for p in active()], selection_mode="multi")
        comment = st.text_area("한 줄 후기 (남기면 다른 사람에게 보여요)", max_chars=200, placeholder="예: 갈비찜보다 와인 향이 진했어요")
        if st.form_submit_button("보내기", type="primary", width="stretch"):
            reviews.save(s.scan.get("restaurant", ""), it["name_orig"], ordered == "네", imagine or 3, stronger or [], again == "네",
                         comment or "", ",".join(who or []))
            st.toast("고마워요. 다음 사람에게 알려 줄게요.")
            go("dish")
    st_ = reviews.stats(it["name_orig"])
    if st_["n"]:
        md(f'<div class="sec">이 메뉴에 쌓인 답</div><div class="sum"><div><span>응답</span><b>{st_["n"]}개</b></div>'
           f'<div><span>맛이 그려졌어요</span><b>{st_["imagine"]} / 5</b></div><div><span>다시 추천받고 싶어요</span><b>{st_["again"]}%</b></div>'
           + (f'<div><span>예상보다 강했던 맛</span><b>{E(st_["strong"]["taste"])} {st_["strong"]["pct"]}%</b></div>' if st_.get("strong") else "") + "</div>")


# ---------------- 조합 ----------------
def combo():
    s = st.session_state
    scan = s.scan
    title("이렇게 시키면 어때요?", "사람마다 한 접시씩, 후식은 같이 나눠요. 가장 덜 맞는 사람도 맛있게 먹는 조합부터 골랐어요.")
    names = [c["title"] for c in scan["combos"]]
    if s.get("combo_w") not in names:
        s.combo_w = names[s.get("combo_idx", 0) if s.get("combo_idx", 0) < len(names) else 0]
    pick = st.segmented_control("조합", names, key="combo_w", label_visibility="collapsed") or names[0]
    idx = names.index(pick)
    if idx != s.get("combo_idx", 0):
        s.combo_idx, s.picks = idx, {}
    c = scan["combos"][idx]
    plates = [dict(p, **s.picks[p["person"]["id"]]) if p["person"]["id"] in s.get("picks", {}) else p for p in c["plates"]]
    price = lambda p: float(menu2._price(p))
    total = sum(price(p["item"]["price"]) for p in plates) + sum(price(d["item"]["price"]) * d["count"] for d in c["share"])
    mins = max([p["item"]["serve_minutes"] for p in plates] + [d["item"]["serve_minutes"] for d in c["share"]])
    happy = sum(p["verdict"] == "편히" for p in plates)
    md(f'<div class="note">{E(c["note"])}</div><div class="sum"><div><span>입에 맞는 사람</span><b>{happy} / {len(plates)}명</b></div>'
       f'<div><span>나오는 시간</span><b>{mins}분쯤</b></div><div><span>금액</span><b>{total:g}€</b></div>'
       f'<div><span>접시 수</span><b>{len(plates) + sum(d["count"] for d in c["share"])}개</b></div></div>')
    h = '<div class="card"><div class="name">한 사람에 한 접시</div>'
    for p in plates:
        m = p["match"]
        h += (f'<div class="plate {VCLASS[p["verdict"]]}"><span class="av">{E(p["person"]["name"][:1])}</span><div style="flex:1">'
              f'<div class="small muted">{E(p["person"]["name"])}</div><div class="name"><span class="vm">{VMARK[p["verdict"]]}</span> {E(p["item"]["name_ko"])}</div>'
              f'<div class="reading"><i>{E(p["item"]["name_orig"])}</i> · {E(p["item"]["price"])}</div>'
              + (f'<div class="like">좋아하는 {E(m["food"])}{josa(m["food"], "과", "와")} {E(m["level"])}{level(m["bars"])}</div>' if m else "")
              + (f'<div class="small muted">{E(p["reason"])}</div>' if p["verdict"] != "편히" else "") + "</div></div>")
    md(h + "</div>")
    with st.expander("접시 바꾸기"):
        for p in c["plates"]:
            opts = [p] + p["alts"]
            labels = [f'{VMARK[o["verdict"]]} {o["item"]["name_ko"]} · {o["item"]["price"]}' for o in opts]
            cur = s.picks.get(p["person"]["id"], {}).get("item", {}).get("id", p["item"]["id"])
            key = f"sw_{idx}_{p['person']['id']}"
            st.selectbox(p["person"]["name"], range(len(opts)), format_func=lambda k, labels=labels: labels[k],
                         index=next((k for k, o in enumerate(opts) if o["item"]["id"] == cur), 0), key=key,
                         on_change=_swap, args=(key, p["person"]["id"], opts))
    if c["share"]:
        md('<div class="card"><div class="name">가운데 두고 같이</div>' + "".join(
            f'<div class="small"><b>{E(d["item"]["name_ko"])}</b> × {d["count"]} <span class="muted">{E(d["item"]["price"])} · {E(", ".join(d["who"]))} 먹을 수 있어요</span></div>'
            for d in c["share"]) + "</div>")
    with st.expander("왜 이렇게 골랐나요"):
        md(f'<div style="font-size:15px;line-height:1.7">{E(c["why"])}</div>')
    st.button("이대로 주문 카드 만들기", type="primary", width="stretch", on_click=nav, args=('order',))


# ---------------- 주문 카드 ----------------
def order_card():
    s = st.session_state
    scan = s.scan
    c = scan["combos"][s.get("combo_idx", 0)]
    plates = [dict(p, **s.picks[p["person"]["id"]]) if p["person"]["id"] in s.get("picks", {}) else p for p in c["plates"]]
    count = {}
    for p in plates:
        count[p["item"]["id"]] = count.get(p["item"]["id"], 0) + 1
    for d in c["share"]:
        count[d["item"]["id"]] = count.get(d["item"]["id"], 0) + d["count"]
    title("주문 카드", f"{c['title']} 조합이에요. 알레르기와 못 먹는 것을 맨 위에 적었어요.")
    reqs = st.pills("부탁할 것 더하기", list(order.REQUESTS), selection_mode="multi", key="order_reqs") or []
    card = order.card(scan, active(), [{"item_id": k, "count": v} for k, v in count.items()], reqs)
    big = st.toggle("글씨 크게", key="order_big")
    h = f'<div class="oc {"big" if big else ""}" lang="{card["lang"]}"><div class="lbl">직원에게 이 화면을 보여 주세요</div>'
    if card["first"]:
        h += '<div class="first">' + "".join(f'<div><b>{E(t)}</b><span class="ko">{E(k)}</span></div>' for t, k in zip(card["first"], card["first_ko"])) + "</div>"
    h += f'<div class="hello">{E(card["hello"])}</div>'
    h += "".join(f'<div class="ln"><b>{o["count"]} × {E(o["orig"])}</b><span class="ko">{E(o["ko"])} · {E(o["price"])}</span></div>' for o in card["order"])
    h += "".join(f'<div class="ln"><b style="font-size:17px">{E(r["orig"])}</b><span class="ko">{E(r["ko"])}</span></div>' for r in card["requests"])
    md(h + f'<div class="hello">{E(card["thanks"])}</div></div>')
    if card.get("note"):
        st.info(card["note"])
    md(f'<div class="sec">{"프랑스어" if card["lang"] == "fr" else "영어"}로 읽어 주기</div>')
    lines = [(t, k) for t, k in zip(card["first"], card["first_ko"])] + [(f'{o["count"]} {o["orig"]}', o["ko"]) for o in card["order"]] + \
            [(r["orig"], r["ko"]) for r in card["requests"]]
    speak_block([(" ".join([*card["first"], card["hello"], *[f'{o["count"]} {o["orig"]}' for o in card["order"]], *[r["orig"] for r in card["requests"]], card["thanks"]]),
                  "알레르기부터 주문, 인사까지 차례로 읽어요", "카드 전체 읽기")] + lines, card["voice"], 64 * (len(lines) + 1) + 10)
    md('<div class="note">현지어 문장은 자동으로 만든 거라 어색할 수 있어요. 직원이 헷갈려하면 메뉴 이름을 손가락으로 가리켜 주세요.</div>')


# ---------------- 자유 식사 ----------------
# ---------------- 위치와 주변 식당 ----------------
@st.cache_data(ttl=900, show_spinner=False)
def _places(lat, lng):
    """같은 동네(소수점 셋째 자리, 약 100m)는 15분 동안 다시 묻지 않는다."""
    src, els = nearby.find(lat, lng)
    return src, nearby.to_places(els, lat, lng)


def geo_block(key):
    """지금 위치를 묻는다. 위치가 있으면 {lat, lng}, 없으면 None. 위치는 저장하지 않고 이 화면에서만 쓴다."""
    s = st.session_state
    if s.get("geo"):
        return s.geo
    if s.get("geo_asking"):
        from streamlit_js_eval import get_geolocation

        loc = get_geolocation(component_key=f"geo_{s.geo_asking}")
        if loc and loc.get("coords"):
            s.geo = {"lat": round(loc["coords"]["latitude"], 5), "lng": round(loc["coords"]["longitude"], 5)}
            s.geo_asking = None
            st.rerun()
        elif loc and loc.get("error"):
            s.geo_asking, s.geo_err = None, ("위치를 가져오지 못했어요. 휴대폰은 설정에서 브라우저 위치 권한을, 노트북(맥)은 시스템 설정 > 개인정보 보호 및 보안 > "
                                             "위치 서비스에서 브라우저를 켜 주세요. 주소창 왼쪽 자물쇠에서 이 사이트 위치 허용도 확인해 주세요.")
            st.rerun()
        md('<div class="card soft small">위치 허용 창이 뜨면 <b>허용</b>을 눌러 주세요.</div>')
        return None
    if s.get("geo_err"):
        st.warning(s.pop("geo_err"))
    if st.button("지금 위치로 찾기", icon=":material/my_location:", type="primary", width="stretch", key=f"geo_btn_{key}"):
        s.geo_asking = (s.get("geo_try") or 0) + 1
        s.geo_try = s.geo_asking
        st.rerun()
    md('<div class="note">위치는 주변 식당을 찾는 데만 쓰고 저장하지 않아요.</div>')
    return None


def places_here(geo):
    with st.spinner("주변 식당을 찾고 있어요"):
        try:
            return _places(round(geo["lat"], 3), round(geo["lng"], 3))
        except Exception as e:
            print(f"[nearby] 실패: {e!r}")
            return None, None


def _map(center, center_label, rows, label_of, color_of, key, height=260):
    from folium import DivIcon, Map, Marker

    m = Map(location=[center["lat"], center["lng"]], zoom_start=16, tiles="OpenStreetMap", control_scale=False)
    pill = 'position:absolute;transform:translate(-50%,-100%);white-space:nowrap;padding:3px 9px;border-radius:999px;font:700 12px sans-serif;box-shadow:0 2px 6px rgba(0,0,0,.25);'
    Marker([center["lat"], center["lng"]], icon=DivIcon(html=f'<span style="{pill.replace("translate(-50%,-100%)", "translate(calc(-100% - 8px),-50%)")}background:#22302a;color:#fff">{center_label}</span>')).add_to(m)
    for r in rows:
        Marker([r["lat"], r["lng"]], icon=DivIcon(html=f'<span style="{pill}background:{color_of(r)};color:#fff;border:2px solid #fff">{label_of(r)}</span>')).add_to(m)
    if rows:
        m.fit_bounds([[center["lat"], center["lng"]]] + [[r["lat"], r["lng"]] for r in rows], padding=(30, 30))
    # 서버와 주고받지 않는 정적 지도 (다시 그리기 부담을 줄인다)
    components.html(m.get_root().render(), height=height)


def _marks(marks):
    out = '<ul class="marks col">'
    for x in marks:
        if x.get("unknown"):
            out += f'<li class="v-care"><span class="vm">!</span><b>{E(x["name"])}</b><span class="why">메뉴 정보가 없어요. 들어가서 메뉴판을 찍어 보세요</span></li>'
            continue
        out += (f'<li class="{VCLASS[x["mark"]]}"><span class="vm">{VMARK[x["mark"]]}</span><b>{E(x["name"])}</b><span class="why">{E(x["dish"] or "먹을 게 없어요")}'
                + (f' · {E(x["match"]["food"])}{josa(x["match"]["food"], "과", "와")} {E(x["match"]["level"])}' if x["match"] else "") + "</span></li>")
    return out + "</ul>"


def _pick(r, key):
    """이 식당을 고르고 메뉴판 찍기로."""
    st.button("이 식당 메뉴판 찍기", key=key, icon=":material/photo_camera:", width="stretch", on_click=nav, args=('scan',), kwargs={"place": {'name': r['name'], 'id': r['id']}})


def nearby_view():
    s = st.session_state
    st.button("← 메뉴판 찍기로", type="tertiary", on_click=nav, args=('scan',))
    title("주변 식당", "지금 있는 곳에서 가까운 식당이에요. 같이 먹는 사람마다 먹을 메뉴를 미리 보여 드려요.")
    geo = geo_block("near")
    if not geo:
        return
    src, places = places_here(geo)
    if places is None:
        st.warning("주변 식당을 불러오지 못했어요. 잠시 뒤 다시 찾아 주세요.")
        st.button("다시 찾기", width="stretch", key="near_retry")
        return
    if not places:
        st.info("가까운 곳에 등록된 식당이 없어요. 조금 이동한 뒤 위치를 다시 잡아 주세요.")
        st.button("위치 다시 잡기", width="stretch", key="near_regeo", on_click=_set, kwargs={"geo": None})
        return
    act = active()
    speed, slowest = freemeal.group_speed(act)
    rows = []
    for r in places:
        marks = freemeal.person_marks(r["dishes"], act)
        walk = max(1, round(r["distance_m"] * 1.3 / speed / 60))
        score = sum((1 if m["mark"] == "편히" else 0.4 if m["mark"] == "조심" else -1) + (m["match"] and 0.5 or 0) for m in marks) / max(1, len(act))
        score -= walk / 30 + (0.3 if r["kind"] == "카페" else 0) + (0.6 if r["wait_min"] <= 5 else 0) + (0 if r["dishes"] else 0.8)
        rows.append(dict(r, marks=marks, walk_min=walk, score=score, all_ok=all(m["mark"] == "편히" for m in marks)))
    rows.sort(key=lambda r: -r["score"])
    only = st.toggle("모두 편히 먹을 수 있는 곳만", key="near_only")
    shown = [r for r in rows if r["all_ok"]] if only else rows
    shown = shown[:15]
    md(f'<div class="small">지금 있는 곳 주변 {len(rows)}곳 중 잘 맞는 순서로 {len(shown)}곳이에요.</div>'
       f'<div class="note">걸어서 걸리는 시간은 가장 천천히 걷는 {E(slowest)} 기준이에요.</div>')
    _map(geo, "지금 여기", shown, lambda r: f'{shown.index(r) + 1}', lambda r: "#2f7a50" if r["all_ok"] else "#c99a1e", "nearmap")
    for i, r in enumerate(shown):
        orig = f' <span class="small muted">{E(r["orig_name"])}</span>' if r.get("orig_name") else ""
        md(f'<div class="card"><div class="row"><div><span class="tag {"good" if r["all_ok"] else ""}">{i + 1}</span> <b style="font-size:16px">{E(r["name"])}</b>{orig}'
           f'<div class="small muted">{E(r["kind"])} · 걸어서 {r["walk_min"]}분</div></div></div>{_marks(r["marks"])}'
           + (f'<div class="note">{E(r["note"])}</div>' if r.get("note") else "") + "</div>")
        _pick(r, f"near_pick_{r['id']}")
    md(f'<div class="note">식당 정보: {E(src)}. 대표 메뉴는 요리 종류로 짐작한 것이라, 실제 메뉴는 메뉴판을 찍어서 확인해 주세요.</div>')
    if geo and st.button("위치 다시 잡기", width="stretch"):
        s.geo = None
        st.rerun()


def local_now():
    """휴대폰(브라우저) 시간대의 지금 시각. 시간대를 모르면 서버 시각."""
    from datetime import datetime, timedelta, timezone

    try:
        from zoneinfo import ZoneInfo

        if st.context.timezone:
            return datetime.now(ZoneInfo(st.context.timezone))
    except Exception:
        pass
    off = st.context.timezone_offset  # 분, 자바스크립트 getTimezoneOffset 기준(UTC보다 빠르면 음수)
    return datetime.now(timezone(timedelta(minutes=-off))) if off is not None else datetime.now()


def free():
    from datetime import timedelta

    s = st.session_state
    title("자유 식사 시간", "모이는 시간에 늦지 않게 다녀올 수 있는 식당만 먼저 보여 드려요.")
    if "free_now" not in s:  # 처음 열 때 지금 시각으로 채우고, 모이는 시간은 1시간 10분 뒤로
        n = local_now()
        n = n.replace(minute=n.minute - n.minute % 5, second=0, microsecond=0)
        s.free_now, s.free_meet = n.time(), (n + timedelta(minutes=70)).time()
    with st.container(key="pair_time"):
        c1, c2 = st.columns(2)
        now = c1.time_input("지금", step=300, key="free_now")
        meet = c2.time_input("모이는 시간", step=300, key="free_meet")
    buf = st.segmented_control("미리 돌아오기", [5, 10, 15], default=10, format_func=lambda b: f"{b}분 전") or 10
    geo = geo_block("free")
    if not geo:  # 위치가 없으면 계산하지 않는다 (예시 데이터를 보여 주지 않음)
        return
    src, places = places_here(geo)
    if places is None:
        st.warning("주변 식당을 불러오지 못했어요. 잠시 뒤 다시 찾아 주세요.")
        st.button("다시 찾기", width="stretch", key="free_retry")
        return
    if not places:
        st.info("가까운 곳에 등록된 식당이 없어요. 조금 이동한 뒤 위치를 다시 잡아 주세요.")
        return
    meet_pt = {"name": "지금 있는 곳", "lat": geo["lat"], "lng": geo["lng"]}
    data = freemeal.plan(active(), now.strftime("%H:%M"), meet.strftime("%H:%M"), buf, meet_pt, places)
    if data["left_min"] <= 0:
        st.warning("모이는 시간이 지금보다 늦어야 해요.")
        return
    md(f'<div><b style="font-size:24px;color:var(--accent-text)">{data["left_min"]}분</b> 남았어요</div><div class="small">지금 있는 곳을 모이는 곳으로 보고 계산했어요.</div>'
       f'<div class="note">걷는 속도는 가장 천천히 걷는 {E(data["slowest"])} 기준 (분당 {round(data["speed"] * 60)}m)</div>')
    fits = [r for r in data["restaurants"] if r["fits"] and r["known"]][:12]
    rest = [r for r in data["restaurants"] if not r["fits"] and r["known"]][:3]
    if not fits:
        st.info("이 시간 안에 다녀올 수 있는 식당이 없어요. 모이는 시간을 늦추거나 미리 돌아오기를 줄여 보세요.")
    _map(data["meet"], f'{data["meet"]["time"]} 모여요', fits + rest, lambda r: f'{r["need_min"]}분' if r["fits"] else "부족",
         lambda r: "#2f7a50" if r["fits"] else "#8a8f8b", "freemap")
    md('<div class="legend"><span><i style="background:#8ccb9f"></i>가고 오기</span><span><i style="background:#f2c6b6"></i>기다림</span>'
       '<span><i style="background:#ffc94a"></i>식사</span><span><i style="background:#dce2da"></i>여유</span><span>┃ 모이는 시간</span><span>(숫자는 분)</span></div>')
    for t, lst in [("시간 안에 다녀와요", fits), ("시간이 모자라요", rest)]:
        if not lst:
            continue
        md(f'<div class="sec">{t} <span class="n">{len(lst)}곳</span></div>')
        for r in lst:
            scale = max(data["left_min"], r["need_min"])
            seg = lambda v, cls, lab: f'<span class="{cls}" style="width:{v / scale * 100}%" title="{lab} {v}분">{str(v) if v / scale > .07 else ""}</span>'
            bar = (f'<div class="tb">{seg(r["walk_min"], "w", "가기")}{seg(r["wait_min"], "q", "기다림")}{seg(r["meal_min"], "m", "식사")}'
                   f'{seg(r["walk_min"], "w", "오기")}{seg(r["buffer_min"], "b", "여유")}<i style="left:{data["left_min"] / scale * 100}%"></i></div>')
            tag = f'<span class="tag good">{r["back_by"]} 도착 · {r["spare_min"]}분 남아요</span>' if r["fits"] else f'<span class="tag warn">{-r["spare_min"]}분 모자라요</span>'
            md(f'<div class="card {"" if r["fits"] else "soft"}"><div><b style="font-size:16px">{E(r["name"])}</b> <span class="small muted">{E(r["kind"])}</span></div>'
               f'<div>{tag}</div>{bar}{_marks(r["marks"])}' + (f'<div class="note">{E(r["note"])}</div>' if r["note"] else "") + "</div>")
            if r["fits"]:
                _pick(r, f"free_pick_{r['id']}")
    md(f'<div class="note">식당 정보: {E(src)}. 기다림과 식사 시간은 가게 종류로 어림한 값이에요. 걷는 길은 직선 거리의 1.3배로 어림했어요.</div>')
    st.button("위치 다시 잡기", width="stretch", key="free_regeo", on_click=_set, kwargs={"geo": None})
