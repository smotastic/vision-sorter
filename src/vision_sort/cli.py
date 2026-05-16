from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from .config import load_config


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_audit_entry(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
ANSI_CYAN = "\033[36m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_MAGENTA = "\033[35m"
ANSI_BLUE = "\033[34m"
ANSI_RED = "\033[31m"


def _color(text: str, code: str, *, enabled: bool) -> str:
    return f"{code}{text}{ANSI_RESET}" if enabled else text


def _format_json_value(value, *, color: bool) -> str:
    if isinstance(value, str):
        return _color(json.dumps(value, ensure_ascii=False), ANSI_GREEN, enabled=color)
    if isinstance(value, bool):
        return _color(str(value).lower(), ANSI_MAGENTA, enabled=color)
    if value is None:
        return _color("null", ANSI_DIM, enabled=color)
    if isinstance(value, (int, float)):
        return _color(str(value), ANSI_YELLOW, enabled=color)
    return _color(json.dumps(value, ensure_ascii=False, sort_keys=True), ANSI_BLUE, enabled=color)


def format_ollama_response(raw_response: str, *, color: bool | None = None) -> str:
    """Pretty-print a model JSON response one attribute per line when possible."""
    if color is None:
        color = sys.stdout.isatty()
    if not raw_response.strip():
        return ""
    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError:
        return _color(raw_response, ANSI_RED, enabled=color)
    if not isinstance(parsed, dict):
        return _color(json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True), ANSI_BLUE, enabled=color)

    lines = []
    for key in sorted(parsed):
        formatted_key = _color(str(key), ANSI_CYAN + ANSI_BOLD, enabled=color)
        lines.append(f"    {formatted_key}: {_format_json_value(parsed[key], color=color)}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vision-sort",
        description="Classify photos with Ollama and sort them into dated category folders.",
    )
    parser.add_argument("source", nargs="?", help="Source folder to scan recursively")
    parser.add_argument("destination", nargs="?", help="Destination root for sorted images")
    parser.add_argument("--config", help="Path to JSON config file (default: ./config.json if present)")
    parser.add_argument("--model", help="Override the Ollama model from config")
    parser.add_argument("--move", action="store_true", help="Move files instead of copying (destructive)")
    parser.add_argument("--dry-run", action="store_true", help="Classify and print destinations without copying or moving")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.source or not args.destination:
        # argparse should still allow --help without requiring positional args.
        parser.error("source and destination are required")

    from .classifier import classify_image
    from .dates import get_image_date
    from .files import (
        build_by_date_destination_path,
        build_category_symlink_path,
        create_relative_symlink,
        discover_images,
    )
    from .manifest import build_manifest_entry, write_manifest_entry

    config = load_config(args.config)
    model = args.model or config["ollama"]["model"]
    action = "move" if args.move else "copy"

    print("Vision Sort")
    print(f"Source:      {args.source}")
    print(f"Destination: {args.destination}")
    print(f"Action:      {action}{' (destructive)' if action == 'move' else ''}")
    print(f"Model:       {model}")
    print(f"Config:      {args.config or './config.json'}")
    print(f"Dry run:     {'yes' if args.dry_run else 'no'}")
    print()
    print("Scanning recursively..." if config["files"]["recursive"] else "Scanning...")

    source = Path(args.source)
    destination = Path(args.destination)
    images = discover_images(
        source,
        set(config["files"]["supported_extensions"]),
        recursive=config["files"]["recursive"],
    )
    print(f"Found {len(images)} supported image files.")

    date_format = config["dates"]["folder_date_format"]
    completed = 0
    failed = 0
    for index, image in enumerate(images, start=1):
        image_date, date_source, warnings = get_image_date(image, config)
        classification = classify_image(image, config, model_override=args.model)
        warnings.extend(classification.warnings)
        date_label = image_date.strftime(date_format)
        dest = build_by_date_destination_path(
            destination,
            date_label,
            classification.category,
            image,
            date_root=config["layout"]["date_root"],
        )
        symlink_path = None
        symlink_relative_path = None
        if config["layout"]["create_category_symlinks"]:
            symlink_path = build_category_symlink_path(
                destination,
                dest,
                date_label,
                classification.category,
                category_index_root=config["layout"]["category_index_root"],
            )
            symlink_relative_path = symlink_path.relative_to(destination)
        dest_relative_path = dest.relative_to(destination)
        print(f"[{index}/{len(images)}] {image.name} -> {dest_relative_path} ({classification.category}, {date_source})")
        if symlink_relative_path is not None:
            print(f"  category symlink: {symlink_relative_path}")
        if classification.preferred_category:
            print(f"  preferred category: {classification.preferred_category}")
        formatted_response = format_ollama_response(classification.raw_response)
        if formatted_response:
            print("  ollama response:")
            print(formatted_response)
        for warning in warnings:
            label = "info" if warning.startswith("Normalized image for Ollama:") else "warning"
            print(f"  {label}: {warning}")

        operation_error = ""
        symlink_created = False
        if not args.dry_run:
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if action == "move":
                    shutil.move(str(image), str(dest))
                else:
                    shutil.copy2(image, dest)
                if symlink_path is not None:
                    try:
                        create_relative_symlink(symlink_path, dest)
                        symlink_created = True
                    except Exception as exc:
                        warnings.append(f"Could not create category symlink: {exc}")
                        print(f"  warning: Could not create category symlink: {exc}")
                write_manifest_entry(
                    destination / config["layout"]["manifest_path"],
                    build_manifest_entry(
                        source=image,
                        canonical_relative_path=dest_relative_path,
                        symlink_relative_path=symlink_relative_path if symlink_created else None,
                        image_date=image_date,
                        date_label=date_label,
                        date_source=date_source,
                        classification=classification,
                        action=action,
                    ),
                )
                completed += 1
            except Exception as exc:
                failed += 1
                operation_error = str(exc)
                print(f"  error: Could not {action} file: {exc}")

        if config["audit"]["enabled"]:
            write_audit_entry(Path(config["audit"]["path"]), {
                "timestamp": utc_timestamp(),
                "source": str(image),
                "destination": str(dest),
                "category_symlink": str(symlink_path) if symlink_path is not None else "",
                "action": action,
                "dry_run": args.dry_run,
                "date": image_date.isoformat(),
                "date_source": date_source,
                "category": classification.category,
                "preferred_category": classification.preferred_category,
                "confidence": classification.confidence,
                "description": classification.description,
                "model": classification.model,
                "warnings": warnings,
                "ollama_response": classification.raw_response,
                "operation_status": "dry-run" if args.dry_run else ("failed" if operation_error else ("completed-with-warning" if any(warning.startswith("Could not create category symlink:") for warning in warnings) else "completed")),
                "operation_error": operation_error,
            })

    action_past = "moved" if action == "move" else "copied"
    print()
    print(f"Done. Processed: {len(images)}, {action_past}: {completed}, failed: {failed}")
    return 0
