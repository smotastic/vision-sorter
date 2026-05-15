#!/usr/bin/env python3
"""Analyze Vision Sort audit logs and update default categories after approval."""
from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

FALLBACK_CATEGORY = "Unclear-Needs-Review"
DEFAULT_CONFIG_PATH = Path("src/vision_sort/config.py")
EXAMPLE_CONFIG_PATH = Path("config.example.json")


def slug_title(name: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", name.strip())
    return "-".join(part[:1].upper() + part[1:] for part in parts if part)


def pluralize(name: str) -> str:
    # Conservative pluralization for simple species/category labels.
    if "-" in name:
        return name
    lower = name.lower()
    if lower.endswith(("s", "x", "ch", "sh")):
        return name + "es"
    if lower.endswith("y") and len(name) > 1 and lower[-2] not in "aeiou":
        return name[:-1] + "ies"
    return name + "s"


def normalize_candidate(raw: str, *, plural: bool = True) -> str | None:
    if not raw or not raw.strip():
        return None
    value = slug_title(raw)
    if not value:
        return None
    return pluralize(value) if plural else value


def read_audit(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if isinstance(record, dict):
                rows.append(record)
    return rows


def read_categories_from_example(path: Path) -> list[str] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    categories = data.get("classification", {}).get("categories")
    return categories if isinstance(categories, list) else None


def read_categories_from_config(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "DEFAULT_CATEGORIES":
                    value = ast.literal_eval(node.value)
                    if isinstance(value, list):
                        return [str(item) for item in value]
    raise SystemExit(f"Could not find DEFAULT_CATEGORIES in {path}")


def existing_categories() -> list[str]:
    return read_categories_from_example(EXAMPLE_CONFIG_PATH) or read_categories_from_config(DEFAULT_CONFIG_PATH)


def propose(args: argparse.Namespace) -> None:
    audit_path = Path(args.audit)
    rows = read_audit(audit_path)
    existing = set(existing_categories())
    candidate_counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    broad_counts: Counter[str] = Counter()
    fallback_descriptions: list[str] = []

    for row in rows:
        broad = str(row.get("category") or "")
        if broad:
            broad_counts[broad] += 1
        preferred = str(row.get("preferred_category") or "")
        candidate = normalize_candidate(preferred, plural=not args.singular)
        if candidate and candidate not in existing:
            candidate_counts[candidate] += 1
            if len(examples[candidate]) < 3:
                source = row.get("source") or row.get("destination") or "unknown source"
                description = row.get("description") or ""
                examples[candidate].append(f"{source}: {description}".strip())
        if broad == FALLBACK_CATEGORY and row.get("description"):
            fallback_descriptions.append(str(row["description"]))

    min_count = args.min_count
    candidates = [
        {
            "category": name,
            "count": count,
            "examples": examples[name],
        }
        for name, count in candidate_counts.most_common()
        if count >= min_count
    ]

    result = {
        "audit_path": str(audit_path),
        "records": len(rows),
        "existing_category_count": len(existing),
        "current_category_counts": dict(broad_counts.most_common()),
        "proposed_categories": candidates,
        "fallback_descriptions_sample": fallback_descriptions[: args.fallback_examples],
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def format_python_list(items: list[str]) -> str:
    body = "\n".join(f'    "{item}",' for item in items)
    return f"DEFAULT_CATEGORIES = [\n{body}\n]"


def update_config_py(path: Path, categories: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"DEFAULT_CATEGORIES = \[\n(?:    .*?\n)*\]", re.MULTILINE)
    replacement = format_python_list(categories)
    new_text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise SystemExit(f"Could not replace DEFAULT_CATEGORIES in {path}")
    path.write_text(new_text, encoding="utf-8")


def update_example_json(path: Path, categories: list[str]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("classification", {})["categories"] = categories
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def merge_categories(existing: list[str], additions: list[str]) -> list[str]:
    clean_additions: list[str] = []
    seen = set(existing)
    for raw in additions:
        name = slug_title(raw)
        if not name:
            continue
        if name in seen:
            continue
        clean_additions.append(name)
        seen.add(name)

    without_fallback = [c for c in existing if c != FALLBACK_CATEGORY]
    if FALLBACK_CATEGORY in existing:
        return without_fallback + clean_additions + [FALLBACK_CATEGORY]
    return existing + clean_additions


def apply(args: argparse.Namespace) -> None:
    additions = [item.strip() for item in args.categories.split(",") if item.strip()]
    if not additions:
        raise SystemExit("No categories supplied. Use --categories 'Name,Another-Name'.")
    current = read_categories_from_config(DEFAULT_CONFIG_PATH)
    updated = merge_categories(current, additions)
    if updated == current:
        print("No new categories to add.")
        return
    update_config_py(DEFAULT_CONFIG_PATH, updated)
    if EXAMPLE_CONFIG_PATH.exists():
        update_example_json(EXAMPLE_CONFIG_PATH, updated)
    added = [c for c in updated if c not in current]
    print(json.dumps({"added": added, "category_count": len(updated)}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("propose", help="Analyze audit JSONL and print category candidates")
    p.add_argument("--audit", default="vision-sort-audit.jsonl", help="Path to audit JSONL")
    p.add_argument("--min-count", type=int, default=1, help="Minimum candidate frequency")
    p.add_argument("--singular", action="store_true", help="Keep preferred_category labels singular")
    p.add_argument("--fallback-examples", type=int, default=10, help="Number of unclear descriptions to include")
    p.set_defaults(func=propose)

    a = sub.add_parser("apply", help="Apply confirmed categories to default config files")
    a.add_argument("--categories", required=True, help="Comma-separated confirmed categories")
    a.set_defaults(func=apply)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
