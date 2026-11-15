"""Evaluate file → Wettkampf → recognition → unchanged approval → CSV, in isolation."""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime, timezone
import csv
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from uuid import uuid4

from startkartenleser.application.use_cases import StartkartenUseCases, UseCaseError
from startkartenleser.browser_workflow import (
    BrowserError, BrowserWorkflow, MAX_IMAGE_BYTES, STROKES, _course_reading,
)
from startkartenleser.domain.postprocessing import POSTPROCESSING_VERSION
from startkartenleser.domain.schema import CROP_VERSION, MODEL_VERSION, SCHEMA_VERSION
from startkartenleser.domain.validation import (
    parse_time_milliseconds, validate_positive_integer, validate_year,
)
from startkartenleser.evaluation import SCORED_FIELDS, matches, normalize_stroke
from startkartenleser.infrastructure.correction_policy import DEFAULT_CONFIG_PATH, load_correction_policy
from startkartenleser.infrastructure.image_pipeline import ImageInputError, load_selected_image
from startkartenleser.infrastructure.image_store import ManagedImageStore
from startkartenleser.infrastructure.paths import AppDataPaths
from startkartenleser.infrastructure.recognizer import MODEL_SHA256, CONFIG_SHA256
from startkartenleser.infrastructure.sqlite_repositories import SqliteRepositories
from startkartenleser.infrastructure.workflow_adapters import (
    ConservativeCheckboxProposer, LazyDEHTRLineRecognizer, TemplateCardAligner,
)
from startkartenleser.localization import TextCatalog


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_FILE = ROOT / "tests/reference_data.csv"
METADATA_FIELDS = {"course", "position", "gender"}
REQUIRED_CARD_FIELDS = ("name", "first_name", "year", "heat", "lane", "time")
EXPORT_FIELDS = {
    "name": "name", "first_name": "first_name", "year": "year_text",
    "heat": "heat_text", "lane": "lane_text", "time": "time_text",
    "course": "course", "position": "position",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_default(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (datetime, Path)):
        return str(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def write_json(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=json_default)
        stream.write("\n")


def git_metadata() -> tuple[str | None, bool | None]:
    """Return revision/dirty state when run in Git; source archives have none."""
    try:
        revision = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        status = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None, None
    return revision.stdout.strip() or None, bool(status.stdout.strip())


def event_key(reference: dict, policy) -> tuple[int, str, str]:
    course = re.fullmatch(r"\s*([0-9]+)\s*m?\s*", reference["course"], re.IGNORECASE)
    if course is None or not 1 <= int(course[1]) <= 2_147_483_647:
        raise ValueError(f"invalid reference course: {reference['course']!r}")
    stroke = normalize_stroke(reference["position"], policy)
    gender = {"Mädchen": "female", "Junge": "male"}.get(reference["gender"])
    if stroke not in STROKES or gender is None:
        raise ValueError(f"invalid reference stroke/gender on card {reference['card_no']}")
    return int(course[1]), stroke, gender


def preflight(images_dir: Path, output_dir: Path, references: Path, policy) -> list[dict]:
    """Validate the entire fixed mapping before creating data or loading the model."""
    if output_dir.exists():
        raise FileExistsError(f"refusing existing run directory: {output_dir}")
    if not images_dir.is_dir():
        raise NotADirectoryError(images_dir)
    if output_dir.resolve().is_relative_to(images_dir.resolve()):
        raise ValueError("output directory must be outside the photo directory")
    with references.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"card_no", "image_filename", *SCORED_FIELDS}
        if not required <= set(reader.fieldnames or ()):
            raise ValueError(f"missing reference columns: {sorted(required - set(reader.fieldnames or ()))}")
        rows = list(reader)
    if not rows:
        raise ValueError("reference dataset is empty")
    for key in ("card_no", "image_filename"):
        values = [row[key] for row in rows]
        if any(not value or not value.strip() for value in values) or len(set(values)) != len(rows):
            raise ValueError(f"reference {key} values must be nonempty and unique")
    for row in rows:
        if None in row or any(row[field] is None or not row[field].strip() for field in required):
            raise ValueError(f"incomplete reference row: {row.get('card_no')}")
        filename = row["image_filename"]
        if Path(filename).name != filename or "\\" in filename or filename in {".", ".."}:
            raise ValueError(f"photo filename must be a basename: {filename!r}")
        photo = images_dir / filename
        if not photo.is_file() or not photo.resolve().is_relative_to(images_dir.resolve()):
            raise ValueError(f"missing photo or external symlink: {photo}")
        if photo.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError(f"photo exceeds capture limit ({MAX_IMAGE_BYTES} bytes): {photo}")
        # Production intake validates format, dimensions, corruption and decompression limits.
        loaded = load_selected_image(photo)
        loaded.image.close()
        loaded.preview.close()
        event_key(row, policy)
        for field, validator in (
            ("year", validate_year), ("heat", validate_positive_integer),
            ("lane", validate_positive_integer), ("time", parse_time_milliseconds),
        ):
            if not validator(row[field]).valid:
                raise ValueError(f"invalid reference {field} on card {row['card_no']}")
    return sorted(rows, key=lambda row: (event_key(row, policy), row["card_no"]))


@contextmanager
def production_workflow(data_dir: Path, policy):
    paths = AppDataPaths(data_dir)
    paths.ensure()
    recognizer = LazyDEHTRLineRecognizer()
    images = ManagedImageStore(paths.images)
    repositories = SqliteRepositories(paths.database, images)
    try:
        use_cases = StartkartenUseCases(
            repositories, repositories, images, TemplateCardAligner(), recognizer,
            ConservativeCheckboxProposer(), retention=repositories, correction_policy=policy,
        )
        yield BrowserWorkflow(repositories, images, use_cases, TextCatalog.load())
    finally:
        repositories.close()
        recognizer.close()


def gender_value(marks: dict) -> str:
    if marks.get("female") == "checked" and marks.get("male") == "unchecked":
        return "female"
    if marks.get("male") == "checked" and marks.get("female") == "unchecked":
        return "male"
    return ""


def raw_metadata(evidence: dict, field: str, policy) -> tuple[str, str]:
    if field == "gender":
        marks = evidence.get("gender") or {}
        return json.dumps(marks, sort_keys=True), gender_value(marks)
    candidate = evidence.get(field) or evidence.get("course_position") or {}
    raw = candidate.get("raw_transcription") or ""
    if field == "course":
        reading, ambiguous = _course_reading(raw)
    else:
        # Accept policy aliases, not fuzzy spelling repairs, in the raw OCR score.
        reading, ambiguous = BrowserWorkflow._position_reading(raw, replace(policy, max_edit_distance=0))
    return raw, "" if ambiguous or reading is None else reading


def score_card(reference: dict, detail: dict, evidence: dict, exported: dict | None, policy) -> list[dict]:
    fields = detail.get("fields", {})
    marks = {key: value["state"] for key, value in detail.get("checkboxes", {}).items()}
    results = []
    for field in SCORED_FIELDS:
        persisted = (
            gender_value(marks) if field == "gender"
            else str(fields.get(field, {}).get("value") or "")
        )
        raw, ocr = (
            raw_metadata(evidence, field, policy) if field in METADATA_FIELDS
            else (fields.get(field, {}).get("raw_transcription") or "",) * 2
        )
        export_value = ""
        if exported is not None:
            export_value = (
                gender_value({"female": exported["female_mark"], "male": exported["male_mark"]})
                if field == "gender" else exported[EXPORT_FIELDS[field]]
            )
        results.append({
            "card_no": reference["card_no"], "image_filename": reference["image_filename"],
            "card_id": detail.get("id", ""), "field": field, "expected": reference[field],
            "card_state": detail.get("state", "capture_failed"),
            "persisted_value": persisted,
            "persisted_points": 100 if matches(field, reference[field], persisted, policy) else 0,
            "final_origin": "event_reference" if field in METADATA_FIELDS else "ocr_candidate",
            "exported_value": export_value,
            "export_points": 100 if exported is not None and matches(field, reference[field], export_value, policy) else 0,
            "export_origin": (
                "card_marks" if field == "gender" else "card_field"
            ),
            "export_status": "exported" if exported is not None else "blocked",
            "raw_ocr": raw, "ocr_comparison_value": ocr,
            "ocr_points": 100 if matches(field, reference[field], ocr, policy) else 0,
            "ocr_origin": "reference_evidence" if field in METADATA_FIELDS else "raw_transcription",
        })
    return results


def approval_blockers(detail: dict) -> dict:
    blockers = dict(detail.get("validation", {}))
    for field in REQUIRED_CARD_FIELDS:
        if not str(detail.get("fields", {}).get(field, {}).get("value") or "").strip():
            blockers[field] = "evaluation.missing_required_field"
    recognition = detail.get("recognition", {})
    if recognition.get("status") not in {"completed", "partial"}:
        blockers["recognition"] = recognition.get("error_key") or recognition.get("status", "missing")
    return blockers


def run(
    images_dir: Path, output_dir: Path, references: Path = REFERENCE_FILE,
    *, workflow_factory=production_workflow,
) -> dict:
    images_dir, output_dir, references = images_dir.resolve(), output_dir.resolve(), references.resolve()
    policy = load_correction_policy()
    rows = preflight(images_dir, output_dir, references, policy)
    output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    exports_dir, evidence_dir = output_dir / "exports", output_dir / "evidence"
    exports_dir.mkdir()
    evidence_dir.mkdir()
    shutil.copyfile(references, output_dir / "references.csv")
    shutil.copyfile(DEFAULT_CONFIG_PATH, output_dir / "config.json")
    photo_hashes = {row["card_no"]: digest(images_dir / row["image_filename"]) for row in rows}
    git_revision, git_dirty = git_metadata()
    write_json(output_dir / "run.json", {
        "started_utc": datetime.now(timezone.utc), "images_dir": images_dir,
        "references": references, "references_sha256": digest(references),
        "policy_sha256": digest(DEFAULT_CONFIG_PATH),
        "git_revision": git_revision, "git_dirty": git_dirty,
        "runner_sha256": digest(Path(__file__)), "python": platform.python_version(),
        "packages": {name: version(name) for name in (
            "Pillow", "numpy", "opencv-python-headless", "onnxruntime",
        )},
        "source_sha256": {
            str(path.relative_to(ROOT)): digest(path)
            for path in sorted((ROOT / "src/startkartenleser").rglob("*.py"))
        },
        "schema_version": SCHEMA_VERSION, "crop_version": CROP_VERSION,
        "model_version": MODEL_VERSION, "postprocessing_version": POSTPROCESSING_VERSION,
        "expected_model_sha256": MODEL_SHA256, "expected_config_sha256": CONFIG_SHA256,
        "cards": [{**row, "sha256": photo_hashes[row["card_no"]]} for row in rows],
        "scored_fields": SCORED_FIELDS, "workflow_factory": workflow_factory.__name__,
    })
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault(event_key(row, policy), []).append(row)
    scores, events = [], []
    with (output_dir / "stages.jsonl").open("x", encoding="utf-8") as journal:
        def record(stage: str, **data) -> None:
            journal.write(json.dumps(
                {"stage": stage, **data}, ensure_ascii=False, default=json_default,
            ) + "\n")
            journal.flush()

        with workflow_factory(output_dir / "data", policy) as workflow:
            for number, ((distance, stroke, gender), group) in enumerate(groups.items(), 1):
                event = workflow.create_session({
                    "number": number, "distance_m": distance, "stroke": stroke, "gender": gender,
                })
                record("create", response=event)
                cards = []
                capture_failed = False
                for reference in group:
                    card_id = None
                    try:
                        source = images_dir / reference["image_filename"]
                        data = source.read_bytes()
                        if hashlib.sha256(data).hexdigest() != photo_hashes[reference["card_no"]]:
                            raise ValueError(f"photo changed after preflight: {source}")
                        mime = "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"
                        captured = workflow.capture({
                            "session_id": event["id"], "request_id": str(uuid4()),
                            "image": f"data:{mime};base64," + base64.b64encode(data).decode("ascii"),
                        })
                        card_id = captured["id"]
                        record("capture", card_no=reference["card_no"], response=captured)
                        recognized = workflow.recognize(card_id, {"revision": captured["revision"]})
                        record("recognize", card_no=reference["card_no"], response=recognized)
                        blockers = approval_blockers(recognized)
                        if blockers:
                            record("validation_warning", card_no=reference["card_no"], blockers=blockers)
                        approved = workflow.approve(card_id, {"revision": recognized["revision"]})
                        record("approve", card_no=reference["card_no"], response=approved)
                    except (BrowserError, UseCaseError, ImageInputError) as error:
                        capture_failed = capture_failed or card_id is None
                        record("card_error", card_no=reference["card_no"], error=str(error),
                               error_type=type(error).__name__, status=getattr(error, "status", None))
                    detail = workflow.detail(card_id) if card_id else {}
                    if card_id:
                        # detail() exposes policy suggestions; score actual storage instead.
                        detail["fields"] = {
                            key: asdict(value)
                            for key, value in workflow.repositories.get_field_values(card_id).items()
                        }
                    evidence = workflow.repositories.get_reference_evidence(card_id) if card_id else None
                    write_json(evidence_dir / f"card-{reference['card_no'].encode().hex()}.json", {
                        "reference": reference, "persisted": detail, "reference_evidence": evidence,
                    })
                    cards.append((reference, detail, evidence or {}))
                exported_rows = {}
                event_result = {"number": number, "session_id": event["id"], "cards": len(group)}
                try:
                    # A failed import must not allow a misleading partial event export.
                    if capture_failed:
                        event_result.update(status="blocked", error="evaluation.capture_failed")
                    else:
                        content = workflow.export(event["id"])
                        filename = workflow.export_filename(event["id"])
                        with (exports_dir / filename).open("xb") as stream:
                            stream.write(content)
                        # Score bytes read back from the actual application CSV, not suggestions.
                        with (exports_dir / filename).open(encoding="utf-8-sig", newline="") as stream:
                            exported_rows = {row["card_id"]: row for row in csv.DictReader(stream, delimiter=";")}
                        if set(exported_rows) != {detail["id"] for _, detail, _ in cards}:
                            raise ValueError("exported card mapping differs from captured cards")
                        event_result.update(status="exported", filename=filename)
                except BrowserError as error:
                    event_result.update(status="blocked", error=error.key, http_status=error.status)
                record("export", **event_result)
                events.append(event_result)
                for reference, detail, evidence in cards:
                    scores.extend(score_card(
                        reference, detail, evidence, exported_rows.get(detail.get("id")), policy,
                    ))
    with (output_dir / "field-scores.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(scores[0]))
        writer.writeheader()
        writer.writerows(scores)
    summary = {
        "finished_utc": datetime.now(timezone.utc), "cards": len(rows),
        "observations": len(scores), "events": events,
        "blocked_events": sum(event["status"] == "blocked" for event in events),
        **{
            f"{metric}_correct": sum(row[f"{metric}_points"] == 100 for row in scores)
            for metric in ("persisted", "export", "ocr")
        },
        "fields": {
            field: {
                f"{metric}_correct": sum(row[f"{metric}_points"] == 100 for row in scores if row["field"] == field)
                for metric in ("persisted", "export", "ocr")
            } for field in SCORED_FIELDS
        },
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="new, nonexistent run directory")
    parser.add_argument("--references", type=Path, default=REFERENCE_FILE)
    args = parser.parse_args()
    try:
        summary = run(args.images_dir, args.output_dir, args.references)
    except (OSError, ValueError, UseCaseError) as error:
        print(f"Evaluation failed: {error}", file=sys.stderr)
        return 1
    print(f"{summary['cards']} cards, {summary['observations']} observations; "
          f"{summary['blocked_events']}/{len(summary['events'])} events blocked.")
    for metric in ("persisted", "export", "ocr"):
        print(f"{metric}: {summary[f'{metric}_correct']}/{summary['observations']} correct")
    for event in summary["events"]:
        if event["status"] == "blocked":
            print(f"Blocked event {event['number']}: {event['error']}")
    print("Persisted/export metadata is event-supplied, not OCR accuracy; see field-scores.csv.")
    print(f"Results: {args.output_dir.resolve()}")
    return 2 if summary["blocked_events"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
