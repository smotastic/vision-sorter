from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .images import normalize_image_for_ollama


@dataclass
class ClassificationResult:
    category: str
    confidence: float | None
    description: str
    model: str
    warnings: list[str]
    preferred_category: str = ""
    raw_response: str = ""


def build_prompt(categories: list[str], fallback_category: str) -> str:
    category_lines = "\n".join(f"- {category}" for category in categories)
    return (
        "You are classifying a photo for filesystem organization.\n"
        "Choose exactly one category from this allowed list:\n"
        f"{category_lines}\n\n"
        f"If the image is ambiguous or does not fit, choose {fallback_category}.\n"
        "Also include preferred_category: the category name you would have chosen if you were not restricted to the allowed list.\n"
        "Return only strict JSON with this schema:\n"
        '{"category":"<one allowed category>","preferred_category":"<free-form best category>","confidence":0.0,"description":"short visual description"}\n'
        "Confidence must be a number from 0 to 1. Do not include markdown or extra text."
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model response did not contain a JSON object")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Model JSON response must be an object")
    return parsed


def parse_classification_response(response_text: str, config: dict, model: str, warnings: list[str] | None = None) -> ClassificationResult:
    warnings = list(warnings or [])
    classification = config["classification"]
    fallback = classification["fallback_category"]
    categories = set(classification["categories"])
    min_confidence = classification["min_confidence"]

    try:
        parsed = _extract_json_object(response_text)
    except Exception as exc:
        warnings.append(f"Invalid model JSON response: {exc}")
        return ClassificationResult(fallback, None, "", model, warnings, raw_response=response_text)

    category = parsed.get("category")
    preferred_category = parsed.get("preferred_category") or ""
    description = parsed.get("description") or ""
    confidence_value = parsed.get("confidence")
    try:
        confidence = float(confidence_value)
    except (TypeError, ValueError):
        confidence = None
        warnings.append("Model confidence was missing or not numeric")

    if category not in categories:
        warnings.append(f"Model returned unknown category: {category!r}")
        category = fallback
    if confidence is None or confidence < min_confidence:
        warnings.append(f"Model confidence below threshold: {confidence!r}")
        category = fallback

    return ClassificationResult(str(category), confidence, str(description), model, warnings, str(preferred_category), response_text)


def _extract_ollama_response_text(body: Any, warnings: list[str]) -> str:
    """Return generated text from common Ollama-compatible response shapes."""
    if not isinstance(body, dict):
        warnings.append(f"Ollama returned unexpected JSON type: {type(body).__name__}")
        return ""

    if body.get("error"):
        warnings.append(f"Ollama returned error: {body['error']}")

    response_text = body.get("response")
    if isinstance(response_text, str) and response_text.strip():
        return response_text

    message = body.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content

    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content
            text = first.get("text")
            if isinstance(text, str) and text.strip():
                return text

    keys = ", ".join(sorted(str(key) for key in body.keys())) or "none"
    preview = json.dumps(body, default=str)[:500]
    warnings.append(f"Ollama response did not include generated text; keys: {keys}; body preview: {preview}")
    return ""


def classify_image(path: Path, config: dict, model_override: str | None = None) -> ClassificationResult:
    ollama = config["ollama"]
    classification = config["classification"]
    model = model_override or ollama["model"]
    warnings: list[str] = []

    normalized_image_path: Path | None = None
    try:
        normalized_image_path, image_warnings = normalize_image_for_ollama(
            path,
            max_size=ollama["image_max_size"],
            jpeg_quality=ollama["jpeg_quality"],
        )
        warnings.extend(image_warnings)
        image_payload = base64.b64encode(normalized_image_path.read_bytes()).decode("ascii")
        prompt = build_prompt(classification["categories"], classification["fallback_category"])
        url = ollama["host"].rstrip("/") + "/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "images": [image_payload],
            "stream": False,
            "format": "json",
            "options": ollama["options"],
        }
        if ollama.get("keep_alive"):
            payload["keep_alive"] = ollama["keep_alive"]

        response = requests.post(url, json=payload, timeout=ollama["timeout_seconds"])
        response.raise_for_status()
        body = response.json()
    except Exception as exc:
        warnings.append(f"Ollama request failed: {exc}")
        return ClassificationResult(classification["fallback_category"], None, "", model, warnings)
    finally:
        if normalized_image_path is not None:
            try:
                os.unlink(normalized_image_path)
            except OSError as exc:
                warnings.append(f"Could not remove temporary Ollama image {normalized_image_path}: {exc}")

    response_text = _extract_ollama_response_text(body, warnings)
    if not response_text:
        return ClassificationResult(classification["fallback_category"], None, "", model, warnings)
    return parse_classification_response(response_text, config, model, warnings)
