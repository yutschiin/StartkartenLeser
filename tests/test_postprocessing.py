from dataclasses import replace
import json

import pytest

from startkartenleser.domain.contracts import RecognitionCandidate
from startkartenleser.domain.postprocessing import CorrectionPolicy, correct_candidate, edit_distance
from startkartenleser.infrastructure.correction_policy import (
    DEFAULT_CONFIG_PATH,
    load_app_configuration,
    load_correction_policy,
)


@pytest.mark.parametrize(("raw", "expected"), [
    ("F", "Freistil"), ("Frei", "Freistil"), ("R", "Rücken"),
    ("K", "Freistil"), ("Kraul", "Freistil"), ("kraul", "Freistil"),
    ("Ruecken", "Rücken"), ("B", "Brust"), ("S", "Schmetterling"),
    ("D", "Schmetterling"), ("Delphin", "Schmetterling"),
    ("Rücken.", "Rücken"), ("Freistill", "Freistil"),
    ("unknown", "unknown"), ("7", "7"), ("", ""), ("f", "Freistil"),
])
def test_position_aliases_and_bounded_matching_preserve_raw(raw, expected):
    result = correct_candidate(RecognitionCandidate("position", raw), load_correction_policy())
    assert result.text == expected
    assert result.raw_transcription == raw
    assert result.confidence is None


def test_tied_nearest_positions_are_not_guessed():
    policy = CorrectionPolicy((("Brust", ()), ("Brast", ())))
    assert correct_candidate(RecognitionCandidate("position", "Brest"), policy).text == "Brest"


def test_position_policy_can_disable_aliases_and_fuzzy_matching():
    policy = replace(load_correction_policy(), positions=(("Freistil", ()),), max_edit_distance=0)
    assert correct_candidate(RecognitionCandidate("position", "R"), policy).text == "R"
    assert correct_candidate(RecognitionCandidate("position", "Freistill"), policy).text == "Freistill"


