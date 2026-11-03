"""모시고: 가족 메뉴판 도우미 (모바일 웹앱, Streamlit)."""
import os

import streamlit as st

st.set_page_config(page_title="모시고 · 가족 메뉴판 도우미", page_icon="🐢", layout="centered", initial_sidebar_state="collapsed")

# 키는 Streamlit secrets(배포) 또는 환경 변수(로컬)에서 읽는다
for k in ("ANTHROPIC_API_KEY", "CLOVA_OCR_URL", "CLOVA_OCR_SECRET", "KAKAO_REST_KEY", "GEOAPIFY_KEY"):
    try:
        if k in st.secrets and not os.environ.get(k):
            os.environ[k] = str(st.secrets[k])
    except Exception:  # secrets 파일이 없을 때
        pass

from core import menu2, store  # noqa: E402
from ui import screens  # noqa: E402
from ui.common import CSS, E, md, momo, nav  # noqa: E402

s = st.session_state
if "code" not in s:
    # 기기 코드: 주소의 ?me= (다른 기기에서 불러올 때) > 이 브라우저 쿠키 > 새로 만들기
    code = st.query_params.get("me") or st.context.cookies.get("moshigo_me")
    if not code or len(code) != 6:
        code = store.new_code()
    s.code = code
    s.people = screens.clean_examples(store.load_or_default(code, menu2.START_PEOPLE))
    store.save(code, s.people)
    s.dev = st.query_params.get("dev") == "1"  # 개발자 확인용 (예시 메뉴판 버튼)
    s.view = "start"
    s.picks = {}
    s.cookie_set = False
if "me" in st.query_params:
    # 주소에 코드를 남기지 않는다: 링크를 공유해도 받은 사람이 내 입맛 목록을 같이 고치지 않게
    del st.query_params["me"]
if not s.get("cookie_set"):
    import streamlit.components.v1 as components
    components.html(f'''<script>document.cookie = "moshigo_me={s.code}; max-age=31536000; path=/; SameSite=Lax";
try {{ window.parent.document.cookie = "moshigo_me={s.code}; max-age=31536000; path=/; SameSite=Lax"; }} catch (e) {{}}</script>''', height=0)
    s.cookie_set = True

st.markdown(CSS, unsafe_allow_html=True)
act = [p["name"] for p in s.people if p.get("active", True)]
md(f'<div class="top"><div class="brand">{momo(32)}<span>모시고</span></div>'
   + (f'<span class="pill">{E(" · ".join(act))}</span>' if act and s.view != "start" else "") + "</div>")

has_scan = bool(s.get("scan"))
view = s.view
if view in ("menu", "dish", "combo", "order", "survey") and not has_scan:
    view = "scan"
page = {
    "start": screens.start, "people": screens.people, "edit": screens.edit, "scan": screens.scan, "menu": screens.menu,
    "dish": screens.dish, "survey": screens.survey, "combo": screens.combo, "order": screens.order_card, "free": screens.free, "nearby": screens.nearby_view,
}.get(view, screens.start)
try:
    page()
except Exception as e:  # 화면을 그리다 오류가 나면 내부 기록 대신 안내를 보여 준다
    if type(e).__name__ in ("StopException", "RerunException", "RerunData"):
        raise
    import traceback
    print("[page error]", view, repr(e)); traceback.print_exc()
    md('<div class="card warnbox"><div><b>이 화면을 여는 중에 문제가 생겼어요.</b><br>잠시 뒤 다시 해 주세요. 계속 그러면 메뉴판을 다시 찍어 주세요.</div></div>')
    st.button("처음 화면으로", type="primary", width="stretch", on_click=nav, args=("start",), key="err_home")

# 아래 탭바
if view != "start":
    tabs = [("people", "사람", ":material/group:", True),
            ("menu" if has_scan else "scan", "메뉴판", ":material/menu_book:", True),
            ("combo", "조합", ":material/restaurant:", has_scan),
            ("order", "주문", ":material/receipt_long:", has_scan),
            ("free", "자유식", ":material/schedule:", True)]
    cur = {"edit": "people", "dish": "menu", "survey": "menu", "nearby": "menu", "scan": "menu" if has_scan else "scan"}.get(view, view)
    with st.container(key="tabbar"):
        cols = st.columns(len(tabs))
        for col, (key, label, icon, ok) in zip(cols, tabs):
            col.button(label, icon=icon, key=f"tab_{key}", disabled=not ok, width="stretch",
                       type="primary" if (cur == key or (key == "menu" and cur == "scan")) else "secondary",
                       on_click=nav, args=(key,))
