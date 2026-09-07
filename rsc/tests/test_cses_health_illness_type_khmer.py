"""Direct Khmer options recover three codes without guessing the remaining dictionary."""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cses_db"))
from recover_cses_2021_illness_dictionary import extract_tail, recover  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SPEC = json.loads((ROOT / "rsc/specs/cses_health_illness_type_khmer_v2.json").read_text())


def test_literal_khmer_tail_and_embedded_covid_numerals():
    text = "18 = Chikungunya " + "  ".join(f"{k}= {v['khmer']}" for k, v in SPEC["mapping"].items())
    assert extract_tail(text) == {k: v["khmer"] for k, v in SPEC["mapping"].items()}


@pytest.mark.parametrize("bad", ["19 = Other diseases", "19=a 20=b", "19=a 19=b 20=c 21=d"])
def test_missing_or_duplicate_tail_fails(bad):
    with pytest.raises(ValueError):
        extract_tail(bad)


def make_frame():
    return pd.DataFrame(
        {
            "survey_wave": ["2021"] * 7 + ["2019"],
            "raw_type_code": [18, 19, 20, 21, 22, 73, 21, 19],
            "raw_screen_code": [1, 1, 1, 1, 1, 1, 2, 1],
            "category": pd.Series(["old"] * 8, dtype="string"),
            "category_status": pd.Series(["old"] * 8, dtype="string"),
            "source_interpreted_label": pd.Series(["old"] * 8, dtype="string"),
            "type_alignment_status": pd.Series(["old"] * 8, dtype="string"),
            "type_needs_code_review": [True] * 8,
            "strict_screening_eligible": [True] * 6 + [False, False],
            "within_wave_analysis_eligible": [True] + [False] * 7,
        }
    )


def test_recovery_only_2021_19_through21_and_no_input_mutation():
    original = make_frame()
    before = original.copy(deep=True)
    actual, mask = recover(original, SPEC)
    assert mask.tolist() == [False, True, True, True, False, False, True, False]
    assert actual.loc[[0, 4, 5, 7], "category"].tolist() == ["old"] * 4
    assert actual.loc[1, "category"] == "covid19_reported_khmer2021"
    assert actual.loc[2, "category"] == "flu_cold_khmer2021"
    assert actual.loc[3, "category"] == "other_specified_khmer2021"
    pd.testing.assert_frame_equal(original, before)


def test_injury_is_labelled_but_not_eligible_and_strict_flag_stays_same():
    original = make_frame()
    actual, _ = recover(original, SPEC)
    assert actual.version_qualified_analysis_eligible.tolist() == [False, True, True, True, False, False, False, False]
    pd.testing.assert_series_equal(actual.within_wave_analysis_eligible, original.within_wave_analysis_eligible)
    assert actual.within_wave_eligible_with_qualifications.tolist() == [
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
    ]
    pd.testing.assert_series_equal(actual.raw_type_code, original.raw_type_code)
    pd.testing.assert_series_equal(actual.raw_screen_code, original.raw_screen_code)


def test_old_interpretation_retained_and_unknown_codes_still_flagged():
    actual, _ = recover(make_frame(), SPEC)
    assert actual.category_v1.eq("old").all()
    assert actual.loc[[4, 5], "type_needs_code_review"].all()
    assert not actual.loc[[1, 2, 3], "type_needs_code_review"].any()
    assert actual.loc[[1, 2, 3], "category_status"].eq("khmer_form_supported_version_qualified").all()


def test_spec_pins_evidence_without_publication():
    assert len(SPEC["upstream_manifest_sha256"]) == 64
    assert len(SPEC["questionnaire_sha256"]) == 64
    assert not SPEC["publication_approved"]
    assert set(SPEC["mapping"]) == {"19", "20", "21"}


def test_cached_khmer_and_english_forms_really_disagree():
    base = ROOT / "data/processed/cses_questionnaires/v1"
    if not (base / "manifest.json").exists():
        pytest.skip("Questionnaire cache not available")
    km = json.loads((base / "2021/text/253ed542d52c8f46.json").read_text())["sheets"][SPEC["sheet"]]
    en = json.loads((base / "2021/text/715917b0b0b7597b.json").read_text())["sheets"]["13 Health Care Seeking _ 2"]
    assert extract_tail(km["B47"])["19"] == SPEC["mapping"]["19"]["khmer"]
    assert km["F30"] == "(2b)"
    assert "19 = Other diseases" in en["C42"]
