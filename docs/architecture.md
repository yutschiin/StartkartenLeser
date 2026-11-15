# Architecture — StartkartenLeser

**Current UI:** Local browser, React/TypeScript and Material UI.
See [ADR-0007](adr/ADR-0007-local-browser-mui.md) and the
[takeover plan](feature-designs/browser-mui-implementation.md).

## Components

```text
Browser: bundled React/MUI application
  ├─ Wettkampf setup and overview
  ├─ getUserMedia camera / user-selected PNG or JPEG
  └─ Keyboard-first review, autosave, approval and CSV download
                  │ authenticated same-origin loopback HTTP
Python browser_server.py
                  │
browser_workflow.py: browser action orchestration
  ├─ Existing StartkartenUseCases: alignment, real OCR, corrections, approval
  ├─ SqliteRepositories: sessions/Wettkämpfe, cards and evidence
  └─ ManagedImageStore: validated originals and retryable cleanup
```

`app.py` composes the existing recognizer/aligner/repositories, binds the server
to `127.0.0.1` and opens the launch URL. The Python process serves built assets;
Node is build tooling, never a runtime server. The old Tk UI is removed.
Domain models remain free of browser, HTTP, SQLite and widget dependencies.

## Persistence and migration

The production data location remains
`$XDG_DATA_HOME/startkartenleser` or `~/.local/share/startkartenleser`.
`--data-dir` selects a different directory; spike data is never imported.
One process holds an OS lock per data directory.

SQLite schema v2 adds nullable Wettkampf metadata to existing sessions and a
capture-request deduplication table. Internal `Session`/`session_id` names remain
compatible. New Wettkämpfe require positive number/distance and explicit
stroke/category keys. Existing sessions retain null metadata and all original
membership/evidence. Users may split a mixed legacy batch by moving individual
cards into explicit Wettkämpfe.

Before upgrading an existing schema-v1 database, SQLite's backup API creates
`startkartenleser.before-v2.sqlite3` next to it. Migration is transactional;
future versions are rejected. An already-present backup blocks a retry rather
than overwriting the earlier snapshot. Preserve/move that backup before retrying.
To restore, stop every application instance, retain the current database and
images as a separate backup, restore the v1 snapshot into a separate data
directory with its corresponding images, and use the pre-migration application.
Database backup alone is not a full image backup.

Wettkampf metadata is initially immutable. Moving a card allocates its new
sequence transactionally and invalidates approval; IDs, image and provenance
survive. Numbering is not globally unique.

## Capture, drafts and recognition

Capture validates a bounded PNG/JPEG, durably copies it into private storage,
then commits the card and capture-request ID. Retrying the identical request
cannot create a second card. Retake retains the same ID/sequence, replaces the
image and clears evidence in one transaction; the old image remains until the
new reference commits, then deletion uses the durable outbox.

Draft PATCHes carry revisions and only changed fields. They never confirm
values. Editing a reviewed card revokes its review state. Frontend writes are
serialized; blur and approval flush queued edits. Errors retain dirty input and
prevent success-shaped advancement.

Real DE·HTR v2 recognition is an explicit action, not an automatic blocker
between capture and entry. `StartkartenUseCases` retains layout-specific
alignment/crops, conservative independent mark proposals, correction policy,
raw OCR, provenance and confidence. Missing models or unsafe alignment remain
visible manual-review cases. Manual/confirmed values are protected. Revision
changes discard obsolete recognition; recognizer access is serialized while
ordinary draft requests can proceed independently.

On restart, interrupted recognition returns to `needs_review`. Source images
and saved values remain available. Reloading the same browser origin restores
the selected card from session storage; a new random port starts at the overview,
where persisted Wettkämpfe and drafts can be reopened.
The original is displayed beside entry. The old corner-adjustment tool is not
ported; use manual transcription or retake when alignment is unsafe.

## HTTP and privacy boundary

The server accepts only the exact loopback Host. APIs/images require a random
per-launch `X-App-Token`. Mutations require the exact Origin, reads reject
foreign Origins, and no CORS is enabled. The fragment token is removed from the
address bar after session storage. Reloading an old tab after a server restart
requires the new launch URL.

Assets are local; CSP disallows remote resources and inline scripts. Inline
styles are allowed for MUI/Emotion. Microphone permission is disabled and camera
requests specify `audio: false`. Image/request sizes and decoding dimensions
are bounded. Static paths cannot escape the bundled directory.

There are no access logs containing tokens, image references or field values.
No hosted OCR, analytics or synchronization is used. Local storage and exported
CSV are not encrypted; OS account security, retention and backups remain the
user's responsibility. Deletion removes managed copies, not imported originals
or independently downloaded CSV.

## Build and verification

`frontend/` contains the npm lock, TypeScript source and frontend tests. The
Vite build writes `src/startkartenleser/web_static/`, included by Python package
data. Commit source and rebuilt assets together. Python dependencies remain
unchanged by the UI choice.

Backend tests cover authentication/origin/host checks, migration, capture
deduplication, retake rollback, autosave versus approval, stale revisions,
concurrent OCR edits, legacy moves, deletion and CSV. Existing domain/OCR tests
remain in place. Frontend type/build/tests and actual browser checks complement
them; no headless-only result is evidence of camera/device compatibility.
