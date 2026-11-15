# StartkartenLeser Desktop

> **Fictional test data:** The bundled reference cards and photos contain no real
> people or real meet entries. They are fictional test fixtures included for
> public development and testing only.

The project's own code is licensed under the [MIT License](LICENSE). Third-party
software and model artifacts retain their upstream terms. The bundled sample
photos/reference data are fictional test fixtures cleared for public use. See
[`THIRD_PARTY_NOTICES.md`](src/startkartenleser/assets/THIRD_PARTY_NOTICES.md)
and the bundled frontend license file for third-party terms.

Local Python application with a React/Material UI browser interface. All card
data, image processing and handwriting recognition stay on this computer.
The Android source remains separate.

The initial public release is source code only. No prebuilt wheel or desktop
installer is being published; build instructions below let users create and
smoke-test those artifacts themselves.

## Status

The browser UI replaces Tkinter on the keyboard-first Wettkampf epic. It uses
actual Material UI components, real camera capture, file input, durable drafts,
explicit local OCR/manual review, retake, deletion and CSV export.
See the [takeover plan](docs/feature-designs/browser-mui-implementation.md) and
[architecture decision](docs/adr/ADR-0007-local-browser-mui.md).

## Requirements

- Python 3.11+ with `venv` support
- Node.js 22+ and npm; `setup.sh` always runs the locked frontend install and build
- A recent desktop browser with camera permission (Linux/Chromium tested)
- The pinned Pillow, NumPy, OpenCV, and ONNX Runtime dependencies (installed by setup)

Tkinter, Qt and Electron are not required. The built frontend is included in the
Python package; Node is not needed to run it.
The package metadata declares Python 3.11+, but the exact dependency lock and
clean setup gate are currently verified on Python 3.14/Linux only. The tested
environment was Ubuntu 26.04.1 LTS, Python 3.14.4, Node.js 22.23.3, npm 10.9.9,
and Chromium 156.0.8078.47 (Snap). Windows, macOS, and other Python versions are
not currently claimed as supported.

The source setup needs internet access to install Python and npm dependencies.
The pinned DE·HTR model files are included and checksum-verified; if any are
missing or invalid, setup fetches the pinned copy from Hugging Face. On Ubuntu
26.04, install the prerequisites with:

```bash
sudo apt update
sudo apt install python3.14 python3.14-venv nodejs npm
sudo snap install chromium
```

Check `node --version` is 22 or newer and `npm --version` is available. The
package names were checked against Ubuntu 26.04; a clean OS installation using
these exact commands has not been rehearsed separately.

## Setup and run

From this directory, create the virtual environment and install the project:

```bash
./setup.sh
```

The script uses `python3` when available and falls back to `python`. To select a specific Python 3.11+ executable, set `PYTHON`, for example `PYTHON=python3.14 ./setup.sh`. Setup builds the locked npm frontend, creates `.venv`, installs pinned application/test dependencies, verifies/provisions the pinned DE·HTR v2 model and attribution files, and checks image/OCR imports. The model is not initialized and no inference is run during setup. If `python -m venv` is unavailable, install the venv package using your distribution's package manager; the Ubuntu 26.04 package names are listed above.

The frontend build currently prints non-fatal Rollup warnings that MUI's
`use client` directives are ignored, plus Vite's advisory that the JavaScript
chunk exceeds 500 kB. The build still completes; these are known cleanup items.

Run the app with the virtual environment's interpreter:

```bash
.venv/bin/python -m startkartenleser
```

The app opens its loopback URL in your browser. Keep the terminal open; Ctrl+C
stops the Python server. Close the browser tab to release the camera.
If automatic opening fails, use the complete printed URL, including its
per-launch fragment token. A restarted server needs its new launch URL.

For an explicitly separate test database and manual browser launch:

```bash
.venv/bin/python -m startkartenleser --no-browser --data-dir /tmp/startkartenleser-demo
```

### Keyboard workflow

