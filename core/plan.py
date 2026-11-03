"""추천 플랜: 출발 시간과 도착 시간 안에 식당 한 곳과 둘러볼 곳 0~2곳을 묶는다.

걷는 시간은 일행 중 가장 느린 사람 걸음, 식당은 나오기와 식사 시간(붐비는 시간이면 더), 둘러볼 곳은 머무는 시간 어림값.
같이 가는 사람에게 잘 맞는 곳(식당 점수, 장소 점수)을 많이 담고, 남는 시간이 너무 많거나 많이 걷는 플랜은 뒤로.
"""
import itertools

from . import burden, nearby

MEALTIME = [(11 * 60 + 30, 13 * 60 + 30), (17 * 60 + 30, 19 * 60 + 30)]


def hm(m):
    return f"{m // 60 % 24:02d}:{m % 60:02d}"


def _walk(a, b, speed):
    d = burden.haversine_m({"lat": a["lat"], "lng": a["lng"]}, {"lat": b["lat"], "lng": b["lng"]}) * 1.3
    return max(1, round(d / speed / 60))


def _peak(t):
    return any(a <= t < b for a, b in MEALTIME)


def _schedule(order, origin, start, speed, back):
    """순서대로 걸어 다닐 때 각 곳에 머무는 시간표. (stops, 끝나는 시각, 총 걷는 분)"""
    t, prev, walked, stops = start, origin, 0, []
    for p in order:
        w = _walk(prev, p, speed)
        t += w
        walked += w
        if p["type"] == "food":
            dur = p["wait_min"] + (10 if p.get("sitdown", True) else 5) * _peak(t) + p["meal_min"]
        else:
            dur = nearby.STAY_MIN[p["group"]]
        stops.append({"place": p, "walk": w, "arrive": t, "leave": t + dur})
        t += dur
        prev = p
    back_walk = _walk(prev, origin, speed) if back else 0
    return stops, t + back_walk, walked + back_walk, back_walk


def make_plans(origin, start, end, restaurants, spots, speed, back=True, buffer=10, n=3):
    """restaurants, spots: 점수(score)가 매겨진 목록. 시간 안에 드는 플랜을 좋은 순서로 n개 (식당이 겹치지 않게)."""
    R = [dict(r, type="food") for r in restaurants[:20]]
    S = [dict(s, type="spot") for s in spots[:6]]
    limit = end - buffer
    cands = []
    for r in R:
        orders = [[r]]
        for s1 in S:
            orders += [[s1, r], [r, s1]]
        for s1, s2 in itertools.permutations(S, 2):
            orders += [[s1, r, s2], [s1, s2, r], [r, s1, s2]]
        for order in orders:
            stops, finish, walked, back_walk = _schedule(order, origin, start, speed, back)
            if finish > limit:
                continue
            meal = next(x for x in stops if x["place"]["type"] == "food")
            at_mealtime = any(a <= meal["arrive"] < b for a, b in MEALTIME)
            window_has_meal = any(start < b and a < end for a, b in MEALTIME)
            score = (1.5 * r["score"] + sum(x["place"]["score"] for x in stops if x["place"]["type"] == "spot")
                     + (0.6 if at_mealtime else -0.4 if window_has_meal else 0)
                     - walked / 40 - max(0, limit - finish - 30) / 60)
            cands.append({"score": score, "stops": stops, "finish": finish, "walked": walked, "back_walk": back_walk,
                          "spare": end - finish, "names": tuple(x["place"]["name"] for x in stops)})
    cands.sort(key=lambda c: -c["score"])
    out, used = [], set()
    for c in cands:
        food = next(x["place"]["name"] for x in c["stops"] if x["place"]["type"] == "food")
        if food in used:
            continue
        used.add(food)
        out.append(c)
        if len(out) == n:
            break
    return out
