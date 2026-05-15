from __future__ import annotations

import re
from pathlib import Path


def discover_images(source: Path, extensions: set[str], recursive: bool = True) -> list[Path]:
    """Return supported image files below source, sorted for deterministic output."""
    normalized_extensions = {extension.lower() for extension in extensions}
    pattern = "**/*" if recursive else "*"
    return sorted(
        path
        for path in source.glob(pattern)
        if path.is_file() and path.suffix.lower() in normalized_extensions
    )


def sanitize_category(category: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", category.strip())
    sanitized = re.sub(r"-+", "-", sanitized).strip(".-")
    return sanitized or "Uncategorized"


def build_destination_path(destination_root: Path, date_label: str, category: str, source: Path) -> Path:
    """Build a date/category destination, appending -N when the target exists."""
    folder = destination_root / f"{date_label}-{sanitize_category(category)}"
    candidate = folder / source.name
    if not candidate.exists():
        return candidate

    stem = source.stem
    suffix = source.suffix
    counter = 1
    while True:
        candidate = folder / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
