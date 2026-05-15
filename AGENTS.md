# Agent Instructions

## Project overview

Vision Sort is a Python CLI that uses an Ollama-compatible vision model to classify images and sort them into dated category folders.

Key files:

- `src/vision_sort/cli.py` — command-line entry point and audit writing
- `src/vision_sort/classifier.py` — Ollama request/response handling and prompt construction
- `src/vision_sort/config.py` — default config, categories, validation
- `src/vision_sort/dates.py` — EXIF/mtime date extraction
- `src/vision_sort/files.py` — image discovery and destination path building
- `src/vision_sort/images.py` — image normalization for Ollama
- `config.example.json` — example user config matching defaults
- `.agents/skills/vision-sort-audit-categories/` — local agent skill for audit-driven category proposals

## Commands

Use `python3`; this environment may not have `python` on PATH.

Run tests:

```bash
PYTHONPATH=src pytest
```

Validate default config:

```bash
PYTHONPATH=src python3 - <<'PY'
from vision_sort.config import DEFAULT_CONFIG, validate_config
validate_config(DEFAULT_CONFIG)
print('config ok')
PY
```

Run the CLI locally:

```bash
./vision-sort incoming sorted --dry-run
```

## Coding guidelines

- Keep `src/vision_sort/config.py` and `config.example.json` in sync when changing defaults.
- Keep `Unclear-Needs-Review` as the final classification category.
- Preserve deterministic, testable behavior around parsing, validation, and file paths.
- Prefer small focused functions and add/adjust tests for behavior changes.
- Do not use destructive `--move` runs unless the user explicitly asks.
- Do not edit a user's local `config.json` without asking first.

## Audit category workflow

When asked to analyze audit logs or suggest new categories, use the local skill:

```bash
python3 .agents/skills/vision-sort-audit-categories/scripts/audit_categories.py propose \
  --audit vision-sort-audit.jsonl
```

Present proposed categories with counts/examples and ask for confirmation before applying changes.

After user confirmation:

```bash
python3 .agents/skills/vision-sort-audit-categories/scripts/audit_categories.py apply \
  --categories "Category-One,Category-Two"
```

Then validate config and preferably run tests.

## Notes

- Audit logs are JSONL and may contain raw model output; treat them as generated data.
- Image inputs and sorted outputs can be large/binary; avoid unnecessary reads or commits.
- The wrapper script `./vision-sort` sets `PYTHONPATH=src` and prefers `.venv/bin/python` when present.
