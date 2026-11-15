# Desktop MVP Implementation Plan

> **Historical plan:** This describes the earlier Tk/file-import MVP and is not
> the current implementation plan. The browser/Wettkampf implementation in the
> [keyboard-first epic](feature-designs/keyboard-first-wettkampf-epic.md) and
> [browser/MUI takeover](feature-designs/browser-mui-implementation.md) supersedes
> it. It is retained for implementation history; see the README for current
> install, build, and test instructions.

- **Status:** Historical MVP plan; not current work in progress.
- **Feature design:** [MVP workflow](feature-designs/mvp-workflow.md)
- **Recognition decision:** [ADR-0005](adr/ADR-0005-ocr-engine-evaluation.md)
- **Localization decision:** [ADR-0006](adr/ADR-0006-keyed-localization-catalogs.md)

## 1. Execution strategy

Implement in one long, mostly autonomous run. Resolve system/dependency setup and model provisioning first, then build/test pure components and use cases with fakes. Do not start database/UI/model integration until the unit-test gate passes. Keep integration testing and real-card evaluation as later, clearly separated gates; real card data is not needed to implement the app shell or prove unit behavior.

The MVP remains a **desktop file-import workflow**. Webcam capture is explicitly deferred to the next planned input milestone; at that point, webcam capture becomes the primary source and the file picker remains the secondary source. Phone-camera photos and scanner images can be imported during the MVP.

## 2. Assistance boundaries and setup gate

### Upfront environment gate

Resolve all install/setup friction before feature implementation so it does not interrupt the coding run:

1. Confirm Python 3.14, Tkinter, and the existing `.venv` work. `python3-tk` is already installed on the current Ubuntu machine; run `./setup.sh` after updating dependency declarations and verify `import tkinter` in `.venv`. On another Ubuntu/Debian setup, the only expected privileged install is `sudo apt install python3-tk`.
2. Declare the Python runtime dependencies in `pyproject.toml`: Pillow for safe image decoding/previews; NumPy for model input/output; `opencv-python-headless` for alignment/rectification and checkbox-region processing; and `onnxruntime` CPU for DE·HTR v2. Keep CUDA, PyTorch, PaddlePaddle, Transformers, network OCR, and GUI OpenCV packages out of the default install.
3. Add pytest (and coverage if useful) as development dependencies. Keep `requirements.txt` and `setup.sh` as the single contributor setup path; `./setup.sh` should install the app plus test dependencies and verify Python/Tk imports.
4. Add a deterministic model-provisioning script that retrieves only the pinned DE·HTR v2 ONNX/config artifacts, verifies the documented SHA-256 values, and places them in the application asset path. The model is a public static artifact, not a service: no card image or transcription is sent. Bundle the verified assets with the app so recognition runs offline after setup.
5. Add license/attribution notices for the model, training data, ONNX Runtime, image libraries, and any redistributed artifacts.

The CPU ONNX path is the default even though this laptop has a GeForce RTX 3050 Ti Mobile. GPU acceleration is optional and should be considered only after measuring the CPU path; do not make CUDA installation a prerequisite.

### Assistance deferred to the end

- Ask for permission-cleared completed Startkarten, expected transcriptions, checkbox examples, and allowed `Strecke`/`Lage` options only when starting the real-card quality gate. Do not block unit tests, the app shell, or manual entry on these inputs.
- If package/model download fails in the upfront gate, stop only for the specific install/access blocker; do not work around it by using a hosted OCR service or unpinned model.

## 3. Implementation phases

### Phase 0 — Environment and dependency lock-in (upfront)

- Resolve the system Tk prerequisite and test that the project venv can import it.
- Add runtime/dev dependencies and model-fetch tooling; run setup once and verify imports for Tk, Pillow, NumPy, OpenCV, and ONNX Runtime.
- Pin model/config hashes and verify the fetched files with SHA-256. Do not initialize the ONNX session or run inference in this phase; model execution is tested only after the unit-test gate, in Phase 8.
- Record exact dependency/model versions and license notices.

**Exit:** one reproducible setup command creates a usable venv, Tk and Python image/OCR dependencies import, and the pinned model assets pass checksum validation. No real Startkarte is used.

### Phase 1 — Localization and app contracts (unit tests first)

- Add a `TextCatalog` boundary and complete `locales/de.json` for every app-owned user-visible and accessibility string: window/screen titles, field and option labels, buttons, status, menus, errors, dialogs, tooltips, file filters, empty/loading/success states, and accessibility descriptions.
- Use stable namespaced keys and named interpolation parameters. Keep strings out of view/controller/domain code; no raw-key or source-language fallback is allowed.
- Add unit tests for key lookup, named placeholders, plurals, default locale behavior, and catalog completeness/compatibility. Add a check that schema fields/options/statuses refer to catalog keys.
- Define stable domain contracts for sessions, cards, field values/provenance, checkbox tri-state, card states, alignment results, recognition requests/candidates/outcomes, and model/schema versions.

