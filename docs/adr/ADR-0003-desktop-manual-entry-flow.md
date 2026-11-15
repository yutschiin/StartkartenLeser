# ADR-0003: File intake and manual review

- **Status:** Superseded for the main workflow by
  [ADR-0007](ADR-0007-local-browser-mui.md); file intake and manual fallback
  remain supported.
- **Date:** 2026-11-03

## Context

The initial vertical slice needed to validate card intake, durable local drafts,
manual transcription and recovery without depending on OCR quality.

## Decision

The first workflow was designed around one user-selected card image, a locally
stored draft, manual review and card-to-card navigation. Recognition was initially
represented by an unavailable stub; that implementation was replaced by local
DE·HTR v2 recognition under ADR-0005. The current workflow also supports browser
camera capture and is specified by ADR-0007.

## Consequences

- File selection remains an available alternative to camera capture.
- Recognition or alignment failure must leave the saved image and draft available
  for manual completion or retake.
- User-selected originals are not modified.
