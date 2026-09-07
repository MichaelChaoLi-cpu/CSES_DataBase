"""Question alignment preserves wave, language, locators and uncertainty."""

import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cses_db"))
from align_cses_questionnaires import audit_registered_questions, build, longest_candidates, matches  # noqa: E402
from organize_cses_questionnaires import (  # noqa: E402
    classify,
    compact_code,
    question_candidates,
    walk_archive,
    wave_from_path,
    write_once,
)

SOURCE = {"source_file": "source.zip::form.xlsx", "survey_wave": "2016", "instrument_type": "household_questionnaire",
          "language_code": "en", "documentation_status": "verified"}


def test_printed_local_question_gets_section_prefix():
    rows = question_candidates(SOURCE, {"04 Housing": {"A33": "Q7", "B33": "What is the main source of lighting?"}})
    assert rows[0]["normalized_code"] == "q0407"
    assert rows[0]["option_count"] is None and rows[0]["response_options"] is None
    assert rows[0]["is_exact_question_text"] is False


def test_column_marker_is_explicit_candidate_not_global_rewrite():
    rows = question_candidates(SOURCE, {"01 A_ Initial": {"O7": "Sex", "O11": "1 = Male\n2 = Female", "O19": "(3)"}})
    assert rows[0]["question_text_candidate"] == "Sex"
    assert rows[0]["source_code_candidates"] == ["q01a03", "q01ac03"]
    assert longest_candidates("q01ac03", rows) == rows
    assert not matches("q01ac03", "q01a03")
    assert rows[0]["context_cells"]["O11"] == "1 = Male\n2 = Female"


def test_birth_registration_prefers_question_but_keeps_heading():
    rows = question_candidates(SOURCE, {"01 A_ Initial": {"AA7": "Birth Registration", "AA10": "Does NAME have a birth certificate?", "AA19": "(5b)"}})
    assert rows[0]["text_cell_candidates"] == ["AA10", "AA7"]


def test_village_section_number_prevents_cross_section_match():
    source = {**SOURCE, "instrument_type": "village_questionnaire"}
    rows = question_candidates(source, {"Sections": {"A1": "1. DEMOGRAPHIC INFORMATION", "A3": "1", "B3": "How many people live here?",
                                                     "A29": "2. ECONOMY", "A31": "1", "B31": "How many roads are there?"}})
    assert [r["normalized_code"] for r in rows] == ["s1q1", "s2q1"]


def test_prefix_digit_boundary_and_longest_part():
    assert not matches("q04_070", "q0407")
    assert matches("Q04_22A", "q0422")
    pool = [{"candidate_id": "a", "normalized_code": "q0422"}, {"candidate_id": "b", "normalized_code": "q0422a"}]
    assert longest_candidates("q04_22a", pool) == [pool[1]]


def test_duplicate_question_occurrences_are_retained():
    rows = question_candidates(SOURCE, {"04 Housing": {"A1": "Q7", "B1": "What lighting?", "A10": "Q7", "B10": "What lighting?"}})
    assert len(rows) == 2 and rows[0]["candidate_id"] != rows[1]["candidate_id"]


def test_numeric_respondent_rows_are_not_questions():
    assert question_candidates(SOURCE, {"01 A_ Initial": {"A20": "01", "A21": "02", "A22": "03"}}) == []


def test_missing_original_locator_is_not_a_pass():
    registry = {"instruments": [{"instrument_id": 1, "source_file": "x"}], "questions": [
        {"question_id": 1, "instrument_id": 1, "question_code": "q1", "question_text": "Text", "repeat_context": {"source_sheet": "s", "question_text_cell": "B2"}}]}
    assert audit_registered_questions(registry, [])[0]["status"] == "source_locator_not_available"


def test_normalization_does_not_erase_numbers_or_parts():
    assert compact_code(" Q01A_C05b ") == "q01ac05b"
    assert wave_from_path("data/raw/CSES 2011-12.zip") == "2011-12"


