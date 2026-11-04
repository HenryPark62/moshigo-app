# 메뉴 가격과 원화 참고 금액

`core/menu_prices.py`는 명시된 단일 가격만 환산한다. 언어·식당 이름으로 통화를 추측하지 않는다. 기존 `httpx==0.28.1`을 사용하며 새 의존성은 없다.

## UI 계약

```python
from core.menu_prices import CURRENCY_OPTIONS, price_info
info = price_info("14,90 €")
# display: 원문 가격(단위 포함), krw: "약 22,377원" 또는 ""
# date: 환율 기준 YYYY-MM-DD 또는 "", currency: ISO 코드 또는 ""
# status: converted / krw / currency_required / unparsed / unavailable
# notice: 통화 확인 또는 환산 불가 안내, 정상일 때 ""
```

`price_info(price, currency='', *, fx_data=...)`의 `currency`는 호출자가 전달한 통화다. 메뉴에서 확인했는지 이미지 분석으로 추정했는지는 호출 UI가 구분해 표시한다. 단위 없는 숫자와 `$`/`¥` 같은 모호한 기호를 해석할 때만 사용한다. `€` 같은 명시 단위가 우선하며 기호와 통화가 모순되면 환산하지 않는다. `CURRENCY_OPTIONS`는 자주 쓰는 통화의 `{ISO: 한국어 라벨}`일 뿐 유효성 검사 목록이 아니다. 영문 3자리 코드 형식은 목록 밖의 `INR`·`SEK`·`NZD`도 허용한다. 실제 지원 여부는 Frankfurter의 응답 코드와 base/quote 검증으로 확인하며, 미지원 응답(예: 422)은 통화 코드를 유지한 채 `unavailable`로 표시한다. 카드마다 지원 통화 목록을 별도 조회하지 않는다.

`fx_data`를 생략하면 조회·캐시를 사용한다. `{date, base, quote, rate}`를 주입하면 검증 후 해당 환율만 사용하고 네트워크는 호출하지 않는다. `fx_data=None`이나 `{}`는 환산 불가 상태를 재현한다. 테스트·스크린샷에서는 주입을 사용한다. 응답 `date`를 참고 환율 날짜로 표시하며 실제 결제 환율·수수료는 포함하지 않는다. 이미 KRW인 가격은 재환산하지 않는다.

소수점 `14,90`, `14.90`, 천 단위 `1.234,50`, `1,234.50`, 공백 묶음 `1 234,50`을 지원한다. 단일 구분자 뒤 세 자리는 엄격한 천 단위 그룹일 때만 인정한다. 범위·슬래시·추가 요금·음수·비정상 구분자는 원문을 유지한다. 실패 시 원문을 버리거나 임의 금액으로 바꾸지 않는다.

## 채택한 서비스와 운영 동작

- 출처: [Frankfurter 공식 문서](https://frankfurter.dev/), API v2.
- 엔드포인트: `https://api.frankfurter.dev/v2/rate/{BASE}/KRW`. 무료 공개·키 없는 API를 HTTP로 이용하며 외부 코드·데이터셋을 복사하지 않는다. 문서/API 형태는 통합 작업의 사전 조사에서 확인했다.
- 검증된 응답 예: `{"date":"2026-11-04","base":"EUR","quote":"KRW","rate":1501.84}`. 이 모듈 작업에서는 실제 요청을 반복하지 않았다.
- 응답의 base/quote, 유한한 양수 rate, 유효하고 미래가 아닌 ISO date를 검증한다.
- 기준 환율은 일별 값이며 메모리 캐시는 UTC 날짜별·최대 1시간, 최대 16개다. 프로세스 재시작 시 비워진다.
- 요청 타임아웃 3초, 리다이렉트 없음, 자동 재시도 없음. 일반 실패는 60초간 캐시한다.
- 429의 `Retry-After` 초 또는 HTTP 날짜를 존중해 같은 프로세스의 모든 통화 요청을 해당 시각까지 중단한다. 대기는 사용자 요청 스레드를 sleep하지 않고 환산 불가를 반환하는 방식이다.
- 검증: `tests/test_menu_prices.py`에서 HTTP 모의 응답으로 파싱·환율 검증·시간/날짜 캐시·429·장애·캐시 상한을 검사한다.

## 누락된 추정 통화 코드 호환

`currency_code(extraction)`은 `currency_source`가 `printed` 또는 `inferred`일 때 명시된 영문 3자리 `currency_code`를 반환한다. `inferred`인데 코드가 비어 있으면 `currency_evidence`에 독립된 대문자 3자리 코드가 정확히 한 종류 있을 때만 복구한다. 예를 들어 `"유로화(EUR)로 추정됨"`은 `EUR`이며, 이 결과도 UI에서 **추정 통화**로 표시해야 한다. 코드가 없거나 여러 종류이거나 source가 `unknown`이면 빈 문자열이다. 잘못된 비어 있지 않은 코드를 설명으로 덮어쓰지 않는다. 언어·장소·자연어 통화 이름으로 매핑하지 않으며 네트워크를 호출하거나 원본 분석을 변경하지 않는다.
