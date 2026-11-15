# MVP Feature Design — Local Startkarte Digitization

- **Status:** Historical file-import MVP proposal; superseded by the implemented
  [Wettkampf/browser workflow](keyboard-first-wettkampf-epic.md). Retained for
  design history; do not treat its Tkinter implementation steps as current work.
- **Target for first implementation:** Ubuntu/Linux x86_64 desktop, Python/Tkinter
- **Parity reference:** Android sibling pre-MVP session/card workflow, adapted to desktop file import
- **OCR decision:** [ADR-0005](../adr/ADR-0005-ocr-engine-evaluation.md)

The successor is the [Wettkampf and keyboard-first workflow](keyboard-first-wettkampf-epic.md),
which extends this session/file-import MVP with event metadata, camera capture,
keyboard-first review and CSV export, and selects the local browser UI.

## 1. Goal and product promise

Digitize a session of paper Startkarten using a local desktop app. A user imports one card image at a time, sees OCR-produced candidate values in an editable German form, checks every value against the physical card, saves the reviewed card, and continues. Sessions, imported images, candidates, and corrections remain on the computer.

OCR assists transcription; it does not certify values. Every card and every proposed value remains subject to human review. The selected engine has not yet been evaluated on representative Startkarten, so the app must not claim a Startkarten accuracy rate.

## 2. Selected local recognition engine

Use **DE·HTR v2** (`naeyn/de-htr-web-v2`) for modern German handwriting, via its int8 ONNX artifact and **ONNX Runtime CPU**. The recognizer accepts a single pre-cropped text line, not a whole card. Its model card reports 8.01% CER / 32.3% WER on a writer-disjoint external set of 601 German handwriting lines; this is useful evidence of feasibility, not a prediction of Startkarten performance.

The engine fits this laptop's current environment: Intel Core i7-12700H (14 cores / 20 threads), 62 GiB RAM, Ubuntu 26.04 x86_64, Python 3.14, and GeForce RTX 3050 Ti Mobile. The ONNX model is about 10.4 MB and does not require CUDA. ONNX Runtime publishes a Linux x86_64 CPython 3.14 CPU wheel. Use CPU inference as the MVP default to avoid CUDA setup; OCR runs on a worker thread, never the Tk event loop. Measure actual end-to-end latency before considering optional GPU acceleration.

### Model and runtime handling

- Pin model version 2 / source release `v0.2.0`, `config.json`, and their SHA-256 values from the model card. The selected int8 `model.onnx` SHA-256 is `b576a0a1281b9be46b2574028b75575e041b7d7cb650f063886e733467cc1499`; `config.json` SHA-256 is `4ebd69d9d27b398ea3997b031318accc13123f6a8950def1fedc6e364cb758fa`.
- Bundle the pinned model and config with the desktop distribution (about 10.4 MB) so first launch and recognition work offline. Do not download models on demand or send card data to a service.
- Include model, dataset-attribution, ONNX Runtime, and image-library notices in distribution. The model card identifies the model release as Apache-2.0 for rights held by the project and attributes CC BY 4.0 and AFL-3.0 training data; preserve required notices and verify redistribution terms before packaging.
- Keep model-specific preprocessing, the alphabet, CTC decoding, and ONNX Runtime types inside a replaceable recognition adapter. No Paddle, PyTorch, Transformers, or CUDA dependency is needed for inference.

## 3. MVP scope

### Included

- Session list/create/open/delete and session detail with ordered cards and review status.
- Explicit one-image-at-a-time PNG/JPEG import through the native file picker; preview, replace, rotate/align, accept, or cancel.
- Card boundary/orientation normalization and canonical template alignment, with a guided manual corner-adjustment fallback when automatic alignment is uncertain.
- Versioned field crops from the normalized card. DE·HTR runs on line crops for text fields; a separate template-specific mark detector proposes the two gender-checkbox states.
- Local recognition after durable draft/image persistence; progress, partial results, unavailable/failure states, retry, and manual fallback.
- Editable German review form for all ten fields, provenance/review status, time parsing and formatting, and explicit save/next actions.
- Every application-owned UI string is resolved from locale catalogs; German is the initial locale.
- SQLite persistence, app-managed image storage, restart recovery, individual card/session deletion, keyboard access, resizable/scrollable layout, and accessible textual status.
- Field-level OCR evaluation on permission-cleared, representative completed cards before making quality claims.

