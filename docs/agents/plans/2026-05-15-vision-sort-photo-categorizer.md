---
date: 2026-05-15T14:20:53.623956+00:00
git_commit: ""
branch: ""
topic: "Vision Sort Python photo categorizer"
tags: [plan, python, ollama, image-classification, exif, cli]
status: draft
---

# Vision Sort Python Photo Categorizer Implementation Plan

## Overview

Implement a Python-based photo sorting tool that recursively scans a source folder, classifies mixed-format images with Ollama, and copies them by default into timestamped category folders under a destination root. A simple Bash wrapper will provide the main user-facing command, with an explicit `--move` flag for destructive moves.

## Current State Analysis

The repository is effectively blank. The only existing project file is the research document created for this feature:

- `docs/agents/research/2026-05-15-image-categorization-script.md`

There is no existing source tree, package metadata, tests, config file, CLI wrapper, or Ollama integration.

## Desired End State

A user can run:

```bash
./vision-sort ./incoming ./sorted
```

and the tool will recursively classify supported image files from `./incoming`, then copy them into folders such as:

```text
./sorted/2026_05_15-Birds/IMG_1234.JPG
./sorted/2026_05_15-Flowers/IMG_5678.JPG
./sorted/2026_05_15-Unclear-Needs-Review/IMG_9999.JPG
```

A user can explicitly move files instead of copying:

```bash
./vision-sort ./incoming ./sorted --move
```

A user can override config/model:

```bash
./vision-sort ./incoming ./sorted --config config.json --model llava
```

The tool writes an append-only JSONL audit log describing every processed image.

### UI Mockups

CLI usage:

```text
$ ./vision-sort ./incoming ./sorted
Vision Sort
Source:      ./incoming
Destination: ./sorted
Action:      copy
Model:       qwen3.6
Config:      ./config.json

Scanning recursively...
Found 42 supported image files.

[1/42] IMG_1234.JPG -> 2024_08_03-Birds/IMG_1234.JPG
[2/42] flower.webp -> 2024_08_03-Flowers/flower.webp
[3/42] unknown.png -> 2024_08_04-Unclear-Needs-Review/unknown.png

Done. Processed: 42, copied: 42, failed: 0
Audit log: vision-sort-audit.jsonl
```

Destructive mode should be explicit in output:

```text
$ ./vision-sort ./incoming ./sorted --move
Vision Sort
Action: move (destructive)
...
```

### Key Discoveries

- The repo currently has no source files or conventions to preserve.
- The research document specifies a hybrid classification approach: fixed category list with fallback category.
- EXIF date should be preferred over filesystem timestamps.
- Filesystem mtime is the fallback date source.
- Source scanning must be recursive.
- Mixed image formats must be supported: `.jpg`, `.jpeg`, `.png`, `.webp`, `.heic`, `.heif`, `.tif`, `.tiff`, `.bmp`, `.gif`, `.nef`.
- Duplicate destination filenames should use an appended counter, e.g. `IMG_1234-1.JPG`.
- Default config lookup should be `./config.json`, with `--config` override.

## What We're NOT Doing

- [ ] Do not implement a GUI.
- [ ] Do not implement species-level taxonomy or automatic category creation.
- [ ] Do not upload images to remote services; use local Ollama only.
- [ ] Do not require exact model confidence calibration beyond parsing/validating the model's returned confidence value.
- [ ] Do not build a database; JSONL audit logging is sufficient.
- [ ] Do not implement automatic retry queues beyond logging failures in this first version.
- [ ] Do not modify original files unless `--move` is explicitly passed.

## Implementation Approach

Build a small Python CLI module with focused components:

```text
Bash wrapper -> Python CLI -> Config loader
                         -> Image scanner
                         -> Date extractor
                         -> Image normalizer/encoder
                         -> Ollama classifier
                         -> File copier/mover
                         -> JSONL audit logger
```

The Python CLI will own all behavior. The Bash wrapper will simply locate the repository root and execute the Python module/script with passed arguments.

Classification will use a fixed category list from config. The prompt will require strict JSON output with exactly one configured category. Invalid, missing, or low-confidence categories route to the configured fallback category.

