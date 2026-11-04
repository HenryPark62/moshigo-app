# Food Guide 연동

## 변경 경계

- 기본 사진 경로: `ui.foodguide.scan` → `foodguide_flow.run_image` → `POST /v1/jobs/image` → `GET /v1/jobs/{job_id}`.
- 웹 메뉴: 기존 `webmenu.find_menu`의 검색·출처 검증만 사용한 뒤 `POST /v1/jobs/text`. `describe_list`는 호출하지 않는다.
- 프로필 수정: 원본 사진을 다시 인식하지 않고 이미 추출된 이름·설명을 텍스트 API로 재비교한다. 새 사진 분석이 실패/대기 중이면 그 작업을 먼저 이어 본다.
- `MOSHIGO_ANALYSIS_PROVIDER=legacy`에서만 이전 모듈을 사용한다. API 오류에서 legacy나 예시 성공 결과로 자동 전환하지 않는다.

## 입력·데이터 의미

최대 6명, 개인별 좋아하는 음식 ID 및 제한 재료는 각각 50개까지다. API 요청의 `preferences[].name`에는 표시 이름 대신 안정적인 사람 ID를 사용하여 같은 별명을 구분한다.

즐겨 먹는 음식명은 설명 없이 텍스트 API로 조회한다. `profile.source=dataset`이며 `name_resolution=canonical|dataset_alias`인 고유 ID만 자동 사용한다. 모호한 대표형의 `candidates`는 사용자가 직접 선택하며 나중에도 변경·해제할 수 있다. 다른 닮은 음식인 `matches[].id`를 좋아하는 음식 ID로 대체하지 않는다. 미등록 음식은 그대로 보존하고 개인 점수에 사용한 기준 수를 표시한다.

알레르기·못 먹는 재료는 `avoid_ingredients`로 전달한다. `매운 음식`, `질긴 것` 회피는 각각 `max_chili_heat=2`, `max_chewiness=2`(0~5 척도)로 연결한다. 다른 회피 맛·좋아하는 맛·아이 식습관은 API 비교 조건에 반영되지 않음을 화면에서 알린다. 해당 프로필 값은 기존 장소 기능/legacy용으로 보존한다.

| 결과 | 화면 처리 |
|---|---|
| `matches` | 등록된 한식과의 전역 유사도·비교 정보 비율·닮은 점·차이점 |
| `preferences` | 개인 비교 점수·제한 조건. null은 정보/기준 부족으로 유지 |
| `group` | API의 한 가지 조합·사람별 연결. 여러 작업의 그룹을 합쳐 최적 조합이라고 표시하지 않음 |
| `unknown`, `ambiguous`, `error`, `insufficient` | 메뉴 이름은 유지하고 상태를 표시. 성공으로 바꾸지 않음 |
| `weak_match` | 가까운 비교 한식이 없다는 의미. 사진 인식 실패와 구분 |
| `profile` 없음 | 없는 재료·맛·시간을 채우지 않음 |
| `menu_context.description` | 메뉴판 원문 설명으로 보존. 한국어 번역이라고 표시하지 않음 |
| 원문·발음·가격·언어 | 기존 현지어 주문 카드에 연결. 수량은 사람이 선택 |

사진은 API가 최대 20개를 읽고 같은 이름을 합칠 수 있다. 웹 목록도 처음 20개의 서로 다른 이름을 비교하며 초과·중복을 안내한다. 추가 메뉴는 해당 부분을 촬영한다. 조리시간·인분·품절·실제 알레르기 안전성은 이 응답에 포함되지 않는다.

## 작업·키·세션

