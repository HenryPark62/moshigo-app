# 모시고 · 가족 메뉴판 도우미

해외 메뉴판 사진을 우리말로 읽고, 닮은 한식과 가족별 입맛 비교 결과를 보여 주는 Streamlit 모바일 웹앱입니다.
SVC Seoul AI 해커톤 지정 과제 03, 팀 NEXUS.

## 현재 분석 흐름

```text
사진 → Food Guide 이미지 작업 → 진행률·결과 조회 → 메뉴·개인 비교·가족 조합 → 현지어 주문 카드
웹 메뉴 → 출처 확인된 메뉴 목록 → Food Guide 텍스트 작업 → 같은 결과 화면
```

기본값은 `MOSHIGO_ANALYSIS_PROVIDER=foodguide`입니다. 사진 인식·음식 특징·유사도·개인 취향 비교는 Food Guide API가 담당합니다. 모시고 서버는 `X-API-Key`를 보관하고 작업을 제출·조회합니다. 브라우저에 키나 작업 조회 권한을 전달하지 않습니다. 기존 Claude·CLOVA 사진 분석을 자동 대체 경로로 호출하지 않습니다.

| 화면 | 현재 동작 |
|---|---|
| 사람·입맛 편집 | 즐겨 먹는 음식·제한·알레르기 저장. API 기준 음식의 연결 수를 표시하고 모호한 대표형은 직접 선택 |
| 사진 | JPG·PNG·WebP, 15 MiB 이하. 이미지 API는 최대 20개 메뉴. 단계별 진행률과 작업 이어 보기 |
| 메뉴·상세 | 구성원 평균 추천 점수·음식 이미지·메뉴명·통화/원화 가격·읽는 법·개인별 점수. 식사류 평균 상위 2개 추천 강조·OpenAI 이미지 자동 생성·재사용, 카드 클릭으로 상세 확인 |
| 가족 조합 | API가 돌려준 최대 3개 메뉴의 한 가지 조합. 사람별 연결과 미포함 구성원 표시 |
| 주문 | 원문 메뉴·수량을 직접 선택. 알레르기·못 먹는 재료를 먼저 전달하는 현지어 카드와 브라우저 음성 |
| 간단 모드 | 공유 링크로 선택된 한 사람 기준의 사진·결과·주문. 그룹 참여 여부와 독립 |
| 후기 | 실제 주문·맛·재추천 의향 저장. API 비교 점수나 그룹 추천을 변경하지 않음 |
| 주변·자유 식사 | 기존 장소 검색·대표 음식·시간 계산 유지. 사진 분석 결과와 별도 경로 |

`matches`는 등록된 한식과의 비교이고 `preferences`는 개인이 선택한 음식 기준입니다. 두 결과를 섞지 않습니다. 점수는 0~100의 비교 수치이며 확률이 아닙니다. `null`은 0점이 아니라 비교 기준/정보 부족입니다. `eligible`은 입력한 제한 조건의 검사 결과이며 알레르기 안전 보장이 아닙니다.

API가 제공하지 않는 기존 8축 맛 지도, 예상 조리시간, 직원 질문, 아이 주문 변형, 세 종류의 조합을 새 결과에 임의 생성하지 않습니다. 원문 설명과 한국어 특징을 구분하며, 원문·가격은 주문 카드에 보존합니다.

## 실행·설정

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .streamlit/secrets.example.toml .streamlit/secrets.toml
# FOODGUIDE_API_URL, FOODGUIDE_API_KEY 설정
.venv/bin/streamlit run streamlit_app.py
```

- 필수: `FOODGUIDE_API_URL`, `FOODGUIDE_API_KEY`. Food Guide 호출키이며 OpenAI 키와 다릅니다.
- `FOODGUIDE_MAX_WAIT_SECONDS`: 한 번 조회하는 최대 시간, 기본 600초. 시간 초과 후 같은 작업을 이어 조회할 수 있습니다.
- URL은 HTTPS origin만 허용합니다. 로컬 개발의 `http://127.0.0.1:8000`은 허용합니다. 리다이렉트는 따라가지 않습니다.
- `ANTHROPIC_API_KEY`: 선택 기능인 웹 메뉴 검색에만 사용합니다. 찾은 메뉴는 Food Guide 텍스트 API로 넘기며 Claude 설명 단계를 다시 실행하지 않습니다.
- `KAKAO_REST_KEY`, `GEOAPIFY_KEY`: 기존 주변 장소 검색의 선택 설정입니다.
- 명시적 롤백: `MOSHIGO_ANALYSIS_PROVIDER=legacy`. 이 경우 기존 Claude/CLOVA 설정이 필요합니다.

Render는 `render.yaml`의 서버 전용 환경변수에 연결 주소와 키를 설정해야 합니다. 이 PR 자체가 운영 비밀값을 설정하거나 배포를 확인하는 것은 아닙니다. 외부 Render 서비스에서 개발 PC의 loopback 주소에는 접근할 수 없으므로 접근 가능한 HTTPS API 주소가 필요합니다. SQLite 영속 디스크는 현재 배포 설정에 없습니다.

## 모듈

| 경로 | 역할 |
|---|---|
| `core/foodguide_client.py` | 이미지·텍스트 HTTP 계약, 작업 재개, 오류·응답 검증 |
| `core/foodguide_references.py` | 선택 음식만 조회해 카탈로그 ID 연결, 모호한 후보·미지원 항목 표시 |
| `core/foodguide_flow.py` | 사진/웹/재비교 흐름, API 응답을 화면 계약으로 변환, 세션 소유 경계 |
| `ui/foodguide.py` | API 결과 전용 화면 |
| `streamlit_app.py`, `ui/screens.py`, `ui/simple.py` | 라우팅, 공통 화면, 사람 편집, 공유 모드 |
| `core/order.py`, `core/reviews.py`, `core/store.py` | 현지어 카드, 후기·프로필 SQLite 저장 |
| `core/nearby.py`, `freemeal.py`, `plan.py`, `burden.py` | 기존 장소·자유 식사 계획 |
| `core/menu2.py`, `ocr.py`, `world.py` | 명시적 legacy 분석 및 기존 장소 추천에서 재사용 |

## 검증과 화면 비교

```bash
.venv/bin/pip install pytest
.venv/bin/python -m pytest tests -q
```

[연동 계약·제한·복구 방법](docs/foodguide-integration.md), [변경 전 → 변경 후 스크린샷](docs/changes/foodguide/README.md)을 참고하세요. 화면 캡처는 같은 공개 예시 사진·프로필로 실제 Streamlit을 렌더링합니다. 변경 전은 저장소의 예시 JSON, 변경 후는 실제 Food Guide 호출 응답을 고정한 fixture를 사용합니다. 처리 중·장애 상태만 제어된 모의 응답입니다.

원본 음식 데이터셋은 이 저장소에 복사하지 않습니다. 사용자가 고른 음식명만 API로 조회하며, 고유 데이터셋 ID만 자동 연결합니다. 모호한 음식은 사용자가 대표형을 고르기 전까지 개인 비교 기준에서 제외하고 연결 수를 표시합니다.
