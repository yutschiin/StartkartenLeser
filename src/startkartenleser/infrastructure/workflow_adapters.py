"""Concrete bridges from image/model utilities to application ports."""

from __future__ import annotations

from pathlib import Path
from threading import Event, Lock

from PIL import Image

from startkartenleser.application.ports import AlignmentAttempt, LineRecognitionResult
from startkartenleser.domain.contracts import (
    AlignmentQuality,
    AlignmentResult,
    CheckboxValue,
    RecognitionStatus,
)
from startkartenleser.domain.schema import (
    CARD_LAYOUT_A6_V1,
    CARD_LAYOUT_A6_V2,
    CARD_LAYOUT_A6_V3,
    CARD_LAYOUT_A6_V4,
    recognition_regions_for_layout,
)
from startkartenleser.infrastructure.checkbox_detector import propose_checkbox_state
from startkartenleser.infrastructure.image_pipeline import (
    align_card,
    crop_card_regions,
    crop_contains_handwriting,
    project_region_overlays,
)
from startkartenleser.infrastructure.recognizer import (
    DEFAULT_ASSET_DIR,
    DEHTRRecognizer,
    RecognitionFailure,
)


class TemplateCardAligner:
    """Use canonical card geometry, conservatively routing uncertain cases to review."""

    def align(self, image: object) -> AlignmentAttempt:
        if not isinstance(image, Image.Image):
            return AlignmentAttempt(
                AlignmentResult(
                    AlignmentQuality.REJECTED,
                    reason_key="error.image_unreadable",
                ),
                {},
                {},
            )
        aligned = align_card(image)
        if aligned is None:
            return AlignmentAttempt(
                AlignmentResult(
                    AlignmentQuality.NEEDS_MANUAL_ADJUSTMENT,
                    reason_key="error.alignment_uncertain",
                ),
                {},
                {},
            )
        if aligned.result.quality is not AlignmentQuality.ACCEPTED:
            return AlignmentAttempt(aligned.result, {}, {})
        layout_version = aligned.result.schema_version
        crops = crop_card_regions(aligned.image, layout_version=layout_version)
        text_crops = {}
        skipped_text_regions = []
        for key in recognition_regions_for_layout(layout_version):
            crop = crops[key]
            if (
                layout_version in (
                    CARD_LAYOUT_A6_V1, CARD_LAYOUT_A6_V2, CARD_LAYOUT_A6_V3, CARD_LAYOUT_A6_V4,
                )
                and not crop_contains_handwriting(crop)
            ):
                skipped_text_regions.append(key)
            else:
                text_crops[key] = crop
        checkbox_crops = {
            key: crops[key] for key in ("checkbox_female", "checkbox_male")
        }
        return AlignmentAttempt(
            aligned.result,
            text_crops,
            checkbox_crops,
            project_region_overlays(
                aligned.result.transform,
                layout_version=layout_version,
                aligned_image=aligned.image,
            ),
            tuple(skipped_text_regions),
            aligned.image,
        )


class DEHTRLineRecognizer:
    """Translate typed adapter results into the application recognition port."""

    def __init__(self, recognizer: DEHTRRecognizer) -> None:
        self.recognizer = recognizer

    def recognize(
        self,
        field_key: str,
        crop: object,
        cancellation: Event | None = None,
    ) -> LineRecognitionResult:
        if not isinstance(crop, Image.Image):
            return LineRecognitionResult(
                RecognitionStatus.FAILED,
                error_key="error.recognition_failed",
            )
        result = self.recognizer.recognize(field_key, crop, cancellation=cancellation)
        return LineRecognitionResult(
            status=result.status,
            candidate=result.candidate,
            error_key=_failure_key(result.failure),
        )


class LazyDEHTRLineRecognizer:
    """Initialize the local ONNX session on the first worker-thread request."""

    def __init__(self, asset_dir: Path | str = DEFAULT_ASSET_DIR) -> None:
        self.asset_dir = Path(asset_dir)
        self._delegate: DEHTRLineRecognizer | None = None
        self._unavailable = False
        self._lock = Lock()

    def recognize(
        self,
        field_key: str,
        crop: object,
        cancellation: Event | None = None,
    ) -> LineRecognitionResult:
        if cancellation is not None and cancellation.is_set():
            return LineRecognitionResult(RecognitionStatus.CANCELLED, error_key="error.recognition_cancelled")
        with self._lock:
            if self._delegate is None and not self._unavailable:
                try:
                    self._delegate = DEHTRLineRecognizer(
                        DEHTRRecognizer(self.asset_dir)
                    )
                except Exception:
                    self._unavailable = True
            delegate = self._delegate
        if delegate is None:
            return LineRecognitionResult(
                RecognitionStatus.UNAVAILABLE,
                error_key="error.model_unavailable",
            )
        return delegate.recognize(field_key, crop, cancellation)

    def close(self) -> None:
        with self._lock:
            delegate = self._delegate
            self._delegate = None
        if delegate is not None:
            delegate.recognizer.close()


class ConservativeCheckboxProposer:
    def propose(self, field_key: str, crop: object) -> CheckboxValue:
        if not isinstance(crop, Image.Image):
            from startkartenleser.domain.contracts import CheckboxState, FieldProvenance

            return CheckboxValue(field_key, CheckboxState.UNKNOWN, FieldProvenance.OCR)
        return propose_checkbox_state(field_key, crop)


def _failure_key(failure: RecognitionFailure | None) -> str | None:
    if failure is None:
        return None
    if failure in (
        RecognitionFailure.MODEL_MISSING,
        RecognitionFailure.MODEL_HASH_MISMATCH,
        RecognitionFailure.INVALID_MODEL_CONFIG,
        RecognitionFailure.MODEL_UNAVAILABLE,
    ):
        return "error.model_unavailable"
    if failure is RecognitionFailure.EMPTY_OUTPUT:
        return "error.recognition_empty"
    if failure is RecognitionFailure.CANCELLED:
        return "error.recognition_cancelled"
    return "error.recognition_failed"
