---
date: 2026-05-16T14:05:28.218836+00:00
git_commit: a6a5338ecbc6010622a9a5b26f6f5cf199e705ba
branch: master
topic: "By-Date Layout, Category Symlinks, and Manifest Index"
tags: [plan, layout, manifest, migration, cli]
status: draft
---

# By-Date Layout, Category Symlinks, and Manifest Index Implementation Plan

## Overview

Change Vision Sort's default library layout from flat `DATE-Category/` folders to a date-first canonical structure, add a generated category-first symlink index, and maintain a durable `index/manifest.jsonl` catalog. Provide a one-time standalone migration script that copies the existing `sorted/YYYY_MM_DD-Category/` library into the new structure, enriches manifest entries from `vision-sort-audit.jsonl` when possible, and never deletes the old layout.

## Current State Analysis

Vision Sort currently treats the destination filesystem as both storage and lightweight index. It writes each classified image to a folder named with the date and category combined, for example `sorted/2025_04_05-Birds/DSC_2508.NEF`. This makes it easy to inspect one category/date bucket, but hard to browse all photos from a date across categories or all photos from a category across dates.

Key current implementation points:

- Destination path construction is centralized in `src/vision_sort/files.py:24-38`, where `build_destination_path()` currently creates `destination_root / f"{date_label}-{category}" / source.name` and appends `-N` for duplicate filenames.
- CLI sorting flow is in `src/vision_sort/cli.py:117-145`: get image date, classify, build destination path, then copy/move the file.
- Audit logging is in `src/vision_sort/cli.py:147-164` and appends one JSONL record per processed image.
- Defaults and validation live in `src/vision_sort/config.py:55-88` and `src/vision_sort/config.py:115-179`.
- `config.example.json` mirrors config defaults and must stay in sync with `src/vision_sort/config.py`.
- `README.md` documents the old `DATE-Category/` output layout.
- Existing tests cover discovery/path building in `tests/test_files.py`, CLI copy/audit behavior in `tests/test_cli.py`, and config validation in `tests/test_config.py`.
- The existing `vision-sort-audit.jsonl` contains enough metadata to enrich many migrated manifest entries, including old destination, source, date, category, confidence, description, model, preferred category, raw Ollama response, and warnings.

## Desired End State

Newly sorted images use this default structure:

```text
sorted/
  by-date/
    2025/
      2025-04-05/
        Birds/
          DSC_2508.NEF
  by-category/
    Birds/
      2025/
        2025-04-05/
          DSC_2508.NEF -> ../../../../by-date/2025/2025-04-05/Birds/DSC_2508.NEF
  index/
    manifest.jsonl
```

The `by-date` tree is the canonical storage location. The `by-category` tree is a generated symlink index for browsing categories in Finder or Terminal. The manifest is a durable JSONL catalog of successfully stored images. Audit logs remain separate run/debug logs.

### CLI Output Mockup

Current sort output conceptually shows old relative destinations:

```text
[1/3] DSC_2508.NEF -> 2025_04_05-Birds/DSC_2508.NEF (Birds, exif:DateTimeOriginal)
```

New sort output should show the canonical date-first destination:

```text
[1/3] DSC_2508.NEF -> by-date/2025/2025-04-05/Birds/DSC_2508.NEF (Birds, exif:DateTimeOriginal)
  category symlink: by-category/Birds/2025/2025-04-05/DSC_2508.NEF
```

Dry-run output should preview the same canonical destination and planned symlink, without copying, moving, linking, or appending to `index/manifest.jsonl`.

### Key Discoveries:

- Destination layout can be changed cleanly by replacing/extending `build_destination_path()` in `src/vision_sort/files.py:24-38`.
- CLI operation success is the correct point to create symlinks and append manifest entries, because failed operations should not enter the durable catalog (`src/vision_sort/cli.py:133-145`).
- Audit remains useful and should not be repurposed as manifest because it may include dry-runs, failures, raw model output, and run-specific debug information (`src/vision_sort/cli.py:147-164`).
- Existing audit entries can be matched to existing sorted files by their old `destination` field.
- macOS supports symlinks natively, which is sufficient for this project constraint.
- Existing real library files under `sorted/` include duplicate names across categories/dates and at least some old duplicate-counter filenames, so duplicate-safe allocation must remain deterministic.

