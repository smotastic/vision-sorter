#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from vision_sort.files import (  # noqa: E402
    build_by_date_destination_path,
    build_category_symlink_path,
    create_relative_symlink,
)
from vision_sort.manifest import write_manifest_entry  # noqa: E402

IGNORED_TOP_LEVEL = {"by-date", "by-category", "index", ".DS_Store"}


@dataclass
class MigrationStats:
    discovered: int = 0
    copied: int = 0
    linked: int = 0
    manifest_entries: int = 0
    skipped: int = 0
    audit_matches: int = 0
    audit_misses: int = 0
    failures: int = 0
    messages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OldLayoutFile:
    source_path: Path
    old_relative_path: Path
    date_label: str
    category: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Copy old YYYY_MM_DD-Category sorted folders into the new by-date layout.")
    parser.add_argument("sorted_root", help="Existing sorted directory")
    parser.add_argument("--audit", default="vision-sort-audit.jsonl", help="Audit JSONL path for metadata enrichment")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview planned writes without changing files")
    mode.add_argument("--apply", action="store_true", help="Actually copy files, create symlinks, and write manifest")
    return parser


def parse_old_layout_dir(path: Path) -> tuple[str, str] | None:
    name = path.name
    if name in IGNORED_TOP_LEVEL or not path.is_dir():
        return None
    if len(name) <= 11 or name[10] != "-":
        return None
    date_part = name[:10]
    try:
        parsed = datetime.strptime(date_part, "%Y_%m_%d")
    except ValueError:
        return None
    category = name[11:]
    if not category:
        return None
    return parsed.strftime("%Y-%m-%d"), category


def discover_old_layout_files(sorted_root: Path) -> list[OldLayoutFile]:
    files: list[OldLayoutFile] = []
    for folder in sorted(sorted_root.iterdir() if sorted_root.exists() else []):
        parsed = parse_old_layout_dir(folder)
        if parsed is None:
            continue
        date_label, category = parsed
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.name != ".DS_Store":
                files.append(OldLayoutFile(path, path.relative_to(sorted_root), date_label, category))
    return files


def _audit_record_is_preferred(record: dict[str, Any]) -> bool:
    if record.get("dry_run") is True:
        return False
    status = record.get("operation_status")
    return status in {None, "", "completed", "completed-with-warning"}


def _audit_keys(destination: str, sorted_root: Path) -> set[str]:
    keys = {destination}
    path = Path(destination)
    sorted_root_resolved = sorted_root.resolve()
    if path.is_absolute():
        try:
            keys.add(str(path.resolve().relative_to(sorted_root_resolved)))
        except ValueError:
            pass
    else:
        parts = path.parts
        if sorted_root.name in parts:
            index = parts.index(sorted_root.name)
            suffix = Path(*parts[index + 1 :])
            if str(suffix) != ".":
                keys.add(str(suffix))
        keys.add(str(path))
    return {key for key in keys if key and key != "."}


def load_audit_lookup(audit_path: Path, sorted_root: Path) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    if not audit_path.exists():
        return lookup
    with audit_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict) or not _audit_record_is_preferred(record):
                continue
            destination = record.get("destination")
            if not isinstance(destination, str) or not destination:
                continue
            for key in _audit_keys(destination, sorted_root):
                lookup[key] = record
    return lookup


def find_audit_record(lookup: dict[str, dict[str, Any]], old_file: OldLayoutFile, sorted_root: Path) -> dict[str, Any] | None:
    candidates = [str(old_file.old_relative_path), str(old_file.source_path), str(old_file.source_path.resolve())]
    try:
        candidates.append(str(old_file.source_path.resolve().relative_to(sorted_root.resolve())))
    except ValueError:
        pass
    for key in candidates:
        if key in lookup:
            return lookup[key]
    return None


