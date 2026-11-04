"""Food Guide 화면에 얹는 모시고 기능 (core.fg_extras). ui.foodguide에서는 짧은 호출만 한다.

보강 설명이 없거나 실패해도 그 줄만 빠지고, 안내나 오류 문구는 보여 주지 않는다.
"""
import time

import streamlit as st

from core import fg_extras as fx, menu2, order
from .common import E, md, nav

CSS = """<style>
.fgx_card_bdg{margin-top:7px}
.fgx_card_bdg .bd{font-size:11px;padding:2px 7px}
</style>"""
POLL_LIMIT = 120  # 보강을 이만큼 기다렸는데도 안 끝나면 자동 새로고침을 멈춘다 (다음 화면 이동 때 다시 확인)


def _badges(item, n=None, small=False, cls=""):
    words = fx.badges(item, n)
    if not words:
        return ""
    return (f'<div class="bdg{" sm" if small else ""}{" " + cls if cls else ""}">'
            + "".join(f'<span class="bd {c}">{E(w)}</span>' for c, w in words) + "</div>")


def card_badges(item):
    """메뉴판 카드 이름 아래 작은 맛 뱃지 (맛·향·식감 하나씩 + 조리법)."""
    return _badges(item, 3, True, "fgx_card_bdg")


def _dish_view():
    return "sdish" if st.session_state.get("simple") else "dish"


def _enrich(scan, people, start=True):
    return fx.status(scan, people, st.session_state, start=start)


# ---------- 메뉴판 ----------
def menu_top(scan, people, fresh):
    """메뉴판 위쪽: 설명 보강을 미리 시작하고(기다리지 않음), '아는 맛과 닮은 메뉴'를 보여 준다."""
    md(CSS)
    _enrich(scan, people)
    if not fresh:
        return
    sims = fx.similar_top(scan, people, 3)
    if not sims:
        return
    md('<div class="sec">아는 맛과 닮은 메뉴 <span class="n">각자 좋아하는 음식과 비교했어요</span></div>')
    with st.container(key="simlist"):
        for n, r in enumerate(sims, 1):
            it = r["item"]
            chips = "".join(f'<span class="kw same">{E(w)}</span>' for w in r["shared"])
            with st.container(key=f"sim_{it['id']}"):
                md(f'<div class="sim"><span class="sn">{n}</span><div class="sb">'
                   f'<div class="row"><div class="name">{E(it["name_ko"])}</div><span class="price">{E(it.get("price") or "")}</span></div>'
                   f'<div class="like">{E(r["line"])}</div>'
                   + (f'<div class="chips">{chips}</div>' if chips else "") + '</div><span class="go">›</span></div>')
                st.button(f"{it['name_ko']} 보기", key=f"simopen_{it['id']}", on_click=nav, args=(_dish_view(),), kwargs={"dish_id": it["id"]})


# ---------- 메뉴 자세히 ----------
ICON = {  # ui.screens.ICON과 같은 그림
    "bowl": '<svg viewBox="0 0 24 24"><path d="M3 12h18a9 9 0 0 1-18 0z"/><path d="M9 3c-1 1.5 1 2.5 0 4.5M14 3c-1 1.5 1 2.5 0 4.5"/></svg>',
    "dome": '<svg viewBox="0 0 24 24"><path d="M3 18h18M5 18a7 7 0 0 1 14 0M12 8.5V6.5M10.5 6.5h3"/></svg>',
    "bulb": '<svg viewBox="0 0 24 24"><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.6 10.8c.7.6 1.1 1.3 1.1 2.2h5c0-.9.4-1.6 1.1-2.2A6 6 0 0 0 12 3z"/></svg>',
}


def dish_guide(item, people, fresh):
    """맛 뱃지, (보강되면) 어떤 맛?/한식에 빗대면/상상 포인트, 이런 분께 맞아요."""
    scan = st.session_state.scan
    _, data = _enrich(scan, people)
    extra = fx.extra_for(item, data)
    b = _badges(item)
    if b:
        md(b)
    food = fx.is_food(item)
    rows = [("bowl", "어떤 맛?", extra.get("taste_line"))]
    if food:
        rows += [("dome", "한식에 빗대면", extra.get("ko_compare")), ("bulb", "상상 포인트", extra.get("imagine"))]
    g = "".join(f'<div class="g"><span class="ic">{ICON[ic]}</span><b>{t}</b><div>{E(v)}</div></div>' for ic, t, v in rows if v)
    if g:
        md(f'<div class="card guide">{g}</div>')
    if not food:
        return
    fit = fx.fans(scan, item, people) if fresh else []
    foods = [f.split(" 좋아하는 ")[0] for f in fit]
    fit += [g for g in extra.get("good_for") or [] if not any(food_name in g for food_name in foods)]  # 같은 음식 이야기는 한 번만
    if fit:
        md('<div class="fit"><div class="t">이런 분께 맞아요</div>' + "".join(f'<div class="c">{E(f)}</div>' for f in fit[:4]) + "</div>")


