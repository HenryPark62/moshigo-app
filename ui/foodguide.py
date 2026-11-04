"""Food Guide 원본 분석을 보여 주는 화면. 기존 추정 필드를 만들지 않는다."""
import math
from urllib.parse import urlsplit

import streamlit as st

from core import foodguide_flow as flow, order, reviews, dish_images, menu_prices
from core.foodguide_client import FoodGuideError
from .common import E, go, md, nav


COMPARISON_SCOPE = ("즐겨 먹는 음식으로 입맛을 비교하고, 알레르기·못 먹는 재료·매운 음식과 질긴 음식 제한을 함께 확인해요. "
                    "좋아하는 맛과 아이 식습관은 이 비교 점수에 반영되지 않아요.")

STATUS = {"unknown": "이 음식의 정보를 찾지 못했어요.", "ambiguous": "같은 이름의 음식이 여러 가지라 확인이 필요해요.",
          "error": "이 음식은 분석을 마치지 못했어요.", "insufficient": "비교할 음식 정보가 부족해요."}


def active():
    from .screens import active as get_active
    people = get_active()
    return [dict(person, active=True) for person in people] if st.session_state.get("simple") else people


def _title(title, sub=""):
    md(f'<div class="h1">{E(title)}</div>' + (f'<div class="sub">{E(sub)}</div>' if sub else ""))


def _limit():
    count = len(active())
    if not 1 <= count <= 6:
        st.warning("함께 비교할 사람을 1~6명으로 골라 주세요. 사람 화면에서 오늘 같이 먹는 사람을 바꿀 수 있어요.")
        return False
    return True


def _run(action):
    if not _limit():
        return False
    with st.status("메뉴를 분석하고 있어요", expanded=True) as status:
        progress = st.progress(0)

        def update(value):
            progress.progress(max(0, min(100, int(value.get("percent", 0)))), text=str(value.get("message", "분석 중이에요")))

        try:
            action(update)
        except FoodGuideError as exc:
            st.session_state._fg_ui_error = {"code": exc.code, "message": exc.message, "retry_after": exc.retry_after}
            status.update(label="분석 상태를 확인해 주세요", state="error")
            st.warning(exc.message)
            return False
        status.update(label="분석을 마쳤어요", state="complete")
        st.session_state.pop("_fg_ui_error", None)
        for key in list(st.session_state):
            if key.startswith("fg_qty_"):
                del st.session_state[key]
        return True


def _pending():
    s = st.session_state
    error = s.get("_fg_ui_error") or s.get("foodguide_error") or {}
    if isinstance(error, FoodGuideError):
        error = {"code": error.code, "message": error.message, "retry_after": error.retry_after}
    if not isinstance(error, dict):
        error = {}
    if error.get("message"):
        st.warning(str(error["message"]))
    if error.get("retry_after"):
        st.caption(f"{error['retry_after']}초 뒤에 다시 확인해 주세요.")
    if not s.get("foodguide_pending") or not error:
        return
    code = error.get("code")
    terminal = code in {"analysis_failed", "interrupted", "daily_budget_exceeded", "budget_unavailable", "not_found"}
    terminal = terminal or bool(code) and any(isinstance(job, dict) and job.get("failed") == code
                                              for job in (s.get("foodguide_jobs") or {}).values())
    if code in {"configuration_error", "unauthorized", "not_configured", "web_not_configured"}:
        terminal = False
    if code == "submission_unknown" or terminal:
        if code == "submission_unknown":
            st.info("이전 요청이 서버에서 처리되고 있을 수 있어요. 새로 요청하면 별도 작업이 만들어질 수 있어요.")
        else:
            st.info("이 작업은 이어서 볼 수 없어요. 안내된 문제가 해결된 뒤 새 작업으로 요청해 주세요.")
        if st.button("새 작업으로 다시 요청", key="fg_restart", width="stretch"):
            flow.restart(s)
            s.pop("_fg_ui_error", None)
            if _run(lambda progress: flow.resume(active(), s, on_progress=progress)):
                go("menu")
            st.rerun()
    elif st.button("분석 이어 보기", key="fg_resume", type="primary", width="stretch"):
        if _run(lambda progress: flow.resume(active(), s, on_progress=progress)):
            go("menu")


