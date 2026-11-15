# Product Requirements Document — StartkartenLeser Desktop

**Status:** Browser/MUI keyboard-first epic implemented; OCR accuracy remains under evaluation
**Platform:** Local desktop browser + Python backend
**Product name:** StartkartenLeser Desktop  
**Product language:** German (`de-DE`)  
**Legacy sample:** [Blank Startkarte](Startkarte_empty.jpg)

**A6 form references:** [A6 Startkarte proposal](startkarte-a6-proposal.html) and
[blank form](startkarte-a6-form.pdf) are design references. The application has
versioned A6 recognition layouts; the proposal is not a claim that every printer
or event-specific form has been physically validated.

**Current scope:** The [Wettkampf and keyboard-first design package](feature-designs/keyboard-first-wettkampf-epic.md)
and [takeover plan](feature-designs/browser-mui-implementation.md) supersede the
historical MVP boundary below. The UI is now React/Material UI in a local browser,
not Tkinter. It supports explicit event metadata, camera/file capture,
keyboard-first autosave/approval, real local OCR/manual entry, same-card retake,
legacy card reassignment and CSV export of fully reviewed Wettkämpfe.

No hosted service is introduced. CSV export is an explicit user download and
does not upload or delete data. Event categories initially remain female/male;
metadata editing, mixed/open categories and automatic mismatch warnings are
deferred. Corner adjustment is not ported: unsafe alignment requires manual
entry or retake. Source images and optional projected crop overlays remain.

## Historical MVP requirements

The sections below retain the original product baseline and its deferred
features for context. Where they conflict, the accepted browser/Wettkampf
scope above and ADR-0007 take precedence.

## 1. Summary

StartkartenLeser Desktop helps a user review and digitize a batch of paper Startkarten. The user imports a photo or scan of each card, local handwriting recognition may read the predefined fields, and the application presents the presumed values in an editable form. The user checks and corrects those values before proceeding to the next card. Sessions, source images, and values are stored on the user's computer; export is out of scope for the MVP.

The application assists data entry; it does not silently certify recognition results. A person reviews every card before it is considered complete.

## 2. Problem and opportunity

Transcribing handwritten Startkarten by hand is repetitive and can introduce errors. A desktop workflow with image import, field-aware handwriting recognition, and a clear verification step can reduce typing while keeping the user in control. A larger resizable screen also provides room for a focused review form and session overview.

Recognition quality is the central feasibility risk. German handwriting, card condition, and field layout determine whether a local recognizer can extract useful values. Test with representative cards before selecting a production OCR implementation or making accuracy claims.

## 3. Goals

- Import a photo or scan of one Startkarte at a time from the desktop file system.
- Read German handwriting in predefined fields and show presumed values using German labels.
- Let the user quickly verify, edit, or leave a value blank.
- Support multiple cards in a session, one card at a time.
- Keep sessions, card images, and reviewed values available after the application closes and reopens.
- Keep card data local; do not send images or personal information to a remote OCR service.
- Make uncertain or missing readings visible rather than presenting them as certain.

## 4. Non-goals for the first version

- Automatic acceptance of readings without user review.
- General-purpose OCR for arbitrary documents or card layouts.
- Web service, accounts, cloud archive, synchronization, or team collaboration.
- CSV or other data export.
- Editing the card template or field definitions inside the application.
- Importing multiple cards from a single image.
- Advanced image manipulation, batch cropping, or bulk correction tools.
- Built-in webcam capture is deferred from the MVP; file import is the MVP baseline. The next planned input milestone makes webcam capture primary and retains file import as the secondary source.
- Guaranteeing recognition accuracy before representative sample cards have been evaluated.

## 5. Users and primary workflow

### Primary user

A person with a stack of Startkarten who wants to review and digitize the predefined information on each card in a private, local desktop application.

### Happy path

1. The user opens or starts a scanning session.
2. The user imports a photo or scan of one Startkarte using the desktop file picker.
3. The application stores a private copy of the image and attempts to identify configured fields and handwritten values locally.
4. The application shows an editable digital twin with presumed values and clearly marked uncertain or unreadable values. During review, it shows the source image beside the form with labeled crop boxes so the user can compare each candidate to its source region.
5. The user confirms or corrects each value. The user may leave a value blank and revisit it later.
6. The user saves the reviewed card and chooses **Nächste Karte** to import another, or returns to the session overview.