### Excluded

- Automatic acceptance or silent completion of a card; cloud/remote OCR, uploads, analytics, accounts, sync, export, or sharing.
- Multi-card-per-image import, arbitrary templates, bulk correction, model training/fine-tuning, or user-facing engine selection. Webcam capture is deferred from this MVP but is a committed next input milestone, not an optional feature.
- App-managed encryption at rest. Document that local data relies on OS account/device protection and may be included in user-managed backups.

### Planned next input milestone (after the MVP)

Add webcam capture as the primary/default card-image source. Keep the existing file picker as the secondary source for scans, phone photos, and previously captured images. Both sources must feed the same alignment, preview, durable-draft, and recognition pipeline so camera support does not fork card processing or persistence. Request camera access only after the user starts capture; if no camera is available or capture fails, offer the file picker as the fallback. Webcam hardware integration is intentionally scheduled after the import-based MVP and its unit/integration gates.

## 4. End-to-end user journey

### A. Sitzungen

- List sessions newest-first with generated German title, date, and a concise card/review count.
- **Neue Sitzung** creates a dated session and opens it. User-defined names are deferred.
- Empty state offers a direct path to import the first Startkarte. Delete requires confirmation and explains that all cards, images, and values are removed.

### B. Sitzung detail

- Show session title, a prominent **Startkarte importieren** action, and cards in ascending sequence order.
- Each card row shows its number and textual state: **Erkennung läuft**, **Prüfung ausstehend**, or **Geprüft**. Never rely on color alone.
- Opening a card restores its persisted image reference, candidates, manual edits, and review state. Card deletion requires confirmation.
- **Nächste Karte** adds the next sequence number to the same session and starts image selection; it never creates another session.

### C. Bild auswählen und ausrichten

1. Use a native file picker for PNG/JPEG and read only the explicitly selected image. Preserve the original unchanged.
2. Show filename and bounded preview. Allow selecting another file, canceling, or accepting. Do not create a card until acceptance.
3. Before OCR, normalize EXIF orientation and identify a versioned layout. For new A6 cards, detect the unique ArUco corner markers (on a white-padded copy, so markers touching the photo edge are still found), fit a homography from all marker corners of at least three markers to their printed positions, and warp to the exact card (1050×1480, upright regardless of camera rotation); fewer than three markers or a reprojection error above 12 px requires manual adjustment. For legacy cards, retain the legacy boundary/heading fallback. Then show the rectified card, with detection areas in card coordinates, instead of the raw photo.
4. If automatic alignment cannot meet its geometric checks, let the user adjust four card corners and confirm. If alignment still fails, preserve the image and route to manual entry with OCR marked unavailable; do not use guessed crop coordinates.
5. On **Bild verwenden**, privately copy the original, save the `CAPTURED` card draft and schema version, and only then queue recognition. Failure to copy or persist blocks OCR and shows a retryable error.

### D. Lokale Erkennung

