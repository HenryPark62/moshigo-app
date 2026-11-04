"""사진/웹 메뉴 → Food Guide 작업 → 화면 데이터. 외부 호출과 렌더링을 분리한다."""
from copy import deepcopy
import hashlib
import json
import os

from .foodguide_client import Client, Config, FoodGuideError
from . import foodguide_references as references
from . import store


LANGUAGES = {"ko": "한국어", "en": "영어", "fr": "프랑스어", "ja": "일본어", "zh": "중국어",
             "es": "스페인어", "it": "이탈리아어", "de": "독일어", "th": "태국어", "vi": "베트남어"}
CONTEXT_FIELDS = ("original_name", "korean_name", "pronunciation", "description", "price", "confidence")


def enabled():
    """기존 경로는 명시적 legacy 설정에서만 사용한다."""
    return os.environ.get("MOSHIGO_ANALYSIS_PROVIDER", "foodguide").strip().lower() != "legacy"


def _strings(value):
    return [x for x in value if isinstance(x, str)] if isinstance(value, list) else []


def _string(value, default=""):
    return value if isinstance(value, str) else default


def build_scan(report, people, reference_summary=None, metadata=None):
    """API의 전역 유사도와 개인 점수를 분리하며, 없는 값은 만들지 않는다."""
    metadata = metadata or {}
    people = [p for p in people if p.get("active", True)]
    by_id = {p["id"]: p for p in people}
    summary = deepcopy(reference_summary or [])
    refs = {r["id"]: r for r in summary}
    items = []
    for index, row in enumerate(report["items"]):
        context = row.get("menu_context") or {}
        profile = row.get("profile")
        profile = profile if isinstance(profile, dict) else None
        original = _string(context.get("original_name")) or row["input_name"]
        korean = _string(context.get("korean_name")) or _string((profile or {}).get("name")) or original
        description = _string((profile or {}).get("description"))
        if not description:
            facts = []
            for label, field in (("주재료", "main_ingredients"), ("조리법", "cooking_methods")):
                values = _strings((profile or {}).get(field))
                if values:
                    facts.append(f"{label}: {', '.join(values[:4])}")
            description = " · ".join(facts)
        per_by_id = {p["name"]: p for p in row.get("preferences", []) if p.get("name") in by_id}
        personal = []
        for person in people:
            pref, ref = per_by_id.get(person["id"], {}), refs.get(person["id"], {})
            personal.append({"id": person["id"], "name": person["name"], "score": pref.get("score"),
                             "eligible": pref.get("eligible"), "reasons": _strings(pref.get("reasons")),
                             "ingredient_check": _string(pref.get("ingredient_check")),
                             "reference_count": ref.get("resolved", 0), "reference_total": ref.get("total", len(person.get("favorites", [])))})
        iid = "fg-" + hashlib.sha256(f"{index}:{row['input_name']}".encode()).hexdigest()[:16]
        items.append({"id": iid, "input_name": row["input_name"], "name_orig": original,
                      "name_ko": korean, "reading": _string(context.get("pronunciation")) or _string((profile or {}).get("pronunciation")),
                      "price": _string(context.get("price")),
                      "desc_ko": description, "description_original": _string(context.get("description")),
                      "status": row["status"], "profile": deepcopy(profile),
                      "matches": deepcopy(row.get("matches", [])), "preferences": personal,
                      "text": _string(row.get("text")), "candidates": deepcopy(row.get("candidates", [])),
                      "weak_match": bool(row.get("weak_match")), "semantic_used": bool(row.get("semantic_used"))})
    by_input = {i["input_name"]: i for i in items}
    raw_group = report.get("group") or {}
    group = {"menu_names": [], "menu_ids": [], "member_coverage": [], "uncovered_members": [], "text": "", "limitations": ""}
    if len(people) >= 2:
        names = [n for n in _strings(raw_group.get("menu_names")) if n in by_input and by_input[n]["status"] == "ok"]
        coverage = []
        for row in raw_group.get("member_coverage", []):
            pid = row.get("name")
            name = row.get("menu_name")
            if pid not in by_id or name not in names:
                continue
            pref = next((p for p in by_input[name]["preferences"] if p["id"] == pid), {})
            if pref.get("eligible") is not True or pref.get("score") is None:
                continue
            coverage.append({**row, "person_id": pid, "name": by_id[pid]["name"]})
        covered = {row["person_id"] for row in coverage}
        group = {"menu_names": names if coverage else [], "menu_ids": [by_input[n]["id"] for n in names] if coverage else [],
                 "member_coverage": coverage, "uncovered_members": [p["name"] for p in people if p["id"] not in covered],
                 "text": _string(raw_group.get("text")), "limitations": _string(raw_group.get("limitations"))}
    extraction = report.get("extraction") or {}
    currency = {key: extraction.get(key, "") for key in ("currency_code", "currency_source", "currency_evidence")} if extraction.get("currency_source") in {"printed", "inferred"} else deepcopy(metadata.get("currency") or {})
    code = _string(extraction.get("language")) or _string(metadata.get("language_code"))
    warnings = _strings(report.get("warnings")) + _strings(metadata.get("warnings"))
    for ref in summary:
        if ref.get("not_applied"):
            warnings.append(f"{ref['name']}: {', '.join(ref['not_applied'])} 항목은 이번 비교 조건에 반영되지 않았어요. 음식 설명과 재료를 확인해 주세요.")
    return {"provider": "foodguide", "report": deepcopy(report), "items": items,
            "restaurant": _string(metadata.get("restaurant")) or "메뉴판", "language_code": code,
            "currency": currency,
            "menu_language": LANGUAGES.get(code.replace("_", "-").split("-")[0].lower(), code or "외국어"),
            "people": [{"id": p["id"], "name": p["name"]} for p in people], "group": group,
            "warnings": list(dict.fromkeys(warnings)), "reference_summary": summary,
            "source": deepcopy(metadata.get("source") or {}), "combos": []}


