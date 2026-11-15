"""Conservative, locale-independent validation of numeric and time fields."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re


@dataclass(frozen=True)
class IntegerValidation:
    value: int | None
    error_key: str | None = None

    @property
    def valid(self) -> bool:
        return self.error_key is None


@dataclass(frozen=True)
class TimeParseResult:
    raw_text: str
    milliseconds: int | None
    error_key: str | None = None

    @property
    def valid(self) -> bool:
        return self.error_key is None


_UNSIGNED_INTEGER = re.compile(r"[0-9]+\Z")
_YEAR = re.compile(r"[0-9]{4}\Z")
_MINUTES_SECONDS = re.compile(
    r"(?P<minutes>[0-9]+):(?P<seconds>[0-9]{2})(?:[,.](?P<fraction>[0-9]{1,3}))?\Z"
)
_MINUTES_SECONDS_UNITS = re.compile(
    r"(?P<minutes>[0-9]{1,2})\s*min\s*(?P<seconds>[0-9]{1,2})"
    r"(?:\s*[,\.]\s*(?P<fraction>[0-9]{1,3})?)?\s*sek\Z",
    re.IGNORECASE,
)
_HOURS_MINUTES_SECONDS = re.compile(
    r"(?P<hours>[0-9]+):(?P<minutes>[0-9]{2}):(?P<seconds>[0-9]{2})"
    r"(?:[,.](?P<fraction>[0-9]{1,3}))?\Z"
)
_SECONDS_FRACTION = re.compile(r"(?P<seconds>[0-9]+)[,.](?P<fraction>[0-9]{1,3})\Z")
_SECONDS_FRACTION_UNITS = re.compile(
    r"(?P<seconds>[0-9]{1,2})(?:\s*[,\.]\s*(?P<fraction>[0-9]{1,3}))?\s*sek\Z",
    re.IGNORECASE,
)


def validate_positive_integer(raw: str | None) -> IntegerValidation:
    """Parse an optional positive integer without accepting signs or decimals."""
    if raw is None or not raw.strip():
        return IntegerValidation(None)
    value = raw.strip()
    if not _UNSIGNED_INTEGER.fullmatch(value):
        return IntegerValidation(None, "validation.positive_integer")
    parsed = int(value)
    if parsed < 1:
        return IntegerValidation(None, "validation.positive_integer")
    return IntegerValidation(parsed)


def validate_year(raw: str | None, *, current_year: int | None = None) -> IntegerValidation:
    """Accept only a four-digit year between 1900 and the current year."""
    if raw is None or not raw.strip():
        return IntegerValidation(None)
    value = raw.strip()
    if not _YEAR.fullmatch(value):
        return IntegerValidation(None, "validation.year")
    year = int(value)
    latest = date.today().year if current_year is None else current_year
    if year < 1900 or year > latest:
        return IntegerValidation(None, "validation.year")
    return IntegerValidation(year)


def parse_time_milliseconds(raw: str | None) -> TimeParseResult:
    """Parse explicit duration notation to milliseconds; leave ambiguous text raw.

    Supported forms are ``M:SS``, ``M:SS,ff``/``M:SS.fff``,
    the marked-card form ``M min SS,fff sek``,
    ``H:MM:SS[,fraction]``, and ``SS,fraction``. Fractions contain one to
    three decimal digits. A bare integer is intentionally not interpreted as
    a duration because its unit is ambiguous.
    """
    source = "" if raw is None else raw
    text = source.strip()
    if not text:
        return TimeParseResult(source, None)

    units_match = _MINUTES_SECONDS_UNITS.fullmatch(text)
    if units_match:
        minutes = int(units_match.group("minutes"))
        seconds = int(units_match.group("seconds"))
        fraction = units_match.group("fraction") or ""
        if seconds >= 60:
            return TimeParseResult(source, None, "validation.time_unrecognized")
        total_seconds = minutes * 60 + seconds
        return TimeParseResult(source, total_seconds * 1000 + _fraction_ms(fraction))

    seconds_units_match = _SECONDS_FRACTION_UNITS.fullmatch(text)
    if seconds_units_match:
        seconds = int(seconds_units_match.group("seconds"))
        fraction = seconds_units_match.group("fraction") or ""
        if seconds >= 60:
            return TimeParseResult(source, None, "validation.time_unrecognized")
        return TimeParseResult(source, seconds * 1000 + _fraction_ms(fraction))

    hours_match = _HOURS_MINUTES_SECONDS.fullmatch(text)
    if hours_match:
        hours = int(hours_match.group("hours"))
        minutes = int(hours_match.group("minutes"))
        seconds = int(hours_match.group("seconds"))
        fraction = hours_match.group("fraction") or ""
        if minutes >= 60 or seconds >= 60:
            return TimeParseResult(source, None, "validation.time_unrecognized")
        total_seconds = hours * 3600 + minutes * 60 + seconds
        return TimeParseResult(source, total_seconds * 1000 + _fraction_ms(fraction))

    minutes_match = _MINUTES_SECONDS.fullmatch(text)
    if minutes_match:
        minutes = int(minutes_match.group("minutes"))
        seconds = int(minutes_match.group("seconds"))
        fraction = minutes_match.group("fraction") or ""
        if seconds >= 60:
            return TimeParseResult(source, None, "validation.time_unrecognized")
        total_seconds = minutes * 60 + seconds
        return TimeParseResult(source, total_seconds * 1000 + _fraction_ms(fraction))

    seconds_match = _SECONDS_FRACTION.fullmatch(text)
    if seconds_match:
        seconds = int(seconds_match.group("seconds"))
        fraction = seconds_match.group("fraction")
        return TimeParseResult(source, seconds * 1000 + _fraction_ms(fraction))

    return TimeParseResult(source, None, "validation.time_unrecognized")


def _fraction_ms(fraction: str) -> int:
    return int(fraction.ljust(3, "0")) if fraction else 0
