"""Load a validated, local race-specific OCR correction policy."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from startkartenleser.domain.postprocessing import CorrectionPolicy, _match_text


DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[1] / "assets" / "recognition-policy.json"


def load_correction_policy(path: Path = DEFAULT_POLICY_PATH) -> CorrectionPolicy:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"positions", "max_edit_distance"}
    allowed = required | {"minimum_birth_year"}
    if not isinstance(data, dict) or not required <= set(data) <= allowed:
        raise ValueError(
            "correction policy requires positions and max_edit_distance; "
            "minimum_birth_year is optional"
        )
    positions = data["positions"]
    maximum = data["max_edit_distance"]
    minimum_birth_year = data.get("minimum_birth_year", 1927)
    if type(minimum_birth_year) is not int or not 1900 <= minimum_birth_year <= date.today().year:
        raise ValueError("minimum_birth_year must be an integer between 1900 and the current year")
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
