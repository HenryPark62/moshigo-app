"""좋아하는 음식 목록. Food Guide 텍스트 API로 연결을 확인한 음식만 고르게 한다 (core/data/foodguide_favorites.json).

목록에 없는 음식(예: 쌀국수, 초밥)은 Food Guide가 비교 기준으로 쓰지 못해서 그 사람의 추천 점수가 비게 된다.
김치찌개처럼 Food Guide에 후보가 여럿인 이름은 대표 후보(DEFAULT_REFS)로 비교하고, 사람이 나중에 다른 후보로 바꿀 수 있다.
맛 닮은꼴(개발 버전, 이전 경로)에 쓰는 맛 수치는 core/world.py에 같은 이름으로 있다.
"""
import json
from pathlib import Path

_DATA = json.loads((Path(__file__).parent / "data" / "foodguide_favorites.json").read_text("utf-8"))
GROUPS = [(g["title"], g["foods"]) for g in _DATA["groups"]]
ALL = [f for _, foods in GROUPS for f in foods]
DEFAULT_REFS = _DATA["default_refs"]


def unsupported(favorites):
    """목록에 없는(Food Guide가 비교하지 못하는) 음식."""
    return [f for f in favorites or [] if f not in ALL]


def refs_with_defaults(favorites, refs, before=()):
    """사람이 고른 후보는 그대로 두고, 이번에 새로 고른 이름에만 대표 후보를 넣는다.
    (전부터 있던 이름의 후보를 사람이 지웠다면 지운 대로 둔다)"""
    out = {f: v for f, v in (refs or {}).items() if f in favorites}
    for f in favorites:
        if f in DEFAULT_REFS and f not in out and f not in before:
            out[f] = dict(DEFAULT_REFS[f])
    return out
