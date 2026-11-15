from __future__ import annotations

import hashlib
import json
from pathlib import Path
import threading

import numpy as np
from PIL import Image
import pytest

from startkartenleser.domain.contracts import RecognitionStatus
from startkartenleser.infrastructure.recognizer import (
    DEHTRRecognizer,
    ModelConfig,
    RecognitionAdapterError,
    RecognitionFailure,
    decode_greedy_ctc,
    load_model_config,
    preprocess_line,
)


def _fake_asset_files(directory: Path) -> tuple[Path, str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    model_path = directory / "model.onnx"
    config_path = directory / "config.json"
    model_path.write_bytes(b"not an executable model; unit tests inject inference")
    alphabet = "".join(chr(0x100 + index) for index in range(111))
    config = {
        "format_version": 2,
        "model": "model.onnx",
        "input_name": "image",
        "output_name": "logits",
        "image_height": 64,
        "max_width": 1024,
        "output_stride": 4,
        "blank_index": 0,
        "alphabet": alphabet,
        "preprocessing": {"scale": 1 / 255, "pad_value": 1.0},
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return model_path, _sha256(model_path), _sha256(config_path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _config() -> ModelConfig:
    alphabet = "".join(chr(0x100 + index) for index in range(111))
    return ModelConfig(
        "model.onnx", "image", "logits", 64, 1024, 4, 0, alphabet, 1 / 255, 1.0
    )


class FakeSession:
    def __init__(self, outputs, *, error: Exception | None = None, on_run=None):
        self.outputs = outputs
        self.error = error
        self.on_run = on_run
        self.calls = []
        self.closed = False

    def run(self, output_names, input_feed):
        self.calls.append((output_names, input_feed))
        if self.on_run:
            self.on_run()
        if self.error:
            raise self.error
        return self.outputs

    def close(self):
        self.closed = True


def _logits(ids: list[int], class_count: int = 112) -> np.ndarray:
    values = np.full((1, len(ids), class_count), -1.0, dtype=np.float32)
    for step, token_id in enumerate(ids):
        values[0, step, token_id] = 1.0
    return values


def _recognizer(tmp_path: Path, session: FakeSession, *, cpu_threads: int = 2):
    model_path, model_hash, config_hash = _fake_asset_files(tmp_path / "assets")
    called = []

    def factory(path: Path, threads: int):
        called.append((path, threads))
        return session

    recognizer = DEHTRRecognizer(
        model_path.parent,
        session_factory=factory,
        cpu_threads=cpu_threads,
        expected_model_sha256=model_hash,
        expected_config_sha256=config_hash,
    )
    return recognizer, called


def test_model_config_is_loaded_only_after_matching_hash(tmp_path: Path) -> None:
    _, _, config_hash = _fake_asset_files(tmp_path)

    config = load_model_config(tmp_path / "config.json", expected_sha256=config_hash)

    assert config.image_height == 64
    assert config.max_width == 1024
    assert len(config.alphabet) == 111


def test_missing_or_changed_config_has_typed_failure(tmp_path: Path) -> None:
    with pytest.raises(RecognitionAdapterError) as missing:
        load_model_config(tmp_path / "missing.json")
    assert missing.value.failure is RecognitionFailure.MODEL_MISSING

    _fake_asset_files(tmp_path)
    with pytest.raises(RecognitionAdapterError) as mismatch:
        load_model_config(tmp_path / "config.json")
    assert mismatch.value.failure is RecognitionFailure.MODEL_HASH_MISMATCH


def test_bad_model_config_values_are_rejected_after_hash_verification(tmp_path: Path) -> None:
    _fake_asset_files(tmp_path)
    path = tmp_path / "config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["format_version"] = 1
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(RecognitionAdapterError) as error:
        load_model_config(path, expected_sha256=_sha256(path))

    assert error.value.failure is RecognitionFailure.INVALID_MODEL_CONFIG


def test_preprocessing_preserves_grayscale_range_and_white_stride_padding() -> None:
    image = Image.new("RGB", (301, 30), (0, 0, 0))

    prepared = preprocess_line(image, _config())

    assert prepared.tensor.shape == (1, 1, 64, 644)
    assert prepared.tensor.dtype == np.float32
    assert prepared.padded_width % 4 == 0
    assert prepared.resized_size == (642, 64)
    assert prepared.tensor.min() == 0.0
    assert prepared.tensor.max() == 1.0
    assert np.all(prepared.tensor[0, 0, :, 642:] == 1.0)


def test_preprocessing_caps_extreme_aspect_ratio_without_cropping() -> None:
    image = Image.new("L", (3000, 30), 128)

    prepared = preprocess_line(image, _config())

    assert prepared.tensor.shape == (1, 1, 64, 1024)
    assert prepared.resized_size == (1024, 10)
    assert np.all(prepared.tensor[0, 0, :27, :] == 1.0)
    assert np.all(prepared.tensor[0, 0, 37:, :] == 1.0)
    assert np.allclose(prepared.tensor[0, 0, 27:37, :], 128 / 255)


def test_invalid_line_is_typed() -> None:
    from startkartenleser.infrastructure.recognizer import preprocess_line

    with pytest.raises(RecognitionAdapterError) as error:
        preprocess_line(None, _config())  # type: ignore[arg-type]
    assert error.value.failure is RecognitionFailure.INVALID_LINE


def test_ctc_decoder_collapses_repeats_drops_blanks_and_keeps_unicode() -> None:
    config = _config()
    ids = [1, 1, 0, 1, 2, 2, 0, 111]

    text = decode_greedy_ctc(_logits(ids), config)

    assert text == config.alphabet[0] * 2 + config.alphabet[1] + config.alphabet[-1]


@pytest.mark.parametrize(
    "values",
    [
        np.zeros((0, 112), dtype=np.float32),
        np.zeros((2, 4, 112), dtype=np.float32),
        np.zeros((1, 4, 111), dtype=np.float32),
        np.full((1, 4, 112), np.nan, dtype=np.float32),
    ],
)
def test_ctc_decoder_rejects_bad_logits(values) -> None:
    with pytest.raises(RecognitionAdapterError) as error:
        decode_greedy_ctc(values, _config())
    assert error.value.failure is RecognitionFailure.INVALID_OUTPUT


def test_adapter_uses_one_bounded_fake_session_and_returns_untrusted_candidate(tmp_path: Path) -> None:
    session = FakeSession([_logits([1, 1, 0, 2])])
    recognizer, factories = _recognizer(tmp_path, session, cpu_threads=2)

    result = recognizer.recognize("name", Image.new("L", (100, 30), 255))

    assert factories == [(recognizer.model_path, 2)]
    assert len(session.calls) == 1
    outputs, inputs = session.calls[0]
    assert outputs == ["logits"]
    assert inputs["image"].shape == (1, 1, 64, 216)
    assert result.status is RecognitionStatus.COMPLETED
    assert result.candidate is not None
    assert result.candidate.text == recognizer.config.alphabet[0] + recognizer.config.alphabet[1]
    assert result.candidate.confidence is None
    recognizer.close()
    assert session.closed


def test_adapter_maps_inference_failure_and_empty_text(tmp_path: Path) -> None:
    broken, _ = _recognizer(tmp_path / "broken", FakeSession([], error=RuntimeError()))
    failed = broken.recognize("name", Image.new("L", (40, 20), 255))
    assert failed.status is RecognitionStatus.FAILED
    assert failed.failure is RecognitionFailure.MODEL_UNAVAILABLE

    empty, _ = _recognizer(tmp_path / "empty", FakeSession([_logits([0, 0, 0])]))
    blank = empty.recognize("name", Image.new("L", (40, 20), 255))
    assert blank.status is RecognitionStatus.PARTIAL
    assert blank.candidate is None
    assert blank.failure is RecognitionFailure.EMPTY_OUTPUT


def test_cancellation_before_and_during_inference_is_reported(tmp_path: Path) -> None:
    already_cancelled = threading.Event()
    already_cancelled.set()
    session = FakeSession([_logits([1])])
    recognizer, _ = _recognizer(tmp_path / "before", session)
    result = recognizer.recognize(
        "name", Image.new("L", (40, 20)), cancellation=already_cancelled
    )
    assert result.status is RecognitionStatus.CANCELLED
    assert session.calls == []

    cancel_during = threading.Event()
    session_during = FakeSession([_logits([1])], on_run=cancel_during.set)
    during, _ = _recognizer(tmp_path / "during", session_during)
    cancelled = during.recognize(
        "name", Image.new("L", (40, 20)), cancellation=cancel_during
    )
    assert cancelled.status is RecognitionStatus.CANCELLED
    assert cancelled.failure is RecognitionFailure.CANCELLED


def test_missing_model_and_bad_model_hash_are_typed(tmp_path: Path) -> None:
    _, model_hash, config_hash = _fake_asset_files(tmp_path / "assets")
    (tmp_path / "assets" / "model.onnx").unlink()
    with pytest.raises(RecognitionAdapterError) as missing:
        DEHTRRecognizer(
            tmp_path / "assets",
            session_factory=lambda *_: FakeSession([]),
            expected_model_sha256=model_hash,
            expected_config_sha256=config_hash,
        )
    assert missing.value.failure is RecognitionFailure.MODEL_MISSING

    model_path, _, _ = _fake_asset_files(tmp_path / "mismatch")
    with pytest.raises(RecognitionAdapterError) as mismatch:
        DEHTRRecognizer(
            model_path.parent,
            session_factory=lambda *_: FakeSession([]),
            expected_model_sha256="0" * 64,
            expected_config_sha256=_sha256(model_path.parent / "config.json"),
        )
    assert mismatch.value.failure is RecognitionFailure.MODEL_HASH_MISMATCH


def test_model_session_factory_failure_is_typed(tmp_path: Path) -> None:
    model_path, model_hash, config_hash = _fake_asset_files(tmp_path / "assets")

    with pytest.raises(RecognitionAdapterError) as error:
        DEHTRRecognizer(
            model_path.parent,
            session_factory=lambda *_: (_ for _ in ()).throw(RuntimeError()),
            expected_model_sha256=model_hash,
            expected_config_sha256=config_hash,
        )

    assert error.value.failure is RecognitionFailure.MODEL_UNAVAILABLE
