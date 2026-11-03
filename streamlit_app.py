"""모시고: 가족 메뉴판 도우미 (모바일 웹앱, Streamlit)."""
import os

import streamlit as st

st.set_page_config(page_title="모시고 · 가족 메뉴판 도우미", page_icon="🐢", layout="centered", initial_sidebar_state="collapsed")

# 키는 Streamlit secrets(배포) 또는 환경 변수(로컬)에서 읽는다
for k in ("ANTHROPIC_API_KEY", "CLOVA_OCR_URL", "CLOVA_OCR_SECRET"):
    try:
        if k in st.secrets and not os.environ.get(k):
            os.environ[k] = str(st.secrets[k])
    except Exception:  # secrets 파일이 없을 때
        pass

from core import menu2, store  # noqa: E402
from ui import screens  # noqa: E402
from ui.common import CSS, E, md, momo  # noqa: E402

s = st.session_state
if "code" not in s:
    code = st.query_params.get("me")
    if not code or store.load(code) is None:
        code = code if code and len(code) == 6 else store.new_code()
    s.code = code
    s.people = store.load_or_default(code, menu2.DEFAULT_PEOPLE)
    store.save(code, s.people)
    s.view = "start"
    s.picks = {}
if st.query_params.get("me") != s.code:
    st.query_params["me"] = s.code

st.markdown(CSS, unsafe_allow_html=True)
act = [p["name"] for p in s.people if p.get("active", True)]
md(f'<div class="top"><div class="brand">{momo(32)}<span>모시고</span></div>'
   + (f'<span class="pill">{E(" · ".join(act))}</span>' if act and s.view != "start" else "") + "</div>")

has_scan = bool(s.get("scan"))
view = s.view
if view in ("menu", "dish", "combo", "order", "survey") and not has_scan:
    view = "scan"
{
    "start": screens.start, "people": screens.people, "edit": screens.edit, "scan": screens.scan, "menu": screens.menu,
    "dish": screens.dish, "survey": screens.survey, "combo": screens.combo, "order": screens.order_card, "free": screens.free,
}.get(view, screens.start)()

# 아래 탭바
if view != "start":
    tabs = [("people", "사람", ":material/group:", True),
            ("menu" if has_scan else "scan", "메뉴판", ":material/menu_book:", True),
            ("combo", "조합", ":material/restaurant:", has_scan),
            ("order", "주문", ":material/receipt_long:", has_scan),
            ("free", "자유식", ":material/schedule:", True)]
    cur = {"edit": "people", "dish": "menu", "survey": "menu", "scan": "menu" if has_scan else "scan"}.get(view, view)
    with st.container(key="tabbar"):
        cols = st.columns(len(tabs))
        for col, (key, label, icon, ok) in zip(cols, tabs):
            if col.button(label, icon=icon, key=f"tab_{key}", disabled=not ok, width="stretch",
                          type="primary" if (cur == key or (key == "menu" and cur == "scan")) else "secondary"):
                s.view = key
                st.rerun()
