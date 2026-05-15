from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
import tempfile

from PIL import Image

_PLUGINS_REGISTERED = False


def register_image_plugins() -> None:
    """Register optional Pillow image plugins, including HEIF/HEIC when installed."""
    global _PLUGINS_REGISTERED
    if _PLUGINS_REGISTERED:
        return
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except Exception:
        # HEIF support is optional at runtime; callers can still process formats
        # natively supported by Pillow.
        pass
    _PLUGINS_REGISTERED = True


def open_image(path: Path) -> Image.Image:
    register_image_plugins()
    return Image.open(path)


def _raw_image_to_pillow(path: Path) -> Image.Image:
    try:
        import rawpy
    except Exception as exc:
        raise RuntimeError(f"RAW image support requires rawpy: {exc}") from exc

    with rawpy.imread(str(path)) as raw:
        rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=True)
    return Image.fromarray(rgb)


def _load_for_ollama(path: Path) -> tuple[Image.Image, list[str]]:
    warnings: list[str] = []
    if path.suffix.lower() == ".nef":
        try:
            return _raw_image_to_pillow(path), warnings
        except Exception as exc:
            warnings.append(f"Could not render RAW with rawpy: {exc}")
            raise

    image = open_image(path)
    try:
        image.seek(0)
    except EOFError:
        pass
    except Exception as exc:
        warnings.append(f"Could not seek first image frame: {exc}")
    return image, warnings


DEFAULT_OLLAMA_IMAGE_MAX_SIZE = 768
DEFAULT_OLLAMA_JPEG_QUALITY = 70


def _prepare_ollama_jpeg(path: Path, max_size: int = DEFAULT_OLLAMA_IMAGE_MAX_SIZE) -> tuple[Image.Image, list[str]]:
    image, warnings = _load_for_ollama(path)
    image.thumbnail((max_size, max_size))
    if image.mode in {"RGBA", "LA", "P"}:
        image = image.convert("RGBA")
        background = Image.new("RGBA", image.size, (255, 255, 255, 255))
        background.alpha_composite(image)
        image = background.convert("RGB")
        warnings.append("Converted transparent image to RGB JPEG on white background")
    elif image.mode != "RGB":
        image = image.convert("RGB")
    return image, warnings


def normalize_image_for_ollama(
    path: Path,
    max_size: int = DEFAULT_OLLAMA_IMAGE_MAX_SIZE,
    jpeg_quality: int = DEFAULT_OLLAMA_JPEG_QUALITY,
) -> tuple[Path, list[str]]:
    """Write a smaller normalized JPEG to disk and return its absolute path."""
    image, warnings = _prepare_ollama_jpeg(path, max_size=max_size)
    try:
        handle = tempfile.NamedTemporaryFile(prefix="vision-sort-ollama-", suffix=".jpg", delete=False)
        handle.close()
        output_path = Path(handle.name).resolve()
        image.save(output_path, format="JPEG", quality=jpeg_quality, optimize=True)
        warnings.append(f"Normalized image for Ollama: {output_path}")
        return output_path, warnings
    finally:
        image.close()


def image_to_ollama_base64(
    path: Path,
    max_size: int = DEFAULT_OLLAMA_IMAGE_MAX_SIZE,
    jpeg_quality: int = DEFAULT_OLLAMA_JPEG_QUALITY,
) -> tuple[str, list[str]]:
    """Convert an image to a base64 JPEG payload for Ollama."""
    image, warnings = _prepare_ollama_jpeg(path, max_size=max_size)
    try:
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode("ascii"), warnings
    finally:
        image.close()
