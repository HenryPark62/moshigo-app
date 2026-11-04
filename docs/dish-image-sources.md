# 메뉴 썸네일 출처와 처리

`core/dish_images.py`는 음식 분석 API를 바꾸지 않고 카드에 사용할 이미지를 별도로 준비한다. 새로운 런타임 의존성이나 서비스 키를 추가하지 않았다.

## 반환 계약

```python
from core.dish_images import menu_images

images = menu_images(
    scan["items"],
    report=scan.get("report"),
    image_bytes=session.get("scan_img"),
)
# images[item_id] = {
#   "src": "data:image/jpeg;base64,..." | "https://upload.wikimedia.org/..." | "data:image/svg+xml;base64,...",
#   "label": "메뉴판 사진" | "대표 사진" | "종류 참고 그림",
#   "title": str, "author": str, "license": str,
#   "source_url": str, "license_url": str,
# }
```

한 번에 앞쪽 20개 항목을 처리한다. `report.items[].input_name`으로 원본 `menu_context.photo_bbox`를 찾는다. 직접 `item.menu_context`를 전달해도 된다. 대표 사진을 표시하는 UI는 `label`과 출처·저작자·라이선스 링크를 함께 제공하고, 모든 문자열을 HTML escape해야 한다. 화면에서 사진을 더 잘라 표시한다면 그 변형도 명시한다.

## 선택 순서

1. **메뉴판 사진**: 제공된 이미지에서 API가 지정한 음식 사진 영역만 자른다. bbox는 유한한 0~1 숫자 4개이며 가로·세로가 양수, 전체 면적의 85% 이하, 가로·세로 각각 20px 이상이어야 한다. API 이미지 전처리와 같이 EXIF 방향을 적용한다. 최대 480px JPEG data URI를 반환하며 사용자 사진이나 crop을 전역 캐시·파일·외부 서비스에 저장하지 않는다.
2. **대표 사진**: 고정된 공개 음식명으로 Wikipedia 음식 문서를 찾고 Commons의 파일별 라이선스·저작자·출처를 확인한다. 실제 식당 사진으로 표시하지 않는다. `Schnitzel`, `Jägerschnitzel`, `Käsespätzle`, `Frankfurter Grüne Soße`, `Frikadeller`, `Currywurst`, `Schweinshaxe`, `Schweinsbraten`, `Leberkäse`, `Bratwurst`, `Rump steak` 등 명시된 별칭만 검색한다. 데리야키 연어는 넓은 대표형인 `Salmon as food`로 연결되므로 실제 소스·조리 형태를 보장하지 않는다.
3. **종류 참고 그림**: 사진 영역·검증된 대표 사진이 없으면 새로 작성한 로컬 SVG를 사용한다. 국물·고기·생선·면·채소·후식·음료 또는 일반 접시 그림이며 “종류 참고 그림”으로 구분한다. 원래 메뉴의 실제 모습으로 주장하지 않는다.

미등록 음식명은 임의 검색 결과로 대체하지 않는다. 개인 이름·가족 설정·원문 설명·전체 메뉴 원문은 공개 검색어로 보내지 않고, 코드에 고정된 일반 음식 제목만 전송한다. 전역 유사도 결과의 `matches[].id`나 이름을 원래 음식 사진의 근거로 사용하지 않는다.

## 공급처와 권리 확인

- 문서 메타데이터: `https://en.wikipedia.org/w/api.php`의 `pageimages`, `categories`, `pageprops`.
- 파일 메타데이터: `https://commons.wikimedia.org/w/api.php`의 `imageinfo`, `extmetadata`.
- 이미지 호스트는 HTTPS `upload.wikimedia.org` 또는 `thumb.wikimedia.org`만 허용한다. 출처는 HTTPS `commons.wikimedia.org`, Creative Commons 라이선스 링크는 HTTPS `creativecommons.org`만 허용한다. 사용자 정보가 포함된 URL·비표준 포트·HTTP redirect는 허용하지 않는다.
- 허용 파일 라이선스: `CC BY 1.0–4.0`, `CC BY-SA 1.0–4.0`, `CC0`, `Public domain`. 저작자가 없거나 BY 계열의 라이선스 링크가 없으면 제외한다. 음식 분류가 없거나 동음이의 문서면 제외한다.
- 이미지 파일은 저장소에 내려받거나 커밋하지 않는다. 실행 시 승인된 파일 URL과 해당 파일의 출처·저작자·라이선스를 함께 반환한다. Wikimedia 전체가 동일 라이선스라는 전제는 사용하지 않는다.

## 재사용 기록

기존 로컬 앱의 다음 TypeScript 구현에서 사진 선택 순서·라이선스 확인·fallback 설계를 참고했다. 별도 코드 재배포 라이선스가 확인되지 않아 원문 코드를 복사하지 않고 Python HTTP 처리와 SVG를 새로 작성했다.

| 참고 파일 | 확인한 SHA-256 |
|---|---|
| `해커톤/sites/family-menu-guide/lib/server/dish-image.ts` | `ef1888368b494542a873a730ac4ab609cf346c307370f78036d46d8c66d96d77` |
| `해커톤/sites/family-menu-guide/components/DishImage.tsx` | `b8a46bb061eb642dfa6e27e57637e9862f1aa23e15200f4ea06c02d3fd6c0e2a` |

기존 `httpx==0.28.1`(BSD-3-Clause), Streamlit 의존성으로 설치된 Pillow(검증 환경 11.3.0, HPND)를 사용한다. 기존 패키지 라이선스 파일을 유지하며 새 이미지 라이브러리·API 키·원격 실행 코드는 도입하지 않았다. 참고 저장소의 Git HEAD는 없어 파일 해시로 식별했다.

## 지연·캐시·검증

- 전역 최대 3개 공개 조회를 동시에 실행한다. 같은 공개 음식명은 진행 중인 작업을 공유한다. 대기 작업은 최대 24개다.
- 요청별 timeout은 최대 3초, 음식별 조회 예산은 5.5초, 전체 helper 대기는 최대 6초다. 늦은 공개 결과는 다음 렌더에서 캐시로 이용하고 현재 화면은 참고 그림으로 표시한다.
- 메모리 캐시는 최대 256개, 성공 24시간·실패 5분이다. 프로세스 재시작 시 사라진다. 사용자 메뉴판 사진은 이 캐시에 들어가지 않는다.
- HTTP 429의 `Retry-After`를 읽어 공유 cooldown 동안 새 공급처 요청을 중단한다. 제한·오류·redirect에서 다른 경로나 프록시로 우회하지 않는다.
- `tests/test_dish_images.py`: **24 passed in 0.10s**. HTTP 모의 응답으로 출처·라이선스·비음식·동음이의·redirect·429·timeout·잘못된 bbox·캐시·동시 실행·개인 사진 비저장을 검증했다.
- 2026-11-04 실제 확인: `Schnitzel`, `Bratwurst` 두 음식의 Wikipedia 메타데이터 요청이 이 실행 환경에서 모두 **HTTP 403**을 반환했다. 실제 대표 사진 확보에는 실패했으며 제한을 우회하지 않았다. 따라서 이 환경에서의 실제 카드 이미지는 유효한 메뉴판 사진 영역 또는 종류 참고 그림이다. 다른 배포 환경에서도 대표 사진 제공을 보장하지 않는다.