## What We're NOT Doing

- [ ] Do not introduce SQLite or any database-backed search index.
- [ ] Do not build a local search UI or search engine.
- [ ] Do not delete existing old-layout folders during migration.
- [ ] Do not edit the user's local `config.json` automatically.
- [ ] Do not change the classification taxonomy except as required by existing tests/config sync.
- [ ] Do not use destructive `--move` migration behavior; migration copies only.
- [ ] Do not make Windows symlink compatibility a goal; current target is macOS.

## Implementation Approach

Implement reusable filesystem/index helpers first, then update the normal CLI flow to use them, then add the one-time migration script. The helpers should be deterministic and easy to unit test. The CLI should append manifest entries only for successful non-dry-run operations. The migration script should be conservative: dry-run by default, require `--apply` for writes, copy files into the new structure, create symlinks, and write manifest entries enriched from audit when possible.

The default date folder format should change to ISO dates (`YYYY-MM-DD`). Since current config uses `dates.folder_date_format`, set the default to `%Y-%m-%d` and update documentation/example config. The year folder should be derived from the rendered date label's first four characters after validating the date label has an ISO-style year prefix.

## Architecture and Code Reuse

Proposed helper split:

```text
src/vision_sort/
  files.py          # discovery, category sanitization, layout path builders, duplicate path allocation, symlink creation
  manifest.py       # JSONL manifest entry construction/writing helpers
  cli.py            # orchestration: classify, copy/move, link, manifest, audit
  config.py         # default layout/index config and validation
scripts/
  migrate_sorted_layout.py  # one-time old-layout -> new-layout copy/link/manifest migration
```

High-level data flow for normal sorting:

```text
incoming image
  -> get_image_date()
  -> classify_image()
  -> build_by_date_destination_path()
  -> copy2()/move()
  -> create_category_symlink()
  -> append_manifest_entry()
  -> append_audit_entry()
```

High-level data flow for migration:

```text
old sorted/YYYY_MM_DD-Category/file
  -> parse old folder date/category
  -> convert date to YYYY-MM-DD
  -> find matching audit record by old destination
  -> copy to by-date/YYYY/YYYY-MM-DD/Category/file
  -> create by-category symlink
  -> append manifest entry with audit metadata when available
```

Third-party APIs/libraries:

- Python standard library only for the new functionality: `pathlib`, `json`, `shutil`, `argparse`, `datetime`, `os` if needed for relative symlinks.
- Existing project dependencies remain unchanged.

Affected file tree:

```text
src/vision_sort/files.py        # replace old DATE-Category path builder with by-date/by-category helpers
src/vision_sort/manifest.py     # new JSONL manifest helper module
src/vision_sort/cli.py          # use new layout, symlinks, manifest writes
src/vision_sort/config.py       # add layout/index defaults and validation; ISO date default
config.example.json             # mirror default config changes
README.md                       # document new layout, manifest, migration, audit distinction
scripts/migrate_sorted_layout.py # standalone one-time migration script
tests/test_files.py             # update layout path tests and symlink helper tests
tests/test_manifest.py          # new manifest tests
tests/test_cli.py               # update copy/dry-run/audit tests for new layout and manifest behavior
tests/test_config.py            # new layout config validation tests
tests/test_migrate_sorted_layout.py # migration script tests
```

## Phase 1: Layout and Manifest Helpers

### Overview

Add deterministic path-building, duplicate handling, symlink, and manifest helpers without changing CLI behavior yet. This keeps the foundational behavior unit-testable before wiring it into sorting.

### Changes Required:

#### [x] 1. Update date layout helpers
**File**: `src/vision_sort/files.py`
**Changes**: Add helpers for canonical by-date destinations and by-category symlink paths. Keep or adapt duplicate-counter behavior.

