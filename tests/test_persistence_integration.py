from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import sqlite3

from PIL import Image
import pytest

from startkartenleser.application.ports import ConcurrentCardUpdate
from startkartenleser.domain.contracts import (
    Card,
    CardEvent,
    CardState,
    CheckboxState,
    CheckboxValue,
    FieldProvenance,
    FieldReviewStatus,
    FieldValue,
    RecognitionCandidate,
    Session,
    SharedTextCandidate,
)
from startkartenleser.infrastructure.image_store import ManagedImageStore
from startkartenleser.infrastructure.image_pipeline import ImageInputError
from startkartenleser.infrastructure.paths import AppDataPaths
from startkartenleser.infrastructure.sqlite_repositories import (
    CleanupPendingError,
    SqliteRepositories,
)


NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def _session_card(repo: SqliteRepositories, session_id="session-1", card_id="card-1"):
    session = Session(session_id, "Wettkampf", NOW)
    repo.create_session(session)
    card = Card(
        card_id,
        session_id,
        1,
        CardState.CAPTURED,
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png",
        "startkarte-v1",
        created_at=NOW,
        updated_at=NOW,
    )
    repo.create_card(card)
    return session, card


def _to_recognizing(repo: SqliteRepositories, card: Card) -> Card:
    aligning = repo.transition_card(card.id, card.revision, CardEvent.START_ALIGNMENT)
    return repo.transition_card(aligning.id, aligning.revision, CardEvent.ALIGNMENT_ACCEPTED)


def test_sessions_cards_and_provenance_round_trip_across_reopen(tmp_path) -> None:
    database = tmp_path / "app.sqlite3"
    repo = SqliteRepositories(database)
    session, card = _session_card(repo)
    recognizing = _to_recognizing(repo, card)
    values = {
        "name": FieldValue(
            "name", "Müller", FieldProvenance.OCR, FieldReviewStatus.CANDIDATE,
            raw_transcription="Müller", confidence=None, source_region="name",
        ),
        "year": FieldValue(
            "year", 2012, FieldProvenance.MANUAL, FieldReviewStatus.CONFIRMED,
            confirmed=True,
        ),
    }
    checkboxes = {
        "female": CheckboxValue("female", CheckboxState.UNKNOWN, FieldProvenance.OCR),
        "male": CheckboxValue("male", CheckboxState.CHECKED, FieldProvenance.MANUAL),
    }
    shared = {
        "course_position": SharedTextCandidate("course_position", "Freistil 100 m")
    }
    saved = repo.save_recognition(
        card.id,
        recognizing.revision,
        values,
        checkboxes,
        shared,
        "de-htr-v2.0.0",
    )
    repo.close()

    reopened = SqliteRepositories(database)
    assert reopened.get_session(session.id) == session
    assert reopened.list_cards(session.id) == (saved,)
    assert reopened.get_field_values(card.id) == values
    assert reopened.get_checkbox_values(card.id) == checkboxes
    assert reopened.get_shared_candidates(card.id) == shared
    assert reopened.get_card(card.id).model_version == "de-htr-v2.0.0"
    assert reopened.get_card(card.id).crop_version == "startkarte-crops-v7"
    reviewed = reopened.save_review(
        card.id,
        saved.revision,
        {"name": replace(values["name"], confirmed=True, review_status=FieldReviewStatus.CONFIRMED)},
        checkboxes,
    )
    assert reviewed.state is CardState.REVIEWED
    reopened.close()


def test_card_order_is_stable_and_sequences_are_unique(tmp_path) -> None:
    repo = SqliteRepositories(tmp_path / "app.sqlite3")
    session = Session("session", "Session", NOW)
    repo.create_session(session)
    second = Card("second", session.id, 2, CardState.CAPTURED, None, "v1")
    first = Card("first", session.id, 1, CardState.CAPTURED, None, "v1")
    repo.create_card(second)
    repo.create_card(first)

    assert [card.id for card in repo.list_cards(session.id)] == ["first", "second"]
    assert repo.next_sequence(session.id) == 3
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_card(replace(first, id="duplicate"))
    repo.close()


