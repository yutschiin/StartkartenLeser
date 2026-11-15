# ADR-0005: DE·HTR v2 for local handwriting recognition

- **Status:** Accepted for local recognition; Startkarten accuracy is not
  certified.
- **Date:** 2026-11-03

## Context

The application needs local recognition of German handwriting on fixed card
fields. Card images and transcriptions must not be sent to a hosted OCR service.
The recognizer must work on CPU and remain replaceable independently of the card
alignment and review workflow.

## Decision

- Use the int8 ONNX model from **DE·HTR v2** with ONNX Runtime's CPU provider.
- Pin model release v2 (`v0.2.0`) and verify model/configuration checksums. Bundle
  the model and required attribution/license files. If assets are missing or
  invalid, setup downloads the pinned files; inference itself is local.
- Pass aligned, pre-cropped handwriting lines to the recognizer. Card alignment,
  field crops, checkbox detection, validation and correction remain separate
  application responsibilities.
- Treat OCR as untrusted editable suggestions. Keep manual entry and recoverable
  behavior for missing models, unsafe alignment and recognition failures. Never
  auto-approve OCR results or overwrite user-confirmed values.
- Do not claim Startkarten accuracy from the model publisher's benchmark or the
  included development photos. Any product accuracy claim requires a separate,
  permission-cleared, representative evaluation set.

## Rationale

DE·HTR v2 is a compact German line-recognition model distributed as ONNX, so it
fits the fixed-field workflow without a large ML framework or GPU dependency.
CPU inference avoids platform-specific GPU setup. Its published benchmark is
evidence about the publisher's dataset only, not about Startkarten.

## Consequences

- The application provisions model files during setup and can recognize cards
  offline once those files are present.
- Checkbox marks use a separate conservative detector; text OCR does not decide
  mark state.
- Recognition and postprocessing changes require tests and checksum/version
  review. See the [OCR evaluation guide](../ocr-test-strategy.md).

Model source: [DE·HTR v2 on Hugging Face](https://huggingface.co/naeyn/de-htr-web-v2).
