from __future__ import annotations

from pathlib import Path

from vision_sort.files import build_destination_path, discover_images, sanitize_category


def test_discover_images_recurses_case_insensitively(tmp_path):
    source = tmp_path / "incoming"
    nested = source / "nested"
    nested.mkdir(parents=True)
    jpg = source / "A.JPG"
    png = nested / "b.png"
    nef = nested / "raw.NEF"
    txt = nested / "note.txt"
    jpg.write_bytes(b"jpg")
    png.write_bytes(b"png")
    nef.write_bytes(b"nef")
    txt.write_text("ignore", encoding="utf-8")

    images = discover_images(source, {".jpg", ".png", ".nef"}, recursive=True)

    assert images == sorted([jpg, png, nef])


def test_discover_images_can_scan_non_recursive(tmp_path):
    source = tmp_path / "incoming"
    nested = source / "nested"
    nested.mkdir(parents=True)
    root_image = source / "root.jpg"
    nested_image = nested / "nested.jpg"
    root_image.write_bytes(b"root")
    nested_image.write_bytes(b"nested")

    images = discover_images(source, {".jpg"}, recursive=False)

    assert images == [root_image]


def test_build_destination_path_uses_date_category_and_name(tmp_path):
    source = tmp_path / "IMG_1234.JPG"

    destination = build_destination_path(tmp_path / "sorted", "2026_05_15", "Birds", source)

    assert destination == tmp_path / "sorted" / "2026_05_15-Birds" / "IMG_1234.JPG"


def test_build_destination_path_appends_counter_for_duplicates(tmp_path):
    source = tmp_path / "IMG_1234.JPG"
    existing_dir = tmp_path / "sorted" / "2026_05_15-Birds"
    existing_dir.mkdir(parents=True)
    (existing_dir / "IMG_1234.JPG").write_bytes(b"one")
    (existing_dir / "IMG_1234-1.JPG").write_bytes(b"two")

    destination = build_destination_path(tmp_path / "sorted", "2026_05_15", "Birds", source)

    assert destination.name == "IMG_1234-2.JPG"


def test_sanitize_category_removes_filesystem_sensitive_characters():
    assert sanitize_category(" Birds / Wildlife ") == "Birds-Wildlife"
