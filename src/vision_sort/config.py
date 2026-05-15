from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

DEFAULT_CATEGORIES = [
    "Birds",
    "Mammals",
    "Insects",
    "Butterflies-Moths",
    "Reptiles-Amphibians",
    "Fish-Aquatic-Life",
    "Pets-Domestic-Animals",
    "Animal-Tracks-Signs",
    "Flowers",
    "Trees-Forests",
    "Leaves-Foliage",
    "Mushrooms-Fungi",
    "Moss-Lichen",
    "Plants-Other",
    "Mountains-Rocks",
    "Water-Rivers-Lakes",
    "Seascapes-Coast",
    "Fields-Meadows",
    "Sky-Clouds-Weather",
    "Sunrise-Sunset",
    "Snow-Ice",
    "Macro-Nature-Details",
    "People-Outdoors",
    "Buildings-Structures",
    "Trails-Paths",
    "Vehicles-Equipment",
    "Other-Nature",
    "Unclear-Needs-Review",
]

DEFAULT_SUPPORTED_EXTENSIONS = [
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".heic",
    ".heif",
    ".tif",
    ".tiff",
    ".bmp",
    ".gif",
    ".nef",
]

DEFAULT_CONFIG: dict[str, Any] = {
    "ollama": {
        "host": "http://localhost:11434",
        "model": "llama3.2-vision",
        "timeout_seconds": 600,
        "keep_alive": "30m",
        "options": {
            "temperature": 0,
            "num_predict": 80,
        },
        "image_max_size": 768,
        "jpeg_quality": 70,
    },
    "classification": {
        "fallback_category": "Unclear-Needs-Review",
        "min_confidence": 0.55,
        "categories": DEFAULT_CATEGORIES,
    },
    "files": {
        "recursive": True,
        "default_action": "copy",
        "supported_extensions": DEFAULT_SUPPORTED_EXTENSIONS,
        "duplicate_strategy": "append-counter",
    },
    "dates": {
        "prefer_exif": True,
        "fallback_to_mtime": True,
        "folder_date_format": "%Y_%m_%d",
    },
    "audit": {
        "enabled": True,
        "path": "vision-sort-audit.jsonl",
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | None = None) -> dict[str, Any]:
    """Load configuration from an explicit path or ./config.json when present."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    config_path = Path(path) if path else Path("config.json")
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            user_config = json.load(handle)
        if not isinstance(user_config, dict):
            raise ValueError(f"Config file must contain a JSON object: {config_path}")
        config = _deep_merge(config, user_config)
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    required_sections = ["ollama", "classification", "files", "dates", "audit"]
    for section in required_sections:
        if not isinstance(config.get(section), dict):
            raise ValueError(f"Missing or invalid config section: {section}")

    ollama = config["ollama"]
    if not isinstance(ollama.get("host"), str) or not ollama["host"]:
        raise ValueError("ollama.host must be a non-empty string")
    if not isinstance(ollama.get("model"), str) or not ollama["model"]:
        raise ValueError("ollama.model must be a non-empty string")
    if not isinstance(ollama.get("timeout_seconds"), (int, float)) or ollama["timeout_seconds"] <= 0:
        raise ValueError("ollama.timeout_seconds must be a positive number")
    if "keep_alive" in ollama and ollama["keep_alive"] is not None and not isinstance(ollama["keep_alive"], str):
        raise ValueError("ollama.keep_alive must be a string when provided")
    if not isinstance(ollama.get("options"), dict):
        raise ValueError("ollama.options must be an object")
    if "num_predict" in ollama["options"] and not isinstance(ollama["options"]["num_predict"], int):
        raise ValueError("ollama.options.num_predict must be an integer")
    if "temperature" in ollama["options"] and not isinstance(ollama["options"]["temperature"], (int, float)):
        raise ValueError("ollama.options.temperature must be a number")
    if not isinstance(ollama.get("image_max_size"), int) or ollama["image_max_size"] <= 0:
        raise ValueError("ollama.image_max_size must be a positive integer")
    if not isinstance(ollama.get("jpeg_quality"), int) or not 1 <= ollama["jpeg_quality"] <= 95:
        raise ValueError("ollama.jpeg_quality must be an integer between 1 and 95")

    classification = config["classification"]
    categories = classification.get("categories")
    fallback = classification.get("fallback_category")
    min_confidence = classification.get("min_confidence")
    if not isinstance(categories, list) or not categories or not all(isinstance(c, str) and c for c in categories):
        raise ValueError("classification.categories must be a non-empty list of strings")
    if len(set(categories)) != len(categories):
        raise ValueError("classification.categories must not contain duplicates")
    if not isinstance(fallback, str) or fallback not in categories:
        raise ValueError("classification.fallback_category must be included in classification.categories")
    if not isinstance(min_confidence, (int, float)) or not 0 <= min_confidence <= 1:
        raise ValueError("classification.min_confidence must be between 0 and 1")

    files = config["files"]
    extensions = files.get("supported_extensions")
    if files.get("default_action") not in {"copy", "move"}:
        raise ValueError("files.default_action must be 'copy' or 'move'")
    if not isinstance(files.get("recursive"), bool):
        raise ValueError("files.recursive must be a boolean")
    if not isinstance(extensions, list) or not extensions:
        raise ValueError("files.supported_extensions must be a non-empty list")
    for extension in extensions:
        if not isinstance(extension, str) or not extension.startswith("."):
            raise ValueError("Each supported extension must be a string starting with '.'")
    files["supported_extensions"] = [extension.lower() for extension in extensions]

    dates = config["dates"]
    if not isinstance(dates.get("prefer_exif"), bool):
        raise ValueError("dates.prefer_exif must be a boolean")
    if not isinstance(dates.get("fallback_to_mtime"), bool):
        raise ValueError("dates.fallback_to_mtime must be a boolean")
    if not isinstance(dates.get("folder_date_format"), str) or not dates["folder_date_format"]:
        raise ValueError("dates.folder_date_format must be a non-empty string")

    audit = config["audit"]
    if not isinstance(audit.get("enabled"), bool):
        raise ValueError("audit.enabled must be a boolean")
    if not isinstance(audit.get("path"), str) or not audit["path"]:
        raise ValueError("audit.path must be a non-empty string")