- 키는 Streamlit 서버 환경변수/secrets에서만 읽는다. URL은 서버 설정이며 브라우저 입력으로 바꾸지 못한다. HTTPS 또는 loopback HTTP만 허용하고 redirect는 따라가지 않는다.
- 제출 응답의 작업 ID를 세션에 먼저 저장한 뒤 2~5초 간격으로 조회한다. upstream의 `status_url`을 신뢰해 다른 주소로 인증 정보를 보내지 않는다.
- POST는 자동 재시도하지 않는다. 응답 유실은 접수 불확실 상태로 남겨 사용자가 명시적으로 새 작업을 요청하게 한다. 새 요청은 기존 작업 취소가 아니다.
- 대기 시간 초과·일시 조회 오류는 같은 작업을 재개한다. 종료된 실패 작업은 명시적 새 요청으로 구분한다. 429의 `Retry-After`를 따른다.
- 같은 입력·설정의 완료 작업은 재사용한다. 키/서버가 바뀌면 기존 요청 캐시와 참조 연결 범위를 공유하지 않는다.
- 기존 앱의 일일 분석 요청 한도도 유지한다. 새 분석/명시적 재시작에 차감하며 같은 작업을 이어 조회할 때는 다시 차감하지 않는다. Food Guide 서버의 별도 사용량 한도도 적용된다.
- 프로필·대상자가 바뀌면 이전 개인 결과·조합·주문을 차단하고 재비교를 요구한다. 다른 기기 코드를 불러오면 이전 사진·작업·선택을 제거하며, 전환 뒤 늦게 도착한 이전 코드의 분석 결과도 표시하지 않는다.
- 브라우저에 API 키나 upstream 작업 ID를 노출하지 않는다. 사진·결과·job ID는 Streamlit 세션에만 있다. 새 세션/서버 재시작 뒤 작업을 복원하는 영속 BFF 저장소는 추가하지 않았다.

## 검증·재사용

기존 `httpx==0.28.1`(BSD-3-Clause), Streamlit 1.50.0(Apache-2.0), 주문 카드·후기·화면 스타일을 재사용한다. 새 운영 의존성은 없다. 시각 검증 도구 Playwright 1.57.0(Apache-2.0)은 개발 전용이며 `tests/visual/package.json`과 lockfile에 고정한다.

공식 문서: [Streamlit AppTest](https://docs.streamlit.io/develop/concepts/app-testing), [Playwright screenshots](https://playwright.dev/docs/screenshots), [HTTPX](https://www.python-httpx.org/).

사용자 Food Guide 계약은 로컬 `foodguide/api_models.py`, `docs/api.md`를 기준으로 연결했다. 인증값이나 원본 3,000개 음식 데이터는 복사하지 않았다. `tests/visual/fixtures/foodguide-paris.json`은 저장소 공개 예시 메뉴판·예시 가족으로 2026-11-04 실제 호출한 응답 중 화면 필드만 보존하며, 작업 ID·키·인증 해시·원본 카탈로그는 포함하지 않는다.

실제 검증: 별도 선호 음식명 해석 후 이미지 제출·진행 조회·완료 수신에 성공했다. 메뉴 15개가 `ok`, 그룹 메뉴 3개를 받았다. 이는 예시 1건의 연결 확인이며 음식 추정·추천 정확도 검증은 아니다. 운영 Render 배포와 영속 데이터 보관은 별도 설정 대상이다.

단위 테스트와 화면 캡처 결과는 [변경 비교 기록](changes/foodguide/README.md)에 기록한다. 캡처 하네스는 `MOSHIGO_SNAPSHOT=1`이 필요한 별도 진입점이며 운영 앱에 캡처 URL이나 가짜 API 응답을 추가하지 않는다.


## 상단 음식 이미지 자동 생성

메뉴판 상단 두 카드는 `/v1/food-images`에 자동 접수하고 같은 음식 설명의 결과를 재사용합니다. 분석 대기열과 분리되어 있으며 기존 URL·키 설정을 그대로 사용합니다. 소비 앱 서버나 브라우저에 OpenAI 키를 추가하지 않습니다. [API 패치·계약·검증](changes/automatic-images/README.md)을 참고하세요.
