from __future__ import annotations

from contextlib import contextmanager
import csv
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

from PIL import Image
import pytest

from startkartenleser.application.ports import AlignmentAttempt, LineRecognitionResult
from startkartenleser.application.use_cases import StartkartenUseCases
from startkartenleser.browser_workflow import BrowserError, BrowserWorkflow
from startkartenleser.domain.contracts import (
    AlignmentQuality, AlignmentResult, CheckboxState, CheckboxValue,
    FieldProvenance, RecognitionCandidate, RecognitionStatus,
)
from startkartenleser.domain.schema import CARD_LAYOUT_A6_V2, recognition_regions_for_layout
from startkartenleser.evaluation import SCORED_FIELDS, matches
from startkartenleser.infrastructure.correction_policy import load_correction_policy
from startkartenleser.infrastructure.image_store import ManagedImageStore
from startkartenleser.infrastructure.sqlite_repositories import SqliteRepositories
from startkartenleser.infrastructure.workflow_adapters import (
    ConservativeCheckboxProposer, LazyDEHTRLineRecognizer, TemplateCardAligner,
)
from startkartenleser.localization import TextCatalog


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load_script("evaluate_wettkampf_workflow")
baseline = load_script("evaluate_reference_dataset")


class Aligner:
    def __init__(self, rejected=()):
        self.rejected = rejected

    def align(self, image):
        number = image.getpixel((0, 0))[0]
        if number in self.rejected:
            return AlignmentAttempt(
                AlignmentResult(AlignmentQuality.REJECTED, reason_key="error.alignment_uncertain"),
                {}, {},
            )
        return AlignmentAttempt(
            AlignmentResult(AlignmentQuality.ACCEPTED, schema_version=CARD_LAYOUT_A6_V2),
            {key: number for key in recognition_regions_for_layout(CARD_LAYOUT_A6_V2)},
            {key: number for key in ("checkbox_female", "checkbox_male")},
        )


class Recognizer:
    def __init__(self, rows, overrides=None):
        self.rows = {int(row["card_no"]): row for row in rows}
        self.overrides = overrides or {}
        self.recognizer = SimpleNamespace(close=lambda: None)

    def recognize(self, field_key, crop, cancellation=None):
        text = self.overrides.get((crop, field_key), self.rows[crop].get(field_key, ""))
        return LineRecognitionResult(
            RecognitionStatus.COMPLETED, RecognitionCandidate(field_key, text),
        )


class Marks:
    def __init__(self, rows, wrong=()):
        self.rows = {int(row["card_no"]): row for row in rows}
        self.wrong = wrong

    def propose(self, field_key, crop):
        selected = "female" if self.rows[crop]["gender"] == "Mädchen" else "male"
        checked = field_key == selected
        if crop in self.wrong:
            checked = not checked
        return CheckboxValue(
            field_key, CheckboxState.CHECKED if checked else CheckboxState.UNCHECKED,
            FieldProvenance.OCR,
        )


@pytest.fixture
def dataset(tmp_path):
    images = tmp_path / "photos"
    images.mkdir()
    with (ROOT / "tests/reference_data.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        Image.new("RGB", (80, 60), (int(row["card_no"]), 30, 50)).save(
            images / row["image_filename"], format="PNG",
        )
    references = tmp_path / "references.csv"

    def write(selected):
        with references.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(selected)
        return references

    write(rows)
    return images, references, rows, write


def workflow_factory(rows, calls, *, overrides=None, wrong_marks=(), rejected=()):
    @contextmanager
    def factory(data_dir, policy):
        images = ManagedImageStore(data_dir / "images")
        repositories = SqliteRepositories(data_dir / "startkartenleser.sqlite3", images)
        cases = StartkartenUseCases(
            repositories, repositories, images, Aligner(rejected), Recognizer(rows, overrides),
            Marks(rows, wrong_marks), retention=repositories, correction_policy=policy,
        )

        class TracedWorkflow(BrowserWorkflow):
            def create_session(self, payload):
                calls.append(("create", payload))
                return super().create_session(payload)

            def capture(self, payload):
                calls.append(("capture", payload["session_id"]))
                return super().capture(payload)

            def recognize(self, card_id, payload):
                calls.append(("recognize", card_id))
                return super().recognize(card_id, payload)

            def approve(self, card_id, payload):
                assert set(payload) == {"revision"}
                before = self.detail(card_id)
                result = super().approve(card_id, payload)
                assert {k: v["value"] for k, v in before["fields"].items()} == {
                    k: v["value"] for k, v in result["fields"].items()
                }
                calls.append(("approve", card_id))
                return result

            def save(self, *args):
                pytest.fail("evaluation must never edit fields")

            def export(self, session_id):
                calls.append(("export", session_id))
                return super().export(session_id)

        try:
            yield TracedWorkflow(repositories, images, cases, TextCatalog.load())
        finally:
            repositories.close()

    return factory


