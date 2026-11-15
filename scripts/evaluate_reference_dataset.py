"""Score the local image-recognition pipeline against the fixed photo references."""

from __future__ import annotations

import argparse
import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import sys

from startkartenleser.domain.contracts import AlignmentQuality, CheckboxState
from startkartenleser.domain.contracts import RecognitionCandidate
from startkartenleser.domain.postprocessing import POSTPROCESSING_VERSION, correct_candidate
from startkartenleser.infrastructure.correction_policy import DEFAULT_CONFIG_PATH, load_correction_policy
from startkartenleser.domain.schema import CROP_VERSION, MODEL_VERSION, SCHEMA_VERSION
from startkartenleser.evaluation import SCORED_FIELDS, matches as _matches
from startkartenleser.infrastructure.image_pipeline import load_selected_image
from startkartenleser.infrastructure.recognizer import DEHTRRecognizer
from startkartenleser.infrastructure.workflow_adapters import (
    ConservativeCheckboxProposer,
    DEHTRLineRecognizer,
    TemplateCardAligner,
)


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_FILE = ROOT / "tests" / "reference_data.csv"
PHOTO_DIRECTORY = ROOT / "tests" / "testfotos"
FIELDS = SCORED_FIELDS
RESULT_COLUMNS = (
    "card_no",
    "image_filename",
    "field",
    "expected",
    "detected",
    "raw_detected",
    "points",
    "status",
    "detail",
    "alignment_quality",
    "layout_version",
    "schema_version",
    "crop_version",
    "model_version",
    "postprocessing_version",
    "policy_sha256",
)
EXPECTED_CARDS = 16


def _read_references() -> list[dict[str, str]]:
    with REFERENCE_FILE.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {
        "card_no",
        "name",
        "first_name",
        "year",
        "gender",
        "course",
        "position",
        "heat",
        "lane",
        "time",
        "timekeeper",
        "image_filename",
    }
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"{REFERENCE_FILE} is missing required reference columns")
    if len(rows) != EXPECTED_CARDS:
        raise ValueError(f"expected {EXPECTED_CARDS} reference rows, found {len(rows)}")
    card_numbers = [row["card_no"] for row in rows]
    filenames = [row["image_filename"] for row in rows]
    if len(set(card_numbers)) != len(rows) or len(set(filenames)) != len(rows):
        raise ValueError("reference card numbers and photo filenames must be unique")
    for filename in filenames:
        if Path(filename).name != filename:
            raise ValueError(f"photo filename must not contain a directory: {filename!r}")
        if not (PHOTO_DIRECTORY / filename).is_file():
            raise FileNotFoundError(PHOTO_DIRECTORY / filename)
    if any(row["gender"] not in {"Mädchen", "Junge"} for row in rows):
        raise ValueError("gender values must be 'Mädchen' or 'Junge'")
    return rows


def _write_field_result(
    results: list[dict[str, str]],
    reference: dict[str, str],
    field: str,
    detected: str,
    status: str,
    detail: str,
    alignment_quality: str,
    layout_version: str,
    raw_detected: str = "",
    policy_sha256: str = "",
) -> None:
    expected = reference[field]
    if field == "gender":
        correct = status == "correct_marks"
    else:
        correct = bool(detected) and _matches(field, expected, detected)
    results.append(
        {
            "card_no": reference["card_no"],
            "image_filename": reference["image_filename"],
            "field": field,
            "expected": expected,
            "detected": detected,
            "raw_detected": raw_detected,
            "points": "100" if correct else "0",
            "status": status if correct else ("incorrect" if detected else status),
            "detail": detail,
            "alignment_quality": alignment_quality,
            "layout_version": layout_version,
            "schema_version": SCHEMA_VERSION,
            "crop_version": CROP_VERSION,
            "model_version": MODEL_VERSION,
            "postprocessing_version": POSTPROCESSING_VERSION,
            "policy_sha256": policy_sha256,
        }
    )


