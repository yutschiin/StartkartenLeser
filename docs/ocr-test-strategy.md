# Real-photo OCR test strategy

## Purpose

Measure how well the current local image pipeline reads the supplied handwritten Startkarten, establish a reproducible baseline, and use field-level results to prioritize improvements. This is an evaluation set, not training data: do not tune the model or crop geometry against these cards and then treat the same scores as independent validation.

The current 16 reference cards and photos are fictional test fixtures with no
real people or meet entries. They are included for public development/testing;
historical score summaries below refer to older versions of these fixtures.

## Fixed test set

- Ground truth: [`tests/reference_data.csv`](../tests/reference_data.csv)
- Photos: [`tests/testfotos/`](../tests/testfotos/)
- Expected set: 16 records, one photo per card, mapped by `image_filename`.
- The baseline must record the dataset, crop/schema, and model versions and the run date.
- If a card or photo is corrected, update the reference CSV and document that change; do not silently change the ground truth between runs.

Run notes below are historical summaries from earlier photo versions. Those
photos and the generated result CSVs have been removed from the repository, so
the old scores cannot be reproduced from the current fixture set. New result
files are written under the ignored `tests/results/` directory.

## Fields and scoring

Score these nine visible card fields separately across all 16 cards:

1. Name
2. Vorname
3. Jahrgang
4. Geschlecht
5. Strecke
6. Lage
7. Lauf
8. Bahn
9. Erzielte Zeit

Zeitnehmer/timekeeper remains in the application, cards, and reference CSV but is
excluded from all current evaluation scoring. Historical results below retain
their original ten-field/160-observation denominators and are not directly
comparable to new runs.

Each card-field comparison is binary: **100 points** for a correct detection and **0 points** for a wrong, blank, missing, or unavailable result. A field score is the mean of its 16 comparisons (0–100). The run score is the mean of all **144** card-field comparisons (equivalently, the mean of the nine field scores); it is not an average of per-card scores.

Before comparison, trim and case-fold text and collapse repeated whitespace. Preserve letters and diacritics. For Strecke, accept numeric metres or an optional `m` suffix/space. Accept the correction policy's exact stroke aliases. Compare year, heat, and lane as exact digits. Compare time as a duration, so equivalent supported notations for the same minutes, seconds, and fractional seconds match. Do not silently correct spelling or infer missing values.

Geschlecht is one visible field. It earns 100 only when the expected checkbox is detected as checked and the other checkbox as unchecked. An unknown, ambiguous, or contradictory pair earns 0.

Alignment failure, unsupported layout, empty crop, inference failure, unavailable model, and blank output all score 0 for each affected field. Do not drop failed cards from the denominator. Report alignment success and field-level correct counts alongside scores so a low score can be distinguished from an infrastructure failure.

## Repeatable run procedure

For the full event-create/import/recognize/unchanged-approve/export evaluation
with new photos, see [Wettkampf workflow evaluation](feature-designs/wettkampf-workflow-evaluation.md).
It separates metadata supplied by the event from genuine OCR correctness.
The procedure below evaluates only the image-recognition pipeline.