def _kid_box(scan, item, people, extra):
    """아이 접시로 바꾸려면: 덜어 주는 법(보강), 직원에게 할 부탁, 안 먹으면 대신 시킬 메뉴. 보여 준 부탁을 돌려준다."""
    from .screens import speak_block
    child = fx.child_of(people)
    if not child or not fx.is_food(item) or fx.is_dessert(item):
        return []
    alt = fx.kid_backup(scan, child, exclude=item["id"])
    alt_html = (f'<b>{E(alt["name_ko"])}</b>' + (f' <span style="white-space:nowrap">{E(alt["price"])}</span>' if alt["price"] else "")) if alt else ""
    if fx.pref_of(item, child["id"]).get("eligible") is False:
        if alt:
            md(f'<div class="note">{E(child["name"])}에게는 대신 {alt_html}</div>')
        return []
    tw, tip = fx.kid_tweaks(item, child), extra.get("kid_tip") or ""
    if not (tw or tip or alt):
        return []
    md('<div class="sec">아이 접시로 바꾸려면' + (f' <span class="n">{E(child["name"])}</span>' if child["name"] != "아이" else "") + "</div>")
    if tip:
        md(f'<div class="card soft">{E(tip)}</div>')
    if tw:
        key = order.lang_key(scan)
        speak_block([(order.speakable(order.request_text(key, r), key), r, order.request_text(key, r)) for r in tw], order.voice(scan), 66 * len(tw) + 8)
    if alt:
        md(f'<div class="note">안 먹으면 대신 {alt_html}</div>')
    return tw


def dish_help(item, people, fresh):
    """아이 접시, 직원이 물어볼 수 있어요(보강), 직원에게 부탁하기. 맨 끝에서 보강이 끝나는지 조용히 지켜본다."""
    from .screens import asks_view, speak_block
    scan = st.session_state.scan
    state, data = _enrich(scan, people)
    extra = fx.extra_for(item, data)
    if fx.is_food(item):
        kid = _kid_box(scan, item, people, extra) if fresh else []
        asks = extra.get("staff_asks") or []
        asks_view([(item, q) for q in asks], scan, "fgdish")
        reqs = fx.dish_requests(item, people if fresh else [], skip=kid, asks=asks)
        if reqs:
            key = order.lang_key(scan)
            md(f'<div class="sec">직원에게 부탁하기 <span class="n">{E(order.LANG[key]["name"])}</span></div>')
            phr = [(order.speakable(order.request_text(key, r), key), r, order.request_text(key, r)) for r in reqs]
            speak_block(phr, order.voice(scan), 60 * len(phr) + 8)
    watch(state)


def watch(state):
    """보강이 진행 중이면 3초마다 확인하다가 끝나면(성공이든 실패든) 화면을 한 번 다시 그린다."""
    if state != "pending":
        return
    s = st.session_state
    started = next((r.get("started") for r in (s.get("fg_enrich") or {}).values() if r.get("status") == "pending"), None)
    if started and time.time() - started > POLL_LIMIT:
        return

    def check():
        if fx.status(s.scan, _people(), s, start=False)[0] != "pending":
            st.rerun()

    st.fragment(run_every="3s")(check)()


def _people():
    from .foodguide import active
    return active()


# ---------- 함께 고를 메뉴, 주문 카드 ----------
def combo_kid(scan, people):
    """함께 고를 메뉴: 아이 몫 메뉴를 아이가 안 먹을 때 대신 시킬 메뉴 한 줄."""
    child = fx.child_of(people)
    mine = fx.child_menu(scan, child)
    if not mine or len(people) < 2:
        return
    alt = fx.kid_backup(scan, child, exclude=mine["id"])
    if alt:
        md(f'<div class="note">{E(menu2.subj(child["name"]))} 안 먹으면 대신 <b>{E(alt["name_ko"])}</b>'
           + (f' <span style="white-space:nowrap">{E(alt["price"])}</span>' if alt["price"] else "") + "</div>")


def order_presets(scan, people, quantities, key="fg_order_requests"):
    """주문 카드를 처음 열 때 부탁을 미리 골라 둔다 (아이 몫 메뉴의 부탁·작은 접시, 자유식이면 빨리·계산서)."""
    from .screens import hurry_left
    if key in st.session_state:
        return
    pre = fx.order_requests(scan, people, quantities, hurry=hurry_left() is not None)
    if pre:
        st.session_state[key] = pre


def order_asks(scan, people, quantities):
    """주문 카드 아래: 담은 메뉴에 직원이 되물을 말 (보강된 경우만)."""
    from .screens import asks_view
    _, data = _enrich(scan, people, start=False)
    pairs = [(item, q) for item in scan["items"] if quantities.get(item["id"]) for q in fx.extra_for(item, data).get("staff_asks") or []]
    asks_view(pairs, scan, "fgorder", names=True)
