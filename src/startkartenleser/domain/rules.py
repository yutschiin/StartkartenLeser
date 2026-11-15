"""Pure card lifecycle and safe recognition-candidate merge rules."""

from __future__ import annotations

from startkartenleser.domain.contracts import (
    CardEvent,
    CardState,
    FieldProvenance,
    FieldReviewStatus,
    FieldValue,
    CheckboxState,
    CheckboxValue,
    RecognitionCandidate,
    SharedTextCandidate,
)


class InvalidCardTransition(ValueError):
    """Raised when an event cannot be applied to the current card state."""


_TRANSITIONS: dict[tuple[CardState, CardEvent], CardState] = {
    (CardState.CAPTURED, CardEvent.START_ALIGNMENT): CardState.ALIGNING,
    (CardState.CAPTURED, CardEvent.CANCEL): CardState.NEEDS_REVIEW,
    (CardState.ALIGNING, CardEvent.ALIGNMENT_ACCEPTED): CardState.RECOGNIZING,
    (CardState.ALIGNING, CardEvent.ALIGNMENT_FAILED): CardState.NEEDS_REVIEW,
    (CardState.ALIGNING, CardEvent.CANCEL): CardState.NEEDS_REVIEW,
    (CardState.RECOGNIZING, CardEvent.RECOGNITION_FINISHED): CardState.NEEDS_REVIEW,
    (CardState.RECOGNIZING, CardEvent.RECOGNITION_FAILED): CardState.NEEDS_REVIEW,
    (CardState.RECOGNIZING, CardEvent.CANCEL): CardState.NEEDS_REVIEW,
    (CardState.NEEDS_REVIEW, CardEvent.START_ALIGNMENT): CardState.ALIGNING,
    (CardState.NEEDS_REVIEW, CardEvent.START_RECOGNITION): CardState.RECOGNIZING,
    (CardState.NEEDS_REVIEW, CardEvent.SAVE_REVIEW): CardState.REVIEWED,
    (CardState.REVIEWED, CardEvent.EDIT): CardState.NEEDS_REVIEW,
    (CardState.REVIEWED, CardEvent.SAVE_REVIEW): CardState.REVIEWED,
}


def transition_card(state: CardState, event: CardEvent) -> CardState:
    """Return the next state or fail closed for an undefined transition."""
    try:
        return _TRANSITIONS[state, event]
    except KeyError as error:
        raise InvalidCardTransition(f"cannot apply {event.value} to {state.value}") from error


def _is_empty(value: str | int | None) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def merge_recognition_candidate(
    existing: FieldValue | None,
    candidate: RecognitionCandidate,
    *,
    replace_ocr_candidate: bool = False,
) -> FieldValue | None:
    """Fill an unprotected blank, never silently clobbering user data.

    A retry may replace an unconfirmed OCR suggestion only when the caller has
    explicit approval. Manual, user-edited, and confirmed values are immutable
    to recognition retries, even when their current value is blank.
    """
    if not candidate.text.strip():
        return existing
    if existing is None:
        return FieldValue(
            candidate.field_key,
            candidate.text,
            FieldProvenance.OCR,
            FieldReviewStatus.CANDIDATE,
            raw_transcription=candidate.raw_transcription if candidate.raw_transcription is not None else candidate.text,
            confidence=candidate.confidence,
            source_region=candidate.field_key,
        )
    if existing.field_key != candidate.field_key:
        raise ValueError(
            f"candidate field {candidate.field_key!r} does not match "
            f"existing field {existing.field_key!r}"
        )
    if (
        existing.provenance in (FieldProvenance.MANUAL, FieldProvenance.USER_EDITED)
        or existing.confirmed
        or existing.review_status is FieldReviewStatus.CONFIRMED
    ):
        return existing
    if _is_empty(existing.value):
        return FieldValue(
            candidate.field_key,
            candidate.text,
            FieldProvenance.OCR,
            FieldReviewStatus.CANDIDATE,
            raw_transcription=candidate.raw_transcription if candidate.raw_transcription is not None else candidate.text,
            confidence=candidate.confidence,
            source_region=candidate.field_key,
        )
    if existing.provenance is FieldProvenance.OCR and replace_ocr_candidate:
        return FieldValue(
            candidate.field_key,
            candidate.text,
            FieldProvenance.OCR,
            FieldReviewStatus.CANDIDATE,
            raw_transcription=candidate.raw_transcription if candidate.raw_transcription is not None else candidate.text,
            confidence=candidate.confidence,
            source_region=candidate.field_key,
        )
    return existing


def edit_field_value(existing: FieldValue | None, field_key: str, value: str) -> FieldValue:
    """Record first manual entry or an edit without claiming it is reviewed."""
    if existing is not None and existing.field_key != field_key:
        raise ValueError(f"existing field {existing.field_key!r} does not match {field_key!r}")
    if existing is not None and str(existing.value) == value:
        return existing
    first_manual_entry = existing is None or _is_empty(existing.value)
    return FieldValue(
        field_key=field_key,
        value=value,
        provenance=FieldProvenance.MANUAL if first_manual_entry else FieldProvenance.USER_EDITED,
        review_status=FieldReviewStatus.CANDIDATE,
        raw_transcription=existing.raw_transcription if existing is not None else None,
        confidence=existing.confidence if existing is not None else None,
        source_region=existing.source_region if existing is not None else None,
    )


def confirm_field_value(existing: FieldValue) -> FieldValue:
    """Mark explicit user confirmation while preserving original provenance."""
    return FieldValue(
        field_key=existing.field_key,
        value=existing.value,
        provenance=existing.provenance,
        review_status=FieldReviewStatus.CONFIRMED,
        raw_transcription=existing.raw_transcription,
        confidence=existing.confidence,
        confirmed=True,
        source_region=existing.source_region,
    )


def merge_checkbox_proposal(
    existing: CheckboxValue | None,
    proposal: CheckboxValue,
    *,
    replace_ocr_candidate: bool = False,
) -> CheckboxValue | None:
    """Merge an independent mark proposal without overwriting user decisions."""
    if existing is not None and existing.field_key != proposal.field_key:
        raise ValueError(
            f"proposal field {proposal.field_key!r} does not match "
            f"existing field {existing.field_key!r}"
        )
    if existing is None:
        return proposal
    if proposal.state is CheckboxState.UNKNOWN:
        return existing
    if existing.confirmed or existing.provenance in (
        FieldProvenance.MANUAL,
        FieldProvenance.USER_EDITED,
    ):
        return existing
    if existing.state is CheckboxState.UNKNOWN:
        return proposal
    if existing.provenance is FieldProvenance.OCR and replace_ocr_candidate:
        return proposal
    return existing


def merge_shared_text_candidate(
    existing: SharedTextCandidate | None,
    candidate: SharedTextCandidate,
) -> SharedTextCandidate:
    """Keep the combined Strecke/Lage line raw and avoid silent retry replacement."""
    if existing is not None and existing.region_key != candidate.region_key:
        raise ValueError(
            f"candidate region {candidate.region_key!r} does not match "
            f"existing region {existing.region_key!r}"
        )
    if existing is None or not existing.raw_text.strip():
        return candidate
    if not candidate.raw_text.strip():
        return existing
    return existing
