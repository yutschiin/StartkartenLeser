"""Stable, infrastructure-independent domain data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypeAlias


class CardState(StrEnum):
    CAPTURED = "captured"
    ALIGNING = "aligning"
    RECOGNIZING = "recognizing"
    NEEDS_REVIEW = "needs_review"
    REVIEWED = "reviewed"


class FieldProvenance(StrEnum):
    OCR = "ocr"
    MANUAL = "manual"
    USER_EDITED = "user_edited"


class FieldReviewStatus(StrEnum):
    CANDIDATE = "candidate"
    LOW_CONFIDENCE = "low_confidence"
    INVALID = "invalid"
    MISSING = "missing"
    CONFIRMED = "confirmed"


class CheckboxState(StrEnum):
    CHECKED = "checked"
    UNCHECKED = "unchecked"
    UNKNOWN = "unknown"


class AlignmentQuality(StrEnum):
    ACCEPTED = "accepted"
    NEEDS_MANUAL_ADJUSTMENT = "needs_manual_adjustment"
    REJECTED = "rejected"


class RecognitionStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CardEvent(StrEnum):
    START_ALIGNMENT = "start_alignment"
    ALIGNMENT_ACCEPTED = "alignment_accepted"
    ALIGNMENT_FAILED = "alignment_failed"
    START_RECOGNITION = "start_recognition"
    RECOGNITION_FINISHED = "recognition_finished"
    RECOGNITION_FAILED = "recognition_failed"
    CANCEL = "cancel"
    SAVE_REVIEW = "save_review"
    EDIT = "edit"


FieldKey: TypeAlias = str
CardId: TypeAlias = str
SessionId: TypeAlias = str


@dataclass(frozen=True)
class Session:
    id: SessionId
    title: str
    created_at: datetime
    revision: int = 0
    number: int | None = None
    distance_m: int | None = None
    stroke: str | None = None
    gender: str | None = None


@dataclass(frozen=True)
class Card:
    id: CardId
    session_id: SessionId
    sequence: int
    state: CardState
    image_reference: str | None
    schema_version: str
    model_version: str | None = None
    crop_version: str = "startkarte-crops-v7"
    revision: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


FieldContent: TypeAlias = str | int | None


@dataclass(frozen=True)
class FieldValue:
    field_key: FieldKey
    value: FieldContent
    provenance: FieldProvenance
    review_status: FieldReviewStatus
    raw_transcription: str | None = None
    confidence: float | None = None
    confirmed: bool = False
    source_region: str | None = None


@dataclass(frozen=True)
class CheckboxValue:
    field_key: FieldKey
    state: CheckboxState
    provenance: FieldProvenance | None = None
    confirmed: bool = False


@dataclass(frozen=True)
class AlignmentResult:
    quality: AlignmentQuality
    transform: tuple[float, ...] | None = None
    confidence: float | None = None
    reason_key: str | None = None
    schema_version: str = "card-layout-v1"


@dataclass(frozen=True)
class RegionOverlay:
    """Crop rectangle projected back onto the orientation-normalized source image."""

    region_key: str
    label_key: str
    source_corners: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class RecognitionRequest:
    card_id: CardId
    schema_version: str
    model_version: str
    request_revision: int
    field_keys: tuple[FieldKey, ...]


@dataclass(frozen=True)
class RecognitionCandidate:
    field_key: FieldKey
    text: str
    confidence: float | None = None
    raw_transcription: str | None = None


@dataclass(frozen=True)
class SharedTextCandidate:
    region_key: str
    raw_text: str
    confidence: float | None = None
    provenance: FieldProvenance = FieldProvenance.OCR
    confirmed: bool = False


@dataclass(frozen=True)
class RecognitionOutcome:
    status: RecognitionStatus
    candidates: tuple[RecognitionCandidate, ...] = ()
    shared_candidates: tuple[SharedTextCandidate, ...] = ()
    checkbox_proposals: tuple[CheckboxValue, ...] = ()
    error_key: str | None = None
    model_version: str | None = None
    schema_version: str | None = None


@dataclass(frozen=True)
class VersionInfo:
    schema_version: str
    crop_version: str
    model_version: str | None = None
