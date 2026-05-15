from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import ExifTags

from .images import open_image

EXIF_DATE_FIELDS = ("DateTimeOriginal", "DateTimeDigitized", "DateTime")
_TAG_IDS_BY_NAME = {name: tag_id for tag_id, name in ExifTags.TAGS.items()}


def _parse_exif_datetime(value: object) -> datetime:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not isinstance(value, str):
        value = str(value)
    return datetime.strptime(value.strip(), "%Y:%m:%d %H:%M:%S")


def _get_pillow_exif_date(path: Path, warnings: list[str]) -> tuple[datetime, str] | None:
    try:
        with open_image(path) as image:
            exif = image.getexif()
            for field in EXIF_DATE_FIELDS:
                tag_id = _TAG_IDS_BY_NAME.get(field)
                if tag_id is None:
                    continue
                value = exif.get(tag_id)
                if not value:
                    continue
                try:
                    return _parse_exif_datetime(value), f"exif:{field}"
                except Exception as exc:
                    warnings.append(f"Could not parse EXIF {field}: {exc}")
    except Exception as exc:
        warnings.append(f"Could not read EXIF with Pillow: {exc}")
    return None


def _get_raw_exif_date(path: Path, warnings: list[str]) -> tuple[datetime, str] | None:
    """Read EXIF date fields from RAW files such as Nikon NEF via exifread."""
    try:
        import exifread
    except Exception as exc:
        warnings.append(f"Could not read RAW EXIF: exifread is not available ({exc})")
        return None

    tag_names = {
        "DateTimeOriginal": "EXIF DateTimeOriginal",
        "DateTimeDigitized": "EXIF DateTimeDigitized",
        "DateTime": "Image DateTime",
    }
    try:
        with path.open("rb") as handle:
            tags = exifread.process_file(handle, details=False, stop_tag="UNDEF")
    except Exception as exc:
        warnings.append(f"Could not read RAW EXIF: {exc}")
        return None

    for field in EXIF_DATE_FIELDS:
        value = tags.get(tag_names[field])
        if not value:
            continue
        try:
            return _parse_exif_datetime(value), f"exif:{field}"
        except Exception as exc:
            warnings.append(f"Could not parse EXIF {field}: {exc}")
    return None


def get_image_date(path: Path, config: dict) -> tuple[datetime, str, list[str]]:
    """Return image date, source label, and warnings.

    Prefers configured EXIF fields, falling back to filesystem mtime when enabled.
    """
    warnings: list[str] = []
    dates_config = config.get("dates", {})

    if dates_config.get("prefer_exif", True):
        exif_date = _get_pillow_exif_date(path, warnings)
        if exif_date is None and path.suffix.lower() == ".nef":
            exif_date = _get_raw_exif_date(path, warnings)
        if exif_date is not None:
            date, source = exif_date
            return date, source, warnings

    if dates_config.get("fallback_to_mtime", True):
        return datetime.fromtimestamp(path.stat().st_mtime), "filesystem:mtime", warnings

    raise ValueError(f"No image date available for {path}")
