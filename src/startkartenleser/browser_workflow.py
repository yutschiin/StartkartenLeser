"""Production browser actions over the existing local storage and OCR pipeline."""

from __future__ import annotations

import base64
import binascii
import csv
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import io
import json
import logging
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from threading import Event, Lock, RLock
from uuid import UUID, uuid4

from startkartenleser.application.ports import ConcurrentCardUpdate
from startkartenleser.application.use_cases import StartkartenUseCases
from startkartenleser.domain.contracts import AlignmentQuality
from startkartenleser.domain.contracts import (
    Card, CardState, CheckboxState, CheckboxValue, FieldProvenance,
    FieldReviewStatus, FieldValue, RecognitionCandidate, RecognitionStatus, Session,
)
from startkartenleser.domain.postprocessing import correct_candidate
from startkartenleser.domain.rules import edit_field_value
from startkartenleser.domain.schema import (
    CARD_LAYOUT_A6_V4,
    CROP_VERSION,
    FIELDS,
    FieldKind,
    SCHEMA_VERSION,
)
from startkartenleser.domain.validation import (
    parse_time_milliseconds, validate_positive_integer, validate_year,
)
from startkartenleser.infrastructure.correction_policy import (
    DEFAULT_STROKE_OPTIONS, StrokeOption,
)
from startkartenleser.infrastructure.image_pipeline import card_region_overlays
from startkartenleser.infrastructure.image_store import ManagedImageStore
from startkartenleser.infrastructure.sqlite_repositories import CleanupPendingError, SqliteRepositories
from startkartenleser.localization import TextCatalog


