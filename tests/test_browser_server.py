from __future__ import annotations

import base64
import csv
from datetime import datetime, timezone
import io
import json
import sqlite3
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from PIL import Image
import pytest

from startkartenleser.application.ports import AlignmentAttempt, LineRecognitionResult
from startkartenleser.application.use_cases import StartkartenUseCases
from startkartenleser.browser_server import BrowserServer
from startkartenleser.browser_workflow import BrowserWorkflow
from startkartenleser.domain.contracts import (
    AlignmentQuality, AlignmentResult, Card, CardState, CheckboxState, CheckboxValue,
    FieldProvenance, FieldReviewStatus, FieldValue,
    RecognitionCandidate, RecognitionStatus, Session,
)
from startkartenleser.domain.schema import RECOGNITION_REGIONS
from startkartenleser.infrastructure.application_lock import application_lock
from startkartenleser.infrastructure.correction_policy import load_correction_policy
from startkartenleser.infrastructure.correction_policy import StrokeOption
from startkartenleser.infrastructure.image_store import ManagedImageStore
from startkartenleser.infrastructure.sqlite_repositories import CleanupPendingError, SqliteRepositories
from startkartenleser.localization import TextCatalog


class Aligner:
    def __init__(self):
        self.layout_version = "card-layout-v1"

    def align(self, image):
        return AlignmentAttempt(
            AlignmentResult(AlignmentQuality.ACCEPTED, schema_version=self.layout_version),
            {"wk_number": object(), **{key: object() for key in RECOGNITION_REGIONS}},
            {key: object() for key in ("checkbox_female", "checkbox_male")},
        )


class Recognizer:
    def __init__(self):
        self.started = Event()
        self.release = Event()
        self.release.set()
        self.course_position = "50m Rücken"
        self.wk_number = "2"

    def recognize(self, field_key, crop, cancellation=None):
        self.started.set()
        assert self.release.wait(10)
        return LineRecognitionResult(
            RecognitionStatus.COMPLETED, RecognitionCandidate(
                field_key, {
                    "name": "OCR name",
                    "course_position": self.course_position,
                    "wk_number": self.wk_number,
                }.get(field_key, "")
            )
        )


class Marks:
    def __init__(self):
        self.states = {}

    def propose(self, field_key, crop):
        return CheckboxValue(
            field_key, self.states.get(field_key, CheckboxState.UNKNOWN), FieldProvenance.OCR,
        )


@pytest.fixture
def server(tmp_path):
    images = ManagedImageStore(tmp_path / "images")
    repo = SqliteRepositories(tmp_path / "app.sqlite3", images)
    recognizer = Recognizer()
    marks = Marks()
    cases = StartkartenUseCases(
        repo, repo, images, Aligner(), recognizer, marks,
        retention=repo, correction_policy=load_correction_policy(),
    )
    workflow = BrowserWorkflow(repo, images, cases, TextCatalog.load())
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>bundled UI</html>")
    server = BrowserServer(workflow, static=static)
    thread = Thread(target=server.serve_forever)
    thread.start()
    yield server
    recognizer.release.set()
    workflow.cancellation.set()
    server.shutdown()
    server.server_close()
    thread.join()
    repo.close()


def request(server, path, method="GET", payload=None, *, auth=True, origin=True, headers=None):
    request_headers = {}
    if auth:
        request_headers["X-App-Token"] = server.token
    if origin:
        request_headers["Origin"] = server.origin
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    request_headers.update(headers or {})
    data = json.dumps(payload).encode() if payload is not None else None
    try:
        response = urlopen(Request(
            server.origin + path, data=data, method=method, headers=request_headers,
        ), timeout=15)
    except HTTPError as error:
        response = error
    with response:
        content = response.read()
        result = json.loads(content) if response.headers.get_content_type() == "application/json" else content
        return response.status if hasattr(response, "status") else response.code, result, response.headers


def session(server, *, distance=50, stroke="ruecken", gender="female"):
    status, body, _ = request(server, "/api/sessions", "POST", {
        "number": 2, "distance_m": distance, "stroke": stroke, "gender": gender,
    })
    assert status == 201
    return body


def capture_payload(session_id, **extra):
    output = io.BytesIO()
    Image.new("RGB", (80, 60), (30, 80, 110)).save(output, "PNG")
    return {
        "session_id": session_id, "request_id": str(uuid4()),
        "image": "data:image/png;base64," + base64.b64encode(output.getvalue()).decode(),
        **extra,
    }


def capture(server, session_id):
    status, body, _ = request(server, "/api/capture", "POST", capture_payload(session_id))
    assert status == 200
    return body


