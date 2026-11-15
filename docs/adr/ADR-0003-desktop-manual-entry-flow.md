# ADR-0003: Desktop image-import and manual-entry vertical slice

- **Status:** Superseded for implementation scope by ADR-0005; import and manual-fallback decisions remain
- **Date:** 2026-11-03

## Context

Local handwriting recognition needs a feasibility evaluation using representative completed cards. The MVP validates image intake, the German digital twin/manual form, persistence, and card-to-card navigation with explicit file import. Webcam capture is a separate, requested next input milestone: it will become the primary source while file import remains available as the secondary source.

## Decision

The first desktop vertical slice was planned to follow the production import and review route, but without OCR-assisted field filling:

1. Select one Startkarte photo or scan using a desktop file picker and preview it.
2. Allow the user to choose another file or **Use image**.
3. On **Use image**, copy the image into application-managed storage, persist a draft, and invoke the `HandwritingRecognizer` interface.
4. Have the default stub return a controlled “recognition unavailable” result.
5. Show a compact manual-review form without displaying the source image; the physical card is the reference.
6. Save the manually completed card as `REVIEWED`.
7. Offer **Nächste Karte** to repeat the workflow in the same session.

The stub must not imply that OCR ran or that any value was recognized. Preserve the copied image and draft on failure. The MVP uses file import; the planned webcam-first milestone will use a separate input adapter and share the same acceptance/persistence pipeline, with file import retained as fallback.

## Consequences

- The first prototype can validate import, preview, recognition-failure handling, manual correction, persistence, and navigation independently of OCR quality or camera hardware.
- The application reads only the file explicitly selected by the user and leaves the original file unchanged.
- Manually entered values are marked as manual, not OCR-derived.
- The review model can accept OCR candidates later without silently replacing user-entered values.