def scan():
    s = st.session_state
    _title("메뉴판 찍기", "JPG·PNG·WebP 사진 한 장, 최대 15MB · 메뉴는 최대 20개까지 읽어요.")
    if s.pop("web_go", False) and s.get("place"):
        place = dict(s.place)
        if _run(lambda progress: flow.run_web(place, active(), s, on_progress=progress)):
            go("menu")
    _pending()
    ok = _limit()
    previous = s.get("scan_img")
    if previous and not s.get("foodguide_error"):
        if st.button("이전 사진으로 다시 읽기", width="stretch", disabled=not ok):
            if _run(lambda progress: flow.reread_image(active(), s, on_progress=progress)):
                go("menu")
    upload = st.file_uploader("메뉴판 사진", type=["jpg", "jpeg", "png", "webp"], key="fg_photo", label_visibility="collapsed")
    if upload is not None:
        data = upload.getvalue()
        if len(data) > 15 * 1024 * 1024:
            st.error("사진은 15MB 이하로 올려 주세요.")
        else:
            st.image(data, width="stretch")
            if st.button("이 사진으로 읽기", type="primary", width="stretch", disabled=not ok or (s.get("foodguide_error") or {}).get("code") == "submission_unknown"):
                if _run(lambda progress: flow.run_image(data, upload.type or "image/jpeg", active(), s, on_progress=progress)):
                    go("menu")
                st.rerun()
    if s.get("simple"):
        from .simple import person, tastes, escape_button
        p = person()
        if p:
            md('<div class="sec">내 입맛</div>' + tastes(p))
        escape_button()
    else:
        st.button("사람 바꾸기", on_click=nav, args=("people",), width="stretch")
        st.button("주변 식당 찾기", on_click=nav, args=("nearby",), width="stretch")


def _fresh():
    if st.session_state.get("foodguide_error") and st.session_state.get("foodguide_pending"):
        st.warning("새 분석이 아직 완료되지 않았어요. 아래에서 해당 작업을 확인해 주세요. 이전 결과로 다시 비교하지 않아요.")
        _pending()
        return False
    if not flow.stale(active(), st.session_state):
        return True
    st.warning("함께 먹는 사람이나 입맛이 바뀌었어요. 다시 비교하면 개인별 결과와 주문 카드를 볼 수 있어요.")
    if st.button("현재 입맛으로 다시 비교", type="primary", key="fg_refresh", width="stretch"):
        if _run(lambda progress: flow.refresh(active(), st.session_state, on_progress=progress)):
            st.rerun()
    _pending()
    return False


def _status(item):
    if item.get("status") in STATUS:
        st.info(STATUS[item["status"]])
    if item.get("weak_match"):
        st.caption("가까운 한식과도 닮은 정도가 낮아요.")


def _preferences(item, compact=False):
    rows = item.get("preferences") or []
    if not rows:
        st.caption("개인 입맛을 비교할 정보가 없어요.")
    for row in rows:
        score = row.get("score")
        label = ("연결된 비교 기준 없음" if not row.get("reference_count") else "비교 정보 부족") if score is None else f"비교 점수 {score}점"
        if compact:
            restriction = ("제한 조건 충족" if row.get("eligible") is True else
                           "제한 조건 확인 필요" if row.get("eligible") is False else "제한 조건 정보 없음")
            compact_score = f"{score}점" if score is not None else label
            md(f'<div class="small"><b>{E(str(row.get("name", "")))}</b> · {E(compact_score)} · {E(restriction)}</div>')
            continue
        md(f'<div class="card soft"><b>{E(str(row.get("name", "")))}</b><div>{E(label)}</div></div>')
        st.caption(f'비교 기준 음식 {row.get("reference_count", 0)} / {row.get("reference_total", 0)}개')
        if row.get("eligible") is False:
            st.warning("입력한 제한 조건에 맞는지 확인이 필요해요.")
        for reason in row.get("reasons") or []:
            st.write(str(reason))
        if row.get("ingredient_check"):
            st.caption(str(row["ingredient_check"]))