def build_migration_manifest_entry(
    *,
    old_file: OldLayoutFile,
    destination: Path,
    symlink_path: Path,
    sorted_root: Path,
    audit_record: dict[str, Any] | None,
    migrated_at: datetime | None = None,
) -> dict[str, Any]:
    timestamp = migrated_at or datetime.now(timezone.utc)
    destination_relative = destination.relative_to(sorted_root)
    symlink_relative = symlink_path.relative_to(sorted_root)
    image_date = datetime.strptime(old_file.date_label, "%Y-%m-%d")
    entry: dict[str, Any] = {
        "source_path": str(audit_record.get("source", "")) if audit_record else "",
        "destination_path": str(destination_relative),
        "category_symlink_path": str(symlink_relative),
        "date": str(audit_record.get("date")) if audit_record and audit_record.get("date") else image_date.isoformat(),
        "date_label": old_file.date_label,
        "date_source": str(audit_record.get("date_source", "folder")) if audit_record else "folder",
        "category": str(audit_record.get("category", old_file.category)) if audit_record else old_file.category,
        "preferred_category": str(audit_record.get("preferred_category", "")) if audit_record else "",
        "confidence": audit_record.get("confidence") if audit_record else None,
        "description": str(audit_record.get("description", "")) if audit_record else "",
        "model": str(audit_record.get("model", "")) if audit_record else "",
        "action": "migration-copy",
        "metadata_source": "audit" if audit_record else "filesystem",
        "migration_source_path": str(old_file.old_relative_path),
        "migrated_at": timestamp.isoformat(),
        "manifest_schema_version": 1,
    }
    if audit_record and audit_record.get("warnings") is not None:
        entry["warnings"] = audit_record["warnings"]
    return entry


def migrate(sorted_root: Path, audit_path: Path, *, apply: bool = False) -> MigrationStats:
    stats = MigrationStats()
    files = discover_old_layout_files(sorted_root)
    stats.discovered = len(files)
    lookup = load_audit_lookup(audit_path, sorted_root)
    manifest_path = sorted_root / "index" / "manifest.jsonl"

    for old_file in files:
        audit_record = find_audit_record(lookup, old_file, sorted_root)
        if audit_record:
            stats.audit_matches += 1
        else:
            stats.audit_misses += 1

        try:
            destination = build_by_date_destination_path(sorted_root, old_file.date_label, old_file.category, old_file.source_path)
            symlink_path = build_category_symlink_path(sorted_root, destination, old_file.date_label, old_file.category)
            stats.messages.append(f"{old_file.old_relative_path} -> {destination.relative_to(sorted_root)}")
            if apply:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old_file.source_path, destination)
                create_relative_symlink(symlink_path, destination)
                entry = build_migration_manifest_entry(
                    old_file=old_file,
                    destination=destination,
                    symlink_path=symlink_path,
                    sorted_root=sorted_root,
                    audit_record=audit_record,
                )
                write_manifest_entry(manifest_path, entry)
            stats.copied += 1
            stats.linked += 1
            stats.manifest_entries += 1
        except Exception as exc:
            stats.failures += 1
            stats.messages.append(f"FAILED {old_file.old_relative_path}: {exc}")
    return stats


def print_summary(stats: MigrationStats, *, apply: bool) -> None:
    planned = "" if apply else " planned"
    for message in stats.messages:
        print(message)
    print()
    print("Migration summary")
    print(f"Discovered: {stats.discovered}")
    print(f"Copied{planned}: {stats.copied}")
    print(f"Linked{planned}: {stats.linked}")
    print(f"Manifest entries{planned}: {stats.manifest_entries}")
    print(f"Skipped: {stats.skipped}")
    print(f"Audit matches: {stats.audit_matches}")
    print(f"Audit misses: {stats.audit_misses}")
    print(f"Failures: {stats.failures}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    apply = bool(args.apply)
    if not args.apply and not args.dry_run:
        print("No mode provided; defaulting to dry-run. Pass --apply to write changes.")
    if not apply:
        print("Dry run: no files, symlinks, or manifest entries will be written.")

    sorted_root = Path(args.sorted_root)
    audit_path = Path(args.audit)
    stats = migrate(sorted_root, audit_path, apply=apply)
    print_summary(stats, apply=apply)
    return 1 if stats.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
