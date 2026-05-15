#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 IMAGE_PATH [MODEL]" >&2
  echo "Example: $0 ./incoming/example.jpg llama3.2-vision" >&2
  exit 2
fi

IMAGE_PATH="$1"
MODEL="${2:-llama3.2-vision}"
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
MAX_SIZE="${MAX_SIZE:-1600}"
JPEG_QUALITY="${JPEG_QUALITY:-85}"
CURL_MAX_TIME_SECONDS="${CURL_MAX_TIME_SECONDS:-600}"
# Ollama's HTTP API documents base64 images. Set USE_IMAGE_PATH=1 only if you
# explicitly want to test a local build/provider that accepts filesystem paths.
USE_IMAGE_PATH="${USE_IMAGE_PATH:-0}"

if [[ ! -f "$IMAGE_PATH" ]]; then
  echo "Image not found: $IMAGE_PATH" >&2
  exit 1
fi

INPUT_ABS="$(python3 - "$IMAGE_PATH" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).expanduser().resolve())
PY
)"

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ollama-vision-test.XXXXXX")"
PROCESSED_IMAGE="$WORK_DIR/ollama-input.jpg"

PYTHON_BIN="python3"
if [[ -x "./.venv/bin/python" ]]; then
  PYTHON_BIN="./.venv/bin/python"
fi

"$PYTHON_BIN" - "$INPUT_ABS" "$PROCESSED_IMAGE" "$MAX_SIZE" "$JPEG_QUALITY" <<'PY'
import sys
from pathlib import Path
from PIL import Image

source = Path(sys.argv[1])
dest = Path(sys.argv[2])
max_size = int(sys.argv[3])
quality = int(sys.argv[4])

with Image.open(source) as image:
    try:
        image.seek(0)
    except Exception:
        pass
    image.thumbnail((max_size, max_size))
    if image.mode in {"RGBA", "LA", "P"}:
        image = image.convert("RGBA")
        background = Image.new("RGBA", image.size, (255, 255, 255, 255))
        background.alpha_composite(image)
        image = background.convert("RGB")
    elif image.mode != "RGB":
        image = image.convert("RGB")
    image.save(dest, format="JPEG", quality=quality, optimize=True)
PY

PROCESSED_ABS="$(python3 - "$PROCESSED_IMAGE" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).resolve())
PY
)"

ORIGINAL_BYTES="$(wc -c < "$INPUT_ABS" | tr -d ' ')"
PROCESSED_BYTES="$(wc -c < "$PROCESSED_ABS" | tr -d ' ')"

echo "Original image:  $INPUT_ABS ($ORIGINAL_BYTES bytes)" >&2
echo "Processed image: $PROCESSED_ABS ($PROCESSED_BYTES bytes)" >&2
echo "Curl timeout:    ${CURL_MAX_TIME_SECONDS}s" >&2

PROMPT='Choose exactly one category: Birds, Mammals, Insects, Butterflies-Moths, Reptiles-Amphibians, Fish-Aquatic-Life, Pets-Domestic-Animals, Animal-Tracks-Signs, Flowers, Trees-Forests, Leaves-Foliage, Mushrooms-Fungi, Moss-Lichen, Plants-Other, Mountains-Rocks, Water-Rivers-Lakes, Seascapes-Coast, Fields-Meadows, Sky-Clouds-Weather, Sunrise-Sunset, Snow-Ice, Macro-Nature-Details, People-Outdoors, Buildings-Structures, Trails-Paths, Vehicles-Equipment, Other-Nature, Unclear-Needs-Review. Return only JSON like {"category":"Birds","confidence":0.8,"description":"short description"}.'

if [[ "$USE_IMAGE_PATH" == "1" ]]; then
  IMAGE_VALUE="$PROCESSED_ABS"
  echo "Sending image path in JSON images[] (non-standard for Ollama HTTP API)." >&2
else
  IMAGE_VALUE="$(python3 - "$PROCESSED_ABS" <<'PY'
import base64
import sys
from pathlib import Path
print(base64.b64encode(Path(sys.argv[1]).read_bytes()).decode("ascii"))
PY
)"
  echo "Sending processed image as base64, as required by Ollama HTTP API." >&2
fi

python3 - "$MODEL" "$PROMPT" "$IMAGE_VALUE" <<'PY' | curl -v --max-time "$CURL_MAX_TIME_SECONDS" "$OLLAMA_HOST/api/generate" \
  -H 'Content-Type: application/json' \
  --data-binary @-
import json
import sys

model, prompt, image = sys.argv[1:4]
print(json.dumps({
    "model": model,
    "prompt": prompt,
    "images": [image],
    "stream": False,
    "format": "json",
}))
PY
