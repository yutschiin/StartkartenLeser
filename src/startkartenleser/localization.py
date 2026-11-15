"""Keyed locale catalog loading and safe named-message formatting."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import json
import string
from typing import Any


class CatalogError(ValueError):
    """Raised when a locale catalog is missing or malformed."""


class MissingTranslationError(CatalogError, KeyError):
    """Raised instead of exposing an untranslated key to a user."""


class _DuplicateKeyError(ValueError):
    pass


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate catalog key: {key}")
        result[key] = value
    return result


def _placeholders(message: str) -> frozenset[str]:
    try:
        return frozenset(
            name
            for _, name, _, _ in string.Formatter().parse(message)
            if name is not None
        )
    except ValueError as error:
        raise CatalogError(f"invalid format string: {message!r}") from error


def _message_values(value: Any, key: str) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, dict):
        if set(value) != {"one", "other"} or not all(
            isinstance(item, str) for item in value.values()
        ):
            raise CatalogError(
                f"plural entry {key!r} must contain string forms 'one' and 'other'"
            )
        return value["one"], value["other"]
    raise CatalogError(f"catalog entry {key!r} must be a string or plural object")


@dataclass(frozen=True)
class TextCatalog:
    """Resolve stable string keys from one locale catalog.

    Locale selection may fall back to the configured default catalog. Individual
    missing keys never fall back and always raise ``MissingTranslationError``.
    """

    messages: Mapping[str, str | Mapping[str, str]]
    locale: str = "de"

    @classmethod
    def load(
        cls,
        locale: str | None = None,
        *,
        directory: Path | str | None = None,
        default_locale: str = "de",
    ) -> "TextCatalog":
        catalog_dir = Path(directory) if directory is not None else Path(__file__).parent / "locales"
        selected_locale = locale or default_locale
        selected_path = catalog_dir / f"{selected_locale}.json"
        if not selected_path.is_file() and selected_locale != default_locale:
            selected_locale = default_locale
            selected_path = catalog_dir / f"{selected_locale}.json"
        if not selected_path.is_file():
            raise CatalogError(f"locale catalog not found: {selected_path}")
        try:
            with selected_path.open(encoding="utf-8") as stream:
                data = json.load(stream, object_pairs_hook=_object_without_duplicates)
        except (OSError, json.JSONDecodeError, _DuplicateKeyError) as error:
            raise CatalogError(f"cannot load locale catalog {selected_path}: {error}") from error
        if not isinstance(data, dict) or not all(isinstance(key, str) for key in data):
            raise CatalogError(f"locale catalog must be a JSON object: {selected_path}")
        for key, value in data.items():
            for message in _message_values(value, key):
                _placeholders(message)
        return cls(data, selected_locale)

    def text(self, key: str, **parameters: object) -> str:
        """Return a translated message, supporting named fields and one/other plurals."""
        if key not in self.messages:
            raise MissingTranslationError(f"missing translation for {key!r} ({self.locale})")
        entry = self.messages[key]
        if isinstance(entry, Mapping):
            if "count" not in parameters:
                raise CatalogError(f"plural translation {key!r} requires a named 'count'")
            form = "one" if parameters["count"] == 1 else "other"
            message = entry[form]
        else:
            message = entry

        expected = _placeholders(message)
        supplied = frozenset(parameters)
        if expected != supplied:
            missing = sorted(expected - supplied)
            extra = sorted(supplied - expected)
            raise CatalogError(
                f"parameters for {key!r} do not match placeholders "
                f"(missing={missing}, extra={extra})"
            )
        try:
            return message.format(**parameters)
        except (KeyError, ValueError, TypeError) as error:
            raise CatalogError(f"cannot format translation {key!r}: {error}") from error


def validate_compatible_catalogs(
    catalogs: Mapping[str, Mapping[str, str | Mapping[str, str]]]
) -> None:
    """Require matching keys, plural categories, and placeholders across locales."""
    if not catalogs:
        raise CatalogError("at least one locale catalog is required")
    iterator = iter(catalogs.items())
    reference_locale, reference = next(iterator)
    reference_keys = set(reference)
    for locale, messages in iterator:
        if set(messages) != reference_keys:
            missing = sorted(reference_keys - set(messages))
            extra = sorted(set(messages) - reference_keys)
            raise CatalogError(
                f"catalog {locale!r} key mismatch against {reference_locale!r}: "
                f"missing={missing}, extra={extra}"
            )
        for key in sorted(reference_keys):
            reference_entry = reference[key]
            current_entry = messages[key]
            if isinstance(reference_entry, Mapping) != isinstance(current_entry, Mapping):
                raise CatalogError(f"catalog entry {key!r} changes plural structure in {locale!r}")
            reference_forms = _message_values(reference_entry, key)
            current_forms = _message_values(current_entry, key)
            if len(reference_forms) != len(current_forms):
                raise CatalogError(f"catalog entry {key!r} changes plural forms in {locale!r}")
            for base, current in zip(reference_forms, current_forms, strict=True):
                if _placeholders(base) != _placeholders(current):
                    raise CatalogError(f"catalog entry {key!r} placeholder mismatch in {locale!r}")


def load_catalogs(directory: Path | str | None = None) -> dict[str, dict[str, str | Mapping[str, str]]]:
    """Load every ``*.json`` catalog in a locale directory."""
    catalog_dir = Path(directory) if directory is not None else Path(__file__).parent / "locales"
    catalogs: dict[str, dict[str, str | Mapping[str, str]]] = {}
    for path in sorted(catalog_dir.glob("*.json")):
        catalog = TextCatalog.load(path.stem, directory=catalog_dir)
        catalogs[path.stem] = dict(catalog.messages)
    return catalogs
