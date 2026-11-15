"""Conservative OCR suggestions constrained by an explicit race policy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
import re
import unicodedata

from .contracts import RecognitionCandidate
from .validation import parse_time_milliseconds, validate_year


POSTPROCESSING_VERSION = "postprocessing-v5-illegal-character-filter"


@dataclass(frozen=True)
class CorrectionPolicy:
    positions: tuple[tuple[str, tuple[str, ...]], ...]
    max_edit_distance: int = 1
    minimum_birth_year: int = 1927


def _match_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value).casefold().strip()
    return value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")


def edit_distance(left: str, right: str) -> int:
    """Return Levenshtein distance without third-party dependencies."""
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, 1):
        current = [row]
        for column, right_char in enumerate(right, 1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def _correct_position(raw: str, policy: CorrectionPolicy) -> str:
    query = _match_text(raw)
    if not query:
        return raw
    exact = {
        canonical
        for canonical, aliases in policy.positions
        if query in {_match_text(value) for value in (canonical, *aliases)}
    }
    if len(exact) == 1:
        return exact.pop()
    if exact or len(query) < 3 or len(query) > 80:
        return raw
    distances = {
        canonical: min(
            edit_distance(query, _match_text(value))
            for value in (canonical, *aliases)
            if len(_match_text(value)) >= 3
        )
        for canonical, aliases in policy.positions
    }
    if not distances:
        return raw
    nearest = min(distances.values())
    winners = [value for value, distance in distances.items() if distance == nearest]
    if nearest <= policy.max_edit_distance and len(winners) == 1:
        return winners[0]
    return raw


def _correct_course(raw: str) -> str:
    match = re.fullmatch(r"([0-9]+)\s*[mM]?", raw.strip())
    if match is None:
        return raw
    meters = match.group(1).lstrip("0")
    return f"{meters} m" if meters else raw


def _correct_time(raw: str) -> str:
    text = re.sub(r"\s*([:,.])\s*", r"\1", raw.strip())
    parsed = parse_time_milliseconds(text)
    if not parsed.valid or parsed.milliseconds is None:
        return raw
    minutes, remainder = divmod(parsed.milliseconds, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    fraction = f"{milliseconds:03d}"
    if fraction.endswith("0"):
        fraction = fraction[:2]
    return f"{minutes}:{seconds:02d},{fraction}"


def _correct_year(raw: str, current_year: int, minimum_birth_year: int) -> str:
    # Year values are digits only; remove OCR punctuation before validation.
    text = re.sub(r"[^0-9'’]", "", raw).strip()
    short_year = re.fullmatch(r"(?P<prefix>['’1])(?P<year>[0-9]{2})", text)
    if short_year:
        year = current_year // 100 * 100 + int(short_year.group("year"))
        if year > current_year:
            year -= 100
        if year < minimum_birth_year:
            return raw
        # A leading OCR "1" may be an apostrophe, but must identify only one century.
        if short_year.group("prefix") == "1" and year - 100 >= minimum_birth_year:
            return raw
        text = str(year)
    parsed = validate_year(text, current_year=current_year)
    return str(parsed.value) if parsed.valid and parsed.value is not None else raw


def _correct_name(raw: str) -> str:
    """Remove OCR punctuation while preserving letters, marks, spaces and name joins."""
    kept = []
    for character in unicodedata.normalize("NFC", raw):
        category = unicodedata.category(character)
        if category.startswith(("L", "M")) or character.isspace() or character in "-'’":
            kept.append(character)
    return re.sub(r"\s+", " ", "".join(kept)).strip()


def correct_candidate(
    candidate: RecognitionCandidate,
    policy: CorrectionPolicy,
    *,
    current_year: int | None = None,
) -> RecognitionCandidate:
    raw = candidate.raw_transcription if candidate.raw_transcription is not None else candidate.text
    corrected = candidate.text
    if candidate.field_key == "position":
        corrected = _correct_position(raw, policy)
    elif candidate.field_key == "course":
        corrected = _correct_course(raw)
    elif candidate.field_key == "time":
        corrected = _correct_time(raw)
    elif candidate.field_key == "year":
        corrected = _correct_year(
            raw,
            date.today().year if current_year is None else current_year,
            policy.minimum_birth_year,
        )
    elif candidate.field_key in ("name", "first_name"):
        cleaned = _correct_name(raw)
        if cleaned:
            corrected = cleaned
    return replace(candidate, text=corrected, raw_transcription=raw)