def evaluate(output: Path, policy_path: Path = DEFAULT_CONFIG_PATH) -> tuple[list[dict[str, str]], datetime]:
    references = _read_references()
    policy = load_correction_policy(policy_path)
    policy_digest = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    recognizer = DEHTRRecognizer()
    line_recognizer = DEHTRLineRecognizer(recognizer)
    aligner = TemplateCardAligner()
    checkbox_proposer = ConservativeCheckboxProposer()
    results: list[dict[str, str]] = []
    run_at = datetime.now(timezone.utc)
    try:
        for reference in references:
            image_path = PHOTO_DIRECTORY / reference["image_filename"]
            loaded = load_selected_image(image_path)
            attempt = aligner.align(loaded.image)
            quality = attempt.result.quality.value
            layout = attempt.result.schema_version
            if attempt.result.quality is not AlignmentQuality.ACCEPTED:
                reason = attempt.result.reason_key or quality
                for field in FIELDS:
                    _write_field_result(
                        results, reference, field, "", "alignment_failed", reason,
                        quality, layout, policy_sha256=policy_digest,
                    )
                continue

            recognized: dict[str, str] = {}
            statuses: dict[str, str] = {}
            for region, crop in attempt.text_crops.items():
                result = line_recognizer.recognize(region, crop)
                if result.candidate is not None and result.candidate.text.strip():
                    recognized[region] = result.candidate.text.strip()
                    statuses[region] = "detected"
                else:
                    statuses[region] = result.error_key or result.status.value

            for field in FIELDS:
                detected = recognized.get(field, "")
                status = statuses.get(field, "blank_crop" if field in attempt.skipped_text_regions else "missing_crop")
                detail = ""
                if field == "time" and layout == "card-layout-a6-v1":
                    seconds = recognized.get("time_seconds", "")
                    minute_region = "time_minutes"
                    fraction_region = "time_fraction"
                    time_regions = (minute_region, "time_seconds", fraction_region)
                    complete = all(
                        region in recognized or region in attempt.skipped_text_regions
                        for region in time_regions
                    )
                    if complete and seconds:
                        fraction = recognized.get(fraction_region, "")
                        seconds_text = f"{seconds},{fraction}" if fraction else seconds
                        minutes = recognized.get(minute_region, "")
                        detected = (
                            f"{minutes} min {seconds_text} sek"
                            if minutes
                            else f"{seconds_text} sek"
                        )
                        status = "detected"
                    else:
                        status = "incomplete_time"
                        detail = "; ".join(
                            f"{region}={statuses.get(region, 'blank_crop' if region in attempt.skipped_text_regions else 'missing_crop')}"
                            for region in time_regions
                        )
                elif field == "gender":
                    female = checkbox_proposer.propose(
                        "female", attempt.checkbox_crops["checkbox_female"]
                    ).state
                    male = checkbox_proposer.propose(
                        "male", attempt.checkbox_crops["checkbox_male"]
                    ).state
                    detected = f"female={female.value};male={male.value}"
                    expected_female = reference["gender"] == "Mädchen"
                    expected_pair = (
                        CheckboxState.CHECKED if expected_female else CheckboxState.UNCHECKED,
                        CheckboxState.UNCHECKED if expected_female else CheckboxState.CHECKED,
                    )
                    status = (
                        "correct_marks"
                        if (female, male) == expected_pair
                        else "unknown_marks"
                        if CheckboxState.UNKNOWN in (female, male)
                        else "wrong_marks"
                    )
                    detail = f"female={female.value};male={male.value}"
                raw_detected = detected
                if field != "gender" and detected:
                    corrected = correct_candidate(RecognitionCandidate(field, detected), policy)
                    detected = corrected.text
                    if detected != raw_detected:
                        detail = f"{detail}; postprocessed".strip("; ")
                _write_field_result(
                    results, reference, field, detected, status, detail, quality, layout,
                    raw_detected, policy_digest,
                )
    finally:
        line_recognizer.recognizer.close()

    if len(results) != EXPECTED_CARDS * len(FIELDS):
        raise RuntimeError(f"expected {EXPECTED_CARDS * len(FIELDS)} scored fields, got {len(results)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing result file: {output}")
    with output.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(results)
    return results, run_at


def _print_summary(results: list[dict[str, str]], run_at: datetime, output: Path) -> None:
    print(f"Run UTC: {run_at.isoformat(timespec='seconds')}")
    print(f"Result CSV: {output}")
    print(f"Scored field observations: {len(results)}")
    print("Field scores:")
    correct_total = 0
    for field in FIELDS:
        field_results = [row for row in results if row["field"] == field]
        correct = sum(row["points"] == "100" for row in field_results)
        correct_total += correct
        score = 100 * correct / len(field_results)
        print(f"  {field}: {correct}/{len(field_results)} correct — {score:.2f}/100")
    overall = 100 * correct_total / len(results)
    aligned = sum(row["alignment_quality"] == AlignmentQuality.ACCEPTED.value for row in results)
    print(f"Run score: {correct_total}/{len(results)} correct field observations — {overall:.2f}/100")
    print(f"Accepted alignment: {aligned // len(FIELDS)}/{EXPECTED_CARDS} cards")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/results/ocr-baseline.csv"),
        help="new CSV path for the per-card-field scores (existing files are never overwritten)",
    )
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    try:
        results, run_at = evaluate(output, args.config)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Benchmark failed: {error}", file=sys.stderr)
        return 1
    _print_summary(results, run_at, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
