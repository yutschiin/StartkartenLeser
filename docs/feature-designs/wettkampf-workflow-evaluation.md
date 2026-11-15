# Wettkampf workflow evaluation

The runner is ready for **handwritten-card photos**. It does not use a camera or
start OCR until explicitly invoked with a complete photo directory. The current
`tests/testfotos/` is the development set, not an independent holdout. Use a
separate permission-cleared directory for any new validation set.

## Prepare and run

Photograph each of the 16 cards separately, with the entire card and its corner
markers visible. Keep the originals. Copy/rename each photo to the **exact**
`image_filename` in [`tests/reference_data.csv`](../../tests/reference_data.csv):
`karte-01-mueller-anna.jpg`, …, `karte-16-braun-oskar.jpg`. The CSV lists all
16 names. Mapping is by filename only, never by recognized person/name.
JPEG and PNG image contents are supported; no HEIC or PDF conversion is done.
Keep each file below the application's 20 MiB capture limit.

From the repository root, after all photos are available:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_wettkampf_workflow.py \
  --images-dir /absolute/path/to/new-card-photos \
  --output-dir tests/results/wettkampf-handwritten-001
```

`--references path/to/references.csv` optionally selects another reference set.
The default 16 cards produce **144 observations: nine fields per card**.
Zeitnehmer/timekeeper stays on the cards, in the app, and in CSV v1, but is
excluded from **all evaluation scores**, including the older reference evaluator.

Use a **new, nonexistent** output directory for every run, outside the photo
directory. Existing run directories are rejected, even if empty. All references,
filenames, photos, image limits and event metadata are preflighted before any
run data or model instance is created. Extra unrelated files are ignored.
Missing or duplicate mappings fail preflight; there is no OCR-based fallback.
No downloads, camera capture, HTTP server or user application database are used.
The real local model must already be installed as for the normal application.

## Stages and failures

References are grouped by `(distance_m, stroke_key, gender_key)`, sorted by that
tuple and then `card_no`; events receive consecutive numbers starting at one.
For each event the runner uses the production `BrowserWorkflow` and the same
SQLite, managed-image store, lazy DE·HTR recognizer, template aligner, checkbox
proposer and default correction policy as the composition root:

1. Create the Wettkampf with reference metadata.
2. Import each mapped photo through `capture` (a managed copy, original unchanged).
3. Recognize, preserving application responses and original OCR evidence.
4. Approve with **only the current revision**, no field edits or checkbox edits.
5. Export the event through the application's CSV v1 exporter.

Validation issues and missing required readings are logged as
`validation_warning`, but every captured card is submitted to the production
approval method without edits, exactly as requested for this test. Only a
rejection by the application blocks approval. Application correction-policy
suggestions are allowed, exactly as in the browser's normal no-edit approval.
Incorrect or blank values that the application accepts remain in the export
and score zero; the evaluator never repairs them.

A draft blocks export of its **whole event**, including otherwise good cards.
Failed imports also block that event rather than exporting a misleading subset.
Other independent cards and events continue. Expected application errors are
recorded with their original keys/statuses. Unexpected errors terminate with
the evidence and journal collected so far intact; they are not silently ignored.
Exit codes: `0` completed with all events exported, `2` completed with blocked
events, `1` preflight/operational failure.

## Results and score meanings

The run directory retains `data/startkartenleser.sqlite3`, managed original
photo copies, per-card `evidence/*.json`, per-event `exports/*.csv`, a flushed
`stages.jsonl` journal, reference/policy snapshots, version/hash metadata in
`run.json`, `field-scores.csv`, and `summary.json`. Git revision and dirty-state
metadata are recorded when available; both are `null` when running from a source
archive without `.git`. A run is complete only when `summary.json` exists. Never
treat a partial run as a completed accuracy result.

Each field row contains three **separate** binary scores (100 correct / 0 wrong,
blank, missing or unavailable):

- **Persisted:** final persisted field/mark values versus the reference, even if
  event export was blocked.
- **Export:** values read back from the actual application CSV. A blocked event
  contributes nine explicit zero observations per card, never disappears from
  the denominator. The six per-card fields use their `*_text`/text columns;
  course and position use `distance_m` and `stroke_key`. Gender uses the exported
  `female_mark`/`male_mark` pair. CSV v1 is unchanged.
- **OCR:** genuine raw transcriptions versus the reference, before correction
  suggestions or event substitution. For course/position/gender the source is
  the repository's persisted **reference evidence**, not the event-filled fields
  or current marks. Legacy combined course/stroke evidence is parsed only when
  unambiguous. Stroke aliases from the policy are accepted, but fuzzy repairs
  are not credited in the raw score. Missing/ambiguous checkbox pairs earn zero.

**Course, position and gender are supplied by event metadata in the production
workflow.** Their persisted/export success is metadata/workflow correctness,
**not OCR accuracy**. `final_origin`, `export_origin` and `ocr_origin` identify
these sources. Consult the separate field counts in `summary.json` and raw
columns in `field-scores.csv`, especially for those three fields.

Shared normalization trims/case-folds text, normalizes Unicode and whitespace,
accepts numeric metres or `100 m`, and compares supported times by duration.
Names retain diacritics; numeric year/heat/lane text is not guessed or repaired.
The runner never changes reference values to make recognition pass.