```python
def build_by_date_destination_path(
    destination_root: Path,
    date_label: str,
    category: str,
    source: Path,
    *,
    date_root: str = "by-date",
) -> Path:
    """Build sorted/by-date/YYYY/YYYY-MM-DD/Category/name.ext with duplicate counter."""


def build_category_symlink_path(
    destination_root: Path,
    canonical_path: Path,
    date_label: str,
    category: str,
    *,
    category_index_root: str = "by-category",
) -> Path:
    """Build sorted/by-category/Category/YYYY/YYYY-MM-DD/name.ext."""


def allocate_duplicate_path(candidate: Path) -> Path:
    """Return candidate or append -N before suffix when it already exists."""


def create_relative_symlink(link_path: Path, target_path: Path) -> None:
    """Create a relative symlink, replacing only safe stale/broken symlinks if needed."""
```

Rules:

- [x] Sanitize category folder names using existing `sanitize_category()`.
- [x] Use ISO date labels like `2025-04-05`.
- [x] Derive year folder as `date_label[:4]`.
- [x] Keep duplicate behavior as append-counter before suffix.
- [x] Do not overwrite existing real files when creating symlinks.
- [x] If the symlink path already exists and points to the same canonical target, treat as success/idempotent.
- [x] If the symlink path exists as a different symlink or real file, allocate a duplicate symlink name using append-counter.

#### [x] 2. Preserve backward compatibility surface temporarily
**File**: `src/vision_sort/files.py`
**Changes**: Decide whether to keep `build_destination_path()` as a wrapper around the new by-date helper or update all imports/tests immediately.

```python
def build_destination_path(destination_root: Path, date_label: str, category: str, source: Path) -> Path:
    return build_by_date_destination_path(destination_root, date_label, category, source)
```

This reduces churn while tests and CLI are updated.

#### [x] 3. Add manifest module
**File**: `src/vision_sort/manifest.py`
**Changes**: Add JSONL append helper and manifest entry builder for sorted images.

```python
def write_manifest_entry(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def build_manifest_entry(...):
    return {
        "source_path": str(source),
        "destination_path": str(canonical_relative_path),
        "category_symlink_path": str(symlink_relative_path),
        "date": image_date.isoformat(),
        "date_label": date_label,
        "date_source": date_source,
        "category": classification.category,
        "preferred_category": classification.preferred_category,
        "confidence": classification.confidence,
        "description": classification.description,
        "model": classification.model,
        "action": action,
        "sorted_at": current_timestamp,
        "manifest_schema_version": 1,
    }
```

Manifest should not include raw Ollama response by default unless we intentionally choose to duplicate it. The raw response remains in audit.

### Success Criteria:

#### Automated Verification:
- [x] Unit tests pass for new by-date destination path construction.
- [x] Unit tests pass for category symlink path construction.
- [x] Unit tests pass for duplicate allocation on canonical paths and symlink paths.
- [x] Unit tests pass for relative symlink creation/idempotency.
- [x] Unit tests pass for manifest JSONL writing.
- [x] Full test suite passes: `PYTHONPATH=src pytest`

#### Manual Verification:
- No manual verification for this internal helper phase.

**Implementation Note**: Continue to Phase 2 after automated verification passes.

---

## Phase 2: Config Defaults and Validation

### Overview

Introduce explicit layout/index config, switch default date folders to ISO hyphen dates, and keep `config.py` and `config.example.json` synchronized.

### Changes Required:

#### [x] 1. Add layout config defaults
**File**: `src/vision_sort/config.py`
**Changes**: Add a `layout` section to `DEFAULT_CONFIG`.

```python
"layout": {
    "date_root": "by-date",
    "category_index_root": "by-category",
    "index_root": "index",
    "create_category_symlinks": True,
    "manifest_path": "index/manifest.jsonl",
},
"dates": {
    "prefer_exif": True,
    "fallback_to_mtime": True,
    "folder_date_format": "%Y-%m-%d",
},
```

#### [x] 2. Validate layout config
**File**: `src/vision_sort/config.py`
**Changes**: Include `layout` in required sections and validate all layout fields.

Rules:

- [x] `layout.date_root` is a non-empty relative path string.
- [x] `layout.category_index_root` is a non-empty relative path string.
- [x] `layout.index_root` is a non-empty relative path string.
- [x] `layout.manifest_path` is a non-empty relative path string.
- [x] `layout.create_category_symlinks` is boolean.
- [x] Reject absolute layout paths to keep all generated artifacts under destination root.
- [x] Reject `..` path segments in layout paths.