def stale(people, session):
    scan = session.get("scan") or {}
    if scan.get("provider") != "foodguide":
        return False
    owner_changed = "foodguide_owner" in session and session["foodguide_owner"] != session.get("code")
    return owner_changed or bool(session.get("foodguide_stale")) or session.get("foodguide_people_signature") != references.signature(people)


def invalidate(session):
    if (session.get("scan") or {}).get("provider") == "foodguide":
        session["foodguide_stale"] = True
        session["foodguide_picks"] = {}
        session["simple_picks"] = []


def restart(session):
    """새 작업 요청 버튼에서만 호출. 기존 서버 작업을 취소하는 기능은 아니다."""
    session["foodguide_jobs"] = {}
    session.pop("foodguide_gate", None)
    session.pop("foodguide_error", None)


def clear_analysis(session):
    """기기 코드 변경 시 이전 코드의 사진·작업·주문 선택을 넘기지 않는다."""
    exact = {"scan", "scan_report", "scan_raw", "scan_img", "scan_source", "scan_note", "scan_warn",
             "dish_id", "picks", "simple_picks", "combo_w", "combo_idx", "place", "hurry", "_fg_ui_error"}
    for key in list(session):
        if key in exact or key.startswith(("foodguide_", "fg_")):
            del session[key]


def _store_error(session, error):
    session["foodguide_error"] = {"code": error.code, "message": error.message,
                                   "retry_after": error.retry_after, "job_id": error.job_id}


def _complete(report, people, summary, metadata, pending, session):
    scan = build_scan(report, people, summary, metadata)
    session["scan"] = scan
    session["scan_report"] = deepcopy(report)
    session["foodguide_summary"] = deepcopy(summary)
    session["foodguide_metadata"] = deepcopy(metadata)
    session["foodguide_people_signature"] = references.signature(people)
    session["foodguide_owner"] = session.get("code")
    session["foodguide_stale"] = False
    session["foodguide_pending"] = pending
    session["scan_source"] = "foodguide"
    session["scan_note"] = None
    session["scan_img"] = None if pending.get("kind") == "web" else pending.get("image") or session.get("scan_img")
    session["foodguide_picks"] = {}
    session["simple_picks"] = []
    session["picks"] = {}
    session.pop("foodguide_error", None)
    session.pop("scan_raw", None)  # 기존 8축 판정/조합 경로가 API 결과를 다시 해석하지 않게 한다.
    if not session.get("place") or (session.get("hurry") or {}).get("id") != session["place"].get("id"):
        session["hurry"] = None
    session["place"] = None
    return scan


