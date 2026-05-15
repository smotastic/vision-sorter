from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image

from vision_sort.images import image_to_ollama_base64, normalize_image_for_ollama


def test_image_to_ollama_base64_converts_png_to_jpeg_payload(tmp_path):
    path = tmp_path / "transparent.png"
    Image.new("RGBA", (10, 10), (255, 0, 0, 128)).save(path)

    payload, warnings = image_to_ollama_base64(path)

    decoded = base64.b64decode(payload)
    converted = Image.open(BytesIO(decoded))
    assert converted.format == "JPEG"
    assert converted.mode == "RGB"
    assert any("transparent" in warning for warning in warnings)


def test_normalize_image_for_ollama_writes_smaller_jpeg_file(tmp_path):
    path = tmp_path / "source.png"
    Image.new("RGB", (20, 20), "blue").save(path)

    output_path, warnings = normalize_image_for_ollama(path)

    try:
        assert output_path.is_absolute()
        assert output_path.exists()
        converted = Image.open(output_path)
        assert converted.format == "JPEG"
        assert converted.mode == "RGB"
        assert any("Normalized image for Ollama" in warning for warning in warnings)
    finally:
        output_path.unlink(missing_ok=True)
