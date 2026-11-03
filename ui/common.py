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
/* 버튼 */
.stButton>button,.stDownloadButton>button,.stFormSubmitButton>button{min-height:48px;border-radius:14px;font-weight:700;font-size:15px;border:1px solid var(--hair);background:var(--surface);color:var(--ink);box-shadow:none}
.stButton>button:hover{border-color:var(--accent);color:var(--accent-text)}
[data-testid="stBaseButton-primary"]{background:var(--accent)!important;color:#fff!important;border-color:transparent!important;min-height:54px!important;font-size:16px!important}
[data-testid="stBaseButton-primary"] p{color:#fff!important}
[data-testid="stBaseButton-tertiary"]{min-height:32px!important;padding:0!important;color:var(--accent-text)!important;text-decoration:underline;font-weight:700}
/* 위 머리 */
.top{display:flex;align-items:center;justify-content:space-between;padding:10px 0 6px;border-bottom:1px solid var(--hair);margin:0 -16px;padding-left:12px;padding-right:12px;background:var(--surface)}
.top .brand{display:flex;align-items:center;gap:6px;font-family:var(--display);font-size:24px}
.pill{display:inline-block;padding:4px 12px;border-radius:999px;background:var(--tint-sun);font-size:12px;font-weight:700}
.pill.ink{background:var(--ink);color:#fff}
.h1{font-family:var(--display);font-size:26px;line-height:1.3;margin:8px 0 2px}
.h2d{font-family:var(--display);font-size:22px;line-height:1.3}
.sub{color:var(--muted);font-size:14px;line-height:1.6}
.small{font-size:13px}.muted{color:var(--muted)}
.sec{font-size:17px;font-weight:700;margin-top:6px;display:flex;gap:8px;align-items:baseline}
.sec .n{font-size:13px;color:var(--muted)}
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
.marks{list-style:none;margin:2px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:6px 12px}
.marks li{display:inline-flex;align-items:center;gap:5px;font-size:13px}.marks b{white-space:nowrap}
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
.hero{display:flex;flex-direction:column;align-items:center;text-align:center;gap:6px;padding:18px 0 4px}
/* 입력 */
[data-testid="stTextInput"] input,[data-testid="stTimeInput"] input{min-height:46px;border-radius:12px;font-size:16px}
[data-testid="stWidgetLabel"] p{font-weight:700;font-size:14px}
[data-testid="stFileUploaderDropzone"]{border-radius:18px;background:var(--sun);border:0;padding:22px}
[data-testid="stFileUploaderDropzone"] *{color:#22302a!important}
[data-testid="stFileUploaderDropzoneInstructions"] span{font-size:15px;font-weight:700}
div[data-testid="stExpander"] details{border-radius:16px;border:1px solid var(--hair);background:var(--surface)}
/* 큰 선택 버튼 */
.st-key-choices button{min-height:84px;justify-content:flex-start;text-align:left;padding:14px 16px;border-width:2px}
.st-key-choices button p{font-size:15px;line-height:1.5}
.st-key-choices [data-testid="stBaseButton-primary"]{background:var(--tint-green)!important;color:var(--ink)!important;border:2px solid var(--accent)!important;min-height:84px!important}
.st-key-choices [data-testid="stBaseButton-primary"] p{color:var(--ink)!important}
/* 메뉴 줄 */
[class*="st-key-mrow_"]{background:var(--surface);border:1px solid var(--hair);border-radius:16px;padding:12px 14px 8px}
[class*="st-key-mrow_"] [data-testid="stVerticalBlock"]{gap:4px}
[class*="st-key-mrow_"] .stButton{display:flex;justify-content:flex-end}
[class*="st-key-mrow_"] .stButton>button{min-height:34px;padding:0 12px;font-size:13px;border-radius:999px}
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
[class*="st-key-pair"] button{min-height:42px;font-size:14px}
[data-testid="stBaseButton-primaryFormSubmit"]{background:var(--accent)!important;color:#fff!important;border:0!important;min-height:54px!important}
[data-testid="stBaseButton-primaryFormSubmit"] p{color:#fff!important;font-size:16px!important}
/* 사진 올리기: 영어 안내 대신 우리말 */
[data-testid="stFileUploaderDropzoneInstructions"]{display:none!important}
[data-testid="stFileUploaderDropzone"]{justify-content:center}
[data-testid="stFileUploaderDropzone"] button{font-size:0!important;min-height:64px;width:100%;border-radius:14px;border:3px dashed #22302a!important;background:transparent!important}
[data-testid="stFileUploaderDropzone"] button::after{content:"메뉴판 찍기 · 사진 고르기";font-size:20px;font-weight:700;font-family:"Gowun Dodum",sans-serif;color:#22302a}
[data-testid="stFileUploaderDropzone"]{min-height:auto}
.st-key-tabbar button [data-testid="stIconMaterial"]{font-size:22px}
.st-key-tabbar button>div{flex-direction:column;gap:0}
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


def josa(word, a, b):
    ch = re.sub(r"[^가-힣]", "", word or "")[-1:]
    if not ch:
        return b
    return a if (ord(ch) - 0xAC00) % 28 else b


def level(bars):
    return '<span class="lv">' + "".join(f'<i class="{"on" if i <= bars else ""}"></i>' for i in (1, 2, 3)) + "</span>"


def chips(items, cls="kw"):
    return '<div class="chips">' + "".join(f'<span class="{cls}">{E(x)}</span>' for x in items) + "</div>"


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


def go(view, **kw):
    st.session_state.view = view
    for k, v in kw.items():
        st.session_state[k] = v
    st.rerun()
