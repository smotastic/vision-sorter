from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "migrate_sorted_layout.py"
spec = importlib.util.spec_from_file_location("migrate_sorted_layout", SCRIPT_PATH)
migrate_sorted_layout = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = migrate_sorted_layout
spec.loader.exec_module(migrate_sorted_layout)


def write_audit(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_parse_old_layout_dir_accepts_valid_and_ignores_invalid(tmp_path):
    valid = tmp_path / "2025_04_05-Birds"
    valid.mkdir()
    invalid = tmp_path / "not-old-layout"
    invalid.mkdir()

    assert migrate_sorted_layout.parse_old_layout_dir(valid) == ("2025-04-05", "Birds")
    assert migrate_sorted_layout.parse_old_layout_dir(invalid) is None


def test_dry_run_reports_planned_copies_but_writes_nothing(tmp_path):
    sorted_root = tmp_path / "sorted"
    old = sorted_root / "2025_04_05-Birds"
    old.mkdir(parents=True)
    (old / "photo.jpg").write_bytes(b"photo")

    stats = migrate_sorted_layout.migrate(sorted_root, tmp_path / "missing.jsonl", apply=False)

    assert stats.discovered == 1
    assert stats.copied == 1
    assert not (sorted_root / "by-date").exists()
    assert not (sorted_root / "by-category").exists()
    assert not (sorted_root / "index" / "manifest.jsonl").exists()


def test_apply_copies_creates_symlink_and_preserves_old_file(tmp_path):
    sorted_root = tmp_path / "sorted"
    old = sorted_root / "2025_04_05-Birds"
    old.mkdir(parents=True)
    source = old / "photo.jpg"
    source.write_bytes(b"photo")

    stats = migrate_sorted_layout.migrate(sorted_root, tmp_path / "missing.jsonl", apply=True)

    destination = sorted_root / "by-date" / "2025" / "2025-04-05" / "Birds" / "photo.jpg"
    link = sorted_root / "by-category" / "Birds" / "2025" / "2025-04-05" / "photo.jpg"
    assert stats.failures == 0
    assert destination.read_bytes() == b"photo"
    assert link.is_symlink()
    assert link.resolve() == destination
    assert source.exists()


def test_apply_writes_manifest_enriched_from_matching_audit(tmp_path):
    sorted_root = tmp_path / "sorted"
    old = sorted_root / "2025_04_05-Birds"
    old.mkdir(parents=True)
    (old / "photo.jpg").write_bytes(b"photo")
    audit = tmp_path / "audit.jsonl"
    write_audit(audit, [
        {
            "source": "incoming/photo.jpg",
            "destination": str(sorted_root / "2025_04_05-Birds" / "photo.jpg"),
            "dry_run": False,
            "operation_status": "completed",
            "date": "2025-04-05T10:00:00",
            "date_source": "exif:DateTimeOriginal",
            "category": "Birds",
            "preferred_category": "Songbird",
            "confidence": 0.88,
            "description": "small bird",
            "model": "llama3.2-vision",
            "warnings": ["note"],
        }
    ])

    migrate_sorted_layout.migrate(sorted_root, audit, apply=True)

    manifest = sorted_root / "index" / "manifest.jsonl"
    entry = json.loads(manifest.read_text(encoding="utf-8").splitlines()[0])
    assert entry["metadata_source"] == "audit"
    assert entry["source_path"] == "incoming/photo.jpg"
    assert entry["confidence"] == 0.88
    assert entry["description"] == "small bird"
    assert entry["model"] == "llama3.2-vision"
    assert entry["preferred_category"] == "Songbird"
    assert entry["warnings"] == ["note"]


def test_apply_writes_partial_manifest_without_audit_match(tmp_path):
    sorted_root = tmp_path / "sorted"
    old = sorted_root / "2025_04_05-Birds"
    old.mkdir(parents=True)
    (old / "photo.jpg").write_bytes(b"photo")

    migrate_sorted_layout.migrate(sorted_root, tmp_path / "missing.jsonl", apply=True)

    entry = json.loads((sorted_root / "index" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert entry["metadata_source"] == "filesystem"
    assert entry["migration_source_path"] == "2025_04_05-Birds/photo.jpg"
    assert entry["destination_path"] == "by-date/2025/2025-04-05/Birds/photo.jpg"
    assert entry["category_symlink_path"] == "by-category/Birds/2025/2025-04-05/photo.jpg"


def test_duplicate_destination_appends_counter(tmp_path):
    sorted_root = tmp_path / "sorted"
    old = sorted_root / "2025_04_05-Birds"
    old.mkdir(parents=True)
    (old / "photo.jpg").write_bytes(b"new")
    existing = sorted_root / "by-date" / "2025" / "2025-04-05" / "Birds"
    existing.mkdir(parents=True)
    (existing / "photo.jpg").write_bytes(b"existing")

    migrate_sorted_layout.migrate(sorted_root, tmp_path / "missing.jsonl", apply=True)

    assert (existing / "photo-1.jpg").read_bytes() == b"new"


def test_ignores_new_layout_non_matching_and_ds_store(tmp_path):
    sorted_root = tmp_path / "sorted"
    (sorted_root / "by-date").mkdir(parents=True)
    (sorted_root / "by-category").mkdir()
    (sorted_root / "index").mkdir()
    (sorted_root / "random").mkdir()
    old = sorted_root / "2025_04_05-Birds"
    old.mkdir()
    (old / ".DS_Store").write_bytes(b"ignore")
    (old / "photo.jpg").write_bytes(b"photo")
    (sorted_root / ".DS_Store").write_bytes(b"ignore")

    files = migrate_sorted_layout.discover_old_layout_files(sorted_root)

    assert [file.old_relative_path for file in files] == [Path("2025_04_05-Birds/photo.jpg")]


def test_audit_lookup_prefers_latest_valid_entry_and_ignores_dry_run(tmp_path):
    sorted_root = tmp_path / "sorted"
    audit = tmp_path / "audit.jsonl"
    destination = "sorted/2025_04_05-Birds/photo.jpg"
    write_audit(audit, [
        {"destination": destination, "dry_run": True, "description": "dry"},
        {"destination": destination, "operation_status": "completed", "description": "old"},
        {"destination": destination, "operation_status": "completed", "description": "new"},
    ])

    lookup = migrate_sorted_layout.load_audit_lookup(audit, sorted_root)

    assert lookup["2025_04_05-Birds/photo.jpg"]["description"] == "new"
