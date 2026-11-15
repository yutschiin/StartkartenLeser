# Architecture

## Runtime

```text
React/TypeScript + Material UI (bundled static files in the browser)
                           │ same-origin loopback HTTP
Python app.py → browser_server.py → browser_workflow.py
                                      ├─ application use cases
                                      ├─ SQLite repositories
                                      ├─ managed image storage
                                      └─ alignment, OCR and correction policy
```

The Python process serves the built frontend and owns application state. It
binds to `127.0.0.1` on a random port and opens the launch URL. Node/npm are
build-time tools only. The browser owns camera access and can also send a
user-selected PNG/JPEG image. The domain and application layers do not depend on
React, HTTP, SQLite, or browser APIs.

## Capture and review

The browser sends an image to the Python workflow. The backend validates and
stores a managed copy and creates a card before recognition. Capture requests
are idempotent so retries do not create duplicate cards. A retake replaces the
image on the same card only after the new image is committed; failed attempts
retain the old image and data.

Recognition uses layout-specific alignment/crops, the bundled DE·HTR v2 ONNX
model, a separate conservative checkbox detector, and a local correction policy.
Results are suggestions. Wettkampf metadata is authoritative; OCR comparisons
can produce visible mismatch warnings but do not change event metadata or
approve cards. Users can edit fields and marks, save drafts, and explicitly
approve. Editing an approved card returns it to review. Unsafe alignment or OCR
failure leaves the image and card available for manual entry or retake.

Frontend writes are revision-checked and serialized. Editing never means
approval; failed writes retain unsaved input rather than advancing. OCR access
is serialized, while regular draft edits remain available. On restart,
interrupted alignment/recognition returns to review.

## Data and migration

The production data directory is `$XDG_DATA_HOME/startkartenleser` or
`~/.local/share/startkartenleser`; `--data-dir` selects another directory. One
application process may hold a data directory at a time.

SQLite schema v3 stores sessions, cards, event metadata, fields, checkbox marks,
OCR evidence, capture-request IDs, reference comparisons, and pending image
deletions. The UI calls classified sessions **Wettkämpfe**; internal `Session`
names remain for compatibility. New capture and export require complete event
metadata. Old sessions are left unclassified rather than inferred from card
OCR; users can explicitly move their cards into a new Wettkampf.

Opening a schema-v1 database creates a SQLite backup beside it named
`startkartenleser.before-v2.sqlite3` before migration. Migration is transactional
and newer unsupported schemas are rejected. An existing snapshot blocks a
second migration attempt rather than being overwritten. Keep the database and
its images together in backups; a database-only backup cannot restore card
images.

Card movement preserves card IDs, images and evidence, allocates a new sequence
in the destination, and invalidates approval. Retake and deletion use retryable
managed-image cleanup. Deleting a card or Wettkampf removes app-managed copies,
not the user's original files or downloaded CSV exports.

## Local service and privacy boundary

The server accepts the exact loopback Host, uses a random per-launch token from
the URL fragment for API/image access, requires the exact Origin for mutations,
and enables no CORS. Static paths are confined to bundled assets. Content
Security Policy disallows remote resources and inline scripts; microphone access
is disabled. Input sizes and image decoding are bounded.

The application has no hosted OCR, analytics, synchronization, or remote card
storage. Model files may be fetched during setup if bundled copies are missing
or invalid; card images and text are never sent. Local files, SQLite, and CSV
exports are not encrypted. OS account access, backups, retention, and export
handling remain the user's responsibility.

## Build and verification

The frontend lives in `frontend/`; Vite writes production files to
`src/startkartenleser/web_static/`, which is included in Python distributions.
Keep frontend source, npm lockfile, generated static assets, and frontend
third-party notices in sync. A wheel build packages the checked-in assets and
does not run npm.

The Python tests cover persistence, migrations, image lifecycle, workflow,
recognition, HTTP security, and export. Frontend tests cover UI behavior,
keyboard navigation and draft saving. Browser/device testing is still needed to
verify camera access on a particular machine; automated tests do not establish
camera compatibility.