#### [x] 3. Sync example config
**File**: `config.example.json`
**Changes**: Mirror `DEFAULT_CONFIG` layout/date changes exactly.

#### [x] 4. Update config tests
**File**: `tests/test_config.py`
**Changes**: Add assertions for layout defaults and validation failures.

```python
def test_load_config_includes_layout_defaults(...): ...
def test_validate_config_rejects_absolute_layout_paths(...): ...
def test_default_date_format_is_iso_hyphenated(...): ...
```

### Success Criteria:

#### Automated Verification:
- [x] Config default validation succeeds: `PYTHONPATH=src python3 - <<'PY'\nfrom vision_sort.config import DEFAULT_CONFIG, validate_config\nvalidate_config(DEFAULT_CONFIG)\nprint('config ok')\nPY`
- [x] Config tests pass: `PYTHONPATH=src pytest tests/test_config.py`
- [x] Full test suite passes: `PYTHONPATH=src pytest`

#### Manual Verification:
- No manual verification for this internal config phase.

**Implementation Note**: Continue to Phase 3 after automated verification passes.

---

## Phase 3: CLI Sorting Uses New Layout, Symlinks, and Manifest

### Overview

Wire the new helpers into the main `vision-sort` command. New images should be stored under `by-date`, symlinked under `by-category`, and appended to `index/manifest.jsonl` only after successful copy/move operations.

### Changes Required:

#### [x] 1. Use by-date destination paths
**File**: `src/vision_sort/cli.py`
**Changes**: Replace the old destination path builder with `build_by_date_destination_path()` using layout config.

```python
date_label = image_date.strftime(config["dates"]["folder_date_format"])
dest = build_by_date_destination_path(
    destination,
    date_label,
    classification.category,
    image,
    date_root=config["layout"]["date_root"],
)
```

#### [x] 2. Preview symlink paths in output
**File**: `src/vision_sort/cli.py`
**Changes**: Build planned symlink path before operation and print it when symlink creation is enabled.

```python
symlink_path = build_category_symlink_path(...)
print(f"  category symlink: {symlink_path.relative_to(destination)}")
```

#### [x] 3. Create category symlinks after successful file operation
**File**: `src/vision_sort/cli.py`
**Changes**: After successful copy/move, create a relative symlink if enabled.

Rules:

- [x] Do not create symlinks during `--dry-run`.
- [x] Create symlink only after copy/move succeeds.
- [x] If symlink creation fails, decide whether the operation counts as failed or completed-with-warning. Recommended: count file operation as completed, write audit `operation_status` as `completed-with-warning`, do not write manifest unless the symlink outcome is represented accurately.
- [x] Add warnings to audit for symlink failures.

#### [x] 4. Append manifest after successful storage
**File**: `src/vision_sort/cli.py`
**Changes**: Write manifest entry after successful file operation and symlink creation attempt.

Rules:

- [x] Do not write manifest during `--dry-run`.
- [x] Do not write manifest when copy/move fails.
- [x] Include canonical destination path relative to destination root.
- [x] Include symlink path relative to destination root when created or planned.
- [x] Include classification/date/action metadata.
- [x] Keep audit log behavior unchanged except for paths/status/warnings reflecting new layout.

#### [x] 5. Update CLI tests
**File**: `tests/test_cli.py`
**Changes**: Update existing tests and add new ones.

Test cases:

- [x] Normal copy creates `sorted/by-date/YYYY/YYYY-MM-DD/Birds/photo.jpg`.
- [x] Normal copy creates `sorted/by-category/Birds/YYYY/YYYY-MM-DD/photo.jpg` symlink pointing relatively to the canonical file.
- [x] Normal copy appends `sorted/index/manifest.jsonl`.
- [x] Dry-run does not copy, link, or write manifest, but still writes audit if audit is enabled.
- [x] Audit destination field now references the canonical by-date destination.
- [x] Existing copy summary remains understandable.

### Success Criteria:

