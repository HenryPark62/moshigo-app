"""걷는 속도와 걷는 시간.

나이대와 성별로 걷는 속도를 정하고(일행 중 가장 느린 사람 기준), 거리를 걷는 분으로 바꾼다.
"""
import math

# Bohannon & Andrews (2011) 정상 보행 속도 메타분석, m/s. 연령대(10년 단위)별.
SPEED_MPS = {
    "female": {20: 1.341, 30: 1.337, 40: 1.390, 50: 1.313, 60: 1.241, 70: 1.132, 80: 0.943},
    "male": {20: 1.358, 30: 1.433, 40: 1.434, 50: 1.433, 60: 1.339, 70: 1.262, 80: 0.968},
}

PARAMS = {
    "knee_factor": 0.85,          # 무릎이 불편할 때 속도 보정
    "detour_factor": 1.3,         # 직선 거리를 실제 걷는 거리로 바꾸는 계수 (경로 API 없을 때)
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


def walk_min(distance_m, speed):
    """직선 거리(m)를 걷는 분으로. 길이 돌아가는 만큼 detour_factor를 곱한다. 가까워도 1분."""
    return max(1, round(distance_m * PARAMS["detour_factor"] / speed / 60))
