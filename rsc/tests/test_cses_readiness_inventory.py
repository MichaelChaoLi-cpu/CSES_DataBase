"""Readiness dimensions must not confuse observations, provenance and semantic approval."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "rsc/cses_db"))
import inventory_cses_readiness as inventory  # noqa: E402


@pytest.mark.parametrize("rows,nonnull,expected", [
    (0, 0, "wave_absent_from_table"), (4, 0, "all_null_reason_not_inferred"),
    (4, 2, "partially_observed"), (4, 4, "fully_observed"),
])
def test_availability_does_not_infer_semantics(rows, nonnull, expected):
    assert inventory.availability(rows, nonnull) == expected


def test_numeric_codes_and_null_stay_distinct():
    assert inventory.code_key(9.0) == "9"
    assert inventory.code_key(0) == "0"
    assert inventory.code_key(pd.NA) is None
    assert inventory.code_key(float("nan")) is None
    assert inventory.code_key("09") == "09"


def small_inventory(approved):
    table, field = "final_HO_CSES", "lighting_code"
    snapshot = {"surveys": [{"survey_id": 1, "survey_wave": "2004"}, {"survey_id": 2, "survey_wave": "2007"}],
        "datasets": [{"dataset_id": 10, "survey_id": 1}],
        "source_variables": [{"dataset_id": 10, "variable_name": "q1", "variable_label": "Lighting",
                              "question_id": 8, "question_link_status": "provisional"}],
        "questions": [{"question_id": 8, "documentation_status": "provisional", "is_exact_question_text": False}],
        "canonical_variables": [{"canonical_variable_id": 5, "target_table": table, "canonical_name": field,
            "database_type": "smallint", "measure_type": "category", "canonical_definition": "Source code", "status": "approved"}],
        "variable_mappings": [{"dataset_id": 10, "canonical_variable_id": 5, "variable_mapping_id": mid,
            "mapping_version": version, "source_variable_names": ["q1"]} for mid, version in ((1, "baseline"), (2, "dictionary"))]}
    frames = {table: pd.DataFrame({"survey_wave": ["2004"] * 4, field: [1.0, 1.0, 9.0, None]})}
    profiles = {table: {"2004": {"_rows": 4, field: 3}}}
    reviewed = [{"canonical_name": field, "survey_wave": "2004", "review_bucket": "candidate", "review_row_id": "one"}]
    selected = [{"canonical_name": field, "survey_wave": "2004", "source_code": "1"}] if approved else []
    return inventory.field_rows(snapshot, frames, profiles, selected, reviewed)


def test_dictionary_coverage_counts_observations_without_absorbing_null():
    present, absent = small_inventory(True)
    assert present["published_dictionary_entries"] == 1
    assert present["dictionary_matched_nonnull_rows"] == 2
    assert present["dictionary_unmatched_nonnull_rows"] == 1
    assert present["null_count"] == 1
    assert absent["availability"] == "wave_absent_from_table"


def test_catalog_approval_is_not_semantic_completion():
    present, _ = small_inventory(False)
    assert present["catalog_status"] == "approved"
    assert present["semantic_readiness"] == "builder_definition_recorded_not_reaudited_for_analysis"
    assert present["cross_wave_comparability"] == "not_certified_by_this_inventory"


def test_history_and_provisional_question_evidence_are_preserved():
    present, _ = small_inventory(True)
    assert present["mapping_record_ids"] == [1, 2]
    assert present["source_evidence"][0]["question_documentation_status"] == "provisional"
    assert present["source_evidence"][0]["is_exact_question_text"] is False


def test_inventory_refuses_to_overwrite_different_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(inventory, "render", lambda report: "test\n")
    inventory.write_outputs(tmp_path, {"version": 1})
    first = (tmp_path / "inventory.json").read_bytes()
    inventory.write_outputs(tmp_path, {"version": 1})
    assert (tmp_path / "inventory.json").read_bytes() == first
    with pytest.raises(ValueError, match="Existing inventory differs"):
        inventory.write_outputs(tmp_path, {"version": 2})
    assert (tmp_path / "inventory.json").read_bytes() == first


def test_hh_date_extension_requires_unique_household_keys(tmp_path):
    hh = pd.DataFrame({"Survey Wave": ["2004"], "Household ID": ["h1"]})
    dates = pd.DataFrame({"Survey Wave": ["2004", "2004"], "Household ID": ["h1", "h1"],
                          "Survey Actual Year": [2004, 2004], "Survey Actual Month": [1, 1], "Survey Actual Day": [1, 1]})
    output = tmp_path / "data/processing/cses"
    output.mkdir(parents=True)
    hh.to_parquet(output / "final_HH_CSES.parquet")
    dates.to_parquet(output / "final_SURVEY_DATE_CSES.parquet")
    with pytest.raises(ValueError, match="duplicate household keys"):
        inventory.local_frames(tmp_path, ["final_HH_CSES", "final_SURVEY_DATE_CSES"])