- Align the accepted card to canonical template coordinates and crop the configured handwritten regions with safe margins. Keep crop definitions versioned with the field schema.
- Run DE·HTR v2 on each supported text line, with batch size one or a small bounded batch. Use the model's exact grayscale input contract: height 64, aspect ratio preserved, width capped at 1024, white padding to a multiple of four, float values in `[0,1]`, then greedy CTC decoding using the bundled v2 alphabet.
- Recognize `Name`, `Vorname`, `Jahrgang`, `Lauf`, `Bahn`, `erzielte Zeit`, and `Zeitnehmer` as text candidates. For the new A6 layout, recognize `Strecke` and `Lage` from separate crops; retain the combined `Strecke, Lage` candidate only for legacy layouts. Do not treat model confidence as calibrated certainty; v2's published interface provides transcription logits but no validated per-field confidence calibration. Initially mark every OCR result **Vorschlag — bitte prüfen**.
- Process `Mädchen` and `Junge` checkboxes separately using aligned box regions and a conservative mark detector. Keep checked, unchecked, and unreadable/unknown independently representable. Low-quality/ambiguous states remain unknown; never infer a mark from missing text OCR.
- Preserve the combined legacy `Strecke, Lage` line as a shared raw candidate until the allowed values, aliases, and separation rules are supplied. Do not invent dropdown options or silently split/nearest-match a legacy value. The A6 design's separate fields map directly to `Strecke` and `Lage`.
- For the current line-based A6 layout (`card-layout-a6-v2`), crop nine handwriting regions after their inline labels, including one continuous time line. Crop the interiors of the two gender checkboxes separately. Exclude printed labels and writing rules from the OCR regions; skip regions with no detected handwriting. The former boxed A6 layout is deprecated and is no longer selected automatically.
- Validate `Jahrgang`, `Lauf`, and `Bahn` without silently changing candidates. Preserve the original time transcription; parse the explicit A6 `min`/`sek`/fraction notation and legacy supported notations to milliseconds. Ambiguous or invalid input is flagged for user correction.
- Persist mapped candidates and provenance (`OCR`) atomically, set card state to `NEEDS_REVIEW`, and open the review form. On no lines, alignment failure, model failure, or cancellation, preserve the durable draft and offer manual entry.

### E. Prüfen und speichern

- Show the rectified card (or the source image when alignment is not accepted) beside the review form with labeled crop overlays; the paper Startkarte remains the reference. Show a short German recognition status and make OCR suggestions visibly distinct from manual/user-edited values with text, not color alone.
- Keep printed field order and grouping:

  1. `Name`, then `Vorname` on separate rows.
  2. `Jahrgang`.
  3. independent `Mädchen` / `Junge` checkboxes on one row.
  4. `Strecke` / `Lage` on one row.
  5. `Lauf` / `Bahn` on one row.
  6. `erzielte Zeit`.
  7. `Zeitnehmer`.

- Use compact, native, resizable controls. Support keyboard traversal in field order, visible focus, screen magnification, text scaling, and scrolling when needed. Keep **Speichern**, **Speichern und nächste Karte**, and **Zur Sitzung** reachable and text-labeled.
- All fields are optional; an unreadable or blank value does not prevent save. Editing an OCR candidate changes provenance to `USER_EDITED`; filling a blank field manually records `MANUAL`. Unedited OCR candidates remain `OCR` until the user explicitly confirms them.
- Persist draft edits as work proceeds and flush before navigation/close. Show saved/unsaved state. Do not clear form state on errors or while saving.
- **Speichern** records `REVIEWED` only after a successful explicit save/confirmation of all current values, then returns to session detail. **Speichern und nächste Karte** does the same and starts the next import in the same session.
- Show a normalized time below the entered value only for supported unambiguous forms, using German formatting and nonbreaking spaces. Otherwise preserve the text and show **Zeitformat unklar — bitte prüfen**.

### F. Retry, resume, and deletion

- Retry is explicit. Never overwrite `USER_EDITED`, `MANUAL`, or already-confirmed fields. New recognition may fill blanks; replacing an existing candidate requires a clear confirmation and retains the prior value until accepted.
- On startup, transition interrupted `RECOGNIZING` cards to `NEEDS_REVIEW`; restore incomplete forms for manual completion or retry.
- Delete confirmation explains impact. Remove associated DB rows and managed image files; do not claim success if filesystem cleanup fails. Make cleanup retryable/idempotent.
- Explain local retention and how to delete one card, a session, or all application data. Retain until user deletion; no automatic expiration.

## 5. Major software components

```text
Tk/ttk screens and presenters
  ├─ Sessions / session detail
  ├─ Image select / align / preview
  └─ Candidate review form
           │
Application use cases and ports
  ├─ Create/list/delete session; list/open/delete card
  ├─ Accept image; normalize; recognize; save draft/review
  └─ Local ports: repositories, image store, aligner, recognizer
           │
Infrastructure
  ├─ SQLite + migrations          ├─ private image store
  ├─ template alignment/crops     ├─ checkbox mark detector
  └─ DE·HTR v2 ONNX Runtime CPU adapter (replaceable)
```

