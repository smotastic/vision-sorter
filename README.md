# Vision Sort

Vision Sort classifies photos with an Ollama-compatible vision model and sorts them into dated category folders.

It copies files by default, can move files when requested, writes a JSONL audit log, and records the model's unrestricted `preferred_category` so the taxonomy can improve over time.

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

Use a custom config:

```bash
./vision-sort incoming sorted --config config.json
```

## Output layout

Files are placed under folders named with the image date and category:

```text
sorted/
  2025_04_05-Birds/
    DSC_2508.NEF
  2025_06_07-Squirrels/
    DSC_4510.jpeg
```

Dates prefer EXIF metadata and fall back to file modification time by default.

## Configuration

Defaults live in `src/vision_sort/config.py`. `config.example.json` shows the JSON format. If `config.json` exists in the working directory, Vision Sort deep-merges it over the defaults.

Important sections:

- `ollama`: host, model, timeout, generation options, image normalization settings
- `classification`: fallback category, minimum confidence, allowed categories
- `files`: copy/move behavior, recursion, supported extensions, duplicate strategy
- `dates`: EXIF and folder date behavior
- `audit`: enables the audit log and sets its path

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