For compatibility, images sent to Ollama should be normalized to a temporary JPEG/PNG representation using Pillow. This lets the tool accept HEIC, TIFF, WebP, BMP, GIF, and other supported formats while sending a commonly supported payload to Ollama.

## Architecture and Code Reuse

No existing code can be reused. Planned third-party dependencies:

- `Pillow` for image loading, EXIF reading, conversion, and test image generation.
- `pillow-heif` for HEIC/HEIF support.
- `requests` for calling the Ollama HTTP API.
- `pytest` for tests.
- `exifread` for EXIF metadata from RAW formats such as Nikon `.NEF`.
- `rawpy` for rendering RAW formats such as Nikon `.NEF` for model classification.

Planned file tree:

```text
.
├── vision-sort                      # Bash wrapper executable
├── config.example.json              # Example/default config users can copy
├── requirements.txt                 # Runtime + test dependencies
├── README.md                        # Usage and setup instructions
├── src/
│   └── vision_sort/
│       ├── __init__.py
│       ├── __main__.py              # python -m vision_sort entry point
│       ├── audit.py                 # JSONL audit writer
│       ├── classifier.py            # Ollama request/prompt/response parsing
│       ├── cli.py                   # argparse and orchestration
│       ├── config.py                # defaults + config loading/validation
│       ├── dates.py                 # EXIF date extraction + mtime fallback
│       ├── files.py                 # recursive scan, destination paths, copy/move
│       └── images.py                # image format support and conversion
└── tests/
    ├── test_config.py
    ├── test_dates.py
    ├── test_files.py
    ├── test_classifier.py
    └── test_cli.py
```

## Phase 1: Project Skeleton, Dependencies, and Defaults

### Overview

Create the Python package layout, dependency file, default/example config, and entry points without implementing full sorting behavior yet.

### Changes Required:

#### [x] 1. Python package skeleton
**File**: `src/vision_sort/__init__.py`  
**Changes**: Add package marker and version constant.

```python
__version__ = "0.1.0"
```

#### [x] 2. Python module entry point
**File**: `src/vision_sort/__main__.py`  
**Changes**: Delegate to CLI main.

```python
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

#### [x] 3. Requirements
**File**: `requirements.txt`  
**Changes**: Add runtime/test dependencies.

```text
Pillow
pillow-heif
requests
pytest
```

#### [x] 4. Default example config
**File**: `config.example.json`  
**Changes**: Add full example config with Ollama defaults, categories, supported extensions, date behavior, and audit settings.

```json
{
  "ollama": { "host": "http://localhost:11434", "model": "qwen3.6", "timeout_seconds": 120 },
  "classification": { "fallback_category": "Unclear-Needs-Review", "min_confidence": 0.55, "categories": [] },
  "files": { "recursive": true, "default_action": "copy", "supported_extensions": [] },
  "dates": { "prefer_exif": true, "fallback_to_mtime": true, "folder_date_format": "%Y_%m_%d" },
  "audit": { "enabled": true, "path": "vision-sort-audit.jsonl" }
}
```

#### [x] 5. Config loading module
**File**: `src/vision_sort/config.py`  
**Changes**: Implement defaults, JSON loading from `./config.json` if present, override support, and config validation.

```python
def load_config(path: str | None = None) -> dict:
    ...

def validate_config(config: dict) -> None:
    ...
```

### Success Criteria:

#### Automated Verification:
- [x] Import works: `PYTHONPATH=src python3 -m vision_sort --help`
- [x] Config module imports: `PYTHONPATH=src python3 -c "from vision_sort.config import load_config; print(load_config()['ollama']['model'])"`
- [x] Tests pass for added config behavior: `PYTHONPATH=src pytest tests/test_config.py`

#### Manual Verification:
- [ ] Running `./vision-sort --help` is not required yet in this phase.

**Implementation Note**: Continue to Phase 2 after automated verification.

---

## Phase 2: CLI and Bash Wrapper

### Overview

Add the user-facing Bash command and Python argument parsing, including copy default and explicit `--move` mode.

### Changes Required:

#### [x] 1. Python CLI parser
**File**: `src/vision_sort/cli.py`  
**Changes**: Implement argparse for source, destination, config, model override, `--move`, and `--dry-run` if simple to include.

```python
def build_parser() -> argparse.ArgumentParser:
    ...