def test_offline_assets_and_http_boundary(server):
    status, body, headers = request(server, "/", auth=False, origin=False)
    assert status == 200 and b"bundled UI" in body
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["Permissions-Policy"] == "camera=(self), microphone=()"
    assert headers["Cache-Control"] == "no-store"
    assert request(server, "/api/bootstrap", auth=False)[0] == 403
    assert request(server, "/api/bootstrap", headers={"Host": "evil.invalid"})[0] == 403
    assert request(server, "/api/bootstrap", headers={"Origin": "https://evil.invalid"})[0] == 403
    assert request(server, "/api/sessions", "POST", {}, origin=False)[0] == 403
    assert request(server, "/../app.sqlite3")[0] == 404
    assert request(server, "/api/bootstrap", origin=False)[0] == 200
    assert "Access-Control-Allow-Origin" not in headers


@pytest.mark.parametrize("changes", [
    {"number": 0}, {"number": True}, {"number": 1.5}, {"number": "2"},
    {"distance_m": -1}, {"distance_m": 0}, {"stroke": ""}, {"stroke": "  "},
    {"stroke": "x" * 81}, {"stroke": "bad\nname"}, {"gender": "guessed"},
    {"stroke": []}, {"stroke": True},
])
def test_invalid_event_metadata_is_explicitly_rejected(server, changes):
    payload = {"number": 2, "distance_m": 50, "stroke": "ruecken", "gender": "female", **changes}
    status, body, _ = request(server, "/api/sessions", "POST", payload)
    assert status == 400
    assert body["message"] and body["error"] == "browser.invalid_request"
    assert not server.workflow.repositories.list_sessions()


def test_configured_strokes_drive_bootstrap_creation_and_card_expectation(server):
    defaults = request(server, "/api/bootstrap")[1]["strokes"]
    assert defaults == [
        {"value": "freistil", "label": "Freistil"},
        {"value": "brust", "label": "Brust"},
        {"value": "ruecken", "label": "Rücken"},
        {"value": "schmetterling", "label": "Schmetterling"},
        {"value": "lagen", "label": "Lagen"},
        {"value": "flossenschwimmen_mit_brett", "label": "Flossenschwimmen mit Brett"},
        {"value": "freistil_mit_flossen", "label": "Freistil mit Flossen"},
    ]

    server.workflow.strokes = (StrokeOption("kraul_spezial", "Kraul Spezial", ("Kraul",)),)
    assert request(server, "/api/bootstrap")[1]["strokes"] == [
        {"value": "kraul_spezial", "label": "Kraul Spezial"},
    ]
    event = session(server, stroke="kraul_spezial")
    assert event["title"] == "Wettkampf 2 · 50 m Kraul Spezial · Weiblich"
    assert server.workflow.export_filename(event["id"]) == "wettkampf-2-50m-kraul-spezial-weiblich.csv"
    card = capture(server, event["id"])
    assert card["fields"]["position"]["value"] == "Kraul Spezial"


def test_unlisted_custom_stroke_can_be_used_for_one_wettkampf(server):
    event = session(server, stroke="Speziallage")
    assert event["stroke"] == "Speziallage"
    assert event["stroke_label"] == "Speziallage"
    assert event["title"] == "Wettkampf 2 · 50 m Speziallage · Weiblich"

    card = capture(server, event["id"])
    assert card["fields"]["position"]["value"] == "Speziallage"


def test_mixed_wettkampf_group_does_not_assume_a_single_gender_checkbox(server):
    event = session(server, gender="mixed")
    assert event["gender"] == "mixed"
    assert event["title"] == "Wettkampf 2 · 50 m Rücken · Mixed"
    card = capture(server, event["id"])
    server.workflow.use_cases.recognizer.course_position = "50m Rücken"
    server.workflow.use_cases.checkbox_proposer.states = {
        "female": CheckboxState.CHECKED,
        "male": CheckboxState.UNCHECKED,
    }

    status, result, _ = request(server, f"/api/cards/{card['id']}/recognize", "POST", {
        "revision": card["revision"],
    })

    assert status == 200
    assert result["reference_check"]["warnings"] == {}


def test_session_card_count_in_bootstrap_and_detail(server):
    event = session(server)
    assert event["card_count"] == 0

    bootstrap = request(server, "/api/bootstrap")[1]
    bootstrap_event = next(item for item in bootstrap["sessions"] if item["id"] == event["id"])
    assert bootstrap_event["card_count"] == 0
    detail = request(server, f"/api/sessions/{event['id']}")[1]
    assert detail["session"]["card_count"] == 0

    capture(server, event["id"])
    bootstrap = request(server, "/api/bootstrap")[1]
    bootstrap_event = next(item for item in bootstrap["sessions"] if item["id"] == event["id"])
    assert bootstrap_event["card_count"] == 1
    detail = request(server, f"/api/sessions/{event['id']}")[1]
    assert detail["session"]["card_count"] == 1


