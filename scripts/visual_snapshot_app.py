"""실제 앱 화면의 결정적 캡처 진입점. 운영 배포에서는 실행하지 않는다.

MOSHIGO_SNAPSHOT=1 MOSHIGO_CAPTURE_ROOT=/absolute/source/root \
    streamlit run scripts/visual_snapshot_app.py
화면 선택: ?case=menu-translated (목록: tests/visual/manifest.json)
"""
import copy
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import time

if os.environ.get("MOSHIGO_SNAPSHOT") != "1":
    raise RuntimeError("MOSHIGO_SNAPSHOT=1 is required for the visual capture harness")

HARNESS_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(os.environ.get("MOSHIGO_CAPTURE_ROOT", str(HARNESS_ROOT)))
if not SOURCE_ROOT.is_absolute() or not (SOURCE_ROOT / "streamlit_app.py").is_file():
    raise RuntimeError("MOSHIGO_CAPTURE_ROOT must be an absolute application source root")
SOURCE_ROOT = SOURCE_ROOT.resolve()
sys.path.insert(0, str(SOURCE_ROOT))

import streamlit as st

# 프로세스마다 격리한다. 운영 DB 및 실제 사용자 후기는 읽지 않는다.
@st.cache_resource
def capture_directory():
    return tempfile.TemporaryDirectory(prefix="moshigo-visual-")

os.environ["MOSHIGO_DB"] = str(Path(capture_directory().name) / "capture.sqlite")

from core import menu2, ocr, webmenu


def blocked_provider(*args, **kwargs):
    raise RuntimeError("External provider disabled by visual snapshot harness")


# 사진/웹 버튼을 눌러도 실제 API를 호출하지 않는다. 결과 화면은 로컬 시드만 사용한다.
ocr.read = blocked_provider
menu2.read_menu = blocked_provider
menu2.read_menu_text = blocked_provider
webmenu.read_web = blocked_provider

manifest = json.loads((HARNESS_ROOT / "tests/visual/manifest.json").read_text("utf-8"))
cases = {case["id"]: case for case in manifest["cases"]}
case_id = st.query_params.get("case", "menu-translated")
if case_id not in cases:
    st.error("Unknown snapshot case. See tests/visual/manifest.json.")
    st.stop()
case = cases[case_id]
native = (SOURCE_ROOT / "core/foodguide_flow.py").exists()
if native:
    from concurrent.futures import Future
    from core import dish_images, menu_prices
    def no_photo_lookup(query):
        result = Future()
        result.set_result(None)
        return result
    dish_images._schedule = no_photo_lookup
    menu_prices._rate = lambda currency: {"date": "2026-11-04", "base": currency, "quote": "KRW", "rate": 1501.84} if currency == "EUR" else None

bundle = json.loads((HARNESS_ROOT / "tests/visual/fixtures/foodguide-paris.json").read_text("utf-8")) if native else None

if case.get("action") in {"processing", "provider-error"}:
    # 실제 API 없이 운영 처리 경로에 고정된 공급자 응답을 연결한다.
    os.environ["ANTHROPIC_API_KEY"] = "snapshot-placeholder-not-a-real-key"
    os.environ.pop("CLOVA_OCR_URL", None)
    os.environ.pop("CLOVA_OCR_SECRET", None)
    def preview_read(*args):
        if case["action"] == "provider-error":
            raise RuntimeError("Controlled provider failure for snapshot")
        if len(args) > 3:
            args[3]("메뉴의 이름을 읽고 있어요")
        time.sleep(20)
        return json.loads((SOURCE_ROOT / "core/data/demo_paris.json").read_text("utf-8"))
    menu2.read_menu = preview_read
    if native:
        import httpx
        from core import foodguide_flow, foodguide_client, foodguide_references
        os.environ["FOODGUIDE_API_URL"] = "https://snapshot.example.test"
        os.environ["FOODGUIDE_API_KEY"] = "snapshot-placeholder"
        class PreviewClient(foodguide_client.Client):
            def __init__(self, config):
                self.gets = 0
                def handle(request):
                    job_id = "f" * 32
                    if request.method == "POST" and request.url.path == "/v1/jobs/image":
                        return httpx.Response(202, json={"job_id": job_id, "status": "queued", "status_url": "/ignored"})
                    if request.method == "GET" and request.url.path == f"/v1/jobs/{job_id}":
                        self.gets += 1
                        if case["action"] == "provider-error":
                            return httpx.Response(200, json={"job_id": job_id, "status": "failed", "error": {"code": "analysis_failed", "message": "Controlled failure"}})
                        if self.gets > 1:
                            time.sleep(20)
                        return httpx.Response(200, json={"job_id": job_id, "status": "running", "progress": {"stage": "comparison", "percent": 85, "message": "Fixture"}})
                    raise RuntimeError("Unexpected external request in snapshot harness")
                super().__init__(config, transport=httpx.MockTransport(handle))
        foodguide_flow.Client = PreviewClient

