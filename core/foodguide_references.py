"""선택한 익숙한 음식만 API 대표형에 연결한다. 모호한 대표형은 사람이 고른다."""
import hashlib
import json

from .foodguide_client import FoodGuideError


SIGNATURE_FIELDS = ("id", "name", "active", "favorites", "foodguide_refs", "avoid", "cannot", "allergies", "child", "likes")


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def signature(people):
    """개인 설정 변경 시 이전 분석 결과가 남지 않도록 비교하는 서명."""
    return _hash([{key: p.get(key) for key in SIGNATURE_FIELDS} for p in people])


def _invalid():
    return FoodGuideError("invalid_request", "가족은 최대 6명이며 고유한 ID와 올바른 취향 정보가 필요해요.")


def _strings(values, maximum=50):
    if not isinstance(values, list) or len(values) > maximum:
        raise _invalid()
    if any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in values):
        raise _invalid()
    return list(dict.fromkeys(v.strip() for v in values))


def _people(people):
    if not isinstance(people, list) or any(not isinstance(p, dict) for p in people):
        raise _invalid()
    active = [p for p in people if p.get("active", True)]
    if len(active) > 6:
        raise _invalid()
    out = []
    for p in active:
        pid, name = p.get("id"), p.get("name")
        if not isinstance(pid, str) or not pid.strip() or len(pid) > 100 or not isinstance(name, str) or not name.strip():
            raise _invalid()
        refs = p.get("foodguide_refs") or {}
        if not isinstance(refs, dict):
            raise _invalid()
        row = {**p, "id": pid.strip(), "name": name, "foodguide_refs": refs}
        for key in ("favorites", "avoid", "cannot", "allergies"):
            row[key] = _strings(p.get(key) or [])
        if len(set(row["allergies"] + row["cannot"])) > 50:
            raise _invalid()
        out.append(row)
    if len({p["id"] for p in out}) != len(out):
        raise _invalid()
    return out


def _food(value):
    if not isinstance(value, dict):
        return None
    fid, name = value.get("id"), value.get("name")
    if not isinstance(fid, str) or not fid.strip() or len(fid) > 200 or not isinstance(name, str) or not name.strip() or len(name) > 200:
        return None
    return {"id": fid, "name": name}


def _reference(item, dataset_sha):
    resolution = item.get("name_resolution")
    resolution = resolution if isinstance(resolution, str) else "unresolved"
    status = item.get("status")
    status = status if isinstance(status, str) else "unknown"
    profile = item.get("profile")
    food = _food(profile)
    unique = food is not None and profile.get("source") == "dataset" and resolution in ("canonical", "dataset_alias")
    candidates = []
    if status == "ambiguous" and isinstance(item.get("candidates"), list):
        seen = set()
        for candidate in item["candidates"]:
            candidate = _food(candidate)
            if candidate and candidate["id"] not in seen:
                candidates.append(candidate)
                seen.add(candidate["id"])
    return {"id": food["id"] if unique else "", "name": food["name"] if unique else "",
            "candidates": candidates, "status": "resolved" if unique else "unresolved" if status == "ok" else status,
            "resolution": resolution, "dataset_sha": dataset_sha if isinstance(dataset_sha, str) else ""}


def resolve(people, client, jobs, cache, on_progress=None):
    """선호 API 입력과 화면용 연결 요약을 반환한다. 실패는 호출자에게 전달한다."""
    active = _people(people)
    if not isinstance(jobs, dict) or not isinstance(cache, dict):
        raise _invalid()
    scope = _hash([client.config.base_url, hashlib.sha256(client.config.api_key.encode()).hexdigest()])
    if cache.get("scope") != scope or not isinstance(cache.get("foods"), dict):
        cache.clear()
        cache.update(scope=scope, foods={})
    foods = cache["foods"]
    favorites = list(dict.fromkeys(f for p in active for f in p["favorites"]))
    missing = [favorite for favorite in favorites if favorite not in foods]
    for offset in range(0, len(missing), 20):
        batch = missing[offset:offset + 20]
        report = client.run_text(batch, [], state=jobs, operation_key="references:" + _hash([scope, batch]),
                                 on_progress=on_progress)
        items = report.get("items") if isinstance(report, dict) else None
        if not isinstance(items, list) or len(items) != len(batch) or any(not isinstance(i, dict) or i.get("input_name") not in batch for i in items):
            raise FoodGuideError("invalid_response", "선호 음식 연결 결과를 확인할 수 없어요.")
        by_name = {item["input_name"]: item for item in items}
        if len(by_name) != len(batch):
            raise FoodGuideError("invalid_response", "선호 음식 연결 결과를 확인할 수 없어요.")
        for favorite in batch:
            foods[favorite] = _reference(by_name[favorite], report.get("dataset_sha256"))

    preferences, summary = [], []
    for p in active:
        resolved, unresolved = [], []
        for favorite in p["favorites"]:
            ref = foods[favorite]
            unique = _food(ref) if ref.get("status") == "resolved" else None
            choices = ([unique] if unique else []) + ref["candidates"]
            selected = p["foodguide_refs"].get(favorite)
            selected_id = selected.get("id") if isinstance(selected, dict) else None
            chosen = next((candidate for candidate in choices if candidate["id"] == selected_id), None) or unique
            if chosen:
                resolved.append({"favorite": favorite, **chosen})
            else:
                unresolved.append({"name": favorite, "status": ref["status"],
                                   "candidates": [dict(candidate) for candidate in ref["candidates"]]})
        avoid = p["avoid"]
        preferences.append({"name": p["id"], "liked_food_ids": list(dict.fromkeys(r["id"] for r in resolved)),
                            "avoid_ingredients": list(dict.fromkeys(p["allergies"] + p["cannot"])),
                            "max_chili_heat": 2 if "매운 음식" in avoid else None,
                            "max_chewiness": 2 if "질긴 것" in avoid else None})
        summary.append({"id": p["id"], "name": p["name"], "total": len(p["favorites"]), "resolved": len(resolved),
                        "unresolved": unresolved, "resolved_foods": resolved,
                        "not_applied": [value for value in avoid if value not in ("매운 음식", "질긴 것")]})
    return preferences, summary
