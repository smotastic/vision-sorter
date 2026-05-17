from __future__ import annotations

import json
from datetime import datetime, timezone

from vision_sort.classifier import ClassificationResult
from vision_sort.manifest import (
    build_manifest_entry,
    is_source_processed,
    load_processed_source_paths,
    repair_manifest,
    write_manifest_entry,
)


def test_write_manifest_entry_appends_sorted_jsonl_and_creates_parent(tmp_path):
    manifest = tmp_path / "sorted" / "index" / "manifest.jsonl"

    write_manifest_entry(manifest, {"b": 2, "a": 1})
    write_manifest_entry(manifest, {"c": 3})

    assert manifest.read_text(encoding="utf-8").splitlines() == [
        '{"a": 1, "b": 2}',
        '{"c": 3}',
    ]


def test_load_processed_source_paths_reads_source_paths_from_manifest(tmp_path):
    manifest = tmp_path / "sorted" / "index" / "manifest.jsonl"
    source = tmp_path / "incoming" / "photo.jpg"
    write_manifest_entry(manifest, {"source_path": str(source), "destination_path": "by-date/photo.jpg"})

    processed = load_processed_source_paths(manifest)

    assert is_source_processed(source, processed)
    assert not is_source_processed(tmp_path / "incoming" / "other.jpg", processed)


def test_load_processed_source_paths_ignores_entries_with_missing_destinations(tmp_path):
    destination = tmp_path / "sorted"
    manifest = destination / "index" / "manifest.jsonl"
    source = tmp_path / "incoming" / "photo.jpg"
    write_manifest_entry(manifest, {"source_path": str(source), "destination_path": "by-date/photo.jpg"})

    assert load_processed_source_paths(manifest, destination_root=destination) == set()


def test_repair_manifest_removes_entries_with_missing_destinations(tmp_path):
    destination = tmp_path / "sorted"
    manifest = destination / "index" / "manifest.jsonl"
    existing = destination / "by-date" / "kept.jpg"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"fake")
    write_manifest_entry(manifest, {"source_path": "incoming/kept.jpg", "destination_path": "by-date/kept.jpg"})
    write_manifest_entry(manifest, {"source_path": "incoming/missing.jpg", "destination_path": "by-date/missing.jpg"})

    assert repair_manifest(manifest, destination_root=destination) == 1

    entries = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    assert entries == [{"destination_path": "by-date/kept.jpg", "source_path": "incoming/kept.jpg"}]


def test_load_processed_source_paths_returns_empty_set_for_missing_manifest(tmp_path):
    assert load_processed_source_paths(tmp_path / "missing.jsonl") == set()


def test_build_manifest_entry_includes_sorted_image_metadata(tmp_path):
    classification = ClassificationResult("Birds", 0.9, "bird", "llama3.2-vision", [], "Songbird", "{}")
    sorted_at = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
    image_date = datetime(2026, 5, 15, 8, 30, tzinfo=timezone.utc)

    entry = build_manifest_entry(
        source=tmp_path / "incoming" / "photo.jpg",
        canonical_relative_path="by-date/2026/2026-05-15/Birds/photo.jpg",
        symlink_relative_path="by-category/Birds/2026/2026-05-15/photo.jpg",
        image_date=image_date,
        date_label="2026-05-15",
        date_source="mtime",
        classification=classification,
        action="copy",
        sorted_at=sorted_at,
    )

    assert entry["destination_path"] == "by-date/2026/2026-05-15/Birds/photo.jpg"
    assert entry["category_symlink_path"] == "by-category/Birds/2026/2026-05-15/photo.jpg"
    assert entry["category"] == "Birds"
    assert entry["preferred_category"] == "Songbird"
    assert entry["confidence"] == 0.9
    assert entry["sorted_at"] == "2026-05-16T12:00:00+00:00"
    assert entry["manifest_schema_version"] == 1
    assert "ollama_response" not in entry
