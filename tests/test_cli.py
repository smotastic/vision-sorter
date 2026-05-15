from __future__ import annotations

import json

import pytest

from vision_sort.classifier import ClassificationResult
from vision_sort.cli import build_parser, main


def test_parser_accepts_expected_arguments():
    parser = build_parser()

    args = parser.parse_args([
        "incoming",
        "sorted",
        "--config",
        "custom.json",
        "--model",
        "llava",
        "--move",
        "--dry-run",
    ])

    assert args.source == "incoming"
    assert args.destination == "sorted"
    assert args.config == "custom.json"
    assert args.model == "llava"
    assert args.move is True
    assert args.dry_run is True


def test_main_prints_copy_summary_by_default(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "incoming"
    destination = tmp_path / "sorted"
    source.mkdir()
    destination.mkdir()

    exit_code = main([str(source), str(destination), "--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Vision Sort" in output
    assert f"Source:      {source}" in output
    assert f"Destination: {destination}" in output
    assert "Action:      copy" in output
    assert "Model:       llama3.2-vision" in output
    assert "Dry run:     yes" in output


def test_main_writes_audit_log_with_raw_ollama_response(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "incoming"
    destination = tmp_path / "sorted"
    source.mkdir()
    destination.mkdir()
    image = source / "photo.jpg"
    image.write_bytes(b"fake")
    raw_response = '{"category":"Birds","preferred_category":"Songbird","confidence":0.8,"description":"bird"}'

    monkeypatch.setattr(
        "vision_sort.classifier.classify_image",
        lambda path, config, model_override=None: ClassificationResult(
            "Birds",
            0.8,
            "bird",
            "llama3.2-vision",
            [],
            "Songbird",
            raw_response,
        ),
    )

    exit_code = main([str(source), str(destination), "--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "preferred category: Songbird" in output
    entries = [json.loads(line) for line in (tmp_path / "vision-sort-audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert entries[0]["preferred_category"] == "Songbird"
    assert entries[0]["ollama_response"] == raw_response


def test_main_copies_classified_images_when_not_dry_run(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "incoming"
    destination = tmp_path / "sorted"
    source.mkdir()
    destination.mkdir()
    image = source / "photo.jpg"
    image.write_bytes(b"fake")

    monkeypatch.setattr(
        "vision_sort.classifier.classify_image",
        lambda path, config, model_override=None: ClassificationResult(
            "Birds",
            0.9,
            "bird",
            "llama3.2-vision",
            [],
            "Bird",
            '{"category":"Birds"}',
        ),
    )

    exit_code = main([str(source), str(destination)])

    output = capsys.readouterr().out
    assert exit_code == 0
    copied_files = list(destination.glob("*-Birds/photo.jpg"))
    assert len(copied_files) == 1
    assert copied_files[0].read_bytes() == b"fake"
    assert image.exists()
    assert "Done. Processed: 1, copied: 1, failed: 0" in output


def test_main_prints_destructive_move_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "incoming"
    destination = tmp_path / "sorted"
    source.mkdir()
    destination.mkdir()

    exit_code = main([str(source), str(destination), "--move"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Action:      move (destructive)" in output


def test_main_requires_source_and_destination():
    with pytest.raises(SystemExit):
        main([])