def test_wettkampf_capture_autosave_approve_reopen_export(server):
    event = session(server)
    assert event["title"] == "Wettkampf 2 · 50 m Rücken · Weiblich"
    card = capture(server, event["id"])
    assert card["state"] == "needs_review"
    assert card["fields"]["course"]["value"] == "50"
    assert card["fields"]["position"]["value"] == "Rücken"
    assert card["checkboxes"]["female"]["state"] == "checked"
    assert card["checkboxes"]["male"]["state"] == "unchecked"
    status, saved, _ = request(server, f"/api/cards/{card['id']}", "PATCH", {
        "revision": card["revision"],
        "fields": {
            "name": "=formula", "first_name": "Alex", "time": "0:42,18",
            "year": "unclear", "course": "75", "position": "Brust",
        },
        "checkboxes": {"female": "checked", "male": "checked"},
    })
    assert status == 200
    assert saved["state"] == "needs_review"
    assert saved["validation"]["year"]
    assert not saved["fields"]["name"]["confirmed"]
    status, approved, _ = request(server, f"/api/cards/{card['id']}/approve", "POST", {
        "revision": saved["revision"],
    })
    assert status == 200 and approved["state"] == "reviewed"
    assert approved["fields"]["name"]["confirmed"]
    reopened = request(server, f"/api/cards/{card['id']}")[1]
    assert reopened == approved
    csv_status, data, headers = request(server, f"/api/sessions/{event['id']}/export")
    assert csv_status == 200
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))
    assert rows[0]["name"] == "'=formula"
    assert rows[0]["time_ms"] == "42180"
    assert rows[0]["female_mark"] == rows[0]["male_mark"] == "checked"
    assert rows[0]["course"] == "75"
    assert rows[0]["position"] == "Brust"
    assert rows[0]["wk_number"] == "2"
    assert rows[0]["csv_version"] == "2"
    assert "wettkampf_id" not in rows[0]
    assert "gender_key" not in rows[0]
    assert headers["Content-Disposition"] == (
        'attachment; filename="wettkampf-2-50m-ruecken-weiblich.csv"'
    )
    assert request(server, f"/api/cards/{card['id']}/image")[1].startswith(b"\x89PNG")


def test_export_blocks_empty_and_drafts_and_editing_approved_card_revokes_approval(server):
    event = session(server)
    csv_path = f"/api/sessions/{event['id']}/export"
    assert request(server, csv_path)[0] == 400
    card = capture(server, event["id"])
    assert request(server, csv_path)[0] == 409
    approved = request(server, f"/api/cards/{card['id']}/approve", "POST", {"revision": 0})[1]
    assert approved["state"] == "reviewed"
    saved = request(server, f"/api/cards/{card['id']}", "PATCH", {
        "revision": approved["revision"], "fields": {"name": "New"},
    })[1]
    assert saved["state"] == "needs_review"
    assert request(server, csv_path)[0] == 409


def test_export_uses_approved_card_data_and_wettkampf_only_for_filename(server):
    event = session(server, distance=50, stroke="ruecken", gender="female")
    card = capture(server, event["id"])
    saved = request(server, f"/api/cards/{card['id']}", "PATCH", {
        "revision": card["revision"],
        "fields": {
            "wk_number": "8", "course": "100", "position": "Brust",
            "name": "Card swimmer", "heat": "3", "lane": "4", "time": "1:02,34",
        },
        "checkboxes": {"female": "unchecked", "male": "checked"},
    })[1]
    request(server, f"/api/cards/{card['id']}/approve", "POST", {
        "revision": saved["revision"],
    })

    status, data, headers = request(server, f"/api/sessions/{event['id']}/export")

    assert status == 200
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))
    assert len(rows) == 1
    assert rows[0]["wk_number"] == "8"
    assert rows[0]["course"] == "100"
    assert rows[0]["position"] == "Brust"
    assert rows[0]["female_mark"] == "unchecked"
    assert rows[0]["male_mark"] == "checked"
    assert rows[0]["name"] == "Card swimmer"
    assert rows[0]["time_ms"] == "62340"
    assert headers["Content-Disposition"] == (
        'attachment; filename="wettkampf-2-50m-ruecken-weiblich.csv"'
    )


def test_capture_idempotency_survives_reload_and_rejects_reuse(server):
    event = session(server)
    payload = capture_payload(event["id"])
    first = request(server, "/api/capture", "POST", payload)[1]
    second = request(server, "/api/capture", "POST", payload)[1]
    assert first == second
    assert len(server.workflow.images.list_image_references()) == 1
    other_event = session(server)
    assert request(server, "/api/capture", "POST", {
        **payload, "session_id": other_event["id"],
    })[0] == 409
    assert len(server.workflow.repositories.list_cards(event["id"])) == 1


