# ADR-0001: Python desktop baseline

- **Status:** Python/storage/recognition accepted; Tk UI superseded by [ADR-0007](ADR-0007-local-browser-mui.md)
- **Date:** 2026-11-03

## Context

StartkartenLeser Desktop needs a cross-platform desktop UI, local persistence, image intake, and a path to local handwriting recognition. The first release should stay simple to run and should not require a web service or remote infrastructure.

## Decision

- Use **Python 3.11 or newer** as the runtime baseline.
- Use **Tkinter/ttk** for the native desktop UI and standard file dialogs for explicit image selection.
- Use Python's **SQLite (`sqlite3`)** support for structured local data and app-managed files for image copies.
- Keep recognition behind a provider-neutral local interface. DE·HTR v2 is the selected initial desktop MVP adapter; retain the unavailable stub as manual fallback and a deterministic test double. See [ADR-0005](ADR-0005-ocr-engine-evaluation.md).
- Keep optional runtime dependencies limited and document them before adding them. Python distributions must include Tk support.

## Consequences

- The first implementation can be developed and tested using standard Python desktop tooling without a server.
- Python installations without Tk support are unsupported; packaging must bundle or clearly document the required runtime/Tk components.
- Supported operating systems and packaging/distribution strategy remain to be confirmed before release.
- Local storage location and operating-system backup behavior must be documented for each supported OS.
