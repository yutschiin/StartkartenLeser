#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT_DIR"

if [ -n "${PYTHON:-}" ]; then
    PYTHON=$PYTHON
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "Error: Python 3.11+ was not found. Install Python or set PYTHON to its executable." >&2
    exit 1
fi

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Error: Python executable '$PYTHON' was not found." >&2
    exit 1
fi

"$PYTHON" -c 'import sys; sys.exit("Error: Python 3.11 or newer is required.") if sys.version_info < (3, 11) else None'

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    echo "Error: Node.js 22+ and npm are required to build the bundled browser UI." >&2
    exit 1
fi
node -e 'if (Number(process.versions.node.split(".")[0]) < 22) { console.error("Error: Node.js 22+ is required."); process.exit(1); }'

npm --prefix frontend ci
npm --prefix frontend run build

"$PYTHON" -m venv .venv
.venv/bin/python -m pip install --upgrade pip==26.3
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/fetch_model.py
.venv/bin/python -c 'import PIL, numpy, cv2, onnxruntime; print("Pillow, NumPy, OpenCV, and ONNX Runtime imports verified.")'
.venv/bin/python scripts/fetch_model.py --check

echo "Setup complete. Run the app with: .venv/bin/python -m startkartenleser"