def test_stale_writes_approval_and_retake_do_not_change_saved_data(server):
    event = session(server)
    card = capture(server, event["id"])
    saved = request(server, f"/api/cards/{card['id']}", "PATCH", {
        "revision": 0, "fields": {"name": "User"},
    })[1]
    assert request(server, f"/api/cards/{card['id']}", "PATCH", {
        "revision": 0, "fields": {"name": "Lost"},
    })[0] == 409
    assert request(server, f"/api/cards/{card['id']}/approve", "POST", {"revision": 0})[0] == 409
    assert request(server, "/api/capture", "POST", capture_payload(
        event["id"], replace_card_id=card["id"], revision=0,
    ))[0] == 409
    assert request(server, f"/api/cards/{card['id']}")[1] == saved


def test_successful_retake_preserves_identity_and_sequence_resets_values_and_deletes_old_image(server):
    event = session(server)
    card = capture(server, event["id"])
    second = capture(server, event["id"])
    saved = request(server, f"/api/cards/{card['id']}", "PATCH", {
        "revision": 0, "fields": {"name": "Old"}, "checkboxes": {"female": "checked"},
    })[1]
    payload = capture_payload(event["id"], replace_card_id=card["id"], revision=saved["revision"])
    status, retaken, _ = request(server, "/api/capture", "POST", payload)
    assert status == 200
    assert (retaken["id"], retaken["sequence"]) == (card["id"], card["sequence"])
    assert retaken["fields"]["course"]["value"] == "50"
    assert retaken["fields"]["position"]["value"] == "Rücken"
    assert retaken["checkboxes"]["female"]["state"] == "checked"
    assert retaken["checkboxes"]["male"]["state"] == "unchecked"
    assert retaken["image_reference"] != card["image_reference"]
    assert len(server.workflow.images.list_image_references()) == 2
    assert request(server, "/api/capture", "POST", payload)[1] == retaken
    assert second["sequence"] == 2


def test_failed_retake_keeps_old_image_and_values(server):
    event = session(server)
    card = capture(server, event["id"])
    payload = capture_payload(
        event["id"], replace_card_id=card["id"], revision=0,
        image="data:image/png;base64,bm90LWFuLWltYWdl",
    )
    assert request(server, "/api/capture", "POST", payload)[0] == 400
    assert request(server, f"/api/cards/{card['id']}")[1] == card
    assert len(server.workflow.images.list_image_references()) == 1


def test_committed_retake_reports_pending_cleanup_as_warning(server, monkeypatch):
    event = session(server)
    card = capture(server, event["id"])
    def pending():
        raise CleanupPendingError("retry later")
    monkeypatch.setattr(server.workflow.repositories, "retry_pending_cleanup", pending)
    status, body, _ = request(server, "/api/capture", "POST", capture_payload(
        event["id"], replace_card_id=card["id"], revision=0,
    ))
    assert status == 200
    assert body["warning"]
    assert body["revision"] == 1
    assert server.workflow.repositories.pending_cleanup_count() == 1


@pytest.mark.parametrize("patch", [
    {"fields": {"unknown": "oops"}}, {"fields": {"name": None}},
    {"checkboxes": {"female": True}}, {"checkboxes": {"male": "maybe"}},
    {"fields": []}, {"revision": True}, {"fields": {"name": "x" * 4001}},
])
def test_invalid_draft_shapes_are_not_silently_saved(server, patch):
    card = capture(server, session(server)["id"])
    assert request(server, f"/api/cards/{card['id']}", "PATCH", {"revision": 0, **patch})[0] == 400
    assert request(server, f"/api/cards/{card['id']}")[1] == card


def test_real_pipeline_adapter_is_used_and_manual_values_are_protected(server):
    card = capture(server, session(server)["id"])
    saved = request(server, f"/api/cards/{card['id']}", "PATCH", {
        "revision": 0, "fields": {"name": "Human"},
    })[1]
    status, recognized, _ = request(server, f"/api/cards/{card['id']}/recognize", "POST", {
        "revision": saved["revision"],
    })
    assert status == 200
    assert recognized["recognition"]["status"] == "completed"
    assert recognized["fields"]["name"]["value"] == "Human"
    assert recognized["shared_candidates"]["course_position"]["raw_text"] == "50m Rücken"


@pytest.mark.parametrize(
    ("distance", "stroke", "gender", "reading", "checked", "unchecked"),
    [
        (100, "brust", "male", "100m B", "male", "female"),
        (100, "ruecken", "female", "100 R", "female", "male"),
        (50, "freistil", "male", "50 K", "male", "female"),
        (100, "freistil", "female", "100m Kraul", "female", "male"),
    ],
)
def test_reference_check_accepts_course_and_stroke_aliases(
    server, distance, stroke, gender, reading, checked, unchecked,
):
    event = session(server, distance=distance, stroke=stroke, gender=gender)
    card = capture(server, event["id"])
    server.workflow.use_cases.recognizer.course_position = reading
    server.workflow.use_cases.checkbox_proposer.states = {
        checked: CheckboxState.CHECKED, unchecked: CheckboxState.UNCHECKED,
    }

    status, result, _ = request(server, f"/api/cards/{card['id']}/recognize", "POST", {
        "revision": card["revision"],
    })

    assert status == 200
    assert result["reference_check"]["warnings"] == {}
    assert result["fields"]["course"]["value"] == str(distance)
    expected_position = {"brust": "Brust", "ruecken": "Rücken", "freistil": "Freistil"}[stroke]
    assert result["fields"]["position"]["value"] == expected_position
    assert result["fields"]["course"]["raw_transcription"] == reading
    assert result["fields"]["wk_number"]["value"] == "2"
    assert result["fields"]["wk_number"]["raw_transcription"] == "2"
    assert result["reference_check"]["run_id"]


