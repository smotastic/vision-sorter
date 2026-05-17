from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _source_path_keys(source: str | Path) -> set[str]:
    path = Path(source)
    return {str(path), str(path.resolve())}


def _read_manifest_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid manifest JSON at {path}:{line_number}: {exc.msg}") from exc
            if isinstance(entry, dict):
                entries.append(entry)
    return entries


def _manifest_entry_destination_exists(destination_root: Path, entry: dict[str, Any]) -> bool:
    destination_path = entry.get("destination_path")
    if not isinstance(destination_path, str) or not destination_path:
        return False
    path = Path(destination_path)
    if path.is_absolute() or ".." in path.parts:
        return False
    return (destination_root / path).exists()


def load_processed_source_paths(path: Path, *, destination_root: Path | None = None) -> set[str]:
    """Return source path keys already recorded in a manifest JSONL file.

    When destination_root is provided, stale entries whose canonical destination file is
    missing are ignored so deleted files can be processed again.
    """
    processed: set[str] = set()
    for entry in _read_manifest_entries(path):
        if destination_root is not None and not _manifest_entry_destination_exists(destination_root, entry):
            continue
        source_path = entry.get("source_path")
        if isinstance(source_path, str) and source_path:
            processed.update(_source_path_keys(source_path))
    return processed


def repair_manifest(path: Path, *, destination_root: Path) -> int:
    """Remove manifest entries whose canonical destination file is missing.

    Returns the number of stale entries removed.
    """
    entries = _read_manifest_entries(path)
    if not entries:
        return 0

    retained = [entry for entry in entries if _manifest_entry_destination_exists(destination_root, entry)]
    removed = len(entries) - len(retained)
    if removed == 0:
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for entry in retained:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return removed


def is_source_processed(source: Path, processed_source_paths: set[str]) -> bool:
    return any(key in processed_source_paths for key in _source_path_keys(source))


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
