from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from PIL import Image
import pytest

from startkartenleser.application.ports import (
    AlignmentAttempt,
    ConcurrentCardUpdate,
    LineRecognitionResult,
)
from startkartenleser.application.use_cases import StartkartenUseCases, UseCaseError
from startkartenleser.domain.contracts import (
    AlignmentQuality,
    AlignmentResult,
    Card,
    CardEvent,
    CardState,
    CheckboxState,
    CheckboxValue,
    FieldProvenance,
    FieldReviewStatus,
    FieldValue,
    RecognitionCandidate,
    RecognitionStatus,
    Session,
)
from startkartenleser.domain.rules import transition_card
from startkartenleser.domain.schema import (
    CARD_LAYOUT_A6_V1,
    CARD_LAYOUT_A6_V2,
    RECOGNITION_REGIONS,
    SCHEMA_VERSION,
    recognition_regions_for_layout,
)


NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)


class FakeSessions:
    def __init__(self):
        self.items = {}

    def create_session(self, session):
        self.items[session.id] = session
        return session

    def get_session(self, session_id):
        return self.items.get(session_id)

    def list_sessions(self):
        return tuple(sorted(self.items.values(), key=lambda item: item.created_at, reverse=True))

    def delete_session(self, session_id):
        del self.items[session_id]


class FakeCards:
    def __init__(self, sessions: FakeSessions):
        self.sessions = sessions
        self.items = {}
        self.fields = {}
        self.checkboxes = {}
        self.shared = {}
        self.fail_create = False

    def create_card(self, card):
        if self.fail_create:
            raise OSError("simulated repository write failure")
        if card.session_id not in self.sessions.items:
            raise KeyError(card.session_id)
        if any(
            item.session_id == card.session_id and item.sequence == card.sequence
            for item in self.items.values()
        ):
            raise ValueError("duplicate sequence")
        self.items[card.id] = card
        self.fields[card.id] = {}
        self.checkboxes[card.id] = {}
        self.shared[card.id] = {}
        return card

    def get_card(self, card_id):
        return self.items.get(card_id)

    def list_cards(self, session_id):
        return tuple(
            sorted(
                (card for card in self.items.values() if card.session_id == session_id),
                key=lambda card: card.sequence,
            )
        )

    def next_sequence(self, session_id):
        return max((card.sequence for card in self.list_cards(session_id)), default=0) + 1

    def transition_card(self, card_id, expected_revision, event):
        card = self._expect_revision(card_id, expected_revision)
        updated = replace(
            card,
            state=transition_card(card.state, event),
            revision=card.revision + 1,
            updated_at=NOW,
        )
        self.items[card_id] = updated
        return updated

    def get_field_values(self, card_id):
        return dict(self.fields[card_id])

    def get_checkbox_values(self, card_id):
        return dict(self.checkboxes[card_id])

    def get_shared_candidates(self, card_id):
        return dict(self.shared[card_id])

    def save_recognition(
        self, card_id, expected_revision, fields, checkboxes, shared_candidates, model_version
    ):
        card = self._expect_revision(card_id, expected_revision)
        if card.state is not CardState.RECOGNIZING:
            raise ConcurrentCardUpdate("card is no longer recognizing")
        self.fields[card_id] = dict(fields)
        self.checkboxes[card_id] = dict(checkboxes)
        self.shared[card_id] = dict(shared_candidates)
        updated = replace(
            card,
            state=CardState.NEEDS_REVIEW,
            model_version=model_version,
            revision=card.revision + 1,
            updated_at=NOW,
        )
        self.items[card_id] = updated
        return updated

    def save_review(self, card_id, expected_revision, fields, checkboxes):
        card = self._expect_revision(card_id, expected_revision)
        if card.state not in (CardState.NEEDS_REVIEW, CardState.REVIEWED):
            raise ValueError("card is not ready to review")
        self.fields[card_id] = dict(fields)
        self.checkboxes[card_id] = dict(checkboxes)
        updated = replace(
            card,
            state=CardState.REVIEWED,
            revision=card.revision + 1,
            updated_at=NOW,
        )
        self.items[card_id] = updated
        return updated

    def set_field_during_inference(self, card_id, value):
        self.fields[card_id][value.field_key] = value
        self.items[card_id] = replace(self.items[card_id], revision=self.items[card_id].revision + 1)

    def _expect_revision(self, card_id, expected_revision):
        card = self.items[card_id]
        if card.revision != expected_revision:
            raise ConcurrentCardUpdate("stale revision")
        return card


