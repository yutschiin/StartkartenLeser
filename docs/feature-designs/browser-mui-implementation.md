# Browser/MUI takeover plan

Status: implemented on `epic/keyboard-first-wettkampf-workflow`.

The successful browser camera spike is preserved on
`spike/local-browser-workflow`; the Qt spike remains independent. Neither test
database is migrated into application storage.

## Implementation sequence

1. Replace the Tk entry point with a loopback-only Python HTTP service. Retain
   the existing managed images, SQLite database, real local OCR, corrections,
   provenance, revision checks and retryable deletion.
2. Add explicit Wettkampf metadata without guessing metadata for old sessions.
   Keep legacy batches readable; let users explicitly assign cards to a newly
   created Wettkampf. Add transactional draft saves, same-card retakes and
   idempotent capture requests. Autosave is never approval.
3. Implement an offline React/TypeScript frontend using actual Material UI
   components. Keep the approved keyboard order, independent tri-state marks,
   debounced/blur autosave, explicit approval, retake/cancel, camera/file input,
   reopening/deletion and original-image review.
4. Run real local recognition automatically once after each capture or retake
   (and on demand via the header action), with visible errors and manual
   fallback. Never present invented OCR. While recognition runs, a status
   notice is shown and entry is locked; input becomes available when it ends.
   Detection areas are shown by default; the header toggle shows on/off.
5. Export a fully reviewed, nonempty Wettkampf as UTF-8 semicolon CSV, with
   explicit headers, canonical numeric values where parseable, independent
   gender marks and spreadsheet formula protection. Block incomplete exports.
6. Bundle built assets in the Python package; remove the Tk setup requirement.
   Document development/build/run and the local-server lifetime.
7. Verify repository persistence/migration and HTTP boundaries with Python
   tests, frontend type/build and keyboard tests, then exercise the complete UI
   with the real browser/camera. Record remaining limitations honestly.

## Transport contract

All API and image requests require `X-App-Token` from the launch URL fragment.
Mutations additionally require the exact loopback Origin. No CORS, remote
assets, microphone or remote recognition. JSON errors have `error` (catalog
key) and `message` (localized explanation); conflicts use HTTP 409.

- `GET /api/bootstrap`: `{sessions, texts}` (the German backend catalog).
- `POST /api/sessions`: `{number, distance_m, stroke, gender}`.
- `GET /api/sessions/{id}`: `{session, cards}`.
- `DELETE /api/sessions/{id}`.
- `GET /api/sessions/{id}/export`: UTF-8 CSV of reviewed cards.
- `POST /api/capture`: `{session_id, request_id, image}` (JPEG/PNG data URL),
  optionally `{replace_card_id, revision}` for a confirmed retake.
- `GET /api/cards/{id}`: card detail.
- `GET /api/cards/{id}/image`: original image.
- `GET /api/cards/{id}/card-image`: image shown in review. Accepted alignments
  return the rectified card (cropped to the card edges and upright, A6: 1050×1480);
  otherwise the original image.
- `GET /api/cards/{id}/overlays`: `{width,height,aligned,overlays,error_key}` in the
  coordinates of `card-image` (`aligned: true` means rectified card coordinates);
  unsafe alignment returns no boxes. The display alignment is cached per image
  reference, so a retake recalculates it.
- `PATCH /api/cards/{id}`: `{revision, fields: {key: string},
  checkboxes: {key: "unknown"|"checked"|"unchecked"}}`; partial changes.
- `POST /api/cards/{id}/approve`: `{revision}`.
- `POST /api/cards/{id}/recognize`: `{revision}`; real OCR; response adds
  `recognition: {status, error_key}` and optional
  `reference_check: {run_id, warnings}`. The request may take time.
- `POST /api/cards/{id}/move`: `{revision, session_id}`; explicit reassignment.
- `DELETE /api/cards/{id}`.

Session JSON: `id, title, created_at, revision, number, distance_m, stroke,
gender`. Null metadata means an unclassified legacy batch (readable, no new
capture/export). Initial categories are `female`, `male`; strokes are `freistil`,
`brust`, `ruecken`, `schmetterling`, `lagen`. No arbitrary distance whitelist.

Card detail: `id, session_id, sequence, state, revision, fields, checkboxes,
shared_candidates`; field/mark records retain their existing domain attributes
(`value`, `state`, `provenance`, `confirmed`, raw text etc.). List cards include
the same shape. Optional `reference_check` is
`{run_id: string, warnings: {course?, position?, gender?}}`; each warning is
`{expected: string, detected: string|null}`. Capture and mutation responses
return card detail directly.

## Recognition reference warnings

The Wettkampf distance, stroke and gender are authoritative on capture and after
each OCR run. OCR comparison evidence remains separate: course and position
warnings are shown beside their inputs, and gender warnings beside the radio
group. Each has an accessible warning tooltip with expected and detected values
(or “nicht lesbar”); the fields are not marked invalid and no per-field
notification is raised. Focus alone does not dismiss a warning. Leaving a
field, or leaving the whole gender group, acknowledges it in session storage
keyed by card, OCR run and field. A new OCR run has a new run ID and therefore
shows fresh warnings; ordinary saves and reopening in the same browser session
do not restore acknowledged warnings.

## Scope decisions

