"""승인한 현재 메뉴 1~2개만 기존 Food Guide 서버의 이미지 생성 함수로 생성한다."""
import argparse
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-root", required=True, type=Path, help="기존 Food Guide 프로젝트 경로")
    parser.add_argument("--input", required=True, type=Path, help="선택한 메뉴 1~2개의 정제 JSON 배열")
    parser.add_argument("--model", help="이 실행에만 적용할 OpenAI 이미지 모델")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.generated_menu_images import GeneratedImageError, descriptor, generate_batch
    try:
        if args.input.stat().st_size > 100_000:
            raise GeneratedImageError("입력 파일이 너무 큽니다.")
        items = json.loads(args.input.read_text("utf-8"))
        if not isinstance(items, list) or not 1 <= len(items) <= 2:
            raise GeneratedImageError("입력에는 1~2개 메뉴만 포함해야 합니다.")
        for item in items:
            if not isinstance(item, dict) or set(item) - {"input_name", "name_orig", "name_ko", "profile"}:
                raise GeneratedImageError("입력에는 음식명과 프로필만 포함해야 합니다.")
            descriptor(item)
        api_root = args.api_root.resolve(strict=True)
        if not (api_root / "foodguide" / "stage3.py").is_file():
            raise GeneratedImageError("기존 Food Guide 프로젝트를 찾을 수 없습니다.")
        sys.path.insert(0, str(api_root))
        from dotenv import load_dotenv
        from foodguide.models import FoodProfile
        from foodguide import stage3
        from foodguide.openai_client import GuideAPIError
        if Path(stage3.__file__).resolve() != api_root / "foodguide" / "stage3.py":
            raise GeneratedImageError("Food Guide 모듈 경로가 일치하지 않습니다.")
        load_dotenv(api_root / ".env", override=False)
        if args.model:
            os.environ["OPENAI_IMAGE_MODEL"] = args.model
        model = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
        def generate(profile):
            try:
                return stage3.generate_food_image(FoodProfile.model_validate(profile))
            except GuideAPIError as error:
                raise GeneratedImageError(str(error)) from None
        result = generate_batch(items, generate, model=model)
        print(json.dumps({"results": result}, ensure_ascii=False))
        return 0 if all(row["state"] in ("completed", "reused") for row in result) else 2
    except GeneratedImageError as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception:
        print("이미지 생성 입력 또는 서버 설정을 확인할 수 없습니다. 비밀값과 공급자 오류는 출력하지 않습니다.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
