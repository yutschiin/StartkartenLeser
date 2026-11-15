# ADR-0007: Local browser UI with React and Material UI

- **Status:** Accepted by the user after the browser camera spike
- **Supersedes:** UI choice in ADR-0001; Tk-specific presentation in ADR-0003/0004
- **Branch:** `epic/keyboard-first-wettkampf-workflow`

## Context

The keyboard-first Wettkampf workflow needs modern components, predictable
focus, real camera capture and local, durable data. Independent Qt/PySide and
local-browser spikes were tested. The user selected the successful browser
approach and explicitly requested Material UI.

## Decision

- Replace Tkinter with React/TypeScript and real `@mui/material` components.
- Bundle the production frontend into the Python distribution. No CDN, remote
  fonts, analytics, external assets or Node process at runtime.
- Keep Python, SQLite, managed images and DE·HTR v2. The browser talks only to
  the Python standard-library HTTP server on `127.0.0.1`.
- Use a random port and per-launch capability token delivered in the URL
  fragment. Validate exact Host, token and mutation Origin; do not enable CORS.
- Use browser `getUserMedia` for video only, with file selection as fallback.
- Retain keyed German catalogs: Python owns existing field/domain messages;
  frontend-only presentation strings live in its keyed German catalog.
- Use debounced/blur draft saving, separate deliberate approval, transactional
  retake, explicit local recognition and reviewed-Wettkampf CSV export.

## Consequences

An installed compatible browser and camera permission are required. Closing the
tab releases the camera, not the Python process; Ctrl+C in the terminal stops
the server. Linux/Chromium with the Razer Kiyo is the initial tested target,
not a claim of Windows/macOS or every browser support.

Development builds require Node/npm; running built Python packages does not.
Emotion/MUI injects styles, so CSP permits inline styles but not inline scripts.
The server is a single-user local service, not a network deployment target.
The data-directory process lock prevents simultaneous cleanup by independent
instances.

Initial Wettkampf metadata is immutable. Old mixed sessions remain unclassified
until cards are explicitly moved, never inferred from OCR. The CSV v1 dialect is
documented in the takeover plan; compatibility with a particular meet-management
program still needs verification.

The old manual corner editor is not ported. Unsafe alignment falls back to
manual transcription or retake; no guessed crop is passed to the recognizer.
All feedback uses queued, accessible MUI snackbars (persistent ones carry an
action button where needed); ongoing state is an overlay on the card image.
