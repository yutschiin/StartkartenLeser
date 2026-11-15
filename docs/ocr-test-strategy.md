# OCR evaluation

The 16 cards in `tests/testfotos/` and `tests/reference_data.csv` are fictional
development fixtures. They are useful for repeatable regression checks, but they
are not an independent holdout: alignment, crops and correction rules have been
developed against them. Do not present their scores as production accuracy.

Run the image-recognition benchmark from the repository root:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_reference_dataset.py \
  --output tests/results/ocr-run-001.csv
```

Use a new output filename for each run; existing result files are not
overwritten. The benchmark scores nine fields per card (144 comparisons for the
current fixtures); timekeeper is not scored. Alignment or inference failures and
blank readings remain in the denominator. The output records raw and corrected
recognition plus model, layout, crop and policy versions.

For a complete Wettkampf capture-to-CSV evaluation, use the
[workflow evaluation tool](workflow-evaluation.md). Its event metadata can supply
course, position and gender values, so exported values in those fields are not
evidence of OCR accuracy. Use a separate, permission-cleared photo set for any
new validation claim; keep images and generated results out of Git unless
deliberately approved as fixtures.
