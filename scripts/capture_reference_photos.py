"""Take webcam photos of reference cards in CSV order, saving mapped filenames.

Run from the repository root:

    PYTHONPATH=src .venv/bin/python scripts/capture_reference_photos.py

The browser opens a local capture page. Start the camera, then press the capture
button for each card shown. Each accepted frame is saved immediately under the
CSV's ``image_filename`` and the next card is shown. Output goes into a new
``tests/new-card-photos-<timestamp>`` directory; existing directories are never
overwritten. Press Ctrl+C in the terminal to stop the server.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime
import io
import json
from pathlib import Path
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any
import webbrowser

from PIL import Image, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCES = ROOT / "tests" / "reference_data.csv"
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_JSON_BYTES = MAX_IMAGE_BYTES * 4 // 3 + 4096
MAX_IMAGE_PIXELS = 40_000_000
SUPPORTED_TYPES = {"image/jpeg": {".jpg", ".jpeg"}, "image/png": {".png"}}


class CaptureError(ValueError):
    """An expected request or input error with an HTTP status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def load_dataset(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"card_no", "name", "first_name", "image_filename"}
        if reader.fieldnames is None or not required <= set(reader.fieldnames):
            missing = sorted(required - set(reader.fieldnames or ()))
            raise ValueError(f"reference CSV is missing required columns: {', '.join(missing)}")
        rows = list(reader)

    if not rows:
        raise ValueError("reference CSV contains no cards")
    numbers: set[str] = set()
    filenames: set[str] = set()
    for row in rows:
        number = row["card_no"].strip()
        filename = row["image_filename"].strip()
        suffix = Path(filename).suffix.lower()
        if not number or number in numbers:
            raise ValueError(f"card numbers must be present and unique: {number!r}")
        if not filename or Path(filename).name != filename or suffix not in {".jpg", ".jpeg", ".png"}:
            raise ValueError(f"invalid image_filename for card {number}: {filename!r}")
        if filename in filenames:
            raise ValueError(f"duplicate image_filename: {filename!r}")
        if any(not row[key].strip() for key in ("name", "first_name")):
            raise ValueError(f"card {number} is missing a name")
        row["card_no"] = number
        row["image_filename"] = filename
        numbers.add(number)
        filenames.add(filename)
    return rows  # Keep the CSV row order; it is the capture order.


def validate_image(data: bytes, mime_type: str, filename: str) -> None:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise CaptureError(413, f"photo must be between 1 byte and {MAX_IMAGE_BYTES} bytes")
    allowed_extensions = SUPPORTED_TYPES.get(mime_type)
    if allowed_extensions is None or Path(filename).suffix.lower() not in allowed_extensions:
        raise CaptureError(415, "photo format must match the dataset filename (JPEG or PNG)")
    expected_format = {"image/jpeg": "JPEG", "image/png": "PNG"}[mime_type]
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != expected_format:
                raise CaptureError(415, "photo content does not match its format")
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
                raise CaptureError(413, "photo dimensions exceed the supported limit")
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as error:
        raise CaptureError(400, "photo could not be decoded") from error


class DatasetCapture:
    """Save one accepted photo per row, requiring order and never overwriting."""

    def __init__(self, rows: list[dict[str, str]], output_dir: Path, *, resume: bool = False) -> None:
        self.rows = rows
        self.output_dir = output_dir.resolve()
        self.index = 0
        if self.output_dir.exists():
            if not resume:
                raise ValueError(f"output directory already exists: {self.output_dir}")
            if not self.output_dir.is_dir():
                raise ValueError(f"resume path is not a directory: {self.output_dir}")
            existing = sorted(path.name for path in self.output_dir.iterdir())
            expected = [row["image_filename"] for row in rows[:len(existing)]]
            if existing != sorted(expected) or len(existing) > len(rows):
                raise ValueError("resume directory must contain only a complete prefix of dataset photos")
            for row in rows[:len(existing)]:
                image_path = self.output_dir / row["image_filename"]
                if image_path.is_symlink() or not image_path.is_file():
                    raise ValueError(f"invalid existing photo: {image_path.name}")
                suffix = image_path.suffix.lower()
                mime_type = "image/png" if suffix == ".png" else "image/jpeg"
                validate_image(image_path.read_bytes(), mime_type, image_path.name)
            self.index = len(existing)
        elif resume:
            raise ValueError(f"cannot resume; output directory does not exist: {self.output_dir}")
        self.lock = Lock()

    def state(self) -> dict[str, Any]:
        with self.lock:
            current = self.rows[self.index] if self.index < len(self.rows) else None
            return {
                "total": len(self.rows),
                "captured": self.index,
                "complete": current is None,
                "current": current,
                "output_dir": str(self.output_dir),
            }

    def save_current(self, card_no: str, data: bytes, mime_type: str) -> dict[str, Any]:
        with self.lock:
            if self.index >= len(self.rows):
                raise CaptureError(409, "all dataset cards have already been captured")
            row = self.rows[self.index]
            if card_no != row["card_no"]:
                raise CaptureError(409, "capture is out of dataset order; reload the page")
            filename = row["image_filename"]
            validate_image(data, mime_type, filename)

            if not self.output_dir.exists():
                self.output_dir.mkdir(parents=True, exist_ok=False)
            destination = self.output_dir / filename
            try:
                with destination.open("xb") as output:
                    output.write(data)
                    output.flush()
            except FileExistsError as error:
                raise CaptureError(409, f"refusing to overwrite {filename}") from error
            except OSError as error:
                try:
                    destination.unlink(missing_ok=True)
                except OSError:
                    pass
                raise CaptureError(500, "photo could not be saved") from error

            self.index += 1
            current = self.rows[self.index] if self.index < len(self.rows) else None
            return {
                "total": len(self.rows),
                "captured": self.index,
                "complete": current is None,
                "current": current,
                "output_dir": str(self.output_dir),
            }