def _matches(item):
    matches = item.get("matches") or []
    if not matches:
        st.caption("닮은 한식 비교 정보가 없어요.")
        return
    md('<div class="sec">닮은 한식</div><div class="note">등록된 한식과 비교한 결과예요. 개인 입맛 비교와는 달라요.</div>')

    def heading(match):
        name = match.get("name") or "비교 음식 이름 없음"
        score = match.get("score")
        label = f"유사도 {score}점" if score is not None else "유사도 정보 없음"
        md(f'<div class="card soft"><b>{E(str(name))}</b><div>{E(label)}</div></div>')
        coverage = match.get("coverage")
        if isinstance(coverage, (int, float)) and not isinstance(coverage, bool) and 0 <= coverage <= 1:
            st.caption(f"비교 정보 {coverage * 100:.0f}%")

    def evidence(match, start=0, stop=None):
        for same in (match.get("similarities") or [])[start:stop]:
            st.write("닮은 점: " + str(same))
        for different in (match.get("differences") or [])[start:stop]:
            st.write("다른 점: " + str(different))

    best = matches[0]
    heading(best)
    evidence(best, stop=1)
    with st.expander("비교 근거 더 보기"):
        evidence(best, start=1)
        if best.get("notes"):
            st.write(best["notes"])
        for match in matches[1:]:
            heading(match)
            evidence(match)
            if match.get("notes"):
                st.write(match["notes"])


def _select(item, key):
    quantities = st.session_state.setdefault("foodguide_picks", {})
    if st.button("주문에 담기", key=key, width="stretch"):
        quantities[item["id"]] = max(1, quantities.get(item["id"], 0))
        st.session_state[f'fg_qty_{item["id"]}'] = quantities[item["id"]]
        go("order")


def _edit_reference(person_id):
    s = st.session_state
    if s.get("simple"):
        s.simple, s.cookie_set = None, False
        flow.invalidate(s)
    nav("edit", edit_id=person_id)


def _reference_overview(use_expander=True):
    summary = st.session_state.get("foodguide_summary") or st.session_state.scan.get("reference_summary") or []
    if isinstance(summary, dict):
        summary = summary.get("reference_summary") or []
    rows = {row.get("id"): row for row in summary}
    with st.expander("비교 기준 확인") if use_expander else st.container():
        st.caption(COMPARISON_SCOPE)
        for person in active():
            row = rows.get(person["id"])
            if row:
                st.caption(f'{person["name"]}: 비교 기준 {row.get("resolved", 0)} / {row.get("total", 0)}개 연결')
            else:
                st.caption(f'{person["name"]}: 연결된 비교 기준 정보가 없어요.')
            label = f'{person["name"]} 입맛 수정' + (" · 전체 화면" if st.session_state.get("simple") else "")
            st.button(label, key=f'fg_edit_reference_{person["id"]}', on_click=_edit_reference, args=(person["id"],), width="stretch")


