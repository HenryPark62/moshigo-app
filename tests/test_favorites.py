"""좋아하는 음식 목록이 Food Guide 연결 목록과 앱 맛 데이터에 맞는지."""
from core import favorites, world


def test_every_favorite_has_taste_profile_and_no_duplicates():
    assert len(favorites.ALL) == len(set(favorites.ALL)) >= 80
    assert not [f for f in favorites.ALL if f not in world.WORLD]  # 개발 버전 닮은꼴 계산에 필요


def test_ambiguous_names_get_representative_only_when_newly_picked():
    assert favorites.DEFAULT_REFS["김치찌개"]["name"] == "돼지고기김치찌개"
    refs = favorites.refs_with_defaults(["김치찌개", "불고기"], {})
    assert refs["김치찌개"]["name"] == "돼지고기김치찌개" and "불고기" not in refs
    chosen = {"id": "x", "name": "참치김치찌개"}
    assert favorites.refs_with_defaults(["김치찌개"], {"김치찌개": chosen}) == {"김치찌개": chosen}  # 사람이 고른 후보 유지
    assert favorites.refs_with_defaults(["김치찌개"], {}, before=["김치찌개"]) == {}  # 지운 선택은 그대로
    assert favorites.refs_with_defaults([], {"김치찌개": chosen}) == {}  # 뺀 음식의 후보는 지움


def test_unsupported_old_favorites_are_listed():
    assert favorites.unsupported(["쌀국수", "불고기", "초밥"]) == ["쌀국수", "초밥"]