1. Confirm every CSV photo path exists and the reference set contains 16 unique card numbers and filenames.
2. Run the benchmark from the repository root using the local recognizer and the same alignment/cropping path as the application. Give each run a new output filename; the runner refuses to overwrite results.

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/evaluate_reference_dataset.py \
     --output tests/results/ocr-run-001.csv
   ```

3. Preserve one result row per card and visible field, including expected value, detected value, points, status/reason, alignment layout, and model/crop/schema version. Avoid recording unrelated personal or system data.
4. Write a summary with each field's correct count and score, the overall score, and alignment/inference failure counts.
5. Save the first run as a baseline. For future changes, compare the same fixed set and versions, inspect score deltas by field, and retain prior results rather than overwriting them.
6. Once fixes are selected from this development set, collect a separate permission-cleared holdout set before making accuracy claims. Do not use the development-set score as a holdout result.

## Improvement plan

Work in this order, using the field scores and failure reasons to choose each next task:

1. **Validate the test inputs and layout route.** Confirm the photographed card version, marker recognition, orientation, alignment quality, and selected crop schema. Fix routing or rectification failures before tuning OCR.
2. **Measure and correct crop geometry.** Compare each crop with the handwritten region on the aligned photo. Correct crop bounds, normalization, and time-region handling for the actual printed layout; add focused crop tests and retain visual overlays for review.
3. **Improve checkbox decisions.** Measure checked, unchecked, and ambiguous marks separately; tune thresholds only against labeled examples and keep uncertain marks as unknown instead of guessing.
4. **Improve text recognition by field.** Prioritize fields with low exact-match scores. Verify preprocessing and line width/scale; evaluate model candidates on the development set without changing its ground truth.
5. **Harden field interpretation.** Add only justified, field-specific normalization for values such as time and distance. Keep raw OCR output available and route uncertain or invalid values to review rather than silently rewriting them.
6. **Expand and gate evaluation.** Add varied handwriting, card versions, lighting, rotation, and blank/ambiguous marks to a permission-cleared holdout set. Track per-field scores and failures on every relevant change. Set acceptance thresholds only after the product owner reviews the baseline and holdout behavior.

## First-round baseline

- **Run time:** 2026-11-09 18:37:14 UTC
- **Model / schema / crop:** `de-htr-v2.0.0` / `startkarte-v1` / `startkarte-crops-v4`
- **Detected layout:** `card-layout-a6-v1`
- **Photos aligned:** 16/16 accepted
- **Scoring:** 160 card-field comparisons; correct = 100, incorrect or unavailable = 0
- **Overall run score:** **47/160 correct = 29.38/100**
- **Detailed result CSV:** removed from the repository; the historical summary is retained here.

| Field | Correct | Score |
|---|---:|---:|
| Name | 4/16 | 25.00 |
| Vorname | 1/16 | 6.25 |
| Jahrgang | 11/16 | 68.75 |
| Geschlecht | 0/16 | 0.00 |
| Strecke | 4/16 | 25.00 |
| Lage | 6/16 | 37.50 |
| Lauf | 9/16 | 56.25 |
| Bahn | 11/16 | 68.75 |
| Erzielte Zeit | 0/16 | 0.00 |
| Zeitnehmer | 1/16 | 6.25 |

### First-round observations

- Alignment succeeded for every photo, so the low score is downstream of card detection.
- The inspected photos show the earlier boxed card design, but all 16 are routed to `card-layout-a6-v1`. This is a likely layout/crop mismatch to investigate first; the score alone does not prove whether layout routing, crop geometry, or handwriting recognition is the root cause.
- `Jahrgang` and `Bahn` currently score highest; `Geschlecht` and `Erzielte Zeit` score zero. Names and timekeeper entries also need focused review.
- Treat these scores as a development baseline only. Fix or verify layout routing before using this same set to judge OCR-model improvements, and obtain a separate holdout set before making accuracy claims.

## Run 002: updated line-layout cards

- **Run time:** 2026-11-09 18:50:46 UTC
- **Inputs:** the 16 unsuffixed filenames in the reference CSV. The original photos now have a `-v1` suffix and were not used in this run.
- **Detector and scoring:** unchanged from the baseline.
- **Model / schema / crop:** `de-htr-v2.0.0` / `startkarte-v1` / `startkarte-crops-v4`
- **Detected layout:** `card-layout-a6-v1`
- **Photos aligned:** 15/16 accepted. Card 12 (`karte-12-wolf-elias.jpg`) returned `error.alignment_uncertain`; all ten fields remain in the denominator with zero points.
- **Overall run score:** **0/160 correct = 0.00/100**, compared with **29.38/100** for the original photos.
- **Detailed result CSV:** removed from the repository; the historical summary is retained here.

| Field | Correct | Score |
|---|---:|---:|
| Name | 0/16 | 0.00 |
| Vorname | 0/16 | 0.00 |
| Jahrgang | 0/16 | 0.00 |
| Geschlecht | 0/16 | 0.00 |
| Strecke | 0/16 | 0.00 |
| Lage | 0/16 | 0.00 |
| Lauf | 0/16 | 0.00 |
| Bahn | 0/16 | 0.00 |
| Erzielte Zeit | 0/16 | 0.00 |
| Zeitnehmer | 0/16 | 0.00 |

The new physical layout is not yet reflected in the detector's fixed crop geometry.
For example, card 01's name crop reads `Väme:` and its course/position crops read
parts of the TSV instruction rather than the intended handwritten entries.
This run measures the unchanged detector against a changed layout, not whether
writing lines are inherently better or worse than boxes. No detector improvements
were made as part of this scoring run.

## Run 003: corrected line-layout crops

- **Run time:** 2026-11-09 19:13:08 UTC
- **Inputs and scoring:** the same 16 unsuffixed photos, unchanged references and comparison rules.
- **Model / schema / crop:** `de-htr-v2.0.0` / `startkarte-v1` / `startkarte-crops-v5`
- **Current layout:** `card-layout-a6-v2`; the boxed A6 layout is deprecated. Marker alignment now selects the line layout directly, without attempting to distinguish or support the old boxed photos.
- **Changes:** nine handwriting crops placed after inline labels and above writing rules; one continuous time crop; gender crops restricted to checkbox interiors. No model, checkbox thresholds, aliases, year expansion, or scoring changes.
- **Photos aligned:** 15/16; card 12 still requires manual alignment.
- **Overall run score:** **83/160 correct = 51.88/100**, up from **0.00/100** for the same photos with the previous crop map.
- **Detailed result CSV:** removed from the repository; the historical summary is retained here.

| Field | Correct | Score |
|---|---:|---:|
| Name | 11/16 | 68.75 |
| Vorname | 9/16 | 56.25 |
| Jahrgang | 9/16 | 56.25 |
| Geschlecht | 14/16 | 87.50 |
| Strecke | 5/16 | 31.25 |
| Lage | 1/16 | 6.25 |
| Lauf | 14/16 | 87.50 |
| Bahn | 12/16 | 75.00 |
| Erzielte Zeit | 4/16 | 25.00 |
| Zeitnehmer | 4/16 | 25.00 |

Visual crop review confirms that the handwritten values, rather than printed labels,
now occupy the text regions. Some new cards use shorthand absent from the reference:
for example, card 04 shows `'10` for the year and `R` for Lage, while the reference
expects `2010` and `Rücken`. These remain zero under the unchanged scoring rules.
OCR-inserted whitespace in time strings also remains significant under the existing
duration parser. Alias handling, time parsing improvements, and the remaining
alignment/recognition failures are separate follow-up work, not crop changes.

