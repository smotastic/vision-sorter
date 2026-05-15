from __future__ import annotations

from datetime import datetime

from PIL import ExifTags, Image

from vision_sort.config import load_config
from vision_sort.dates import _get_raw_exif_date, get_image_date

_TAG_IDS_BY_NAME = {name: tag_id for tag_id, name in ExifTags.TAGS.items()}


def _write_jpeg(path, exif_values=None):
    image = Image.new("RGB", (10, 10), color="red")
    exif = Image.Exif()
    for name, value in (exif_values or {}).items():
        exif[_TAG_IDS_BY_NAME[name]] = value
    image.save(path, exif=exif)


def test_get_image_date_prefers_datetime_original(tmp_path):
    path = tmp_path / "photo.jpg"
    _write_jpeg(
        path,
        {
            "DateTimeOriginal": "2024:08:03 09:41:22",
            "DateTimeDigitized": "2023:01:02 03:04:05",
        },
    )

    date, source, warnings = get_image_date(path, load_config())

    assert date == datetime(2024, 8, 3, 9, 41, 22)
    assert source == "exif:DateTimeOriginal"
    assert warnings == []


def test_get_image_date_uses_digitized_then_datetime(tmp_path):
    digitized = tmp_path / "digitized.jpg"
    generic = tmp_path / "generic.jpg"
    _write_jpeg(digitized, {"DateTimeDigitized": "2023:01:02 03:04:05"})
    _write_jpeg(generic, {"DateTime": "2022:02:03 04:05:06"})

    date, source, _ = get_image_date(digitized, load_config())
    generic_date, generic_source, _ = get_image_date(generic, load_config())

    assert date == datetime(2023, 1, 2, 3, 4, 5)
    assert source == "exif:DateTimeDigitized"
    assert generic_date == datetime(2022, 2, 3, 4, 5, 6)
    assert generic_source == "exif:DateTime"


def test_get_image_date_falls_back_to_mtime(tmp_path):
    path = tmp_path / "photo.jpg"
    _write_jpeg(path)
    expected_timestamp = datetime(2021, 5, 6, 7, 8, 9).timestamp()
    path.touch()
    import os

    os.utime(path, (expected_timestamp, expected_timestamp))

    date, source, warnings = get_image_date(path, load_config())

    assert date == datetime.fromtimestamp(expected_timestamp)
    assert source == "filesystem:mtime"
    assert warnings == []


def test_get_image_date_warns_on_bad_exif_then_falls_back(tmp_path):
    path = tmp_path / "photo.jpg"
    _write_jpeg(path, {"DateTimeOriginal": "not a date"})

    _, source, warnings = get_image_date(path, load_config())

    assert source == "filesystem:mtime"
    assert any("Could not parse EXIF DateTimeOriginal" in warning for warning in warnings)


def test_raw_exif_date_supports_nef_tags(tmp_path, monkeypatch):
    path = tmp_path / "photo.NEF"
    path.write_bytes(b"fake nef")

    class FakeExifread:
        @staticmethod
        def process_file(handle, details=False, stop_tag="UNDEF"):
            return {"EXIF DateTimeOriginal": "2020:01:02 03:04:05"}

    import sys

    monkeypatch.setitem(sys.modules, "exifread", FakeExifread)
    warnings = []

    date, source = _get_raw_exif_date(path, warnings)

    assert date == datetime(2020, 1, 2, 3, 4, 5)
    assert source == "exif:DateTimeOriginal"
    assert warnings == []