def main(argv: list[str] | None = None) -> int:
    ...
```

Arguments:
- `source`
- `destination`
- `--config`
- `--model`
- `--move`
- `--dry-run`

#### [x] 2. Bash wrapper
**File**: `vision-sort`  
**Changes**: Add executable Bash script that runs the Python module with `PYTHONPATH=src`.

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m vision_sort "$@"
```

#### [x] 3. CLI summary output
**File**: `src/vision_sort/cli.py`  
**Changes**: Print source, destination, action, model, config, and dry-run status at startup.

### Success Criteria:

#### Automated Verification:
- [x] Help works: `./vision-sort --help`
- [x] Python module help works: `PYTHONPATH=src python3 -m vision_sort --help`
- [x] CLI parser tests pass: `PYTHONPATH=src pytest tests/test_cli.py`

#### Manual Verification:
- [x] User can run `./vision-sort --help` and see source/destination plus options.
- [x] User can run `./vision-sort ./incoming ./sorted --dry-run` after creating empty folders and see a clear startup summary.

**Implementation Note**: Pause for manual confirmation after this phase because the user-facing command exists.

---

## Phase 3: Image Discovery, EXIF Dates, and Destination Paths

### Overview

Implement recursive image discovery, multi-format recognition, EXIF-preferred date extraction, mtime fallback, folder naming, and duplicate-safe paths.

### Changes Required:

#### [x] 1. Recursive image scanner
**File**: `src/vision_sort/files.py`  
**Changes**: Add supported extension matching and recursive scanning.

```python
def discover_images(source: Path, extensions: set[str], recursive: bool = True) -> list[Path]:
    ...
```

#### [x] 2. Duplicate-safe destination paths
**File**: `src/vision_sort/files.py`  
**Changes**: Build destination folder `{YYYY_MM_DD-Category}` and append counters to duplicate filenames.

```python
def build_destination_path(destination_root: Path, date_label: str, category: str, source: Path) -> Path:
    ...
```

#### [x] 3. EXIF date extraction
**File**: `src/vision_sort/dates.py`  
**Changes**: Prefer EXIF fields in order, then fallback to mtime.

```python
def get_image_date(path: Path, config: dict) -> tuple[datetime, str, list[str]]:
    ...
```

Preferred fields:
- `DateTimeOriginal`
- `DateTimeDigitized`
- `DateTime`
- filesystem mtime fallback

#### [x] 4. Format registration
**File**: `src/vision_sort/images.py`  
**Changes**: Register HEIF opener if available and provide basic image open helper.

```python
def register_image_plugins() -> None:
    ...
```

### Success Criteria:

#### Automated Verification:
- [x] File discovery tests pass: `PYTHONPATH=src pytest tests/test_files.py`
- [x] EXIF/mtime date tests pass: `PYTHONPATH=src pytest tests/test_dates.py`
- [x] Full current test suite passes: `PYTHONPATH=src pytest`

#### Manual Verification:
- [x] With sample folders containing nested mixed extensions, `./vision-sort ./incoming ./sorted --dry-run` reports all supported image files.
- [x] Dry-run output shows destination folders using EXIF date where present and mtime where EXIF is absent.

**Implementation Note**: Pause for manual confirmation after this phase because recursive scan/date behavior is visible.

---

## Phase 4: Ollama Classification and Image Normalization

### Overview

Implement image conversion/encoding for Ollama, prompt construction, HTTP calls, strict JSON parsing, category validation, and fallback handling.

### Changes Required:

#### [x] 1. Image normalization/encoding
**File**: `src/vision_sort/images.py`  
**Changes**: Convert any supported image into a base64-encoded JPEG or PNG payload suitable for Ollama.

```python
def image_to_ollama_base64(path: Path) -> tuple[str, list[str]]:
    ...
```

