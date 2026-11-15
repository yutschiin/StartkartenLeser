---
license: apache-2.0
language:
- de
pipeline_tag: image-to-text
library_name: onnx
datasets:
- fhswf/german_handwriting
tags:
- handwriting-recognition
- handwritten-text-recognition
- htr
- ocr
- german-handwriting
- handschrifterkennung
- ctc
- onnx
- onnxruntime-web
- browser
- offline
- wasm
- image-to-text
- german
- resnet
- bilstm
metrics:
- cer
- wer
model-index:
- name: de-htr-web-v2
  results:
  - task:
      type: image-to-text
      name: Handwritten Text Recognition (line-level)
    dataset:
      type: scads-ai-german-handwriting
      name: ScaDS.AI German Handwriting (sealed writer-disjoint test split)
    metrics:
    - type: cer
      value: 8.01
      name: Character Error Rate (int8, greedy, batch 1)
    - type: wer
      value: 32.3
      name: Word Error Rate (int8, greedy, batch 1)
---

# DE·HTR v2 — German handwriting recognition in the browser

**Offline German handwritten text recognition (HTR / Handschrifterkennung) that
runs entirely client-side: a 10.4 MB int8 ONNX model for ONNX Runtime Web, no
image upload, no per-call cost, no GPU required.**