def read_scores(output):
    with (output / "field-scores.csv").open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def test_full_workflow_groups_and_scores_actual_csv_without_edits(dataset, tmp_path):
    images, references, rows, _ = dataset
    before = {path.name: path.read_bytes() for path in images.iterdir()}
    calls = []
    output = tmp_path / "run"
    summary = runner.run(images, output, references, workflow_factory=workflow_factory(rows, calls))
    assert summary["cards"] == 16
    assert summary["observations"] == 144
    assert summary["persisted_correct"] == summary["export_correct"] == summary["ocr_correct"] == 144
    assert summary["blocked_events"] == 0
    policy = load_correction_policy()
    keys = sorted({runner.event_key(row, policy) for row in rows})
    creates = [payload for kind, payload in calls if kind == "create"]
    assert [(p["distance_m"], p["stroke"], p["gender"]) for p in creates] == keys
    assert [p["number"] for p in creates] == list(range(1, len(keys) + 1))
    assert [kind for kind, _ in calls].count("capture") == 16
    stages = [json.loads(line) for line in (output / "stages.jsonl").read_text().splitlines()]
    for index, stage in enumerate(stages):
        if stage["stage"] == "capture":
            assert [item["stage"] for item in stages[index:index + 3]] == ["capture", "recognize", "approve"]
    assert [kind for kind, _ in calls].count("export") == len(keys)
    scores = read_scores(output)
    assert {row["field"] for row in scores} == set(SCORED_FIELDS)
    course = next(row for row in scores if row["field"] == "course")
    assert course["exported_value"] == "50"
    assert course["expected"] == "50 m"
    assert course["final_origin"] == "event_reference"
    assert course["export_origin"] == "event_metadata"
    assert (output / "data/startkartenleser.sqlite3").is_file()
    assert len(list((output / "data/images").iterdir())) == 16
    assert len(list((output / "evidence").glob("*.json"))) == 16
    assert before == {path.name: path.read_bytes() for path in images.iterdir()}
    with pytest.raises(FileExistsError):
        runner.run(images, output, references)


def test_source_archive_run_records_missing_git_metadata(dataset, tmp_path, monkeypatch):
    images, references, rows, write = dataset
    write(rows[:1])
    output = tmp_path / "source-archive-run"

    def no_git(*args, **kwargs):
        raise subprocess.CalledProcessError(128, args[0])

    monkeypatch.setattr(runner.subprocess, "run", no_git)
    runner.run(images, output, references, workflow_factory=workflow_factory(rows, []))

    metadata = json.loads((output / "run.json").read_text())
    assert metadata["git_revision"] is None
    assert metadata["git_dirty"] is None


def test_invalid_values_are_approved_unchanged_and_scored_incorrect(dataset, tmp_path):
    images, references, rows, write = dataset
    # 01 and 15 share an event; 02 is independent. Process all three.
    selected = [rows[14], rows[1], rows[0]]
    write(selected)
    calls = []
    output = tmp_path / "blocked"
    summary = runner.run(
        images, output, references,
        workflow_factory=workflow_factory(selected, calls, overrides={(1, "time"): "not a time"}),
    )
    assert summary["blocked_events"] == 0
    assert summary["observations"] == 27
    scores = read_scores(output)
    assert {row["export_status"] for row in scores if row["card_no"] in {"01", "15"}} == {"exported"}
    assert {row["export_status"] for row in scores if row["card_no"] == "02"} == {"exported"}
    time = next(row for row in scores if row["card_no"] == "01" and row["field"] == "time")
    assert time["persisted_value"] == "not a time"
    stages = [json.loads(line) for line in (output / "stages.jsonl").read_text().splitlines()]
    assert time["export_points"] == "0"
    assert any(stage["stage"] == "validation_warning" and "time" in stage["blockers"] for stage in stages)
    assert sum(kind == "approve" for kind, _ in calls) == 3
    assert sum(kind == "recognize" for kind, _ in calls) == 3
    assert len(list((output / "exports").glob("*.csv"))) == 2


