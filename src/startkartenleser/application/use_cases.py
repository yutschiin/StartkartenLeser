"""Purely orchestrated session/card actions; infrastructure is supplied via ports."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import Event
from typing import Callable, Mapping
from uuid import uuid4

from startkartenleser.domain.contracts import (
    AlignmentQuality,
    Card,
    CardEvent,
    CardId,
    CardState,
    CheckboxValue,
    FieldValue,
    RecognitionCandidate,
    RecognitionOutcome,
    RecognitionStatus,
    Session,
    SessionId,
    SharedTextCandidate,
)
from startkartenleser.domain.rules import (
    InvalidCardTransition,
    confirm_field_value,
    merge_checkbox_proposal,
    merge_recognition_candidate,
    merge_shared_text_candidate,
)
from startkartenleser.domain.postprocessing import CorrectionPolicy, correct_candidate
from startkartenleser.domain.schema import (
    CHECKBOX_REGIONS,
    CHECKBOX_REGION_FIELDS,
    CROP_VERSION,
    A6_TIME_CROP_REGIONS,
    MODEL_VERSION,
    SCHEMA_VERSION,
    recognition_regions_for_layout,
)

from .ports import (
    AlignmentAttempt,
    CardAligner,
    CardRepository,
    CheckboxProposer,
    ConcurrentCardUpdate,
    HandwritingRecognizer,
    ImageStore,
    LineRecognitionResult,
    RetentionCoordinator,
    SessionRepository,
)


class UseCaseError(RuntimeError):
    """Expected workflow failure with a localized user-message key."""

    def __init__(self, localization_key: str) -> None:
        super().__init__(localization_key)
        self.localization_key = localization_key


@dataclass(frozen=True)
class CardProcessingResult:
    card: Card
    outcome: RecognitionOutcome
    alignment: AlignmentAttempt | None = None
    source_image: object | None = None


class StartkartenUseCases:
    def __init__(
        self,
        sessions: SessionRepository,
        cards: CardRepository,
        images: ImageStore,
        aligner: CardAligner,
        recognizer: HandwritingRecognizer,
        checkbox_proposer: CheckboxProposer,
        *,
        retention: RetentionCoordinator | None = None,
        model_version: str = MODEL_VERSION,
        correction_policy: CorrectionPolicy | None = None,
        clock=None,
    ) -> None:
        self.sessions = sessions
        self.cards = cards
        self.images = images
        self.aligner = aligner
        self.recognizer = recognizer
        self.checkbox_proposer = checkbox_proposer
        self.retention = retention
        self.model_version = model_version
        self.correction_policy = correction_policy
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def create_session(self, title: str) -> Session:
        if not title.strip():
            raise ValueError("session title cannot be blank")
        return self.sessions.create_session(
            Session(id=str(uuid4()), title=title, created_at=self.clock())
        )

    def list_sessions(self) -> tuple[Session, ...]:
        return self.sessions.list_sessions()

    def open_session(self, session_id: SessionId) -> Session:
        session = self.sessions.get_session(session_id)
        if session is None:
            raise UseCaseError("error.session_not_found")
        return session

    def list_cards(self, session_id: SessionId) -> tuple[Card, ...]:
        self.open_session(session_id)
        return self.cards.list_cards(session_id)

    def open_card(self, card_id: CardId) -> Card:
        card = self.cards.get_card(card_id)
        if card is None:
            raise UseCaseError("error.card_not_found")
        return card

    def card_review_data(
        self, card_id: CardId
    ) -> tuple[Card, Mapping[str, FieldValue], Mapping[str, CheckboxValue], Mapping[str, SharedTextCandidate]]:
        """Load review suggestions using the current policy, preserving user values."""
        card = self.open_card(card_id)
        fields = dict(self.cards.get_field_values(card_id))
        if self.correction_policy is not None:
            current_year = self.clock().year
            for key, value in fields.items():
                if value.source_region == "event_reference":
                    continue
                candidate = correct_candidate(
                    RecognitionCandidate(
                        key,
                        "" if value.value is None else str(value.value),
                        value.confidence,
                        value.raw_transcription,
                    ),
                    self.correction_policy,
                    current_year=current_year,
                )
                merged = merge_recognition_candidate(
                    value, candidate, replace_ocr_candidate=True
                )
                if merged is not None:
                    fields[key] = merged
        return (
            card,
            fields,
            self.cards.get_checkbox_values(card_id),
            self.cards.get_shared_candidates(card_id),
        )

    def read_card_image(self, card_id: CardId):
        """Return the locally managed original for review/reference display."""
        card = self.open_card(card_id)
        if not card.image_reference:
            raise UseCaseError("error.image_unreadable")
        return self.images.read_image(card.image_reference)

    def alignment_for_display(self, card_id: CardId) -> tuple[object, AlignmentAttempt]:
        """Reload the source image and recalculate ROI boxes for a reopened card."""
        image = self.read_card_image(card_id)
        return image, self.aligner.align(image)

    def next_card_sequence(self, session_id: SessionId) -> int:
        self.open_session(session_id)
        return self.cards.next_sequence(session_id)

    def delete_card(self, card_id: CardId) -> None:
        self.open_card(card_id)
        self._delete_with_retention("card", card_id)

    def delete_session(self, session_id: SessionId) -> None:
        self.open_session(session_id)
        self._delete_with_retention("session", session_id)

    def accept_image(self, session_id: SessionId, source_path: str) -> Card:
        """Copy the selected image first, then durably create its CAPTURED draft."""
        self.open_session(session_id)
        image_reference = self.images.store_selected(source_path)
        try:
            now = self.clock()
            card = Card(
                id=str(uuid4()),
                session_id=session_id,
                sequence=self.cards.next_sequence(session_id),
                state=CardState.CAPTURED,
                image_reference=image_reference,
                schema_version=SCHEMA_VERSION,
                crop_version=CROP_VERSION,
                created_at=now,
                updated_at=now,
            )
            return self.cards.create_card(card)
        except Exception:
            # The later filesystem repository adds startup orphan cleanup; this
            # immediate compensation keeps ordinary failures from leaking copies.
            try:
                self.images.delete_image(image_reference)
            except Exception:
                # Startup orphan cleanup retries a failed compensating unlink.
                pass
            raise

    def process_card(
        self,
        card_id: CardId,
        *,
        expected_revision: int | None = None,
        cancellation: Event | None = None,
        approve_replace_ocr_candidates: bool = False,
        on_alignment_ready: Callable[[Card, AlignmentAttempt, object], None] | None = None,
    ) -> CardProcessingResult:
        """Align/crop and request local candidates without accepting any value."""
        card = self.open_card(card_id)
        if expected_revision is not None and card.revision != expected_revision:
            raise UseCaseError("error.card_changed")
        if not card.image_reference:
            raise UseCaseError("error.image_unreadable")
        if cancellation is not None and cancellation.is_set():
            recoverable = self._transition(card, CardEvent.CANCEL)
            return CardProcessingResult(
                recoverable,
                RecognitionOutcome(
                    RecognitionStatus.CANCELLED,
                    error_key="error.recognition_cancelled",
                    schema_version=card.schema_version,
                ),
            )

        aligning = self._transition(card, CardEvent.START_ALIGNMENT)
        image: object | None = None
        try:
            image = self.images.read_image(aligning.image_reference or "")
            attempt = self.aligner.align(image)
        except Exception:
            recoverable = self._transition_current(aligning, CardEvent.ALIGNMENT_FAILED)
            return CardProcessingResult(
                recoverable,
                RecognitionOutcome(
                    RecognitionStatus.FAILED,
                    error_key="error.image_unreadable",
                    schema_version=card.schema_version,
                ),
                source_image=image,
            )

        if attempt.result.quality is not AlignmentQuality.ACCEPTED:
            recoverable = self._transition_current(aligning, CardEvent.ALIGNMENT_FAILED)
            return CardProcessingResult(
                recoverable,
                RecognitionOutcome(
                    RecognitionStatus.FAILED,
                    error_key=attempt.result.reason_key or "error.alignment_uncertain",
                    schema_version=card.schema_version,
                ),
                attempt,
                image,
            )

        recognizing = self._transition_current(aligning, CardEvent.ALIGNMENT_ACCEPTED)
        if on_alignment_ready is not None:
            on_alignment_ready(recognizing, attempt, image)
        fields_before = self.cards.get_field_values(card_id)
        checkboxes_before = self.cards.get_checkbox_values(card_id)
        shared_before = self.cards.get_shared_candidates(card_id)
        candidates = []
        time_parts: dict[str, str] = {}
        shared_candidates: list[SharedTextCandidate] = []
        checkbox_proposals: list[CheckboxValue] = []
        first_error: str | None = None
        saw_partial = False
        status = RecognitionStatus.COMPLETED
        expected_regions = recognition_regions_for_layout(attempt.result.schema_version)
        skipped_regions = set(attempt.skipped_text_regions)
        missing_regions = set(expected_regions) - set(attempt.text_crops) - skipped_regions
        missing_checkbox_regions = set(CHECKBOX_REGIONS) - set(attempt.checkbox_crops)
        if missing_regions or missing_checkbox_regions:
            saw_partial = True
            status = RecognitionStatus.PARTIAL
            first_error = "error.recognition_failed"

        for field_key, crop in attempt.text_crops.items():
            if cancellation is not None and cancellation.is_set():
                status = RecognitionStatus.CANCELLED
                first_error = "error.recognition_cancelled"
                break
            try:
                line_result = self.recognizer.recognize(field_key, crop, cancellation)
            except Exception:
                line_result = LineRecognitionResult(
                    RecognitionStatus.FAILED,
                    error_key="error.model_unavailable",
                )
            if line_result.candidate is not None and line_result.candidate.text.strip():
                if line_result.candidate.field_key != field_key:
                    saw_partial = True
                    status = RecognitionStatus.PARTIAL
                    first_error = first_error or "error.recognition_failed"
                    continue
                if field_key in A6_TIME_CROP_REGIONS:
                    time_parts[field_key] = line_result.candidate.text.strip()
                elif field_key == "course_position":
                    shared_candidates.append(
                        SharedTextCandidate(field_key, line_result.candidate.text,
                                            line_result.candidate.confidence)
                    )
                else:
                    candidates.append(line_result.candidate)
            if line_result.status is not RecognitionStatus.COMPLETED:
                saw_partial = True
                if first_error is None:
                    first_error = line_result.error_key or _recognition_error_key(line_result)
                if line_result.status is RecognitionStatus.UNAVAILABLE:
                    status = RecognitionStatus.UNAVAILABLE
                elif line_result.status is RecognitionStatus.CANCELLED:
                    status = RecognitionStatus.CANCELLED
                elif status is RecognitionStatus.COMPLETED:
                    status = RecognitionStatus.PARTIAL

        seconds = time_parts.get("time_seconds", "")
        time_parts_complete = all(
            key in time_parts or key in skipped_regions
            for key in A6_TIME_CROP_REGIONS
        )
        if (
            status is not RecognitionStatus.CANCELLED
            and time_parts_complete
            and seconds
        ):
            fraction = time_parts.get("time_fraction", "")
            seconds_text = f"{seconds},{fraction}" if fraction else seconds
            minutes = time_parts.get("time_minutes", "")
            time_text = (
                f"{minutes} min {seconds_text} sek"
                if minutes
                else f"{seconds_text} sek"
            )
            candidates.append(RecognitionCandidate("time", time_text))

        if status is not RecognitionStatus.CANCELLED:
            for region_key, crop in attempt.checkbox_crops.items():
                if cancellation is not None and cancellation.is_set():
                    status = RecognitionStatus.CANCELLED
                    first_error = "error.recognition_cancelled"
                    break
                field_key = CHECKBOX_REGION_FIELDS.get(region_key)
                if field_key is None:
                    saw_partial = True
                    status = RecognitionStatus.PARTIAL
                    first_error = first_error or "error.recognition_failed"
                    continue
                try:
                    proposal = self.checkbox_proposer.propose(field_key, crop)
                    checkbox_proposals.append(proposal)
                except Exception:
                    saw_partial = True
                    if first_error is None:
                        first_error = "error.recognition_failed"
                    if status is RecognitionStatus.COMPLETED:
                        status = RecognitionStatus.PARTIAL

        if self.correction_policy is not None:
            candidates = [
                correct_candidate(
                    candidate, self.correction_policy, current_year=self.clock().year
                )
                for candidate in candidates
            ]
        merged_fields: dict[str, FieldValue] = dict(fields_before)
        for candidate in candidates:
            merged = merge_recognition_candidate(
                merged_fields.get(candidate.field_key),
                candidate,
                replace_ocr_candidate=approve_replace_ocr_candidates,
            )
            if merged is not None:
                merged_fields[candidate.field_key] = merged
        merged_checkboxes: dict[str, CheckboxValue] = dict(checkboxes_before)
        for proposal in checkbox_proposals:
            merged = merge_checkbox_proposal(
                merged_checkboxes.get(proposal.field_key),
                proposal,
                replace_ocr_candidate=approve_replace_ocr_candidates,
            )
            if merged is not None:
                merged_checkboxes[proposal.field_key] = merged
        merged_shared: dict[str, SharedTextCandidate] = dict(shared_before)
        for candidate in shared_candidates:
            merged = merge_shared_text_candidate(
                merged_shared.get(candidate.region_key), candidate
            )
            merged_shared[candidate.region_key] = merged

        outcome = RecognitionOutcome(
            status=status if saw_partial or status is not RecognitionStatus.COMPLETED else RecognitionStatus.COMPLETED,
            candidates=tuple(candidates),
            shared_candidates=tuple(shared_candidates),
            checkbox_proposals=tuple(checkbox_proposals),
            error_key=first_error,
            model_version=self.model_version,
            schema_version=card.schema_version,
        )
        try:
            saved = self.cards.save_recognition(
                card_id,
                recognizing.revision,
                merged_fields,
                merged_checkboxes,
                merged_shared,
                self.model_version,
            )
        except ConcurrentCardUpdate:
            # A late model result is discarded rather than racing a user edit.
            latest = self.open_card(card_id)
            return CardProcessingResult(
                latest,
                RecognitionOutcome(
                    RecognitionStatus.CANCELLED,
                    error_key="error.recognition_cancelled",
                    model_version=self.model_version,
                    schema_version=card.schema_version,
                ),
                attempt,
                image,
            )
        return CardProcessingResult(saved, outcome, attempt, image)

    def save_review(
        self,
        card_id: CardId,
        expected_revision: int,
        fields: Mapping[str, FieldValue],
        checkboxes: Mapping[str, CheckboxValue],
    ) -> Card:
        """Explicitly save and confirm current values as a human-reviewed card."""
        confirmed_fields = {
            key: confirm_field_value(value) for key, value in fields.items()
        }
        confirmed_checkboxes = {
            key: replace(value, confirmed=True) for key, value in checkboxes.items()
        }
        return self.cards.save_review(
            card_id,
            expected_revision,
            confirmed_fields,
            confirmed_checkboxes,
        )

    def _transition(self, card: Card, event: CardEvent) -> Card:
        try:
            return self.cards.transition_card(card.id, card.revision, event)
        except ConcurrentCardUpdate:
            raise UseCaseError("error.card_changed") from None
        except InvalidCardTransition as error:
            raise UseCaseError("error.card_transition_invalid") from error

    def _transition_current(self, card: Card, event: CardEvent) -> Card:
        return self._transition(card, event)

    def _delete_with_retention(self, entity: str, identifier: str) -> None:
        if self.retention is None:
            raise UseCaseError("error.delete_unavailable")
        try:
            if entity == "card":
                self.retention.delete_card(identifier)
            else:
                self.retention.delete_session(identifier)
        except Exception as error:
            raise UseCaseError("error.delete_failed") from error


def _recognition_error_key(result: LineRecognitionResult) -> str:
    if result.status is RecognitionStatus.UNAVAILABLE:
        return "error.model_unavailable"
    if result.status is RecognitionStatus.CANCELLED:
        return "error.recognition_cancelled"
    return "error.recognition_failed"
