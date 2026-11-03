"""화면 공통: 스타일, 거북이 모모, 작은 HTML 조각들."""
import html
import re

import streamlit as st

E = html.escape

CSS = """
<link href="https://fonts.googleapis.com/css2?family=Gowun+Dodum&family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#f2f5ef;--surface:#fff;--surface2:#f7f8f4;--ink:#22302a;--muted:#5e6a63;--hair:#dce2da;--hair-strong:#b9c2b7;
--accent:#2f7a50;--accent-text:#2f7a50;--sun:#ffc94a;--tint-sun:#fff1c7;--tint-sun2:#fff6da;--tint-green:#ddf0e3;--tint-warn:#fdebe3;
--warn:#9a3a22;--warn-line:#c2502e;--display:"Gowun Dodum","Noto Sans KR",sans-serif;--elev:0 1px 2px rgba(34,48,42,.06),0 6px 20px rgba(34,48,42,.08)}
html,body,.stApp{background:var(--bg)!important;color:var(--ink);font-family:"Noto Sans KR",system-ui,sans-serif}
.stApp *:not([data-testid="stIconMaterial"]):not(.material-symbols-rounded){font-family:"Noto Sans KR",system-ui,sans-serif}
[data-testid="stIconMaterial"]{font-family:"Material Symbols Rounded"!important}
header[data-testid="stHeader"],#MainMenu,footer,[data-testid="stToolbar"],[data-testid="stDecoration"],[data-testid="stStatusWidget"]{display:none!important}
[data-testid="stMainBlockContainer"]{max-width:480px!important;padding:0 16px 120px!important;margin:0 auto}
[data-testid="stVerticalBlock"]{gap:12px}
h1,h2,h3{color:var(--ink)!important;padding:0!important;margin:0!important}
.stMarkdown p{margin:0}
/* 한글은 낱말 단위로 줄을 바꾼다 (긴 영문 이름은 필요하면 중간에서) */
body,.stApp,[role="dialog"]{word-break:keep-all;overflow-wrap:anywhere}
/* Streamlit 기본값(margin-bottom:-16px) 때문에 글 아래가 다음 요소에 가려지던 것을 없앤다 */
[data-testid="stMarkdownContainer"]{margin-bottom:0!important}
.sub{margin-bottom:4px}
/* 버튼 */
.stButton>button,.stDownloadButton>button,.stFormSubmitButton>button{min-height:48px;border-radius:14px;font-weight:700;font-size:15px;border:1px solid var(--hair);background:var(--surface);color:var(--ink);box-shadow:none}
/* 누르는 순간 바로 반응이 보이게 */
.stButton>button{transition:transform .08s ease,background-color .08s ease}
.stButton>button:active:not(:disabled){transform:scale(.97);background:var(--tint-green)}
/* 서버가 일하는 동안 맨 위에 얇은 막대 */
.stApp[data-test-script-state="running"]::before{content:"";position:fixed;top:0;left:0;right:0;height:3px;z-index:1000;
background:linear-gradient(90deg,#2f7a50,#2f7a50);background-size:40% 100%;background-repeat:no-repeat;animation:moshi-run .9s linear infinite}
@keyframes moshi-run{from{background-position:-40% 0}to{background-position:140% 0}}
[data-testid="stBaseButton-primary"]{background:var(--accent)!important;color:#fff!important;border-color:transparent!important;min-height:54px!important;font-size:16px!important}
[data-testid="stBaseButton-primary"] p{color:#fff!important}
/* 아직 누를 수 없는 버튼은 흐리게: 초록색이 비활성 상태를 덮지 않게 */
[data-testid="stBaseButton-primary"]:disabled{background:var(--hair)!important;color:var(--muted)!important;cursor:not-allowed;opacity:1}
[data-testid="stBaseButton-primary"]:disabled p{color:var(--muted)!important}
[data-testid="stBaseButton-tertiary"]{min-height:36px!important;padding:0 14px 0 10px!important;border:1px solid var(--hair)!important;border-radius:999px!important;
background:var(--surface)!important;color:var(--ink)!important;text-decoration:none!important;font-weight:500!important;font-size:14px!important;gap:4px}
[data-testid="stBaseButton-tertiary"] p{color:var(--ink)!important;text-decoration:none!important;font-size:14px!important}
[data-testid="stBaseButton-tertiary"] [data-testid="stIconMaterial"]{font-size:18px;color:var(--ink)}
/* 위 머리 */
.top{display:flex;align-items:center;justify-content:space-between;padding:10px 0 6px;border-bottom:1px solid var(--hair);margin:0 -16px;padding-left:12px;padding-right:12px;background:var(--surface)}
.top .brand{display:flex;align-items:center;gap:6px;font-family:var(--display);font-size:24px}
.pill{display:inline-block;padding:4px 12px;border-radius:999px;background:var(--tint-sun);font-size:12px;font-weight:700}
.pill.ink{background:var(--ink);color:#fff}
.h1{font-family:var(--display);font-size:26px;line-height:1.3;margin:10px 0 4px}
.h2d{font-family:var(--display);font-size:22px;line-height:1.3}
.sub{color:var(--muted);font-size:14px;line-height:1.6}
.small{font-size:13px}.muted{color:var(--muted)}
.sec{font-size:17px;font-weight:700;margin-top:10px;display:flex;flex-wrap:wrap;gap:2px 8px;align-items:baseline}
.sec .n{font-size:13px;font-weight:400;color:var(--muted)}
.card{background:var(--surface);border:1px solid var(--hair);border-radius:18px;padding:14px 16px;display:flex;flex-direction:column;gap:8px}
.card.soft{background:var(--surface2)}
.card.warnbox{background:var(--tint-warn);border-color:transparent;color:var(--warn)}
.card.sunbox{background:var(--tint-sun2);border-color:transparent}
.row{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.name{font-size:17px;font-weight:700;line-height:1.4}
.orig{font-size:15px;font-weight:700;font-style:italic}
.reading{font-size:12px;color:var(--muted)}
.desc{font-size:14px;color:var(--muted);line-height:1.55}
.price{font-weight:700;white-space:nowrap}
.like{font-size:14px;font-weight:700;color:var(--accent-text)}
.chips{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.kw{display:inline-flex;padding:3px 10px;border-radius:999px;background:var(--surface2);border:1px solid var(--hair);font-size:13px}
.kw.food{background:var(--tint-sun2);border-color:transparent}
.kw.bad{background:var(--tint-warn);color:var(--warn);border-color:transparent;font-weight:700}
.kw.care{background:var(--tint-sun);border-color:transparent}
.kw.same{background:var(--tint-green);color:var(--accent-text);border-color:transparent;font-weight:700}
.gl{padding:3px 9px;border-radius:8px;background:var(--tint-sun2);font-size:13px}.gl b{margin-right:3px}
.tag{display:inline-block;padding:2px 9px;border-radius:999px;background:var(--surface2);font-size:12px;font-weight:700}
.tag.sun{background:var(--sun)}.tag.good{background:var(--tint-green);color:var(--accent-text)}.tag.warn{background:var(--tint-warn);color:var(--warn)}
.vm{display:inline-grid;place-items:center;width:20px;height:20px;border-radius:50%;font-size:12px;font-weight:800;flex-shrink:0;line-height:1}
.v-easy .vm,.vm.v-easy{background:var(--accent);color:#fff}.v-care .vm,.vm.v-care{background:var(--sun);color:#22302a}.v-avoid .vm,.vm.v-avoid{background:var(--warn-line);color:#fff}
.marks{list-style:none;margin:2px 0 0!important;padding:0!important;display:flex;flex-wrap:wrap;gap:6px 9px}
.marks li{display:inline-flex;align-items:center;gap:4px;font-size:13px}.marks b{white-space:nowrap}
.marks.col{flex-direction:column;gap:6px}.marks.col li{align-items:flex-start}
.marks .why{color:var(--muted)}.marks .v-avoid .why,.marks li.v-avoid .why{color:var(--warn)}
.lv{display:inline-flex;gap:2px;vertical-align:middle;margin-left:4px}.lv i{width:6px;height:13px;border-radius:2px;background:var(--hair-strong)}.lv i.on{background:var(--accent)}
.plike{padding:12px 14px;border-radius:14px;background:var(--surface2);border-left:5px solid var(--accent);display:flex;flex-direction:column;gap:6px;font-size:14px}
.plike.v-care{border-left-color:var(--sun)}.plike.v-avoid{border-left-color:var(--warn-line)}
.plike .head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:15px}
.dl{display:grid;grid-template-columns:78px 1fr;gap:10px 10px;font-size:14px;line-height:1.6}.dl dt{font-weight:700}.dl dd{margin:0}
.rv{display:flex;gap:10px;padding:10px 0;border-bottom:1px dashed var(--hair);font-size:14px;line-height:1.55}.rv:last-child{border-bottom:0}
.rv .tag{align-self:flex-start;white-space:nowrap}.rv .st{color:#e3a300;white-space:nowrap;font-size:13px}
.oc{border:2px solid var(--ink);border-radius:22px;background:var(--surface);padding:18px;display:flex;flex-direction:column;gap:12px}
.oc .lbl{font-size:12px;font-weight:700;color:var(--muted)}
.oc .first{background:var(--tint-warn);color:var(--warn);border-radius:14px;padding:12px 14px;display:flex;flex-direction:column;gap:8px}
.oc .first b{font-size:19px;line-height:1.4}.oc .ko{font-size:12px;color:var(--muted);display:block}.oc .first .ko{color:var(--warn)}
.oc .ln b{font-size:21px;line-height:1.35}.oc .hello{font-size:17px}
.oc.big .first b{font-size:25px}.oc.big .ln b{font-size:28px}.oc.big .hello{font-size:21px}
.plate{display:flex;gap:10px;padding:10px 0;border-bottom:1px dashed var(--hair)}.plate:last-child{border-bottom:0}
.av{width:34px;height:34px;flex-shrink:0;border-radius:50%;background:var(--tint-sun);display:grid;place-items:center;font-weight:700;font-size:14px}
.sum{display:grid;grid-template-columns:1fr 1fr;gap:8px}.sum div{background:var(--surface);border:1px solid var(--hair);border-radius:14px;padding:10px 12px;display:flex;flex-direction:column}
.sum span{font-size:12px;color:var(--muted)}.sum b{font-size:18px}
.tb{display:flex;height:24px;border-radius:7px;background:var(--surface2);position:relative}
.tb span{display:flex;align-items:center;justify-content:center;overflow:hidden;font-size:11px;color:#22302a;border-right:1px solid #fff;white-space:nowrap}
.tb .w{background:#8ccb9f}.tb .q{background:#f2c6b6}.tb .m{background:#ffc94a}.tb .b{background:repeating-linear-gradient(45deg,#dce2da,#dce2da 4px,#f7f8f4 4px,#f7f8f4 8px)}
.tb i{position:absolute;top:-4px;bottom:-4px;border-left:3px solid var(--ink)}
.legend{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:var(--muted)}.legend i{display:inline-block;width:12px;height:9px;border-radius:2px;margin-right:4px}
.thumb{width:100%;max-height:200px;object-fit:cover;object-position:top;border-radius:14px;border:1px solid var(--hair)}
.note{font-size:12px;color:var(--muted);line-height:1.6}
/* 위치 묻기, 쿠키 저장 같은 보이지 않는 틀은 자리를 차지하지 않게 */
[data-testid="stElementContainer"]:has(iframe[title^="streamlit_js_eval"]),[data-testid="stElementContainer"]:has(iframe[height="0"]){position:absolute!important;width:1px;height:0!important;overflow:hidden;margin:0!important}
/* 사진 위에 뜨는 작은 '전체 화면' 단추는 숨기고, 올린 사진 지우기(×)는 누르기 쉽게 */
[data-testid="stElementToolbar"]{display:none!important}
[data-testid="stFileUploaderDeleteBtn"] button{min-width:40px!important;min-height:40px!important}
.note.one-line{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hero{display:flex;flex-direction:column;align-items:center;text-align:center;gap:6px;padding:18px 0 4px}
/* 선택 버튼 묶음: 둥근 막대, 고른 것은 진한 색 */
[data-testid="stButtonGroup"] [data-testid^="stBaseButton-segmented_control"]{min-height:40px;border-radius:999px!important;border:1px solid var(--hair-strong)!important;
background:var(--surface)!important;color:var(--ink)!important;font-size:14px;margin-right:6px;padding:0 14px}
[data-testid="stButtonGroup"] [data-testid="stBaseButton-segmented_controlActive"]{background:var(--ink)!important;border-color:var(--ink)!important;color:#fff!important}
[data-testid="stButtonGroup"] [data-testid="stBaseButton-segmented_controlActive"] p{color:#fff!important;font-weight:700}
[data-testid^="stBaseButton-pills"]{min-height:36px;border-radius:999px!important;border:1px solid var(--hair-strong)!important;background:var(--surface)!important;font-size:14px}
[data-testid="stButtonGroup"] [data-testid="stBaseButton-pillsActive"],[data-testid="stBaseButton-pillsActive"]{background:var(--tint-green)!important;border-color:var(--accent)!important}
[data-testid="stBaseButton-pillsActive"] p{color:var(--accent-text)!important;font-weight:700}
/* 알림 상자: 기본 파랑, 노랑 대신 차분한 색 */
[data-testid="stAlertContainer"]{border-radius:14px!important;padding:12px 14px!important}
[data-testid="stAlertContentWarning"],[data-testid="stAlertContentInfo"]{font-size:14px;line-height:1.6}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]){background:var(--tint-warn)!important;color:var(--warn)!important}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]){background:var(--tint-sun2)!important;color:var(--ink)!important}
[data-testid="stAlertContainer"] p{color:inherit!important}
/* 입력 */
[data-testid="stTextInput"] input,[data-testid="stTimeInput"] input{min-height:46px;border-radius:12px;font-size:16px}
/* 입력칸은 테두리로 칸이라는 게 보이게 */
[data-testid="stTextInput"] [data-baseweb="input"],[data-testid="stTextArea"] [data-baseweb="textarea"],[data-testid="stTimeInput"] [data-baseweb="select"]>div,
[data-testid="stSelectbox"] [data-baseweb="select"]>div{border:1px solid var(--hair-strong)!important;border-radius:12px!important;background:var(--surface)!important}
[data-testid="stTextInput"] [data-baseweb="input"]:focus-within,[data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within{border-color:var(--accent)!important}
[data-testid="stWidgetLabel"] p{font-weight:700;font-size:14px}
[data-testid="stFileUploaderDropzone"]{border-radius:18px;background:var(--sun);border:0;padding:6px;box-shadow:0 2px 0 #e0ad2e}
[data-testid="stFileUploaderDropzone"] *{color:#22302a!important}
[data-testid="stFileUploaderDropzoneInstructions"] span{font-size:15px;font-weight:700}
[data-testid="stCheckbox"]{padding:4px 0}
div[data-testid="stExpander"] details{border-radius:16px;border:1px solid var(--hair);background:var(--surface)}
/* 큰 선택 버튼 */
.st-key-choices button{min-height:84px;justify-content:flex-start;text-align:left;padding:14px 16px;border-width:2px}
.st-key-choices button p{font-size:15px;line-height:1.5}
.st-key-choices [data-testid="stBaseButton-primary"]{background:var(--tint-green)!important;color:var(--ink)!important;border:2px solid var(--accent)!important;min-height:84px!important}
.st-key-choices [data-testid="stBaseButton-primary"] p{color:var(--ink)!important}
/* 메뉴 줄 */
[class*="st-key-mrow_"]{background:var(--surface);border:1px solid var(--hair);border-radius:16px;padding:12px 14px}
[class*="st-key-mrow_"] [data-testid="stVerticalBlock"]{gap:8px}
[class*="st-key-mrow_"] .stButton{display:flex;justify-content:flex-end}
[class*="st-key-mrow_"] .stButton>button{min-height:34px;padding:0 4px;font-size:14px;border:0;background:none;color:var(--accent-text);font-weight:700}
[class*="st-key-mrow_"] .stButton>button p{color:var(--accent-text)}
/* 사람 카드 (2열) */
[class*="st-key-pgrid_"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:10px!important;align-items:stretch}
[class*="st-key-pgrid_"] [data-testid="stColumn"]{min-width:0!important;width:auto!important;flex:1 1 0!important}
[class*="st-key-pc_"]{background:var(--surface);border:1px solid var(--hair);border-radius:18px;padding:12px 10px 10px;height:100%;justify-content:space-between}
[class*="st-key-pc_"] [data-testid="stVerticalBlock"]{gap:6px}
[class*="st-key-pc_off_"]{background:var(--surface2)}
[class*="st-key-pc_off_"] .pcard{opacity:.5}
.pcard{display:flex;flex-direction:column;align-items:center;text-align:center;gap:3px}
.pcard .pname{font-size:17px;font-weight:700;line-height:1.3}
.pcard .pmeta{font-size:12px;color:var(--muted)}
.pcard .chips{justify-content:center;margin-top:4px;gap:4px}
.pcard .kw{font-size:11.5px;padding:2px 8px}
.pcard .state{font-size:11px;font-weight:700;padding:1px 8px;border-radius:999px;background:var(--tint-green);color:var(--accent-text)}
.pcard .state.off{background:var(--hair);color:var(--muted)}
[class*="st-key-pc_"] [data-testid="stHorizontalBlock"]{gap:6px!important}
[class*="st-key-pc_"] button{min-height:34px!important;font-size:13px!important;border-radius:10px!important;background:var(--surface2)!important;border-color:transparent!important;padding:0 4px!important}
[class*="st-key-pc_"] button p{font-size:13px!important}
[class*="st-key-pgrid_"] [data-testid="stColumn"]>div{height:100%}
.st-key-padd{position:relative;height:100%;min-height:190px;border:2px dashed var(--hair-strong);border-radius:18px;justify-content:center}
.st-key-padd .pcard .pname{font-size:14px;color:var(--muted)}
/* 칸 전체를 누를 수 있게: 투명한 버튼을 위에 덮는다 */
.st-key-padd [data-testid="stElementContainer"]:has(.stButton){position:absolute!important;inset:0;z-index:2;margin:0!important}
.st-key-padd .stButton,.st-key-padd .stButton>button{width:100%!important;height:100%!important}
.st-key-padd button{opacity:0!important;min-height:100%!important}
/* 찍기 화면의 같이 먹는 사람 (작은 캐릭터) */
.mini-people{display:flex;flex-wrap:wrap;gap:8px}
.mini{flex:1 1 72px;max-width:110px;display:flex;flex-direction:column;align-items:center;gap:2px;padding:8px 4px;background:var(--surface);border:1px solid var(--hair);border-radius:14px;text-align:center}
.mini b{font-size:13px}
.mini .kw{font-size:10.5px;padding:1px 6px;margin-top:2px}
/* 가게 추천 메뉴 */
[class*="st-key-pick_"]{background:var(--tint-sun2);border:1px solid #f0d58a;border-radius:16px;padding:12px 14px}
[class*="st-key-pick_"] [data-testid="stVerticalBlock"]{gap:8px}
[class*="st-key-pick_"] .stButton>button{min-height:34px;padding:0 4px;font-size:14px;border:0!important;background:none!important;color:var(--accent-text);font-weight:700}
[class*="st-key-pick_"] .stButton>button p{color:var(--accent-text)!important}
[class*="st-key-pick_"] .stButton>button:hover p,[class*="st-key-mrow_"] .stButton>button:hover p{color:var(--accent-text)!important}
.stMarkdown a.golink,.stMarkdown a.golink:hover{text-decoration:none!important}
.golink{flex-shrink:0;font-size:13px;font-weight:700;color:var(--accent-text)!important;text-decoration:none;border:1px solid var(--hair);border-radius:999px;padding:4px 10px;background:var(--surface);white-space:nowrap}
/* 메뉴 가이드: 맛 뱃지와 설명 줄 */
.bdg{display:flex;flex-wrap:wrap;gap:6px}
.bd{display:inline-flex;align-items:center;padding:4px 11px;border-radius:999px;font-size:13px;font-weight:700;line-height:1.3}
.bd.t{background:#fde4ea;color:#a8324f}.bd.a{background:#e9e6fb;color:#4c44a0}.bd.x{background:#e1eef8;color:#2a5f8a}.bd.c{background:var(--tint-green);color:var(--accent-text)}
.bdg.sm .bd{font-size:11.5px;padding:2px 8px}
.pop{display:inline-flex;align-items:center;gap:4px;padding:2px 10px;border-radius:999px;border:1.5px solid #e8a33a;color:#b46a00;background:#fff7e8;font-size:12px;font-weight:700;vertical-align:middle}
.rvlink{display:inline-flex;align-items:center;padding:4px 12px;border-radius:999px;border:1.5px solid var(--accent);color:var(--accent-text) !important;font-size:13px;font-weight:700;text-decoration:none !important}
.guide{display:flex;flex-direction:column;padding:2px 14px}
.guide .g{display:grid;grid-template-columns:30px 82px minmax(0,1fr);gap:8px;align-items:center;padding:11px 0;border-bottom:1px dashed var(--hair-strong)}
.guide .g:last-child{border-bottom:0}
.guide .ic{width:30px;height:30px;border-radius:50%;background:var(--tint-green);display:flex;align-items:center;justify-content:center}
.guide .ic svg{width:17px;height:17px;fill:none;stroke:var(--accent-text);stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.guide .g b{font-size:14px}.guide .g div{font-size:14px;line-height:1.55}
.fit{background:var(--tint-sun2);border-radius:14px;padding:12px 14px;display:flex;flex-direction:column;gap:6px;font-size:14px}
.fit .t{font-weight:800;font-size:15px}.fit .c{display:flex;gap:8px;align-items:flex-start}.fit .c::before{content:"✓";color:var(--accent-text);font-weight:800}
/* 추천 플랜 시간표 */
.tl{display:flex;flex-direction:column;gap:0;margin-top:4px}
.tl-row{display:grid;grid-template-columns:54px minmax(0,1fr);gap:10px;align-items:start}
.tl-row>b{font-size:14px;line-height:1.35;padding-top:12px}
.tl-row>b .muted{font-size:12px;font-weight:500}
.tl-row.edge{align-items:center;padding:6px 0}
.tl-row.edge>b{padding-top:0;color:var(--accent-text)}
.tl-row.edge span{font-size:14px;font-weight:700}
.tl-walk{margin-left:64px;padding:6px 0 6px 12px;border-left:3px dotted var(--hair-strong);font-size:12px;color:var(--muted)}
.tl-card{margin:2px 0;gap:6px}
.fbline{font-size:12px;color:var(--accent-text);font-weight:700;margin-top:6px}
/* 아래 탭바 */
.st-key-tabbar{position:fixed;bottom:0;left:50%;transform:translateX(-50%);width:min(480px,100%);z-index:99;background:var(--surface);border-top:1px solid var(--hair);padding:6px 6px calc(8px + env(safe-area-inset-bottom))}
.st-key-tabbar [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:2px!important}
.st-key-tabbar [data-testid="stColumn"]{min-width:0!important;width:auto!important;flex:1 1 0!important}
.st-key-tabbar button{border:0!important;min-height:52px!important;padding:0!important;flex-direction:column;font-size:12px!important;background:none!important;width:100%}
.st-key-tabbar button p{font-size:12px!important}
.st-key-tabbar [data-testid="stBaseButton-primary"]{background:var(--tint-sun)!important;color:var(--ink)!important}
.st-key-tabbar [data-testid="stBaseButton-primary"] p{color:var(--ink)!important;font-weight:800}
/* 가로 두 칸 버튼을 휴대폰에서도 가로로 */
[class*="st-key-pair"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:8px!important}
[class*="st-key-pair"] [data-testid="stColumn"]{min-width:0!important;width:auto!important;flex:1 1 0!important}
[class*="st-key-pair"] button{min-height:40px;font-size:14px;font-weight:500}
[class*="st-key-pair_p"]{margin-top:-4px}
[class*="st-key-pair_p"] button{min-height:36px;background:var(--surface2);border-color:transparent}
[data-testid="stBaseButton-primaryFormSubmit"]{background:var(--accent)!important;color:#fff!important;border:0!important;min-height:54px!important}
[data-testid="stBaseButton-primaryFormSubmit"] p{color:#fff!important;font-size:16px!important}
/* 사진 올리기: 영어 안내 대신 우리말 */
[data-testid="stFileUploaderDropzoneInstructions"]{display:none!important}
[data-testid="stFileUploaderDropzone"]{justify-content:center}
[data-testid="stFileUploaderDropzone"]{min-height:auto}
[data-testid="stFileUploaderDropzone"] button{font-size:0!important;min-height:76px;width:100%;border:0!important;background:transparent!important;
display:flex;align-items:center;justify-content:center;gap:12px}
[data-testid="stFileUploaderDropzone"] button::before{content:"";width:34px;height:34px;flex-shrink:0;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2322302a' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 8h3l2-3h6l2 3h3v11H4z'/%3E%3Ccircle cx='12' cy='13' r='3.5'/%3E%3C/svg%3E") center/contain no-repeat}
[data-testid="stFileUploaderDropzone"] button::after{content:"메뉴판 찍기 · 사진 고르기";font-size:21px;font-family:"Gowun Dodum",sans-serif;color:#22302a}
[data-testid="stFileUploaderDropzone"]:active{transform:scale(.99)}
.st-key-tabbar button [data-testid="stIconMaterial"]{font-size:22px}
.st-key-tabbar button>div{flex-direction:column;gap:0}
/* 마우스를 올리기만 해서는 색이 바뀌지 않게: 고른 것(선택 상태)만 색이 들어간다 */
[data-testid="stBaseButton-secondary"]:hover,[data-testid="stBaseButton-secondary"]:focus:not(:active){background:var(--surface)!important;border-color:var(--hair)!important;color:var(--ink)!important;box-shadow:none!important}
[data-testid="stBaseButton-secondary"]:hover p,[data-testid="stBaseButton-secondary"]:focus p{color:var(--ink)!important}
[data-testid="stBaseButton-primary"]:hover:not(:disabled),[data-testid="stBaseButton-primary"]:focus:not(:active):not(:disabled){background:var(--accent)!important;border-color:transparent!important;box-shadow:none!important}
[data-testid="stBaseButton-tertiary"]:hover,[data-testid="stBaseButton-tertiary"]:focus{color:var(--ink)!important;background:var(--surface)!important;border-color:var(--hair)!important}
[data-testid="stButtonGroup"] [data-testid="stBaseButton-pills"]:hover,[data-testid="stButtonGroup"] [data-testid="stBaseButton-pills"]:focus:not(:active){background:var(--surface)!important;border-color:var(--hair-strong)!important;color:var(--ink)!important}
[data-testid="stButtonGroup"] [data-testid="stBaseButton-pills"]:hover p{color:var(--ink)!important}
[data-testid="stButtonGroup"] [data-testid="stBaseButton-pillsActive"]:hover{background:var(--tint-green)!important;border-color:var(--accent)!important}
[data-testid="stButtonGroup"] [data-testid="stBaseButton-segmented_control"]:hover,[data-testid="stButtonGroup"] [data-testid="stBaseButton-segmented_control"]:focus:not(:active){background:var(--surface)!important;border-color:var(--hair-strong)!important;color:var(--ink)!important}
[data-testid="stButtonGroup"] [data-testid="stBaseButton-segmented_control"]:hover p{color:var(--ink)!important}
[data-testid="stButtonGroup"] [data-testid="stBaseButton-segmented_controlActive"]:hover{background:var(--ink)!important;border-color:var(--ink)!important}
.st-key-choices [data-testid="stBaseButton-secondary"]:hover{border-color:var(--hair)!important;background:var(--surface)!important}
.st-key-choices [data-testid="stBaseButton-primary"]:hover{background:var(--tint-green)!important;border-color:var(--accent)!important}
.st-key-tabbar [data-testid="stBaseButton-secondary"]:hover,.st-key-tabbar [data-testid="stBaseButton-secondary"]:focus{background:none!important;border:0!important}
.st-key-tabbar [data-testid="stBaseButton-primary"]:hover{background:var(--tint-sun)!important}
[class*="st-key-mrow_"] .stButton>button:hover,[class*="st-key-mrow_"] .stButton>button:focus{background:none!important;border:0!important;color:var(--accent-text)!important}
[class*="st-key-mrow_"] .stButton>button:hover p{color:var(--accent-text)!important}
[class*="st-key-pair_p"] [data-testid="stBaseButton-secondary"]:hover,[class*="st-key-pair_p"] [data-testid="stBaseButton-secondary"]:focus{background:var(--surface2)!important;border-color:transparent!important}
[data-testid="stFileUploaderDropzone"]:hover{background:var(--sun)!important}
[data-testid="stExpander"] summary:hover{color:var(--ink)!important}
[data-testid="stExpander"] summary:hover svg{fill:currentColor}
</style>
"""

