"""간단 모드: 링크를 받은 한 사람(부모님)이 메뉴판만 찍으면 되는 큰 글씨 화면."""
import json

import streamlit as st
import streamlit.components.v1 as components

from core import order, simple
from .common import ALLERGENS, E, VCLASS, VMARK, avatar, josa, md, nav

HEADS = {"편히": "편히 먹을 수 있어요", "조심": "조심해서 드세요", "피하기": "피하는 게 좋아요"}
CLS = {"편히": "easy", "조심": "care", "피하기": "avoid"}

CSS = """<style>
.stApp{font-size:19px}
.h1{font-size:29px!important}
.sub{font-size:17px!important;line-height:1.55!important}
.note{font-size:15px!important}
.stButton>button{min-height:58px;font-size:18px}
.stButton>button p{font-size:18px}
[data-testid="stBaseButton-primary"]{min-height:64px!important;font-size:19px!important}
[data-testid="stBaseButton-primary"] p{font-size:19px!important}
[data-testid="stBaseButton-tertiary"]{min-height:44px!important}
[data-testid="stBaseButton-tertiary"] p{font-size:16px!important}
[data-testid^="stBaseButton-pills"]{min-height:44px}
[data-testid^="stBaseButton-pills"] p{font-size:16px}
[data-testid="stFileUploaderDropzone"]{align-items:stretch}[data-testid="stFileUploaderDropzone"]>span{width:100%}
[data-testid="stFileUploaderDropzone"] button{width:100%!important;min-height:150px;flex-direction:column;align-items:center;justify-content:center;gap:8px}
[data-testid="stFileUploaderDropzone"] button::before{width:56px;height:56px}
[data-testid="stFileUploaderDropzone"] button::after{content:"메뉴판 찍기";font-size:30px}
.st-key-tabbar button{min-height:60px!important}
.st-key-tabbar button p{font-size:15px!important}
.st-key-tabbar button [data-testid="stIconMaterial"]{font-size:26px}
.ssec{display:flex;align-items:center;gap:8px;font-size:21px;font-weight:700;margin-top:14px}
.ssec .n{font-size:16px;font-weight:400;color:var(--muted)}
.ssec .vm{width:28px;height:28px;font-size:16px}
[class*="st-key-stap_"]{position:relative;background:var(--surface);border:1px solid var(--hair);border-left:7px solid var(--accent);border-radius:18px;padding:14px 16px}
[class*="st-key-stap_care"]{border-left-color:var(--sun)}
[class*="st-key-stap_"] [data-testid="stElementContainer"]:has(.stButton){position:absolute!important;inset:0;z-index:2;margin:0!important}
[class*="st-key-stap_"] .stButton,[class*="st-key-stap_"] .stButton>button{width:100%!important;height:100%!important}
[class*="st-key-stap_"] button{opacity:0!important;min-height:100%!important}
.si{display:flex;flex-direction:column;gap:5px}
.si .nm{font-size:23px;font-weight:700;line-height:1.35}
.si .pr,.sd .pr{font-size:20px;font-weight:700;white-space:nowrap}
.si .og,.sd .og{font-size:15px;color:var(--muted);font-style:italic}
.si .lk,.sd .lk{font-size:18px;font-weight:700;color:var(--accent-text);line-height:1.45}
.si .why{font-size:17px;line-height:1.5}
.si .more{align-self:flex-end;font-size:15px;font-weight:700;color:var(--accent-text)}
.savoid{display:flex;flex-direction:column;gap:0}
.savoid div{padding:10px 0;border-bottom:1px dashed var(--hair);font-size:17px;line-height:1.5}.savoid div:last-child{border-bottom:0}
.savoid b{display:block;font-size:19px}.savoid span{color:var(--warn)}
.sd{display:flex;flex-direction:column;gap:8px}
.sd .vb{display:inline-flex;align-items:center;gap:8px;font-size:19px;font-weight:700}
.sd .vb .vm{width:32px;height:32px;font-size:18px}
.sd .diff{font-size:17px;color:var(--muted);line-height:1.5}
.sd .why{font-size:18px;line-height:1.5}.sd .why.v-avoid{color:var(--warn);font-weight:700}
.sd .guide .g{grid-template-columns:96px minmax(0,1fr)}.sd .guide .g b,.sd .guide .g div{font-size:17px}
.stx{display:flex;flex-direction:column;gap:6px;font-size:17px;line-height:1.5}
.stx b{margin-right:6px}
.oc .lbl{font-size:15px!important}.oc .ko{font-size:15px!important;margin-top:2px}
</style>"""


def person():
    s = st.session_state
    return next((p for p in s.people if p["id"] == s.get("simple")), None)


