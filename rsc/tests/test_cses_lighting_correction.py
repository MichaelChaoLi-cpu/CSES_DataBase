"""Scope and whole-table invariants for the approved missing-code correction."""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))

from correct_cses_housing_lighting import (  # noqa: E402
    check_database_state,
    compare_local,
    normalize_legacy_archive_paths,
)
from cses_housing import lighting_source_codes  # noqa: E402


def test_missing_code_rule_is_specific_to_2004():
    assert lighting_source_codes("2004") == set(range(1, 11)) - {9}
    for wave in ("2007", "2009", "2011-12", "2013", "2014", "2016", "2017", "2019", "2021"):
        assert lighting_source_codes(wave) == set(range(1, 11))


@pytest.fixture
def correction_pair():
    spec = json.loads((ROOT / "rsc/specs/cses_housing_lighting_missing_v1.json").read_text())
    before = pd.DataFrame({
        "Survey Wave": ["2004", "2021"], "Household ID": [spec["household_id"], "other"],
        "Source Row ID": [spec["source_row_id"], "other"],
        "Main Lighting Source Code": pd.Series([9, 9], dtype="Int16"),
        "Unrelated": pd.Series([3, 4], dtype="Int16"),
    })
    after = before.copy()
    after.loc[0, "Main Lighting Source Code"] = pd.NA
    return spec, before, after


def test_whole_table_diff_accepts_only_one_cell(correction_pair):
    spec, before, after = correction_pair
    assert compare_local(before, after, spec)["changed_cells"] == 1
    after.loc[1, "Main Lighting Source Code"] = pd.NA
    with pytest.raises(AssertionError):
        compare_local(before, after, spec)


def test_extra_column_change_and_type_change_fail(correction_pair):
    spec, before, after = correction_pair
    after.loc[1, "Unrelated"] = 5
    with pytest.raises(AssertionError):
        compare_local(before, after, spec)
    after["Unrelated"] = after["Unrelated"].astype("Float64")
    with pytest.raises(ValueError, match="dtypes"):
        compare_local(before, after, spec)


def test_unrelated_database_drift_is_not_accepted():
    spec = {"column": "lighting"}
    before = {"protected_relations": [{"sha256": "original"}], "structure_sha256": "structure",
              "target_row": {"lighting": 9, "unrelated": 2},
              "housing_full": "before", "compatibility_full": "before"}
    after = {**before, "target_row": {"lighting": None, "unrelated": 2},
             "housing_full": "after", "compatibility_full": "after"}
    check_database_state(after, before, spec, True)
    after["protected_relations"] = [{"sha256": "changed"}]
    with pytest.raises(ValueError, match="content changed"):
        check_database_state(after, before, spec, True)


def test_current_full_release_changes_one_cell():
    spec = json.loads((ROOT / "rsc/specs/cses_housing_lighting_missing_v1.json").read_text())
    before_path = ROOT / spec["release_directory"] / "before/final_HO_CSES.parquet"
    before = pd.read_parquet(before_path)
    after = pd.read_parquet(ROOT / "data/processing/cses/final_HO_CSES.parquet")
    assert compare_local(before, after, spec)["rows"] == 77922


def test_archive_comparison_normalizes_only_the_accepted_prefix():
    values = pd.Series(["data/raw/CSE/CSES 2004.zip", "data/raw/CSES2019.zip", "elsewhere/data/raw/CSE/source.zip"])
    assert normalize_legacy_archive_paths(values).tolist() == [
        "data/raw/CSES 2004.zip", "data/raw/CSES2019.zip", "elsewhere/data/raw/CSE/source.zip"]