MOMO = """<svg viewBox="0 0 120 120" width="{s}" height="{s}" role="img" aria-label="거북이 모모"><ellipse cx="60" cy="106" rx="42" ry="6" fill="#22302A" opacity="0.12"/><path d="M18 84 q-9 1 -11 -6" fill="none" stroke="#22302A" stroke-width="3" stroke-linecap="round"/><rect x="26" y="80" width="15" height="22" rx="7.5" fill="#8CCB9F" stroke="#22302A" stroke-width="3"/><rect x="72" y="80" width="15" height="22" rx="7.5" fill="#8CCB9F" stroke="#22302A" stroke-width="3"/><path d="M18 84 C18 48 40 32 58 32 C78 32 98 48 98 84 Z" fill="#3E8E5E" stroke="#22302A" stroke-width="3" stroke-linejoin="round"/><path d="M45 50 L58 43 L71 50 L71 64 L58 71 L45 64 Z" fill="#6DBA88" stroke="#22302A" stroke-width="2.5" stroke-linejoin="round"/><path d="M32 60 L42 56 M74 56 L85 61" stroke="#22302A" stroke-width="2.5" stroke-linecap="round"/><rect x="12" y="78" width="92" height="11" rx="5.5" fill="#FFC94A" stroke="#22302A" stroke-width="3"/><circle cx="100" cy="62" r="15" fill="#8CCB9F" stroke="#22302A" stroke-width="3"/><path d="M100.5 61 q3.5 -4.5 7 0" fill="none" stroke="#22302A" stroke-width="2.5" stroke-linecap="round"/><circle cx="109" cy="67" r="3" fill="#F29C8C"/><path d="M101 68 q3 3 6 0" fill="none" stroke="#22302A" stroke-width="2" stroke-linecap="round"/><path d="M87 52 Q100 36 113 52 Z" fill="#FFC94A" stroke="#22302A" stroke-width="3" stroke-linejoin="round"/><path d="M83 52 H117" stroke="#22302A" stroke-width="3" stroke-linecap="round"/></svg>"""

