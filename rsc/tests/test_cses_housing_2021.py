"""The 2021 resolution preserves language conflict and never imputes tenure."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cses_db"))
import cses_housing_2021_evidence as evidence  # noqa: E402
import publish_cses_housing_2021 as publication  # noqa: E402


@pytest.fixture(scope="module")
def plan():
    return evidence.local_plan(Path(__file__).resolve().parents[2])


def test_only_lighting_eight_added(plan):
    assert len(plan["rows"]) == 1
    row = plan["rows"][0]
    assert (row["survey_wave"], row["source_variable"], row["source_code"], row["category"], row["observed_count"]) == (
        "2021", "q04_07", "8", "biogas", 6)
    assert row["source_label"] == "ជីវឧស្ម័ន"


def test_bilingual_conflict_is_retained(plan):
    questions = {s["language_code"]: s["questions"] for s in plan["evidence"]["sources"]}
    options = {lang: {o["code"]: o["label"] for o in next(q for q in qs if q["question_code"] == "q04_07")["options"]}
               for lang, qs in questions.items()}
    assert options["en"]["8"] == "Other (specify)"
    assert "9" not in options["en"]
    assert options["km"]["8"] == "ជីវឧស្ម័ន" and "9" in options["km"]
    assert plan["rows"][0]["evidence"]["conflict_cause"] == "not_established"
    assert plan["evidence"]["macros_executed"] is False


def test_tenure_zero_not_promoted(plan):
    anomaly = plan["tenure_anomaly"]
    assert anomaly["raw_code"] == 0 and anomaly["published_value"] is None
    assert anomaly["intended_response"] == "unknown"
    assert anomaly["source_row_id"] == "2021:S04_HHhousing.dta:6458"
    tenure = next(p for p in plan["coverage"] if p["field"] == "dwelling_tenure_source_code")
    assert tenure["nulls"] == 4 and tenure["nonnull"] == 10076


def test_four_questions_are_separate_by_language(plan):
    registry = publication.provenance_desired(plan)
    assert len(registry["instruments"]) == 2 and len(registry["questions"]) == 4
    assert {q["repeat_context"]["language_code"] for q in registry["questions"]} == {"en", "km"}
    assert all(q["repeat_context"]["source_sheet"] == "04 Housing_Revised-1" for q in registry["questions"])
    assert all(q["skip_instruction"] for q in registry["questions"] if q["question_code"] == "q04_28")
    assert all(not q["is_exact_question_text"] for q in registry["questions"])


def test_dictionary_is_additive(plan):
    dictionary, category = publication.view_queries(plan)
    assert "cses_housing_value_dictionary_v3 UNION ALL" in dictionary.as_string()
    assert "cses_housing_value_dictionary_v4" in category.as_string()
    assert "cses-housing-interface-v4" in category.as_string()
    assert "s.survey_wave=e.survey_wave" in dictionary.as_string()


def test_desired_record_keeps_original_khmer_label_and_anomaly(plan):
    prior = {"survey_wave": "2021", "canonical_name": "main_lighting_source_code", "dataset_id": 162,
             "canonical_variable_id": 181, "source_variable_names": ["q04_07"], "source_kind": "explicit",
             "transformation_rule": "Prior rule."}
    desired = publication.desired(plan, {"predecessors": [prior], "implementation_sha256": {}, "backup": []}, "hash")
    assert len(desired["mappings"]) == len(desired["values"]) == 1
    assert desired["values"][0]["source_label"] == "ជីវឧស្ម័ន"
    assert desired["run"]["validation_summary"]["tenure_anomaly"] == plan["tenure_anomaly"]
    assert desired["run"]["code_git_revision"] is None and desired["run"]["dvc_revision"] is None


@pytest.mark.parametrize("raw", ["1 = A\n1 = B", "not an option"])
def test_bad_options_rejected(raw):
    with pytest.raises(ValueError):
        evidence.options_from_cells({"A1": raw}, ["A1"])


def test_exact_link_targets():
    assert "'q04_07','q04_28'" in publication.LINK_TARGET_SQL
    assert "s.survey_wave='2021'" in publication.LINK_TARGET_SQL
    assert "S04_HHhousing.dta" in publication.LINK_TARGET_SQL