### Recovery paths

- If an image is blurry or incomplete, the user can choose another file before accepting it.
- If recognition fails or is unavailable, the user can enter values manually.
- If the application exits during recognition, the persisted draft remains available for manual completion or retry when reopened.
- Saved cards and their review state remain available after restart.
- If the selected file cannot be read or copied into application storage, the application explains the problem and does not create a misleading completed card.

## 6. Functional requirements

### Session and card management

- **FR-01:** The application can create a session containing multiple Startkarten.
- **FR-02:** The application can show a session overview with card order and review status (for example: needs review, reviewed).
- **FR-03:** The user can reopen and continue editing a card after navigating away or restarting the application.
- **FR-04:** The user can import the next card without recreating the session.
- **FR-05:** The application must not silently discard an imported image or entered value when navigating between cards.

### Image intake and recognition

- **FR-06:** The user can select a supported image file from the desktop file system and preview it before proceeding. The application must report unsupported or unreadable files in a recoverable way.
- **FR-07:** The application must not assume every Startkarte uses one fixed print layout. It uses versioned layout definitions and detectable registration markers/anchors to align and crop the configured fields. Uncertain layout or alignment remains a manual-review case; the application must not silently use guessed crop positions.
- **FR-08:** Each extracted value can include a confidence/status indicator. Missing or low-confidence values must be visually distinguishable from high-confidence readings.
- **FR-09:** The user can replace the selected image or proceed to manual entry when the image or OCR result is poor. Recognition can be retried from a saved draft; retry must preserve user-edited values and must not silently replace any saved candidate.
- **FR-10:** Handwriting recognition runs locally. Card images and extracted values must not be sent to a remote OCR service.

### Review and correction

- **FR-11:** The digital twin displays all configured field labels, the current presumed value, and an editable control appropriate to the field. `Mädchen` and `Junge` use two independent tri-state checkboxes so checked, unchecked, and unclear can each be reviewed.
- **FR-12:** The user can edit every field, including values OCR marked as confident.
- **FR-13:** The user can save a card without filling optional or unreadable fields; required-field behavior depends on the agreed field schema.
- **FR-14:** The application records whether a value was OCR-produced, user-corrected, or manually entered so its review state is understandable and useful for diagnostics.
- **FR-15:** Keep the captured/imported source image with the card and display it beside the review form with labeled projected crop regions. The physical card remains the reference; boxes and OCR values are proposals, not confirmations.
- **FR-20:** Interpret `erzielte Zeit` into an integer millisecond value and retain the original transcription. Read the current card's continuous time line using supported explicit duration notations (for example, `1:34,92`). Show normalized durations in German with nonbreaking spacing; ambiguous notation must be confirmed rather than guessed.
- **FR-21:** Preserve the Jahrgang candidate as written. A short entry such as `85` or `18` is ambiguous; do not silently expand it to a century/year (for example, 1985 or 2018). Leave interpretation to the user during review.

## Implementation progress and current evaluation

The following prototype capabilities are implemented; they do not constitute an accuracy claim or final crop acceptance:

- Local PNG/JPEG intake, perspective alignment from four unique ArUco corner markers for the new A6 layout, and legacy boundary/heading alignment as a compatibility fallback.
- Versioned crops: eight text regions and two checkbox crops for legacy cards; nine text regions and two checkbox-interior crops for the current line-based A6 card (`card-layout-a6-v2`, `startkarte-crops-v5`). A6 uses separate `Strecke`/`Lage` crops and one continuous time crop. Labeled crop overlays are projected onto the source image for review. The previous boxed A6 card is deprecated.
- Local German handwriting OCR and a separate conservative checkbox-mark proposer run on the crops. Results remain editable suggestions and are not automatically accepted.
- The real filled A6 sample is detected by marker IDs 0–3 and currently returns candidates for all nine logical text fields in a local smoke run. Two legacy filled samples still align using their respective layouts. These candidate counts are not accuracy measures; expected transcriptions and field-level evaluation remain pending.
- Automated tests cover synthetic marker alignment including quarter-turn rotations, layout-specific crops, legacy compatibility, persistence, recognition workflow, and ambiguous checkbox handling. Real-card field accuracy and final print/crop validation remain subject to review.

### Data protection and retention