## Run 005: configurable Lage postprocessing

- **Run time:** 2026-11-09 19:40:55 UTC
- **Inputs and scoring:** the same 16 unsuffixed photos, unchanged references and comparison rules.
- **Model / schema / crop:** `de-htr-v2.0.0` / `startkarte-v1` / `startkarte-crops-v5`
- **Current layout:** `card-layout-a6-v2`
- **Changes:** shared app/benchmark postprocessing with configurable Lage values, exact aliases, and bounded unique edit-distance matching. Raw OCR is retained in storage, review, and benchmark output. No numeric, time, year, model, or crop changes.
- **Postprocessing:** `postprocessing-v1`; the CSV records the policy SHA-256 fingerprint.
- **Photos aligned:** 15/16; card 12 still requires manual alignment and contributes ten zero-point fields.
- **Overall run score:** **90/160 correct = 56.25/100**, up from **51.88/100** before postprocessing.
- **Detailed result CSV:** removed from the repository; the historical summary is retained here.

| Field | Correct | Score |
|---|---:|---:|
| Name | 11/16 | 68.75 |
| Vorname | 9/16 | 56.25 |
| Jahrgang | 9/16 | 56.25 |
| Geschlecht | 14/16 | 87.50 |
| Strecke | 5/16 | 31.25 |
| Lage | 8/16 | 50.00 |
| Lauf | 14/16 | 87.50 |
| Bahn | 12/16 | 75.00 |
| Erzielte Zeit | 4/16 | 25.00 |
| Zeitnehmer | 4/16 | 25.00 |

