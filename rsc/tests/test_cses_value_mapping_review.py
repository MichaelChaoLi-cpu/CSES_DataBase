"""Conservative review triage, evidence integrity and correction-aware coverage."""

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))

from plan_cses_value_mapping_review import (  # noqa: E402
    SPEC,
    build_review,
    load_inputs,
    markdown,
    overview,
    triage,
    write_outputs,
)


@pytest.fixture(scope="module")
def inputs():
    spec = json.loads((ROOT / SPEC).read_text())
    return spec, load_inputs(ROOT, spec)


@pytest.fixture(scope="module")
def report(inputs):
    return build_review(ROOT, *inputs)


def select(report, wave, field, code):
    return next(r for r in report["code_rows"] if (r["survey_wave"], r["canonical_name"], r["source_code"]) ==
                (wave, field, code))


def test_unknown_tenure_zero_is_not_a_missingness_rule(report):
    row = select(report, "2021", "dwelling_tenure_source_code", "0")
    assert (row["raw_count"], row["current_published_code_count"]) == (1, 0)
    assert row["review_bucket"] == "blocked"
    assert row["missing_class"] == "unresolved"
    assert row["candidate_category"] is None


def test_correction_is_separate_from_categories_and_old_audit_is_retained(report, inputs):
    row = select(report, "2004", "main_lighting_source_code", "9")
    assert (row["baseline_published_code_count"], row["current_published_code_count"]) == (1, 0)
    assert row["review_bucket"] == "missing_only"
    assert row["correction_resolution"]["status"] == "corrected_to_null"
    assert row["effective_mapping_version"] == "cses-housing-lighting-missing-v1"
    assert select(inputs[1]["audit"], "2004", "main_lighting_source_code", "9")["local_published_code_count"] == 1
    other = select(report, "2021", "main_lighting_source_code", "9")
    assert other["candidate_category"] == "other"
    assert other["review_bucket"] == "manual_review"
    assert other["correction_resolution"] is None


def test_draft_skip_and_compound_categories_stay_manual(report):
    assert select(report, "2014", "dwelling_tenure_source_code", "3")["review_bucket"] == "manual_review"
    assert select(report, "2004", "dwelling_tenure_source_code", "1")["review_bucket"] == "manual_review"
    assert all(r["review_bucket"] == "manual_review" for r in report["code_rows"]
               if r["candidate_category"] in {"kerosene_or_diesel", "firewood_and_charcoal"})


def test_translation_and_conflicting_labels_never_become_candidates(report, inputs):
    assert select(report, "2021", "main_lighting_source_code", "8")["review_bucket"] == "blocked"
    row = {"missing_class": "substantive", "candidate_category": "other", "flags": ["source_label_option_conflict"]}
    assert triage(row, inputs[0])[0] == "blocked"


def test_category_keys_include_field_and_never_only_the_numeric_code(report):
    substantive = [r for r in report["code_rows"] if r["candidate_category"] is not None]
    assert all(r["category_key"] == f"{r['canonical_name']}:{r['candidate_category']}" for r in substantive)
    assert len({r["review_row_id"] for r in report["code_rows"]}) == 208
    assert all(r["source_key"]["archive_relative_path"] for r in report["code_rows"])


def test_coverage_accounts_for_all_current_cells_without_pooling_households(report):
    assert len(report["profiles"]) == 30
    assert all(sum(p["current_numeric_counts_by_bucket"].values()) + p["current_sql_null_count"] ==
               p["current_published_row_count"] for p in report["profiles"])
    assert all(not r["publication_ready"] and r["review_status"] == "proposed" for r in report["code_rows"])
    assert not report["publication_ready"] and not report["database_mutated"]
    assert any(r["raw_count"] == 0 for r in report["code_rows"])


def test_missing_codes_retain_kind_and_do_not_acquire_a_reason(report):
    missing = [r for r in report["code_rows"] if r["code_kind"] == "stata_missing"]
    assert len(missing) == 13
    assert all(r["review_bucket"] == "missing_only" and r["candidate_category"] is None for r in missing)
    assert all(r["current_published_code_count"] is None for r in missing)


def test_fingerprint_change_rejected_before_source_or_database_access(inputs):
    bad = copy.deepcopy(inputs[0])
    bad["evidence"]["audit"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Evidence fingerprint changed"):
        load_inputs(ROOT, bad)


def test_write_scope_is_rejected(inputs):
    bad = copy.deepcopy(inputs[0])
    bad["database_write_allowed"] = True
    with pytest.raises(ValueError, match="Review-only scope"):
        load_inputs(ROOT, bad)


def test_outputs_repeat_exactly_and_different_existing_evidence_is_never_replaced(tmp_path, report):
    write_outputs(tmp_path, report)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    write_outputs(tmp_path, report)
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    altered = copy.deepcopy(report)
    altered["summary"]["code_rows"] = 0
    with pytest.raises(ValueError, match="Existing review differs"):
        write_outputs(tmp_path, altered)
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert markdown(report) == markdown(report)
    assert overview(report) == overview(report)