- **Domain:** versioned card schema, typed session/card/field values, source/status transitions, checkbox states, validation, and time normalization. No UI, SQLite, Pillow/OpenCV, or ONNX imports.
- **Localization:** keyed catalogs in `locales/<locale>.json`, loaded through a `TextCatalog` service. Keep user-visible wording out of Python view/controller code and out of domain models. Field definitions store stable localization keys, not display strings. German (`de`) is the default catalog; additional locales add catalogs without changing feature code.
- **Application:** use cases coordinate storage, alignment, recognition, candidate mapping, review, retry, next-card, and deletion. Depend on narrow repository/image/aligner/recognizer ports.
- **Image intake:** Pillow handles safe decode, EXIF orientation, preview, and supported PNG/JPEG formats. A focused alignment adapter (OpenCV or an equivalent justified library) returns a canonical card transform plus an alignment quality result; manual corner adjustment is the fallback.
- **Recognition adapter:** owns pinned model/config loading, ONNX session lifecycle, preprocessing, CTC decode, and candidate result mapping. Initialize once; use bounded CPU threads. It accepts a field-line crop and returns text/status/provenance, never a definitive value.
- **Checkbox adapter:** separate geometry/mark logic from handwriting recognition; return checked/unchecked/unknown candidates with conservative thresholds.
- **Persistence:** SQLite stores sessions, ordered cards, values, schema/model version, provenance, review status, raw transcription, and canonical time. Store the original image in app-specific local storage. Do not persist temporary crops or raw model tensors by default.
- **UI:** presenters coordinate use cases and German feedback; views never access SQL/files/model APIs. All Tk operations run on the main thread. Decode, alignment, inference, and disk I/O run on workers; marshal results back through `root.after`.
- **Composition root:** `app.py` wires the selected engine and adapters, model path, database, worker, and Tk lifecycle. Keep provider choice out of feature/domain code and avoid a general DI framework.

Filesystem and SQLite are not one atomic transaction. Copy to a temporary managed image, finalize the copy, persist the card in a DB transaction, and clean up on failure. Persist the draft before starting inference. Recognition result writes must be atomic and edit-safe. Deletion uses an idempotent cleanup process so partial failures can be retried.

## 6. Data and recognition state

- Card lifecycle: `CAPTURED` → `ALIGNING` → `RECOGNIZING` → `NEEDS_REVIEW` → `REVIEWED`; alignment/model failures recover to `NEEDS_REVIEW` with explicit messages. `REVIEWED` always means a person explicitly saved the values.
- Each field value stores stable key, typed/canonical value where supported, original transcription, source (`OCR`, `USER_EDITED`, `MANUAL`), nullable confidence, review status (`CANDIDATE`, `LOW_CONFIDENCE`, `INVALID`, `MISSING`, `CONFIRMED`), and optional source region.
- Do not invent missing fields as empty strings in a way that suggests a negative answer. Preserve unknown checkbox marks and unresolved shared-line candidates.
- Recognition retry and save must not race. Serialize writes per card or use optimistic revision checks so delayed inference cannot overwrite edits.
- Store current model and crop/schema version with recognition results for diagnosability and future migrations.

## 7. Privacy, security, and accessibility

- Recognition is offline. The model is bundled; inference must work with networking disabled. No card images, crops, handwriting, extracted text, or personal data are transmitted or logged.
- Only read user-selected files. Keep originals unchanged; keep managed copies in application-specific storage. Do not put absolute paths or card text in error telemetry.
- Limit image dimensions/file size before decode; avoid unbounded allocations and use temporary buffers safely. Delete temporary crops after recognition.
- Use visible focus, keyboard navigation, sensible tab order, scalable text, status words/icons in addition to color, and reachable actions in small/resized windows.

## 8. Localization and internationalization