MENU_TILE_CSS = """<style>
[class*="st-key-fg_menu_tile_"]{position:relative;background:var(--surface);border:2px solid var(--hair);border-radius:20px;padding:14px;gap:0!important}
[class*="st-key-fg_menu_tile_"]:hover{border-color:var(--accent)}
[class*="st-key-fg_menu_tile_"]:has(.fg_recommend_badge){border:4px solid transparent;background:linear-gradient(var(--surface),var(--surface)) padding-box,linear-gradient(120deg,#ee728d,#efbc50,#78c685,#62bde4,#9b88df,#ee728d) border-box;background-size:100% 100%,300% 300%;animation:fg_rainbow 4s ease infinite;box-shadow:0 3px 16px #9b88df18;padding-top:31px}
@keyframes fg_rainbow{0%,100%{background-position:0 0,0% 50%}50%{background-position:0 0,100% 50%}}
@media(prefers-reduced-motion:reduce){[class*="st-key-fg_menu_tile_"]:has(.fg_recommend_badge){animation:none}}
.fg_recommend_badge{position:absolute;top:-23px;left:0;font-size:10px;line-height:1.4;font-weight:750;color:#694696;background:#f4eefb;border-radius:20px;padding:2px 9px;letter-spacing:.03em;z-index:1}
[class*="st-key-fg_menu_tile_"] [data-testid="stElementContainer"]:has(.stButton){position:absolute!important;inset:0;z-index:2;margin:0!important}
[class*="st-key-fg_menu_tile_"] .stButton,[class*="st-key-fg_menu_tile_"] .stButton>button{width:100%!important;height:100%!important}
[class*="st-key-fg_menu_tile_"] .stButton>button{min-height:100%!important;background:transparent!important;border:0!important;border-radius:20px!important;box-shadow:none!important;color:transparent!important}
[class*="st-key-fg_menu_tile_"] .stButton>button p{opacity:0!important}
[class*="st-key-fg_menu_tile_"] .stButton>button:focus-visible{outline:3px solid var(--accent)!important;outline-offset:3px!important}
.fg_menu_tile_content{position:relative;display:grid;grid-template-columns:82px minmax(0,1fr) 74px;gap:8px 12px;align-items:center;min-height:116px}
.fg_menu_tile_photo{position:relative;align-self:stretch;min-height:96px;max-height:144px;border-radius:12px;overflow:hidden;background:#eeeadf}
.fg_menu_tile_photo img{width:100%;height:100%;position:absolute;inset:0;object-fit:cover}
.fg_menu_tile_photo span{position:absolute;bottom:0;left:0;right:0;background:#fffE;color:#5e6a63;text-align:center;font-size:9px;line-height:1.35;padding:3px 1px}
.fg_menu_tile_name{font-size:19px;font-weight:750;line-height:1.4;overflow-wrap:anywhere}
.fg_menu_tile_price{font-size:14px;font-weight:650;margin-top:7px;line-height:1.4}
.fg_menu_tile_krw{display:block;font-size:11px;font-weight:500;color:var(--muted);margin-top:2px}
.fg_menu_tile_reading{font-size:12px;line-height:1.5;color:var(--muted);margin-top:7px;overflow-wrap:anywhere}
.fg_menu_tile_reading span{font-size:10px;margin-right:4px}
.fg_menu_tile_score{text-align:right;color:var(--accent-text);font-variant-numeric:tabular-nums;white-space:nowrap;line-height:1.1}
.fg_menu_tile_score_label{display:block;font-size:10px;font-weight:600;color:var(--muted);letter-spacing:0;margin-bottom:5px}
.fg_menu_tile_score strong{font-size:48px;font-weight:800;letter-spacing:-2px}
.fg_menu_tile_score small{font-size:12px;margin-left:2px}
.fg_menu_tile_score.fg_menu_tile_unscored{color:var(--muted)}
.fg_menu_tile_score.fg_menu_tile_unscored small{display:block;white-space:normal;font-size:11px;margin-top:5px;margin-left:0;line-height:1.4}
.fg_menu_tile_people{grid-column:2 / -1;text-align:right;display:flex;justify-content:flex-end;gap:3px 8px;flex-wrap:wrap;font-size:10px;line-height:1.6;color:var(--muted)}
.fg_menu_tile_people .fg_restricted{color:var(--warn)}
@media(max-width:380px){.fg_menu_tile_content{grid-template-columns:64px minmax(0,1fr) 60px;gap:8px}.fg_menu_tile_name{font-size:17px}.fg_menu_tile_score strong{font-size:40px}.fg_menu_tile_price{font-size:13px}.fg_menu_tile_photo span{font-size:8px}}
</style>"""


def _menu_score(item, person_id, fresh):
    """선택한 사람의 유효한 개인 점수만 표시한다. 알 수 없는 값은 0으로 바꾸지 않는다."""
    if not fresh or item.get("status") != "ok":
        return "—", "확인 필요"
    preference = next((row for row in item.get("preferences") or [] if row.get("id") == person_id), {})
    if preference.get("eligible") is False:
        return "—", "제한 확인"
    score = preference.get("score")
    if score is None:
        return "—", "점수 없음"
    if preference.get("eligible") is not True:
        return "—", "확인 필요"
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 100:
        return "—", "점수 없음"
    return str(round(score)), "점"


