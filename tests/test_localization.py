from __future__ import annotations

import json

import pytest

from startkartenleser.localization import (
    CatalogError,
    MissingTranslationError,
    TextCatalog,
    load_catalogs,
    validate_compatible_catalogs,
)


def test_german_catalog_is_the_default_and_interpolates_named_parameters() -> None:
    catalog = TextCatalog.load()

    assert catalog.locale == "de"
    assert catalog.text("accessibility.review_status", status="Geprüft") == (
        "Prüfstatus: Geprüft"
    )


def test_unknown_locale_uses_german_default_catalog(tmp_path) -> None:
    (tmp_path / "de.json").write_text(json.dumps({"app.title": "Deutsch"}), encoding="utf-8")

    catalog = TextCatalog.load("fr", directory=tmp_path)

    assert catalog.locale == "de"
    assert catalog.text("app.title") == "Deutsch"


def test_missing_key_raises_instead_of_showing_raw_key() -> None:
    catalog = TextCatalog.load()

    with pytest.raises(MissingTranslationError):
        catalog.text("not.a.real.key")


@pytest.mark.parametrize(
    ("count", "expected"),
    [(1, "1 Karte"), (0, "0 Karten"), (2, "2 Karten")],
)
def test_plural_forms_require_and_use_count(count: int, expected: str) -> None:
    catalog = TextCatalog.load()

    assert catalog.text("session.card_count", count=count) == expected


def test_plural_message_requires_count() -> None:
    catalog = TextCatalog.load()

    with pytest.raises(CatalogError, match="requires.*count"):
        catalog.text("session.card_count")


def test_named_parameters_must_match_exactly() -> None:
    catalog = TextCatalog.load()

    with pytest.raises(CatalogError, match="parameters"):
        catalog.text("accessibility.field_value", field="Name")


def test_all_catalogs_are_compatible() -> None:
    validate_compatible_catalogs(load_catalogs())


def test_catalog_completeness_and_schema_labels() -> None:
    catalog = TextCatalog.load()
    from startkartenleser.domain.contracts import CardState
    from startkartenleser.domain.schema import (
        CARD_STATE_LABEL_KEYS,
        CHECKBOX_REGION_FIELDS,
        FIELDS,
        REGION_LABEL_KEYS,
        SHARED_TEXT_REGIONS,
    )

    referenced_keys = {field.label_key for field in FIELDS}
    referenced_keys.update(SHARED_TEXT_REGIONS.values())
    referenced_keys.update(REGION_LABEL_KEYS.values())
    referenced_keys.update(CARD_STATE_LABEL_KEYS.values())
    assert set(CARD_STATE_LABEL_KEYS) == set(CardState)
    assert set(CHECKBOX_REGION_FIELDS.values()) == {"female", "male"}
    assert referenced_keys <= set(catalog.messages)


def test_current_domain_and_adapter_error_keys_are_localized() -> None:
    catalog = TextCatalog.load()
    required_keys = {
        "error.image_unreadable",
        "error.image_too_large",
        "error.unsupported_image",
        "error.image_copy_failed",
        "error.model_unavailable",
        "error.recognition_failed",
        "error.recognition_empty",
        "error.recognition_cancelled",
        "error.alignment_uncertain",
        "error.alignment_orientation_uncertain",
        "error.session_not_found",
        "error.card_not_found",
        "error.card_changed",
        "error.card_transition_invalid",
        "error.delete_failed",
        "screen.image_preview.title",
        "session.generated_title",
        "session.row",
        "image.filename",
        "status.closing",
        "action.back",
        "action.delete_session",
        "action.delete_card",
        "action.open_card",
        "label.shared_candidate",
        "checkbox.unknown",
        "checkbox.checked",
        "checkbox.unchecked",
        "screen.review.overlay_legend",
        "screen.review.no_overlay",
    }

    assert required_keys <= set(catalog.messages)


def test_duplicate_json_keys_are_rejected(tmp_path) -> None:
    (tmp_path / "de.json").write_text(
        '{"app.title":"one","app.title":"two"}', encoding="utf-8"
    )

    with pytest.raises(CatalogError, match="duplicate catalog key"):
        TextCatalog.load(directory=tmp_path)


def test_compatibility_rejects_placeholder_mismatch() -> None:
    catalogs = {
        "de": {"message": "Hallo {name}"},
        "en": {"message": "Hello {person}"},
    }

    with pytest.raises(CatalogError, match="placeholder mismatch"):
        validate_compatible_catalogs(catalogs)
