---
date: 2026-05-15T14:14:58.351809+00:00
git_commit: ""
branch: ""
topic: "Image categorization script using Ollama with timestamped category folders"
tags: [research, codebase, image-classification, ollama]
status: complete
---

# Research: Image categorization script using Ollama with timestamped category folders

## Research Question
The user wants to write a script that categorizes pictures from a source folder into category folders named `{YYYY_MM_DD-Category}`. Categorization should use Ollama with a configurable model defaulting to `qwen3.6`. The user mostly takes nature pictures, including many animals and nature scenes, and asked what categories would be good and whether categories should be predefined or left to the model.

## Summary
The repository currently contains no project files, source files, configuration, or existing implementation. It is not initialized as a Git repository. There is therefore no existing script, package layout, CLI convention, dependency file, test setup, or project-specific architecture to document.

For the requested future script, the main design decision is category control. For nature-heavy photo organization, a predefined category vocabulary with an `Other`/`NeedsReview` fallback is the most predictable approach. Letting the model invent categories freely will likely produce inconsistent folder names such as `Bird`, `Birds`, `Small birds`, `Wild birds`, `Songbird`, or overly specific categories that fragment the archive.

A practical category set should be specific enough to separate common nature subjects, but not so specific that every species or visual variation becomes its own folder.

## Detailed Findings

### Repository State
- Current working directory: `/Users/nils/Development/projects/vision-sort`
- `find . -maxdepth 3 -print` returned only `.` before this research document was created.
- `git status` reported: `fatal: not a git repository (or any of the parent directories): .git`
- No existing files define runtime language, package manager, CLI framework, Ollama integration, image handling, or destination-folder behavior.

### Existing File Layout
After this research, the only created project content is this research document:
- `docs/agents/research/2026-05-15-image-categorization-script.md`

### Candidate Nature-Oriented Categories
A balanced initial category vocabulary for nature photography could be:

Animal categories:
- `Birds`
- `Mammals`
- `Insects`
- `Butterflies-Moths`
- `Reptiles-Amphibians`
- `Fish-Aquatic-Life`
- `Pets-Domestic-Animals`
- `Animal-Tracks-Signs`

Plant and fungi categories:
- `Flowers`
- `Trees-Forests`
- `Leaves-Foliage`
- `Mushrooms-Fungi`
- `Moss-Lichen`
- `Plants-Other`

Landscape and environment categories:
- `Mountains-Rocks`
- `Water-Rivers-Lakes`
- `Seascapes-Coast`
- `Fields-Meadows`
- `Sky-Clouds-Weather`
- `Sunrise-Sunset`
- `Snow-Ice`
- `Macro-Nature-Details`

Human/contextual categories:
- `People-Outdoors`
- `Buildings-Structures`
- `Trails-Paths`
- `Vehicles-Equipment`

Fallback/quality categories:
- `Unclear-Needs-Review`
- `Other-Nature`

This list favors visual subjects that a vision-language model can usually identify from an image without requiring exact species-level knowledge.

### Predefined Categories vs Model-Decided Categories
Predefined categories:
- Produce stable folder names.
- Avoid duplicate near-synonyms.
- Make reruns idempotent and easier to audit.
- Make it easier to validate model output.
- Work well with a fallback category for ambiguous images.

Model-decided categories:
- Can capture unexpected subjects.
- May create more descriptive categories for unusual images.
- Often creates inconsistent naming and overly granular folders.
- Requires a later normalization/merge step.

A hybrid approach is best suited to the stated use case: provide the model with a fixed allowed list, require it to choose exactly one category, and optionally ask it for a short free-text subject label or confidence score for logs/metadata. If confidence is low, route to `Unclear-Needs-Review` instead of creating a new folder.

### Folder Naming Implications
The target folder pattern is:

```text
root/{YYYY_MM_DD-Category}
```

Important details for a future implementation:
- `YYYY_MM_DD` should usually come from image EXIF capture date when available.
- If EXIF date is unavailable, file modification time can be used as fallback.
- Category folder names should be sanitized to avoid spaces and filesystem-sensitive characters.
- The model should return a category token that exactly matches one allowed category.

Example output folders:

```text
2026_05_15-Birds
2026_05_15-Flowers
2026_05_15-Water-Rivers-Lakes
2026_05_15-Unclear-Needs-Review
```

## Code References
No source code currently exists in the repository.

## Architecture Documentation
No existing architecture is present. There are no current modules, entry points, command-line interfaces, configuration files, tests, or Ollama integration code to document.

