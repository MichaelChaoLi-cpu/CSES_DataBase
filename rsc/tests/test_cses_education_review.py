"""Education evidence must preserve wave-specific meaning, routing and uncertainty."""
import copy
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
from cses_education import harmonize_current_level, harmonize_highest_level  # noqa: E402
from review_cses_education import (  # noqa: E402
    evidence_review,
    expected_codes,
    field_profile,
    load_inputs,
    normalize_legacy_source_paths,
    options,
    value_counts,
)


@pytest.fixture(scope="module")
def inputs():
    if not (ROOT / "data/processing/cses/questionnaire_alignment_v1/source_cells.json").exists():
        pytest.skip("Frozen DVC sources not available")
    return load_inputs(ROOT)


@pytest.fixture(scope="module")
def review(inputs):
    return evidence_review(*inputs)


def test_exact_question_scope_and_no_publication(review):
    questions, universes = review
    assert len(questions) == 48 and len(universes) == 7
    assert all(not r["whole_variable_certified"] and not r["database_publication_approved"] for r in questions)


def test_three_form_gaps_not_borrowed(review):
    assert not ({"2007", "2017", "2019"} & {r["survey_wave"] for r in review[0]})


def test_2004_age_five_later_three(review):
    for r in review[1]:
        assert r["minimum_age"] == (5 if r["survey_wave"] == "2004" else 3)


def test_2014_seven_questions_remain_draft(review):
    rows = [r for r in review[0] if r["survey_wave"] == "2014"]
    assert len(rows) == 7 and all(r["documentation_status"] == "provisional" for r in rows)


def test_years_numeric_and_absent_2004(review):
    rows = [r for r in review[0] if r["canonical_field"] == "years_attended_school"]
    assert len(rows) == 6 and all(r["substantive_option_count"] is None for r in rows)
    assert all("not a printed maximum" in r["numeric_unit"] for r in rows)


def test_current_postgraduate_conflict_is_not_fixed_in_old_builder(review):
    for wave in ["2013", "2014", "2016"]:
        q = next(r for r in review[0] if r["survey_wave"] == wave and r["canonical_field"] == "current_education_level_source_code")
        option = next(o for o in q["options"] if o["source_code"] == 21)
        assert option["label_as_printed"] == "Postgraduate studies"
        assert harmonize_current_level(wave, 21) == 7
        assert harmonize_highest_level(wave, 21) == 7  # Separate item: Other is correct here.


def test_current_and_highest_2021_code20_differ(review):
    current, highest = [next(r for r in review[0] if r["survey_wave"] == "2021" and r["canonical_field"] == f)
                        for f in ["current_education_level_source_code", "highest_education_level_source_code"]]
    assert "Other" in next(o["label_as_printed"] for o in current["options"] if o["source_code"] == 20)
    assert "Doctorate" in next(o["label_as_printed"] for o in highest["options"] if o["source_code"] == 20)


def test_grade_ellipsis_expansion_not_claimed_literal(review):
    q = next(r for r in review[0] if r["survey_wave"] == "2004" and r["canonical_field"] == "highest_education_level_source_code")
    expanded = next(o for o in q["options"] if o["source_code"] == 3)
    assert expanded["label_as_printed"] is None
    assert expanded["label_basis"] == "grade_sequence_expanded_from_printed_ellipsis"
    assert q["substantive_option_count"] == 21 and q["unknown_option_count"] == 1


def test_option_counts_do_not_treat_numeric_years_as_choices():
    assert expected_codes("2016", "years_attended_school") == set()
    assert len(expected_codes("2016", "current_education_level_source_code")) == 18


def test_duplicate_option_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        options("1=Yes\n1=No", "A1", "can_read")


def test_source_option_drift_fails_closed(inputs):
    spec, alignment, inventory, cells = copy.deepcopy(inputs)
    target = next(s for s in cells if "HSES V21 ENG" in s["source_file"])
    target["sheets"]["02 Education"]["C8"] = "1=Yes\n3=No"
    with pytest.raises(ValueError, match="Option set changed"):
        evidence_review(spec, alignment, inventory, cells)


def test_source_age_gate_drift_fails_closed(inputs):
    spec, alignment, inventory, cells = copy.deepcopy(inputs)
    target = next(s for s in cells if "HSES V21 ENG" in s["source_file"])
    target["sheets"]["02 Education"]["A2"] = "All ages"
    with pytest.raises(ValueError, match="age gate"):
        evidence_review(spec, alignment, inventory, cells)


def sample_frame():
    return pd.DataFrame({"age": pd.Series([2, 5, 6, pd.NA], dtype="Int16"),
        "ever_attended_school": pd.Series([1, 0, 1, 1], dtype="Int8"),
        "currently_attending_school": pd.Series([1, 0, 1, pd.NA], dtype="Int8"),
        "current_education_level_source_code": pd.Series([1, 88, 2, pd.NA], dtype="Int16")})


def test_route_counts_do_not_delete_outside_records():
    frame = sample_frame()
    result = field_profile(frame, "current_education_level_source_code", 3)
    assert result["rows"] == 4 and result["nonnull"] == 3
    assert result["literal_route_eligible_records"] == result["nonnull_within_literal_route"] == 1
    assert result["nonnull_below_minimum_age"] == result["nonnull_despite_ever_no"] == 1
    assert result["literal_route_unknown_records"] == 1


def test_missing_form_gets_no_assumed_denominator():
    result = field_profile(sample_frame(), "current_education_level_source_code", None)
    assert result["literal_route_eligible_records"] is None
    assert result["nonnull_within_literal_route"] is None
    assert result["nonnull_below_minimum_age"] is None


def test_absent_source_item_gets_no_invented_route_denominator():
    result = field_profile(sample_frame(), "current_education_level_source_code", 3, item_available=False)
    assert result["literal_route_eligible_records"] is None
    assert result["literal_route_unknown_records"] is None
    assert not result["source_item_available"]


def test_fractional_raw_values_not_silently_rounded():
    assert value_counts(pd.Series([1, 1.5, 1, None])) == {"1": 2, "1.5": 1}


def test_only_established_leading_path_relocation_is_normalized():
    original = pd.Series(["data/raw/CSE/a.zip", "data/raw/a.zip", "other/data/raw/CSE/a.zip"], dtype="string")
    assert normalize_legacy_source_paths(original).tolist() == ["data/raw/a.zip", "data/raw/a.zip", "other/data/raw/CSE/a.zip"]
    assert original.iloc[0] == "data/raw/CSE/a.zip"