**Exit:** catalog tests and contract/schema tests pass with no Tk display, SQLite, ONNX runtime, or real images required.

### Phase 2 — Domain rules and field semantics (unit tests)

- Implement the fixed/versioned Startkarte schema with internal keys and localization keys, not display labels.
- Implement card/session state transitions and invariants: `CAPTURED → ALIGNING → RECOGNIZING → NEEDS_REVIEW → REVIEWED`; failure/cancellation returns a recoverable draft to `NEEDS_REVIEW`.
- Implement manual/OCR/user-edited provenance transitions and retry merge rules: retry can fill blanks but cannot overwrite user edits/confirmed values without explicit approval.
- Implement numeric/year validation, independent gender mark states, shared `Strecke/Lage` unresolved behavior, and explicit time parsing to canonical integer milliseconds. Keep locale-specific duration display in the presentation/localization layer.
- Keep all fields optional for the first MVP; unresolved values are visible and revisit-able.

**Exit:** pure unit tests cover schema order, all state transitions, provenance, retry safety, validation, tri-state checkboxes, supported/ambiguous time formats, and localization keys.

### Phase 3 — Image normalization and field crops (synthetic unit fixtures)

- Implement safe image loading, EXIF orientation, pixel/file-size limits, thumbnail preview, and user-facing failure mapping.
- Implement canonical card alignment as a pure component: use four uniquely identified ArUco markers for the new A6 format, with legacy boundary/heading alignment retained for existing cards. Compute orientation/perspective transforms and return a quality result. Keep manual adjustment as the UI fallback, not as guessed crop geometry.
- Define versioned, layout-specific regions. Preserve the eight text crops and shared `Strecke, Lage` crop for legacy cards; add the marker-aligned A6 layout with separate `Strecke` and `Lage`, eleven OCR crops for nine logical text fields (including three time-cell crops), and checkbox ROIs.
- Use generated fixtures (blank template overlays, rotations, skew, synthetic lines, invalid dimensions) for unit tests. Do not include personal or real completed card images.

**Exit:** unit tests verify transforms, crop bounds/order, orientation, size limits, invalid input handling, and conservative alignment rejection. These are geometric tests only, not OCR-quality tests.

### Phase 4 — OCR adapter and checkbox detector (mocked unit tests)

- Implement the DE·HTR v2 ONNX adapter behind `HandwritingRecognizer`: load the pinned local artifact once, exact grayscale preprocessing, capped/resized/padded input, CTC decode from the configured alphabet, typed failures, and deterministic cleanup.
- Keep ONNX Runtime types behind the adapter. Use CPU threads bounded to a small configurable count; do not touch Tk from inference code.
- Unit-test preprocessing tensors, shape/padding, CTC collapse/blank handling, Unicode decoding, empty/invalid lines, bad model/config hashes, missing model, cancellation, and typed error mapping with a fake inference session and fixed logits.
- Implement checkbox proposals separately using synthetic box crops. Threshold logic must return `UNKNOWN` for ambiguous/noisy cases; no text OCR result may determine the mark state.
- Map raw `Strecke/Lage` text to an unresolved shared candidate until the user supplies allowed values and split rules. Do not guess options or assignments.

**Exit:** adapter and mark-detector unit tests pass without loading a real ONNX model or connecting to a network; all values are suggestions requiring review.

### Phase 5 — Application use cases (unit tests with fakes)

- Implement create/list/open/delete session, list/open/delete card, accept image, align/crop, recognize, save draft/review, retry, and next-card use cases.
- Enforce durable image/card draft before recognition. Model/unavailable/alignment/write failures preserve the draft and route to manual entry.
- Ensure OCR results are merged only into safe blank/unconfirmed values; serialize or version writes so late inference cannot overwrite edits.
- Add a fake repository, image store, aligner, and recognizer for use-case tests.

**Unit-test gate (must pass before integration):** complete tests for catalog/domain/image transforms/OCR decoding/use-case transitions, including failure, cancellation, retry, and no data loss. Run the entire unit suite before proceeding to SQLite, a real model session, or Tk navigation.

### Phase 6 — Persistence and filesystem integration

- Implement SQLite schema/migrations and repositories for sessions/cards/field values, stable card ordering, schema/model versions, and user-controlled retention.
- Implement app-data paths, atomic managed-image copies, transaction ordering, startup recovery, and retryable/idempotent deletion cleanup.
- Add repository integration tests using temporary SQLite databases and temporary directories: create/list/reopen, values/provenance, migration, interrupted recognition recovery, image copy failure/rollback, card/session delete, and orphan cleanup.
- Do not use the real home directory or real card data in tests.

