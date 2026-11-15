"""Pinned DE·HTR v2 CPU adapter with preprocessing and greedy CTC decoding."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from pathlib import Path
import os
import threading
from typing import Any, Protocol

import numpy as np
from PIL import Image, ImageOps

from startkartenleser.domain.contracts import (
    RecognitionCandidate,
    RecognitionStatus,
)
from startkartenleser.domain.schema import MODEL_VERSION


MODEL_SHA256 = "b576a0a1281b9be46b2574028b75575e041b7d7cb650f063886e733467cc1499"
CONFIG_SHA256 = "4ebd69d9d27b398ea3997b031318accc13123f6a8950def1fedc6e364cb758fa"
DEFAULT_ASSET_DIR = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "models"
    / "de-htr-v2"
)


class RecognitionFailure(StrEnum):
    MODEL_MISSING = "model_missing"
    MODEL_HASH_MISMATCH = "model_hash_mismatch"
    INVALID_MODEL_CONFIG = "invalid_model_config"
    MODEL_UNAVAILABLE = "model_unavailable"
    INVALID_LINE = "invalid_line"
    INVALID_OUTPUT = "invalid_output"
    EMPTY_OUTPUT = "empty_output"
    CANCELLED = "cancelled"


class RecognitionAdapterError(RuntimeError):
    """Typed model/config/inference failure without card content in its message."""

    def __init__(self, failure: RecognitionFailure) -> None:
        super().__init__(failure.value)
        self.failure = failure


@dataclass(frozen=True)
class ModelConfig:
    model_filename: str
    input_name: str
    output_name: str
    image_height: int
    max_width: int
    output_stride: int
    blank_index: int
    alphabet: str
    scale: float
    pad_value: float


@dataclass(frozen=True)
class PreprocessedLine:
    tensor: np.ndarray
    resized_size: tuple[int, int]
    padded_width: int


@dataclass(frozen=True)
class RecognitionResult:
    status: RecognitionStatus
    candidate: RecognitionCandidate | None = None
    failure: RecognitionFailure | None = None


class InferenceSession(Protocol):
    def run(self, output_names: list[str], input_feed: dict[str, np.ndarray]) -> list[np.ndarray]: ...


SessionFactory = Any


def load_model_config(path: Path, expected_sha256: str = CONFIG_SHA256) -> ModelConfig:
    """Read and validate the versioned config only after checking its digest."""
    if not path.is_file():
        raise RecognitionAdapterError(RecognitionFailure.MODEL_MISSING)
    if _sha256(path) != expected_sha256:
        raise RecognitionAdapterError(RecognitionFailure.MODEL_HASH_MISMATCH)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("model config must be an object")
        if raw.get("format_version") != 2 or raw.get("model") != "model.onnx":
            raise ValueError("unsupported model config")
        preprocessing = raw["preprocessing"]
        config = ModelConfig(
            model_filename=raw["model"],
            input_name=raw["input_name"],
            output_name=raw["output_name"],
            image_height=int(raw["image_height"]),
            max_width=int(raw["max_width"]),
            output_stride=int(raw["output_stride"]),
            blank_index=int(raw["blank_index"]),
            alphabet=raw["alphabet"],
            scale=float(preprocessing["scale"]),
            pad_value=float(preprocessing["pad_value"]),
        )
        if (
            not config.input_name
            or not config.output_name
            or config.image_height != 64
            or config.max_width != 1024
            or config.output_stride != 4
            or config.blank_index != 0
            or len(config.alphabet) != 111
            or len(set(config.alphabet)) != len(config.alphabet)
            or not 0 < config.scale <= 1
            or not 0 <= config.pad_value <= 1
        ):
            raise ValueError("invalid DE·HTR v2 config values")
        return config
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise RecognitionAdapterError(RecognitionFailure.INVALID_MODEL_CONFIG) from error


def preprocess_line(image: Image.Image, config: ModelConfig) -> PreprocessedLine:
    """Convert a grayscale line to a bounded [1,1,64,W] float tensor."""
    if not isinstance(image, Image.Image) or image.width <= 0 or image.height <= 0:
        raise RecognitionAdapterError(RecognitionFailure.INVALID_LINE)
    if image.width * image.height > 40_000_000:
        raise RecognitionAdapterError(RecognitionFailure.INVALID_LINE)

    gray = ImageOps.grayscale(image)
    max_width = config.max_width
    target_height = config.image_height
    scale_factor = min(target_height / gray.height, max_width / gray.width)
    resized_width = max(1, min(max_width, round(gray.width * scale_factor)))
    resized_height = max(1, min(target_height, round(gray.height * scale_factor)))
    resized = gray.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
    padded_width = min(
        max_width,
        ((resized_width + config.output_stride - 1) // config.output_stride)
        * config.output_stride,
    )
    canvas = Image.new("L", (padded_width, target_height), color=round(config.pad_value * 255))
    vertical_offset = (target_height - resized_height) // 2
    canvas.paste(resized, (0, vertical_offset))
    pixels = np.asarray(canvas, dtype=np.float32) * config.scale
    tensor = np.ascontiguousarray(pixels[None, None, :, :], dtype=np.float32)
    return PreprocessedLine(tensor, (resized_width, resized_height), padded_width)


def decode_greedy_ctc(logits: np.ndarray, config: ModelConfig) -> str:
    """Collapse repeated CTC symbols, drop blank tokens, and preserve Unicode."""
    values = np.asarray(logits)
    if values.ndim == 3:
        if values.shape[0] != 1:
            raise RecognitionAdapterError(RecognitionFailure.INVALID_OUTPUT)
        values = values[0]
    if (
        values.ndim != 2
        or values.shape[0] == 0
        or values.shape[1] != len(config.alphabet) + 1
        or not np.isfinite(values).all()
    ):
        raise RecognitionAdapterError(RecognitionFailure.INVALID_OUTPUT)

    ids = np.argmax(values, axis=-1)
    result: list[str] = []
    previous: int | None = None
    for token_id in ids:
        index = int(token_id)
        if index != previous and index != config.blank_index:
            alphabet_index = index - 1
            if not 0 <= alphabet_index < len(config.alphabet):
                raise RecognitionAdapterError(RecognitionFailure.INVALID_OUTPUT)
            result.append(config.alphabet[alphabet_index])
        previous = index
    return "".join(result)


class DEHTRRecognizer:
    """One-session CPU inference adapter; ONNX Runtime stays behind this boundary."""

    def __init__(
        self,
        asset_dir: Path | str = DEFAULT_ASSET_DIR,
        *,
        session_factory: SessionFactory | None = None,
        cpu_threads: int | None = None,
        expected_model_sha256: str = MODEL_SHA256,
        expected_config_sha256: str = CONFIG_SHA256,
    ) -> None:
        self.asset_dir = Path(asset_dir)
        self.model_path = self.asset_dir / "model.onnx"
        self.config_path = self.asset_dir / "config.json"
        self._session: InferenceSession | None = None
        self._closed = False
        self._lock = threading.Lock()
        self._run_lock = threading.Lock()
        self.cpu_threads = cpu_threads or max(1, min(os.cpu_count() or 1, 4))
        if self.cpu_threads < 1:
            raise ValueError("cpu_threads must be positive")

        self.config = load_model_config(self.config_path, expected_config_sha256)
        if not self.model_path.is_file():
            raise RecognitionAdapterError(RecognitionFailure.MODEL_MISSING)
        if _sha256(self.model_path) != expected_model_sha256:
            raise RecognitionAdapterError(RecognitionFailure.MODEL_HASH_MISMATCH)
        factory = session_factory or self._create_onnx_session
        try:
            self._session = factory(self.model_path, self.cpu_threads)
        except RecognitionAdapterError:
            raise
        except Exception as error:
            raise RecognitionAdapterError(RecognitionFailure.MODEL_UNAVAILABLE) from error
        if self._session is None:
            raise RecognitionAdapterError(RecognitionFailure.MODEL_UNAVAILABLE)

    def recognize(
        self,
        field_key: str,
        image: Image.Image,
        *,
        cancellation: threading.Event | None = None,
    ) -> RecognitionResult:
        """Return a candidate or typed failure; confidence is deliberately unset."""
        if cancellation is not None and cancellation.is_set():
            return RecognitionResult(RecognitionStatus.CANCELLED, failure=RecognitionFailure.CANCELLED)
        try:
            prepared = preprocess_line(image, self.config)
        except RecognitionAdapterError as error:
            return RecognitionResult(RecognitionStatus.FAILED, failure=error.failure)

        with self._run_lock:
            if self._closed or self._session is None:
                return RecognitionResult(
                    RecognitionStatus.UNAVAILABLE,
                    failure=RecognitionFailure.MODEL_UNAVAILABLE,
                )
            if cancellation is not None and cancellation.is_set():
                return RecognitionResult(RecognitionStatus.CANCELLED, failure=RecognitionFailure.CANCELLED)
            try:
                raw_outputs = self._session.run(
                    [self.config.output_name],
                    {self.config.input_name: prepared.tensor},
                )
            except Exception:
                return RecognitionResult(
                    RecognitionStatus.FAILED,
                    failure=RecognitionFailure.MODEL_UNAVAILABLE,
                )
        if cancellation is not None and cancellation.is_set():
            return RecognitionResult(RecognitionStatus.CANCELLED, failure=RecognitionFailure.CANCELLED)
        if not isinstance(raw_outputs, (list, tuple)) or not raw_outputs:
            return RecognitionResult(RecognitionStatus.FAILED, failure=RecognitionFailure.INVALID_OUTPUT)
        try:
            text = decode_greedy_ctc(raw_outputs[0], self.config)
        except RecognitionAdapterError as error:
            return RecognitionResult(RecognitionStatus.FAILED, failure=error.failure)
        if not text:
            return RecognitionResult(RecognitionStatus.PARTIAL, failure=RecognitionFailure.EMPTY_OUTPUT)
        return RecognitionResult(
            RecognitionStatus.COMPLETED,
            candidate=RecognitionCandidate(field_key, text),
        )

    def close(self) -> None:
        """Release the provider session if it exposes a deterministic close hook."""
        with self._run_lock:
            if self._closed:
                return
            self._closed = True
            session = self._session
            self._session = None
            close = getattr(session, "close", None)
            if close is None:
                native_session = getattr(session, "_sess", None)
                close = getattr(native_session, "close", None)
            if close is not None:
                close()

    def __enter__(self) -> "DEHTRRecognizer":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _create_onnx_session(model_path: Path, cpu_threads: int) -> InferenceSession:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = cpu_threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        return ort.InferenceSession(
            str(model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise RecognitionAdapterError(RecognitionFailure.MODEL_MISSING) from error
    return digest.hexdigest()
