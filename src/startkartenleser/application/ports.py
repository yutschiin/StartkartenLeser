"""Narrow repository, image, alignment, and recognition ports for use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol

from startkartenleser.domain.contracts import (
    AlignmentResult,
    Card,
    CardEvent,
    CardId,
    CheckboxValue,
    FieldValue,
    RecognitionCandidate,
    RecognitionStatus,
    RegionOverlay,
    Session,
    SessionId,
    SharedTextCandidate,
)


class ConcurrentCardUpdate(RuntimeError):
    """The card revision changed while an operation was in progress."""


class SessionRepository(Protocol):
    def create_session(self, session: Session) -> Session: ...
    def get_session(self, session_id: SessionId) -> Session | None: ...
    def list_sessions(self) -> tuple[Session, ...]: ...
    def delete_session(self, session_id: SessionId) -> None: ...


class CardRepository(Protocol):
    def create_card(self, card: Card) -> Card: ...
    def get_card(self, card_id: CardId) -> Card | None: ...
    def list_cards(self, session_id: SessionId) -> tuple[Card, ...]: ...
    def next_sequence(self, session_id: SessionId) -> int: ...
    def transition_card(
        self, card_id: CardId, expected_revision: int, event: CardEvent
    ) -> Card: ...
    def get_field_values(self, card_id: CardId) -> Mapping[str, FieldValue]: ...
    def get_checkbox_values(self, card_id: CardId) -> Mapping[str, CheckboxValue]: ...
    def get_shared_candidates(self, card_id: CardId) -> Mapping[str, SharedTextCandidate]: ...
    def save_recognition(
        self,
        card_id: CardId,
        expected_revision: int,
        fields: Mapping[str, FieldValue],
        checkboxes: Mapping[str, CheckboxValue],
        shared_candidates: Mapping[str, SharedTextCandidate],
        model_version: str,
    ) -> Card: ...
    def save_review(
        self,
        card_id: CardId,
        expected_revision: int,
        fields: Mapping[str, FieldValue],
        checkboxes: Mapping[str, CheckboxValue],
    ) -> Card: ...


class ImageStore(Protocol):
    def store_selected(self, source_path: str) -> str: ...
    def read_image(self, image_reference: str) -> object: ...
    def delete_image(self, image_reference: str) -> None: ...


class RetentionCoordinator(Protocol):
    """Coordinate retryable database/image cleanup for user-requested deletion."""

    def delete_card(self, card_id: CardId) -> None: ...
    def delete_session(self, session_id: SessionId) -> None: ...


@dataclass(frozen=True)
class AlignmentAttempt:
    result: AlignmentResult
    text_crops: Mapping[str, object]
    checkbox_crops: Mapping[str, object]
    overlays: tuple[RegionOverlay, ...] = ()
    skipped_text_regions: tuple[str, ...] = ()
    aligned_image: object | None = None


class CardAligner(Protocol):
    def align(self, image: object) -> AlignmentAttempt: ...


@dataclass(frozen=True)
class LineRecognitionResult:
    status: RecognitionStatus
    candidate: RecognitionCandidate | None = None
    error_key: str | None = None


class HandwritingRecognizer(Protocol):
    def recognize(self, field_key: str, crop: object, cancellation: object = None) -> LineRecognitionResult: ...


class CheckboxProposer(Protocol):
    def propose(self, field_key: str, crop: object) -> CheckboxValue: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
