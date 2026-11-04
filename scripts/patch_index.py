"""Streamlit 기본 index.html의 제목과 링크 미리보기 정보를 모시고 것으로 바꾸고, 첫 로딩 화면에 거북이를 넣는다.

카카오톡, 슬랙 같은 메신저는 자바스크립트를 실행하지 않고 처음 받은 HTML만 읽는다.
st.set_page_config의 제목은 자바스크립트로 나중에 바뀌기 때문에 미리보기에는 'Streamlit'이 나온다.
그래서 배포 이미지를 만들 때 이 파일을 직접 고친다.
"""
import importlib.util
import os
import re
from pathlib import Path

import streamlit

URL = os.environ.get("PUBLIC_URL", "https://moshigo.onrender.com").rstrip("/")
TITLE = "모시고 · 가족 메뉴판 도우미"
DESC = "처음 보는 해외 메뉴판을 찍으면, 같이 먹는 사람마다 아는 음식에 빗대어 무슨 맛인지 알려 줘요."

index = Path(streamlit.__file__).parent / "static" / "index.html"
html = index.read_text("utf-8")
meta = (f'<meta name="description" content="{DESC}">'
        f'<meta property="og:type" content="website"><meta property="og:site_name" content="모시고">'
        f'<meta property="og:title" content="{TITLE}"><meta property="og:description" content="{DESC}">'
        f'<meta property="og:url" content="{URL}/"><meta property="og:image" content="{URL}/app/static/og.png">'
        f'<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
        f'<meta name="twitter:card" content="summary_large_image"><meta name="theme-color" content="#2F7A50">')
html = re.sub(r"<title>.*?</title>", f"<title>{TITLE}</title>{meta}", html, count=1, flags=re.S)
html = html.replace('<html lang="en">', '<html lang="ko">')

# 첫 로딩: Streamlit이 화면을 그리기 전(자바스크립트 받기, 서버 연결)에는 빈 화면이라
# 앱 안에서 쓰는 걷는 거북이를 index.html에 미리 넣어 두고, 위쪽 머리(.top)가 그려지면 걷어 낸다.
spec = importlib.util.spec_from_file_location("moshigo_common", Path(__file__).resolve().parent.parent / "ui" / "common.py")
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
boot = (f"<style>{common.LOADER_CSS}"
        "#moshi-boot{position:fixed;inset:0;z-index:999999;background:#f2f5ef;display:flex;align-items:center;justify-content:center;"
        "font-family:'Noto Sans KR',-apple-system,BlinkMacSystemFont,sans-serif;transition:opacity .35s}"
        "#moshi-boot.gone{opacity:0;pointer-events:none}</style>"
        f'<div id="moshi-boot">{common.loader("모시고를 여는 중이에요")}</div>'
        "<script>(function(){var b=document.getElementById('moshi-boot');"
        "function done(){if(!b)return;b.classList.add('gone');var x=b;b=null;setTimeout(function(){x.remove()},400)}"
        "var t=setInterval(function(){if(document.querySelector('.top .brand,[data-testid=\"stException\"]')){clearInterval(t);done()}},120);"
        "setTimeout(function(){clearInterval(t);done()},90000)})();</script>")
if "moshi-boot" not in html:
    html = html.replace("<body>", "<body>" + boot, 1)
index.write_text(html, "utf-8")
print("patched", index)
