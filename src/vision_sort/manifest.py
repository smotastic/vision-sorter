from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_manifest_entry(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def build_manifest_entry(
    *,
    source: Path,
    canonical_relative_path: Path,
    symlink_relative_path: Path | None,
    image_date: datetime,
    date_label: str,
    date_source: str,
    classification: Any,
    action: str,
    sorted_at: datetime | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timestamp = sorted_at or datetime.now(timezone.utc)
    entry: dict[str, Any] = {
        "source_path": str(source),
        "destination_path": str(canonical_relative_path),
        "category_symlink_path": str(symlink_relative_path) if symlink_relative_path is not None else "",
        "date": image_date.isoformat(),
        "date_label": date_label,
        "date_source": date_source,
        "category": classification.category,
        "preferred_category": classification.preferred_category,
        "confidence": classification.confidence,
        "description": classification.description,
        "model": classification.model,
        "action": action,
        "sorted_at": timestamp.isoformat(),
        "manifest_schema_version": 1,
    }
    if extra:
        entry.update(extra)
    return entry
