"""Bounded, local review cannot promote heuristic matches into bulk publication."""

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
from review_cses_questionnaires import (  # noqa: E402
    MEMBER_LAYOUT,
    SPEC,
    TARGETS,
    age_impact,
    checked_inputs,
    evidence,
    parse_options,
    resolve_queue,
    review_members,
)


@pytest.fixture(scope="module")
def baseline():
    path = ROOT / "data/processing/cses/questionnaire_alignment_v1"
    if not (path / "alignment.json").exists():
        pytest.skip("Frozen DVC questionnaire evidence not present")
    spec = json.loads((ROOT / SPEC).read_text())
    return (spec, *[json.loads((path / name).read_text()) for name in
                   ("alignment.json", "source_inventory.json", "source_cells.json")])


def test_continuation_options_are_not_truncated():
    options = parse_options({"AD7": "01 = Head\n02 = Son/\n Daughter\n", "AH7": "10 = Son/\n Daughter-in-law\n15 = Other"})
    assert [r["source_code"] for r in options] == [1, 2, 10, 15]
    assert options[1]["label_as_printed"] == "Son/\n Daughter"
    assert options[2]["source_cell"] == "AH7"


def test_duplicate_option_code_rejected():
    with pytest.raises(ValueError, match="Duplicate option"):
        parse_options({"A1": "1=Head", "B1": "1=Different"})


def test_missing_required_source_cell_fails_closed():
    with pytest.raises(ValueError, match="Missing required cell"):
        evidence({"s": {"A1": "Head"}}, "s", ["A1", "B1"])


def test_exact_16_resolution_roles_and_no_publication(baseline):
    before = copy.deepcopy(baseline)
    rows = resolve_queue(*baseline)
    assert {r["source_variable_id"] for r in rows} == TARGETS
    assert sum(r["role"] == "interview_question" for r in rows) == 9
    assert sum(r["role"] == "repeat_identifier" for r in rows) == 7
    assert all(not r["database_publication_approved"] for r in rows)
    assert all(not r["whole_variable_harmonization_certified"] for r in rows)
    assert baseline == before


def test_identifier_keeps_all_32_header_occurrences_not_questions(baseline):
    rows = [r for r in resolve_queue(*baseline) if r["role"] == "repeat_identifier"]
    assert sum(len(r["candidate_decisions"]) for r in rows) == 32
    assert all(r["selected_candidate_id"] is None for r in rows)
    assert all(r["publication_class"] == "qualified_metadata_only" for r in rows)
    assert rows[0]["candidate_decisions"][0]["evidence_cells"]["B10"].strip() == "PLOT      NUMBER"


def test_2014_identifier_remains_draft(baseline):
    row = next(r for r in resolve_queue(*baseline) if r["source_variable_id"] == 1611)
    assert row["documentation_status"] == "provisional" and row["qualifications"]


def test_2013_nested_data_chain_preserved(baseline):
    row = next(r for r in resolve_queue(*baseline) if r["source_variable_id"] == 1857)
    assert row["data_source"]["nested_member_path"]
    assert row["source_file"].count("::") == 2
    assert row["code_cell"] == "A6" and row["text_cell"] == "B6"


def test_every_old_candidate_gets_one_decision(baseline):
    for row in resolve_queue(*baseline):
        assert sorted(row["original_candidate_ids"]) == sorted(r["candidate_id"] for r in row["candidate_decisions"])


def test_resolution_cannot_silently_shrink_queue(baseline):
    spec, *rest = copy.deepcopy(baseline)
    spec["question_resolutions"].pop()
    with pytest.raises(ValueError, match="exactly the 16"):
        resolve_queue(spec, *rest)


def test_identifier_cannot_drop_a_repeated_panel(baseline):
    spec, *rest = copy.deepcopy(baseline)
    spec["identifier_resolutions"][0]["occurrences"].pop()
    with pytest.raises(ValueError, match="every repeated candidate"):
        resolve_queue(spec, *rest)


def test_bad_question_locator_rejected(baseline):
    spec, *rest = copy.deepcopy(baseline)
    spec["question_resolutions"][0]["code_cell"] = "Z999"
    with pytest.raises(ValueError, match="not unique"):
        resolve_queue(spec, *rest)


