"""Exact scope and safety checks for user-approved manual-review decisions."""

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))

from record_cses_value_mapping_decisions import (  # noqa: E402
    SPEC,
    build_decisions,
    load_review,
    write_outputs,
)


@pytest.fixture(scope="module")
def inputs():
    spec = json.loads((ROOT / SPEC).read_text())
    return spec, load_review(ROOT, spec)


@pytest.fixture(scope="module")
def record(inputs):
    return build_decisions(inputs[1], inputs[0])


def test_exactly_the_seventy_manual_rows_are_approved(record):
    assert record["summary"]["approved_rows"] == 70
    assert len({row["review_row_id"] for row in record["approved_decisions"]}) == 70
    assert record["summary"]["approved_by_field"] == {
        "dwelling_tenure_source_code": 18,
        "main_cooking_fuel_source_code": 38,
        "main_lighting_source_code": 14,
    }
    assert record["summary"]["approved_by_wave"] == {
        "2004": 12, "2009": 10, "2011-12": 10, "2014": 20,
        "2016": 10, "2019": 4, "2021": 4,
    }


def test_unselected_buckets_remain_unchanged(record):
    assert record["summary"]["remaining_review_rows"] == 138
    assert record["summary"]["remaining_by_bucket"] == {
        "blocked": 52, "candidate": 70, "missing_only": 16,
    }
    assert not record["database_write_allowed"]
    assert not record["database_mutated"]
    assert not record["publication_ready"]


def test_qualifications_and_provisional_evidence_are_retained(record):
    reasons = {reason for row in record["approved_decisions"] for reason in row["retained_qualifications"]}
    assert reasons == {"category_comparability_review", "draft_questionnaire",
                       "skip_instruction_retained_not_evaluated"}
    draft = [row for row in record["approved_decisions"] if "draft_questionnaire" in row["retained_qualifications"]]
    assert len(draft) == 20
    assert all(row["questionnaire_option"] is not None for row in draft)


def test_compounds_and_residuals_remain_distinct(record):
    values = {row["approved_canonical_value"] for row in record["approved_decisions"]}
    assert {"firewood_and_charcoal", "gas_and_electricity", "kerosene_or_diesel", "other"} <= values
    assert all(row["category_key"].startswith(row["source_key"]["canonical_name"] + ":")
               for row in record["approved_decisions"])


def test_source_review_tampering_is_rejected_before_decision_build(inputs):
    bad = copy.deepcopy(inputs[0])
    bad["source_review"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="fingerprint changed"):
        load_review(ROOT, bad)


def test_existing_decision_evidence_is_immutable(tmp_path, record):
    write_outputs(tmp_path, record)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    write_outputs(tmp_path, record)
    changed = copy.deepcopy(record)
    changed["summary"]["approved_rows"] = 0
    with pytest.raises(ValueError, match="Existing decision evidence differs"):
        write_outputs(tmp_path, changed)
    assert before == {path.name: path.read_bytes() for path in tmp_path.iterdir()}