class FakeImages:
    def __init__(self):
        self.saved = {}
        self.deleted = []
        self.fail_store = False

    def store_selected(self, source_path):
        if self.fail_store:
            raise OSError("copy failed")
        image_reference = f"managed-{len(self.saved) + 1}"
        self.saved[image_reference] = source_path
        return image_reference

    def read_image(self, image_reference):
        return image_reference

    def delete_image(self, image_reference):
        self.deleted.append(image_reference)
        self.saved.pop(image_reference, None)


class FakeAligner:
    def __init__(
        self,
        quality=AlignmentQuality.ACCEPTED,
        layout_version="card-layout-v1",
        skipped_text_regions=(),
    ):
        self.quality = quality
        self.layout_version = layout_version
        self.skipped_text_regions = tuple(skipped_text_regions)
        self.calls = []

    def align(self, image):
        self.calls.append(image)
        text_crops = {
            key: key
            for key in recognition_regions_for_layout(self.layout_version)
            if key not in self.skipped_text_regions
        }
        checkbox_crops = {
            "checkbox_female": "female-crop",
            "checkbox_male": "male-crop",
        }
        return AlignmentAttempt(
            AlignmentResult(
                self.quality,
                reason_key="error.alignment_uncertain" if self.quality is not AlignmentQuality.ACCEPTED else None,
                schema_version=self.layout_version,
            ),
            text_crops,
            checkbox_crops,
            skipped_text_regions=self.skipped_text_regions,
        )


class FakeRecognizer:
    def __init__(self, cards: FakeCards, status=RecognitionStatus.COMPLETED, *, on_first_call=None):
        self.cards = cards
        self.status = status
        self.on_first_call = on_first_call
        self.calls = []

    def recognize(self, field_key, crop, cancellation=None):
        self.calls.append((field_key, crop))
        if len(self.calls) == 1 and self.on_first_call:
            self.on_first_call()
        if self.status is RecognitionStatus.COMPLETED:
            return LineRecognitionResult(
                RecognitionStatus.COMPLETED,
                RecognitionCandidate(field_key, f"suggestion-{field_key}"),
            )
        return LineRecognitionResult(self.status, error_key="error.model_unavailable")


class FakeCheckboxProposer:
    def propose(self, field_key, crop):
        state = CheckboxState.CHECKED if field_key == "female" else CheckboxState.UNKNOWN
        return CheckboxValue(field_key, state, FieldProvenance.OCR)


class FakeRetention:
    def __init__(self):
        self.deleted_cards = []
        self.deleted_sessions = []
        self.fail = False

    def delete_card(self, card_id):
        if self.fail:
            raise OSError("cleanup pending")
        self.deleted_cards.append(card_id)

    def delete_session(self, session_id):
        if self.fail:
            raise OSError("cleanup pending")
        self.deleted_sessions.append(session_id)


def _use_cases(*, aligner=None, recognizer=None, images=None, correction_policy=None):
    sessions = FakeSessions()
    cards = FakeCards(sessions)
    images = images or FakeImages()
    aligner = aligner or FakeAligner()
    recognizer = recognizer or FakeRecognizer(cards)
    retention = FakeRetention()
    use_cases = StartkartenUseCases(
        sessions,
        cards,
        images,
        aligner,
        recognizer,
        FakeCheckboxProposer(),
        retention=retention,
        clock=lambda: NOW,
        correction_policy=correction_policy,
    )
    return use_cases, sessions, cards, images, aligner, recognizer, retention


def _create_card(use_cases):
    session = use_cases.create_session("Sitzung")
    return session, use_cases.accept_image(session.id, "/selected/card.jpg")