Create a Wettkampf with number, distance, stroke and category. Select the camera
and start scanning. **Space** activates the focused capture button. After saving
the image, **Retake** is focused; **Tab** leads to Name, Vorname, Jahrgang,
the Mädchen/Junge radio group, Strecke, Lage, Lauf, Bahn, Erzielte Zeit and Zeitnehmer.
The form follows the A6 card layout beside an equally sized original-image panel.

- **Tab / Shift+Tab:** forward/backward.
  Both gender options are separate stops: Jahrgang → Mädchen → Junge → Strecke.
- **Enter** in an input: next control.
- **Space / arrow keys** in the gender radio group: select Mädchen or Junge. Existing ambiguous marks
  remain unchanged until selection and display a warning.
- **Ctrl+Enter:** flush changes, approve the entire card, focus the next capture.
- Changes autosave after a short debounce and on field exit; saving is not approval.
- Retake preserves the card number and old data until a new image succeeds.

OCR is a separate, explicit **local recognition** action. It is not simulated
and does not automatically delay field entry. Errors allow manual transcription.
Source images and recognition overlays remain available beside the form; raw OCR
and provenance remain stored but are no longer shown in a Card Details section. Failed alignment can be
handled by retake or manual entry; the old manual corner editor is not ported.

CSV export requires a nonempty, fully reviewed Wettkampf. Downloads use UTF-8
with BOM, semicolons and CRLF, with canonical milliseconds where unambiguous and
formula-safe text. See the exact [CSV contract](docs/feature-designs/browser-mui-implementation.md#csv-v1).
Compatibility with a specific meet-management program is not yet certified.

### Existing data

The existing application data folder is unchanged:
`$XDG_DATA_HOME/startkartenleser` or `~/.local/share/startkartenleser`.
Schema-v1 upgrade creates a database snapshot beside the database before adding
Wettkampf metadata. Old sessions are explicitly unclassified, not guessed from
OCR; reopen them and move their cards into newly created Wettkämpfe.
See [migration/restoration](docs/architecture.md#persistence-and-migration).
Back up the whole data directory, including images, before upgrading important
data. Browser-spike test data is never mixed into production storage.

Run the headless unit and temporary-database/filesystem integration suite with:

```bash
.venv/bin/python -m pytest
```

Frontend validation and rebuilding:

```bash
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Successful test/typecheck/build commands exit with status 0. At this revision,
the Python suite has 368 passing tests and the frontend suite has 47; Vitest uses
a 20-second test timeout for slower MUI/jsdom interactions. TypeScript checking
passes and the production build completes with the non-fatal warnings described
above. Counts can change as tests are added.

`setup.sh` rebuilds the frontend for source users, but the normal Python package
build does not run npm; it packages the checked-in `web_static/` assets. Keep the
generated assets in Git and commit frontend source, npm lock, and rebuilt assets
together so a wheel build from a source archive includes a working UI without
requiring Node at wheel-install/runtime time.
For distribution, build a source archive and then its wheel in a clean build
environment. For example:

```bash
python3 -m venv .build-venv
.build-venv/bin/python -m pip install build
.build-venv/bin/python -m build
```

This writes the source archive and wheel to `dist/`. Install and smoke-test the
wheel in a separate clean environment before publishing it. For example:

```bash
python3 -m venv .wheel-test
.wheel-test/bin/python -m pip install dist/startkartenleser_desktop-*.whl
.wheel-test/bin/python -m startkartenleser --no-browser \
  --data-dir /tmp/startkartenleser-wheel-smoke
```

Open the printed loopback URL and verify the bundled UI; Ctrl+C stops the server.
Do not reuse branch-specific stale `build/` output when checking a release.
`requirements.txt` is the Python contributor setup path; direct dependencies are
pinned in `pyproject.toml` and resolver versions are recorded in
`requirements.lock`. Model attributions are listed in
[`THIRD_PARTY_NOTICES.md`](src/startkartenleser/assets/THIRD_PARTY_NOTICES.md).

## Local OCR correction

OCR results remain editable suggestions. Race-specific Lage values and aliases are
configured in [`recognition-policy.json`](src/startkartenleser/assets/recognition-policy.json).
The app loads a user override from
`$XDG_DATA_HOME/startkartenleser/recognition-policy.json` (normally
`~/.local/share/startkartenleser/recognition-policy.json`) when present; otherwise
it uses the bundled policy. Invalid configuration stops startup with an error.
Restart the app after editing the policy.

Exact aliases are resolved first, followed by a unique nearest match within
`max_edit_distance` (0 disables fuzzy matching). Single-character OCR errors,
ties, and distant matches are not guessed. Corrected suggestions retain their
raw OCR transcription in storage and display it beneath the review fields.
Manual or confirmed values are never overwritten by correction.

The "Startkarte prüfen" inputs use these corrected suggestions, including when
reopening older, unconfirmed OCR results. Distances are normalized to whole meters:
`50`, `50m`, and `50 m` all become `50 m`. Only positive whole numbers with an
optional `m` unit are normalized; ambiguous OCR such as `10Dm` is not guessed.
Times are normalized to `M:SS,ff`
(or three fractional digits when needed), e.g. `42, 18` becomes `0:42,18`.
Explicitly apostrophe-prefixed short years expand to the latest matching year
between `minimum_birth_year` (default `1927`) and the current year:
`'02` becomes `2002`, and `'85` becomes `1985`.
For three-digit OCR starting with `1`, that leading character can also represent
a misread apostrophe: `111` becomes `2011`, but only if exactly one year in the
configured range ends in `11`. Multiple matching centuries are not guessed.
The optional `minimum_birth_year` setting defaults to `1927` in older policies too.
Bare two-digit years and ambiguous or invalid times are not guessed; they stay
visible with a review warning. Normalized suggestions are persisted when the
review is saved; opening a card alone does not modify stored data.

The photo benchmark uses the same policy and correction code:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_reference_dataset.py \
  --config src/startkartenleser/assets/recognition-policy.json \
  --output tests/results/new-run.csv
```

Each result retains raw and corrected text, the correction version, and a policy
SHA-256 fingerprint. The ground truth and binary scoring rules are unchanged.

## Troubleshooting

- **`python -m venv` fails:** install the virtual-environment package for your
  Python distribution, then rerun `./setup.sh`.
- **Node version check fails:** `setup.sh` needs Node.js 22+ and npm even though
  Node is not needed after the frontend is bundled.
- **Model check fails:** run `.venv/bin/python scripts/fetch_model.py --check`.
  The normal setup repairs missing or invalid pinned model files when online.
- **Camera does not open:** use the complete loopback URL printed by the app,
  allow camera access for that local site, and use the new URL after a restart.
- **Frontend build warnings:** Rollup currently reports ignored MUI `use client`
  directives and Vite reports a JavaScript chunk over 500 kB. The build completes;
  treat these as known warnings, not as evidence that the build failed.
- **Workflow evaluation from a source archive:** Git revision/dirty metadata is
  recorded as `null` when the source has no `.git` directory; evaluation/tests
  still work.

## Project documents

- [Wettkampf and keyboard-first workflow](docs/feature-designs/keyboard-first-wettkampf-epic.md)
- [Browser/MUI takeover plan and CSV contract](docs/feature-designs/browser-mui-implementation.md)
- [Product requirements](docs/prd.md)
- [Architecture](docs/architecture.md)
- [Publication-readiness checklist](docs/demo-readiness-checklist.md)
- [Publication-readiness task list](docs/publication-readiness-tasks.md)
- [Historical MVP workflow proposal](docs/feature-designs/mvp-workflow.md)
- [Historical MVP implementation plan](docs/implementation-plan.md)
- [Large-window UI mockup](docs/ui-mockup.html)
- [Proposed A6 Startkarte mockup](docs/startkarte-a6-proposal.html)
- [Architecture decision records](docs/adr/README.md)
- [Blank Startkarte reference](docs/Startkarte_empty.jpg)

Card data is personal information. Do not add hosted OCR, analytics, or synchronization without an explicit privacy and product decision.
