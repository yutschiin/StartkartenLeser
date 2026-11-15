from datetime import datetime, timezone

from startkartenleser.domain.contracts import (
    AlignmentQuality,
    AlignmentResult,
    Card,
    CardState,
    CheckboxState,
    CheckboxValue,
    FieldProvenance,
    FieldReviewStatus,
    FieldValue,
    RecognitionCandidate,
    RecognitionOutcome,
    RecognitionRequest,
    RecognitionStatus,
    Session,
    SharedTextCandidate,
    VersionInfo,
)
from startkartenleser.domain.schema import (
    CROP_VERSION,
    A6_RECOGNITION_REGIONS,
    A6_FORM_RECOGNITION_REGIONS,
    FIELDS,
    RECOGNITION_REGIONS,
    SCHEMA_VERSION,
    FieldKind,
    CARD_LAYOUT_A6_V1,
    CARD_LAYOUT_A6_V4,
    recognition_regions_for_layout,
)


def test_domain_contracts_keep_persisted_identifiers_language_neutral() -> None:
    assert [field.key for field in FIELDS] == [
        "name",
        "first_name",
        "year",
        "female",
        "male",
        "wk_number",
        "course",
        "position",
        "heat",
        "lane",
        "time",
        "timekeeper",
    ]
    assert all(field.label_key.startswith("field.") for field in FIELDS)
    assert [field.kind for field in FIELDS].count(FieldKind.CHECKBOX) == 2
    assert RECOGNITION_REGIONS == (
        "name",
        "first_name",
        "year",
        "course_position",
        "heat",
        "lane",
        "time",
        "timekeeper",
    )
    assert {field.region_key for field in FIELDS if field.region_key} <= set(RECOGNITION_REGIONS) | {
        "checkbox_female",
        "checkbox_male",
        "wk_number",
        "course",
        "position",
    }
    assert A6_RECOGNITION_REGIONS == (
        "name",
        "first_name",
        "year",
        "course",
        "position",
        "heat",
        "lane",
        "time_minutes",
        "time_seconds",
        "time_fraction",
        "timekeeper",
    )
    assert recognition_regions_for_layout(CARD_LAYOUT_A6_V1) == A6_RECOGNITION_REGIONS
    assert recognition_regions_for_layout(CARD_LAYOUT_A6_V4) == A6_FORM_RECOGNITION_REGIONS
    assert SCHEMA_VERSION and CROP_VERSION


def test_contract_values_represent_workflow_and_independent_checkbox_states() -> None:
    now = datetime.now(timezone.utc)
    session = Session("session-1", "Sitzung", now)
    card = Card("card-1", session.id, 1, CardState.CAPTURED, "image-1", SCHEMA_VERSION)
    value = FieldValue(
        "name", "Ada", FieldProvenance.USER_EDITED, FieldReviewStatus.CONFIRMED,
        raw_transcription="Ado", confirmed=True,
    )
    female = CheckboxValue("female", CheckboxState.CHECKED, FieldProvenance.MANUAL)
    male = CheckboxValue("male", CheckboxState.UNKNOWN)
    alignment = AlignmentResult(AlignmentQuality.NEEDS_MANUAL_ADJUSTMENT)
    request = RecognitionRequest(card.id, SCHEMA_VERSION, "de-htr-v2", 0, ("name",))
    outcome = RecognitionOutcome(
        RecognitionStatus.PARTIAL,
        candidates=(RecognitionCandidate("name", "Ado"),),
        shared_candidates=(SharedTextCandidate("course_position", "Freistil"),),
        checkbox_proposals=(female, male),
        model_version=request.model_version,
        schema_version=request.schema_version,
    )
    versions = VersionInfo(SCHEMA_VERSION, CROP_VERSION, "de-htr-v2")

    assert card.state is CardState.CAPTURED
    assert value.provenance is FieldProvenance.USER_EDITED
    assert female.state is CheckboxState.CHECKED
    assert male.state is CheckboxState.UNKNOWN
    assert alignment.quality is AlignmentQuality.NEEDS_MANUAL_ADJUSTMENT
    assert outcome.status is RecognitionStatus.PARTIAL
    assert outcome.shared_candidates[0].raw_text == "Freistil"
    assert versions.model_version == "de-htr-v2"