def test_metadata_accuracy_is_not_ocr_accuracy(dataset, tmp_path):
    images, references, rows, write = dataset
    write(rows[:1])
    output = tmp_path / "metadata"
    summary = runner.run(
        images, output, references,
        workflow_factory=workflow_factory(
            rows, [], overrides={(1, "course"): "100 m", (1, "position"): "Brust"},
            wrong_marks=(1,),
        ),
    )
    assert summary["persisted_correct"] == summary["export_correct"] == 9
    assert summary["ocr_correct"] == 6
    scores = read_scores(output)
    for field in ("course", "position", "gender"):
        row = next(row for row in scores if row["field"] == field)
        assert row["ocr_points"] == "0"
        assert row["persisted_points"] == row["export_points"] == "100"
        assert row["ocr_origin"] == "reference_evidence"
    course = next(row for row in scores if row["field"] == "course")
    assert course["raw_ocr"] == "100 m"


def test_alignment_failure_is_preserved_even_when_application_allows_approval(dataset, tmp_path):
    images, references, rows, write = dataset
    write(rows[:2])
    output = tmp_path / "alignment"
    calls = []
    summary = runner.run(
        images, output, references,
        workflow_factory=workflow_factory(rows, calls, rejected=(1,)),
    )
    assert summary["blocked_events"] == 0
    assert sum(kind == "approve" for kind, _ in calls) == 2
    failed = [row for row in read_scores(output) if row["card_no"] == "01"]
    assert len(failed) == 9
    assert {row["ocr_points"] for row in failed} == {"0"}
    assert "error.alignment_uncertain" in (output / "stages.jsonl").read_text()


@pytest.mark.parametrize("problem", ["missing", "duplicate", "path", "invalid_course", "invalid_time", "corrupt"])
def test_preflight_has_no_side_effects(dataset, tmp_path, problem):
    images, references, rows, write = dataset
    selected = [dict(rows[0])]
    if problem == "missing":
        (images / selected[0]["image_filename"]).unlink()
    elif problem == "duplicate":
        selected.append(dict(selected[0]))
    elif problem == "path":
        selected[0]["image_filename"] = "../outside.jpg"
    elif problem == "invalid_course":
        selected[0]["course"] = "guess"
    elif problem == "invalid_time":
        selected[0]["time"] = "unknown"
    else:
        (images / selected[0]["image_filename"]).write_bytes(b"not an image")
    write(selected)
    output = tmp_path / "never-created"

    @contextmanager
    def forbidden(*args):
        pytest.fail("preflight must run before workflow/model creation")
        yield

    with pytest.raises(ValueError):
        runner.run(images, output, references, workflow_factory=forbidden)
    assert not output.exists()


@pytest.mark.parametrize(("field", "expected", "detected", "correct"), [
    ("course", "100 m", "100", True),
    ("course", "100m", "0100 M", True),
    ("course", "100 m", "50", False),
    ("position", "Rücken", "ruecken", True),
    ("position", "Freistil", "Frei", True),
    ("position", "Freistil", "K", True),
    ("position", "Freistil", "Kraul", True),
    ("position", "Brust", "Brus", False),
    ("time", "1:34,92", "01:34.920", True),
    ("gender", "Mädchen", "female", True),
    ("year", "2012", "12", False),
    ("name", "Müller", " Müller  ", True),
    ("name", "Müller", "Muller", False),
])
def test_shared_scoring(field, expected, detected, correct):
    assert matches(field, expected, detected) is correct
    assert baseline._matches(field, expected, detected) is correct