Position matching uses explicit aliases before fuzzy matching. Fuzzy matching is
limited to words of at least three characters and a unique nearest canonical
value within the configured edit budget. Ties and distant matches remain unchanged.
No reference values are used to correct predictions. In this historical run,
`D` mapped to `Delphin`, a separate canonical value; that policy was corrected in
run 006 following confirmation that Delphin and Schmetterling are synonymous.

## Run 006: synonymous Delphin and Schmetterling

- **Run time:** 2026-11-09 20:24:36 UTC
- **Inputs and scoring:** the same 16 unsuffixed photos, unchanged references and comparison rules.
- **Model / schema / crop:** `de-htr-v2.0.0` / `startkarte-v1` / `startkarte-crops-v5`
- **Current layout:** `card-layout-a6-v2`
- **Changes:** the configurable canonical value `Schmetterling` now accepts `S`, `D`, and `Delphin` as exact aliases. No matching algorithm, numeric, time, year, model, or crop changes.
- **Postprocessing:** `postprocessing-v1`; the changed policy has its own SHA-256 fingerprint in the CSV.
- **Photos aligned:** 15/16; card 12 still requires manual alignment.
- **Overall run score:** **91/160 correct = 56.88/100**, up from **56.25/100** in run 005.
- **Detailed result CSV:** removed from the repository; the historical summary is retained here.

| Field | Correct | Score |
|---|---:|---:|
| Name | 11/16 | 68.75 |
| Vorname | 9/16 | 56.25 |
| Jahrgang | 9/16 | 56.25 |
| Geschlecht | 14/16 | 87.50 |
| Strecke | 5/16 | 31.25 |
| Lage | 9/16 | 56.25 |
| Lauf | 14/16 | 87.50 |
| Bahn | 12/16 | 75.00 |
| Erzielte Zeit | 4/16 | 25.00 |
| Zeitnehmer | 4/16 | 25.00 |

Card 11's raw `D` now correctly resolves to `Schmetterling`, adding one correct
field. All other field scores are unchanged. The prior CSV remains intact so the
policy change is auditable.

## Run 007: time/year normalization and review inputs

- **Run time:** 2026-11-09 20:33:39 UTC
- **Inputs and scoring:** the same 16 unsuffixed photos, unchanged references and comparison rules.
- **Model / schema / crop:** `de-htr-v2.0.0` / `startkarte-v1` / `startkarte-crops-v5`
- **Current layout:** `card-layout-a6-v2`
- **Changes:** shared postprocessing normalizes recognized times to `M:SS,ff`, retaining a third decimal digit when necessary, and expands explicitly apostrophe-prefixed two-digit years to the latest matching nonfuture year. No numeric race-field, model, or crop changes.
- **Review integration:** "Startkarte prüfen" populates inputs with corrected suggestions for new recognition and reopened unconfirmed OCR. Raw OCR stays visible; invalid time/year text remains editable with a localized warning. Manual and confirmed values are protected. Opening a card does not write to storage; saving review persists the displayed values.
- **Postprocessing:** `postprocessing-v2`; the unchanged race policy fingerprint is recorded in the CSV.
- **Photos aligned:** 15/16; card 12 still requires manual alignment.
- **Overall run score:** **98/160 correct = 61.25/100**, up from **56.88/100** in run 006.
- **Detailed result CSV:** removed from the repository; the historical summary is retained here.