- **FR-16:** Card images, recognized values, and user corrections remain on the local computer and are not uploaded or synchronized by the application.
- **FR-17:** The user can delete an individual card and its image, or delete an entire session and all associated data.
- **FR-18:** The application explains what card data it stores and how the user can delete it. It retains session data until the user deletes a card/session or removes the application data; there is no automatic expiration in the MVP.
- **FR-19:** Personal information and card images must not be written to application logs or analytics.

## 7. Data and field schema

The MVP uses the known data fields below across versioned print layouts. The legacy blank reference combines `Strecke` and `Lage`; the new A6 format separates them. Stable keys are internal identifiers and do not determine user-facing labels; displayed labels and option names resolve from the selected locale catalog (German initially).

| Order | Stable key | German label / representation | Data and recognition handling |
| --- | --- | --- | --- |
| 1 | `name` | Name | Free text; preserve spelling as written. |
| 2 | `vorname` | Vorname | Free text; preserve spelling as written. |
| 3 | `jahrgang` | Jahrgang | Preserve the digits as written. Short entries such as `85` or `18` are ambiguous; never infer or append a century automatically. |
| 4 | `geschlecht` | Mädchen / Junge | Two checkboxes on the card. Preserve observed marks; unclear, both-marked, and unmarked states must be reviewable rather than guessed. |
| 5 | `strecke` | Strecke | Value selected from a predetermined set supplied in configuration before OCR evaluation. The allowed set is not yet provided. |
| 6 | `lage` | Lage | Value selected from a predetermined set supplied in configuration before OCR evaluation. The allowed set is not yet provided. |
| 7 | `lauf` | Lauf | Numeric value. Parse and validate as numeric; retain the image and flag uncertain or invalid readings for correction. |
| 8 | `bahn` | Bahn | Numeric value. Parse and validate as numeric; retain the image and flag uncertain or invalid readings for correction. |
| 9 | `erzielte_zeit` | erzielte Zeit | Normalize to integer milliseconds (`erzielte_zeit_ms`) as the canonical value. Retain original recognized text separately. Ask the user to resolve unclear notation rather than guessing. |
| 10 | `zeitnehmer` | Zeitnehmer | Free text; preserve spelling as written. |

The legacy sample has one line labeled **“Strecke, Lage”**; the current A6 design gives `Strecke` and `Lage` separate writing lines. Keep the legacy shared-line handling only for legacy cards. Show `Mädchen` and `Junge` as separate tri-state checkboxes in the digital twin; do not infer one from the other.

Use a fixed, versioned schema for the MVP, with allowed `Strecke` and `Lage` values supplied as configuration before OCR evaluation begins. Do not hard-code allowed values in the application. Preserve numeric `Lauf` and `Bahn` values as numeric data. Normalize `erzielte Zeit` to integer milliseconds and retain original text. Preserve `Jahrgang` exactly as written; any two-digit value remains unresolved until the user confirms its meaning. Required/optional behavior is not yet specified; the user must be able to leave unreadable fields unresolved and review them later.

## 8. UX and accessibility requirements

- Keep the primary sequence obvious: **Bild importieren → Prüfen → Speichern → Nächste Karte**.
- Present all user-facing application text in German, including navigation, actions, status/error messages, and field labels matching the card.
- Store all application-owned user-visible and accessibility text in keyed locale catalogs, never as inline UI literals. Ship German (`de`) as the initial catalog and keep field/status identifiers independent of translated labels. See the [localization decision](adr/ADR-0006-keyed-localization-catalogs.md).
- Use explicit wording such as “Bitte prüfen” rather than implying OCR is definitive.
- Do not communicate confidence using color alone; pair visual styling with text or an icon description.
- Support keyboard navigation, visible focus, screen magnification, and reasonable text scaling using native desktop conventions.
- Make the review form usable at typical desktop window sizes and responsive to resizing; allow scrolling when the window is too small to show every field.
- Show the source card image beside the review form with labeled crop overlays so the user can inspect which source region produced each candidate.
- Match the paper card's order and grouping: `Name` and `Vorname` each have their own line; `Jahrgang` follows, then `Mädchen`/`Junge` checkboxes on one line; `Strecke`/`Lage` and `Lauf`/`Bahn` each share a line; `erzielte Zeit` and `Zeitnehmer` each have their own line.
- Keep the review form compact, avoid redundant headings/instructions, and keep save/next actions easy to reach using standard desktop buttons and menus.
- Use the user's locale for UI formatting while keeping stored canonical values locale-independent.

