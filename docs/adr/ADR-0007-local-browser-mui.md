# ADR-0007: Local browser interface with React and Material UI

- **Status:** Accepted; current UI architecture.
- **Supersedes:** Tkinter as the production UI in ADR-0001 and the presentation
  details in ADR-0003/ADR-0004.

## Context

The keyboard-first Wettkampf workflow needs camera access, predictable focus,
editable local data and a maintainable interface while retaining the Python
recognition and persistence core. A local browser UI meets this without shipping
an embedded browser runtime.

## Decision

- Use React, TypeScript and Material UI for the interface. Bundle its built
  assets with the Python application; use no CDN, remote fonts or runtime Node
  process.
- Keep Python responsible for workflow, local HTTP service, SQLite, managed
  images and recognition. Serve the UI and API on loopback only.
- Use browser camera APIs for capture and support user-selected PNG/JPEG files
  as an alternative. Request video only; do not request microphone access.
- Protect the local service with a per-launch token, exact loopback Host and
  Origin checks, and no CORS. This is a single-user local app, not a network
  deployment target.
- Keep draft saving separate from explicit approval. Support retake, local
  recognition, review, deletion, legacy-card reassignment and reviewed-event
  CSV export.

## Consequences

- A compatible desktop browser is required to use the app; camera capture also
  requires browser permission. Chromium on Linux is the tested example, not a
  claim of compatibility with every browser, device or operating system.
- Node/npm are required to build from source, but not to run a package with its
  bundled UI assets.
- The Python server must remain open while the browser UI is in use. Closing the
  tab releases the camera; Ctrl+C stops the server.
- Wettkampf metadata is immutable after creation. Older unclassified sessions
  are not assigned metadata automatically; users explicitly move their cards.
- The CSV format is versioned, but compatibility with any particular external
  meet-management program is not certified.

See [architecture](../architecture.md) for runtime and security details and
[CSV format](../csv-format.md) for the export contract.
