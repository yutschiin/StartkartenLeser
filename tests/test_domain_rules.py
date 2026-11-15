import pytest

from startkartenleser.domain.contracts import (
    CardEvent,
    CardState,
    FieldProvenance,
    FieldReviewStatus,
    FieldValue,
    RecognitionCandidate,
    SharedTextCandidate,
)
from startkartenleser.domain.rules import (
    InvalidCardTransition,
    confirm_field_value,
    edit_field_value,
    merge_recognition_candidate,
    merge_shared_text_candidate,
    transition_card,
)
from startkartenleser.domain.validation import (
    parse_time_milliseconds,
    validate_positive_integer,
    validate_year,
)


def test_card_lifecycle_happy_path_and_reviewed_edit() -> None:
    state = CardState.CAPTURED
    state = transition_card(state, CardEvent.START_ALIGNMENT)
    assert state is CardState.ALIGNING
    state = transition_card(state, CardEvent.ALIGNMENT_ACCEPTED)
    assert state is CardState.RECOGNIZING
    state = transition_card(state, CardEvent.RECOGNITION_FINISHED)
    assert state is CardState.NEEDS_REVIEW
    state = transition_card(state, CardEvent.SAVE_REVIEW)
    assert state is CardState.REVIEWED
    assert transition_card(state, CardEvent.EDIT) is CardState.NEEDS_REVIEW


@pytest.mark.parametrize(
    "state,event",
    [
        (CardState.ALIGNING, CardEvent.ALIGNMENT_FAILED),
        (CardState.ALIGNING, CardEvent.CANCEL),
        (CardState.RECOGNIZING, CardEvent.RECOGNITION_FAILED),
        (CardState.RECOGNIZING, CardEvent.CANCEL),
    ],
)
def test_failure_and_cancellation_keep_card_recoverable(state, event) -> None:
    assert transition_card(state, event) is CardState.NEEDS_REVIEW


def test_invalid_card_transition_fails_closed() -> None:
    with pytest.raises(InvalidCardTransition):
        transition_card(CardState.CAPTURED, CardEvent.SAVE_REVIEW)


def test_recognition_fills_a_blank_but_does_not_replace_an_existing_candidate() -> None:
    candidate = RecognitionCandidate("name", "Ada", 0.4)
    empty = FieldValue("name", "", FieldProvenance.OCR, FieldReviewStatus.MISSING)
    filled = merge_recognition_candidate(empty, candidate)
    assert filled is not None
    assert filled.value == "Ada"
    assert filled.provenance is FieldProvenance.OCR
    assert filled.raw_transcription == "Ada"
    assert filled.confidence == 0.4
    assert filled.source_region == "name"

    retry = merge_recognition_candidate(
        filled, RecognitionCandidate("name", "Ado", 0.7)
    )
    assert retry == filled


def test_retry_can_replace_only_an_unconfirmed_ocr_suggestion_with_approval() -> None:
    existing = FieldValue("name", "Ado", FieldProvenance.OCR, FieldReviewStatus.CANDIDATE)
    candidate = RecognitionCandidate("name", "Ada")

    assert merge_recognition_candidate(existing, candidate).value == "Ado"
    replaced = merge_recognition_candidate(existing, candidate, replace_ocr_candidate=True)
    assert replaced is not None
    assert replaced.value == "Ada"


@pytest.mark.parametrize(
    "existing",
    [
        FieldValue("name", "", FieldProvenance.MANUAL, FieldReviewStatus.MISSING),
        FieldValue("name", "Ada", FieldProvenance.USER_EDITED, FieldReviewStatus.CANDIDATE),
        FieldValue(
            "name", "Ado", FieldProvenance.OCR, FieldReviewStatus.CONFIRMED, confirmed=True
        ),
    ],
)
def test_retry_never_overwrites_manual_edited_or_confirmed_values(existing) -> None:
    merged = merge_recognition_candidate(
        existing, RecognitionCandidate("name", "OCR"), replace_ocr_candidate=True
    )
    assert merged == existing


def test_manual_entry_and_edits_keep_distinct_provenance() -> None:
    entered = edit_field_value(None, "name", "Ada")
    assert entered.provenance is FieldProvenance.MANUAL

    edited = edit_field_value(entered, "name", "Ada Lovelace")
    assert edited.provenance is FieldProvenance.USER_EDITED
    assert edited.value == "Ada Lovelace"


def test_displaying_an_integer_value_as_text_does_not_change_its_provenance() -> None:
    existing = FieldValue(
        "year", 2012, FieldProvenance.OCR, FieldReviewStatus.CANDIDATE
    )

    assert edit_field_value(existing, "year", "2012") == existing


def test_confirming_ocr_preserves_ocr_provenance() -> None:
    candidate = FieldValue("name", "Ada", FieldProvenance.OCR, FieldReviewStatus.CANDIDATE)

    confirmed = confirm_field_value(candidate)

    assert confirmed.provenance is FieldProvenance.OCR
    assert confirmed.review_status is FieldReviewStatus.CONFIRMED
    assert confirmed.confirmed


def test_shared_course_position_candidate_remains_unresolved_and_retry_safe() -> None:
    initial = SharedTextCandidate("course_position", "Freistil 100 m")
    retry = SharedTextCandidate("course_position", "Freistil 200 m")

    assert merge_shared_text_candidate(None, initial) == initial
    assert merge_shared_text_candidate(initial, retry) == initial
    assert merge_shared_text_candidate(
        SharedTextCandidate("course_position", ""), retry
    ) == retry


@pytest.mark.parametrize("raw,expected", [("1", 1), (" 8 ", 8), (None, None), ("", None)])
def test_positive_integer_values(raw, expected) -> None:
    result = validate_positive_integer(raw)
    assert result.valid
    assert result.value == expected


@pytest.mark.parametrize("raw", ["0", "-2", "+2", "1.5", "١٢", "two"])
def test_invalid_positive_integer(raw) -> None:
    assert validate_positive_integer(raw).error_key == "validation.positive_integer"


def test_year_is_four_digit_and_not_in_the_future() -> None:
    assert validate_year("2000", current_year=2026).value == 2000
    assert validate_year("", current_year=2026).value is None
    for raw in ("99", "1899", "2027", "20a0"):
        assert validate_year(raw, current_year=2026).error_key == "validation.year"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1:02", 62_000),
        ("1:02,3", 62_300),
        ("0:52,34", 52_340),
        ("52.340", 52_340),
        ("1:02:03.4", 3_723_400),
        ("5 min 44,321 sek", 344_321),
        ("5 min 44 sek", 344_000),
        ("44,321 sek", 44_321),
    ],
)
def test_explicit_times_parse_to_canonical_milliseconds(raw, expected) -> None:
    result = parse_time_milliseconds(raw)
    assert result.valid
    assert result.milliseconds == expected
    assert result.raw_text == raw


@pytest.mark.parametrize(
    "raw",
    [
        "52",
        "1:72",
        "1:60:00",
        "1:02,1234",
        "5 min 77 sek",
        "77,1 sek",
        "one minute",
    ],
)
def test_ambiguous_or_invalid_time_is_preserved_without_a_canonical_value(raw) -> None:
    result = parse_time_milliseconds(raw)
    assert not result.valid
    assert result.raw_text == raw
    assert result.milliseconds is None
    assert result.error_key == "validation.time_unrecognized"


def test_empty_time_is_optional_and_not_an_error() -> None:
    result = parse_time_milliseconds("  ")
    assert result.valid
    assert result.milliseconds is None