if st.session_state.get("_capture_case") != case_id:
    st.session_state.clear()
    if native:
        from core import foodguide_images
        def snapshot_images(items, session):
            return {item["id"]: {"status": "completed", "photo": dict(dish_images._illustration(item), label="예시 이미지"), "message": ""} for item in items}
        foodguide_images.ensure_images = snapshot_images
        foodguide_images.retry_images = blocked_provider
    people = copy.deepcopy(menu2.DEFAULT_PEOPLE)
    simple_id = case.get("simple")
    active = [p for p in people if p["id"] == simple_id] if simple_id else people
    raw = json.loads((SOURCE_ROOT / "core/data/demo_paris.json").read_text("utf-8"))
    if native:
        from core import foodguide_flow, foodguide_references
        summary = [r for r in bundle["reference_summary"] if r["id"] in {p["id"] for p in active}]
        scan = foodguide_flow.build_scan(bundle["report"], active, summary, bundle["metadata"])
    else:
        scan = menu2.enrich(copy.deepcopy(raw), active)
        scan["combos"] = menu2.combos(scan, active)
    if case.get("web"):
        scan["source"] = {"kind": "web", "url": "https://example.test/menu", "title": "예시 식당 메뉴", "site": "example.test", "own": True}
    dish = next(i for i in scan["items"] if i["name_orig"] == case["dish"])
    combo_index = next((n for n, c in enumerate(scan["combos"])
                        if c["kind"] == case.get("combo", "all")), 0)
    st.session_state.update(
        _capture_case=case_id, code="vis234", people=people, cookie_set=True,
        dev=False, view=case["view"], simple=simple_id, alone=False, trip="free",
        picks={}, scan_raw=raw, scan=scan,
        scan_img=(SOURCE_ROOT / "core/data/paris_menu.jpg").read_bytes(),
        scan_note=None, scan_source="demo", dish_id=dish["id"],
        menu_mode_w=case.get("menu_mode", "번역만"), combo_idx=combo_index,
        combo_w=scan["combos"][combo_index]["title"] if scan["combos"] else None,
        simple_picks=[dish["id"]] if case.get("selected") else [],
        edit_id=case.get("profile", "me"), order_big=case.get("large", False),
    )
    if native:
        picked = ([dish["id"]] if case.get("selected") else []) if simple_id else scan["group"]["menu_ids"]
        st.session_state.update(scan_report=bundle["report"], foodguide_summary=summary,
                                foodguide_metadata=bundle["metadata"], foodguide_people_signature=foodguide_references.signature(active),
                                foodguide_owner="vis234", foodguide_stale=False,
                                foodguide_reference_cache={"foods": copy.deepcopy(bundle["reference_foods"])},
                                foodguide_picks={iid: 1 for iid in picked},
                                fg_menu_mode="입맛 비교" if case.get("menu_mode") == "누가 먹을까" else case.get("menu_mode", "번역만"),
                                fg_order_large=case.get("large", bool(simple_id)))
        st.session_state.pop("scan_raw", None)
        if case.get("action"):
            config = foodguide_flow.Config.from_env()
            import hashlib
            st.session_state.foodguide_reference_cache["scope"] = foodguide_references._hash([config.base_url, hashlib.sha256(config.api_key.encode()).hexdigest()])
    if case.get("web"):
        st.session_state.scan_img = None
    if case.get("details"):
        st.session_state[f"more_{dish['id']}"] = True
    if case["view"] == "scan":
        for key in ("scan", "scan_raw", "scan_img"):
            st.session_state.pop(key, None)

# 주변 화면은 이번 시드 범위 밖이다. 사용자가 이동해도 외부 위치/지도 API를 호출하지 않는다.
from ui import screens
screens.geo_block = lambda *args, **kwargs: None

runpy.run_path(str(SOURCE_ROOT / "streamlit_app.py"), run_name="__main__")
st.markdown(f'<span data-capture-ready="{case_id}" style="display:none"></span>', unsafe_allow_html=True)
