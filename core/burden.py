"""보행 부담 계산.

부모님 프로필로 걷는 속도를 정하고, 하루 일정에서
쉬지 않고 걷는 시간(연속 보행), 계단, 하루 총 보행, 끝나는 시간을 검사한다.
"""
import math

# Bohannon & Andrews (2011) 정상 보행 속도 메타분석, m/s. 연령대(10년 단위)별.
SPEED_MPS = {
    "female": {20: 1.341, 30: 1.337, 40: 1.390, 50: 1.313, 60: 1.241, 70: 1.132, 80: 0.943},
    "male": {20: 1.358, 30: 1.433, 40: 1.434, 50: 1.433, 60: 1.339, 70: 1.262, 80: 0.968},
}

# 팀에서 확정해야 하는 값. 명세 2의 대괄호 값과 같다.
PARAMS = {
    "knee_factor": 0.85,          # 무릎이 불편할 때 속도 보정
    "detour_factor": 1.3,         # 직선 거리를 실제 걷는 거리로 바꾸는 계수 (경로 API 없을 때)
    "stairs_penalty_min": 3,      # 계단 구간 가산 시간
    "default_walk_limit_min": 15,
    "daily_walk_limit_min": 100,  # 하루 총 보행 한도. MET60+ 기준으로 대체 예정
    "rest_min": 10,
    "meal_min": 60,
    "taxi_kmh": 18,
    "taxi_wait_min": 5,
    "taxi_base_fare": 4800,       # 기본 1.6km
    "taxi_base_m": 1600,
    "taxi_step_fare": 100,
    "taxi_step_m": 131,
}


def haversine_m(a, b):
    r = 6371000
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = p2 - p1
    dl = math.radians(b["lng"] - a["lng"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def walking_speed(profile):
    sex = profile.get("sex") or "female"
    decade = profile.get("age_decade") or 70
    decade = min(max(int(decade) // 10 * 10, 20), 80)
    v = SPEED_MPS[sex][decade]
    if profile.get("knee"):
        v *= PARAMS["knee_factor"]
    return v


def walk_minutes(distance_m, speed, stairs=False):
    t = distance_m / speed / 60
    if stairs:
        t += PARAMS["stairs_penalty_min"]
    return round(t, 1)


def taxi(distance_m):
    road_m = distance_m * 1.4
    minutes = road_m / (PARAMS["taxi_kmh"] * 1000 / 60) + PARAMS["taxi_wait_min"]
    extra = max(0, road_m - PARAMS["taxi_base_m"])
    fare = PARAMS["taxi_base_fare"] + math.ceil(extra / PARAMS["taxi_step_m"]) * PARAMS["taxi_step_fare"]
    return round(minutes), int(round(fare, -2))


def walk_limit(profile):
    return profile.get("walk_limit_min") or PARAMS["default_walk_limit_min"]


def check(day, profile, end_time_min):
    """하루 일정 검사. day = {"stops": [...], "legs": [...]} (legs[i]: stops[i] -> stops[i+1]).

    반환: ok, violations, runs(막대그래프용), summary
    """
    limit = walk_limit(profile)
    stops, legs = day["stops"], day["legs"]
    violations, runs = [], []
    acc, run_from = 0.0, stops[0]["name"]
    acc_v = 0.0  # 위반 찾기용. 위반을 찾으면 그 앞에서 쉰 것으로 보고 다시 세어, 한 번에 모든 위반을 찾는다
    total_walk = 0.0

    def add(minutes, where):
        nonlocal acc, acc_v
        acc += minutes
        before = acc_v
        acc_v += minutes
        if acc_v > limit:
            violations.append({"type": "run", "where": where, "walk_min": round(acc_v), "limit_min": limit,
                               "before": round(before, 1), "chunk": round(minutes, 1)})
            acc_v = 0.0 if minutes > limit else minutes

    def close_run(label):
        nonlocal acc, acc_v, run_from
        if acc > 0:
            runs.append({"label": label, "from": run_from, "minutes": round(acc, 1), "over": acc > limit})
        acc, acc_v, run_from = 0.0, 0.0, label

    for i, stop in enumerate(stops):
        if i > 0:
            leg = legs[i - 1]
            if leg["mode"] in ("taxi", "pickup"):
                close_run(stops[i - 1]["name"])
            else:
                total_walk += leg["walk_min"]
                add(leg["walk_min"], ("leg", i - 1))
                if leg["stairs"] and profile.get("stairs") == "avoid":
                    violations.append({"type": "stairs", "where": ("leg", i - 1)})
        if stop["kind"] in ("rest", "meal"):
            close_run(stop["name"])
        elif stop["kind"] == "visit":
            foot = stop.get("on_foot_min", 0)
            total_walk += foot
            n = stop.get("breaks", 0)  # 관람 중간에 앉아서 쉬는 횟수
            for k in range(n + 1):
                add(foot / (n + 1), ("stop", i))
                if k < n:
                    close_run(f"{stop['name']} 안 쉼터")
    close_run(stops[-1]["name"])

    if total_walk > PARAMS["daily_walk_limit_min"]:
        violations.append({"type": "daily", "walk_min": round(total_walk), "limit_min": PARAMS["daily_walk_limit_min"]})
    if stops[-1]["depart_min"] > end_time_min:
        violations.append({"type": "time", "end_min": stops[-1]["depart_min"], "limit_min": end_time_min})

    walk_m = sum(l["distance_m"] for l in legs if l["mode"] == "walk")
    summary = {
        "walk_km": round(walk_m / 1000, 1),
        "walk_total_min": round(total_walk),
        "max_run_min": round(max((r["minutes"] for r in runs), default=0)),
        "rests": sum(1 for s in stops if s["kind"] == "rest"),
        "taxi_rides": sum(1 for l in legs if l["mode"] == "taxi"),
        "taxi_fare": sum(l.get("fare", 0) for l in legs if l["mode"] == "taxi"),
        "limit_min": limit,
    }
    return {"ok": not violations, "violations": violations, "runs": runs, "summary": summary}