def test_export_scoring_reads_csv_not_persisted_suggestions(dataset, tmp_path):
    images, references, rows, write = dataset
    write(rows[:1])
    factory = workflow_factory(rows, [])

    @contextmanager
    def altered_factory(data_dir, policy):
        with factory(data_dir, policy) as workflow:
            original = workflow.export
            original_detail = workflow.detail

            def altered(session_id):
                return original(session_id).replace("Müller".encode(), b"Different")

            def display_suggestion(card_id):
                detail = original_detail(card_id)
                if "name" in detail["fields"]:
                    detail["fields"]["name"]["value"] = "Display-only suggestion"
                return detail

            workflow.export = altered
            workflow.detail = display_suggestion
            yield workflow

    output = tmp_path / "csv-values"
    summary = runner.run(images, output, references, workflow_factory=altered_factory)
    assert summary["persisted_correct"] == 9
    assert summary["export_correct"] == 8
    name = next(row for row in read_scores(output) if row["field"] == "name")
    assert name["persisted_value"] == "Müller"
    assert name["exported_value"] == "Different"


def test_baseline_evaluator_also_has_144_observations(dataset, tmp_path, monkeypatch):
    images, references, rows, _ = dataset
    monkeypatch.setattr(baseline, "REFERENCE_FILE", references)
    monkeypatch.setattr(baseline, "PHOTO_DIRECTORY", images)
    monkeypatch.setattr(baseline, "DEHTRRecognizer", lambda: None)
    monkeypatch.setattr(baseline, "DEHTRLineRecognizer", lambda _: Recognizer(rows))
    monkeypatch.setattr(baseline, "TemplateCardAligner", Aligner)
    monkeypatch.setattr(baseline, "ConservativeCheckboxProposer", lambda: Marks(rows))
    results, _ = baseline.evaluate(tmp_path / "baseline.csv")
    assert len(results) == 144
    assert {row["field"] for row in results} == set(SCORED_FIELDS)
    assert "timekeeper" not in baseline.FIELDS


def test_raw_metadata_can_read_legacy_shared_evidence():
    policy = load_correction_policy()
    evidence = {"course_position": {"raw_transcription": "100 m R"}}
    assert runner.raw_metadata(evidence, "course", policy) == ("100 m R", "100")
    assert runner.raw_metadata(evidence, "position", policy) == ("100 m R", "Rücken")
    ambiguous = {"course_position": {"raw_transcription": "50 m 100 m Brust Rücken"}}
    assert runner.raw_metadata(ambiguous, "course", policy)[1] == ""
    assert runner.raw_metadata(ambiguous, "position", policy)[1] == ""


def test_real_composition_is_lazy_and_isolated(tmp_path):
    data = tmp_path / "isolated"
    with runner.production_workflow(data, load_correction_policy()) as workflow:
        assert isinstance(workflow, BrowserWorkflow)
        assert isinstance(workflow.repositories, SqliteRepositories)
        assert isinstance(workflow.images, ManagedImageStore)
        assert isinstance(workflow.use_cases.recognizer, LazyDEHTRLineRecognizer)
        assert isinstance(workflow.use_cases.aligner, TemplateCardAligner)
        assert isinstance(workflow.use_cases.checkbox_proposer, ConservativeCheckboxProposer)
        assert workflow.use_cases.recognizer._delegate is None
        assert workflow.images.directory == data / "images"
        assert workflow.repositories.list_sessions() == ()
    assert (data / "startkartenleser.sqlite3").is_file()


def test_capture_failure_never_exports_an_incomplete_event(dataset, tmp_path):
    images, references, rows, write = dataset
    selected = [rows[0], rows[14], rows[1]]
    write(selected)
    factory = workflow_factory(rows, [])

    @contextmanager
    def failing_capture(data_dir, policy):
        with factory(data_dir, policy) as workflow:
            original = workflow.capture
            count = 0

            def capture(payload):
                nonlocal count
                count += 1
                if count == 1:
                    raise BrowserError(415, "error.unsupported_image")
                return original(payload)

            workflow.capture = capture
            yield workflow

    output = tmp_path / "capture-failure"
    summary = runner.run(images, output, references, workflow_factory=failing_capture)
    assert summary["blocked_events"] == 1
    assert summary["observations"] == 27
    assert len(list((output / "exports").glob("*.csv"))) == 1
    event = next(event for event in summary["events"] if event["status"] == "blocked")
    assert event["error"] == "evaluation.capture_failed"
    scores = read_scores(output)
    assert {row["export_points"] for row in scores if row["card_no"] in {"01", "15"}} == {"0"}
    assert "error.unsupported_image" in (output / "stages.jsonl").read_text()
