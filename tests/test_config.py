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
    assert config["layout"]["date_root"] == "by-date"
    assert config["layout"]["category_index_root"] == "by-category"
    assert config["layout"]["manifest_path"] == "index/manifest.jsonl"


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


def test_default_date_format_is_iso_hyphenated():
    config = load_config()

    assert config["dates"]["folder_date_format"] == "%Y-%m-%d"


def test_validate_config_rejects_absolute_layout_paths(tmp_path):
    config = load_config()
    config["layout"]["date_root"] = str(tmp_path / "outside")

    with pytest.raises(ValueError, match="layout.date_root must be a relative path"):
        validate_config(config)


def test_validate_config_rejects_parent_layout_segments():
    config = load_config()
    config["layout"]["manifest_path"] = "../manifest.jsonl"

    with pytest.raises(ValueError, match="layout.manifest_path must not contain"):
        validate_config(config)


def test_validate_config_requires_boolean_symlink_setting():
    config = load_config()
    config["layout"]["create_category_symlinks"] = "yes"

    with pytest.raises(ValueError, match="layout.create_category_symlinks"):
        validate_config(config)