| Field | Correct | Score |
|---|---:|---:|
| Name | 11/16 | 68.75 |
| Vorname | 9/16 | 56.25 |
| Jahrgang | 9/16 | 56.25 |
| Geschlecht | 14/16 | 87.50 |
| Strecke | 5/16 | 31.25 |
| Lage | 9/16 | 56.25 |
| Lauf | 14/16 | 87.50 |
| Bahn | 12/16 | 75.00 |
| Erzielte Zeit | 11/16 | 68.75 |
| Zeitnehmer | 4/16 | 25.00 |

Time improves by seven correct fields: cards 01, 02, 04, 05, 10, 13, and 16.
For example, `42, 18` becomes `0:42,18` and `1: 34,92` becomes `1:34,92`.
All other scores are unchanged. The remaining year misses contain missing or
misrecognized digits rather than an explicitly apostrophe-prefixed short year,
so conservative expansion does not improve this photo set's Jahrgang score.

Validation: the full suite passes **208 tests**, including real Tk input-value
and warning checks under a virtual display, new-recognition persistence, reopened
review/save behavior, raw-OCR retention, protected-value safeguards, invalid
inputs, millisecond precision, and deterministic short-year expansion.

## Run 008: birth-year OCR apostrophe correction

- **Run time:** 2026-11-09 20:43:02 UTC
- **Inputs and scoring:** the same 16 unsuffixed photos, unchanged references and comparison rules.
- **Model / schema / crop:** `de-htr-v2.0.0` / `startkarte-v1` / `startkarte-crops-v5`
- **Current layout:** `card-layout-a6-v2`
- **Changes:** plausible short-year expansions are constrained to `minimum_birth_year` (default `1927`) through the current year. For exactly three OCR digits beginning with `1`, the first digit may represent a misread apostrophe; correction requires exactly one matching year in that range. Bare two-digit years, unrelated OCR errors, and century ties remain unchanged.
- **Review integration:** the existing shared postprocessing path applies this correction to both newly recognized and reopened unconfirmed OCR suggestions. Raw OCR is retained, and manual/confirmed values remain protected.
- **Postprocessing:** `postprocessing-v3`; the updated policy SHA-256 fingerprint is recorded in the CSV. Existing policies without `minimum_birth_year` remain supported and default to `1927`.
- **Photos aligned:** 15/16; card 12 still requires manual alignment.
- **Overall run score:** **101/160 correct = 63.12/100**, up from **61.25/100** in run 007.
- **Detailed result CSV:** removed from the repository; the historical summary is retained here.

| Field | Correct | Score |
|---|---:|---:|
| Name | 11/16 | 68.75 |
| Vorname | 9/16 | 56.25 |
| Jahrgang | 12/16 | 75.00 |
| Geschlecht | 14/16 | 87.50 |
| Strecke | 5/16 | 31.25 |
| Lage | 9/16 | 56.25 |
| Lauf | 14/16 | 87.50 |
| Bahn | 12/16 | 75.00 |
| Erzielte Zeit | 11/16 | 68.75 |
| Zeitnehmer | 4/16 | 25.00 |

Three additional birth years are correct: card 02 `111` becomes `2011`,
card 04 `110` becomes `2010`, and card 07 `114` becomes `2014`.
All other scores, including time, are unchanged.

Validation: **230 tests passed**, including a reproduced failure for `111`,
a real Tk check that the year input contains `2011` while raw `111` is visible,
new-recognition and reopened-review persistence, range boundaries, century
ambiguity, invalid configuration, and backward-compatible policy loading.

## Run 009: optional meter-unit normalization

