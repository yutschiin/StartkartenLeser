# ADR-0005: Select DE·HTR v2 for the desktop OCR-enabled MVP

- **Status:** Accepted for initial MVP integration; Startkarten field-quality gate pending
- **Date:** 2026-11-03

## Context

The MVP needs local recognition of modern German handwriting in fixed Startkarte fields, with no network transfer of card data. The first target machine is Ubuntu 26.04 x86_64 with an Intel Core i7-12700H (14 cores / 20 threads), 62 GiB RAM, Python 3.14, and GeForce RTX 3050 Ti Mobile. The desktop architecture already defines a replaceable `HandwritingRecognizer` boundary.

The model must be usable from Python on CPU, small enough to ship, support German handwriting, and fit line crops generated from the card template. No representative labeled completed Startkarten are available yet. Therefore the engine can be selected as the first integration target, but its external benchmark cannot establish accuracy on Startkarten and must not become a product accuracy claim.

## Decision

- Select **DE·HTR v2** (`naeyn/de-htr-web-v2`) as the default recognizer for the initial desktop MVP, running its int8 ONNX model with ONNX Runtime's CPU execution provider.
- Pin model release v2/source tag `v0.2.0`, `model.onnx` and `config.json` hashes from its model card. Bundle those assets and their notices so recognition works offline after app installation.
- Use exact model contract: one pre-cropped modern-German handwriting line, grayscale input, height 64 with aspect ratio preserved, width capped at 1024, white padding to a multiple of four, input float `[0,1]`, v2 alphabet and greedy CTC decode. Do not pass full-card images to this line recognizer.
- Keep card normalization, fixed field regions, crop creation, checkbox-mark detection, and domain mapping outside the model-specific adapter. The OCR adapter returns untrusted text candidates with source `OCR`; confidence is nullable and not calibrated. Every candidate requires human review.
- Keep manual entry and recoverable failure behavior for every configuration. Persist the accepted image and card draft before alignment or recognition. Never transmit card data, and do not log crops, transcriptions, or personal fields.
- Run local, permission-cleared, field-level evaluation before making any Startkarten accuracy claims. Until allowed `Strecke`/`Lage` options and separation rules are supplied, preserve that area as a shared raw candidate and require manual assignment. Keep gender marks on a separate conservative detector path; unreadable states remain unknown.

## Why this engine

The laptop has ample CPU and memory, as well as an NVIDIA GPU. Still, CPU is the initial default: DE·HTR v2 is a compact 10.4 MB int8 model, CPU avoids CUDA-specific packaging and driver setup, and it keeps the first install predictable. Measure end-to-end CPU latency on this laptop before considering an optional GPU provider. DE·HTR v2 is specifically for modern German handwriting, is line-level, and publishes a direct Python/ONNX Runtime example. The Hugging Face model card reports 8.01% CER and 32.3% WER on 601 writer-disjoint German handwriting lines. The distribution includes an Apache-2.0 model notice and training-data attribution; those notices will accompany any bundled artifact.

ONNX Runtime has a CPU package with a Linux x86_64 CPython 3.14 wheel. This avoids the current PaddlePaddle wheel/support gap on Python 3.14 and avoids installing CUDA or a large model framework for inference. Laptop suitability is an engineering choice, not a Startkarten accuracy conclusion.

## Alternatives considered

| Candidate | Decision |
| --- | --- |
| **PaddleOCR PP-OCRv5/v6** | Not selected for initial integration. General multilingual OCR has useful handwriting improvements, but the German handwriting fit is less direct. Its default full-page pipeline is more than the fixed-field desktop needs, and PaddlePaddle's current documented/available wheel matrix does not cover this Python 3.14 environment. |
| **Kraken** | Not selected for initial app integration. It is a strong trainable HTR framework and useful for future domain-specific evaluation, but its current Python support is 3.10–3.13 (not 3.14), has more runtime/segmentation integration weight, and its historical-manuscript orientation is a less direct fit than DE·HTR v2's modern German line model. |
| **fhswf TrOCR German Handwritten** | Not selected. It is German-specific and line-level, but the published model has about 0.6B parameters and an AFL-3.0 license; the small community checkpoint is 61.6M parameters but its card reports only approximate evaluation and has the same AFL-3.0 license. DE·HTR v2 is considerably smaller, ONNX-native, and Apache-2.0 for rights held by its release. |
| **Tesseract 5 (`deu`)** | Rejected as the primary handwritten recognizer. It remains useful for printed text/control testing, but its layout and recognition assumptions are primarily for print and do not fit free-form handwriting well. |
| **Microsoft TrOCR base handwritten** | Rejected. Its public baseline is trained on IAM English handwriting, requires line crops, and has multi-gigabyte weights/runtime compared with the selected small German-specific ONNX artifact. |
| **Historic German page-level VLM / LightOnOCR** | Rejected for this workflow. It targets whole historical pages/Kurrent and needs a much larger model; the card fields are modern, fixed, short lines. |

## Consequences

- Python 3.14 remains usable for the selected inference path; pin/test ONNX Runtime and NumPy/Pillow versions for the supported platform.
- Add one field-crop pipeline and a separate mark detector; DE·HTR v2 does not perform page layout or checkbox recognition.
- Model-reported CER is external evidence only. A representative Startkarten test set and agreed field-level acceptance thresholds are required before claims or accuracy-based promotion.
- Image normalization/alignment is a first-class MVP component. If alignment confidence is poor, the card remains available for manual entry rather than receiving guessed candidates.
- Review UI must present all recognized values as suggestions and keep manual correction usable when the model fails or is wrong.
- Record ONNX Runtime/model/config versions and hashes. Re-check dependencies, model/data notices, and artifact hashes before packaging updates.

## References checked 2026-11-03

- [DE·HTR v2 model card](https://huggingface.co/naeyn/de-htr-web-v2)
- [DE·HTR source repository](https://github.com/naeyn/de-htr-web)
- [ONNX Runtime Python guide](https://onnxruntime.ai/docs/get-started/with-python.html)
- [ONNX Runtime PyPI platform/Python wheels](https://pypi.org/project/onnxruntime/)
- [PaddleOCR PP-OCRv5 multilingual recognition docs](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.en.md)
- [PaddlePaddle Python 3.14 support issue](https://github.com/PaddlePaddle/Paddle/issues/79527)
- [Kraken on PyPI](https://pypi.org/project/kraken/)
- [fhswf German handwriting TrOCR model card](https://huggingface.co/fhswf/TrOCR_german_handwritten)
- [Tesseract handwriting limitations discussion](https://github.com/tesseract-ocr/tesstrain/issues/395)
