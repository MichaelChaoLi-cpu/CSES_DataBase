"""Population units and completeness must not be overstated."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cses_db"))
from build_cses_variable_brief import assessment, keyed_union  # noqa: E402


def test_person_union_deduplicates_tables_but_not_waves():
    frames = {
        "final_HL_CSES": pd.DataFrame({"survey_wave": ["2004", "2009"], "person_id": ["a", "a"]}),
        "final_ED_CSES": pd.DataFrame({"survey_wave": ["2004", "2009"], "person_id": ["a", "b"]}),
        "final_EC_CSES": pd.DataFrame({"survey_wave": ["2004"], "person_id": ["a"]}),
    }
    result = keyed_union(frames, ["HL", "ED", "EC"], "person_id")
    assert len(result) == 3
    assert result.groupby("survey_wave").size().to_dict() == {"2004": 1, "2009": 2}


def test_household_union_retains_housing_orphans():
    frames = {"final_HH_CSES": pd.DataFrame({"survey_wave": ["2004"], "household_id": ["a"]}),
              "final_HO_CSES": pd.DataFrame({"survey_wave": ["2004", "2004"], "household_id": ["a", "orphan"]})}
    assert len(keyed_union(frames, ["HH", "HO"], "household_id")) == 2


def test_housing_coverage_remains_qualified_not_blanket_certification():
    assert assessment("final_HO_CSES", "main_lighting_source_code") == "published_code_definitions_all_10_waves_with_qualifications"


def test_member_sex_review_does_not_propagate_to_other_modules():
    assert assessment("final_HL_CSES", "sex") == "reviewed_member_foundations_scope_limited"
    assert assessment("final_ED_CSES", "sex") == "baseline_standardization_present_semantic_reaudit_pending"


def test_household_head_age_has_only_bounded_2004_qualification():
    assert assessment("final_HH_CSES", "household_head_age") == "published_2004_age_qualification_other_waves_not_certified"
