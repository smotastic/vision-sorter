from __future__ import annotations

import os
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


def allocate_duplicate_path(candidate: Path) -> Path:
    """Return candidate or append -N before suffix when it already exists."""
    if not candidate.exists() and not candidate.is_symlink():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    parent = candidate.parent
    counter = 1
    while True:
        alternate = parent / f"{stem}-{counter}{suffix}"
        if not alternate.exists() and not alternate.is_symlink():
            return alternate
        counter += 1


def _year_from_date_label(date_label: str) -> str:
    if len(date_label) < 4 or not date_label[:4].isdigit():
        raise ValueError(f"date_label must start with a four-digit year: {date_label!r}")
    return date_label[:4]


def build_by_date_destination_path(
    destination_root: Path,
    date_label: str,
    category: str,
    source: Path,
    *,
    date_root: str = "by-date",
) -> Path:
    """Build sorted/by-date/YYYY/YYYY-MM-DD/Category/name.ext with duplicate counter."""
    folder = destination_root / date_root / _year_from_date_label(date_label) / date_label / sanitize_category(category)
    return allocate_duplicate_path(folder / source.name)


def build_category_symlink_path(
    destination_root: Path,
    canonical_path: Path,
    date_label: str,
    category: str,
    *,
    category_index_root: str = "by-category",
) -> Path:
    """Build sorted/by-category/Category/YYYY/YYYY-MM-DD/name.ext with duplicate counter."""
    folder = destination_root / category_index_root / sanitize_category(category) / _year_from_date_label(date_label) / date_label
    return allocate_duplicate_path(folder / canonical_path.name)


def create_relative_symlink(link_path: Path, target_path: Path) -> None:
    """Create a relative symlink, replacing only safe stale/broken symlinks if needed."""
    link_path.parent.mkdir(parents=True, exist_ok=True)
    relative_target = Path(os.path.relpath(target_path, start=link_path.parent))

    if link_path.is_symlink():
        if Path(os.readlink(link_path)) == relative_target:
            return
        link_path.unlink()
    elif link_path.exists():
        raise FileExistsError(f"Cannot overwrite non-symlink path: {link_path}")

    link_path.symlink_to(relative_target)


def build_destination_path(destination_root: Path, date_label: str, category: str, source: Path) -> Path:
    """Build a by-date destination, appending -N when the target exists."""
    return build_by_date_destination_path(destination_root, date_label, category, source)