def test_reference_check_compares_wk_number_without_replacing_event_metadata(server):
    event = session(server)
    card = capture(server, event["id"])
    server.workflow.use_cases.recognizer.wk_number = "3"
    server.workflow.use_cases.aligner.layout_version = "card-layout-a6-v4"

    _, result, _ = request(server, f"/api/cards/{card['id']}/recognize", "POST", {
        "revision": card["revision"],
    })

    assert result["reference_check"]["warnings"]["wk_number"] == {
        "expected": "2", "detected": "3",
    }
    assert result["fields"]["wk_number"]["value"] == "2"
    assert result["fields"]["wk_number"]["raw_transcription"] == "3"


def test_reference_check_reports_mismatches_and_current_raw_readings(server):
    event = session(server, distance=50, stroke="ruecken", gender="female")
    card = capture(server, event["id"])
    server.workflow.use_cases.recognizer.course_position = "100m Brust"
    server.workflow.use_cases.checkbox_proposer.states = {
        "male": CheckboxState.CHECKED, "female": CheckboxState.UNCHECKED,
    }

    _, result, _ = request(server, f"/api/cards/{card['id']}/recognize", "POST", {
        "revision": card["revision"],
    })

    assert result["reference_check"]["warnings"] == {
        "course": {"expected": "50", "detected": "100"},
        "position": {"expected": "Rücken", "detected": "Brust"},
        "gender": {"expected": "Weiblich", "detected": "Männlich"},
    }
    assert result["fields"]["course"]["value"] == "50"
    assert result["fields"]["position"]["value"] == "Rücken"
    assert result["fields"]["course"]["raw_transcription"] == "100m Brust"
    assert result["shared_candidates"]["course_position"]["raw_text"] == "100m Brust"


@pytest.mark.parametrize(
    ("reading", "marks"),
    [
        ("", {}),
        ("50m Rücken 100m Brust", {
            "female": CheckboxState.CHECKED, "male": CheckboxState.CHECKED,
        }),
    ],
)
def test_reference_check_warns_for_missing_and_ambiguous_evidence(server, reading, marks):
    event = session(server)
    card = capture(server, event["id"])
    server.workflow.use_cases.recognizer.course_position = reading
    server.workflow.use_cases.checkbox_proposer.states = marks

    _, result, _ = request(server, f"/api/cards/{card['id']}/recognize", "POST", {
        "revision": card["revision"],
    })

    warnings = result["reference_check"]["warnings"]
    assert warnings["course"] == {"expected": "50", "detected": None}
    assert warnings["position"] == {"expected": "Rücken", "detected": None}
    assert warnings["gender"] == {"expected": "Weiblich", "detected": None}


def test_repeated_ocr_uses_fresh_evidence_after_manual_overrides_and_keeps_run_stable(server):
    event = session(server, distance=50, stroke="ruecken", gender="female")
    card = capture(server, event["id"])
    server.workflow.use_cases.recognizer.course_position = "100m Brust"
    server.workflow.use_cases.checkbox_proposer.states = {
        "male": CheckboxState.CHECKED, "female": CheckboxState.UNCHECKED,
    }
    _, first, _ = request(server, f"/api/cards/{card['id']}/recognize", "POST", {
        "revision": card["revision"],
    })
    first_run = first["reference_check"]["run_id"]

    _, manual, _ = request(server, f"/api/cards/{card['id']}", "PATCH", {
        "revision": first["revision"],
        "fields": {"course": "75", "position": "Brust"},
        "checkboxes": {"male": "checked", "female": "unchecked"},
    })
    assert manual["fields"]["course"]["value"] == "75"
    assert manual["fields"]["position"]["value"] == "Brust"
    assert manual["reference_check"]["run_id"] == first_run

    server.workflow.use_cases.recognizer.course_position = "50m R"
    server.workflow.use_cases.checkbox_proposer.states = {
        "female": CheckboxState.CHECKED, "male": CheckboxState.UNCHECKED,
    }
    _, second, _ = request(server, f"/api/cards/{card['id']}/recognize", "POST", {
        "revision": manual["revision"],
    })
    assert second["reference_check"]["run_id"] != first_run
    assert second["reference_check"]["warnings"] == {}
    assert second["fields"]["course"]["value"] == "50"
    assert second["fields"]["position"]["value"] == "Rücken"
    assert second["fields"]["course"]["raw_transcription"] == "50m R"
    reopened = request(server, f"/api/cards/{card['id']}")[1]
    assert reopened["reference_check"] == second["reference_check"]
    assert reopened["fields"] == second["fields"]


