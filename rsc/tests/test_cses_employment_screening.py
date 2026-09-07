"""Employment screening semantics and denominators must remain source-specific."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
from review_cses_employment_screening import FIELDS, evidence, route_mask, semantics  # noqa: E402


@pytest.fixture(scope="module")
def reviewed():
    if not (ROOT / "data/processing/cses/questionnaire_alignment_v1/source_cells.json").exists():
        pytest.skip("Frozen source cells unavailable")
    return evidence(ROOT)


def test_exact_28_question_scope_without_publication(reviewed):
    questions, universes = reviewed
    assert len(questions) == 28 and len(universes) == 7
    assert all(not q["whole_variable_certified"] and not q["publication_approved"] for q in questions)


def test_two_options_preserve_source_codes(reviewed):
    assert all({o["source_code"] for o in q["options"]} == {1, 2} for q in reviewed[0])


def test_2009_explicit_correspondence_does_not_rewrite_old_candidates(reviewed):
    rows = [q for q in reviewed[0] if q["survey_wave"] == "2009"]
    assert len(rows) == 4
    assert all(q["original_heuristic_candidate_ids"] == [] and "A/C" in q["correspondence_basis"] for q in rows)


def test_2021_continuations_not_truncated(reviewed):
    first = next(q for q in reviewed[0] if q["survey_wave"] == "2021" and q["field"] == FIELDS[0])
    second = next(q for q in reviewed[0] if q["survey_wave"] == "2021" and q["field"] == FIELDS[1])
    assert first["question_text_cells"] == ["F4", "F7"] and "holiday" in first["question_text"]
    assert second["question_text_cells"] == ["P4", "P7"] and "farm" in second["question_text"]


def test_second_screen_and_search_period_not_equated():
    assert semantics("2016", FIELDS[1]) != semantics("2021", FIELDS[1])
    assert semantics("2004", FIELDS[2]) == "seeking_past_7_days"
    assert semantics("2013", FIELDS[2]) == "seeking_past_4_weeks"


def test_2014_stays_draft_and_three_gaps_not_filled(reviewed):
    assert all(q["documentation_status"] == "provisional" for q in reviewed[0] if q["survey_wave"] == "2014")
    assert not {"2007", "2017", "2019"} & {q["survey_wave"] for q in reviewed[0]}


def sample():
    return pd.DataFrame({"age": pd.Series([20, 20, 20, 3, pd.NA], dtype="Int16"),
        FIELDS[0]: pd.Series([0, 0, 1, 0, 0], dtype="Int8"),
        FIELDS[1]: pd.Series([2, 2, pd.NA, 2, 2], dtype="Int8"),
        FIELDS[2]: pd.Series([1, 0, pd.NA, 1, 1], dtype="Int8")})


def test_later_availability_requires_search_yes_but_2004_does_not():
    f = sample()
    assert route_mask(f, FIELDS[3], "2021").fillna(False).tolist() == [True, False, False, False, False]
    assert route_mask(f, FIELDS[3], "2004").fillna(False).tolist() == [True, True, False, False, False]


def test_unknown_age_not_misclassified_as_known_outside_route():
    assert pd.isna(route_mask(sample(), FIELDS[2], "2016").iloc[-1])


def test_missing_form_has_no_invented_route_or_meaning():
    assert route_mask(sample(), FIELDS[0], "2017") is None
    assert semantics("2017", FIELDS[1]) == "unverified_household_form"


def test_age_thresholds_are_ten_then_five(reviewed):
    assert {u["survey_wave"]: u["minimum_age"] for u in reviewed[1]} == {
        "2004": 10, "2009": 5, "2011-12": 5, "2013": 5, "2014": 5, "2016": 5, "2021": 5}
