"""Load a validated, local race-specific OCR correction policy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re

from startkartenleser.domain.postprocessing import CorrectionPolicy, _match_text


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "assets" / "config.json"


@dataclass(frozen=True)
class StrokeOption:
    value: str
    label: str
    synonyms: tuple[str, ...] = ()


@dataclass(frozen=True)
class AppConfiguration:
    strokes: tuple[StrokeOption, ...]
    correction_policy: CorrectionPolicy


DEFAULT_STROKE_OPTIONS = (
    StrokeOption("freistil", "Freistil", ("F", "Frei", "K", "Kraul")),
    StrokeOption("brust", "Brust", ("B",)),
    StrokeOption("ruecken", "Rücken", ("R", "Ruecken")),
    StrokeOption("schmetterling", "Schmetterling", ("S", "D", "Delphin")),
    StrokeOption("lagen", "Lagen"),
    StrokeOption("flossenschwimmen_mit_brett", "Flossenschwimmen mit Brett", ("Fl + Brett", "Fl+B")),
    StrokeOption(
        "freistil_mit_flossen", "Freistil mit Flossen",
        ("F + Fl", "Freistil + Flossen", "F + Flossen"),
    ),
)


def _validated_policy(
    positions: object, maximum: object, minimum_birth_year: object,
) -> CorrectionPolicy:
    if (
        type(minimum_birth_year) is not int
        or not 1900 <= minimum_birth_year <= date.today().year
    ):
        raise ValueError(
            "minimum_birth_year must be an integer between 1900 and the current year"
        )
    if type(maximum) is not int or not 0 <= maximum <= 2:
        raise ValueError("max_edit_distance must be an integer between 0 and 2")
    if not isinstance(positions, dict) or not positions:
        raise ValueError("positions must be a non-empty object")
    seen: dict[str, str] = {}
    entries: list[tuple[str, tuple[str, ...]]] = []
    for canonical, aliases in positions.items():
        if not isinstance(canonical, str) or not 3 <= len(canonical.strip()) <= 80:
            raise ValueError("position names must contain 3 to 80 characters")
        if not isinstance(aliases, list) or not all(
            isinstance(alias, str) and 1 <= len(alias.strip()) <= 80 for alias in aliases
        ):
            raise ValueError(f"aliases for {canonical!r} must be non-empty strings")
        for value in (canonical, *aliases):
            key = _match_text(value)
            if key in seen and seen[key] != canonical:
                raise ValueError(f"ambiguous position alias: {value!r}")
            seen[key] = canonical
        entries.append((canonical, tuple(aliases)))
    return CorrectionPolicy(tuple(entries), maximum, minimum_birth_year)


def _load_combined(data: object) -> AppConfiguration:
    required = {"strokes", "recognition_policy"}
    if not isinstance(data, dict) or set(data) != required:
        raise ValueError("configuration requires exactly strokes and recognition_policy")
    raw_strokes = data["strokes"]
    if not isinstance(raw_strokes, list) or not 1 <= len(raw_strokes) <= 50:
        raise ValueError("strokes must be a non-empty list of at most 50 entries")
    options: list[StrokeOption] = []
    ids: set[str] = set()
    normalized_labels: set[str] = set()
    labels: dict[str, list[str]] = {}
    for entry in raw_strokes:
        if not isinstance(entry, dict) or set(entry) != {"value", "label", "synonyms"}:
            raise ValueError("each stroke requires value, label, and synonyms")
        value, label, synonyms = entry["value"], entry["label"], entry["synonyms"]
        if not isinstance(value, str) or re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", value) is None:
            raise ValueError("stroke values must be lowercase identifiers (a-z, 0-9, _ or -)")
        if value in ids:
            raise ValueError(f"duplicate stroke value: {value!r}")
        if not isinstance(label, str) or not 3 <= len(label.strip()) <= 80:
            raise ValueError("stroke labels must contain 3 to 80 characters")
        normalized_label = _match_text(label)
        if normalized_label in normalized_labels:
            raise ValueError(f"duplicate stroke label: {label!r}")
        if not isinstance(synonyms, list) or not all(
            isinstance(alias, str) and 1 <= len(alias.strip()) <= 80 for alias in synonyms
        ):
            raise ValueError(f"synonyms for {label!r} must be a list of non-empty strings")
        if any(
            ord(char) < 32 or ord(char) == 127
            for text in (label, *synonyms) for char in text
        ):
            raise ValueError("stroke labels and synonyms cannot contain control characters")
        ids.add(value)
        normalized_labels.add(normalized_label)
        options.append(
            StrokeOption(value, label.strip(), tuple(alias.strip() for alias in synonyms))
        )
        labels[label.strip()] = list(synonyms)

    recognition = data["recognition_policy"]
    if not isinstance(recognition, dict) or not {"max_edit_distance"} <= set(recognition) <= {
        "max_edit_distance", "minimum_birth_year",
    }:
        raise ValueError(
            "recognition_policy requires max_edit_distance; minimum_birth_year is optional"
        )
    policy = _validated_policy(
        labels,
        recognition["max_edit_distance"],
        recognition.get("minimum_birth_year", 1927),
    )
    return AppConfiguration(tuple(options), policy)


def load_app_configuration(path: Path = DEFAULT_CONFIG_PATH) -> AppConfiguration:
    """Load configured dropdown Lagen and the OCR correction policy together."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and set(data) != {"strokes", "recognition_policy"}:
        # Preserve user overrides created with the former standalone policy format.
        return AppConfiguration(DEFAULT_STROKE_OPTIONS, load_correction_policy(path))
    return _load_combined(data)


def load_correction_policy(path: Path = DEFAULT_CONFIG_PATH) -> CorrectionPolicy:
    """Load the correction policy; also supports the former standalone policy format."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and set(data) == {"strokes", "recognition_policy"}:
        return _load_combined(data).correction_policy
    required = {"positions", "max_edit_distance"}
    allowed = required | {"minimum_birth_year"}
    if not isinstance(data, dict) or not required <= set(data) <= allowed:
        raise ValueError("legacy correction policy requires positions and max_edit_distance")
    return _validated_policy(
        data["positions"], data["max_edit_distance"], data.get("minimum_birth_year", 1927),
    )