- **Run time:** 2026-11-09 21:02:24 UTC
- **Inputs and scoring:** the same 16 unsuffixed photos, unchanged references and comparison rules.
- **Model / schema / crop:** `de-htr-v2.0.0` / `startkarte-v1` / `startkarte-crops-v5`
- **Current layout:** `card-layout-a6-v2`
- **Changes:** positive whole-number distances with an optional meter unit normalize to `N m`: `50`, `50m`, and `50 m` all become `50 m`. Leading zeros and unit case are normalized. No fuzzy digit correction, race-distance restrictions, or model/crop changes.
- **Review integration:** the shared postprocessing path applies normalization to newly recognized and reopened unconfirmed OCR suggestions. Raw OCR is retained; manual and confirmed values remain protected.
- **Postprocessing:** `postprocessing-v4`; the unchanged race policy fingerprint is recorded in the CSV.
- **Photos aligned:** 15/16; card 12 still requires manual alignment.
- **Overall run score:** **111/160 correct = 69.38/100**, up from **63.12/100** in run 008.
- **Detailed result CSV:** removed from the repository; the historical summary is retained here.

| Field | Correct | Score |
|---|---:|---:|
| Name | 11/16 | 68.75 |
| Vorname | 9/16 | 56.25 |
| Jahrgang | 12/16 | 75.00 |
| Geschlecht | 14/16 | 87.50 |
| Strecke | 15/16 | 93.75 |
| Lage | 9/16 | 56.25 |
| Lauf | 14/16 | 87.50 |
| Bahn | 12/16 | 75.00 |
| Erzielte Zeit | 11/16 | 68.75 |
| Zeitnehmer | 4/16 | 25.00 |

Distance improves by ten correct fields. The only remaining distance miss is the
card with failed alignment. All other field scores are unchanged. Scoring rules
were not relaxed: the detector now produces explicit meter values for bare numbers.

Validation: **106 targeted tests passed**, covering optional units, whitespace,
leading zeros, raw-OCR preservation, idempotency, invalid/ambiguous inputs,
new-recognition persistence, reopened review/save, and the actual Tk distance input.

## Run 010: German TrOCR Large for Name and Vorname