PAGE = r"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Startkarten-Testfotos</title>
  <style>
    :root { color-scheme: light; font-family: system-ui, sans-serif; color: #17252d; background: #edf1f2; }
    * { box-sizing: border-box; }
    body { margin: 0; min-width: 320px; }
    main { width: min(1050px, 100%); margin: 0 auto; padding: 22px; }
    h1 { margin: 0 0 8px; color: #143b55; }
    #card { margin: 16px 0; padding: 18px; border-radius: 10px; background: white; }
    #position { color: #087c78; font-weight: 750; }
    #person { margin: 5px 0 8px; font-size: 26px; }
    #details { color: #52636c; }
    #filename { margin-top: 8px; font: 14px ui-monospace, monospace; overflow-wrap: anywhere; }
    video { display: block; width: 100%; max-height: 72vh; aspect-ratio: 16 / 9; object-fit: contain; border-radius: 10px; background: #17252d; }
    button { min-height: 48px; margin: 14px 8px 0 0; padding: 0 20px; border: 0; border-radius: 7px; color: white; background: #087c78; font: inherit; font-weight: 750; cursor: pointer; }
    button:disabled { opacity: .48; cursor: default; }
    #status { min-height: 25px; margin-top: 12px; color: #52636c; }
    .done { padding: 20px; border-radius: 10px; background: #e2f4ee; color: #115c4f; }
    @media (max-width: 600px) { main { padding: 12px; } video { max-height: 55vh; } }
  </style>
</head>
<body>
<main>
  <h1>Startkarten-Testfotos</h1>
  <p>Die Aufnahme folgt der Reihenfolge in der Referenz-CSV. Jede Aufnahme wird sofort gespeichert und schaltet zur nächsten Karte weiter.</p>
  <section id="card">
    <div id="position"></div>
    <h2 id="person"></h2>
    <div id="details"></div>
    <div id="filename"></div>
  </section>
  <video id="video" autoplay muted playsinline aria-label="Live-Kamerabild"></video>
  <button id="start">Kamera starten</button>
  <button id="capture" disabled>Foto aufnehmen und weiter</button>
  <div id="status" role="status" aria-live="polite">Starten Sie die Kamera, richten Sie die nächste Karte aus und drücken Sie Leertaste oder die Schaltfläche.</div>
</main>
<script>
  const video = document.querySelector("#video");
  const startButton = document.querySelector("#start");
  const captureButton = document.querySelector("#capture");
  const statusText = document.querySelector("#status");
  let state;
  let stream;
  let busy = false;

  function render() {
    const card = state.current;
    if (!card) {
      stopCamera();
      document.querySelector("#card").innerHTML = "";
      const done = document.createElement("div");
      done.className = "done";
      done.textContent = `Fertig: ${state.total} Fotos gespeichert in ${state.output_dir}`;
      document.querySelector("#card").append(done);
      video.hidden = true;
      startButton.hidden = true;
      captureButton.hidden = true;
      statusText.textContent = "Alle Karten aus dem Datensatz wurden fotografiert.";
      return;
    }
    document.querySelector("#position").textContent = `Karte ${state.captured + 1} von ${state.total} · Datensatz-Nr. ${card.card_no}`;
    document.querySelector("#person").textContent = `${card.name}, ${card.first_name}`;
    const detail = [card.year, card.gender, card.course && `${card.course} m`, card.position && card.position, card.heat && `Lauf ${card.heat}`, card.lane && `Bahn ${card.lane}`].filter(Boolean);
    document.querySelector("#details").textContent = detail.join(" · ");
    document.querySelector("#filename").textContent = `Speichern als: ${card.image_filename}`;
    statusText.textContent = `Fortschritt: ${state.captured} / ${state.total}`;
  }

  async function startCamera() {
    startButton.disabled = true;
    statusText.textContent = "Kamera wird geöffnet …";
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 7680 }, height: { ideal: 4320 } },
        audio: false,
      });
      const track = stream.getVideoTracks()[0];
      const capabilities = track.getCapabilities?.();
      if (capabilities?.width?.max && capabilities?.height?.max) {
        await track.applyConstraints({
          width: { ideal: capabilities.width.max },
          height: { ideal: capabilities.height.max },
        }).catch(() => undefined);
      }
      video.srcObject = stream;
      await video.play();
      await new Promise((resolve) => {
        if (video.videoWidth) resolve();
        else video.addEventListener("loadedmetadata", resolve, { once: true });
      });
      const settings = track.getSettings?.();
      startButton.hidden = true;
      captureButton.disabled = false;
      statusText.textContent = `Kamera bereit · ${settings?.width || video.videoWidth} × ${settings?.height || video.videoHeight}`;
    } catch (error) {
      startButton.disabled = false;
      statusText.textContent = `Kamera nicht verfügbar: ${error.message || error}`;
    }
  }

  function stopCamera() {
    stream?.getTracks().forEach((track) => track.stop());
    stream = undefined;
    video.srcObject = null;
  }

  async function takePhoto() {
    if (!stream || busy || !state.current || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
    busy = true;
    captureButton.disabled = true;
    statusText.textContent = "Foto wird gespeichert …";
    try {
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
      const image = canvas.toDataURL("image/jpeg", 0.94);
      const response = await fetch("/api/capture", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ card_no: state.current.card_no, image }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Foto konnte nicht gespeichert werden.");
      state = result;
      render();
    } catch (error) {
      statusText.textContent = error.message || String(error);
      captureButton.disabled = false;
    } finally {
      busy = false;
      captureButton.disabled = !stream || !state?.current;
    }
  }

  startButton.addEventListener("click", startCamera);
  captureButton.addEventListener("click", takePhoto);
  document.addEventListener("keydown", (event) => {
    if (event.code === "Space" && !event.repeat && !event.target.closest("button")) {
      event.preventDefault();
      takePhoto();
    }
  });
  window.addEventListener("pagehide", stopCamera);
  fetch("/api/state", { cache: "no-store" }).then((response) => response.json()).then((value) => {
    state = value;
    render();
  }).catch((error) => { statusText.textContent = `Datensatz konnte nicht geladen werden: ${error}`; });
</script>
</body>
</html>"""


def make_handler(capture: DatasetCapture) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/":
                body = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Permissions-Policy", "camera=(self), microphone=()")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                    "media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'",
                )
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/state":
                self.send_json(200, capture.state())
            else:
                self.send_json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/api/capture":
                self.send_json(404, {"error": "not found"})
                return
            try:
                length_text = self.headers.get("Content-Length", "")
                if not length_text.isascii() or not length_text.isdigit():
                    raise CaptureError(400, "invalid content length")
                length = int(length_text)
                if length < 1 or length > MAX_JSON_BYTES:
                    raise CaptureError(413, "photo request is too large")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise CaptureError(400, "invalid photo request")
                card_no, image_data = payload.get("card_no"), payload.get("image")
                if not isinstance(card_no, str) or not isinstance(image_data, str):
                    raise CaptureError(400, "photo request needs a card number and image")
                match = re.fullmatch(r"data:(image/(?:jpeg|png));base64,([A-Za-z0-9+/=]+)", image_data)
                if match is None:
                    raise CaptureError(415, "photo must be a JPEG or PNG data URL")
                mime_type, encoded = match.groups()
                try:
                    image_bytes = base64.b64decode(encoded, validate=True)
                except (ValueError, binascii.Error) as error:
                    raise CaptureError(400, "photo data is not valid base64") from error
                self.send_json(200, capture.save_current(card_no, image_bytes, mime_type))
            except CaptureError as error:
                self.send_json(error.status, {"error": str(error)})
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.send_json(400, {"error": "request is not valid JSON"})
            except OSError:
                self.send_json(500, {"error": "photo could not be saved"})

    return Handler


def default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return ROOT / "tests" / f"new-card-photos-{stamp}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--references", type=Path, default=DEFAULT_REFERENCES)
    parser.add_argument("--output-dir", type=Path, default=default_output_dir())
    parser.add_argument("--host", default="127.0.0.1", help="camera capture must remain localhost-only")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="print the URL without opening a browser")
    parser.add_argument("--resume", action="store_true", help="continue a partial output directory after verifying its photos")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("camera capture is intentionally limited to localhost")
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")

    rows = load_dataset(args.references)
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    output_dir = output_dir.resolve()
    capture = DatasetCapture(rows, output_dir, resume=args.resume)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(capture))
    server.daemon_threads = True
    address, port = server.server_address[:2]
    url = f"http://{address}:{port}/"
    print(f"Dataset: {args.references.resolve()} ({len(rows)} cards, CSV order)", flush=True)
    print(f"Photos will be saved to: {output_dir}", flush=True)
    print(f"Open: {url}", flush=True)
    print("Press Ctrl+C here to stop the capture server.", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCapture server stopped.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
