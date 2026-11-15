# ADR-0004: Review the form beside its source image

- **Status:** Current layout is set by
  [ADR-0007](ADR-0007-local-browser-mui.md); the earlier form-only presentation
  is superseded.
- **Date:** 2026-11-03

## Context

OCR suggestions need to be checked against the handwriting on the physical card.
Keeping a stored image without showing it during review would make that check
less direct.

## Decision

- Show the card image beside the editable review form, with detected field regions
  overlaid when alignment is safe.
- Keep fields in card order: name, first name, year, gender selection, event
  number/course/stroke observations, heat and lane, time, and timekeeper.
- Keep the form keyboard-accessible and usable at different window sizes.
- Do not offer manual corner adjustment. When alignment is unsafe, show the
  source image and let the user transcribe manually or retake the image.

## Consequences

- Image and form share the review screen; the image is evidence, not an OCR
  guarantee.
- Unsafe alignment must not be used to pass guessed crops to recognition.
- The printed card remains the reference for every value.