def test_configuration_rejects_ambiguous_aliases_and_unknown_keys(tmp_path):
    data = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    next(stroke for stroke in data["strokes"] if stroke["value"] == "brust")["synonyms"].append("R")
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="ambiguous"):
        load_app_configuration(path)
    data["typo"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_app_configuration(path)


def test_configured_strokes_and_synonyms_are_loaded_for_the_recognition_policy(tmp_path):
    data = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    data["strokes"].append({
        "value": "butterfly", "label": "Butterfly", "synonyms": ["Delfin"],
    })
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    config = load_app_configuration(path)
    assert config.strokes[-1].value == "butterfly"
    assert config.strokes[-1].label == "Butterfly"
    assert correct_candidate(
        RecognitionCandidate("position", "Delfin"), config.correction_policy,
    ).text == "Butterfly"


@pytest.mark.parametrize(("raw", "expected"), [
    ("Fl + Brett", "Flossenschwimmen mit Brett"),
    ("Fl+B", "Flossenschwimmen mit Brett"),
    ("F + Fl", "Freistil mit Flossen"),
    ("Freistil + Flossen", "Freistil mit Flossen"),
    ("F + Flossen", "Freistil mit Flossen"),
])
def test_default_config_recognizes_new_fin_swimming_synonyms(raw, expected):
    result = correct_candidate(RecognitionCandidate("position", raw), load_correction_policy())
    assert result.text == expected


def test_previous_standalone_policy_files_keep_default_dropdown_options(tmp_path):
    path = tmp_path / "recognition-policy.json"
    path.write_text(json.dumps({
        "positions": {"Kraul": ["K"]},
        "max_edit_distance": 0,
        "minimum_birth_year": 1927,
    }), encoding="utf-8")

    config = load_app_configuration(path)
    assert [option.value for option in config.strokes] == [
        "freistil", "brust", "ruecken", "schmetterling", "lagen",
        "flossenschwimmen_mit_brett", "freistil_mit_flossen",
    ]
    assert correct_candidate(
        RecognitionCandidate("position", "K"), config.correction_policy,
    ).text == "Kraul"


def test_distance_computes_substitutions_insertions_and_deletions():
    assert edit_distance("brust", "brest") == 1
    assert edit_distance("", "R") == 1
    assert edit_distance("Freistil", "Freistill") == 1


def test_unrelated_fields_are_not_fuzzy_corrected():
    result = correct_candidate(RecognitionCandidate("name", "Frei"), load_correction_policy())
    assert result.text == "Frei"


@pytest.mark.parametrize(("raw", "expected"), [
    ("50", "50 m"), ("50m", "50 m"), ("50 m", "50 m"),
    (" 100 M ", "100 m"), ("025m", "25 m"), ("1500", "1500 m"),
    ("75", "75 m"), ("0", "0"), ("000 m", "000 m"),
    ("-50", "-50"), ("50.5", "50.5"), ("50,5m", "50,5m"),
    ("5 0m", "5 0m"), ("50km", "50km"), ("10Dm", "10Dm"),
    ("unknown", "unknown"), ("", ""),
])
def test_distance_suggestions_normalize_optional_meter_unit(raw, expected):
    policy = load_correction_policy()
    result = correct_candidate(RecognitionCandidate("course", raw), policy)
    assert result.text == expected
    assert result.raw_transcription == raw
    assert correct_candidate(result, policy) == result


@pytest.mark.parametrize(("raw", "expected"), [
    ("42, 18", "0:42,18"), ("1 : 34.92", "1:34,92"),
    ("1 min 34,92 sek", "1:34,92"), ("42 sek", "0:42,00"),
    ("1:02:03.456", "62:03,456"), ("94,920", "1:34,92"),
    ("0:00,005", "0:00,005"), ("1:34", "1:34,00"),
    ("42", "42"), ("1:99,12", "1:99,12"), ("unknown", "unknown"), ("", ""),
])
def test_time_suggestions_are_canonical_without_guessing(raw, expected):
    result = correct_candidate(RecognitionCandidate("time", raw), load_correction_policy())
    assert result.text == expected
    assert result.raw_transcription == raw
    assert correct_candidate(result, load_correction_policy()) == result


@pytest.mark.parametrize(("raw", "expected"), [
    ("'02", "2002"), ("'85", "1985"), ("’26", "2026"), ("'27", "1927"),
    (" 2012 ", "2012"), ("02", "02"), ("'2", "'2"), ("1899", "1899"),
    ("2027", "2027"), ("unknown", "unknown"), ("", ""),
])
def test_year_suggestions_use_latest_nonfuture_four_digit_year(raw, expected):
    result = correct_candidate(
        RecognitionCandidate("year", raw), load_correction_policy(), current_year=2026
    )
    assert result.text == expected
    assert result.raw_transcription == raw


@pytest.mark.parametrize(("raw", "expected"), [
    ("111", "2011"), ("110", "2010"), ("114", "2014"), ("185", "1985"),
    ("127", "1927"), ("126", "2026"), (" 102 ", "2002"),
    ("211", "211"), ("11", "11"), ("1", "1"), ("1111", "1111"),
    ("1O2", "1O2"), ("'26", "2026"),
])
def test_year_ocr_apostrophe_read_as_one_is_corrected_only_with_unique_year(raw, expected):
    policy = load_correction_policy()
    result = correct_candidate(RecognitionCandidate("year", raw), policy, current_year=2026)
    assert result.text == expected
    assert result.raw_transcription == raw
    assert correct_candidate(result, policy, current_year=2026) == result


def test_year_ocr_correction_respects_configured_range_and_rejects_century_ties():
    policy = replace(load_correction_policy(), minimum_birth_year=1900)
    for raw in ("111", "102", "126"):
        assert correct_candidate(
            RecognitionCandidate("year", raw), policy, current_year=2026
        ).text == raw
    assert correct_candidate(
        RecognitionCandidate("year", "'11"), policy, current_year=2026
    ).text == "2011"
    policy = replace(policy, minimum_birth_year=2000)
    for raw in ("185", "'85"):
        assert correct_candidate(
            RecognitionCandidate("year", raw), policy, current_year=2026
        ).text == raw
    assert correct_candidate(
        RecognitionCandidate("year", "127"), load_correction_policy(), current_year=2027
    ).text == "127"


def test_legacy_policy_without_birth_year_setting_remains_supported(tmp_path):
    data = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    data["recognition_policy"].pop("minimum_birth_year", None)
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_correction_policy(path).minimum_birth_year == 1927


@pytest.mark.parametrize("minimum", [True, "1927", None, 1899, 10000])
def test_policy_rejects_invalid_minimum_birth_year(tmp_path, minimum):
    data = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    data["recognition_policy"]["minimum_birth_year"] = minimum
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="minimum_birth_year"):
        load_correction_policy(path)
