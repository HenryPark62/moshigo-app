"""패키지 자유 식사: 모이는 시간 안에 다녀올 수 있는 식당.

가기 + 기다림 + 식사 + 돌아오기 + 여유 시간이 남은 시간 안에 들어오는지 본다.
걷는 속도는 일행 가운데 가장 느린 사람 기준이다.
"""
import json
from pathlib import Path

from . import burden, menu2, world

DATA = Path(__file__).parent / "data" / "paris_places.json"
CHILD_SPEED = 1.0  # 6~9살 아이 보행 속도 초안 (m/s). 팀 검토 필요
AGE_DECADE = {"20대": 20, "30대": 30, "40대": 40, "50대": 50, "60대": 60, "70대": 70, "80대 이상": 80}


def group_speed(people):
    speeds = []
    for p in people:
        if p.get("child"):
            speeds.append((CHILD_SPEED, p["name"]))
        else:
            sp = burden.walking_speed({"sex": p.get("sex") or "female", "age_decade": AGE_DECADE.get(p.get("age"), 40),
                                       "knee": "천천히 걸어요" in (p.get("likes") or []) or p.get("slow")})
            speeds.append((sp, p["name"]))
    return min(speeds)


def _hm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def _mins(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def person_marks(dishes, people):
    """식당 대표 메뉴로 사람마다 먹을 게 있는지: 편히 / 조심 / 피하기와 가장 닮은 메뉴."""
    out = []
    if not dishes:  # 요리 종류를 모르는 가게
        return [{"id": p["id"], "name": p["name"], "mark": "조심", "dish": None, "match": None, "unknown": True} for p in people]
    for p in people:
        best = None
        for d in dishes:
            if menu2._hard_rules(d, p):
                continue
            m = world.best_match(d, p.get("favorites") or [])
            score = (m["score"] if m else 0) + (0.3 if p["id"] in d.get("good_for", []) else 0) - (0.3 if d["taste"][1] > 0.6 else 0)  # 후식보다 식사
            if best is None or score > best[0]:
                best = (score, d, m)
        if best is None:
            out.append({"id": p["id"], "name": p["name"], "mark": "피하기", "dish": None, "match": None})
        else:
            _, d, m = best
            out.append({"id": p["id"], "name": p["name"], "mark": "편히" if m or p["id"] in d.get("good_for", []) else "조심",
                        "dish": d["name_ko"], "match": m and {"food": m["food"], "level": m["level"]}})
    return out


def plan(people, now="12:10", meet="13:30", buffer_min=10, meet_pt=None, restaurants=None):
    """meet_pt, restaurants를 주면 그것으로(지금 위치와 주변 실제 식당), 없으면 예시 동네(파리)로 계산한다."""
    data = json.loads(DATA.read_text("utf-8"))
    if restaurants is not None:
        data = {"meet": meet_pt, "restaurants": restaurants}
    meet_pt = data["meet"]
    speed, slowest = group_speed(people)
    left = _mins(meet) - _mins(now)
    t = _mins(now)
    peak = 11 * 60 + 30 <= t < 13 * 60 or 17 * 60 + 30 <= t < 19 * 60 + 30  # 점심, 저녁 붐비는 시간
    rows = []
    for r in data["restaurants"]:
        dist = burden.haversine_m(meet_pt, r) * burden.PARAMS["detour_factor"]
        walk = max(1, round(dist / speed / 60))
        wait = r["wait_min"] + ((10 if r.get("sitdown", True) else 5) if peak else 0)
        need = walk + wait + r["meal_min"] + walk + buffer_min
        spare = left - need
        for d in r["dishes"]:
            d["taste"] = d.get("taste") or [0.5] * 8
        marks = person_marks(r["dishes"], people)
        rows.append({
            "id": r["id"], "name": r["name"], "orig_name": r.get("orig_name", ""), "kind": r["kind"], "known": bool(r["dishes"]), "lat": r["lat"], "lng": r["lng"], "price": r["price"],
            "walk_min": walk, "wait_min": wait, "meal_min": r["meal_min"], "buffer_min": buffer_min,
            "need_min": need, "spare_min": spare, "fits": spare >= 0,
            "back_by": _hm(_mins(now) + need - buffer_min), "marks": marks,
            "all_ok": all(m["mark"] != "피하기" for m in marks), "note": r.get("note", ""),
        })
    rows.sort(key=lambda x: (not x["fits"], not x["known"], not x["all_ok"], -sum(m["mark"] == "편히" for m in x["marks"]),
                             -sum((m["match"] or {}).get("level", "") != "" for m in x["marks"]), x["need_min"]))
    return {"meet": {**meet_pt, "time": meet}, "now": now, "left_min": left, "buffer_min": buffer_min, "peak": peak,
            "speed": round(speed, 2), "slowest": slowest, "restaurants": rows}