Notes:
- Convert RGBA/transparency images safely.
- Use first frame for animated GIF/WebP.
- Preserve original source file for final copy/move.

#### [x] 2. Prompt builder
**File**: `src/vision_sort/classifier.py`  
**Changes**: Build a prompt requiring one category from config and strict JSON output.

```python
def build_prompt(categories: list[str], fallback_category: str) -> str:
    ...
```

Expected model response:

```json
{
  "category": "Birds",
  "confidence": 0.82,
  "description": "small bird perched on a branch"
}
```

#### [x] 3. Ollama HTTP client
**File**: `src/vision_sort/classifier.py`  
**Changes**: Call Ollama local API using configured host, model, timeout, prompt, and image payload.

```python
def classify_image(path: Path, config: dict, model_override: str | None = None) -> ClassificationResult:
    ...
```

#### [x] 4. Response parsing and validation
**File**: `src/vision_sort/classifier.py`  
**Changes**: Parse JSON from model response; validate category and confidence; fallback on invalid or low confidence.

```python
@dataclass
class ClassificationResult:
    category: str
    confidence: float | None
    description: str
    model: str
    warnings: list[str]
```

### Success Criteria:

#### Automated Verification:
- [x] Prompt includes all configured categories: `PYTHONPATH=src pytest tests/test_classifier.py`
- [x] Invalid JSON routes to fallback category in tests.
- [x] Unknown category routes to fallback category in tests.
- [x] Low confidence routes to fallback category in tests.
- [x] Full current test suite passes: `PYTHONPATH=src pytest`

#### Manual Verification:
- [ ] With Ollama running and model available, `./vision-sort ./incoming ./sorted --dry-run` classifies at least one real image and prints the chosen category.
- [ ] If Ollama is unavailable, the command logs a clear failure instead of crashing obscurely.

**Implementation Note**: Pause for manual confirmation after this phase because external Ollama behavior is involved.

---

## Phase 5: Copy/Move Execution and JSONL Audit Log

### Overview

Wire scanner, date extraction, classification, destination building, copy/move operation, and JSONL audit logging into the CLI orchestration.

### Changes Required:

#### [ ] 1. Copy/move operations
**File**: `src/vision_sort/files.py`  
**Changes**: Implement safe copy by default and explicit move behavior.

```python
def transfer_file(source: Path, destination: Path, action: str, dry_run: bool = False) -> None:
    ...
```

Requirements:
- Create destination directories as needed.
- Preserve metadata on copy using `shutil.copy2`.
- Use `shutil.move` for move.
- Never move unless CLI action is explicitly `move`.

#### [ ] 2. JSONL audit writer
**File**: `src/vision_sort/audit.py`  
**Changes**: Append one JSON object per processed image.

```python
class AuditLogger:
    def write(self, record: dict) -> None:
        ...
```

Record fields:
- `timestamp`
- `source`
- `destination`
- `action`
- `model`
- `category`
- `confidence`
- `description`
- `date_taken`
- `date_source`
- `status`
- `warnings`
- `error`

#### [ ] 3. CLI orchestration
**File**: `src/vision_sort/cli.py`  
**Changes**: Process discovered images end-to-end, print progress, write audit entries for success and failure.

```python
def process_images(...):
    ...
```

#### [ ] 4. Dry-run behavior
**File**: `src/vision_sort/cli.py`  
**Changes**: Dry-run should classify and compute destinations but not copy/move files. Audit records should mark `dry_run: true` if written.

### Success Criteria:

#### Automated Verification:
- [ ] Copy operation test passes.
- [ ] Move operation test passes using temp directories.
- [ ] Duplicate destination path test passes.
- [ ] JSONL audit writer test passes.
- [ ] CLI integration test with mocked classifier passes.
- [ ] Full current test suite passes: `PYTHONPATH=src pytest`

#### Manual Verification:
- [ ] Running `./vision-sort ./incoming ./sorted --dry-run` does not create copied/moved image files.
- [ ] Running `./vision-sort ./incoming ./sorted` copies files into expected date-category folders.
- [ ] Running `./vision-sort ./incoming ./sorted --move` moves files and removes originals from source.
- [ ] JSONL audit log contains one valid JSON object per processed file.