LOGGER = logging.getLogger(__name__)
STROKES = tuple(option.value for option in DEFAULT_STROKE_OPTIONS)
GENDERS = ("female", "male")
EVENT_GENDERS = (*GENDERS, "mixed")
TEXT_FIELDS = {field.key for field in FIELDS if field.kind is not FieldKind.CHECKBOX}
MARK_FIELDS = {"female", "male"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def _text_key(value: str) -> str:
    return (
        value.casefold().replace("ä", "ae").replace("ö", "oe")
        .replace("ü", "ue").replace("ß", "ss").strip()
    )


def _course_key(value: str) -> str:
    match = re.fullmatch(r"\s*0*([0-9]+)\s*m?\s*", value, re.IGNORECASE)
    return match.group(1) if match else _text_key(value)


def _course_reading(raw: str) -> tuple[str | None, bool]:
    if not raw.strip():
        return None, False
    readings = {
        match.group(1).lstrip("0") or "0"
        for match in re.finditer(r"(?<!\d)(\d+)\s*m?(?!\w)", raw, re.IGNORECASE)
    }
    if len(readings) > 1:
        return None, True
    if len(readings) == 1:
        return readings.pop(), False
    return raw.strip(), False


class BrowserError(ValueError):
    def __init__(self, status: int, key: str) -> None:
        self.status = status
        self.key = key
        super().__init__(key)


def integer(payload: dict, key: str, *, minimum: int = 0) -> int:
    value = payload.get(key)
    if type(value) is not int or not minimum <= value <= 2_147_483_647:
        raise BrowserError(400, "browser.invalid_request")
    return value


def identifier(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise BrowserError(400, "browser.invalid_request")
    return value


class BrowserWorkflow:
    """Serialize human writes, while allowing edits to invalidate slow OCR."""

    def __init__(
        self, repositories: SqliteRepositories, images: ManagedImageStore,
        use_cases: StartkartenUseCases, text: TextCatalog,
        strokes: tuple[StrokeOption, ...] = DEFAULT_STROKE_OPTIONS,
    ) -> None:
        self.repositories = repositories
        self.images = images
        self.use_cases = use_cases
        self.text = text
        self.strokes = strokes
        self.lock = RLock()
        self.recognition_lock = Lock()
        self.cancellation = Event()
        self.display_lock = Lock()
        self.display_cache: dict[tuple[str, str], tuple[object, dict]] = {}

    def session(self, session_id: str, *, classified: bool = False) -> Session:
        session = self.repositories.get_session(session_id)
        if session is None:
            raise BrowserError(404, "error.session_not_found")
        if classified and session.number is None:
            raise BrowserError(400, "browser.legacy_session")
        return session

    def session_data(self, session: Session, *, card_count: int | None = None) -> dict:
        data = asdict(session)
        data["stroke_label"] = self.stroke_label(session.stroke)
        data["card_count"] = (
            len(self.repositories.list_cards(session.id)) if card_count is None else card_count
        )
        return data

    def stroke_label(self, stroke: str | None) -> str:
        if stroke is None:
            return ""
        configured = next(
            (option.label for option in self.strokes if option.value == stroke), None,
        )
        if configured is not None:
            return configured
        label = self.text.messages.get(f"stroke.{stroke}", stroke)
        return label if isinstance(label, str) else stroke

    def create_session(self, payload: dict) -> dict:
        number = integer(payload, "number", minimum=1)
        distance = integer(payload, "distance_m", minimum=1)
        stroke, gender = payload.get("stroke"), payload.get("gender")
        if not isinstance(stroke, str) or gender not in EVENT_GENDERS:
            raise BrowserError(400, "browser.invalid_request")
        stroke = stroke.strip()
        if (
            not stroke
            or len(stroke) > 80
            or any(ord(char) < 32 or ord(char) == 127 for char in stroke)
        ):
            raise BrowserError(400, "browser.invalid_request")
        configured = next(
            (
                option for option in self.strokes
                if option.value == stroke or option.label.casefold() == stroke.casefold()
            ),
            None,
        )
        if configured is not None:
            stroke = configured.value
        title = self.text.text(
            "wettkampf.title", number=number, distance=distance,
            stroke=self.stroke_label(stroke),
            gender=self.text.text(f"gender.{gender}"),
        )
        created = self.repositories.create_session(Session(
            id=str(uuid4()), title=title, created_at=datetime.now(timezone.utc),
            number=number, distance_m=distance, stroke=stroke, gender=gender,
        ))
        return self.session_data(created)

    def card(self, card_id: str, revision: int | None = None) -> Card:
        card = self.repositories.get_card(card_id)
        if card is None:
            raise BrowserError(404, "error.card_not_found")
        if revision is not None and revision != card.revision:
            raise ConcurrentCardUpdate("stale card revision")
        return card

    def card_display(self, card_id: str) -> tuple[object, dict]:
        """Return the image shown in review and its overlays in that image's coordinates.

        Accepted cards are shown rectified (cropped to the card and upright); the
        stored source image stays untouched for retakes and re-alignment.
        """
        card = self.card(card_id)
        key = (card_id, str(card.image_reference))
        with self.display_lock:
            cached = self.display_cache.get(key)
        if cached is not None:
            return cached
        image, attempt = self.use_cases.alignment_for_display(card_id)
        accepted = attempt.result.quality is AlignmentQuality.ACCEPTED
        if accepted and attempt.aligned_image is not None:
            display = attempt.aligned_image
            overlays = card_region_overlays(
                attempt.result.schema_version, aligned_image=attempt.aligned_image,
            )
        else:
            display = image
            overlays = attempt.overlays if accepted else ()
        payload = {
            "width": display.width,
            "height": display.height,
            "aligned": display is not image,
            "overlays": [asdict(overlay) for overlay in overlays],
            "error_key": None if accepted else (
                attempt.result.reason_key or "error.alignment_uncertain"
            ),
        }
        with self.display_lock:
            self.display_cache = {
                cached_key: value for cached_key, value in self.display_cache.items()
                if cached_key[0] != card_id
            }
            if len(self.display_cache) >= 16:
                self.display_cache.pop(next(iter(self.display_cache)))
            self.display_cache[key] = (display, payload)
        return display, payload

    def detail(self, card_id: str) -> dict:
        with self.repositories.read_snapshot():
            return self._detail(card_id)

    def _detail(self, card_id: str) -> dict:
        card = self.card(card_id)
        _, fields, _, _ = self.use_cases.card_review_data(card_id)
        validation = {}
        for key, value in fields.items():
            raw = "" if value.value is None else str(value.value)
            error = None
            if key == "year":
                error = validate_year(raw).error_key
            elif key in ("wk_number", "heat", "lane"):
                error = validate_positive_integer(raw).error_key
            elif key == "time":
                error = parse_time_milliseconds(raw).error_key
            if error is not None:
                validation[key] = self.text.text(error)
        reference_check = self.repositories.get_reference_check(card_id)
        return {
            **asdict(card),
            "fields": {key: asdict(value) for key, value in fields.items()},
            "checkboxes": {
                key: asdict(value)
                for key, value in self.repositories.get_checkbox_values(card_id).items()
            },
            "shared_candidates": {
                key: asdict(value)
                for key, value in self.repositories.get_shared_candidates(card_id).items()
            },
            "validation": validation,
            **({"reference_check": reference_check} if reference_check is not None else {}),
        }

    def capture(self, payload: dict) -> dict:
        session_id = identifier(payload, "session_id")
        self.session(session_id, classified=True)
        request_id = identifier(payload, "request_id")
        try:
            UUID(request_id)
        except ValueError:
            raise BrowserError(400, "browser.invalid_request") from None
        image = payload.get("image")
        if not isinstance(image, str):
            raise BrowserError(400, "error.image_unreadable")
        fingerprint = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode()).hexdigest()
        duplicate = self.repositories.capture_request(request_id, fingerprint)
        if duplicate is not None:
            return self.detail(duplicate.id)
        replacement = payload.get("replace_card_id")
        revision = None
        if replacement is not None:
            replacement = identifier(payload, "replace_card_id")
            revision = integer(payload, "revision")
            if self.card(replacement, revision).session_id != session_id:
                raise BrowserError(400, "browser.invalid_request")
        try:
            prefix, encoded = image.split(",", 1)
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise BrowserError(400, "error.image_unreadable") from None
        if prefix not in ("data:image/png;base64", "data:image/jpeg;base64"):
            raise BrowserError(415, "error.unsupported_image")
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise BrowserError(413, "error.image_too_large")
        with TemporaryDirectory(prefix="startkartenleser-capture-", dir=self.images.directory) as directory:
            source = Path(directory) / "capture"
            source.write_bytes(data)
            reference = self.images.store_selected(str(source))
        now = datetime.now(timezone.utc)
        card = Card(
            id=str(uuid4()), session_id=session_id, sequence=1,
            state=CardState.NEEDS_REVIEW, image_reference=reference,
            schema_version=SCHEMA_VERSION, crop_version=CROP_VERSION,
            created_at=now, updated_at=now,
        )
        event = self.session(session_id, classified=True)
        reference_fields, reference_checkboxes = self._reference_values(event)
        try:
            saved = self.repositories.save_capture(
                card, request_id, fingerprint,
                replace_card_id=replacement, expected_revision=revision,
                fields=reference_fields, checkboxes=reference_checkboxes,
            )
        except Exception:
            # Startup orphan cleanup is the final recovery path for failed unlinks.
            try:
                self.images.delete_image(reference)
            except OSError:
                LOGGER.exception("Capture compensation requires startup cleanup")
            raise
        if saved.image_reference != reference:
            self.images.delete_image(reference)
        # Old retake images are in the durable outbox. A cleanup failure must be
        # visible without reporting that the newly committed image was not saved.
        result = self.detail(saved.id)
        try:
            self.repositories.retry_pending_cleanup()
        except CleanupPendingError:
            LOGGER.exception("Retake image cleanup is pending")
            result["warning"] = self.text.text("browser.cleanup_pending")
        return result

    def save(self, card_id: str, payload: dict) -> dict:
        card = self.card(card_id, integer(payload, "revision"))
        changes = payload.get("fields", {})
        marks = payload.get("checkboxes", {})
        if (
            not isinstance(changes, dict) or not isinstance(marks, dict)
            or not set(changes) <= TEXT_FIELDS or not set(marks) <= MARK_FIELDS
            or any(not isinstance(value, str) or len(value) > 4000 for value in changes.values())
            or any(value not in tuple(CheckboxState) for value in marks.values())
        ):
            raise BrowserError(400, "browser.invalid_request")
        _, suggestions, _, _ = self.use_cases.card_review_data(card_id)
        fields = dict(suggestions)
        checkboxes = dict(self.repositories.get_checkbox_values(card_id))
        for key, value in changes.items():
            existing = fields.get(key)
            edited = edit_field_value(existing, key, value)
            if existing is not None and existing.provenance is FieldProvenance.MANUAL:
                edited = replace(edited, provenance=FieldProvenance.MANUAL)
            fields[key] = edited
        for key, value in marks.items():
            checkboxes[key] = CheckboxValue(key, CheckboxState(value), FieldProvenance.MANUAL)
        self.repositories.save_draft(card_id, card.revision, fields, checkboxes)
        return self.detail(card_id)

    def approve(self, card_id: str, payload: dict) -> dict:
        card = self.card(card_id, integer(payload, "revision"))
        self.session(card.session_id, classified=True)
        _, fields, _, _ = self.use_cases.card_review_data(card_id)
        marks = self.repositories.get_checkbox_values(card_id)
        if card.state not in (CardState.NEEDS_REVIEW, CardState.REVIEWED):
            card = self.repositories.save_draft(card_id, card.revision, fields, marks)
        self.use_cases.save_review(card_id, card.revision, fields, marks)
        return self.detail(card_id)

    def recognize(self, card_id: str, payload: dict) -> dict:
        # ONNX model access is serialized, but normal edits remain independent.
        with self.recognition_lock:
            with self.lock:
                card = self.card(card_id, integer(payload, "revision"))
                if card.state is CardState.REVIEWED:
                    card = self.repositories.save_draft(
                        card_id, card.revision,
                        self.repositories.get_field_values(card_id),
                        self.repositories.get_checkbox_values(card_id),
                    )
            result = self.use_cases.process_card(
                card_id, expected_revision=card.revision, cancellation=self.cancellation,
            )
            with self.lock:
                latest = self.card(card_id)
                session = self.repositories.get_session(latest.session_id)
                if (
                    session is not None and session.number is not None
                    and result.outcome.status is not RecognitionStatus.CANCELLED
                ):
                    self._persist_reference_comparison(
                        latest, session, result.outcome,
                        layout_version=(
                            result.alignment.result.schema_version
                            if result.alignment is not None else ""
                        ),
                    )
                return {
                    **self.detail(card_id),
                    "recognition": {
                        "status": result.outcome.status,
                        "error_key": result.outcome.error_key,
                    },
                }

    def _reference_values(
        self, session: Session, *, raw: dict[str, tuple[str | None, float | None]] | None = None,
    ) -> tuple[dict[str, FieldValue], dict[str, CheckboxValue]]:
        raw = raw or {}
        values = {
            "wk_number": FieldValue(
                "wk_number", str(session.number), FieldProvenance.OCR,
                FieldReviewStatus.CANDIDATE,
                raw_transcription=raw.get("wk_number", (None, None))[0],
                confidence=raw.get("wk_number", (None, None))[1],
                source_region="event_reference",
            ),
            "course": FieldValue(
                "course", str(session.distance_m), FieldProvenance.OCR,
                FieldReviewStatus.CANDIDATE,
                raw_transcription=raw.get("course", (None, None))[0],
                confidence=raw.get("course", (None, None))[1],
                source_region="event_reference",
            ),
            "position": FieldValue(
                "position", self.stroke_label(session.stroke),
                FieldProvenance.OCR, FieldReviewStatus.CANDIDATE,
                raw_transcription=raw.get("position", (None, None))[0],
                confidence=raw.get("position", (None, None))[1],
                source_region="event_reference",
            ),
        }
        marks = {
            key: CheckboxValue(
                key,
                (
                    CheckboxState.UNKNOWN if session.gender == "mixed"
                    else CheckboxState.CHECKED if key == session.gender
                    else CheckboxState.UNCHECKED
                ),
                FieldProvenance.OCR,
            )
            for key in GENDERS
        }
        return values, marks

    def _persist_reference_comparison(self, card, session: Session, outcome, *, layout_version: str) -> None:
        candidates = {item.field_key: item for item in outcome.candidates}
        shared = next(
            (item for item in outcome.shared_candidates if item.region_key == "course_position"),
            None,
        )
        raw_course, confidence_course = self._candidate_raw(candidates.get("course"))
        raw_position, confidence_position = self._candidate_raw(candidates.get("position"))
        if shared is not None:
            raw_course = raw_course or shared.raw_text
            raw_position = raw_position or shared.raw_text
            confidence_course = confidence_course if confidence_course is not None else shared.confidence
            confidence_position = confidence_position if confidence_position is not None else shared.confidence

        course_candidate = candidates.get("course")
        position_candidate = candidates.get("position")
        if course_candidate is not None:
            course_value, ambiguous_course = _course_reading(
                self._candidate_raw(course_candidate)[0] or ""
            )
            raw_course = self._candidate_raw(course_candidate)[0]
            confidence_course = course_candidate.confidence
        elif shared is not None:
            course_value, ambiguous_course = _course_reading(shared.raw_text)
        else:
            course_value, ambiguous_course = None, False

        if position_candidate is not None:
            position_value, ambiguous_position = self._position_reading(
                self._candidate_raw(position_candidate)[0] or "",
                self.use_cases.correction_policy,
            )
            raw_position = self._candidate_raw(position_candidate)[0]
            confidence_position = position_candidate.confidence
        elif shared is not None:
            position_value, ambiguous_position = self._position_reading(
                shared.raw_text, self.use_cases.correction_policy,
            )
        else:
            position_value, ambiguous_position = None, False

        marks = {item.field_key: item.state for item in outcome.checkbox_proposals}
        wk_candidate = candidates.get("wk_number")
        raw_wk_number, confidence_wk_number = self._candidate_raw(wk_candidate)
        wk_validation = validate_positive_integer(raw_wk_number)
        detected_wk_number = (
            str(wk_validation.value) if wk_validation.error_key is None else None
        )
        expected_wk_number = str(session.number)
        detected_gender = None
        if (
            marks.get("female") is CheckboxState.CHECKED
            and marks.get("male") is CheckboxState.UNCHECKED
        ):
            detected_gender = "female"
        elif (
            marks.get("male") is CheckboxState.CHECKED
            and marks.get("female") is CheckboxState.UNCHECKED
        ):
            detected_gender = "male"

        expected_course = str(session.distance_m)
        expected_position = self.stroke_label(session.stroke)
        expected_gender = self.text.text(f"gender.{session.gender}")
        course_matches = (
            course_value is not None and not ambiguous_course
            and _course_key(course_value) == _course_key(expected_course)
        )
        position_matches = (
            position_value is not None and not ambiguous_position
            and _text_key(position_value) == _text_key(expected_position)
        )
        gender_matches = session.gender == "mixed" or detected_gender == session.gender
        warnings = {}
        if layout_version == CARD_LAYOUT_A6_V4 and detected_wk_number != expected_wk_number:
            warnings["wk_number"] = {
                "expected": expected_wk_number,
                "detected": detected_wk_number,
            }
        if not course_matches:
            warnings["course"] = {
                "expected": expected_course,
                "detected": None if ambiguous_course else course_value,
            }
        if not position_matches:
            warnings["position"] = {
                "expected": expected_position,
                "detected": None if ambiguous_position else position_value,
            }
        if not gender_matches:
            warnings["gender"] = {
                "expected": expected_gender,
                "detected": (
                    self.text.text(f"gender.{detected_gender}")
                    if detected_gender is not None else None
                ),
            }

        reference_fields, reference_checkboxes = self._reference_values(
            session,
            raw={
                "wk_number": (raw_wk_number, confidence_wk_number),
                "course": (raw_course, confidence_course),
                "position": (raw_position, confidence_position),
            },
        )
        check = {"run_id": str(uuid4()), "warnings": warnings}
        evidence = {
            "wk_number": self._candidate_evidence(wk_candidate),
            "course": self._candidate_evidence(course_candidate),
            "position": self._candidate_evidence(position_candidate),
            "course_position": (
                {"raw_transcription": shared.raw_text, "confidence": shared.confidence}
                if shared is not None else None
            ),
            "gender": {
                key: (marks[key].value if key in marks else None)
                for key in GENDERS
            },
        }
        self.repositories.save_reference_result(
            card.id, card.revision, reference_fields, reference_checkboxes, check, evidence,
        )

    @staticmethod
    def _candidate_raw(candidate: RecognitionCandidate | None) -> tuple[str | None, float | None]:
        if candidate is None or not candidate.text.strip():
            return None, None
        return candidate.raw_transcription or candidate.text, candidate.confidence

    @staticmethod
    def _candidate_evidence(candidate: RecognitionCandidate | None) -> dict | None:
        if candidate is None:
            return None
        return {
            "raw_transcription": candidate.raw_transcription or candidate.text,
            "confidence": candidate.confidence,
        }

    @staticmethod
    def _position_reading(raw: str, policy) -> tuple[str | None, bool]:
        if not raw.strip():
            return None, False
        key = _text_key(raw)
        entries = (
            policy.positions if policy is not None else (
                ("Freistil", ("F", "Frei", "K", "Kraul")),
                ("Brust", ("B",)),
                ("Rücken", ("R", "Ruecken")),
                ("Schmetterling", ("S", "D", "Delphin")),
                ("Lagen", ()),
            )
        )
        hits = set()
        for canonical, aliases in entries:
            for value in (canonical, *aliases):
                normalized = _text_key(value)
                if re.search(rf"(?<!\w){re.escape(normalized)}(?!\w)", key):
                    hits.add(canonical)
                    break
        if len(hits) > 1:
            return None, True
        if len(hits) == 1:
            return hits.pop(), False
        if policy is not None:
            corrected = correct_candidate(
                RecognitionCandidate("position", raw), policy,
            ).text
            if corrected != raw:
                return corrected, False
        return raw.strip(), False

    def export_filename(self, session_id: str) -> str:
        session = self.session(session_id, classified=True)
        gender = self.text.text(f"gender.{session.gender}").lower()
        stroke = (session.stroke or "lage").lower()
        for umlaut, replacement in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
            gender = gender.replace(umlaut, replacement)
            stroke = stroke.replace(umlaut, replacement)
        stroke = re.sub(r"[^a-z0-9]+", "-", stroke).strip("-") or "lage"
        return (
            f"wettkampf-{session.number}-{session.distance_m}m-"
            f"{stroke}-{gender}.csv"
        )

    def export(self, session_id: str) -> bytes:
        session = self.session(session_id, classified=True)
        cards = self.repositories.list_cards(session_id)
        if not cards:
            raise BrowserError(400, "browser.export_empty")
        if any(card.state is not CardState.REVIEWED for card in cards):
            raise BrowserError(409, "browser.export_drafts")
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter=";", lineterminator="\r\n")
        writer.writerow((
            "csv_version", "wettkampf_id", "wettkampf_number", "distance_m",
            "stroke_key", "gender_key", "card_id", "sequence", "name", "first_name",
            "year_text", "heat", "heat_text", "lane", "lane_text", "time_ms",
            "time_text", "timekeeper", "female_mark", "male_mark",
        ))
        for card in cards:
            fields = self.repositories.get_field_values(card.id)
            marks = self.repositories.get_checkbox_values(card.id)

            def value(key: str) -> str:
                field = fields.get(key)
                return "" if field is None or field.value is None else str(field.value)

            def mark(key: str) -> str:
                return marks[key].state.value if key in marks else CheckboxState.UNKNOWN.value

            time = parse_time_milliseconds(value("time"))
            writer.writerow(tuple(_csv_safe(item) for item in (
                "1", session.id, session.number, session.distance_m, session.stroke,
                session.gender, card.id, card.sequence, value("name"), value("first_name"),
                value("year"), validate_positive_integer(value("heat")).value, value("heat"),
                validate_positive_integer(value("lane")).value, value("lane"),
                time.milliseconds, value("time"), value("timekeeper"),
                mark("female"), mark("male"),
            )))
        return ("\ufeff" + stream.getvalue()).encode("utf-8")


def _csv_safe(value: object) -> str:
    text = "" if value is None else str(value)
    # CSV quoting does not prevent spreadsheet formula evaluation.
    start = 0
    while start < len(text) and (text[start].isspace() or ord(text[start]) < 32):
        start += 1
    if text[start:].startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text