VCLASS = {"편히": "v-easy", "조심": "v-care", "피하기": "v-avoid"}
VMARK = {"편히": "✓", "조심": "!", "피하기": "×"}
ALLERGENS = ["견과류", "우유", "달걀", "밀가루", "갑각류", "조개류", "생선"]


def md(h):
    """HTML 조각을 그대로 그린다. 줄바꿈과 들여쓰기는 마크다운이 코드로 읽지 않게 없앤다."""
    st.markdown(re.sub(r"\n\s*", "", h), unsafe_allow_html=True)


def momo(size=40):
    return MOMO.format(s=size)


# 관계마다 다른 거북이 캐릭터 (사람 카드용): (등껍질, 등 무늬, 모자 색 또는 None, 안경)
LOOKS = {
    "나": ("#3E8E5E", "#6DBA88", "#FFC94A", False),
    "부모님": ("#8B6B4A", "#B89574", None, True),
    "아이": ("#4C8FC9", "#86B9E3", "#E8604C", False),
    "배우자": ("#C0617F", "#E39AB2", "#FFC94A", False),
    "친구": ("#7466C4", "#A79CE3", "#FFC94A", False),
    "가족": ("#3E8E86", "#7CC2BA", None, False),
}


def avatar(relation, size=64):
    shell, plate, hat, glasses = LOOKS.get(relation, LOOKS["가족"])
    svg = MOMO.format(s=size).replace("#3E8E5E", shell).replace("#6DBA88", plate)
    hat_parts = ['<path d="M87 52 Q100 36 113 52 Z" fill="#FFC94A" stroke="#22302A" stroke-width="3" stroke-linejoin="round"/>',
                 '<path d="M83 52 H117" stroke="#22302A" stroke-width="3" stroke-linecap="round"/>']
    if hat is None:
        for h in hat_parts:
            svg = svg.replace(h, "")
    else:
        svg = svg.replace(hat_parts[0], hat_parts[0].replace("#FFC94A", hat))
    if glasses:
        svg = svg.replace("</svg>", '<circle cx="104" cy="60" r="5.5" fill="none" stroke="#22302A" stroke-width="2.2"/>'
                                    '<path d="M98.5 59 H92" stroke="#22302A" stroke-width="2.2" stroke-linecap="round"/></svg>')
    return svg


