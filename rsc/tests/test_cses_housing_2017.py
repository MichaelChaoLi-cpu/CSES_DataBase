"""The user-approved transfer stays scoped, explicit and source-preserving."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cses_db"))
import publish_cses_housing_2017 as transfer  # noqa: E402


def test_structure_ignores_only_case():
    names = [f"q{i}" for i in range(32)]
    assert transfer.check_structure(names, [n.upper() for n in names]) == names


@pytest.mark.parametrize("change", ["order", "missing", "duplicate", "renamed"])
def test_structure_rejects_other_differences(change):
    names = [f"q{i}" for i in range(32)]
    target = names.copy()
    if change == "order":
        target.reverse()
    elif change == "missing":
        target.pop()
    elif change == "duplicate":
        target[-1] = target[0]
    else:
        target[-1] = "new_variable"
    with pytest.raises(ValueError, match="raw columns"):
        transfer.check_structure(names, target)


def test_codes_allow_unobserved_reference_options_not_unknown_target_values():
    transfer.check_codes(["1", "3"], ["1", "2", "3", "4"])
    with pytest.raises(ValueError, match="absent"):
        transfer.check_codes(["1", "9"], ["1", "2", "3", "4"])


def test_new_view_names_and_release_are_explicit():
    dictionary, category = transfer.view_queries({"rows": []})
    assert "cses_housing_value_dictionary_v1 UNION ALL" in dictionary.as_string()
    assert transfer.RELEASE in dictionary.as_string()
    assert "cses_housing_value_dictionary_v2" in category.as_string()
    assert "'cses-housing-interface-v2'::text AS housing_dictionary_version" in category.as_string()
    assert "unmapped_nonnull" in category.as_string() and "source_null" in category.as_string()
    assert "h.*" in category.as_string()


def test_local_transfer_is_exactly_2016_and_never_invents_source_labels():
    root = Path(__file__).resolve().parents[2]
    plan = transfer.local_plan(root)
    assert len(plan["rows"]) == 21
    assert sum(r["observed_count"] > 0 for r in plan["rows"]) == 16
    assert sum(r["observed_count"] for r in plan["rows"]) == 11519
    assert all(r["source_label"] is None for r in plan["rows"])
    assert all(r["evidence"]["approval_basis"] == "user_approved_cross_wave_transfer" for r in plan["rows"])
    assert all(r["evidence"]["target_questionnaire_verified"] is False for r in plan["rows"])
    donor = [r for r in transfer.frozen_plan(root)["approved_rows"] if r["survey_wave"] == "2016"]
    assert {(r["field"], r["source_code"], r["category"], r["label"]) for r in plan["rows"]} == {
        (r["canonical_name"], r["source_code"], r["approved_canonical_value"], r["approved_canonical_label"])
        for r in donor}


def test_desired_records_keep_policy_in_lineage_not_fabricated_git_revision():
    manifest = {"predecessors": [{"canonical_name": "x", "dataset_id": 1, "canonical_variable_id": 2,
                  "source_variable_names": ["Q"], "source_kind": "explicit", "transformation_rule": "Original."}],
                "implementation_sha256": {"code": "hash"}, "backup": []}
    plan = {"spec_sha256": "spec", "rows": [{"field": "x", "source_code": "1", "category": "owned", "label": "Owned"}]}
    desired = transfer.desired(plan, manifest, "exec-hash")
    assert desired["values"][0]["source_label"] is None
    assert desired["mappings"][0]["source_variable_names"] == ["Q"]
    assert desired["run"]["code_git_revision"] is None
    assert desired["run"]["validation_summary"]["execution_sha256"] == "exec-hash"
