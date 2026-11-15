# Spike plan: Qt/PySide keyboard-first workflow

- **Date:** 2026-11-10
- **Status:** Planned at user request; not implemented or evaluated
- **Technology:** PySide6 / Qt Widgets, initially Qt Multimedia for camera capture
- **Epic:** [Wettkampf and keyboard-first processing](keyboard-first-wettkampf-epic.md)
- **Contract:** [Refined workflow](keyboard-first-workflow.md)

## 1. Question and bounded outcome

Can Qt/PySide deliver a contemporary, reliable, keyboard-only capture/review
loop with immediate Retake focus, gender review and durable autosave while
reusing the local Python processing core?

Produce one runnable experimental vertical slice, automated interaction/storage
tests and a measured go/no-go result. This is not authorization to replace
Tkinter, migrate live data or implement the full epic. Start with the documented
Linux target; add Windows validation if Windows is a release requirement.

## 2. Scope

### Include

- Minimal Wettkampf setup/header using synthetic event data; no full management UI.
- Real camera selection/preview/capture and a deterministic fake camera for tests.
- Immediate captured-image/entry view, with **Bild erneut aufnehmen** focused.
- Routine order: Retake → Name → Vorname → Jahrgang → Mädchen → Junge →
  Lauf → Bahn → Erzielte Zeit → Zeitnehmer → Approve.
- Independent tri-state gender controls with all states keyboard-reachable.
- Space activates the focused button; Tab/Shift+Tab traverse; Enter advances
  from entry fields; Ctrl+Enter approves and returns to a focused capture button.
- Change-triggered autosave, flush on every field exit, explicit saved/error
  status and restart recovery of committed edits. Save is not approval.
- Safe retake/replacement and cancellation; no duplicate card or obsolete OCR
  callback after replacing an image.
- Fake recognizer with controllable delay/failure first; existing local
  alignment/OCR integration after the keyboard/storage behavior works.
- Clean, resizable source-image/form layout with visible focus, German catalog
  strings and 200% text-scale checks.
- One packaged offline build on the first target OS, camera lifecycle and
  dependency/license inventory.

### Exclude

- Production UI replacement, production database migration, full legacy reassignment,
  event editing/moving, advanced styling/QML, confidence-based mismatch warnings.
- Final CSV consumer/schema choice. A synthetic export fixture may test a file
  dialog/write, but final CSV implementation is a separate epic slice.
- Additional front ends or speculative abstractions for multiple UI toolkits.

Keep experimental data/database/images separate from the user's existing app
data. Use the existing domain/application ports where they fit; a narrow
experimental fixture can supply Wettkampf context without implementing the full
migration. Do not claim fixture-only recovery proves production migration.

## 3. Execution sequence

1. **Harness and form:** add the spike as an isolated experiment with explicit
   optional dependencies/launch instructions. Keep the existing app entry point
   unchanged. Use standard Qt Widgets, explicit tab order and no default-button
   Enter behavior that bypasses field traversal. Test main/keypad Enter and
   Ctrl+Enter separately. Avoid global Space shortcuts.
2. **Fake capture and focus:** show entry immediately after a captured frame,
   Retake focused; allow edits once image/draft persistence succeeds while
   recognition continues. Implement release/auto-repeat guards so held Space
   cannot trigger Retake on arrival. Late results cannot steal focus.
3. **Draft persistence:** exercise isolated SQLite/image storage, ordered
   revision-checked autosave and field-exit flushes. Commit the current field
   before Ctrl+Enter approval even when it has not lost focus. Serialize/cancel
   pending draft writes so they cannot revert approval or newer text.
4. **Retake:** return to replacement preview with capture focused; cancellation
   restores the original. Persist the replacement before switching references,
   confirm resetting edited values and ignore obsolete recognition. Clean up
   superseded images retryably, never remove the original first.
5. **Real camera/OCR:** validate device resolution, preview, permission/error
   states and disconnect/reconnect. Attach existing OCR off the UI thread;
   preserve edited/confirmed values during delayed result delivery.
6. **Packaged trial and decision:** run acceptance checks on the real device,
   record failures/measurements and decide proceed, narrow follow-up or reject.

The first pass uses Qt Multimedia. If it fails a specific required device check,
investigate a Python-native capture adapter within the same spike rather than
changing the UI toolkit immediately. Document the failure and added complexity.

## 4. Required evidence

Automate the refined [K01–K16 workflow scenarios](keyboard-first-workflow.md#7-measurable-acceptance-scenarios)
where possible, and distinguish simulated passes from real-device/manual checks.
Full CSV and migration acceptance remain later implementation gates, not spike
blockers. In particular:

| Test | Required observation |
|---|---|
| Space capture with delayed OCR | Immediate entry, Retake focused, Tab reaches Name; no held-key recapture |
| Enter, keypad Enter, Tab and Shift+Tab | Correct next/previous focus, gender included, no accidental approval; normal text spaces |
| Gender state changes | Unknown/checked/unchecked reachable for each mark, independently autosaved |
| Field exit / restart | Every changed field flushes on exit without Ctrl+S; committed values restore |
| Save failure and rapid edits | Visible error, dirty values retained, retry works, newest value wins |
| Ctrl+Enter from a dirty field | Includes current edit, one review commit, pending autosaves cannot undo it; capture focused afterward |
| Retake before/after edits | Same ID/sequence, explicit edit reset, safe cancellation/replacement failure, old worker ignored |
| Twenty-card real-camera stack | Zero pointer actions after setup; no extra pictures/cards or focus drift |
| Packaged offline launch | Camera, model and libraries work without the development environment or network |

Measure capture-to-entry separately from capture-to-OCR-ready, plus
approval-commit-to-camera-ready (proposed p95 ≤ 500 ms). Record hardware, image
resolution, model configuration, sample count, median/p95, startup time, memory
and package size. Do not conflate fake-recognizer latency with real OCR latency.

## 5. Stop and decision

- **Proceed:** keyboard/autosave/retake and real-camera checks pass on the target
  machine, packaging works, and no unresolved licensing/runtime blocker remains.
  Record a new UI ADR before production replacement.
- **Narrow follow-up:** name one blocking requirement and bound the next experiment;
  do not keep expanding the spike into the full application.
- **Reject:** record reproducible evidence of the unmet requirement, then revisit
  the [UI comparison](keyboard-first-ui-options.md) rather than assuming Qt failed
  because of an untested device/configuration.

Final event categories, metadata correction and CSV consumer decisions remain
open but do not prevent this isolated synthetic-data spike.