#### Automated Verification:
- [x] CLI tests pass: `PYTHONPATH=src pytest tests/test_cli.py`
- [x] File helper tests pass: `PYTHONPATH=src pytest tests/test_files.py`
- [x] Manifest tests pass: `PYTHONPATH=src pytest tests/test_manifest.py`
- [x] Full test suite passes: `PYTHONPATH=src pytest`

#### Manual Verification:
- [x] Running `./vision-sort incoming sorted --dry-run` previews `by-date/...` destinations and `by-category/...` symlinks without writing files.
- [x] Running a non-dry-run copy on a tiny test input creates the expected canonical file, symlink, manifest entry, and audit entry.
- [x] In Finder or Terminal on macOS, opening the `by-category` symlink resolves to the canonical `by-date` file.

**Implementation Note**: Pause for manual confirmation after this phase because it changes user-visible CLI behavior and filesystem output.

---

## Phase 4: One-Time Migration Script

### Overview

Add a standalone migration script that copies existing old-layout sorted files into the new by-date layout, creates category symlinks, and writes manifest entries. It should be safe by default: dry-run unless `--apply` is explicitly passed, copy-only, and no deletion of old folders.

### Changes Required:

#### [x] 1. Add migration script
**File**: `scripts/migrate_sorted_layout.py`
**Changes**: Implement command-line script.

Proposed usage:

```bash
python3 scripts/migrate_sorted_layout.py sorted --audit vision-sort-audit.jsonl --dry-run
python3 scripts/migrate_sorted_layout.py sorted --audit vision-sort-audit.jsonl --apply
```

Argument behavior:

- [x] Positional `sorted_root` points to the existing sorted directory.
- [x] `--audit` optional path to audit JSONL; default `vision-sort-audit.jsonl`.
- [x] `--dry-run` explicit no-write mode.
- [x] `--apply` required to copy/link/write manifest.
- [x] If neither `--dry-run` nor `--apply` is provided, default to dry-run and print that no writes will occur.
- [x] Reject using both `--dry-run` and `--apply` together.

#### [x] 2. Parse old layout folders
**File**: `scripts/migrate_sorted_layout.py`
**Changes**: Detect only old top-level folders matching `YYYY_MM_DD-Category`.

Rules:

- [x] Ignore `.DS_Store`, `by-date`, `by-category`, `index`, and non-directory files.
- [x] Parse date portion using `datetime.strptime(date_part, "%Y_%m_%d")`.
- [x] Convert date label to ISO `YYYY-MM-DD`.
- [x] Preserve category text after the first 11 characters (`YYYY_MM_DD-`) and sanitize via shared helper when building new paths.
- [x] Recursively migrate supported image files or all files? Recommended: migrate all regular files in matched old folders except hidden `.DS_Store`, because old sorted folders are already curated output and may contain supported images with varied extensions.

#### [x] 3. Load and match audit metadata
**File**: `scripts/migrate_sorted_layout.py`
**Changes**: Load audit JSONL into a lookup keyed by normalized old destination paths.

Matching strategy:

- [x] Normalize audit `destination` by resolving relative entries against the repository/current working directory enough to compare robustly.
- [x] Also support matching by path suffix relative to `sorted_root`, e.g. `2025_04_05-Birds/DSC_2508.NEF`.
- [x] Prefer non-dry-run audit entries where `operation_status` is missing, `completed`, or `completed-with-warning`.
- [x] If multiple audit entries match, prefer the latest line in the audit file.
- [x] If no audit match exists, produce a partial manifest entry with `metadata_source: "filesystem"`.
- [x] If audit match exists, produce `metadata_source: "audit"` and include recovered source/date/date_source/category/confidence/description/model/preferred_category/warnings as available.

#### [x] 4. Copy, link, and manifest write
**File**: `scripts/migrate_sorted_layout.py`
**Changes**: Use shared helpers to allocate destination paths, copy with metadata, create symlinks, and append manifest.

Rules:

- [x] Use `shutil.copy2()` to preserve file metadata.
- [x] Never delete or modify old-layout files.
- [x] Never overwrite existing by-date files.
- [x] Use duplicate-counter allocation when the target already exists.
- [x] Create relative symlinks in by-category.
- [x] Append to `sorted/index/manifest.jsonl` only in `--apply` mode.
- [x] Include `migration_source_path` relative to `sorted_root` in manifest entries.
- [x] Include `migrated_at` timestamp and `manifest_schema_version`.
- [x] Print a summary: discovered, copied/planned, linked/planned, manifest entries written/planned, skipped, audit matches, audit misses, failures.

