from __future__ import annotations

import base64
import json
import os
import re
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
        "Keep preferred_category to 1-3 words and description to 12 words or fewer.\n"
        "Return only strict JSON with this schema:\n"
        '{"category":"<one allowed category>","preferred_category":"<free-form best category>","confidence":0.0,"description":"short visual description"}\n'
        "Confidence must be a number from 0 to 1. Do not include markdown or extra text."
    )


def _json_string_value(text: str, key: str) -> str | None:
    match = re.search(rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"', text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return match.group(1)


def _truncated_json_string_value(text: str, key: str) -> str | None:
    marker = f'"{key}"'
    start = text.find(marker)
    if start == -1:
        return None
    colon = text.find(":", start + len(marker))
    if colon == -1:
        return None
    quote = text.find('"', colon + 1)
    if quote == -1:
        return None
    value = text[quote + 1 :]
    return value.rstrip(' ,')


def _recover_truncated_json_object(text: str) -> dict[str, Any] | None:
    """Recover useful fields from an Ollama response cut off mid-JSON.

    Ollama may stop at num_predict before emitting the closing quote/brace. The
    category and confidence usually appear before the truncated description, so
    salvaging them avoids unnecessary Unclear-Needs-Review results.
    """
    category = _json_string_value(text, "category")
    confidence_match = re.search(r'"confidence"\s*:\s*(-?\d+(?:\.\d+)?)', text)
    if category is None or confidence_match is None:
        return None

    recovered: dict[str, Any] = {
        "category": category,
        "confidence": float(confidence_match.group(1)),
    }
    preferred_category = _json_string_value(text, "preferred_category")
    if preferred_category is not None:
        recovered["preferred_category"] = preferred_category
    description = _json_string_value(text, "description")
    if description is None:
        description = _truncated_json_string_value(text, "description")
    if description is not None:
        recovered["description"] = description
    return recovered


def _extract_json_object(text: str) -> tuple[dict[str, Any], bool]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed, False
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1:
        raise ValueError("Model response did not contain a JSON object")
    if end > start:
        parsed = json.loads(text[start : end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("Model JSON response must be an object")
        return parsed, False

    recovered = _recover_truncated_json_object(text[start:])
    if recovered is not None:
        return recovered, True
    raise ValueError("Model response did not contain a complete JSON object")


def parse_classification_response(response_text: str, config: dict, model: str, warnings: list[str] | None = None) -> ClassificationResult:
    warnings = list(warnings or [])
    classification = config["classification"]
    fallback = classification["fallback_category"]
    categories = set(classification["categories"])
    min_confidence = classification["min_confidence"]

    try:
        parsed, recovered_truncated = _extract_json_object(response_text)
    except Exception as exc:
        warnings.append(f"Invalid model JSON response: {exc}")
        return ClassificationResult(fallback, None, "", model, warnings, raw_response=response_text)
    if recovered_truncated:
        warnings.append("Recovered classification fields from truncated model JSON response")

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
