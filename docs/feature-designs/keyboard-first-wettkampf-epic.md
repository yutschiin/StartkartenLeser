# Epic: Wettkampf and keyboard-first card processing

- **Date:** 2026-11-10
- **Branch:** `epic/keyboard-first-wettkampf-workflow`
- **Status:** Browser/Python selected after spikes; React/Material UI takeover implemented
- **Baseline:** Current `main`, commit `7a7e626`

## Current implementation

The user accepted the successful browser camera spike and requested Material UI.
The Tk production UI is replaced, not retained as a second frontend. See
[ADR-0007](../adr/ADR-0007-local-browser-mui.md) and the
[implementation/verification plan](browser-mui-implementation.md).

Implemented: explicit immutable Wettkampf metadata; legacy card reassignment;
real camera/file capture; immediate keyboard-first entry; draft autosave separate
from approval; same-card retake; real explicit local OCR/manual fallback;
source/raw-evidence review; deletion; reviewed-Wettkampf CSV export.
The independent Qt and browser spike branches remain intact.

The original design sections below document the reasoning and unresolved
proposals. Their provisional Qt recommendation and “not implemented” statements
describe the pre-spike baseline, not the current application. Metadata editing,
mixed/open categories, consumer-specific CSV mapping and mismatch warnings are
still deferred; initial implementation choices are explicit in the takeover plan.

## 1. Outcome

A user creates a **Wettkampf**, for example **Wettkampf 2 · 50 m Rücken ·
Weiblich**, then processes its stack of cards without reaching for the mouse:

**Take picture → review/edit forwards and backwards → approve → take next picture.**

After the stack, the user may use the mouse again to create another Wettkampf
or export this Wettkampf to CSV. Everything, including recognition and export,
remains local.

This epic is deliberately ordered:

1. Refine the data model.
2. Refine the workflow against that model.
3. Compare UI technologies against the workflow.
4. Select a UI and implement only after the design decisions.

## 2. Design package

| Document | Purpose |
|---|---|
| [Data model](wettkampf-data-model.md) | Wettkampf ownership, card evidence, legacy migration and proposed CSV contract |
| [Workflow model](keyboard-first-workflow.md) | States, keyboard/focus contract, recovery and acceptance scenarios |
| [UI alternatives](keyboard-first-ui-options.md) | Sourced comparison, provisional recommendation and prototype gates |
| [Qt/PySide spike plan](qt-pyside-workflow-spike.md) | Bounded experiment for the refined keyboard, camera and autosave contract |

These are next-epic proposals, not a claim that the existing app already has
camera capture, Wettkampf metadata, CSV export or a replacement for Tkinter.
The [MVP design](mvp-workflow.md), [PRD](../prd.md) and
[architecture](../architecture.md) describe the earlier baseline. For this epic,
the documents above propose replacing the generic Sitzung concept, adding CSV
export, and making camera input primary. Existing privacy, retention,
localization and human-review requirements remain.

## 3. Requirements versus proposals

**Requested requirements**

- Sitzung becomes a Wettkampf with Strecke, Lage and Gender.
- Create a Wettkampf and scan its cards into that Wettkampf.
- Mouse use is acceptable during setup and after processing the stack.
- From the first scan, capture, forward/backward form traversal, approval and
  the next capture must all be keyboard-only.
- Export a Wettkampf to CSV.
- Reconsider the outdated-feeling Tkinter presentation.
- Reserve a way to warn about confidently detected mismatches; warning policy
  is a later design discussion.
- Gender stays in routine card review after Jahrgang.
- Space activates the focused button; capture is focused in camera-ready state.
  Immediately after capture, show entry with Retake focused and Tab leading to Name.
- Tab/Shift+Tab traverse forwards/backwards; Enter advances from fields;
  Ctrl+Enter approves the whole card and moves to the next capture.
- Autosave changes, at least on field exit; saving is not approval.
- Plan a Qt/PySide spike before deciding on a production UI replacement.

**Proposals to validate, not settled product decisions**

- Wettkampf number is explicit; no new overarching meet/event entity yet.
- Wettkampf metadata is authoritative; card readings are retained separately.
- Routine review includes swimmer/result fields and card gender marks, while
  Strecke/Lage remain separate from the authoritative event header.
- Approval returns to camera-ready state, but never fires the next shutter.
- Optional-field handling, detailed retake replacement semantics, metadata
  correction rules and the exact CSV dialect/schema remain proposals.
- Production UI selection follows the planned Qt/PySide spike.

## 4. Current implementation and reuse boundary

The current app has generic `Session` records, ordered `Card` records, generic
field values, independent tri-state gender checkboxes, local image storage,
revision-checked persistence and recognition, and explicit review saving.
Input is selected PNG/JPEG files; review still includes Strecke, Lage and
gender on each card. There is no CSV exporter or camera adapter.

Reuse the domain/application/infrastructure separation, local recognition,
source-image retention, locale catalogs and concurrency safeguards. Keep UI
widgets, camera APIs and any browser/IPC transport out of domain models.
Draft autosaving is a requirement to implement and test, not an assumption
about the current form.

## 5. Decision gates and implementation slices

| Gate | Decision/evidence needed | Subsequent slice |
|---|---|---|
| A: Model | Event categories, metadata correction, legacy reassignment and CSV consumer agreed | Wettkampf contracts, repositories, migration and headless tests |
| B: Workflow | Routine field order, shortcuts, optional/invalid values and approval semantics tried with a stack | UI-independent capture/review coordinator and fake camera |
| C: UI | Packaged offline prototype passes the [same acceptance checks](keyboard-first-ui-options.md#5-prototype-and-decision-gate) | Record a new ADR; only then replace/wire the UI |
| D: Delivery | Real-camera cycle, restart recovery, export fixtures and retained MVP behavior verified | Ship the vertical slice, then polish and tune throughput |

Do not build several production front ends. Plan and run the
[Qt/PySide spike](qt-pyside-workflow-spike.md) first; use the runner-up only if it fails a gate.
Do not merge the Qwen experiment into this epic.

### Questions to resolve before implementation

1. Is Linux the first release target only, or must Windows ship at the same time?
2. What camera/device and mounting arrangement will be used?
3. Is Gender limited to Weiblich/Männlich, or are mixed/open categories needed?
   Which Strecke/Lage choices must creation offer?
4. Can a reviewed card intentionally retain missing or invalid values? The
   proposal preserves today's non-blocking optional fields, visibly flagged.
5. Which program consumes the CSV, and what exact headers/dialect does it need?
6. Are the agreed routine fields and capture/approval keys comfortable during
   repeated use? Validate them in the Qt/PySide spike rather than selecting on screenshots.

These do not block reviewing the proposals. They do block treating the proposed
defaults as approved behavior or implementing a final export/UI contract.

## 6. Epic acceptance

- One Wettkampf has explicit metadata; cards cannot silently alter it.
- At least 20 consecutive cards can be processed after setup with zero pointer
  actions, including correcting earlier/later fields.
- No extra per-card wizard or forced confirmation of inherited event metadata
  interrupts the normal cycle.
- After capture, the entry form immediately focuses Retake; Tab reaches Name,
  and gender is reachable in the normal sequence.
- Autosave persists changes at least on field exit, without manual save/approval.
- A failed capture/save never advances as though it succeeded; retry and manual
  review are keyboard-reachable.
- Restart restores saved drafts, approved cards and their Wettkampf association.
- CSV contains the intended Wettkampf and approved card data, not raw OCR guesses
  substituted for reviewed values; export failure cannot appear successful.
- Existing local-only processing, image/provenance retention, deletion behavior
  and German keyed localization survive the implementation.