def _execute(pending, people, session, on_progress):
    owner = session.get("code")
    def require_owner():
        if session.get("code") != owner:
            raise FoodGuideError("session_changed", "기기 코드가 바뀌어 이전 분석을 표시하지 않았어요. 현재 입맛으로 다시 요청해 주세요.")
    session["foodguide_pending"] = pending
    invalidate(session)
    try:
        with Client(Config.from_env()) as client:
            # 기존 앱의 일일 요청 한도는 유지하되, 같은 작업 조회에는 다시 차감하지 않는다.
            request = {k: v for k, v in pending.items() if k != "image"}
            if pending.get("image") is not None:
                request["image_sha256"] = hashlib.sha256(pending["image"]).hexdigest()
            scope = [client.config.base_url, hashlib.sha256(client.config.api_key.encode()).hexdigest()]
            gate = hashlib.sha256(json.dumps([scope, references.signature(people), request],
                                             sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if session.get("foodguide_gate") != gate:
                if not store.take_scan():
                    raise FoodGuideError("daily_limit", "오늘 메뉴 분석 요청 한도를 다 썼어요. 내일 다시 해 주세요.")
                session["foodguide_gate"] = gate
            jobs = session.setdefault("foodguide_jobs", {})
            cache = session.setdefault("foodguide_reference_cache", {})
            preferences, summary = references.resolve(people, client, jobs, cache, on_progress)
            require_owner()
            session["foodguide_summary"] = deepcopy(summary)
            metadata = pending.get("metadata") or {}
            if on_progress:
                on_progress({"stage": "starting", "percent": 0, "message": "메뉴 분석을 시작해요"})
            if pending["kind"] == "image":
                report = client.run_image(pending["image"], pending["mime"], preferences=preferences,
                                          state=jobs, operation_key="analysis-image", on_progress=on_progress)
            else:
                report = client.run_text(pending["menus"], preferences, pending.get("context"),
                                         state=jobs, operation_key="analysis-text", on_progress=on_progress)
            require_owner()
            return _complete(report, people, summary, metadata, pending, session)
    except FoodGuideError as error:
        if session.get("code") == owner:
            _store_error(session, error)
        raise


def run_image(data, mime, people, session, on_progress=None):
    # 입력 제한은 업로드 전에 UI에서도 안내하고, 클라이언트가 다시 검증한다.
    if not isinstance(data, bytes) or not 0 < len(data) <= 15 * 1024 * 1024 or mime not in {"image/jpeg", "image/png", "image/webp"}:
        error = FoodGuideError("invalid_image", "JPG·PNG·WebP 형식의 15MB 이하 사진을 올려 주세요.")
        _store_error(session, error)
        raise error
    metadata = {"restaurant": (session.get("place") or {}).get("name", "")}
    pending = {"kind": "image", "image": data, "mime": mime, "metadata": metadata}
    return _execute(pending, people, session, on_progress)


def reread_image(people, session, on_progress=None):
    """사용자가 다시 읽기를 누르면 완료된 사진 작업만 새로 요청한다."""
    jobs = session.get("foodguide_jobs") or {}
    entry = jobs.get("analysis-image") or {}
    if session.get("foodguide_pending") and (session.get("foodguide_error") or entry.get("job_id") and "result" not in entry):
        return resume(people, session, on_progress=on_progress)
    data = session.get("scan_img")
    if isinstance(data, bytes) and data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif isinstance(data, bytes) and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        mime = "image/jpeg"
    if not isinstance(data, bytes) or not data:
        raise FoodGuideError("invalid_image", "다시 읽을 사진이 없어요. 메뉴판 사진을 올려 주세요.")
    if "result" in entry:
        jobs.pop("analysis-image", None)
    session.pop("foodguide_gate", None)
    return run_image(data, mime, people, session, on_progress=on_progress)


def _web_input(found, place):
    head = found["head"]
    menus, context, warnings = [], {}, []
    for line in head.get("lines", []):
        name = _string(line.get("name_orig")).strip()
        if not name:
            continue
        if name in context:
            warnings.append("같은 이름의 웹 메뉴는 첫 항목만 비교했어요. 가격과 선택지는 원문에서 확인해 주세요.")
            continue
        if len(menus) == 20:
            warnings.append("웹 메뉴는 앞쪽 20개까지 비교했어요. 나머지는 해당 부분을 따로 촬영해 주세요.")
            break
        menus.append(name)
        context[name] = {"original_name": name, "description": _string(line.get("note")), "price": _string(line.get("price"))}
    if not menus:
        raise FoodGuideError("menu_not_found", "비교할 메뉴가 없어요. 메뉴판을 촬영해 주세요.")
    return {"kind": "web", "menus": menus, "context": context,
            "metadata": {"restaurant": head.get("restaurant") or place.get("name", ""),
                         "language_code": head.get("language_code", ""), "source": found.get("source") or {},
                         "warnings": warnings}}


def run_web(place, people, session, on_progress=None):
    # 웹 검색만 기존 구현을 재사용한다. describe_list/Claude 메뉴 설명은 호출하지 않는다.
    from . import webmenu
    session["foodguide_pending"] = {"kind": "web_lookup", "place": deepcopy(place)}
    invalidate(session)
    try:
        Config.from_env()  # 검색 비용이 발생하기 전에 연결 설정부터 확인한다.
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise FoodGuideError("web_not_configured", "웹 메뉴 검색이 연결되지 않았어요. 메뉴판을 촬영해 주세요.")
        progress = (lambda message: on_progress({"stage": "starting", "percent": 0, "message": message})) if on_progress else None
        found = webmenu.find_menu(place, progress)
        if not found:
            raise FoodGuideError("menu_not_found", "이 식당의 웹 메뉴를 확인하지 못했어요. 메뉴판을 촬영해 주세요.")
        return _execute(_web_input(found, place), people, session, on_progress)
    except FoodGuideError as error:
        _store_error(session, error)
        raise


def resume(people, session, on_progress=None):
    pending = session.get("foodguide_pending")
    if isinstance(pending, dict) and pending.get("kind") == "web_lookup":
        return run_web(pending["place"], people, session, on_progress)
    if not isinstance(pending, dict) or pending.get("kind") not in {"image", "web", "text"}:
        raise FoodGuideError("no_pending", "이어 볼 분석이 없어요. 메뉴판을 다시 선택해 주세요.")
    return _execute(pending, people, session, on_progress)


def refresh(people, session, on_progress=None):
    """입맛 수정은 이미 인식한 원문/설명을 텍스트 경로로 재비교한다."""
    if session.get("foodguide_error") and session.get("foodguide_pending"):
        # 새 사진의 작업이 남아 있으면 이전 사진의 report로 덮어쓰지 않는다.
        return resume(people, session, on_progress)
    report = session.get("scan_report") or (session.get("scan") or {}).get("report")
    if not report:
        return resume(people, session, on_progress)
    menus = [i["input_name"] for i in report["items"]]
    context = {i["input_name"]: {k: v for k, v in (i.get("menu_context") or {}).items() if k in CONTEXT_FIELDS}
               for i in report["items"]}
    metadata = deepcopy(session.get("foodguide_metadata") or {})
    metadata["language_code"] = (report.get("extraction") or {}).get("language") or metadata.get("language_code", "")
    metadata["currency"] = deepcopy((session.get("scan") or {}).get("currency") or metadata.get("currency") or {})
    return _execute({"kind": "text", "menus": menus, "context": context, "metadata": metadata}, people, session, on_progress)