## 9. Privacy and data handling

- Startkarten contain personal information. Store images and field values locally only; the MVP must not upload, sync, export, or share them.
- Handwriting recognition must run locally and work without sending card data over a network. If a model must be downloaded or updated, that operation must not include card data, and the user should be told when network access is needed.
- Store data in an application-specific directory and do not modify or delete the user's original imported image. The MVP does not add app-managed encryption at rest; document that protection depends on operating-system account security and the user's device configuration.
- Request access to a source image only through a user-selected file; do not scan folders in the background.
- Provide deletion for an individual card or a session, including associated images and extracted values.
- Retain session data until the user deletes it or removes application data. Do not automatically expire or delete saved cards in the MVP.
- Avoid logging card images, handwriting, or personal field values. Do not add analytics or crash reporting that could receive personal information.
- The user is responsible for operating-system backups and access to the computer; explain that local app storage may be included in user-managed backups.

## 10. Success criteria

The first usable release is successful when a user can:

1. Import an image and reach an editable field review screen.
2. Correct every field and save the card.
3. Continue to and save multiple cards in one session, including after application restart.
4. Delete a card or session and verify its local images and values are removed.
5. Understand which values need review and recover gracefully from unreadable handwriting or local recognition failure.
6. See an unambiguous normalized time value and be asked to resolve uncertain time notation rather than having it guessed.
7. See every application-provided label, message, and accessibility name loaded from the selected locale catalog.

Recognition quality should be measured on a labeled sample set supplied by the user. Agree field-level metrics and acceptable thresholds after representative completed-card images are available; do not treat a single overall OCR score as sufficient.

## 11. Risks and open questions

1. **Local handwriting OCR suitability (engine selected):** DE·HTR v2 is the initial local German line recognizer; see [ADR-0005](adr/ADR-0005-ocr-engine-evaluation.md). Its quality on Startkarten still requires field-level evaluation on permission-cleared representative cards.
2. **`Strecke`/`Lage` configuration:** What are the predetermined allowed values, including spellings, display labels, and aliases? Provide this configuration before OCR evaluation.
3. **Card layout:** The marker-based A6 design is the target for new cards; legacy layout support remains for existing cards. Validate print and camera tolerances for the four ArUco markers and confirm which legacy variants must remain supported.
4. **Image samples:** Can representative completed cards be supplied with expected transcription for each field, especially combined `Strecke, Lage`, numeric `Lauf`/`Bahn`, checkbox marks, and time formats? Redact personal details not needed for OCR evaluation.
5. **Time parsing:** What exact notations occur on completed cards? Confirm parsing rules using examples; ambiguous notation must be shown to the user. Canonical value is integer milliseconds.
6. **Required fields:** Which fields, if any, must be present before a card can be marked reviewed?
7. **Retention (decided):** Retain until user deletion; no automatic expiration in the MVP. See [ADR-0002](adr/ADR-0002-user-controlled-retention.md).
8. **Supported desktop platforms:** Confirm operating systems and Python/Tk availability before packaging/distribution.
9. **Desktop baseline (decided):** Python 3.11+ and Tkinter, with local SQLite persistence. See [ADR-0001](adr/ADR-0001-desktop-baseline.md).

## 12. Suggested MVP boundary

### MVP workflow

The MVP follows the full image-to-review route: create/reopen a session; import, align, and preview one card image; persist the accepted image and draft; run local DE·HTR v2 on field crops plus a separate checkbox-mark detector; and show editable candidates beside the source image with labeled crop boxes. The user checks/corrects values, saves the card as **Geprüft**, and chooses **Nächste Karte** to repeat in the same session. Manual entry remains available for unresolved fields and every recognition failure. The selected engine is an integration decision, not an accuracy claim; evaluate field-level recognition on representative completed cards first. The next planned input milestone makes webcam capture the primary source while retaining file import as the secondary source. See the [MVP workflow design](feature-designs/mvp-workflow.md), [implementation plan](implementation-plan.md), [ADR-0003](adr/ADR-0003-desktop-manual-entry-flow.md), [ADR-0004](adr/ADR-0004-form-first-review-layout.md), and [ADR-0005](adr/ADR-0005-ocr-engine-evaluation.md).
