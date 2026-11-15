"""Shared, reference-only scoring rules (never used to change card values)."""

from __future__ import annotations

import re
import unicodedata

from startkartenleser.domain.postprocessing import CorrectionPolicy
from startkartenleser.domain.validation import parse_time_milliseconds
from startkartenleser.infrastructure.correction_policy import load_correction_policy


SCORED_FIELDS = (
    "name", "first_name", "year", "gender", "course", "position",
    "heat", "lane", "time",
)


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def normalize_stroke(value: str, policy: CorrectionPolicy) -> str:
    def key(text: str) -> str:
        return normalize_text(text).replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")

    query = key(value)
    for canonical, aliases in policy.positions:
        if query in {key(item) for item in (canonical, *aliases)}:
            return key(canonical)
    return query


def matches(
    field: str, expected: str, detected: str, policy: CorrectionPolicy | None = None,
) -> bool:
    if not detected.strip():
        return False
    if field == "time":
        left, right = parse_time_milliseconds(expected), parse_time_milliseconds(detected)
        return left.valid and right.valid and left.milliseconds == right.milliseconds
    if field == "course":
        def meters(value: str) -> int | None:
            match = re.fullmatch(r"\s*([0-9]+)\s*m?\s*", value, re.IGNORECASE)
            return int(match[1]) if match else None
        left, right = meters(expected), meters(detected)
        return left is not None and left == right
    if field == "position":
        policy = policy or load_correction_policy()
        return normalize_stroke(expected, policy) == normalize_stroke(detected, policy)
    if field == "gender":
        aliases = {"mädchen": "female", "junge": "male"}
        left, right = normalize_text(expected), normalize_text(detected)
        return aliases.get(left, left) == aliases.get(right, right)
    return normalize_text(expected) == normalize_text(detected)