**Exit:** repository/filesystem integration suite passes independently of Tk and real-card OCR.

### Phase 7 — Tk workflow and localization integration

- Replace the shell with views/presenters for sessions, session detail, image select/align/preview, OCR progress/fallback, and form-first review.
- Resolve every application-owned UI/accessibility string through `TextCatalog`; field/status schema contains keys only. Keep native OS dialog chrome separate, but localize app-provided titles/filters/messages.
- Match the paper order/grouping, show the source image beside the review form with labeled crop overlays, and provide keyboard focus, readable status text, resizable/scrollable layout, and clear save/next behavior. Use independent tri-state checkboxes for `Mädchen` and `Junge`.
- Route disk/alignment/recognition work through a bounded worker and marshal results to the Tk thread. Add dirty/save state and close/navigation flush behavior.
- Use fake use-case results for screen/presenter tests; defer end-to-end file-picker tests to the integration gate.

**Exit:** headless unit tests for presenters/navigation/locale keys pass; desktop UI launches with empty and populated fake state on the supported Linux environment.

### Phase 8 — Integration and local model smoke tests (no real Startkarten)

- Wire real SQLite, image store, aligner, and pinned ONNX adapter at the composition root.
- Run model smoke tests only on synthetic line images and the model publisher's non-personal public demo fixture; verify no online calls after model provisioning.
- Exercise end-to-end synthetic workflow: create session → import generated template fixture → align/crop → OCR candidate → edit/confirm → save/reopen/next/delete.
- Run display-backed GUI checks (or Xvfb where suitable), test resize/scroll/focus, OS file picker, and system Tk errors. Check app starts offline after model files are provisioned.
- Test missing/corrupt model, unreadable image, cancellation, low disk/write errors, app close/reopen, retry race, and cleanup failures.

**Exit:** integration tests pass on Ubuntu 26.04 x86_64; setup and launch are repeatable; no real user card or personal data has been used.

### Phase 9 — Real-card evaluation (later, user-assisted)

- Start only after the user supplies permission-cleared completed Startkarten and expected values. Keep all samples local and out of Git unless the user explicitly approves otherwise.
- Agree `Strecke`/`Lage` options and aliases, normal ordering/separation, time formats, checkbox mark examples, and any required fields.
- Split by card and writer where feasible; annotate fields and alignment/crop quality. Evaluate alignment and field recognition separately from app integration.
- Report field-level CER/exact match, parsed numeric/year/time validity, checkbox precision/recall/unknown handling, joint `Strecke/Lage`, missing/unresolved rate, and misleading wrong candidates. Set acceptance thresholds with the user; do not infer them from the model's external benchmark.
- Test real phone-camera/scanner image imports with rotation, perspective, glare, blur, shadows, handwriting variation, and both marked/unmarked checkboxes. Keep manual correction available regardless of results.

**Exit:** a documented quality decision per field: suitable, manual-only, or requires another crop/model approach. Accuracy claims remain out of scope until the user approves the measured results.

## 4. Planned next milestone — webcam-first input

This milestone is requested and planned, but does not block the MVP above:

- Add webcam capture as the primary action/source when starting a card. Retain the file picker as a clearly available secondary source for scans and existing photos.
- Introduce a narrow `CardImageSource`/input-adapter boundary so camera frames and selected files produce the same validated image object and share preview/alignment/persist/recognize use cases.
- Add capture preview, retake, use-image actions, camera selection/status, and device-unavailable/error states. Ask for camera access only when capture begins. If capture is unavailable/fails, offer file import without losing the current session.
- Unit-test source mapping, state transitions, cancellation, fallback, and accepted-image handoff with fake camera/file sources first. Then run integration tests using an attached webcam and at least one physical desktop webcam/camera.
- Keep webcam capture local: never record until the user explicitly accepts the preview; release camera resources when leaving capture; do not save rejected retakes.

**Exit:** webcam is the default intake source, file import remains a functional alternative, and both sources pass the same alignment, draft durability, local recognition, and recovery tests. Camera-device integration tests require hardware and are intentionally later than the MVP integration gate.

## 5. Definition of done for the planned MVP

- Unit-test gate passes before integration begins; repository/UI/model integration tests then pass separately.
- A user can run the app from the documented venv setup, work offline with the bundled model, digitize multiple cards in a local session, review/correct every value, recover drafts, and delete cards/sessions.
- Every app-owned user-visible and accessibility string comes from the locale catalog; German is complete and no missing key is displayed.
- The recognizer never auto-accepts; manual fallback works for every field/model failure; card data remains local and does not appear in logs.
- Real-card results are evaluated separately and documented honestly; no unsupported accuracy claim is made.
