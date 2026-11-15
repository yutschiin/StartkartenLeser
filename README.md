# StartkartenLeser Desktop

StartkartenLeser helps a swimming meet organizer capture and review paper
Startkarten. It is a local Python application with a React/Material UI interface
opened in a desktop browser. Card images, OCR and application data stay on the
computer; the app does not upload, sync or share card data.

The source and project code are MIT-licensed. Model and dependency assets retain
their own terms; see [third-party notices](src/startkartenleser/assets/THIRD_PARTY_NOTICES.md)
and the bundled frontend license file. The included sample cards and photos are
fictional test fixtures, not real people or meet entries.
This repository provides source code; no prebuilt desktop installer is published.

## Features

- Create and reopen Wettkämpfe with a number, distance, stroke (Freistil,
  Brust, Rücken, Schmetterling or Lagen) and category (Weiblich or Männlich).
- Capture a card with a camera or choose a PNG/JPEG file.
- Review the source image beside editable card fields. Local handwriting
  recognition supplies suggestions; warnings flag differences from event
  metadata. A person decides what to keep and approves each card. Manual entry
  remains available when alignment or OCR fails.
- Use keyboard navigation, autosaved drafts, same-card retake, card deletion and
  explicit reassignment of older unclassified cards. Space captures when the
  capture button is focused; Tab/Shift+Tab move through controls; Enter advances
  through review fields; Ctrl+Enter approves and returns to capture.
- Export a nonempty, fully reviewed Wettkampf as CSV. Export details are in the
  [CSV format](docs/csv-format.md).

OCR is not a guarantee of accuracy. The app does not provide manual corner
adjustment, editable Wettkampf metadata, mixed/open categories or a certified
import format for a particular meet-management program.

## Requirements and support

- Ubuntu 26.04 x86_64 is the tested source-install target; the clean setup was
  tested with Python 3.14.4, Node.js 22.22.1 and npm 9.2.0. Other operating
  systems and Python versions are not currently claimed as supported.
- Python 3.11+ with `venv`, Node.js 22+ and npm are required for source setup.
  Node/npm are not needed to run the built Python application.
- A recent desktop browser with camera permission is needed to use the app.
  Chromium is the tested example; browser installation is separate and can be
  skipped if a compatible browser is already installed.

Install the Ubuntu source-build prerequisites:

```bash
sudo apt update
sudo apt install python3.14 python3.14-venv nodejs npm
```

The APT commands and venv creation succeeded in a clean `ubuntu:26.04` Docker
container. If you need a browser, Chromium is one option (`sudo snap install
chromium`); that optional Snap command has not been tested on a fresh desktop.

Setup needs internet access for Python and npm dependencies. The pinned DE·HTR
model and notices are included and checksum-verified; if missing or invalid,
setup downloads the pinned copies from Hugging Face. No card data is sent during
setup or recognition.

## Install and run from source

From the repository root:

```bash
./setup.sh
.venv/bin/python -m startkartenleser
```

Setup installs dependencies, builds the browser UI, provisions/verifies model
assets, and checks image/OCR imports. The app prints a local URL and opens it in
your browser. Keep the terminal open; Ctrl+C stops the server. Close the browser
tab to release the camera. If automatic opening fails, open the complete URL
printed in the terminal.

Create a Wettkampf, capture or select a card image, review and edit its values,
then approve it before continuing. Draft saving is not approval. CSV export is
available after all cards in a nonempty Wettkampf have been reviewed.

To run with a disposable data directory and open the URL manually:

```bash
.venv/bin/python -m startkartenleser --no-browser \
  --data-dir /tmp/startkartenleser-demo
```

## Data and privacy

Application data is stored in `$XDG_DATA_HOME/startkartenleser` or, by default,
`~/.local/share/startkartenleser`. Images and records remain until you delete
them or remove the data directory. Back up the entire directory, including
images. The application does not encrypt local data; operating-system account
security and user-managed backups are your responsibility. Deleting a stored
image does not delete the original file you selected or a CSV you downloaded.

Older schema-v1 databases are backed up before migration. Read
[architecture: data and migration](docs/architecture.md#data-and-migration)
before upgrading important data.

## Development and verification

Run the Python tests:

```bash
.venv/bin/python -m pytest
```

Run the frontend tests, type check and production build:

```bash
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

The frontend build may report MUI `use client` and large-chunk warnings; these
are non-fatal. See [architecture](docs/architecture.md), the
[product brief](docs/prd.md), the [ADR index](docs/adr/README.md),
[OCR evaluation](docs/ocr-test-strategy.md), and the
[workflow evaluation tool](docs/workflow-evaluation.md) for focused developer
references.
