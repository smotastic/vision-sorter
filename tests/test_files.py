from __future__ import annotations

import os
from pathlib import Path

import pytest

from vision_sort.files import (
    allocate_duplicate_path,
    build_by_date_destination_path,
    build_category_symlink_path,
    build_destination_path,
    create_relative_symlink,
    discover_images,
    sanitize_category,
)


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


def test_build_by_date_destination_path_uses_date_year_category_and_name(tmp_path):
    source = tmp_path / "IMG_1234.JPG"

    destination = build_by_date_destination_path(tmp_path / "sorted", "2026-05-15", "Birds", source)

    assert destination == tmp_path / "sorted" / "by-date" / "2026" / "2026-05-15" / "Birds" / "IMG_1234.JPG"


def test_build_destination_path_wraps_by_date_layout(tmp_path):
    source = tmp_path / "IMG_1234.JPG"

    destination = build_destination_path(tmp_path / "sorted", "2026-05-15", "Birds", source)

    assert destination == tmp_path / "sorted" / "by-date" / "2026" / "2026-05-15" / "Birds" / "IMG_1234.JPG"


def test_build_by_date_destination_path_appends_counter_for_duplicates(tmp_path):
    source = tmp_path / "IMG_1234.JPG"
    existing_dir = tmp_path / "sorted" / "by-date" / "2026" / "2026-05-15" / "Birds"
    existing_dir.mkdir(parents=True)
    (existing_dir / "IMG_1234.JPG").write_bytes(b"one")
    (existing_dir / "IMG_1234-1.JPG").write_bytes(b"two")

    destination = build_by_date_destination_path(tmp_path / "sorted", "2026-05-15", "Birds", source)

    assert destination.name == "IMG_1234-2.JPG"


def test_build_category_symlink_path_uses_category_year_date_and_name(tmp_path):
    canonical = tmp_path / "sorted" / "by-date" / "2026" / "2026-05-15" / "Birds" / "IMG_1234.JPG"

    link = build_category_symlink_path(tmp_path / "sorted", canonical, "2026-05-15", "Birds")

    assert link == tmp_path / "sorted" / "by-category" / "Birds" / "2026" / "2026-05-15" / "IMG_1234.JPG"


def test_allocate_duplicate_path_checks_symlinks_too(tmp_path):
    target = tmp_path / "target.jpg"
    target.write_bytes(b"target")
    candidate = tmp_path / "photo.jpg"
    candidate.symlink_to(target)

    assert allocate_duplicate_path(candidate) == tmp_path / "photo-1.jpg"


def test_create_relative_symlink_creates_relative_link(tmp_path):
    target = tmp_path / "sorted" / "by-date" / "2026" / "2026-05-15" / "Birds" / "photo.jpg"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"photo")
    link = tmp_path / "sorted" / "by-category" / "Birds" / "2026" / "2026-05-15" / "photo.jpg"

    create_relative_symlink(link, target)

    assert link.is_symlink()
    assert os.readlink(link) == "../../../../by-date/2026/2026-05-15/Birds/photo.jpg"
    assert link.resolve() == target


def test_create_relative_symlink_is_idempotent_for_same_target(tmp_path):
    target = tmp_path / "target.jpg"
    target.write_bytes(b"target")
    link = tmp_path / "links" / "target.jpg"

    create_relative_symlink(link, target)
    create_relative_symlink(link, target)

    assert link.resolve() == target


def test_create_relative_symlink_does_not_overwrite_real_files(tmp_path):
    target = tmp_path / "target.jpg"
    target.write_bytes(b"target")
    link = tmp_path / "links" / "target.jpg"
    link.parent.mkdir()
    link.write_bytes(b"real")

    with pytest.raises(FileExistsError):
        create_relative_symlink(link, target)


def test_sanitize_category_removes_filesystem_sensitive_characters():
    assert sanitize_category(" Birds / Wildlife ") == "Birds-Wildlife"