def test_create_list_open_session_and_next_card_sequence() -> None:
    use_cases, _, _, _, _, _, _ = _use_cases()
    first = use_cases.create_session("Wettkampf")

    assert use_cases.list_sessions() == (first,)
    assert use_cases.open_session(first.id) == first
    assert use_cases.next_card_sequence(first.id) == 1
    with pytest.raises(UseCaseError, match="error.session_not_found"):
        use_cases.open_session("missing")


def test_accept_image_persists_capture_draft_before_recognition() -> None:
    use_cases, _, cards, images, _, recognizer, _ = _use_cases()
    session = use_cases.create_session("Session")

    first = use_cases.accept_image(session.id, "/selected/one.jpg")
    second = use_cases.accept_image(session.id, "/selected/two.png")

    assert (first.sequence, second.sequence) == (1, 2)
    assert first.state is CardState.CAPTURED
    assert first.image_reference in images.saved
    assert cards.get_card(first.id) == first
    assert recognizer.calls == []


def test_image_acceptance_failure_does_not_leave_managed_copy() -> None:
    use_cases, _, cards, images, _, _, _ = _use_cases()
    session = use_cases.create_session("Session")
    cards.fail_create = True

    with pytest.raises(OSError):
        use_cases.accept_image(session.id, "/selected/one.jpg")

    assert images.saved == {}
    assert images.deleted == ["managed-1"]
    assert cards.items == {}


def test_missing_session_and_image_copy_failure_do_not_create_card() -> None:
    use_cases, _, cards, images, _, _, _ = _use_cases()
    with pytest.raises(UseCaseError):
        use_cases.accept_image("missing", "/selected/one.jpg")
    assert not images.saved

    session = use_cases.create_session("Session")
    images.fail_store = True
    with pytest.raises(OSError):
        use_cases.accept_image(session.id, "/selected/one.jpg")
    assert cards.items == {}


def test_process_card_persists_suggestions_and_shared_line_without_splitting() -> None:
    use_cases, _, cards, _, aligner, recognizer, _ = _use_cases()
    _, card = _create_card(use_cases)

    result = use_cases.process_card(card.id)

    assert result.card.state is CardState.NEEDS_REVIEW
    assert result.outcome.status is RecognitionStatus.COMPLETED
    assert len(recognizer.calls) == len(RECOGNITION_REGIONS)
    assert result.outcome.shared_candidates[0].region_key == "course_position"
    assert result.outcome.shared_candidates[0].raw_text == "suggestion-course_position"
    assert cards.shared[card.id]["course_position"].raw_text == "suggestion-course_position"
    assert "course_position" not in cards.fields[card.id]
    assert cards.fields[card.id]["name"].provenance is FieldProvenance.OCR
    assert cards.checkboxes[card.id]["female"].state is CheckboxState.CHECKED
    assert cards.checkboxes[card.id]["male"].state is CheckboxState.UNKNOWN
    assert aligner.calls == [card.image_reference]


def test_process_card_recognizes_separate_a6_course_and_position_fields() -> None:
    aligner = FakeAligner(layout_version=CARD_LAYOUT_A6_V1)
    use_cases, _, cards, _, _, recognizer, _ = _use_cases(aligner=aligner)
    _, card = _create_card(use_cases)

    result = use_cases.process_card(card.id)

    assert result.outcome.status is RecognitionStatus.COMPLETED
    assert "course" in cards.fields[card.id]
    assert "position" in cards.fields[card.id]
    assert cards.fields[card.id]["time"].value == (
        "suggestion-time_minutes min suggestion-time_seconds,"
        "suggestion-time_fraction sek"
    )
    assert cards.shared[card.id] == {}
    assert len(recognizer.calls) == len(recognition_regions_for_layout(CARD_LAYOUT_A6_V1))


def test_blank_a6_text_regions_are_not_treated_as_alignment_failures() -> None:
    skipped = recognition_regions_for_layout(CARD_LAYOUT_A6_V1)
    aligner = FakeAligner(
        layout_version=CARD_LAYOUT_A6_V1,
        skipped_text_regions=skipped,
    )
    use_cases, _, cards, _, _, recognizer, _ = _use_cases(aligner=aligner)
    _, card = _create_card(use_cases)

    result = use_cases.process_card(card.id)

    assert result.outcome.status is RecognitionStatus.COMPLETED
    assert result.outcome.error_key is None
    assert cards.fields[card.id] == {}
    assert recognizer.calls == []