def _analysis_information(fresh):
    s = st.session_state
    report = s.scan
    with st.expander("분석 정보"):
        source = report.get("source") or {}
        if source.get("kind") == "web":
            url = source.get("url") or ""
            try:
                parsed = urlsplit(url)
                valid = parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname) and not parsed.username and not parsed.password
            except (TypeError, ValueError):
                valid = False
            if valid:
                label = str(source.get("title") or source.get("site") or "원문 메뉴 페이지")
                md(f'<div class="note">인터넷에서 찾은 메뉴예요. <a href="{E(url, quote=True)}" target="_blank" rel="noopener noreferrer">{E(label)}</a></div>')
        elif s.get("scan_img"):
            st.image(s.scan_img, width="stretch")
        for warning in report.get("warnings") or []:
            st.caption(str(warning))
        if fresh:
            _reference_overview(use_expander=False)


def _menu_rank(item, people, fresh):
    """구성원 전원의 유효한 원점수 평균. 누락·제한된 사람을 분모에서 빼지 않는다."""
    if not people or any(_menu_score(item, person["id"], fresh)[1] != "점" for person in people):
        return -1
    scores = {row["id"]: row["score"] for row in item["preferences"]}
    return sum(scores[person["id"]] for person in people) / len(people)


def _group_score(item, people, fresh):
    rank = _menu_rank(item, people, fresh)
    if rank >= 0:
        return str(round(rank)), "점"
    reasons = {_menu_score(item, person["id"], fresh)[1] for person in people}
    return "—", next((reason for reason in ("확인 필요", "제한 확인", "점수 없음") if reason in reasons), "점수 없음")


