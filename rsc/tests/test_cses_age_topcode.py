"""2004 age top-code qualification is additive, wave-specific and non-publishing."""

import ast
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
from plan_cses_age_topcode import (  # noqa: E402
    EXTRAS,
    REVIEW,
    TARGETS,
    age_query,
    checked_review,
    local_plan,
    proposed_ddl,
    qualify,
    rule_records,
    save_package,
)


def frame(waves, ages, column="age"):
    return pd.DataFrame({"survey_wave": pd.Series(waves, dtype="string"), column: pd.Series(ages, dtype="Int16")})


def test_96_is_lower_bound_not_exact_and_original_is_unchanged():
    original = frame(["2004"], [96])
    before = original.copy(deep=True)
    result = qualify(original, "age")
    assert result.loc[0, "age"] == 96 and result.loc[0, EXTRAS[0]]
    assert result.loc[0, EXTRAS[1]] == 96 and pd.isna(result.loc[0, EXTRAS[2]])
    assert result.loc[0, EXTRAS[3]] == "topcoded_96_plus"
    pd.testing.assert_frame_equal(original, before)


@pytest.mark.parametrize("value", [0, 1, 14, 15, 64, 65, 95])
def test_other_valid_2004_ages_are_preserved(value):
    result = qualify(frame(["2004"], [value]), "age")
    assert not result.loc[0, EXTRAS[0]]
    assert result.loc[0, EXTRAS[1]] == result.loc[0, EXTRAS[2]] == value
    assert result.loc[0, EXTRAS[3]] == "reported_completed_years"


def test_later_age96_not_automatically_coded_true_or_false():
    result = qualify(frame(["2016", "2017", "2021"], [96, 96, 98]), "age")
    assert result[EXTRAS[:3]].isna().all().all()
    assert result[EXTRAS[3]].eq("outside_rule_scope").all()
    assert list(result.age) == [96, 96, 98]


def test_missing_age_does_not_become_false_topcoding_or_zero():
    result = qualify(frame(["2004", "2016"], [None, None]), "age")
    assert result[EXTRAS[:3]].isna().all().all()
    assert list(result[EXTRAS[3]]) == ["missing_age", "outside_rule_scope"]


@pytest.mark.parametrize("value", [-1, 97, 98, 99, 120])
def test_unexpected_2004_code_is_not_claimed_exact(value):
    result = qualify(frame(["2004"], [value]), "age")
    assert result[EXTRAS[:3]].isna().all().all()
    assert result.loc[0, EXTRAS[3]] == "unexpected_2004_code"


def test_household_head_age_uses_same_rule_without_fabricating_heads():
    result = qualify(frame(["2004", "2004"], [96, None], "household_head_age"), "household_head_age")
    assert result.loc[0, EXTRAS[0]] and pd.isna(result.loc[1, EXTRAS[0]])
    assert len(result) == 2


def test_queries_keep_all_original_columns_and_no_filters_or_joins():
    for table in TARGETS:
        query = age_query(table)
        assert "SELECT b.*" in query and f'cses_data."{table}"' in query
        assert "WHERE" not in query and "JOIN" not in query
        assert all(column in query for column in EXTRAS)
    with pytest.raises(ValueError, match="Unapproved target"):
        age_query("unrelated_table")


def test_proposal_has_no_replacement_or_existing_metadata_update():
    ddl = proposed_ddl({"cses_hl_age_v1": age_query("final_HL_CSES")})
    assert "CREATE VIEW" in ddl and "security_barrier=true" in ddl
    assert "CREATE OR REPLACE" not in ddl and "UPDATE " not in ddl and "DROP " not in ddl
    assert "COMMENT ON COLUMN" in ddl and "GRANT SELECT" in ddl


def test_conflicting_package_refused_before_creating_any_new_file(tmp_path):
    save_package(tmp_path, {"old.json": {"old": 1}})
    with pytest.raises(ValueError, match="Refusing changed"):
        save_package(tmp_path, {"new.json": {}, "old.json": {"old": 2}})
    assert not (tmp_path / "new.json").exists()
    assert json.loads((tmp_path / "old.json").read_text()) == {"old": 1}


def test_actual_local_plan_and_source_evidence():
    if not (ROOT / REVIEW).exists():
        pytest.skip("Accepted DVC review not present")
    review = checked_review(ROOT)
    plan = local_plan(ROOT, review)
    assert plan["distinct_affected_people"] == 3 and plan["same_people_in_hl_ed_ec"]
    assert plan["new_view_count"] == len(plan["queries"]) == 5
    assert not plan["database_publication_approved"] and not plan["database_mutated"]
    assert plan["existing_data_updates"] == plan["existing_metadata_updates"] == 0
    assert [s["topcoded_rows"] for s in plan["local_statistics"].values()] == [3, 3, 3, 0]
    records = rule_records(review)
    assert len(records) == 4 and all(r["source_cell"] == "AA9" and r["survey_wave"] == "2004" for r in records)
    assert all("96 years or more" in r["source_instruction"] for r in records)


def test_planner_does_not_execute_its_generated_ddl():
    tree = ast.parse((ROOT / "rsc/cses_db/plan_cses_age_topcode.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
            assert "proposed_ddl" not in ast.unparse(node)
            if node.args and isinstance(node.args[0], ast.Constant):
                assert str(node.args[0].value).lstrip().startswith(("SELECT", "SHOW", "SET"))