def test_edits_during_slow_ocr_win_and_card_remains_reviewable(server):
    card = capture(server, session(server)["id"])
    recognizer = server.workflow.use_cases.recognizer
    recognizer.release.clear()
    result = []
    thread = Thread(target=lambda: result.append(request(
        server, f"/api/cards/{card['id']}/recognize", "POST", {"revision": 0},
    )))
    thread.start()
    assert recognizer.started.wait(5)
    current = request(server, f"/api/cards/{card['id']}")[1]
    status, saved, _ = request(server, f"/api/cards/{card['id']}", "PATCH", {
        "revision": current["revision"], "fields": {"name": "Typed during OCR"},
    })
    assert status == 200
    recognizer.release.set()
    thread.join(10)
    assert not thread.is_alive()
    assert result[0][0] == 200
    assert result[0][1]["recognition"]["status"] == "cancelled"
    assert request(server, f"/api/cards/{card['id']}")[1] == saved


def test_move_preserves_manual_values_until_ocr_uses_destination_event(server):
    source = session(server, distance=50, stroke="ruecken", gender="female")
    destination = session(server, distance=100, stroke="brust", gender="male")
    card = capture(server, source["id"])
    _, manual, _ = request(server, f"/api/cards/{card['id']}", "PATCH", {
        "revision": card["revision"], "fields": {"course": "75", "position": "Lagen"},
    })

    _, moved, _ = request(server, f"/api/cards/{card['id']}/move", "POST", {
        "revision": manual["revision"], "session_id": destination["id"],
    })
    assert moved["fields"]["course"]["value"] == "75"
    assert moved["fields"]["position"]["value"] == "Lagen"

    server.workflow.use_cases.recognizer.course_position = "100m B"
    server.workflow.use_cases.checkbox_proposer.states = {
        "male": CheckboxState.CHECKED, "female": CheckboxState.UNCHECKED,
    }
    _, recognized, _ = request(server, f"/api/cards/{card['id']}/recognize", "POST", {
        "revision": moved["revision"],
    })
    assert recognized["fields"]["course"]["value"] == "100"
    assert recognized["fields"]["position"]["value"] == "Brust"
    assert recognized["reference_check"]["warnings"] == {}


def test_legacy_batch_is_readable_not_guessed_and_requires_explicit_card_move(server):
    repo = server.workflow.repositories
    legacy = repo.create_session(Session("old", "Mixed old batch", datetime.now(timezone.utc)))
    empty_legacy_card = repo.create_card(Card(
        "legacy-empty", legacy.id, 99, CardState.NEEDS_REVIEW, None, "startkarte-v1",
    ))
    legacy_detail = request(server, f"/api/cards/{empty_legacy_card.id}")[1]
    assert legacy_detail["fields"] == {}
    assert "reference_check" not in legacy_detail
    repo.delete_card(empty_legacy_card.id)
    event = session(server)
    card = capture(server, event["id"])
    approved = request(server, f"/api/cards/{card['id']}/approve", "POST", {"revision": 0})[1]
    # Simulate a pre-migration mixed-batch card without inferring any metadata.
    with repo._transaction() as connection:
        connection.execute("UPDATE cards SET session_id=? WHERE id=?", (legacy.id, card["id"]))
    data = request(server, "/api/sessions/old")[1]
    assert data["session"]["number"] is None
    assert request(server, "/api/capture", "POST", capture_payload("old"))[0] == 400
    assert request(server, "/api/sessions/old/export")[0] == 400
    status, moved, _ = request(server, f"/api/cards/{card['id']}/move", "POST", {
        "revision": approved["revision"], "session_id": event["id"],
    })
    assert status == 200 and moved["session_id"] == event["id"]
    assert moved["state"] == "needs_review"
    assert not request(server, "/api/sessions/old")[1]["cards"]


def test_delete_removes_cards_and_managed_images(server):
    event = session(server)
    card = capture(server, event["id"])
    assert request(server, f"/api/cards/{card['id']}", "DELETE")[0] == 200
    assert not server.workflow.images.list_image_references()
    capture(server, event["id"])
    assert request(server, f"/api/sessions/{event['id']}", "DELETE")[0] == 200
    assert not server.workflow.images.list_image_references()
    assert not server.workflow.repositories.list_sessions()


