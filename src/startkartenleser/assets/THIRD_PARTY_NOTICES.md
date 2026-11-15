# Third-party notices

This application uses the following third-party software and model artifacts.
The listed upstream license terms apply to those components; the application's
own code is licensed separately.

## Runtime and development packages

| Component | Pinned version | License | Source |
| --- | ---: | --- | --- |
| Pillow | 13.0.0 | HPND | <https://github.com/python-pillow/Pillow> |
| NumPy | 2.5.4 | BSD-3-Clause | <https://github.com/numpy/numpy> |
| OpenCV (headless) | 4.14.0.94 | Apache-2.0 | <https://github.com/opencv/opencv> |
| ONNX Runtime (CPU) | 1.31.1 | MIT | <https://github.com/microsoft/onnxruntime> |
| pytest (development) | 9.2.0 | MIT | <https://github.com/pytest-dev/pytest> |
| flatbuffers | 25.12.19 | Apache-2.0 | <https://github.com/google/flatbuffers> |
| protobuf | 7.36.2 | BSD-3-Clause | <https://github.com/protocolbuffers/protobuf> |

Additional resolver packages are pinned in `requirements.lock`; their
distribution metadata includes the applicable license notices.

## Browser UI

The bundled UI uses React, React DOM, Material UI, Material Icons, Emotion and
their runtime dependencies under their upstream licenses. Exact resolved
versions are recorded in `frontend/package-lock.json`. The frontend build
preserves full runtime dependency license notices in the distributed
`web_static/THIRD_PARTY_LICENSES.txt` file. Vite, TypeScript, Vitest and Testing
Library are development tooling, not additional Python runtime requirements.

## DE·HTR v2 model

The bundled `assets/models/de-htr-v2/model.onnx` and `config.json` are from
[`naeyn/de-htr-web-v2`](https://huggingface.co/naeyn/de-htr-web-v2), revision
`6241c1ff0fd42725e0dc46fcd3217469cac851bb`, corresponding to the v2.0.0 model
release. The model weights are identified by their publisher as Apache-2.0 for
rights held by the project. The full Apache-2.0 terms are included as
`assets/models/de-htr-v2/LICENSE-Apache-2.0.txt`; SHA-256 values are enforced by
`scripts/fetch_model.py`.

The model was trained using ScaDS.AI German handwriting data (CC BY 4.0) and
`fhswf/german_handwriting` (AFL-3.0). The publisher's complete dataset
attribution and provenance notice is bundled as
`assets/models/de-htr-v2/NOTICE-training-data.md`; the upstream model card is
also bundled in that directory. Training source images are not redistributed.
