from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config


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
    from .files import build_destination_path, discover_images

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
    for index, image in enumerate(images, start=1):
        image_date, date_source, warnings = get_image_date(image, config)
        classification = classify_image(image, config, model_override=args.model)
        warnings.extend(classification.warnings)
        dest = build_destination_path(destination, image_date.strftime(date_format), classification.category, image)
        print(f"[{index}/{len(images)}] {image.name} -> {dest.relative_to(destination)} ({classification.category}, {date_source})")
        for warning in warnings:
            print(f"  warning: {warning}")

    action_past = "moved" if action == "move" else "copied"
    print()
    print(f"Done. Processed: {len(images)}, {action_past}: 0, failed: 0")
    return 0
