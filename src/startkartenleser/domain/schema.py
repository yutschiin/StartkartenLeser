"""Versioned Startkarte fields, independent of display-language wording."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .contracts import CardState


SCHEMA_VERSION = "startkarte-v1"
CROP_VERSION = "startkarte-crops-v7"
MODEL_VERSION = "de-htr-v2.0.0"

CARD_LAYOUT_V1 = "card-layout-v1"
CARD_LAYOUT_V2 = "card-layout-v2"
CARD_LAYOUT_A6_V1 = "card-layout-a6-v1"
CARD_LAYOUT_A6_V2 = "card-layout-a6-v2"
CARD_LAYOUT_A6_V3 = "card-layout-a6-v3"
CARD_LAYOUT_A6_V4 = "card-layout-a6-v4"


class FieldKind(StrEnum):
    TEXT = "text"
    INTEGER = "integer"
    TIME = "time"
    CHECKBOX = "checkbox"


@dataclass(frozen=True)
class FieldDefinition:
    key: str
    label_key: str
    kind: FieldKind
    region_key: str | None = None


FIELDS = (
    FieldDefinition("name", "field.name", FieldKind.TEXT, "name"),
    FieldDefinition("first_name", "field.first_name", FieldKind.TEXT, "first_name"),
    FieldDefinition("year", "field.year", FieldKind.INTEGER, "year"),
    FieldDefinition("female", "field.female", FieldKind.CHECKBOX, "checkbox_female"),
    FieldDefinition("male", "field.male", FieldKind.CHECKBOX, "checkbox_male"),
    FieldDefinition("wk_number", "field.wk_number", FieldKind.INTEGER, "wk_number"),
    FieldDefinition("course", "field.course", FieldKind.TEXT, "course"),
    FieldDefinition("position", "field.position", FieldKind.TEXT, "position"),
    FieldDefinition("heat", "field.heat", FieldKind.INTEGER, "heat"),
    FieldDefinition("lane", "field.lane", FieldKind.INTEGER, "lane"),
    FieldDefinition("time", "field.time", FieldKind.TIME, "time"),
    FieldDefinition("timekeeper", "field.timekeeper", FieldKind.TEXT, "timekeeper"),
)

SHARED_TEXT_REGIONS = {
    "course_position": "field.shared_course_position",
}

RECOGNITION_REGIONS = (
    "name",
    "first_name",
    "year",
    "course_position",
    "heat",
    "lane",
    "time",
    "timekeeper",
)
A6_RECOGNITION_REGIONS = (
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
A6_TIME_CROP_REGIONS = ("time_minutes", "time_seconds", "time_fraction")
A6_LINE_RECOGNITION_REGIONS = (
    "name",
    "first_name",
    "year",
    "course",
    "position",
    "heat",
    "lane",
    "time",
    "timekeeper",
)
A6_FORM_RECOGNITION_REGIONS = (
    "name",
    "first_name",
    "year",
    "course",
    "position",
    "wk_number",
    "heat",
    "lane",
    "time",
    "timekeeper",
)
CHECKBOX_REGIONS = ("checkbox_female", "checkbox_male")
CHECKBOX_REGION_FIELDS = {
    "checkbox_female": "female",
    "checkbox_male": "male",
}
REGION_LABEL_KEYS = {
    "name": "field.name",
    "first_name": "field.first_name",
    "year": "field.year",
    "course_position": "field.shared_course_position",
    "course": "field.course",
    "position": "field.position",
    "wk_number": "field.wk_number",
    "time_minutes": "field.time_minutes",
    "time_seconds": "field.time_seconds",
    "time_fraction": "field.time_fraction",
    "heat": "field.heat",
    "lane": "field.lane",
    "time": "field.time",
    "timekeeper": "field.timekeeper",
    "checkbox_female": "field.female",
    "checkbox_male": "field.male",
}


def recognition_regions_for_layout(layout_version: str) -> tuple[str, ...]:
    """Return the text crops expected for a recognized print layout."""
    if layout_version == CARD_LAYOUT_A6_V1:
        return A6_RECOGNITION_REGIONS
    if layout_version == CARD_LAYOUT_A6_V4:
        return A6_FORM_RECOGNITION_REGIONS
    if layout_version in (CARD_LAYOUT_A6_V2, CARD_LAYOUT_A6_V3):
        return A6_LINE_RECOGNITION_REGIONS
    if layout_version in (CARD_LAYOUT_V1, CARD_LAYOUT_V2):
        return RECOGNITION_REGIONS
    raise ValueError(f"unsupported card layout version: {layout_version}")

CARD_STATE_LABEL_KEYS = {
    CardState.CAPTURED: "status.captured",
    CardState.ALIGNING: "status.aligning",
    CardState.RECOGNIZING: "status.recognizing",
    CardState.NEEDS_REVIEW: "status.needs_review",
    CardState.REVIEWED: "status.reviewed",
}
