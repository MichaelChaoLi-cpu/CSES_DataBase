"""The question batch never converts identifiers or draft sex entries into questions."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
from plan_cses_questionnaire_batch import QUESTION_IDS, SEX_IDS, build  # noqa: E402


@pytest.fixture(scope="module")
def plan():
    if not (ROOT / "data/processing/cses/questionnaire_review_v1/review.json").exists():
        pytest.skip("Accepted DVC evidence not available")
    return build(ROOT)


def test_exact_15_links_without_semantic_approval(plan):
    assert {r["source_variable_id"] for r in plan["questions_and_links"]} == QUESTION_IDS | SEX_IDS
    assert len(plan["questions_and_links"]) == 15
    assert not plan["database_mutated"] and not plan["publication_approved"]


def test_identifiers_keep_32_occurrences_and_2014_draft(plan):
    rows = plan["identifier_provenance"]
    assert len(rows) == 7 and sum(len(r["candidate_decisions"]) for r in rows) == 32
    assert next(r for r in rows if r["survey_wave"] == "2014")["documentation_status"] == "provisional"
    assert not ({r["source_variable_id"] for r in rows} & (QUESTION_IDS | SEX_IDS))


def test_six_sex_forms_only_and_no_borrowing(plan):
    rows = [r for r in plan["questions_and_links"] if r["source_variable_id"] in SEX_IDS]
    assert {r["survey_wave"] for r in rows} == {"2004", "2009", "2011-12", "2013", "2016", "2021"}
    assert all(set(r["question"]["response_options"]) == {"1", "2"} for r in rows)


def test_nine_questions_do_not_imply_complete_option_transcription(plan):
    rows = [r for r in plan["questions_and_links"] if r["source_variable_id"] in QUESTION_IDS]
    assert all(r["question"]["response_options"] is None for r in rows)
    assert all(r["question"]["is_exact_question_text"] for r in rows)


def test_original_status_not_promoted_to_mapping_approval(plan):
    assert all(set(r["link_update"]) == {"question_link_status", "question_link_role"} for r in plan["questions_and_links"])
    assert plan["proposed_counts"]["physical_data_changes"] == 0
    assert plan["proposed_counts"]["constraint_changes"] == 0
