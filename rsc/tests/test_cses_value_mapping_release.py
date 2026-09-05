"""Protect the approved subset, prior decisions, source identities and option provenance."""

import copy
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))

from plan_cses_value_mapping_release import (  # noqa: E402
    approved_rows,
    load_context,
    mapping_key,
    verify_questionnaire_options,
)


@pytest.fixture(scope="module")
def context():
    return load_context(ROOT)


def test_approved_union_excludes_unresolved_and_missing(context):
    spec, data, _ = context
    rows = approved_rows(spec, data)
    assert Counter(r["review_bucket"] for r in rows) == {"candidate": 70, "manual_review": 70}
    assert len({mapping_key(r) for r in rows}) == 21
    assert len({r["category_key"] for r in rows}) == 24
    assert all(r["missing_class"] == "substantive" for r in rows)
    assert not any(r["survey_wave"] == "2004" and r["canonical_name"] == "main_lighting_source_code"
                   and r["source_code"] == "9" for r in rows)
    assert next(r for r in rows if r["survey_wave"] == "2016" and
                r["canonical_name"] == "main_lighting_source_code" and r["source_code"] == "9"
                )["approved_canonical_value"] == "biogas"


def test_prior_manual_approval_cannot_be_reinterpreted(context):
    spec, data, _ = context
    changed = copy.deepcopy(data)
    changed["manual_decisions"]["approved_decisions"][0]["approved_canonical_value"] = "invented"
    with pytest.raises(ValueError, match="Prior approved decision changed"):
        approved_rows(spec, changed)


def test_duplicate_or_misidentified_approved_rows_fail(context):
    spec, data, _ = context
    changed = copy.deepcopy(data)
    candidate = next(r for r in changed["review"]["code_rows"] if r["review_bucket"] == "candidate")
    candidate["source_key"]["source_code"] = "999"
    with pytest.raises(ValueError, match="Source identity"):
        approved_rows(spec, changed)


def test_retained_cells_validate_code_label_and_skip_not_only_category(context):
    spec, data, evidence = context
    rows = approved_rows(spec, data)
    assert verify_questionnaire_options(ROOT, rows, evidence["audit_spec"]) == 100
    changed = copy.deepcopy(rows)
    next(r for r in changed if r["questionnaire_option"])["questionnaire_option"]["skip_text"] = "invented routing"
    with pytest.raises(ValueError, match="Option code/label/skip text"):
        verify_questionnaire_options(ROOT, changed, evidence["audit_spec"])


def test_effective_correction_is_preserved_and_composite_values_stay_distinct(context):
    spec, data, _ = context
    rows = approved_rows(spec, data)
    lighting = [r for r in rows if r["survey_wave"] == "2004" and r["canonical_name"] == "main_lighting_source_code"]
    assert {r["effective_mapping_version"] for r in lighting} == {"cses-housing-lighting-missing-v1"}
    assert {"kerosene", "kerosene_or_diesel", "firewood", "firewood_and_charcoal", "gas_and_electricity"} <= {
        r["approved_canonical_value"] for r in rows}
