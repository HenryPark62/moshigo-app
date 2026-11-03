# 모시고 · 가족 메뉴판 도우미

처음 보는 해외 메뉴판을 찍으면 우리말로 옮기고, 같이 먹는 사람마다 **각자 아는 음식에 빗대어** 무슨 맛인지 알려 주는 모바일 웹앱.
SVC Seoul AI 해커톤 지정 과제 03, 팀 NEXUS.

## 하는 일

| 화면 | 내용 |
|---|---|
| 시작 | 혼자 / 여럿이, 자유여행 / 패키지 자유 식사 |
| 같이 먹는 사람 | 사람마다 즐겨 먹는 음식(나라 상관없이), 좋아하는 맛, 피하는 맛, 못 먹는 것, 알레르기, 아이 입맛. 기기 코드로 저장 |
| 메뉴판 찍기 | 사진 → CLOVA OCR로 글씨 추출 → LLM이 번역, 설명, 맛 수치, 사람별 판정 |
| 메뉴판 읽기 | 번역만 / 원문과 함께(요리 용어 풀이) / 누가 먹을까(모두 편히, 몇 명만, 모두 피하기) |
| 무슨 맛인지 | 맛 설명, 아는 맛(닮은꼴 아주/꽤/조금), 같은 점과 다른 점, 맛 지도, 후기(이 식당 먼저), 현지어 부탁 문장 읽어 주기 |
| 메뉴 조합 | 모두 만족 / 현지 맛 도전 / 빨리 나와요. 가장 덜 맞는 사람 기준(maximin), 접시 바꾸기, 고른 이유 |
| 주문 카드 | 알레르기와 못 먹는 것을 맨 위에, 현지어 주문 문장, 소리 내어 읽기 |
| 자유 식사 시간 | 모이는 시간 안에 (가기 + 기다림 + 식사 + 돌아오기 + 여유) 다녀올 식당. 가장 느린 사람 걸음 기준 |
| 먹어 본 뒤 설문 | 실제 주문, 맛이 그려졌는지, 예상보다 강한 맛, 다시 추천. 쌓이면 메뉴 설명에 미리 알려 줌 |

알레르기와 못 먹는 재료는 LLM 판정과 상관없이 코드에서 늘 '피하기'로 만든다. 닮은꼴과 조합은 코드로 계산한다 (`core/world.py`, `core/menu2.py`).

## 구성

- Python 3.12+, Streamlit (화면), Anthropic Claude API (설명 생성), 네이버 CLOVA OCR (글씨 추출), SQLite (입맛, 설문, 사용량)
- 지도: OpenStreetMap (folium)
- 로그인 없음. 입맛은 주소의 `?me=코드`로 기기마다 저장하고, 다른 기기에서는 코드로 불러온다.

```
streamlit_app.py   화면 이동, 위 머리, 아래 탭바
ui/common.py       스타일(기존 모시고 디자인), 작은 HTML 조각
ui/screens.py      화면들
core/ocr.py        CLOVA OCR General(V2) 호출, 줄 묶기
core/menu2.py      LLM 구조화 출력(번역, 설명, 판정), 규칙 판정, 닮은꼴, 조합
core/world.py      세계 음식 43종 맛 표와 닮은꼴 계산
core/order.py      주문 카드 문장 (프랑스어, 영어)
core/freemeal.py   자유 식사 시간 계산
core/reviews.py    후기, 설문, 설문을 설명에 반영
core/store.py      입맛 저장, 하루 사용량 한도
```

## 실행

```bash
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .streamlit/secrets.example.toml .streamlit/secrets.toml   # 키 넣기
.venv/bin/streamlit run streamlit_app.py
.venv/bin/python -m pytest -q tests
```

키가 없으면 예시 메뉴판(파리 비스트로)으로 같은 흐름이 동작한다. OCR 키가 없고 Claude 키만 있으면 사진을 Claude가 직접 읽는다.

## 시연용이라 바꿔야 하는 것

- `core/world.py` 맛 수치와 `core/order.py` 현지어 문장은 초안 (팀 검토, 원어민 검토 필요)
- `data/paris_places.json` 식당은 [샘플], `data/sample_reviews.json` 후기는 화면에 '예시'로 표시
- Streamlit Community Cloud의 파일은 다시 시작하면 지워질 수 있다 (SQLite). 오래 보관하려면 외부 DB로 옮긴다