def leave():
    """전체 화면으로: 간단 모드를 끄고 저장된 '오늘 같이' 목록으로 다시 판정한다."""
    from .screens import rejudge

    s = st.session_state
    s.simple, s.cookie_set = None, False
    if (s.get("scan") or {}).get("provider") == "foodguide" or s.get("scan_raw"):
        rejudge()
    s.view = "menu" if s.get("scan") else "people"


def escape_button():
    st.button("전체 화면으로", icon=":material/open_in_full:", type="tertiary", key=f"simple_leave_{st.session_state.view}", on_click=leave)


def tastes(p):
    rows = [("좋아하는 음식", ", ".join(p.get("favorites") or []) or "아직 안 골랐어요"),
            ("못 먹는 것", ", ".join(p.get("cannot") or [])), ("알레르기", ", ".join(p.get("allergies") or []))]
    return '<div class="card soft stx">' + "".join(f"<div><b>{t}</b>{E(v)}</div>" for t, v in rows if v) + "</div>"


# ---------------- 찍기 ----------------
def scan():
    from .screens import run_scan

    s = st.session_state
    p = person()
    md(f'<div class="hero">{avatar(p.get("relation", "가족"), 76)}<div class="h1">메뉴판을 찍어 주세요</div>'
       f'<div class="sub">메뉴판을 찍으면 {"내" if p["id"] == "me" else E(p["name"])} 입맛에 맞는 순서로 보여요.</div></div>')
    warn = s.pop("scan_warn", None)
    if warn:
        st.warning(warn)
    if s.get("dev"):
        from .screens import example_picker
        example_picker("simple")
    else:
        up = st.file_uploader("메뉴판 사진", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed", key="simple_up")
        if up is not None:
            st.image(up.getvalue(), width="stretch")
            if st.button("이 사진으로 읽기", type="primary", width="stretch", key="simple_read"):
                run_scan(up.getvalue(), up.type or "image/jpeg")
    md(f'<div class="sec">{E(p["name"])} 입맛</div>' + tastes(p))
    escape_button()


# ---------------- 메뉴 목록 ----------------
def match_line(x):
    m = x["match"]
    if not m:
        return '<div class="og" style="font-style:normal">처음 먹어 보는 맛이에요</div>'
    return f'<div class="lk">좋아하는 {E(m["food"])}{josa(m["food"], "과", "와")} {E(m["level"])}</div>'


def menu():
    s = st.session_state
    scan = s.scan
    p = person()
    md(f'<div class="h1">{E(scan.get("restaurant") or "메뉴판")}</div>'
       f'<div class="sub">{"내" if p["id"] == "me" else E(p["name"])} 입맛에 맞는 순서예요. 메뉴를 누르면 자세히 보여요.</div>')
    if s.get("scan_note"):
        st.info(s.scan_note)
    g = simple.groups(scan, p["id"])
    for v in ("편히", "조심"):
        if not g[v]:
            continue
        md(f'<div class="ssec {VCLASS[v]}"><span class="vm">{VMARK[v]}</span>{HEADS[v]} <span class="n">{len(g[v])}개</span></div>')
        for it, x in g[v]:
            with st.container(key=f"stap_{CLS[v]}_{it['id']}"):
                tag = ' <span class="tag sun">가게 추천</span>' if it.get("chef_pick") else ""
                md(f'<div class="si"><div class="row"><div class="nm">{E(it["name_ko"])}{tag}</div><span class="pr">{E(it["price"])}</span></div>'
                   f'<div class="og">{E(it["name_orig"])}</div>{match_line(x)}'
                   + (f'<div class="why">{E(x["reason"])}</div>' if v != "편히" and x["reason"] else "")
                   + '<div class="more">자세히 보기 ›</div></div>')
                st.button(it["name_ko"], key=f"sopen_{it['id']}", on_click=nav, args=("sdish",), kwargs={"dish_id": it["id"]})
    if g["피하기"]:
        v = "피하기"
        md(f'<div class="ssec {VCLASS[v]}"><span class="vm">{VMARK[v]}</span>{HEADS[v]} <span class="n">{len(g[v])}개</span></div>'
           '<div class="card savoid">' + "".join(f'<div><b>{E(it["name_ko"])}</b><i class="og">{E(it["name_orig"])}</i><br><span>{E(x["reason"])}</span></div>'
                                                 for it, x in g[v]) + "</div>")
    if not any(g.values()):
        md('<div class="card soft">이 메뉴판에서 고를 만한 요리를 찾지 못했어요. 다시 찍어 주세요.</div>')
    if s.get("simple_picks"):
        st.button(f"주문 카드 보기 ({len(s.simple_picks)}개 담음)", type="primary", width="stretch", on_click=nav, args=("order",), key="smenu_order")
    escape_button()


# ---------------- 메뉴 하나 ----------------
def add_pick(iid):
    picks = st.session_state.setdefault("simple_picks", [])
    if iid not in picks:
        picks.append(iid)
    st.session_state.view = "order"


def drop_pick(iid):
    st.session_state.simple_picks = [i for i in st.session_state.get("simple_picks", []) if i != iid]


def dish():
    s = st.session_state
    p = person()
    it = next((i for i in s.scan["items"] if i["id"] == s.get("dish_id")), None)
    x = next((x for x in (it or {}).get("per") or [] if x["id"] == p["id"]), None)
    st.button("메뉴 목록으로", icon=":material/arrow_back:", type="tertiary", on_click=nav, args=("menu",), key="sdish_back")
    if not it or not x:
        md('<div class="card soft">이 메뉴를 찾지 못했어요.</div>')
        return
    v, m = x["verdict"], x["match"]
    h = (f'<div class="sd"><div class="vb {VCLASS[v]}"><span class="vm">{VMARK[v]}</span>{HEADS[v]}</div>'
         f'<div class="row"><div class="h1" style="margin:0">{E(it["name_ko"])}</div><span class="pr" style="padding-top:6px">{E(it["price"])}</span></div>'
         f'<div class="og">{E(it["name_orig"])}</div>')
    if m:
        h += f'<div class="lk">좋아하는 {E(m["food"])}{josa(m["food"], "과", "와")} {E(m["level"])}</div><div class="diff">{E(m["difference"])}</div>'
    else:
        h += '<div class="diff">처음 먹어 보는 맛이에요.</div>'
    if v != "편히" and x["reason"]:
        h += f'<div class="why {VCLASS[v]}">{E(x["reason"])}</div>'
    rows = [("어떤 맛", it.get("taste_line") or ", ".join(it.get("taste_kw", []))), ("한식에 빗대면", it.get("ko_compare"))]
    g = "".join(f'<div class="g"><b>{t}</b><div>{E(w)}</div></div>' for t, w in rows if w)
    if g:
        h += f'<div class="card guide">{g}</div>'
    al = [c for c in it.get("contains") or [] if c in ALLERGENS]
    if al:
        h += f'<div class="diff">들어 있어요: {E(", ".join(al))}</div>'
    md(h + "</div>")
    from .screens import asks_view
    asks_view([(it, q) for q in it.get("staff_asks") or []], s.scan, "sdish")
    if it["id"] in s.get("simple_picks", []):
        st.button("주문 카드 보기", type="primary", width="stretch", on_click=nav, args=("order",), key="sdish_order")
        st.button("담은 메뉴에서 빼기", width="stretch", on_click=drop_pick, args=(it["id"],), key="sdish_drop")
    else:
        st.button("이 메뉴로 주문하기", type="primary", width="stretch", on_click=add_pick, args=(it["id"],), key="sdish_add")
    st.button("더 자세히 보기", width="stretch", on_click=nav, args=("dish",), key="sdish_full")


# ---------------- 주문 카드 ----------------
def order_view():
    from .screens import active, asks_view, speak_block

    s = st.session_state
    scan = s.scan
    picks = [i for i in s.get("simple_picks", []) if any(it["id"] == i for it in scan["items"])]
    md('<div class="h1">주문 카드</div>')
    if not picks:
        md('<div class="sub">메뉴 목록에서 메뉴를 누르고 <b>이 메뉴로 주문하기</b>를 누르면 여기에 담겨요.</div>')
    slot = st.container()  # 카드를 위에 두고, 부탁할 것은 그 아래에서 고른다
    reqs = st.pills("부탁할 것 더하기", list(order.REQUESTS), selection_mode="multi", key="sorder_reqs") or []
    card = order.card(scan, active(), [{"item_id": i, "count": 1} for i in picks], reqs)
    h = f'<div class="oc big" lang="{card["lang"]}"><div class="lbl">직원에게 이 화면을 보여 주세요</div>'
    if card["first"]:
        h += '<div class="first">' + "".join(f'<div><b>{E(t)}</b><span class="ko">{E(k)}</span></div>' for t, k in zip(card["first"], card["first_ko"])) + "</div>"
    h += f'<div class="hello">{E(card["hello"])}</div>'
    h += "".join(f'<div class="ln"><b>{o["count"]} × {E(o["orig"])}</b><span class="ko">{E(o["ko"])}{(" · " + E(o["price"])) if o["price"] else ""}</span></div>' for o in card["order"])
    h += "".join(f'<div class="ln"><b style="font-size:21px">{E(r["orig"])}</b><span class="ko">{E(r["ko"])}</span></div>' for r in card["requests"])
    sp = lambda t: order.speakable(t, card["lang"])
    whole = sp(" ".join([*card["first"], card["hello"], *[f'{o["count"]} {o["orig"]}' for o in card["order"]], *[r["orig"] for r in card["requests"]], card["thanks"]]))
    with slot:
        md(h + f'<div class="hello">{E(card["thanks"])}</div></div>')
        if card.get("note"):
            st.info(card["note"])
        speak_block([(whole, "직원에게 들려주세요", "카드 읽어 주기")], card["voice"], 70)
    byid = {it["id"]: it for it in scan["items"]}
    asks_view([(byid[i], q) for i in picks for q in byid[i].get("staff_asks") or []], scan, "sorder", names=True)
    st.button("메뉴 더 고르기", width="stretch", on_click=nav, args=("menu",), key="sorder_more")
    if picks:
        st.button("담은 메뉴 비우기", width="stretch", on_click=lambda: s.update(simple_picks=[]), key="sorder_clear")


# ---------------- 사람 화면: 링크 보내기 ----------------
def share_section():
    s = st.session_state
    others = [p for p in s.people if p["id"] != "me" and p.get("relation") != "나"]
    if not others:
        return
    md('<style>[class*="st-key-pair_share"] button{min-height:46px!important;font-size:15px!important}</style>'
       '<div class="sec">따로 식사할 때 보낼 링크</div>'
       '<div class="note">받은 사람은 메뉴판만 찍으면 돼요. 그 사람 입맛에 맞는 메뉴부터 큰 글씨로 보여요.</div>')
    for r in range(0, len(others), 2):
        with st.container(key=f"pair_share_{r}"):
            cols = st.columns(2)
            for col, p in zip(cols, others[r:r + 2]):
                on = s.get("share_for") == p["id"]
                col.button(f'{p["name"]}에게 보낼 링크', key=f"share_{p['id']}", width="stretch", type="primary" if on else "secondary",
                           on_click=lambda pid=p["id"], on=on: s.update(share_for=None if on else pid))
    p = next((p for p in others if p["id"] == s.get("share_for")), None)
    if p:
        try:
            base = simple.base_url(st.context.url, st.context.headers.get("host"))
        except Exception:
            base = simple.base_url(None, st.context.headers.get("host"))
        share_box(simple.link(base, s.code, p["id"]), p["name"])


def share_box(url, name):
    """링크 상자: 휴대폰 공유 창(카카오톡 등)으로 보내거나 주소를 복사한다."""
    text = f"{name}, 식당에서 이 링크를 열고 메뉴판을 찍어 보세요. {name} 입맛에 맞는 메뉴부터 보여요."
    components.html(
        '<style>body{margin:0;font-family:"Noto Sans KR",system-ui,sans-serif;color:#22302a}'
        '.u{font-size:13px;padding:10px 12px;border:1px solid #b9c2b7;border-radius:12px;background:#f7f8f4;word-break:break-all;line-height:1.45;user-select:all}'
        '.b{display:flex;gap:8px;margin-top:8px}button{flex:1;min-height:46px;border-radius:14px;font:700 15px "Noto Sans KR",system-ui,sans-serif;'
        'border:1px solid #dce2da;background:#fff;color:#22302a;cursor:pointer}button.p{background:#2f7a50;color:#fff;border-color:transparent}'
        'button:active{transform:scale(.97)}.m{font-size:12px;color:#2f7a50;font-weight:700;min-height:17px;margin-top:6px}</style>'
        f'<div class="u">{E(url)}</div><div class="b"><button class="p" onclick="share()">보내기</button><button onclick="copy()">주소 복사</button></div><div class="m" id="m"></div>'
        f'<script>const U={json.dumps(url)}, T={json.dumps(text, ensure_ascii=False)};'
        'const say=(t)=>{document.getElementById("m").textContent=t};'
        'async function copy(){let ok=false;for(const n of [navigator,window.parent&&window.parent.navigator]){try{if(n&&n.clipboard){await n.clipboard.writeText(U);ok=true;break}}catch(e){}}'
        'if(!ok){const t=document.createElement("textarea");t.value=U;document.body.appendChild(t);t.select();try{ok=document.execCommand("copy")}catch(e){}t.remove()}'
        'say(ok?"주소를 복사했어요. 카카오톡 대화창에 붙여 넣어 주세요.":"위 주소를 길게 눌러 복사해 주세요.")}'
        'async function share(){for(const n of [window.parent&&window.parent.navigator,navigator]){try{if(n&&n.share){await n.share({title:"모시고",text:T,url:U});return}}'
        'catch(e){if(e&&e.name==="AbortError")return}}copy()}</script>', height=132)
