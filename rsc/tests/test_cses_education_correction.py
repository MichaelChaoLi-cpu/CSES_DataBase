"""The education correction is exact, additive, source-qualified and reproducible."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
from publish_cses_education_correction import (  # noqa: E402
    COUNTS,
    EXTRAS,
    FIELD,
    VERSION,
    corrected,
    correction_mask,
    source_plan,
)


def sample():
    return pd.DataFrame({"survey_wave": ["2013", "2014", "2016", "2017", "2021", "2013", "2013", "2013"],
        "current_education_level_source_code": pd.Series([21, 21, 21, 21, 20, 21, 20, 21], dtype="Int16"),
        "currently_attending_school": pd.Series([1, 1, 1, 1, 1, 0, 1, pd.NA], dtype="Int8"),
        FIELD: pd.Series([7, 7, 7, 7, 7, pd.NA, 7, pd.NA], dtype="Int8"),
        "education_level_harmonized": pd.Series([7] * 8, dtype="Int8")})


def test_only_three_approved_waves_corrected():
    before = sample()
    after = corrected(before)
    assert correction_mask(before).tolist() == [True, True, True, False, False, False, False, False]
    assert after[FIELD].iloc[:5].tolist() == [6, 6, 6, 7, 7]


def test_original_completed_and_raw_codes_preserved():
    before = sample()
    after = corrected(before)
    for c in ["education_level_harmonized", "current_education_level_source_code"]:
        pd.testing.assert_series_equal(before[c], after[c])
    pd.testing.assert_series_equal(before[FIELD], after[EXTRAS[0]], check_names=False)
    assert before[FIELD].iloc[0] == 7


def test_2014_draft_and_2017_uncertainty_retained():
    after = corrected(sample())
    assert after[EXTRAS[2]].iloc[1] == "corrected_user_approved_2014_draft"
    assert after[EXTRAS[2]].iloc[3] == "unresolved_2017_no_household_form"
    assert after[EXTRAS[1]].iloc[1] == VERSION
    assert pd.isna(after[EXTRAS[1]].iloc[3])


def test_missing_attendance_and_missing_level_not_imputed():
    after = corrected(sample())
    assert pd.isna(after[FIELD].iloc[5]) and pd.isna(after[FIELD].iloc[7])
    assert after[FIELD].dtype == sample()[FIELD].dtype


@pytest.fixture(scope="module")
def plan():
    if not (ROOT / "data/processing/cses/education_review_v1/review.json").exists():
        pytest.skip("DVC review not present")
    return source_plan(ROOT)


def test_exact_full_scope_and_no_physical_overwrite(plan):
    p, frame = plan
    assert p["changed_counts"] == COUNTS == {"2013": 6, "2014": 18, "2016": 6}
    assert frame.shape == (343204, 37)
    assert frame[EXTRAS[1]].notna().sum() == 30
    assert p["physical_data_changes"] == p["existing_interfaces_replaced"] == 0


def test_age_qualification_survives_correction(plan):
    frame = plan[1]
    top = frame.loc[frame.age_2004_is_topcoded.fillna(False)]
    assert len(top) == 3 and top.age_2004_exact_years.isna().all()
    assert top.age_2004_lower_bound.eq(96).all()


def test_rule_provenance_and_source_view(plan):
    p, _ = plan
    assert len(p["rules"]) == 3
    assert all(r["source_cell"] == "AF7" and r["source_label"] == "Postgraduate studies" for r in p["rules"])
    assert "cses_analysis.cses_ed_age_v1" in p["queries"]["cses_ed_aligned_v1"]
    assert p["rules"][1]["documentation_status"] == "provisional"
