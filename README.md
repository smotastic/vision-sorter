# Vision Sort

![Vision Sort logo](logo.png)

Vision Sort classifies photos with an Ollama-compatible vision model and sorts them into a date-first photo library.

It copies files by default, can move files when requested, writes a durable JSONL manifest for stored images, writes a separate JSONL audit log, and records the model's unrestricted `preferred_category` so the taxonomy can improve over time.

## Requirements

- Python 3.11+
- An Ollama-compatible vision endpoint, defaulting to `http://localhost:11434`
- A vision model such as `llama3.2-vision`

Install Python dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Classify and copy images from `incoming/` to `sorted/`:

```bash
./vision-sort incoming sorted
```

Preview without copying or moving files:

```bash
./vision-sort incoming sorted --dry-run
```

Move instead of copy, which is destructive:

```bash
./vision-sort incoming sorted --move
```

Override the model:

```bash
./vision-sort incoming sorted --model llama3.2-vision
```

Vision Sort skips source files already recorded in `sorted/index/manifest.jsonl` by default. The manifest is self-repairing: if a recorded canonical destination file is missing, Vision Sort removes that stale manifest entry and processes the source again. Reprocess everything with:

```bash
./vision-sort incoming sorted --no-skip-processed
```

Use a custom config:

```bash
./vision-sort incoming sorted --config config.json
```

## Output layout

Files are stored canonically under `by-date/`, with a generated category-first symlink index under `by-category/`:

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

Dates prefer EXIF metadata and fall back to file modification time by default. The default folder date format is ISO-style `YYYY-MM-DD`.

## Configuration

Defaults live in `src/vision_sort/config.py`. `config.example.json` shows the JSON format. If `config.json` exists in the working directory, Vision Sort deep-merges it over the defaults.

Important sections:

- `ollama`: host, model, timeout, generation options, image normalization settings
- `classification`: fallback category, minimum confidence, allowed categories
- `files`: copy/move behavior, recursion, supported extensions, duplicate strategy
- `dates`: EXIF and folder date behavior; defaults to `%Y-%m-%d` for ISO date folders
- `layout`: generated root names, category symlink behavior, and manifest path
- `audit`: enables the audit log and sets its path

## Manifest vs audit log

`sorted/index/manifest.jsonl` is the durable catalog of successfully stored library images. It records canonical `by-date` paths, category symlink paths, date/category metadata, model metadata, and the copy/move action. Vision Sort uses this index to skip source files it has already processed on later runs, and repairs it by removing entries whose canonical destination files no longer exist. It is suitable for future import into SQLite or search tooling, but Vision Sort does not create a database today.

`vision-sort-audit.jsonl` is a run/debug log. It may include dry-runs, failed operations, warnings, and raw Ollama responses. Use it to inspect classifier behavior and improve categories, not as the canonical library catalog.

## One-time migration from the old layout

If you already have old folders such as `sorted/2025_04_05-Birds/`, use the migration script to copy them into the new layout. The migration is copy-only and never deletes old folders.

Preview first:

```bash
python3 scripts/migrate_sorted_layout.py sorted --audit vision-sort-audit.jsonl --dry-run
```

Apply only after the dry-run looks correct:

```bash
python3 scripts/migrate_sorted_layout.py sorted --audit vision-sort-audit.jsonl --apply
```

The script enriches manifest entries from matching audit log records when possible.

## Audit log and category improvement

When audit logging is enabled, Vision Sort appends records to `vision-sort-audit.jsonl`. Each record includes the chosen category, model confidence, description, raw Ollama response, and `preferred_category`.

A local agent skill can analyze this audit history and propose new categories:

```bash
python3 .agents/skills/vision-sort-audit-categories/scripts/audit_categories.py propose \
  --audit vision-sort-audit.jsonl
```

After reviewing and confirming exact category names, apply them to the defaults:

```bash
python3 .agents/skills/vision-sort-audit-categories/scripts/audit_categories.py apply \
  --categories "Squirrels,Swans"
```

This updates both `src/vision_sort/config.py` and `config.example.json` while keeping `Unclear-Needs-Review` last.

## Development

Run tests:

```bash
PYTHONPATH=src pytest
```

Run the package directly:

```bash
PYTHONPATH=src python3 -m vision_sort incoming sorted --dry-run
```