def test_v1_migration_makes_consistent_backup_and_does_not_infer_metadata(tmp_path):
    # Recreate the actual v1 column shape, independently of the v2 repository.
    database = tmp_path / "old.sqlite3"
    images = ManagedImageStore(tmp_path / "images")
    source = tmp_path / "source.png"
    Image.new("RGB", (20, 20)).save(source)
    reference = images.store_selected(str(source))
    repo = SqliteRepositories(database, images)
    old = repo.create_session(Session("old", "50m maybe mixed", datetime.now(timezone.utc)))
    card = repo.create_card(Card("legacy-card", old.id, 1, CardState.NEEDS_REVIEW, reference, "v1"))
    fields = {
        "course": FieldValue(
            "course", "100 m", FieldProvenance.OCR, FieldReviewStatus.CANDIDATE,
            raw_transcription="100m",
        )
    }
    saved = repo.save_draft(card.id, card.revision, fields, {})
    repo.close()
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE capture_requests")
        for column in ("number", "distance_m", "stroke", "gender"):
            connection.execute(f"ALTER TABLE sessions DROP COLUMN {column}")
        connection.execute("PRAGMA user_version=1")
    migrated = SqliteRepositories(database, images)
    assert migrated.get_session(old.id) == old
    assert migrated.get_session(old.id).number is None
    assert migrated.get_card(card.id) == saved
    assert migrated.get_field_values(card.id) == fields
    assert images.read_image(reference).size == (20, 20)
    with sqlite3.connect(database.with_suffix(".before-v2.sqlite3")) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 1
        assert backup.execute("SELECT title FROM sessions").fetchone()[0] == old.title
    migrated.close()


def test_application_data_lock_is_released_and_prevents_parallel_cleanup(tmp_path):
    with application_lock(tmp_path):
        with pytest.raises(OSError):
            with application_lock(tmp_path):
                pytest.fail("second process lock acquired")
    with application_lock(tmp_path):
        pass


def test_reopened_browser_fields_keep_raw_ocr_and_show_current_correction_policy(server):
    card = capture(server, session(server)["id"])
    repo = server.workflow.repositories
    fields = {
        key: FieldValue(
            key, raw, FieldProvenance.OCR, FieldReviewStatus.CANDIDATE,
            raw_transcription=raw,
        )
        for key, raw in (("position", "D"), ("year", "111"), ("time", "42, 18"), ("course", "50"))
    }
    repo.save_draft(card["id"], 0, fields, {})
    detail = request(server, f"/api/cards/{card['id']}")[1]
    assert detail["fields"]["year"]["value"] == "2011"
    assert detail["fields"]["time"]["value"] == "0:42,18"
    assert detail["fields"]["position"]["value"] == "Schmetterling"
    assert detail["fields"]["course"]["value"] == "50 m"
    assert detail["fields"]["year"]["raw_transcription"] == "111"
    assert repo.get_field_values(card["id"])["year"].value == "111"
    approved = request(server, f"/api/cards/{card['id']}/approve", "POST", {"revision": 1})[1]
    assert approved["fields"]["year"]["value"] == "2011"
    assert repo.get_field_values(card["id"])["year"].value == "2011"


def test_recognition_cannot_start_on_a_retake_after_request_revision_was_checked(server, monkeypatch):
    event = session(server)
    card = capture(server, event["id"])
    cases = server.workflow.use_cases
    process = cases.process_card
    def retake_before_start(card_id, **kwargs):
        with server.workflow.lock:
            server.workflow.capture(capture_payload(
                event["id"], replace_card_id=card_id, revision=0,
            ))
        return process(card_id, **kwargs)
    monkeypatch.setattr(cases, "process_card", retake_before_start)
    status, _, _ = request(server, f"/api/cards/{card['id']}/recognize", "POST", {"revision": 0})
    assert status == 409
    assert not cases.recognizer.started.is_set()
    current = request(server, f"/api/cards/{card['id']}")[1]
    assert current["revision"] == 1
    assert current["state"] == "needs_review"
    assert current["fields"]["course"]["value"] == "50"


def test_capture_request_and_values_survive_database_restart(server):
    event = session(server)
    payload = capture_payload(event["id"])
    card = request(server, "/api/capture", "POST", payload)[1]
    saved = request(server, f"/api/cards/{card['id']}", "PATCH", {
        "revision": 0, "fields": {"name": "Persisted"},
    })[1]
    repo = server.workflow.repositories
    reopened = SqliteRepositories(repo.database_path, server.workflow.images)
    try:
        assert reopened.get_session(event["id"]).number == 2
        assert reopened.get_card(card["id"]).revision == saved["revision"]
        assert reopened.get_field_values(card["id"])["name"].value == "Persisted"
        import hashlib
        fingerprint = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode()).hexdigest()
        assert reopened.capture_request(payload["request_id"], fingerprint).id == card["id"]
    finally:
        reopened.close()


