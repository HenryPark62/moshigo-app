"""개발 버전: API를 쓰지 않고 예시 지도(파리 루브르 근처 실제 지도 데이터를 받아 둔 것), 예시 메뉴판 사진, 예시 결과(전에 실제로 읽은 결과)로 화면을 채운다.

사진 출처 (위키미디어 공용, CC0):
- thai.jpg: "Menu of Sawadee Thai Restaurant (p1) 2024-10-05", Andy Li
- lyon.jpg: "Menu du jour d'un restaurant asiatique lyonnais en 2017", Benoît Prieur
"""
import json
from pathlib import Path

DATA = Path(__file__).parent / "data"
EXAMPLES = [  # (키, 화면 이름, 사진, 결과)
    {"key": "paris", "title": "파리 비스트로", "sub": "프랑스어 메뉴판, 메뉴 16개", "img": DATA / "paris_menu.jpg", "raw": DATA / "demo_paris.json"},
    {"key": "thai", "title": "태국 식당", "sub": "영어 메뉴판, 메뉴 25개", "img": DATA / "examples" / "thai.jpg", "raw": DATA / "examples" / "thai.json"},
    {"key": "lyon", "title": "리옹 아시아 식당", "sub": "프랑스어 오늘의 메뉴, 메뉴 12개", "img": DATA / "examples" / "lyon.jpg", "raw": DATA / "examples" / "lyon.json"},
]
ASIAN = ("태국", "베트남", "중식", "중국", "일식", "일본", "아시아", "인도", "한식", "쌀국수", "라멘", "스시", "카레")


NEAR = DATA / "examples" / "paris_near.json"  # 파리 루브르 근처 실제 지도 데이터(OpenStreetMap)를 한 번 받아 둔 것


def near():
    """개발 버전 지도: {geo, label, places(식당), spots(둘러볼 곳 원본), groups}"""
    return json.loads(NEAR.read_text("utf-8"))


def get(key):
    return next((e for e in EXAMPLES if e["key"] == key), EXAMPLES[0])


def raw(key, people):
    """예시 결과. 같이 먹는 사람 중 예시에 판정이 없는 사람은 enrich에서 '조심'으로 채워진다."""
    ex = get(key)
    data = json.loads(ex["raw"].read_text("utf-8"))
    names = {p["name"] for p in people}
    for it in data["items"]:
        it["people"] = [g for g in it.get("people") or [] if g["name"] in names]
    return data, ex["img"].read_bytes()


def for_place(place):
    """메뉴 불러오기를 누른 식당에 어울리는 예시 (아시아 음식이면 태국 식당, 아니면 파리 비스트로)."""
    text = f'{place.get("kind", "")} {place.get("name", "")}'
    return "thai" if any(w in text for w in ASIAN) else "paris"