def menu():
    s = st.session_state
    report = s.scan
    people = active()
    basis = f'구성원 {len(people)}명 평균' if len(people) > 1 else f'{people[0]["name"]} 기준' if people else ""
    _title(report.get("restaurant") or "메뉴판", f'메뉴 {len(report["items"])}개' + (f' · {basis}' if basis else ""))
    fresh = _fresh()
    # 점수가 같은 메뉴는 원래 순서로 유지한다. 원본 분석 배열은 바꾸지 않는다.
    items = sorted(report["items"], key=lambda item: -_menu_rank(item, people, fresh))
    recommended = {item["id"] for item in items if _menu_rank(item, people, fresh) >= 0}
    recommended = {item["id"] for item in items[:2] if item["id"] in recommended}
    extraction = report.get("currency") or (report.get("report") or {}).get("extraction") or {}
    currency = menu_prices.currency_code(extraction)
    inferred = extraction.get("currency_source") == "inferred"
    photos = dish_images.menu_images(items, report=report.get("report"), image_bytes=s.get("scan_img"))
    prices = {item["id"]: menu_prices.price_info(item.get("price"), currency) for item in items}
    md(MENU_TILE_CSS)
    for item in items:
        score, note = _group_score(item, people, fresh)
        unscored = " fg_menu_tile_unscored" if score == "—" else ""
        reading = str(item.get("reading") or "")
        pronunciation = (f'<div class="fg_menu_tile_reading"><span>읽는 법</span>{E(reading)}</div>' if reading else "")
        photo = photos[item["id"]]
        image = (f'<div class="fg_menu_tile_photo"><img src="{E(photo["src"], quote=True)}" alt="{E(item["name_ko"], quote=True)} · {E(photo["label"], quote=True)}" loading="lazy">'
                 f'<span>{E(photo["label"])}</span></div>')
        price = prices[item["id"]]
        krw = f'<span class="fg_menu_tile_krw">{E(price["krw"])}' + (' · 추정 통화' if inferred and price['krw'] else '') + '</span>' if price["krw"] else ""
        individual = []
        for person in people:
            value, reason = _menu_score(item, person["id"], fresh)
            detail = value if reason == "점" else "제한 확인" if reason == "제한 확인" else "—"
            if reason == "제한 확인":
                raw = next((row.get("score") for row in item.get("preferences", []) if row.get("id") == person["id"]), None)
                if type(raw) in (int, float) and math.isfinite(raw) and 0 <= raw <= 100:
                    detail = f"{round(raw)} · 제한"
            cls = ' class="fg_restricted"' if reason == "제한 확인" else ""
            individual.append(f'<span{cls}>{E(person["name"])}: {E(detail)}</span>')
        badge = '<span class="fg_recommend_badge">추천</span>' if item["id"] in recommended else ""
        with st.container(key=f'fg_menu_tile_{item["id"]}'):
            md(f'<div class="fg_menu_tile_content">{badge}{image}<div><div class="fg_menu_tile_name">{E(item["name_ko"])}</div>'
               f'<div class="fg_menu_tile_price">{E(price["display"] or "가격 미표기")}{krw}</div>{pronunciation}</div>'
               f'<div class="fg_menu_tile_score{unscored}"><span class="fg_menu_tile_score_label">{"평균 추천 점수" if len(people) > 1 else "추천 점수"}</span><strong>{E(score)}</strong><small>{E(note)}</small></div>'
               f'<div class="fg_menu_tile_people">{"".join(individual)}</div></div>')
            st.button(f'{item["name_ko"]} 상세 보기 · {score}{note}', key=f'fg_open_{item["id"]}', width="stretch", on_click=nav,
                      args=("sdish" if s.get("simple") else "dish",), kwargs={"dish_id": item["id"]})
    with st.expander("가격·사진 정보"):
        if currency:
            st.caption(f'메뉴 통화: {currency}' + (' · AI 추정' if inferred else ' · 메뉴판에서 확인'))
            if extraction.get("currency_evidence"):
                st.caption(str(extraction["currency_evidence"]))
        dates = sorted({price["date"] for price in prices.values() if price["date"]})
        if dates:
            st.caption(f'환율 기준일: {", ".join(dates)} · Frankfurter 기준 환율. 원화는 참고 금액이며 결제 환율·수수료에 따라 달라요.')
        if any(price["status"] == "currency_required" for price in prices.values()):
            st.caption("일부 가격의 통화를 확인하지 못해 원화 환산을 생략했어요.")
        if any(price["status"] == "unavailable" for price in prices.values()):
            st.caption("환율을 가져오지 못해 일부 원화 금액을 표시하지 못했어요.")
        st.caption("대표 사진과 종류 참고 그림은 실제 매장 음식과 다를 수 있어요.")
        seen = set()
        for photo in photos.values():
            if photo.get("source_url") and photo["source_url"] not in seen:
                seen.add(photo["source_url"])
                md(f'<div class="small"><a href="{E(photo["source_url"], quote=True)}" target="_blank" rel="noopener noreferrer">{E(photo["title"])}</a> · {E(photo["author"])} · '
                   f'<a href="{E(photo["license_url"], quote=True)}" target="_blank" rel="noopener noreferrer">{E(photo["license"])}</a> · 화면에 맞춰 잘림</div>')
    st.button("메뉴판 다시 읽기", type="tertiary", on_click=nav, args=("scan",))


def dish():
    s = st.session_state
    item = next((i for i in s.scan["items"] if i["id"] == s.get("dish_id")), None)
    st.button("메뉴판으로", on_click=nav, args=("menu",), type="tertiary")
    if not item:
        st.info("이 메뉴를 찾지 못했어요.")
        return
    _title(item["name_ko"], item["name_orig"])
    if item.get("price"):
        st.write(item["price"])
    fresh = _fresh()
    _status(item)
    if item.get("desc_ko"):
        st.write(item["desc_ko"])
    if item.get("description_original"):
        with st.expander("메뉴판 원문 설명"):
            st.write(item["description_original"])
    _matches(item)
    profile = item.get("profile") or {}
    with st.expander("맛과 재료 자세히 보기"):
        for label, field in (("맛", "taste"), ("향", "aroma"), ("식감", "texture"),
                             ("주재료", "main_ingredients"), ("양념", "seasonings"), ("조리법", "cooking_methods")):
            values = profile.get(field) or []
            if values:
                st.write(f"{label}: " + ", ".join(str(value) for value in values))
        if not profile:
            st.caption("상세 음식 정보가 없어요.")
    if fresh:
        md('<div class="sec">입맛 비교</div>')
        _preferences(item)
    st.caption("재료와 알레르기 여부는 직원에게 확인해 주세요. 입맛 점수는 안전 판정이 아니에요.")
    if fresh:
        _select(item, "fg_dish_add")
    st.button("먹어 봤어요", on_click=nav, args=("survey",), width="stretch")
    _analysis_information(fresh)
    saved = reviews.reviews(item["name_orig"], s.scan.get("restaurant", ""))
    for review in (saved.get("here") or []) + (saved.get("other") or []):
        st.write(str(review.get("text", "")))