def ghost_avatar(size=64):
    """아직 없는 사람: 회색 실루엣 거북이와 초록 + 동그라미."""
    svg = MOMO.format(s=size)
    for a, b in [("#22302A", "#b9c2b7"), ("#3E8E5E", "#e4e9e1"), ("#6DBA88", "#f2f5ef"), ("#8CCB9F", "#eef1ec"), ("#FFC94A", "#e4e9e1"), ("#F29C8C", "#e4e9e1")]:
        svg = svg.replace(a, b)
    return svg.replace("</svg>", '<circle cx="96" cy="26" r="17" fill="#2f7a50"/><path d="M96 17 V35 M87 26 H105" stroke="#fff" stroke-width="4" stroke-linecap="round"/></svg>')


# 다리에 이름을 붙인 걷는 모모 (로딩 표시용)
_WALK = MOMO.replace('<rect x="26" y="80"', '<rect class="leg-b" x="26" y="80"').replace('<rect x="72" y="80"', '<rect class="leg-f" x="72" y="80"')
LOADER_CSS = """
.loader{display:flex;flex-direction:column;align-items:center;gap:10px;padding:26px 0 22px}
.loader .track{position:relative;width:200px;height:64px;overflow:hidden}
.loader .track::after{content:"";position:absolute;left:0;right:0;bottom:6px;border-bottom:2px dashed #b9c2b7}
.loader .walker{position:absolute;bottom:2px;left:0;animation:moshi-stroll 3.2s linear infinite}
.loader .walker svg{display:block}
.loader .leg-b,.loader .leg-f{transform-box:fill-box;transform-origin:50% 0}
.loader .leg-b{animation:moshi-step .36s ease-in-out infinite alternate}
.loader .leg-f{animation:moshi-step .36s ease-in-out infinite alternate-reverse}
.loader .walker svg{animation:moshi-bob .36s ease-in-out infinite alternate}
.loader .txt{font-size:15px;font-weight:700;color:#22302a}
.loader .txt i{font-style:normal;display:inline-block;width:1.2em;text-align:left;animation:moshi-dots 1.2s steps(4) infinite;overflow:hidden;vertical-align:bottom;white-space:nowrap}
.loader .sub{font-size:12px;color:#5e6a63}
@keyframes moshi-stroll{0%{transform:translateX(-60px)}100%{transform:translateX(200px)}}
@keyframes moshi-step{0%{transform:rotate(-14deg)}100%{transform:rotate(14deg)}}
@keyframes moshi-bob{0%{transform:translateY(0)}100%{transform:translateY(-2px)}}
@keyframes moshi-dots{0%{width:0}100%{width:1.2em}}
"""