def test_line_layout_recognizes_time_directly_without_composing_digit_segments() -> None:
    aligner = FakeAligner(layout_version=CARD_LAYOUT_A6_V2)
    use_cases, _, cards, _, _, recognizer, _ = _use_cases(aligner=aligner)
    _, card = _create_card(use_cases)

    result = use_cases.process_card(card.id)

    assert result.outcome.status is RecognitionStatus.COMPLETED
    assert cards.fields[card.id]["time"].value == "suggestion-time"
    assert len(recognizer.calls) == len(recognition_regions_for_layout(CARD_LAYOUT_A6_V2))
    assert cards.shared[card.id] == {}


def test_configured_correction_is_persisted_with_raw_ocr_and_does_not_replace_manual_values():
    from startkartenleser.infrastructure.correction_policy import load_correction_policy

    class AbbreviatedRecognizer:
        def recognize(self, field_key, crop, cancellation=None):
            return LineRecognitionResult(
                RecognitionStatus.COMPLETED,
                RecognitionCandidate(field_key, "R" if field_key == "position" else "1"),
            )

    use_cases, _, cards, _, _, _, _ = _use_cases(
        aligner=FakeAligner(layout_version=CARD_LAYOUT_A6_V2),
        recognizer=AbbreviatedRecognizer(),
        correction_policy=load_correction_policy(),
    )
    _, card = _create_card(use_cases)
    use_cases.process_card(card.id)
    value = cards.fields[card.id]["position"]
    assert value.value == "Rücken"
    assert value.raw_transcription == "R"
    assert value.review_status is FieldReviewStatus.CANDIDATE
    manual = FieldValue("position", "Brust", FieldProvenance.MANUAL, FieldReviewStatus.CANDIDATE)
    cards.fields[card.id]["position"] = manual
    use_cases.process_card(card.id, approve_replace_ocr_candidates=True)
    assert cards.fields[card.id]["position"] == manual


def test_a6_time_is_not_composed_when_a_marked_segment_fails_recognition() -> None:
    class MissingFractionRecognizer:
        def recognize(self, field_key, crop, cancellation=None):
            if field_key == "time_fraction":
                return LineRecognitionResult(RecognitionStatus.PARTIAL)
            return LineRecognitionResult(
                RecognitionStatus.COMPLETED,
                RecognitionCandidate(field_key, f"suggestion-{field_key}"),
            )

    aligner = FakeAligner(layout_version=CARD_LAYOUT_A6_V1)
    use_cases, _, cards, _, _, _, _ = _use_cases(
        aligner=aligner,
        recognizer=MissingFractionRecognizer(),
    )
    _, card = _create_card(use_cases)

    result = use_cases.process_card(card.id)

    assert result.outcome.status is RecognitionStatus.PARTIAL
    assert "time" not in cards.fields[card.id]


def test_alignment_failure_keeps_draft_for_manual_review_without_ocr() -> None:
    aligner = FakeAligner(AlignmentQuality.NEEDS_MANUAL_ADJUSTMENT)
    use_cases, _, cards, _, _, recognizer, _ = _use_cases(aligner=aligner)
    _, card = _create_card(use_cases)

    result = use_cases.process_card(card.id)

    assert result.card.state is CardState.NEEDS_REVIEW
    assert result.outcome.error_key == "error.alignment_uncertain"
    assert recognizer.calls == []
    assert cards.fields[card.id] == {}


def test_model_unavailable_keeps_recoverable_card_state() -> None:
    recognizer = FakeRecognizer(FakeCards(FakeSessions()), RecognitionStatus.UNAVAILABLE)
    use_cases, _, cards, _, _, _, _ = _use_cases(recognizer=recognizer)
    _, card = _create_card(use_cases)

    result = use_cases.process_card(card.id)

    assert result.card.state is CardState.NEEDS_REVIEW
    assert result.outcome.status is RecognitionStatus.UNAVAILABLE
    assert result.outcome.error_key == "error.model_unavailable"