**Implementation Note**: Pause for manual confirmation after this phase because destructive `--move` behavior is included.

---

## Phase 6: Documentation and Final Verification

### Overview

Add README usage instructions, setup steps, config documentation, and final end-to-end verification.

### Changes Required:

#### [ ] 1. README
**File**: `README.md`  
**Changes**: Document install, Ollama setup, wrapper usage, config file, supported formats, EXIF behavior, copy/move behavior, and audit log format.

#### [ ] 2. Final config example polish
**File**: `config.example.json`  
**Changes**: Ensure categories and supported extensions are complete and match README.

#### [ ] 3. Executable permissions note
**File**: `README.md`  
**Changes**: Include `chmod +x vision-sort` if needed.

### Success Criteria:

#### Automated Verification:
- [ ] Full test suite passes: `PYTHONPATH=src pytest`
- [ ] CLI help works: `./vision-sort --help`
- [ ] Python module help works: `PYTHONPATH=src python3 -m vision_sort --help`

#### Manual Verification:
- [ ] User can follow README setup from a clean checkout.
- [ ] User can copy `config.example.json` to `config.json` and run the tool.
- [ ] User can sort a small mixed-format folder into expected destination folders.
- [ ] User can inspect `vision-sort-audit.jsonl` and see source, destination, category, date source, status, and warnings.

**Implementation Note**: Final phase requires manual acceptance of real-world behavior.

---

## Testing Strategy

### Unit Tests:
- Config loading with no config file uses defaults.
- Config loading with `./config.json` merges/uses user settings.
- Config override path works.
- Model override changes runtime model without mutating file config.
- Recursive scanner includes supported extensions case-insensitively.
- Recursive scanner ignores unsupported files.
- Destination path creates `{YYYY_MM_DD-Category}` folders.
- Duplicate filename strategy appends `-1`, `-2`, etc.
- EXIF parser prefers `DateTimeOriginal`.
- EXIF parser falls back to `DateTimeDigitized` then `DateTime`.
- EXIF parser falls back to filesystem mtime when needed.
- Prompt builder requires strict JSON and includes configured category list.
- Classifier parser handles clean JSON.
- Classifier parser handles JSON embedded in extra text if feasible.
- Invalid category routes to fallback.
- Low confidence routes to fallback.
- JSONL audit logger writes valid JSON per line.
- Copy preserves source file.
- Move removes source file.
- Dry-run does not transfer files.

### Integration Tests:
- End-to-end CLI run with mocked classifier over temporary nested folders.
- End-to-end dry-run with mocked classifier writes expected output and no files.
- End-to-end copy creates date-category folders.
- End-to-end move removes original files.
- Failure path logs an audit record with `status: "failed"`.

### Manual Testing Steps:
1. Install requirements: `python3 -m pip install -r requirements.txt`.
2. Ensure Ollama is running locally.
3. Ensure the selected model is available in Ollama.
4. Create or choose a small mixed-format image folder with nested subfolders.
5. Run `./vision-sort ./incoming ./sorted --dry-run`.
6. Run `./vision-sort ./incoming ./sorted`.
7. Confirm copied files remain in source.
8. Confirm destination folders use EXIF date where available.
9. Confirm PNG/WebP/BMP/GIF files without EXIF use mtime fallback.
10. Confirm audit log contains valid JSONL records.
11. Test `--move` only on a disposable source folder and confirm originals are removed.

## Performance Considerations

- [ ] Process files sequentially in the first version to keep behavior simple and avoid overwhelming Ollama.
- [ ] Convert images to a reasonable size before sending to Ollama if very large files cause slow classification.
- [ ] Avoid loading all image bytes longer than needed, except for temporary model payload generation.
- [ ] Keep JSONL logging append-only for efficient incremental writes.

## Migration Notes

No migration is needed because the repository has no existing implementation or data format.

Existing user photos are not modified unless `--move` is explicitly passed.

## References

- `docs/agents/research/2026-05-15-image-categorization-script.md` - Research summary, category recommendations, EXIF discussion, config shape, and audit log shape.