`de-htr-web-v2` is a compact line-level CTC recognizer for **modern German
handwriting** (Kurrent/Sütterlin are out of scope). It is the successor to
[`naeyn/de-htr-web`](https://huggingface.co/naeyn/de-htr-web) v1 and beats it on
the identical sealed benchmark while carrying a fully audited, license-clean
training-data ancestry.

- **Live demo:** https://de-htr-web.vercel.app
- **Input:** one pre-cropped handwriting line image (any common format)
- **Output:** Unicode transcription via greedy CTC decoding
- **Privacy:** after the page and model load, inference makes no network requests

## Results

Benchmark: 601 handwritten lines from 78 held-out writers of the ScaDS.AI German
handwriting dataset — writer-disjoint from all training data, aligned with v1's
sealed test writers (38 shared + 40 additional unseen). Greedy CTC decode, no
language model, batch size 1 (exactly how the browser runs it). v1 was
re-evaluated under the identical protocol.

| model | lines CER ↓ | WER ↓ | size |
|---|---:|---:|---:|
| **v2 int8 (this release, `model.onnx`)** | **8.01%** | **32.3%** | 10.4 MB |
| v2 fp32 (`model-fp32.onnx`) | 8.00% | 32.3% | 40.3 MB |
| v1 int8 (previous release) | 8.61% | 33.9% | 9.84 MB |

Per-writer error is heavy-tailed (median writer ≈ 6–8% CER, hardest writers
30%+): expect noticeably better results on clean, well-scanned handwriting and
worse on faint pencil, dense corrections, or unusual styles.

## Release identity

The companion browser app ships this model as of source tag
[`v0.2.0`](https://github.com/naeyn/de-htr-web/releases/tag/v0.2.0) of
[naeyn/de-htr-web](https://github.com/naeyn/de-htr-web).

| file | SHA-256 |
|---|---|
| `model.onnx` (int8) | `b576a0a1281b9be46b2574028b75575e041b7d7cb650f063886e733467cc1499` |
| `model-fp32.onnx` | `68b46411b8236b44d0d98865909d217ef13b41f12db769993c67eeb8d6e8c45a` |
| `config.json` | `4ebd69d9d27b398ea3997b031318accc13123f6a8950def1fedc6e364cb758fa` |

Architecture: ImageNet-initialized **ResNet18 stem (through layer3) + 3×BiLSTM-256
+ CTC head**, 10.06M parameters. Grayscale input at height 64, dynamic width up
to 1024, output stride 4, 112-symbol alphabet (blank + 111 characters covering
≥ 99.99% of benchmark characters).

## ⚠️ Breaking changes vs v1

v2 is **not weight- or interface-compatible** with v1 — that is why it lives in
a separate repository. Read `config.json` (`format_version: 2`) instead of
hard-coding:

| | v1 | v2 |
|---|---|---|
| input tensor | `images`, 3-channel RGB | `image`, **1-channel grayscale** |
| normalization | external ImageNet mean/std | **inside the model** — feed raw [0,1] |
| output tensor | `log_probs` | `logits` (raw; argmax decode unchanged) |
| alphabet | 195 symbols | **112 symbols** |
| max width | 2048 | **1024** |

## Usage

### JavaScript (ONNX Runtime Web — the intended path)

```js
import * as ort from "onnxruntime-web";

const config = await (await fetch("config.json")).json();
const session = await ort.InferenceSession.create("model.onnx");

// preprocess: grayscale, resize to height 64 keeping aspect ratio,
// right-pad width to a multiple of 4 with white, scale to [0,1]
const tensor = new ort.Tensor("float32", pixels, [1, 1, 64, width]);
const { logits } = await session.run({ image: tensor });

// greedy CTC decode: per-frame argmax, collapse repeats, drop blank (index 0)
```

### Python (onnxruntime)

```python
import numpy as np, onnxruntime as ort
from PIL import Image

cfg = json.load(open("config.json"))
img = Image.open("line.png").convert("L")
w = max(4, round(img.width * 64 / img.height) // 4 * 4)
img = img.resize((w, 64))
x = np.asarray(img, dtype=np.float32)[None, None] / 255.0

session = ort.InferenceSession("model.onnx")
logits = session.run(None, {"image": x})[0]          # (1, w//4, 112)
ids = logits.argmax(-1)[0]                            # greedy CTC
text = "".join(cfg["alphabet"][i - 1] for i, prev in zip(ids, np.r_[0, ids[:-1]])
               if i != 0 and i != prev)
print(text)
```

## Training recipe

Trained from scratch (no v1 weights) on a single RTX 5070 Ti in ~3 hours:

| setting | value |
|---|---|
| init | ImageNet ResNet18 stem, no synthetic pretraining |
| data | ScaDS gold lines + word crops (weight 0.3) + 5,240 page-XML extra lines + 9,909 fhswf lines |
| schedule | 65 epochs cosine, AdamW, lr 3e-4, weight decay 1e-4, batch 32 |
| batch composition | ≥ 45% gold-line quota per batch |
| augmentation | mild deterministic geometric/photometric on real images |
| seed | 20260801 (selected on validation-line CER from two independent seeds) |

**Ablation headlines** (full table in the research repo): ImageNet stem −1.3
CER; adding the fhswf corpus −0.94; *dropping* synthetic-data batch mixing
−1.28 at matched exposure; synthetic-only pretraining saturates at 0.25
epoch-equivalents and then hurts transfer; frame-wise two-seed ensembling fails
for CTC (alignment blur). The negative synthetic results are reported
deliberately — the license-clean synthetic renderer and corpus lock ship as a
separate research artifact.

## Training data and provenance

The released weights were trained **exclusively on real handwriting**:

| corpus | license | role |
|---|---|---|
| ScaDS.AI German Line/Word Handwriting ([DOI 10.5281/zenodo.18301532](https://doi.org/10.5281/zenodo.18301532)) | CC BY 4.0 | gold lines, word crops, page-XML extra lines (train writers only) |
| [`fhswf/german_handwriting`](https://huggingface.co/datasets/fhswf/german_handwriting) | AFL-3.0 | cross-domain auxiliary training (9,909 lines; training only) |

Not in the training path of these weights: synthetic rendered text, Leipzig
corpora, VLM pseudo-labels, IAM. Splits are writer-disjoint and pinned; the
sealed test writers were never trained on. Source images are **not**
redistributed here. Full dataset-level attribution: `NOTICE-training-data.md`.

## Limitations

- Modern German handwriting only — no historical scripts (Kurrent, Sütterlin),
  no printed-text OCR guarantee, weak on heavy math/symbols.
- Line-level input: you must segment pages into lines first (the demo app crops
  lines; full-page layout analysis is out of scope for the model).
- Heavy-tailed writer difficulty (see Results) — evaluate on your own
  handwriting distribution before depending on it.
- Alphabet is 112 symbols; characters outside it (e.g. curly quotes, accented
  Romance characters) cannot be emitted.
- Greedy decode has no language model; a domain lexicon or LM rescoring layer
  can further reduce word errors downstream.

## License and attribution

Weights: **Apache-2.0** for the rights held by the project. ScaDS.AI data used
under CC BY 4.0 (Burghardt, Alzin, Nestler et al., ScaDS.AI / Universität
Leipzig; changes: cropping, grayscale normalization, NFC text normalization,
writer-disjoint re-splitting). fhswf data used under AFL-3.0 for training only.
Dataset-level attribution in `NOTICE-training-data.md`.

## Citation

```bibtex
@software{de_htr_web_v2,
  title = {DE·HTR v2: German handwriting recognition in the browser},
  author = {naeyn},
  year = {2026},
  version = {2.0.0},
  url = {https://huggingface.co/naeyn/de-htr-web-v2},
  license = {Apache-2.0}
}
```