def loader(text, sub=""):
    """거북이 모모가 점선 위를 걸어가는 로딩 표시."""
    return (f'<div class="loader"><div class="track"><div class="walker">{_WALK.format(s=52)}</div></div>'
            f'<div class="txt">{E(text)}<i>...</i></div>' + (f'<div class="sub">{E(sub)}</div>' if sub else "") + "</div>")


def josa(word, a, b):
    ch = re.sub(r"[^가-힣]", "", word or "")[-1:]
    if not ch:
        return b
    return a if (ord(ch) - 0xAC00) % 28 else b


def level(bars):
    return '<span class="lv">' + "".join(f'<i class="{"on" if i <= bars else ""}"></i>' for i in (1, 2, 3)) + "</span>"


def chips(items, cls="kw"):
    return '<div class="chips">' + "".join(f'<span class="{cls}">{E(x)}</span>' for x in items) + "</div>"


COOKED = {"굽기": "구운 요리", "끓이기": "끓인 요리", "날것": "날로 먹는 요리", "볶기": "볶은 요리", "부치기": "부친 요리",
          "삶기": "삶은 요리", "섞기": "버무린 요리", "오래 끓이기": "오래 끓인 요리", "찌기": "찐 요리", "튀기기": "튀긴 요리"}


def badges(it, n=None, small=False):
    """맛(분홍), 향(보라), 식감(파랑), 조리법(초록) 뱃지. n개까지만 고르게 섞어서."""
    groups = [("t", it.get("taste_kw") or []), ("a", it.get("aroma_kw") or []), ("x", it.get("texture_kw") or [])]
    out = []
    for i in range(3):
        out += [(c, l[i]) for c, l in groups if len(l) > i]
    if n:
        out = out[:n]
    if it.get("course") not in ("drink", "dessert") and it.get("cooking") in COOKED:
        out.append(("c", COOKED[it["cooking"]]))
    if not out:
        return ""
    return f'<div class="bdg{" sm" if small else ""}">' + "".join(f'<span class="bd {c}">{E(w)}</span>' for c, w in out) + "</div>"