def test_stale_revision_cannot_transition_card(tmp_path) -> None:
    repo = SqliteRepositories(tmp_path / "app.sqlite3")
    _, card = _session_card(repo)
    repo.transition_card(card.id, card.revision, CardEvent.START_ALIGNMENT)

    with pytest.raises(ConcurrentCardUpdate):
        repo.transition_card(card.id, card.revision, CardEvent.CANCEL)
    repo.close()


def test_interrupted_alignment_and_recognition_recover_to_needs_review(tmp_path) -> None:
    database = tmp_path / "app.sqlite3"
    repo = SqliteRepositories(database)
    _, card = _session_card(repo)
    recognizing = _to_recognizing(repo, card)
    repo.close()

    reopened = SqliteRepositories(database)

    recovered = reopened.get_card(card.id)
    assert recovered.state is CardState.NEEDS_REVIEW
    assert recovered.revision == recognizing.revision + 1
    reopened.close()


def test_schema_migration_is_versioned_and_newer_database_is_rejected(tmp_path) -> None:
    database = tmp_path / "app.sqlite3"
    repo = SqliteRepositories(database)
    assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 3
    repo.close()

    future_database = tmp_path / "future.sqlite3"
    connection = sqlite3.connect(future_database)
    connection.execute("PRAGMA user_version = 99")
    connection.close()
    with pytest.raises(RuntimeError, match="newer than supported"):
        SqliteRepositories(future_database)


def test_reference_result_and_raw_evidence_survive_database_reopen(tmp_path) -> None:
    database = tmp_path / "app.sqlite3"
    repo = SqliteRepositories(database)
    session = Session(
        "event", "Wettkampf", NOW, number=4, distance_m=100, stroke="brust", gender="male",
    )
    repo.create_session(session)
    card = Card("reference-card", session.id, 1, CardState.NEEDS_REVIEW, None, "startkarte-v1")
    repo.create_card(card)
    fields = {
        "course": FieldValue(
            "course", "100", FieldProvenance.OCR, FieldReviewStatus.CANDIDATE,
            raw_transcription="100m B", source_region="event_reference",
        ),
        "position": FieldValue(
            "position", "Brust", FieldProvenance.OCR, FieldReviewStatus.CANDIDATE,
            raw_transcription="100m B", source_region="event_reference",
        ),
    }
    checkboxes = {
        "female": CheckboxValue("female", CheckboxState.UNCHECKED, FieldProvenance.OCR),
        "male": CheckboxValue("male", CheckboxState.CHECKED, FieldProvenance.OCR),
    }
    reference_check = {"run_id": "run-1", "warnings": {}}
    evidence = {
        "course_position": {"raw_transcription": "100m B"},
        "gender": {"female": "unchecked", "male": "checked"},
    }
    repo.save_reference_result(
        card.id, card.revision, fields, checkboxes, reference_check, evidence,
    )
    repo.close()

    reopened = SqliteRepositories(database)
    assert reopened.get_field_values(card.id) == fields
    assert reopened.get_checkbox_values(card.id) == checkboxes
    assert reopened.get_reference_check(card.id) == reference_check
    assert reopened.get_reference_evidence(card.id) == evidence
    reopened.close()


def test_save_recognition_rolls_back_all_value_changes_on_invalid_contract(tmp_path) -> None:
    repo = SqliteRepositories(tmp_path / "app.sqlite3")
    _, card = _session_card(repo)
    recognizing = _to_recognizing(repo, card)
    valid = FieldValue("name", "Ada", FieldProvenance.OCR, FieldReviewStatus.CANDIDATE)
    repo.save_recognition(card.id, recognizing.revision, {"name": valid}, {}, {}, "model")
    current = repo.get_card(card.id)
    reviewed = repo.save_review(
        card.id,
        current.revision,
        {"name": valid},
        {},
    )
    editing = repo.transition_card(card.id, reviewed.revision, CardEvent.EDIT)
    with pytest.raises(AttributeError):
        repo.save_review(
            card.id,
            editing.revision,
            {"name": replace(valid, provenance="not-an-enum")},
            {},
        )
    assert repo.get_card(card.id).state is CardState.NEEDS_REVIEW
    assert repo.get_field_values(card.id)["name"] == valid
    repo.close()


