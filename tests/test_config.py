from __future__ import annotations

import json

import pytest

from vision_sort.config import load_config, validate_config


def test_load_config_uses_defaults_when_no_config_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config["ollama"]["model"] == "llama3.2-vision"
    assert "Birds" in config["classification"]["categories"]
    assert ".heif" in config["files"]["supported_extensions"]
    assert ".nef" in config["files"]["supported_extensions"]


def test_load_config_merges_default_config_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    PathConfig = tmp_path / "config.json"
    PathConfig.write_text(json.dumps({"ollama": {"model": "llava"}}), encoding="utf-8")

    config = load_config()

    assert config["ollama"]["model"] == "llava"
    assert config["ollama"]["host"] == "http://localhost:11434"


def test_load_config_uses_explicit_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    explicit = tmp_path / "custom.json"
    explicit.write_text(json.dumps({"audit": {"path": "custom.jsonl"}}), encoding="utf-8")

    config = load_config(str(explicit))

    assert config["audit"]["path"] == "custom.jsonl"


def test_validate_config_requires_fallback_in_categories():
    config = load_config()
    config["classification"]["fallback_category"] = "Missing"

    with pytest.raises(ValueError, match="fallback_category"):
        validate_config(config)


def test_validate_config_normalizes_extensions_to_lowercase():
    config = load_config()
    config["files"]["supported_extensions"] = [".JPG"]

    validate_config(config)

    assert config["files"]["supported_extensions"] == [".jpg"]