- **Run time:** 2026-11-09 22:04:05 UTC
- **Question:** does a larger German handwriting model improve surname and first-name recognition on the existing photos?
- **Inputs and scoring:** the same 16 unsuffixed photos and unchanged references. Only Name and Vorname are evaluated: **32 observations**, including two zero-point fields for card 12's failed alignment. The same NFC/case/whitespace comparison and binary 100/0 scoring apply; no name dictionary or reference-based correction.
- **Baseline:** run 009, DE·HTR v2.0.0, using the exact same crop geometry.
- **Candidate:** [`fhswf/TrOCR_german_handwritten`](https://huggingface.co/fhswf/TrOCR_german_handwritten), German TrOCR Large, approximately 558 million parameters. Revision pinned to `f43d8831af99105e9dbb718fcfc8373c0010174d`.
- **Schema / crop / layout:** `startkarte-v1` / `startkarte-crops-v5` / `card-layout-a6-v2`.
- **Preprocessing:** unchanged field crops, converted to RGB and passed through the model's bundled TrOCR processor (384 x 384 resize and configured normalization). No additional handwriting-tight cropping.
- **Inference:** CPU FP32, four PyTorch threads, batch size one, greedy decoding (`num_beams=1`, `do_sample=False`), maximum 64 new tokens; the checkpoint's other generation settings are retained. All generated sequences ended normally.
- **Runtime:** Python 3.14.4, PyTorch `2.15.0+cpu`, Transformers `5.22.2`, isolated from the desktop environment.
- **Photos aligned:** 15/16, as in run 009.
- **Detailed result CSV:** removed from the repository. It recorded baseline/candidate text and points, model revision, and inference time.
- **Historical reproduction:** commit `fc6b058` contains the benchmark script and optional dependency instructions. The unsuccessful experiment's implementation was subsequently reverted; this narrative is retained as historical documentation, but its result CSV and photos are not.

| Field | Run 009 correct | Run 009 score | TrOCR correct | TrOCR score |
|---|---:|---:|---:|---:|
| Name | 11/16 | 68.75 | 4/16 | 25.00 |
| Vorname | 9/16 | 56.25 | 2/16 | 12.50 |
| Combined names | 20/32 | 62.50 | 6/32 | 18.75 |

**Outcome: do not switch the app to this model on the strength of this run.**
There are fourteen regressions and no newly correct fields. Examples include
`Müller` becoming `Tülker`, `Ben` becoming `Bew`, and `Mila` becoming `Mika`.
The six successful predictions are Fischer, Weber, Becker, Koch, Lukas, and Oskar
(case-insensitive comparison). A hypothetical hybrid replacing only the two name
fields would therefore score **97/160 = 60.62/100**, versus **111/160 = 69.38/100**
in run 009. This is a projection from saved results, not a separate full-card run.

### Laptop feasibility

- Intel Core i7-12700H, approximately 64 GB RAM; the NVIDIA GPU was not used.
- Peak process resident memory: **3.03 GiB**, measured with `/usr/bin/time -v`.
- Thirty actual crop inferences: **173.02 seconds**, averaging **5.77 seconds per
  field**, range **4.16–7.82 seconds**. Roughly 11.5 seconds for both names.
- Evaluation including alignment and CSV writing: **182.25 seconds**.
- Initial processor/model loading including network download: **159.02 seconds**.
  Complete process wall time including startup: **347.05 seconds**.
- All images remained local; only model assets were downloaded. Model weights
  are cached locally, not committed or bundled; the model declares AFL-3.0.

This proves the larger model runs within available laptop RAM, **not** that it
is a better recognizer for these field crops. Its published CER is not directly
comparable to our exact-field scores. Different crop preprocessing, beam search,
or domain fine-tuning remain untested possibilities, not demonstrated fixes.
The desktop model and production dependencies are unchanged.

Validation: the real run produced all 32 unique observations with unchanged
alignment failures. Scores and timing aggregates were independently checked from
the CSV. Script syntax, CLI help without optional dependencies, and refusal to
overwrite historical results were also verified.

## New PDF-form photographs: crop review (2026-11-12)

The 16 fresh webcam photographs of the filled PDF forms all align with four
markers. The PDF has different name baselines and checkbox positions from the
HTML draft. It now routes to `card-layout-a6-v3` using the two long name rules;
the existing `card-layout-a6-v2` bounds remain unchanged. Crop version is
`startkarte-crops-v6`. The form map excludes printed labels, accommodates taller
handwriting, and centres gender crops on the actual PDF widgets. Checkbox
classification accommodates thick printed crosses while retaining conservative
handling of noise, faint marks and solid fills. `K` and `Kraul` are exact
Freistil aliases in the default correction policy and evaluation.

The full workflow creates 14 events, captures/recognizes 16 cards, approves them
without manual changes, and exports every event. Zeitnehmer is excluded.

| Field | Export / 16 | Raw OCR / 16 |
|---|---:|---:|
| Name | 16 | 16 |
| Vorname | 14 | 14 |
| Jahrgang | 16 | 16 |
| Geschlecht | 16 | 16 |
| Strecke | 16 | 16 |
| Lage | 16 | 9 |
| Lauf | 14 | 14 |
| Bahn | 16 | 16 |
| Zeit | 10 | 6 |
| **Total** | **134/144 (93.1%)** | **123/144 (85.4%)** |

Before correction the same photographs scored 117/144 exported and 88/144 raw.
Exported distance, stroke and gender are event-supplied, not OCR achievements.
Time formatting corrections explain some further export/raw differences.
The detailed run bundle, expected/export/raw CSVs, copied images and crop
overlays have been removed. The summary above is a historical note, not a
reproducible result; use the [workflow evaluator](feature-designs/wettkampf-workflow-evaluation.md)
to create ignored local output when permission-cleared inputs are available.

These are development-set measurements after crop calibration, not independent
validation. Several geometry variants were evaluated and retained as separate
runs. Card 03 visibly contains `1:34,92`, while the unchanged reference says
`00:51,27`; it remains scored incorrect, but this is an input/reference mismatch.
Time and stroke interpretation are the main remaining weaknesses.
