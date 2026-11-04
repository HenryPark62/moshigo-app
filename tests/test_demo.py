"""개발 모드 예시 데이터: API 없이 메뉴판 화면을 채울 수 있어야 한다."""
from core import demo, menu2


def test_examples_load_and_enrich_without_api():
    for ex in demo.EXAMPLES:
        raw, img = demo.raw(ex["key"], menu2.DEFAULT_PEOPLE)
        assert img[:2] == b"\xff\xd8"  # JPEG
        scan = menu2.enrich(raw, menu2.DEFAULT_PEOPLE)
        assert len(scan["items"]) >= 10 and scan["judged"]
        assert menu2.combos(scan, menu2.DEFAULT_PEOPLE)


def test_example_for_place():
    assert demo.for_place({"name": "Sawadee", "kind": "태국 음식"}) == "thai"
    assert demo.for_place({"name": "Le Grand Colbert", "kind": "프랑스 음식"}) == "paris"


def test_people_without_verdict_are_dropped_from_raw():
    raw, _ = demo.raw("thai", [{"name": "나"}])
    assert all({g["name"] for g in it["people"]} <= {"나"} for it in raw["items"])


def test_example_map_data_is_usable():
    from core import freemeal, nearby
    ex = demo.near()
    assert len(ex["places"]) >= 20 and len(ex["spots"]) >= 20
    assert {s["group"] for s in ex["spots"]} <= set(nearby.CATS)
    d = freemeal.plan(menu2.DEFAULT_PEOPLE, "12:00", "13:30", 10, {"name": "x", **ex["geo"]}, ex["places"])
    assert any(r["fits"] for r in d["restaurants"])
