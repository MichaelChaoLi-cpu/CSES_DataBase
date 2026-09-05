"""Housing interface conserves original rows, version identity and interpretation boundaries."""

import copy
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
import publish_cses_housing_interface as interface  # noqa: E402


@pytest.fixture
def plan():
    return json.loads((ROOT / "data/processing/cses/value_mapping_release_v1/plan.json").read_text())


def test_exact_approved_dictionary_scope(plan):
    payload = interface.approved_payload(plan)
    assert len(payload) == 140
    assert len({(r["dataset_id"], r["canonical_variable_id"]) for r in payload}) == 21
    assert len(interface.expected_index(plan)) == 140


def test_ambiguous_approved_identity_is_rejected(plan):
    plan["approved_rows"].append(copy.deepcopy(plan["approved_rows"][0]))
    with pytest.raises(ValueError, match="Ambiguous"):
        interface.expected_index(plan)
    with pytest.raises(ValueError, match="unique"):
        interface.approved_payload(plan)


@pytest.mark.parametrize("value", [None, pd.NA, float("nan")])
def test_null_is_not_a_category_or_an_inferred_missing_reason(value):
    assert interface.expected_match({}, "2004", "a", "b", "c", value) == ("source_null", None, None)


def test_nonnull_unknown_code_is_preserved_as_unmatched():
    assert interface.expected_match({}, "2004", "a", "b", "c", 9) == ("unmapped_nonnull", None, None)


def test_matching_requires_exact_wave_file_field_and_code(plan):
    index = interface.expected_index(plan)
    row = plan["approved_rows"][0]
    key = row["source_key"]
    args = [row["survey_wave"], key["archive_relative_path"], interface.source_member(key), row["canonical_name"], float(row["source_code"])]
    assert interface.expected_match(index, *args)[0] == "matched"
    args[2] = "different_source.dta"
    assert interface.expected_match(index, *args)[0] == "unmapped_nonnull"


def test_path_normalization_is_anchored_and_comparison_only():
    assert interface.source_archive("data/raw/CSE/CSES 2004.zip") == "data/raw/CSES 2004.zip"
    assert interface.source_archive("prefix/data/raw/CSE/file.zip") == "prefix/data/raw/CSE/file.zip"
    assert interface.source_member({"member_path": "outer.zip", "nested_member_path": "inner.dta"}) == "outer.zip::inner.dta"


def test_code_nine_does_not_have_one_global_meaning(plan):
    rows = [r for r in plan["approved_rows"] if r["canonical_name"] == "main_lighting_source_code" and r["source_code"] == "9"]
    by_wave = {r["survey_wave"]: r["approved_canonical_value"] for r in rows}
    assert "2004" not in by_wave
    assert by_wave["2016"] != by_wave["2021"]


def test_qualifiers_and_questionnaire_provenance_are_retained(plan):
    row = next(r for r in plan["approved_rows"] if r["survey_wave"] == "2014")
    evidence = interface.row_evidence(row, plan["interpretation_notes"])
    assert evidence["source_evidence"] == row["evidence"]
    assert evidence["questionnaire_option"] == row["questionnaire_option"]
    assert evidence["historical_flags"] == row["historical_flags"]
    assert evidence["interpretation_notes"]["draft"]
    assert evidence["interpretation_notes"]["no_technology_inference"]


def test_sql_uses_three_left_joins_and_exact_release(plan):
    dictionary = interface.dictionary_query(plan).as_string()
    query = interface.category_query(interface.dictionary_query(plan)).as_string()
    assert query.count("LEFT JOIN dictionary") == 3
    assert "h.*" in query
    assert "cses-housing-value-mapping-v1" in dictionary
    assert "LIMIT" not in query and "DISTINCT ON" not in query
    assert "source_submodule=h.source_submodule" in query
    assert len(interface.EXTRAS) == 16 and len(set(interface.EXTRAS)) == 16