#### [x] 5. Add migration tests
**File**: `tests/test_migrate_sorted_layout.py`
**Changes**: Add tests for script functions and/or subprocess-level behavior.

Test cases:

- [x] Dry-run reports planned copies but writes nothing.
- [x] Apply copies `2025_04_05-Birds/photo.jpg` to `by-date/2025/2025-04-05/Birds/photo.jpg`.
- [x] Apply creates category symlink.
- [x] Apply writes manifest enriched from matching audit entry.
- [x] Apply writes partial manifest when no audit match exists.
- [x] Duplicate destination appends `-1` before suffix.
- [x] Existing old-layout files remain in place after apply.
- [x] Ignores `by-date`, `by-category`, `index`, `.DS_Store`, and non-matching folders.

### Success Criteria:

#### Automated Verification:
- [x] Migration tests pass: `PYTHONPATH=src pytest tests/test_migrate_sorted_layout.py`
- [x] Full test suite passes: `PYTHONPATH=src pytest`

#### Manual Verification:
- [x] Running `python3 scripts/migrate_sorted_layout.py sorted --audit vision-sort-audit.jsonl --dry-run` prints a plausible plan and does not create `by-date`, `by-category`, or manifest entries.
- [x] Running `python3 scripts/migrate_sorted_layout.py sorted --audit vision-sort-audit.jsonl --apply` copies files into `by-date`, creates `by-category` symlinks, writes `index/manifest.jsonl`, and leaves old `YYYY_MM_DD-Category` folders untouched.
- [x] Spot-check a migrated image that exists in the audit log and verify its manifest entry includes recovered confidence/description/model metadata.
- [x] Spot-check a migrated image in Finder via `by-category` and verify it opens the canonical file.

**Implementation Note**: Pause for manual confirmation after this phase because it operates on the user's real sorted library when run with `--apply`.

---

## Phase 5: Documentation and Final Polish

### Overview

Update project documentation to reflect the new layout, explain audit vs manifest, and document the one-time migration script.

### Changes Required:

#### [x] 1. Update README layout section
**File**: `README.md`
**Changes**: Replace old output layout docs with new canonical/index layout.

```text
sorted/
  by-date/
    2025/
      2025-04-05/
        Birds/
          DSC_2508.NEF
  by-category/
    Birds/
      2025/
        2025-04-05/
          DSC_2508.NEF -> ../../../../by-date/2025/2025-04-05/Birds/DSC_2508.NEF
  index/
    manifest.jsonl
```

#### [x] 2. Document manifest vs audit
**File**: `README.md`
**Changes**: Add explanation:

- [x] `vision-sort-audit.jsonl` is a run/debug log and may include dry-runs/failures/raw model output.
- [x] `sorted/index/manifest.jsonl` is the durable catalog of successfully stored library images.
- [x] Manifest is suitable for future import into SQLite/search, but SQLite is not part of this change.

#### [x] 3. Document migration command
**File**: `README.md`
**Changes**: Add migration section with dry-run and apply examples.

```bash
python3 scripts/migrate_sorted_layout.py sorted --audit vision-sort-audit.jsonl --dry-run
python3 scripts/migrate_sorted_layout.py sorted --audit vision-sort-audit.jsonl --apply
```

Add clear warning that migration copies into the new layout and does not delete old folders.

#### [x] 4. Update config documentation
**File**: `README.md`
**Changes**: Add `layout` section to important config sections and mention ISO date default.

### Success Criteria:

#### Automated Verification:
- [x] Full test suite passes: `PYTHONPATH=src pytest`
- [x] Default config validates: `PYTHONPATH=src python3 - <<'PY'\nfrom vision_sort.config import DEFAULT_CONFIG, validate_config\nvalidate_config(DEFAULT_CONFIG)\nprint('config ok')\nPY`

#### Manual Verification:
- [x] README examples match actual dry-run output and generated filesystem layout.
- [x] Migration docs are sufficient to safely run dry-run first and apply second.

