# ADR-0004: Form-first review layout

- **Status:** Superseded in part by the updated review requirement in [PRD FR-15](../prd.md#6-functional-requirements)
- **Date:** 2026-11-03

## Context

The user expects to have the physical Startkarte available while entering or validating values. Showing the imported image alongside the form consumes screen space and is not required for the primary review workflow. The copied image remains needed for local recognition and retention.

## Decision

- Keep a private copy of the imported card image with the card record.
- Earlier decision: do not display the source image on the review/data-entry screen. This image-visibility decision is superseded by the updated product requirement to show the source beside the form with labeled crop overlays; the printed field order and desktop usability guidance below remain applicable.
- Match the printed card's order: `Name` and `Vorname` on separate lines, then `Jahrgang`, then the `Mädchen` and `Junge` checkboxes on one line; pair `Strecke`/`Lage` and `Lauf`/`Bahn`; put `erzielte Zeit` and `Zeitnehmer` on separate lines.
- Keep controls compact, use standard resizable Tkinter/ttk widgets, support keyboard traversal and scrolling for smaller windows, and keep save/next actions easy to reach.
- Do not force mobile-specific dimensions or icon-only actions. Use clear desktop labels and standard buttons/menus.

## Consequences

- The form remains focused and usable without a webcam or split-image layout.
- Users are expected to retain access to the physical card during review. A separate image viewer may be considered later if user testing shows that assumption does not hold.
- The layout should adapt to window resizing and platform-native widget metrics without changing field order or semantics.