def combo():
    _title("함께 고를 메뉴", "가족 입맛을 함께 고려한 추천이에요.")
    if not _fresh():
        return
    scan = st.session_state.scan
    group = scan.get("group") or {}
    if group.get("text"):
        st.write(str(group["text"]))
    for coverage in group.get("member_coverage") or []:
        st.write(f'{coverage["name"]}: {coverage["menu_name"]} · 비교 점수 {coverage["score"]}점')
    if group.get("limitations"):
        st.caption(str(group["limitations"]))
    if group.get("uncovered_members"):
        st.info("추천으로 입맛을 충분히 맞추지 못한 사람: " + ", ".join(str(name) for name in group["uncovered_members"]))
    ids = group.get("menu_ids") or []
    items = [item for item in scan["items"] if item["id"] in ids]
    if not items:
        st.info("함께 추천할 메뉴를 정할 정보가 부족해요. 메뉴판에서 각자 고를 수 있어요.")
    for item in items:
        with st.container(border=True):
            md(f'<div class="name">{E(item["name_ko"])}</div>')
            st.caption(item["name_orig"])
            _preferences(item, compact=True)
            _select(item, f'fg_group_{item["id"]}')
    if items and st.button("이 메뉴들을 주문에 담기", type="primary", width="stretch"):
        quantities = st.session_state.setdefault("foodguide_picks", {})
        for item in items:
            quantities[item["id"]] = max(1, quantities.get(item["id"], 0))
            st.session_state[f'fg_qty_{item["id"]}'] = quantities[item["id"]]
        go("order")
    st.button("메뉴판 보기", on_click=nav, args=("menu",), width="stretch")


def order_view():
    from .screens import speak_block
    s = st.session_state
    _title("주문 카드", "메뉴와 수량을 고른 뒤 직원에게 보여 주세요.")
    if not _fresh():
        return
    quantities = s.setdefault("foodguide_picks", {})
    lines = []
    with st.expander("메뉴와 수량 고르기", expanded=not any(quantities.values())):
        for item in s.scan["items"]:
            qty = st.number_input(item["name_ko"], min_value=0, max_value=20, value=int(quantities.get(item["id"], 0)),
                                  step=1, key=f'fg_qty_{item["id"]}')
            quantities[item["id"]] = qty
            if qty:
                lines.append({"item_id": item["id"], "count": qty})
    if not lines:
        st.info("주문할 메뉴의 수량을 1개 이상으로 골라 주세요.")
        return
    requests = st.pills("부탁할 것 더하기", order.REQUEST_KEYS, selection_mode="multi", key="fg_order_requests") or []
    card = order.card(s.scan, active(), lines, requests)
    large = st.toggle("글씨 크게", value=bool(s.get("simple")), key="fg_order_large")
    text = f'<div class="oc {"big" if large else ""}" lang="{E(card["lang"])}"><div class="lbl">직원에게 이 화면을 보여 주세요</div>'
    text += '<div class="first">' + ''.join(f'<div><b>{E(line)}</b><span class="ko">{E(ko)}</span></div>' for line, ko in zip(card["first"], card["first_ko"])) + '</div>'
    text += f'<div class="hello">{E(card["hello"])}</div>'
    for line in card["order"]:
        text += f'<div class="ln"><b>{line["count"]} × {E(line["orig"])}</b><span class="ko">{E(line["ko"])} {E(line["price"])}</span></div>'
    for request in card["requests"]:
        text += f'<div class="ln"><b>{E(request["orig"])}</b><span class="ko">{E(request["ko"])}</span></div>'
    md(text + f'<div class="hello">{E(card["thanks"])}</div></div>')
    if card.get("note"):
        st.info(card["note"])
    speak_block([(order.speakable(card["text"], card["lang"]), "직원에게 들려주세요", "카드 읽어 주기")], card["voice"], 70)


