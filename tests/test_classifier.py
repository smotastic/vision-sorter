from __future__ import annotations

from pathlib import Path

from vision_sort.classifier import build_prompt, classify_image, parse_classification_response
from vision_sort.config import load_config


def test_prompt_includes_all_configured_categories():
    config = load_config()

    prompt = build_prompt(config["classification"]["categories"], config["classification"]["fallback_category"])

    assert "Return only strict JSON" in prompt
    for category in config["classification"]["categories"]:
        assert category in prompt


def test_parse_valid_json_response():
    config = load_config()

    result = parse_classification_response(
        '{"category":"Birds","confidence":0.82,"description":"bird on branch"}',
        config,
        "qwen3.6",
    )

    assert result.category == "Birds"
    assert result.confidence == 0.82
    assert result.description == "bird on branch"
    assert result.warnings == []


def test_parse_json_embedded_in_extra_text():
    config = load_config()

    result = parse_classification_response(
        'Here is the result: {"category":"Flowers","confidence":0.9,"description":"flower"}',
        config,
        "qwen3.6",
    )

    assert result.category == "Flowers"


def test_invalid_json_routes_to_fallback():
    config = load_config()

    result = parse_classification_response("not json", config, "qwen3.6")

    assert result.category == "Unclear-Needs-Review"
    assert result.confidence is None
    assert result.warnings


def test_unknown_category_routes_to_fallback():
    config = load_config()

    result = parse_classification_response(
        '{"category":"Songbird","confidence":0.9,"description":"bird"}',
        config,
        "qwen3.6",
    )

    assert result.category == "Unclear-Needs-Review"
    assert any("unknown category" in warning for warning in result.warnings)


def test_low_confidence_routes_to_fallback():
    config = load_config()

    result = parse_classification_response(
        '{"category":"Birds","confidence":0.1,"description":"maybe a bird"}',
        config,
        "qwen3.6",
    )

    assert result.category == "Unclear-Needs-Review"
    assert result.confidence == 0.1
    assert any("below threshold" in warning for warning in result.warnings)


def test_classify_image_calls_ollama(monkeypatch, tmp_path):
    config = load_config()
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"fake")

    normalized = tmp_path / "normalized.jpg"
    normalized.write_bytes(b"normalized")
    monkeypatch.setattr("vision_sort.classifier.normalize_image_for_ollama", lambda p: (normalized, ["converted"]))

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": '{"category":"Birds","confidence":0.8,"description":"bird"}'}

    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        return FakeResponse()

    monkeypatch.setattr("vision_sort.classifier.requests.post", fake_post)

    result = classify_image(path, config, model_override="llava")

    assert result.category == "Birds"
    assert result.model == "llava"
    assert result.warnings == ["converted"]
    assert calls[0][0] == "http://localhost:11434/api/generate"
    assert calls[0][1]["images"] == ["bm9ybWFsaXplZA=="]
    assert calls[0][2] == 600
    assert not normalized.exists()


def test_classify_image_returns_fallback_on_ollama_failure(monkeypatch, tmp_path):
    config = load_config()
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"fake")
    normalized = tmp_path / "normalized.jpg"
    normalized.write_bytes(b"normalized")
    monkeypatch.setattr("vision_sort.classifier.normalize_image_for_ollama", lambda p: (normalized, []))

    def fake_post(url, json, timeout):
        raise RuntimeError("offline")

    monkeypatch.setattr("vision_sort.classifier.requests.post", fake_post)

    result = classify_image(path, config)

    assert result.category == "Unclear-Needs-Review"
    assert any("Ollama request failed" in warning for warning in result.warnings)
    assert not normalized.exists()