def test_cancel_before_work_returns_durable_draft_to_review() -> None:
    use_cases, _, _, _, aligner, recognizer, _ = _use_cases()
    _, card = _create_card(use_cases)
    import threading

    cancellation = threading.Event()
    cancellation.set()

    result = use_cases.process_card(card.id, cancellation=cancellation)

    assert result.card.state is CardState.NEEDS_REVIEW
    assert result.outcome.status is RecognitionStatus.CANCELLED
    assert aligner.calls == []
    assert recognizer.calls == []


def test_retry_preserves_manual_values_and_confirmed_checkbox_states() -> None:
    use_cases, _, cards, _, _, _, _ = _use_cases()
    _, card = _create_card(use_cases)
    cards.fields[card.id]["year"] = FieldValue(
        "year", "2000", FieldProvenance.MANUAL, FieldReviewStatus.CANDIDATE
    )
    cards.checkboxes[card.id]["female"] = CheckboxValue(
        "female", CheckboxState.UNCHECKED, FieldProvenance.USER_EDITED, confirmed=True
    )

    result = use_cases.process_card(card.id)

    assert result.card.state is CardState.NEEDS_REVIEW
    assert cards.fields[card.id]["year"].value == "2000"
    assert cards.fields[card.id]["name"].value == "suggestion-name"
    assert cards.checkboxes[card.id]["female"].state is CheckboxState.UNCHECKED


def test_late_recognition_cannot_overwrite_a_concurrent_user_edit() -> None:
    recognizer = FakeRecognizer(
        FakeCards(FakeSessions()),
        on_first_call=lambda: None,
    )
    use_cases, _, cards, _, _, _, _ = _use_cases(recognizer=recognizer)
    _, card = _create_card(use_cases)

    def concurrent_edit():
        cards.set_field_during_inference(
            card.id,
            FieldValue(
                "name", "Manual name", FieldProvenance.USER_EDITED, FieldReviewStatus.CANDIDATE
            ),
        )

    recognizer.on_first_call = concurrent_edit
    result = use_cases.process_card(card.id)

    assert result.card.revision > card.revision
    assert result.outcome.status is RecognitionStatus.CANCELLED
    assert cards.fields[card.id]["name"].value == "Manual name"


def test_explicit_review_save_confirms_values_and_moves_card_to_reviewed() -> None:
    use_cases, _, cards, _, _, _, _ = _use_cases()
    _, card = _create_card(use_cases)
    cards.items[card.id] = replace(card, state=CardState.NEEDS_REVIEW, revision=2)
    value = FieldValue("name", "Ada", FieldProvenance.OCR, FieldReviewStatus.CANDIDATE)
    checkbox = CheckboxValue("female", CheckboxState.CHECKED, FieldProvenance.OCR)

    reviewed = use_cases.save_review(card.id, 2, {"name": value}, {"female": checkbox})

    assert reviewed.state is CardState.REVIEWED
    assert cards.fields[card.id]["name"].provenance is FieldProvenance.OCR
    assert cards.fields[card.id]["name"].confirmed
    assert cards.checkboxes[card.id]["female"].confirmed


@pytest.mark.parametrize("raw_year", ["'02", "102"])
def test_reopening_review_normalizes_existing_ocr_and_save_persists_displayed_values(raw_year):
    from startkartenleser.infrastructure.correction_policy import load_correction_policy

    use_cases, _, cards, _, _, _, _ = _use_cases(correction_policy=load_correction_policy())
    _, card = _create_card(use_cases)
    cards.items[card.id] = replace(card, state=CardState.NEEDS_REVIEW)
    for key, raw in (("position", "D"), ("year", raw_year), ("time", "42, 18"), ("course", "50")):
        cards.fields[card.id][key] = FieldValue(
            key, raw, FieldProvenance.OCR, FieldReviewStatus.CANDIDATE,
            raw_transcription=raw,
        )

    reviewed_card, fields, checkboxes, _ = use_cases.card_review_data(card.id)

    assert {key: value.value for key, value in fields.items()} == {
        "position": "Schmetterling", "year": "2002", "time": "0:42,18", "course": "50 m",
    }
    assert fields["time"].raw_transcription == "42, 18"
    assert cards.fields[card.id]["time"].value == "42, 18"
    assert reviewed_card.revision == card.revision
    use_cases.save_review(card.id, card.revision, fields, checkboxes)
    assert cards.fields[card.id]["time"].value == "0:42,18"
    assert cards.fields[card.id]["year"].value == "2002"
    assert cards.fields[card.id]["course"].value == "50 m"
    assert cards.fields[card.id]["course"].raw_transcription == "50"
    assert cards.fields[card.id]["time"].confirmed
    assert use_cases.card_review_data(card.id)[1] == cards.fields[card.id]


