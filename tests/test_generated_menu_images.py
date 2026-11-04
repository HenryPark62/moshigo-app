"""생성 API 없이 로컬 이미지 identity·저장·재시도 방지를 검증한다."""
import io
import json

from PIL import Image
import pytest

from core import generated_menu_images as images


def item(name="슈니첼", ingredients=None):
    return {"input_name": "Schnitzel", "name_orig": "Schnitzel", "name_ko": name,
            "profile": {"name": name, "original_name": "Schnitzel", "main_ingredients": ingredients or ["돼지고기", "빵가루"],
                        "cooking_methods": ["튀기기"], "status": "known", "notes": "생성 prompt에 쓰지 않는 필드"}}


def png():
    output = io.BytesIO()
    Image.new("RGB", (32, 32), "orange").save(output, "PNG")
    return output.getvalue()


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "ASSET_DIR", tmp_path)
    return tmp_path


def test_exact_recipe_matching_and_unused_fields_do_not_affect_identity(root):
    results = images.generate_batch([item()], lambda _: png(), model="image-model")
    assert results[0]["state"] == "completed"
    result = images.get_generated_image(item())
    assert result["src"].startswith("data:image/png;base64,") and result["label"] == "AI 생성 이미지"
    assert set(result) == {"src", "label", "title", "author", "license", "source_url", "license_url"}
    changed = item()
    changed["profile"]["notes"] = "다른 설명"
    changed["input_name"] = "다른 화면 이름"
    assert images.get_generated_image(changed) == result
    assert images.get_generated_image(item(ingredients=["닭고기", "빵가루"])) is None


def test_nfc_whitespace_normalized_in_actual_generator_input_and_lookup(root):
    original = item(name="  Cafe\u0301   메뉴 ")
    original["profile"]["main_ingredients"] = [" 돼지\n 고기 "]
    received = []
    def generate(profile):
        received.append(profile)
        return png()
    images.generate_batch([original], generate, model="image-model")
    assert received[0]["name"] == "Café 메뉴" and received[0]["main_ingredients"] == ["돼지 고기"]
    normalized = item(name="Café 메뉴", ingredients=["돼지 고기"])
    assert images.get_generated_image(normalized)


def test_pending_written_before_call_and_success_reused_without_provider(root):
    calls = []
    def generate(profile):
        manifest = json.loads((root / "manifest.json").read_text())
        assert next(iter(manifest["entries"].values()))["state"] == "pending"
        calls.append(profile)
        return png()
    first = images.generate_batch([item()], generate, model="image-model")
    second = images.generate_batch([item()], generate, model="image-model")
    assert len(calls) == 1 and second[0]["state"] == "reused"
    assert first[0]["generation_key"] == second[0]["generation_key"]
    manifest = json.loads((root / "manifest.json").read_text())
    record = next(iter(manifest["entries"].values()))
    assert record["model"] == "image-model" and record["quality"] == "low"
    assert record["descriptor"] == images.descriptor(item()) and record["sha256"]


def test_uncertain_generation_is_not_retried_and_raw_errors_not_saved(root):
    calls = []
    def generate(_):
        calls.append(1)
        raise RuntimeError("private-token provider traceback")
    assert images.generate_batch([item()], generate, model="image-model")[0]["state"] == "uncertain"
    assert images.generate_batch([item()], generate, model="image-model")[0]["state"] == "blocked"
    assert len(calls) == 1 and images.get_generated_image(item()) is None
    assert "private-token" not in (root / "manifest.json").read_text()


@pytest.mark.parametrize("alter", [
    lambda r: r.update(file="../outside.png"),
    lambda r: r.update(file="https://example.test/image.png"),
    lambda r: r.update(sha256="0" * 64),
    lambda r: r.update(descriptor_hash="0" * 64),
    lambda r: r.update(model="different-model"),
    lambda r: r.update(prompt_version="future-version"),
])
def test_invalid_manifest_paths_hashes_and_identity_are_not_displayed(root, alter):
    images.generate_batch([item()], lambda _: png(), model="image-model")
    path = root / "manifest.json"
    data = json.loads(path.read_text())
    alter(next(iter(data["entries"].values())))
    path.write_text(json.dumps(data))
    assert images.get_generated_image(item()) is None


def test_symlink_and_corrupted_png_are_not_read_or_regenerated(root):
    result = images.generate_batch([item()], lambda _: png(), model="image-model")[0]
    path = root / result["file"]
    outside = root / "other.png"
    path.rename(outside)
    path.symlink_to(outside)
    assert images.get_generated_image(item()) is None
    assert images.generate_batch([item()], lambda _: pytest.fail("must not retry"), model="image-model")[0]["state"] == "blocked"
    path.unlink()
    path.write_bytes(b"invalid")
    assert images.get_generated_image(item()) is None


@pytest.mark.parametrize("items", [[], [item(), item(), item()]])
def test_batch_count_rejected_before_any_generation(root, items):
    with pytest.raises(images.GeneratedImageError):
        images.generate_batch(items, lambda _: pytest.fail("must not call"), model="image-model")
    assert not (root / "manifest.json").exists()


def test_at_most_two_calls_and_duplicate_recipe_deduplicated(root):
    calls = []
    def generate(profile):
        calls.append(profile)
        return png()
    images.generate_batch([item(), item()], generate, model="image-model")
    assert len(calls) == 1
    images.generate_batch([item(ingredients=["생선"]), item(ingredients=["소고기"])], generate, model="image-model")
    assert len(calls) == 3  # 두 번째 호출에서 추가 생성은 정확히 두 번.


def test_invalid_generated_bytes_remain_uncertain(root):
    result = images.generate_batch([item()], lambda _: b"not a PNG", model="image-model")
    assert result[0]["state"] == "uncertain" and not list(root.glob("*.png"))


def test_existing_pending_and_lock_never_make_paid_call(root):
    images.generate_batch([item()], lambda _: png(), model="image-model")
    path = root / "manifest.json"
    data = json.loads(path.read_text())
    next(iter(data["entries"].values()))["state"] = "pending"
    path.write_text(json.dumps(data))
    assert images.generate_batch([item()], lambda _: pytest.fail("must not call"), model="image-model")[0]["state"] == "blocked"
    (root / ".generation.lock").write_text("")
    with pytest.raises(images.GeneratedImageError):
        images.generate_batch([item()], lambda _: pytest.fail("must not call"), model="image-model")
