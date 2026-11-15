# ADR-0001: Python application and local data

- **Status:** Accepted for the Python domain, persistence and recognition layers;
  the Tkinter UI decision is superseded by [ADR-0007](ADR-0007-local-browser-mui.md).
- **Date:** 2026-11-03

## Context

The application needs local persistence, image handling and replaceable local
handwriting recognition without a hosted service. Python and SQLite provide the
application core; a UI can be changed without moving data or recognition into a
remote service.

## Decision

- Use Python 3.11+ for the application and SQLite for structured local data.
- Keep card images in application-managed local storage and retain the original
  user-selected files unchanged.
- Keep recognition behind a local, replaceable interface. DE·HTR v2 is the
  selected initial recognizer; see [ADR-0005](ADR-0005-ocr-engine-evaluation.md).
- Use the local browser UI described in ADR-0007. Tkinter is not a runtime
  requirement.

## Consequences

- UI changes do not require replacing domain rules, persistence, or recognition.
- The application has no hosted runtime dependency. Setup may access package
  registries and fetch pinned model assets when bundled files are unavailable.
- Linux/Python 3.14 is the verified environment; package metadata permits Python
  3.11+, but other versions and operating systems are not currently claimed as
  tested.