def test_atomic_managed_image_copy_preserves_original_bytes_and_deletes_idempotently(tmp_path) -> None:
    source = tmp_path / "phone-photo.png"
    Image.new("RGB", (40, 30), (100, 120, 140)).save(source)
    original_bytes = source.read_bytes()
    store = ManagedImageStore(tmp_path / "private-images")

    reference = store.store_selected(str(source))
    stored_path = tmp_path / "private-images" / reference
    assert reference.endswith(".png")
    assert stored_path.read_bytes() == original_bytes
    assert store.read_image(reference).size == (40, 30)
    assert source.read_bytes() == original_bytes
    store.delete_image(reference)
    store.delete_image(reference)
    assert not stored_path.exists()


def test_image_store_rejects_bad_files_without_creating_managed_copies(tmp_path) -> None:
    store = ManagedImageStore(tmp_path / "private-images")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")

    with pytest.raises(ImageInputError):
        store.store_selected(str(bad))
    assert list((tmp_path / "private-images").iterdir()) == []
    with pytest.raises(ValueError):
        store.delete_image("../../outside.png")


def test_card_delete_uses_retryable_image_cleanup_outbox(tmp_path) -> None:
    image_dir = tmp_path / "images"
    store = ManagedImageStore(image_dir)
    source = tmp_path / "card.png"
    Image.new("RGB", (20, 20), "white").save(source)
    reference = store.store_selected(str(source))
    repo = SqliteRepositories(tmp_path / "app.sqlite3", store)
    _, card = _session_card(repo)
    repo._connection.execute(
        "UPDATE cards SET image_reference=? WHERE id=?", (reference, card.id)
    )

    original_delete = store.delete_image

    def fail_delete(_reference):
        raise OSError("temporary storage failure")

    store.delete_image = fail_delete
    with pytest.raises(CleanupPendingError):
        repo.delete_card(card.id)
    assert repo.get_card(card.id) is None
    assert repo.pending_cleanup_count() == 1
    assert (image_dir / reference).is_file()

    store.delete_image = original_delete
    repo.retry_pending_cleanup()
    assert repo.pending_cleanup_count() == 0
    assert not (image_dir / reference).exists()
    repo.close()


def test_session_delete_removes_cards_and_all_managed_images(tmp_path) -> None:
    store = ManagedImageStore(tmp_path / "images")
    source = tmp_path / "card.jpg"
    Image.new("RGB", (20, 20), "white").save(source, format="JPEG")
    reference = store.store_selected(str(source))
    repo = SqliteRepositories(tmp_path / "app.sqlite3", store)
    session, card = _session_card(repo)
    repo._connection.execute(
        "UPDATE cards SET image_reference=? WHERE id=?", (reference, card.id)
    )

    repo.delete_session(session.id)

    assert repo.get_session(session.id) is None
    assert repo.get_card(card.id) is None
    assert repo.pending_cleanup_count() == 0
    assert not (tmp_path / "images" / reference).exists()
    repo.close()


def test_storage_recovery_removes_orphaned_images_and_interrupted_temps(tmp_path) -> None:
    store = ManagedImageStore(tmp_path / "images")
    source = tmp_path / "card.png"
    Image.new("RGB", (20, 20), "white").save(source)
    referenced = store.store_selected(str(source))
    orphan = store.store_selected(str(source))
    temporary = store.directory / ("." + "a" * 32 + ".tmp")
    temporary.write_bytes(b"incomplete copy")
    repo = SqliteRepositories(tmp_path / "app.sqlite3", store)
    _, card = _session_card(repo)
    repo._connection.execute(
        "UPDATE cards SET image_reference=? WHERE id=?", (referenced, card.id)
    )

    repo.cleanup_storage_orphans()

    assert (store.directory / referenced).is_file()
    assert not (store.directory / orphan).exists()
    assert not temporary.exists()
    repo.close()


def test_default_data_paths_honor_xdg_and_can_be_created(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    paths = AppDataPaths.default()
    paths.ensure()

    assert paths.root == tmp_path / "xdg" / "startkartenleser"
    assert paths.database.parent == paths.root
    assert paths.images.is_dir()
