# Wettkampf metadata as recognition reference

## Feature

For a classified Wettkampf, distance, stroke and gender are the reference for
card entry. For example, a 100 m Brust / männlich event supplies `100`, `Brust`
and the male checkbox selection regardless of the values detected on paper.
The user may subsequently correct these values manually.

- New cards start with the event's values, before OCR.
- Every OCR run restores those three values from the event. Other fields keep
  their existing recognition/manual-edit behavior.
- OCR still reads these areas for comparison, without replacing the reference
  with its findings. Raw evidence must remain available.
- Equivalent representations count as matches (e.g. `100 m` and `100`,
  `B` and `Brust`, `R` and `Rücken`).
- A different, missing, unreadable or ambiguous result produces a warning beside
  the affected distance/stroke input or gender group, not a callout.
- An accessible warning icon and tooltip explain the expected event value and
  the card reading (or that it could not be read).
- Focus alone does not dismiss a warning. Blur dismisses only that field/group's
  warning, even if its value was not edited. Moving between the two gender radio
  buttons is not leaving the group.
- Acknowledgements survive ordinary saves/rerenders and reopening in the same
  browser session. Only a new OCR run creates fresh warnings for that card.
- Moving a card uses its destination event as the reference on the next OCR run.
- Unclassified legacy sessions retain their current behavior.
- Reopening uses persisted form values, including manual corrections. The existing
  CSV format remains unchanged: distance and stroke columns describe the event.

## Implementation plan

1. Backend: reuse domain normalization and stored OCR evidence where possible.
   Seed reference values on capture; after OCR persist event values and expose
   comparison evidence without discarding the original candidates. Add an
   optional `reference_check` response object:
   `{run_id: string, warnings: {course?, position?, gender?}}`.
   Each warning is `{expected: string, detected: string | null}`.
   `run_id` changes on every completed OCR attempt, including partial results.
   Warnings describe actual OCR results, not the substituted event values.
2. Frontend (after backend): type the response; render warning tooltips inline.
   Track acknowledgement by card ID, run ID and field in session storage.
   Dismiss on blur only, retaining the existing select-all, save and radio UX.
   No snackbar is needed for an individual field comparison.
3. Validation: backend tests for capture defaults, matching aliases, mismatches,
   missing/ambiguous readings, repeated OCR, persistence and legacy behavior.
   Frontend tests for authoritative values, tooltip details, focus/blur,
   gender-group blur, ordinary saves/reopening, and warning reset on fresh OCR.
   Run Python tests, frontend typecheck/tests and production build.

## Delegation

Backend and frontend tasks are sequential because they share the recognition
contract. Each implementation task owns its code and regression tests; the
coordinator maintains this plan and performs final integration validation.
