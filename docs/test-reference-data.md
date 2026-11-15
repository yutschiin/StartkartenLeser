# Test fixtures

The 16 cards, sample records in [`tests/reference_data.csv`](../tests/reference_data.csv),
and photos in [`tests/testfotos/`](../tests/testfotos/) are fictional. They contain
no real people or meet entries and are included for development/testing only.

The CSV is the source of truth for expected values and photo filenames; do not
duplicate its rows here. The photo set is a development set, not a holdout for
accuracy claims. See the [OCR evaluation guide](ocr-test-strategy.md) before
interpreting benchmark results.
