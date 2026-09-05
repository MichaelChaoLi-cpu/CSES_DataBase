"""Exact publication records and protection against unintended metadata changes."""

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))

from publish_cses_value_mappings import (  # noqa: E402
    COUNTS,
    PLAN,
    assert_protected,
    expected_records,
    frozen_plan,
    insert_records,
)


@pytest.fixture
def desired():
    plan = json.loads((ROOT / PLAN).read_text())
    manifest = {"code_git_revision": "test-revision", "source_data_dvc_revision": "test-data",
                "backup_sha256": "b" * 64, "protected_before": {"test": "baseline"}}
    return expected_records(plan, manifest, "e" * 64)


def test_preserves_approved_dictionary_and_correction_rule(desired):
    assert len(desired["mappings"]) == 21
    assert len(desired["values"]) == 140
    assert len({(v["dataset_id"],v["canonical_variable_id"],v["source_value"]) for v in desired["values"]}) == 140
    assert desired["run"]["row_counts"] == COUNTS
    provenance = desired["run"]["validation_summary"]["source_rule_provenance"]
    corrected = next(p for p in provenance if p["previous_mapping_version"] == "cses-housing-lighting-missing-v1")
    assert corrected["previous_variable_mapping_id"] == 1715
    mapping = next(m for m in desired["mappings"] if (m["dataset_id"],m["canonical_variable_id"]) ==
                   (corrected["dataset_id"],corrected["canonical_variable_id"]))
    assert "q03_08=9" in mapping["transformation_rule"]
    assert not any(v["source_value"] == "9" and (v["dataset_id"],v["canonical_variable_id"]) ==
                   (corrected["dataset_id"],corrected["canonical_variable_id"]) for v in desired["values"])


def test_questionnaire_labels_are_not_invented_stata_labels(desired):
    assert sum(v["source_label"] is None for v in desired["values"]) > 0
    assert all(v["canonical_label"] and v["canonical_value"] for v in desired["values"])


def test_protected_table_or_structure_drift_is_rejected():
    before = {"structure_sha256": "abc", "protected_relations": [{"table_name": "cses_survey", "sha256": "def"}]}
    assert_protected(copy.deepcopy(before), before)
    after = copy.deepcopy(before)
    after["protected_relations"][0]["sha256"] = "changed"
    with pytest.raises(ValueError, match="Protected database"):
        assert_protected(after, before)


def test_reviewed_plan_tamper_rejected_before_database_access(tmp_path):
    target = tmp_path / PLAN
    target.parent.mkdir(parents=True)
    target.write_text("{}")
    with pytest.raises(ValueError, match="Reviewed plan hash"):
        frozen_plan(tmp_path)


def test_inserts_use_new_mapping_ids_and_only_the_four_metadata_tables(desired):
    class FakeConnection:
        def __init__(self):
            self.calls = []
            self.mapping_ids = {}

        def execute(self, query, params):
            self.calls.append((query, params))
            result = {}
            if "RETURNING alignment_release_id" in query:
                result = {"alignment_release_id": 800}
            if "RETURNING variable_mapping_id" in query:
                mid = 900 + len(self.mapping_ids)
                self.mapping_ids[tuple(params[:2])] = mid
                result = {"variable_mapping_id": mid}

            class Cursor:
                def fetchone(self):
                    return result
            return Cursor()

    connection = FakeConnection()
    insert_records(connection, desired)
    assert len(connection.calls) == 163
    assert all(q.startswith("INSERT INTO cses_") for q, _ in connection.calls)
    inserted = [p for q, p in connection.calls if "INSERT INTO cses_alignment.cses_value_mapping " in q]
    for params, value in zip(inserted, desired["values"], strict=True):
        assert params[0] == connection.mapping_ids[(value["dataset_id"],value["canonical_variable_id"])]
        assert params[1:] == tuple(value[k] for k in
                                 ("source_value","source_label","canonical_value","canonical_label","alignment_status"))