The repository is currently a blank slate for implementing a photo sorting tool.

## Open Questions
- Should the root destination be the same as the source folder or separate?
- How should duplicate destination filenames be handled?

## Follow-up Research 2026-05-15T14:17:17Z

The user clarified these implementation preferences:
- Python implementation.
- Include a simple Bash wrapper script for normal usage.
- Copy files by default.
- Support an explicit parameter for destructive move behavior.
- Recursive source-folder scan.
- JSON audit log.

### EXIF Date Handling
EXIF is relevant because folder names contain a date. For photos, the best date is usually the camera capture date stored inside image metadata, not the filesystem timestamp.

Useful EXIF fields, in preferred order:
1. `DateTimeOriginal` — when the camera originally captured the image.
2. `DateTimeDigitized` — when the image was digitized; often same as original for digital cameras.
3. `DateTime` — generic image modification timestamp from EXIF.
4. Filesystem modification time — fallback when EXIF is unavailable or unreadable.

Why EXIF is preferable:
- Copying files between devices can change filesystem timestamps.
- Downloads, exports, and cloud sync can alter modified/created times.
- EXIF capture date usually preserves when the photo was actually taken.

Expected behavior for the future script:
- Try EXIF first.
- Fall back to filesystem modified time if EXIF is missing.
- Record the date source in the audit log, e.g. `exif:DateTimeOriginal` or `filesystem:mtime`.
- If EXIF parsing fails, continue processing the image and log the warning.

The folder date format remains:

```text
YYYY_MM_DD-Category
```

Example:

```text
2024_08_03-Birds
```

### Config File Shape
A JSON config file is suitable for a simple Python script because it requires no extra parser dependency.

Example `config.json`:

```json
{
  "ollama": {
    "host": "http://localhost:11434",
    "model": "qwen3.6",
    "timeout_seconds": 120
  },
  "classification": {
    "fallback_category": "Unclear-Needs-Review",
    "min_confidence": 0.55,
    "categories": [
      "Birds",
      "Mammals",
      "Insects",
      "Butterflies-Moths",
      "Reptiles-Amphibians",
      "Fish-Aquatic-Life",
      "Pets-Domestic-Animals",
      "Animal-Tracks-Signs",
      "Flowers",
      "Trees-Forests",
      "Leaves-Foliage",
      "Mushrooms-Fungi",
      "Moss-Lichen",
      "Plants-Other",
      "Mountains-Rocks",
      "Water-Rivers-Lakes",
      "Seascapes-Coast",
      "Fields-Meadows",
      "Sky-Clouds-Weather",
      "Sunrise-Sunset",
      "Snow-Ice",
      "Macro-Nature-Details",
      "People-Outdoors",
      "Buildings-Structures",
      "Trails-Paths",
      "Vehicles-Equipment",
      "Other-Nature",
      "Unclear-Needs-Review"
    ]
  },
  "files": {
    "recursive": true,
    "default_action": "copy",
    "supported_extensions": [".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff"],
    "duplicate_strategy": "append-counter"
  },
  "dates": {
    "prefer_exif": true,
    "fallback_to_mtime": true,
    "folder_date_format": "%Y_%m_%d"
  },
  "audit": {
    "enabled": true,
    "path": "vision-sort-audit.jsonl"
  }
}
```

JSON Lines (`.jsonl`) is a practical audit-log format because each processed image can be appended as one JSON object without rewriting the full file.

Example audit record:

```json
{
  "timestamp": "2026-05-15T14:17:17Z",
  "source": "/photos/incoming/IMG_1234.JPG",
  "destination": "/photos/sorted/2024_08_03-Birds/IMG_1234.JPG",
  "action": "copy",
  "model": "qwen3.6",
  "category": "Birds",
  "confidence": 0.82,
  "description": "small bird perched on a branch",
  "date_taken": "2024-08-03T09:41:22",
  "date_source": "exif:DateTimeOriginal",
  "status": "success",
  "warnings": []
}
```

### Bash Wrapper Shape
The Bash wrapper can keep common usage short while delegating logic to Python.

Example usage shape:

```bash
./vision-sort ~/Pictures/incoming ~/Pictures/sorted
./vision-sort ~/Pictures/incoming ~/Pictures/sorted --move
./vision-sort ~/Pictures/incoming ~/Pictures/sorted --config config.json --model llava
```

The destructive move path should require an explicit flag such as `--move`; copy remains default.
