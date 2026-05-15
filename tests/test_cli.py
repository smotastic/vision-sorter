from __future__ import annotations

import pytest

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
    assert "Model:       qwen3.6" in output
    assert "Dry run:     yes" in output


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