Keep internal `Session` names/database relationships compatible; the UI calls
classified records Wettkampf. Metadata is immutable in this first takeover,
so approved cards cannot silently change event context. Explicit reassignment
invalidates approval. Inline OCR reference warnings are shown as described
above; no mixed-category inference, ranking, cloud service or synthetic OCR is
added.

The old manual corner editor is not reproduced: failed alignment explicitly
falls back to manual entry or retake. Original images and raw OCR remain
available. This limitation must remain visible in user documentation.

## Shared page layout

All views use a sticky header with one page-title heading, informational chips
and page actions. Only the overview shows the SL brand. Back navigation lives in
a separate sub-header, above the main content. Header actions wrap on small screens.
The overview contains clickable Wettkampf rows with known card counts; creation
uses a header action and modal metadata form. Wettkampf cards are detail tiles
with separate delete/reassignment actions. Review keeps Retake and approval in
the form to preserve keyboard-first focus order.

## Notifications

The app has no inline callouts: every message is a snackbar. Ongoing state
(OCR running, card being saved) is shown as an overlay on the card image
instead. `useNotify()` returns `notify(severity, message, { timeoutMs?, key?,
action? })` plus `notify.dismiss(key)`; messages are localized by the caller.
Defaults are 5 s for success/info, 8 s for warning and 10 s for error.
`timeoutMs: null` keeps a message until it is closed, dismissed by `key` or its
`action` button is used; this is used for errors that need a decision (retry a
failed save, recover from a stale session). Messages that describe a condition
(legacy Wettkampf, capture warning, overlay warning) are raised with a `key`
and dismissed when the condition ends.

A single snackbar appears at the bottom right, offset on small screens to avoid
the review action row; queued messages are shown one at a time and a message
with an already queued `key` replaces it. It can be dismissed with the close
button and pauses while hovered or focused. Success/info use `role="status"`
with polite announcements; warning/error use `role="alert"` with assertive
announcements.

## CSV v1

Nonempty and fully reviewed Wettkämpfe only; drafts block export instead of being
silently omitted. Browser download uses UTF-8 BOM, semicolons, standard CSV
quoting and CRLF. Rows are in card-sequence order. Stable exact column order:

```text
csv_version;wettkampf_id;wettkampf_number;distance_m;stroke_key;gender_key;card_id;sequence;name;first_name;year_text;heat;heat_text;lane;lane_text;time_ms;time_text;timekeeper;female_mark;male_mark
```

`csv_version` is `1`. Canonical heat/lane/time cells are empty when parsing is
ambiguous or invalid, not zero. Reviewed raw text remains in the adjacent text
columns. Independent mark values are `unknown`, `checked`, `unchecked`; category
is never inferred from them. OCR evidence and private image paths are not
exported. Text beginning with a formula trigger (including after whitespace) or
tab/CR/LF gets an apostrophe in the exported representation only.

The download does not modify review states. The browser manages destination,
cancellation and overwrite prompts; the app makes no atomic-filesystem-write
claim for browser-managed downloads. No external consumer compatibility has
been certified.

## Verification results

- Python: 287 passing tests, including HTTP boundaries, v1 migration/snapshot,
  draft-versus-approval, transactional retake rollback, idempotency, concurrent
  OCR/edit conflicts, legacy reassignment, deletion and exact CSV shape.
- Frontend: strict TypeScript check and 21 passing tests, including native-fetch
  receiver binding, focus, autosave retention/retry, and retake/cancel state.
- Production build: local bundled JS/CSS and generated runtime dependency license
  notices. Clean sdist-to-wheel build includes UI assets and excludes the old Tk
  module; verify installed artifacts outside the editable checkout.
- Integrated browser, real Razer Kiyo: 1920×1080 video, zero audio tracks.
  Twenty consecutive capture/edit/approve cycles completed using only keyboard
  actions after setup. Stored names, year, heat, lane, time, timekeeper, mark,
  approvals, distinct IDs and sequences were verified, not just screen changes.
- Retake: cancellation retained the latest autosaved values and focus.
  Successful replacement retained ID/sequence, changed the image reference,
  and reset fields only after persistence. Leaving capture ended the real video
  track.
- Save failure injection: form input survived; attempted navigation stayed in
  review; retry saved successfully and reload restored the value.
- Denied camera permission produced an explicit error and disabled capture;
  selecting a synthetic PNG still saved a new reviewable card through the file
  fallback.
- 200% root text-size traversal retained the complete routine field order,
  including independent Mädchen/Junge controls.
- CSV: UI export created the intended filename and 24 persisted-card rows plus
  the exact header. Blob content and download initiation were verified; the
  integrated browser did not expose a native download-completion event, so
  destination/overwrite handling is not certified by that check.
- Explicit real recognition on a non-card capture reported unsafe alignment,
  retained human input and allowed manual completion. This verifies recovery,
  not handwriting accuracy.
- A packaged-wheel server launched outside the checkout reopened the same
  database after process restart: all twenty keyboard-loop cards retained their
  values and reviewed states. A new per-launch token was required as designed.
- Opening a new launch-token fragment in an already-mounted tab reauthenticates
  without a hard reload. Unsaved input blocks that reset with an explicit
  instruction to save/copy it first, rather than silently discarding edits.

Remaining limits: Linux/browser/device evidence is not cross-platform camera
certification. Consumer-specific CSV mapping, editable event metadata,
mixed/open categories, mismatch warnings and manual corner adjustment remain
outside this takeover. The build reports a bundle-size advisory; all runtime
assets remain local.