def test_28_member_records_and_three_unborrowed_gaps(baseline):
    _, alignment, inventory, cells = baseline
    rows, foundations, gaps = review_members(alignment, inventory, cells)
    assert len(rows) == 28 and len(foundations) == 7
    assert {r["survey_wave"] for r in gaps} == {"2007", "2017", "2019"}
    assert all(r["publication_class"] == "insufficient_evidence" for r in gaps)
    assert all(not r["database_publication_approved"] for r in rows + foundations + gaps)


def test_complete_relationship_options_and_literal_notes(baseline):
    _, *args = baseline
    _, foundations, _ = review_members(*args)
    for row in foundations:
        assert [o["source_code"] for o in row["relationship_options"]] == list(range(1, 16))
        assert len({o["source_cell"] for o in row["relationship_options"]}) == 2
    assert {r["survey_wave"] for r in foundations if r["relationship_note"]} == {"2011-12", "2013", "2014", "2016"}


def test_age_is_numeric_with_wave_specific_topcode_and_missing_notes(baseline):
    _, *args = baseline
    rows, _, _ = review_members(*args)
    ages = {r["survey_wave"]: r for r in rows if r["canonical_name"] == "age"}
    assert all(r["option_count"] is None for r in ages.values())
    assert ages["2004"]["top_code"] == {"value": 96, "meaning": "96 years or older"}
    assert ages["2004"]["unknown_age_marker"] == "98"
    assert ages["2016"]["unknown_age_marker"] == "-"
    assert ages["2021"]["unknown_age_marker"] is None


def test_marital_scope_does_not_become_roster_age_cutoff(baseline):
    _, *args = baseline
    _, foundations, _ = review_members(*args)
    for row in foundations:
        assert row["marital_and_spouse_minimum_age"] == (15 if row["survey_wave"] == "2004" else 13)
        assert "no separate age minimum" in row["four_core_fields_age_eligibility"]
        assert row["marital_age_header_merge"] == MEMBER_LAYOUT[row["survey_wave"]]["marital_merge"]


def test_absence_polarity_and_reference_period_not_erased(baseline):
    _, *args = baseline
    rows, foundations, _ = review_members(*args)
    absence = {r["survey_wave"]: r for r in rows if r["canonical_name"] == "absent_from_household"}
    assert absence["2004"]["canonical_absent_mapping"] == {"1": 1, "2": 0}
    assert absence["2016"]["canonical_absent_mapping"] == {"1": 0, "2": 1}
    assert absence["2004"]["reference_period"] != absence["2016"]["reference_period"]
    assert "No answer-specific jump" in foundations[0]["absence_routing_rule"]
    assert "question 15" in foundations[-1]["absence_routing_rule"]


def test_2014_member_records_cannot_be_ready(baseline):
    _, *args = baseline
    rows, _, _ = review_members(*args)
    assert all(r["publication_class"] == "qualified_metadata_only" for r in rows if r["survey_wave"] == "2014")
    assert sum(r["publication_class"] == "ready_for_question_link_plan" for r in rows) == 6


def test_review_cannot_be_used_as_publication_authority(baseline):
    spec = copy.deepcopy(baseline[0])
    spec["publication_authorized"] = True
    with pytest.raises(ValueError, match="local only"):
        checked_inputs(ROOT, spec)


def test_baseline_hash_drift_fails_closed(baseline):
    spec = copy.deepcopy(baseline[0])
    spec["input_sha256"]["registry.json"] = "0" * 64
    with pytest.raises(ValueError, match="Accepted baseline changed"):
        checked_inputs(ROOT, spec)


def test_actual_age_topcode_impact_is_aggregate_only(baseline):
    if not (ROOT / "data/processing/cses/final_HL_CSES.parquet").exists():
        pytest.skip("Canonical DVC data not present")
    result = age_impact(ROOT)
    assert result["source_code_counts"] == {"96": 3, "98": 0, "99": 1}
    assert result["raw_topcoded_heads"] == 0
    assert [r["age_96_rows"] for r in result["tables"]] == [3, 3, 3, 0]
    assert not result["data_modified"] and not result["database_mutated"]
    assert "Person ID" not in json.dumps(result)