def marks(per, reasons=False):
    if reasons:
        ok = [x for x in per if x["verdict"] == "편히"]
        rest = [x for x in per if x["verdict"] != "편히"]
        out = '<ul class="marks col">'
        if ok:
            out += f'<li class="v-easy"><span class="vm">✓</span><b>{E(", ".join(x["name"] for x in ok))}</b><span class="why">편히 먹어요</span></li>'
        for x in rest:
            out += f'<li class="{VCLASS[x["verdict"]]}"><span class="vm">{VMARK[x["verdict"]]}</span><b>{E(x["name"])}</b><span class="why">{E(x["reason"])}</span></li>'
        return out + "</ul>"
    return '<ul class="marks">' + "".join(
        f'<li class="{VCLASS[x["verdict"]]}"><span class="vm">{VMARK[x["verdict"]]}</span><b>{E(x["name"])}</b></li>' for x in per) + "</ul>"


def nav(view, **kw):
    """버튼 on_click 용: 화면을 그리기 전에 상태만 바꾼다 (다시 그리기를 한 번으로 줄인다)."""
    st.session_state.view = view
    for k, v in kw.items():
        st.session_state[k] = v


def go(view, **kw):
    st.session_state.view = view
    for k, v in kw.items():
        st.session_state[k] = v
    st.rerun()

CSS = CSS.replace("</style>", LOADER_CSS + "</style>")
