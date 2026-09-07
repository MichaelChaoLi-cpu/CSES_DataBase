"""Illness-type category equivalence must not erase family, branch or codebook gaps."""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cses_db"))
from review_cses_health_illness_type import (  # noqa: E402
    decode,
    eligibility,
    parse_options,
    type_evidence,
    type_population,
)

ROOT = Path(__file__).resolve().parents[2]
SPEC = json.loads((ROOT / "rsc/specs/cses_health_illness_type_v1.json").read_text())
RULES = SPEC["waves"]
CORE = dict(enumerate(SPEC["core18_labels"], 1))
NINETEEN = {**CORE, 19: "Other diseases"}
FIVE = {1: "Fever", 2: "Cough", 3: "Diarrhea", 4: "Flu", 5: "Other (specify)"}


@pytest.mark.parametrize("text", ["01 = Fever\n02 = Cough", "01 = Fever   02 = Cough", "  01=Fever\n 02=Cough  "])
def test_numbered_option_parser_preserves_labels(text):
    assert parse_options(text) == {1: "Fever", 2: "Cough"}


@pytest.mark.parametrize("text", ["no numbered list", "1 = first 1 = second"])
def test_bad_lists_fail(text):
    with pytest.raises(ValueError):
        parse_options(text)


def test_same_number_changes_meaning_between_families():
    _, old, _ = decode(pd.Series([3, 5]), RULES["2013"], FIVE, {}, SPEC)
    _, new, _ = decode(pd.Series([3, 5, 9]), RULES["2016"], NINETEEN, {}, SPEC)
    assert old.tolist() == ["diarrhoea", "other_in_five_option_list"]
    assert new.tolist() == ["diabetes_reported", "tuberculosis_reported", "diarrhoea"]


def test_2019_code19_is_not_other_and_no_extension_is_forced_into_core():
    label, category, state = decode(
        pd.Series([19, 20, 72]), RULES["2019"], {}, {19: "Fever/Cold", 20: "Brain tumor", 72: "Others"}, SPEC
    )
    assert label.tolist() == ["Fever/Cold", "Brain tumor", "Others"]
    assert category.isna().all()
    assert state.eq("native_label_only").all()


def test_2021_form_only19_and_extensions_are_not_harmonized():
    label, category, state = decode(pd.Series([1, 18, 19, 20, 73]), RULES["2021"], NINETEEN, CORE, SPEC)
    assert category.iloc[:2].tolist() == ["respiratory", "chikungunya_reported"]
    assert category.iloc[2:].isna().all()
    assert label.iloc[2] == "Other diseases"
    assert label.iloc[3:].isna().all()
    assert state.iloc[2:].tolist() == ["form_only_residual_unverified", "unresolved_code", "unresolved_code"]


def test_2004_missing_is_not_an_illness_category_or_zero():
    label, category, state = decode(pd.Series([1, 99, None]), RULES["2004"], {1: "STOMACH ACHE"}, {99: "missing"}, SPEC)
    assert category.iloc[0] == "early_28day_01"
    assert category.iloc[1:].isna().all()
    assert label.iloc[1:].isna().all()
    assert state.iloc[1:].tolist() == ["explicit_missing_code", "source_null"]


@pytest.mark.parametrize("wave", ["2007", "2017"])
def test_unverified_codes_do_not_inherit_other_wave_dictionary(wave):
    label, category, state = decode(pd.Series([1, 3, 19]), RULES[wave], NINETEEN, CORE, SPEC)
    assert label.isna().all() and category.isna().all()
    assert state.eq("unverified_semantics").all()


def test_2007_slots_and_2009_absence_are_not_single_choice_zero():
    assert len(RULES["2007"]["fields"]) == 5
    assert RULES["2009"]["fields"] == []
    _, category, state = decode(pd.Series([None, None]), RULES["2009"], {}, {}, SPEC)
    assert category.isna().all()
    assert state.eq("not_collected_in_reviewed_section").all()


def test_unknown_codes_are_not_defaulted_to_other():
    _, category, state = decode(pd.Series([0, 98, 99, 3.5]), RULES["2016"], NINETEEN, {}, SPEC)
    assert category.isna().all()
    assert state.eq("unresolved_code").all()


def test_injury_skip_and_unknown_conditional_blank_are_distinct():
    screen = pd.DataFrame({"raw_screen_code": [1, 2, 3]})
    assert type_population(screen, "2021").tolist() == [
        "illness_branch",
        "not_applicable_injury",
        "not_applicable_no_problem",
    ]
    assert type_population(screen, "2016").iloc[0] == "illness_or_injury_conditional"
    assert type_population(screen, "2017").eq("screen_missing_or_unverified").all()


@pytest.mark.parametrize("wave", ["2013", "2016", "2021"])
def test_analysis_filters_preserve_screening_and_category_requirements(wave):
    f = pd.DataFrame(
        {
            "strict_screening_eligible": [True, False, True, True, True],
            "raw_screen_code": [1, 1, 2, 1, 1],
            "raw_type_code": [3, 3, 3, 20, 19],
            "category": ["a", "a", "a", None, "other"],
            "category_status": ["nineteen_category_form_supported"] * 3
            + ["unresolved_code", "nineteen_category_form_supported"],
        }
    )
    within, core = eligibility(f, wave)
    assert within.tolist() == [True, False, False, False, True]
    assert core.tolist() == ([True, False, False, False, False] if wave != "2013" else [False] * 5)


def test_spec_does_not_publish_and_keeps_one_concept_eighteen_labels():
    assert not SPEC["database_publication_authorized"]
    assert len(set(SPEC["core18_categories"])) == len(SPEC["core18_labels"]) == 18
    assert len(SPEC["five_categories"]) == 5
    assert len(SPEC["screening_manifest_sha256"]) == 64


def test_real_local_option_cells_are_complete_and_support_selected_domains():
    previous = ROOT / "data/processing/cses/health_recent_illness_v1/wave_review.json"
    if not previous.exists():
        pytest.skip("DVC processed questionnaire library absent")
    prior = {r["survey_wave"]: r for r in json.loads(previous.read_text())}
    for wave, expected in [("2004", 41), ("2013", 5), ("2016", 19), ("2021", 19)]:
        proof, options = type_evidence(ROOT, prior[wave], RULES[wave], SPEC)
        assert len(options) == expected
        assert proof["form"]["survey_wave"] == wave
