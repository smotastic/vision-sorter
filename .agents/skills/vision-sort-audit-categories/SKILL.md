---
name: vision-sort-audit-categories
description: Analyzes Vision Sort audit logs to propose new classification categories and, after user confirmation, add them to the default configuration. Use when the user asks to review audit logs, suggest new categories from preferred_category values/descriptions, or update Vision Sort default categories based on audit history.
---

# Vision Sort Audit Categories

## Quick start

From the repository root:

```bash
python3 .agents/skills/vision-sort-audit-categories/scripts/audit_categories.py propose \
  --audit vision-sort-audit.jsonl
```

Show the proposed categories to the user. Do **not** modify config until the user confirms the exact category names to add.

After confirmation:

```bash
python3 .agents/skills/vision-sort-audit-categories/scripts/audit_categories.py apply \
  --categories "Swans,Squirrels"
```

This updates both:

- `src/vision_sort/config.py` (`DEFAULT_CATEGORIES`)
- `config.example.json` (`classification.categories`)

## Workflow

1. Run `propose` against the audit JSONL file.
2. Review candidates from `preferred_category`, fallback/unclear records, and repeated descriptions.
3. Filter out categories that are:
   - already present in `classification.categories`
   - too specific for the user's desired taxonomy
   - duplicates/synonyms of existing categories
   - one-off low-value observations
4. Present a short recommendation with evidence counts and examples.
5. Ask the user to confirm exact category names.
6. Only after confirmation, run `apply --categories ...`.
7. Run tests or at least import/validate config:

```bash
PYTHONPATH=src python3 - <<'PY'
from vision_sort.config import DEFAULT_CONFIG, validate_config
validate_config(DEFAULT_CONFIG)
print(DEFAULT_CONFIG['classification']['categories'])
PY
```

## Notes

- Keep `Unclear-Needs-Review` as the final category.
- Prefer Title-Case-Kebab names, e.g. `Swans`, `Squirrels`, `Urban-Wildlife`.
- When converting species from `preferred_category`, prefer plural category names unless the project taxonomy intentionally uses singular names.
- If a local `config.json` exists, ask before editing it; the default update normally targets code defaults and `config.example.json`.