**Implementation Note**: Pause for final review after this phase.

---

## Testing Strategy

### Unit Tests:

- [ ] `sanitize_category()` still handles filesystem-sensitive category names.
- [ ] `build_by_date_destination_path()` returns `by-date/YYYY/YYYY-MM-DD/Category/file`.
- [ ] `build_by_date_destination_path()` appends duplicate counters deterministically.
- [ ] `build_category_symlink_path()` returns `by-category/Category/YYYY/YYYY-MM-DD/file`.
- [ ] Symlink helper creates relative symlink targets.
- [ ] Symlink helper is idempotent when an equivalent symlink already exists.
- [ ] Symlink helper does not overwrite real files.
- [ ] Manifest writer appends sorted JSONL records and creates parent directories.
- [ ] Config validation accepts default layout config and rejects unsafe absolute/parent paths.
- [ ] Migration parser accepts valid old folder names and ignores invalid names.
- [ ] Audit lookup matches old destination paths and prefers the latest valid audit entry.

### Integration Tests:

- [ ] CLI dry-run previews by-date destination and by-category symlink without filesystem writes except audit.
- [ ] CLI copy creates canonical file, symlink, manifest, and audit entry.
- [ ] CLI move still moves source into canonical by-date path and creates symlink/manifest.
- [ ] CLI copy failure writes audit failure and does not write manifest.
- [ ] Migration dry-run writes nothing.
- [ ] Migration apply copies old files, creates symlinks, writes manifest, and preserves old files.

### Manual Testing Steps:

1. Run `./vision-sort incoming sorted --dry-run` and confirm displayed paths use `by-date/YYYY/YYYY-MM-DD/Category/file` plus planned `by-category` symlink.
2. Run a non-dry-run copy on a small temporary input folder and confirm Finder/Terminal can browse both date-first and category-first views.
3. Run `python3 scripts/migrate_sorted_layout.py sorted --audit vision-sort-audit.jsonl --dry-run` and inspect the summary counts.
4. Run migration with `--apply` only after dry-run looks correct.
5. Spot-check several migrated files in `by-date`, their symlinks in `by-category`, and their entries in `sorted/index/manifest.jsonl`.

## Performance Considerations

- JSONL append is sufficient for multiple thousands of images; no database is needed for this scope.
- Migration loads audit metadata into memory. A ~291 KB audit file is trivial; even much larger JSONL audit files should be fine for thousands/tens of thousands of entries.
- Copying RAW files can be I/O-heavy. Migration should print progress and should not compute expensive hashes in this plan.
- Symlink creation is cheap and avoids duplicate storage for category browsing.
- Duplicate detection is path-existence based only, matching the current behavior. Content hashing/perceptual dedupe is out of scope.

## Migration Notes

- The one-time migration script is copy-only and non-destructive.
- Old folders like `sorted/2025_04_05-Birds/` remain untouched. The user will verify and delete old structure manually later.
- Audit enrichment is best-effort. Manifest entries should include `metadata_source: "audit"` when matched and `metadata_source: "filesystem"` otherwise.
- Old audit destinations may be relative (`sorted/...`) or absolute; the migration script should normalize and also compare suffixes relative to `sorted_root`.
- The new default date format is ISO hyphenated (`YYYY-MM-DD`), not backwards compatible with previous `YYYY_MM_DD`; this is intentional.
- If migration is interrupted, rerunning should avoid overwrites and allocate duplicates. After implementation, consider whether a future idempotency enhancement should detect already-migrated old source paths in the manifest, but that is not required for the first version.

## References

- Current destination path builder: `src/vision_sort/files.py:24-38`
- Current CLI copy/move flow: `src/vision_sort/cli.py:117-145`
- Current audit writer and audit fields: `src/vision_sort/cli.py:12-15`, `src/vision_sort/cli.py:147-164`
- Current config defaults: `src/vision_sort/config.py:55-88`
- Current config validation: `src/vision_sort/config.py:115-179`
- Existing file path tests: `tests/test_files.py`
- Existing CLI/audit tests: `tests/test_cli.py`
- Existing config tests: `tests/test_config.py`
- Existing README output layout docs: `README.md`