def test_crop_overlay_endpoint_keeps_source_pixel_geometry(server):
    card = capture(server, session(server)["id"])
    status, body, _ = request(server, f"/api/cards/{card['id']}/overlays")
    assert status == 200
    assert (body["width"], body["height"]) == (80, 60)
    assert body["overlays"] == []
    assert body["error_key"] is None
    assert body["aligned"] is False
    status, png, _ = request(server, f"/api/cards/{card['id']}/card-image")
    assert status == 200
    assert Image.open(io.BytesIO(png)).size == (80, 60)


class RectifyingAligner:
    def __init__(self):
        self.calls = 0

    def align(self, image):
        self.calls += 1
        return AlignmentAttempt(
            AlignmentResult(AlignmentQuality.ACCEPTED, schema_version="card-layout-a6-v2"),
            {}, {}, aligned_image=Image.new("RGB", (1050, 1480), "white"),
        )


def test_accepted_card_is_displayed_rectified_with_card_overlays(server):
    card = capture(server, session(server)["id"])
    aligner = RectifyingAligner()
    server.workflow.use_cases.aligner = aligner
    status, body, _ = request(server, f"/api/cards/{card['id']}/overlays")
    assert status == 200
    assert body["aligned"] is True
    assert (body["width"], body["height"]) == (1050, 1480)
    assert body["overlays"]
    for overlay in body["overlays"]:
        assert all(0 <= x <= 1050 and 0 <= y <= 1480 for x, y in overlay["source_corners"])
    status, png, _ = request(server, f"/api/cards/{card['id']}/card-image")
    assert status == 200
    assert Image.open(io.BytesIO(png)).size == (1050, 1480)
    assert aligner.calls == 1
    assert Image.open(io.BytesIO(request(server, f"/api/cards/{card['id']}/image")[1])).size == (80, 60)


@pytest.mark.parametrize("text, exported", [
    (" =SUM(1;2)", "' =SUM(1;2)"),
    ("\x00 \u2003@formula", "'\x00 \u2003@formula"),
    ("\tplain", "'\tplain"),
    ('Müller; "Alex"\nSecond line', 'Müller; "Alex"\nSecond line'),
])
def test_csv_quoting_unicode_and_formula_safety_do_not_mutate_storage(server, text, exported):
    event = session(server)
    card = capture(server, event["id"])
    saved = request(server, f"/api/cards/{card['id']}", "PATCH", {
        "revision": 0, "fields": {"name": text, "heat": "unclear", "lane": "3", "time": "1:99"},
    })[1]
    request(server, f"/api/cards/{card['id']}/approve", "POST", {"revision": saved["revision"]})
    data = request(server, f"/api/sessions/{event['id']}/export")[1]
    assert data.startswith(b"\xef\xbb\xbf")
    assert data.endswith(b"\r\n")
    row = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))[0]
    assert row["name"] == exported
    assert row["heat"] == "" and row["heat_text"] == "unclear"
    assert row["lane"] == row["lane_text"] == "3"
    assert row["time_ms"] == "" and row["time_text"] == "1:99"
    assert server.workflow.repositories.get_field_values(card["id"])["name"].value == text


def test_retake_transaction_failure_restores_old_image_values_and_request_state(server):
    event = session(server)
    card = capture(server, event["id"])
    saved = request(server, f"/api/cards/{card['id']}", "PATCH", {
        "revision": 0, "fields": {"name": "Keep me"},
    })[1]
    repo = server.workflow.repositories
    with repo._transaction() as connection:
        connection.execute(
            """CREATE TRIGGER reject_capture BEFORE INSERT ON capture_requests
               BEGIN SELECT RAISE(ABORT, 'test capture commit failure'); END"""
        )
    payload = capture_payload(event["id"], replace_card_id=card["id"], revision=saved["revision"])
    status, body, _ = request(server, "/api/capture", "POST", payload)
    assert status == 500 and body["error"] == "error.save_failed"
    assert request(server, f"/api/cards/{card['id']}")[1] == saved
    assert repo.pending_cleanup_count() == 0
    assert server.workflow.images.list_image_references() == (card["image_reference"],)
    with repo._transaction() as connection:
        connection.execute("DROP TRIGGER reject_capture")
    assert request(server, "/api/capture", "POST", payload)[0] == 200


def test_duplicate_capture_after_autosave_returns_current_draft_without_resetting_it(server):
    event = session(server)
    payload = capture_payload(event["id"])
    card = request(server, "/api/capture", "POST", payload)[1]
    saved = request(server, f"/api/cards/{card['id']}", "PATCH", {
        "revision": 0, "fields": {"name": "Do not reset"},
    })[1]
    assert request(server, "/api/capture", "POST", payload)[1] == saved
    assert len(server.workflow.images.list_image_references()) == 1


def test_missing_frontend_build_is_an_explicit_startup_error(server, tmp_path):
    with pytest.raises(RuntimeError, match="Browser-Oberfläche fehlt"):
        BrowserServer(server.workflow, static=tmp_path / "not-built")