def survey():
    s = st.session_state
    item = next((i for i in s.scan["items"] if i["id"] == s.get("dish_id")), None)
    if not item:
        st.info("이 메뉴를 찾지 못했어요.")
        return
    _title("먹어 보니 어땠어요?", item["name_ko"])
    with st.form("fg_survey"):
        ordered = st.segmented_control("이 메뉴를 실제로 시켰나요?", ["네", "아니요"], default="네")
        imagine = st.segmented_control("설명만 보고 맛이 그려졌나요? (5가 가장 잘)", [1, 2, 3, 4, 5], default=4)
        stronger = st.pills("예상보다 강했던 맛", reviews.STRONG, selection_mode="multi") or []
        again = st.segmented_control("다음에도 이렇게 추천받고 싶나요?", ["네", "아니요"], default="네")
        who = st.pills("누가 먹었나요?", [p["name"] for p in active()], selection_mode="multi") or []
        comment = st.text_area("한 줄 후기", max_chars=200)
        if st.form_submit_button("보내기", type="primary", width="stretch"):
            reviews.save(s.scan.get("restaurant", ""), item["name_orig"], ordered == "네", imagine or 3, stronger, again == "네", comment, ",".join(who))
            st.toast("후기를 저장했어요")
            go("dish")
    st.caption("후기는 앱에 저장돼요. 현재 입맛 비교 점수를 바꾸지는 않아요.")
    st.button("메뉴로", on_click=nav, args=("dish",), width="stretch")


def reference_indicator(person):
    summary = st.session_state.get("foodguide_summary") or (st.session_state.get("scan") or {}).get("reference_summary") or []
    if isinstance(summary, dict):
        summary = summary.get("reference_summary") or []
    row = next((entry for entry in summary if entry.get("id") == person.get("id")), None)
    if row:
        st.caption(f'지난 비교 기준 {row.get("resolved", 0)} / {row.get("total", 0)}개 연결')


def reference_choices(person, key):
    """이미 받은 후보만 보여 주고 저장할 선택을 돌려준다. 렌더 중 API 호출 없음."""
    favorites = list(dict.fromkeys(person.get("favorites") or []))
    refs = {name: value for name, value in (person.get("foodguide_refs") or {}).items() if name in favorites}
    summary = st.session_state.get("foodguide_summary") or (st.session_state.get("scan") or {}).get("reference_summary") or []
    if isinstance(summary, dict):
        summary = summary.get("reference_summary") or []
    row = next((r for r in summary if r.get("id") == person.get("id")), None) or {}
    unresolved = {item["name"]: item for item in row.get("unresolved") or [] if item.get("name") in favorites}
    cached = (st.session_state.get("foodguide_reference_cache") or {}).get("foods") or {}
    names = [name for name in favorites if name in unresolved or name in refs and (cached.get(name) or {}).get("candidates")]
    if not row and not names:
        return refs
    md('<div class="sec">입맛 비교에 쓸 음식 확인</div>')
    if row:
        st.caption(f'즐겨 먹는 음식 {row.get("total", 0)}개 중 {row.get("resolved", 0)}개를 비교 기준으로 찾았어요.')
    for name in names:
        candidates = (unresolved.get(name) or {}).get("candidates") or (cached.get(name) or {}).get("candidates") or []
        choices = {str(c["id"]): c for c in candidates if isinstance(c, dict) and c.get("id") and c.get("name")}
        if not choices:
            st.caption(f"{name}: 비교할 음식을 찾지 못했어요.")
            continue
        saved = str((refs.get(name) or {}).get("id", ""))
        picked = st.selectbox(f"{name} — 어떤 음식인가요?", [""] + list(choices),
                              index=(list(choices).index(saved) + 1) if saved in choices else 0,
                              format_func=lambda value, choices=choices: choices[value]["name"] if value else "아직 고르지 않음",
                              key=f"fg_reference_{key}_{name}")
        if picked:
            refs[name] = {"id": choices[picked]["id"], "name": choices[picked]["name"]}
        else:
            refs.pop(name, None)
    for note in row.get("not_applied") or []:
        st.caption(str(note))
    return refs