@pytest.mark.parametrize("raw_year", ["'02", "102"])
def test_new_recognition_persists_normalized_time_and_year_for_review(raw_year):
    from startkartenleser.infrastructure.correction_policy import load_correction_policy

    class TimeYearRecognizer:
        def recognize(self, field_key, crop, cancellation=None):
            return LineRecognitionResult(
                RecognitionStatus.COMPLETED,
                RecognitionCandidate(
                    field_key, {"year": raw_year, "time": "42, 18", "course": "50m"}.get(field_key, "")
                ),
            )

    use_cases, _, cards, _, _, _, _ = _use_cases(
        correction_policy=load_correction_policy(),
        recognizer=TimeYearRecognizer(),
        aligner=FakeAligner(layout_version=CARD_LAYOUT_A6_V2),
    )
    _, card = _create_card(use_cases)
    use_cases.process_card(card.id)
    fields = use_cases.card_review_data(card.id)[1]
    assert fields["year"].value == "2002"
    assert fields["year"].raw_transcription == raw_year
    assert fields["time"].value == "0:42,18"
    assert fields["time"].raw_transcription == "42, 18"
    assert fields["course"].value == "50 m"
    assert fields["course"].raw_transcription == "50m"
    assert fields == cards.fields[card.id]


@pytest.mark.parametrize(("provenance", "status", "confirmed"), [
    (FieldProvenance.MANUAL, FieldReviewStatus.CANDIDATE, False),
    (FieldProvenance.USER_EDITED, FieldReviewStatus.CANDIDATE, False),
    (FieldProvenance.OCR, FieldReviewStatus.CONFIRMED, False),
    (FieldProvenance.OCR, FieldReviewStatus.CANDIDATE, True),
])
def test_review_postprocessing_preserves_protected_values(provenance, status, confirmed):
    from startkartenleser.infrastructure.correction_policy import load_correction_policy

    use_cases, _, cards, _, _, _, _ = _use_cases(correction_policy=load_correction_policy())
    _, card = _create_card(use_cases)
    value = FieldValue("year", "'02", provenance, status, confirmed=confirmed)
    cards.fields[card.id]["year"] = value
    assert use_cases.card_review_data(card.id)[1]["year"] == value


def test_retry_replaces_existing_ocr_candidates_only_with_explicit_approval() -> None:
    use_cases, _, cards, _, _, _, _ = _use_cases()
    _, card = _create_card(use_cases)
    cards.fields[card.id]["name"] = FieldValue(
        "name", "previous OCR", FieldProvenance.OCR, FieldReviewStatus.CANDIDATE
    )

    first = use_cases.process_card(card.id)
    assert first.card.state is CardState.NEEDS_REVIEW
    assert cards.fields[card.id]["name"].value == "previous OCR"

    second = use_cases.process_card(card.id, approve_replace_ocr_candidates=True)
    assert second.card.state is CardState.NEEDS_REVIEW
    assert cards.fields[card.id]["name"].value == "suggestion-name"


def test_delete_uses_retention_coordinator_and_surfaces_cleanup_failure() -> None:
    use_cases, _, _, _, _, _, retention = _use_cases()
    session, card = _create_card(use_cases)

    use_cases.delete_card(card.id)
    use_cases.delete_session(session.id)
    assert retention.deleted_cards == [card.id]
    assert retention.deleted_sessions == [session.id]

    retention.fail = True
    with pytest.raises(UseCaseError, match="error.delete_failed"):
        use_cases.delete_card(card.id)