def test_composite_locators_are_joined_in_recorded_order():
    registry = {"instruments": [{"instrument_id": 1, "source_file": "x"}], "questions": [
        {"question_id": 1, "instrument_id": 1, "question_code": "q1", "question_text": "If rented: How much?",
         "repeat_context": {"source_sheet": "s", "question_text_cell": "B2+B3"}}]}
    rows = audit_registered_questions(registry, [{"source_file": "x", "sheets": {"s": {"B2": "If rented:", "B3": "How much?"}}}])
    assert rows[0]["status"] == "normalized_cell_matches" and rows[0]["source_cells"] == ["B2", "B3"]


def test_files_remain_distinct_roles():
    assert classify("HH Diaries_V16.xls") == "household_diary"
    assert classify("CSES Report 2004.pdf") == "supporting_document"
    assert classify("Village2007.xls") == "village_questionnaire"


def test_nested_archives_preserve_chain_and_ignore_macos_noise(tmp_path):
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w") as z:
        z.writestr("form.xlsx", b"source")
        z.writestr("__MACOSX/._form.xlsx", b"noise")
    outer = tmp_path / "CSES2013.zip"
    with zipfile.ZipFile(outer, "w") as z:
        z.writestr("nested.zip", nested.getvalue())
    assert list(walk_archive(outer)) == [(("nested.zip", "form.xlsx"), b"source")]


def test_outputs_refuse_differing_overwrite(tmp_path):
    path = tmp_path / "result.json"
    write_once(path, {"a": 1})
    write_once(path, {"a": 1})
    with pytest.raises(ValueError, match="Refusing"):
        write_once(path, {"a": 2})


def minimal_inputs(wave="2016"):
    variable = {"source_variable_id": 1, "dataset_id": 1, "survey_wave": wave, "module_code": "household_members",
                "variable_name": "q01ac03", "variable_label": None, "question_id": None,
                "archive_relative_path": "source.zip", "member_path": "members.dta", "nested_member_path": None}
    instrument = {"instrument_id": 1, "source_file": SOURCE["source_file"], "survey_wave": "2016",
                  "instrument_type": "household_questionnaire", "language_code": "en"}
    canonical = {"canonical_variable_id": 1, "target_table": "final_HL_CSES", "canonical_name": "sex",
                 "canonical_definition": "Recorded sex", "analytical_grain": "person-wave"}
    mapping = {"dataset_id": 1, "canonical_variable_id": 1, "source_variable_names": ["q01ac03"],
               "mapping_version": "existing-v1", "source_kind": "explicit"}
    registry = {"instruments": [instrument], "questions": [], "source_variables": [variable],
                "canonical_variables": [canonical], "mappings": [mapping], "housing_dictionary": []}
    inventory = {"sources": [{**SOURCE, "registered_instrument_id": 1}],
                 "questions": question_candidates(SOURCE, {"01 A_ Initial": {"O7": "Sex", "O19": "(3)"}})}
    return registry, inventory


def test_candidates_do_not_become_published_links():
    registry, inventory = minimal_inputs()
    result = build(registry, inventory)
    assert result["new_mappings_published"] == 0
    assert result["source_links"][0]["status"] == "candidate_requires_review"
    assert result["source_links"][0]["semantic_equivalence_confirmed"] is False
    assert result["summary"]["canonical_field_wave_rows"] == 10


def test_no_transfer_of_unapproved_2017_member_question():
    registry, inventory = minimal_inputs("2017")
    result = build(registry, inventory)
    assert result["source_links"][0]["candidate_ids"] == []
    assert result["source_links"][0]["status"] == "no_extractable_selected_questionnaire"


def test_unregistered_alternate_is_not_silently_selected():
    registry, inventory = minimal_inputs()
    inventory["sources"][0]["registered_instrument_id"] = None
    assert build(registry, inventory)["source_links"][0]["candidate_ids"] == []


def test_different_prompts_for_same_code_remain_ambiguous():
    registry, inventory = minimal_inputs()
    inventory["questions"].append({**inventory["questions"][0], "candidate_id": "other", "question_text_candidate": "Different prompt"})
    assert build(registry, inventory)["source_links"][0]["status"] == "ambiguous_candidates_require_review"