- All application-owned visible strings must live in locale resource files, not inline in Python. This includes window/screen titles, labels, buttons, menus, help text, empty/loading/success states, validation and error messages, confirmation dialogs, OCR/review statuses, tooltips, and accessibility names/descriptions.
- Use stable keys such as `session.create`, `field.name`, `status.needs_review`, `error.image_unreadable`, and `accessibility.delete_card`. UI code calls the catalog service with a key and parameters; it must not provide a literal-text fallback.
- Ship `locales/de.json` for the first German UI. Define the catalog shape to support additional locale files, parameter placeholders, and plural forms. Validate at startup/test time that every referenced key exists and that catalogs have compatible placeholders. A missing key is a development/test error and must never display the raw key to users.
- Domain/schema data stores stable field/status identifiers and localization keys, never translated labels. Persisted enum values, database keys, OCR output, and user-entered content remain language-neutral/original; only their presentation is localized.
- Use locale-aware formatting for dates, numbers, and durations while keeping stored canonical values locale-independent. Transcribed handwriting and user-entered values are data, not UI copy, and must not be translated.
- Native OS-owned dialog chrome may follow the operating-system language; all application-provided dialog titles, file filters, and explanatory text still come from the selected catalog.

## 9. MVP acceptance and quality gates

### Functional acceptance

1. Create/reopen a session; import and align one image; choose another/cancel; accept and persist a draft before any recognition work.
2. Run the pinned DE·HTR v2 model locally on CPU without network access and return mapped candidates for its supported handwriting lines.
3. Preserve the original image and durable draft through alignment/OCR/model failures, cancellation, app restart, and manual fallback.
4. Show every configured field in the editable form, including unresolved shared `Strecke, Lage` and independent checkbox states. Never auto-accept candidates.
5. Save/reopen/edit cards, preserve source/provenance and time semantics, continue with the next ordered card, and delete cards/sessions with associated images.
6. Pass keyboard navigation, resizing/scrolling, text/status, and privacy checks on the initial Ubuntu/Linux x86_64 target.
7. All application-owned visible and accessibility text resolves from `locales/de.json`; automated checks find no missing keys, inline UI copy, or incompatible placeholders.

### OCR evaluation gate

- Before any quality claim, test with a permission-cleared labeled set of completed Startkarten, split by card and writer where feasible. Include diverse image quality, handwriting, field values, checkboxes, combined `Strecke/Lage`, and time formats.
- Report exact match/CER by text field; exact parsed validity for year/numeric/time; checkbox-state accuracy; joint `Strecke`+`Lage` exact match; unresolved/missing rate; and incorrect confident-looking outputs. Since confidence is not calibrated, treat all suggestions as needing review.
- Benchmark complete flow including alignment failure rate, model-load and per-card inference latency, peak memory, offline behavior, restart/retry behavior, and corruption/low-storage paths on this laptop.
- Set field-specific acceptance thresholds with the product owner after the benchmark. If a field misses its threshold, keep that field manual/unresolved; do not delay useful OCR for other fields or claim success based on an aggregate score.

## 10. Inputs still needed

- Permission-cleared completed card images and expected field transcriptions for alignment/crop validation and quality evaluation. The blank reference card alone is not enough to validate handwriting recognition.
- Allowed `Strecke` / `Lage` values, aliases, and how the combined printed line is normally written. Until supplied, retain raw text and require user assignment.
- Examples of how `Mädchen` / `Junge` marks are drawn, including blank, ambiguous, and both-checked cards, to validate the mark detector.
- Supported OS list beyond the current Ubuntu 26.04 laptop. Keep first implementation/acceptance focused on Linux x86_64; check ORT, Tk, image alignment, and packaging separately for other OSes.
- Confirm whether generated dated session names and all-optional card saves are acceptable MVP defaults.

## 11. Research references

- [DE·HTR v2 model card](https://huggingface.co/naeyn/de-htr-web-v2) — architecture, exact preprocessing, model hash, writer-disjoint German-line benchmark, limits, and attribution.
- [DE·HTR source/release](https://github.com/naeyn/de-htr-web) — implementation and reproducibility details.
- [ONNX Runtime Python installation and CPU provider](https://onnxruntime.ai/docs/get-started/with-python.html).
- [PaddleOCR PP-OCRv5 multilingual documentation](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.en.md) — considered alternative.
- [Kraken PyPI](https://pypi.org/project/kraken/) — considered HTR toolkit; current release does not support Python 3.14.
