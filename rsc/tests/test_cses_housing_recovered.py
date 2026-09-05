"""Recovered evidence is wave-specific, source-preserving and narrowly published."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cses_db"))
import extract_cses_housing_recovered_evidence as evidence  # noqa: E402
import publish_cses_housing_recovered as recovery  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def plan():
    return recovery.local_plan(ROOT)


def test_options_preserve_original_skip_and_cell():
    raw = "7 = None/don’t cook (>> Q23)\n8 = Other (Specify) (>> Q23)"
    rows = evidence.parse_options({"O124": raw}, ["O124"])
    assert rows[0]["label"] == "None/don't cook"
    assert rows[0]["raw_text"] == raw.splitlines()[0]
    assert rows[0]["source_cell"] == "O124"
    assert rows[0]["skip_instructions"] == ["(>> Q23)"]
    assert rows[1]["label"] == "Other"


@pytest.mark.parametrize("raw", ["1 = Owned\n1 = Rented", "Unnumbered option"])
def test_reject_duplicate_or_unparsed_options(raw):
    with pytest.raises(ValueError):
        evidence.parse_options({"A1": raw}, ["A1"])


def test_meaning_comparison_rejects_same_code_different_label():
    with pytest.raises(ValueError, match="meanings"):
        evidence.check_options([{"code": "7", "label": "Other"}], {"7": "Solar"})


def test_scope_and_raw_counts(plan):
    assert len(plan["rows"]) == 39
    assert {r["survey_wave"] for r in plan["rows"]} == {"2007", "2013"}
    assert sum(r["observed_count"] > 0 for r in plan["rows"]) == 34
    assert sum(r["observed_count"] for r in plan["rows"]) == 22289
    assert sum(p["nulls"] for p in plan["coverage"]) == 10
    assert len(plan["coverage"]) == 6
    assert all(r["source_label"] is None for r in plan["rows"])


def test_lighting_seven_is_wave_specific(plan):
    rows = {(r["survey_wave"], r["source_code"]): r for r in plan["rows"] if r["field"] == "main_lighting_source_code"}
    assert rows["2007", "7"]["category"] == "other"
    assert rows["2013", "7"]["category"] == "solar"
    assert rows["2013", "8"]["category"] == "other"
    assert ("2007", "8") not in rows


def test_instruments_are_not_fabricated_questions(plan):
    registry = recovery.provenance_desired(plan)
    assert len(registry["instruments"]) == 4
    assert sum(i["instrument_type"] == "code_lookup" for i in registry["instruments"]) == 3
    assert len(registry["questions"]) == 3
    assert {q["question_code"] for q in registry["questions"]} == {"q04_07", "q04_22a", "q04_24"}
    assert all("2013" in q["source_file"] and not q["is_exact_question_text"] for q in registry["questions"])
    workbook = next(s for s in plan["evidence"]["sources"] if s["survey_wave"] == "2013")
    assert len(workbook["sheet_names"]) == 24
    assert len(workbook["member_chain"]) == 2 and workbook["source_file"].endswith(".xls")
    assert sorted(len(q["response_options"]) for q in registry["questions"]) == [4, 8, 8]


def test_same_canonical_field_does_not_cross_join_waves(plan):
    predecessors = [{"survey_wave": wave, "canonical_name": field, "dataset_id": i + 1,
        "canonical_variable_id": j + 1, "source_variable_names": ["Q"], "source_kind": "explicit",
        "transformation_rule": "Original."} for i, wave in enumerate(("2007", "2013"))
        for j, field in enumerate(recovery.FIELDS.values())]
    manifest = {"predecessors": predecessors, "implementation_sha256": {}, "backup": []}
    result = recovery.desired(plan, manifest, "execution")
    assert len(result["mappings"]) == 6 and len(result["values"]) == 39
    assert sum(r["dataset_id"] == 1 for r in result["values"]) == 19
    assert sum(r["dataset_id"] == 2 for r in result["values"]) == 20
    assert result["run"]["code_git_revision"] is None
    assert result["run"]["dvc_revision"] is None


def test_v3_is_additive_and_sql_matches_wave_and_source(plan):
    dictionary, category = recovery.view_queries(plan)
    assert "cses_housing_value_dictionary_v2 UNION ALL" in dictionary.as_string()
    assert "s.survey_wave=e.survey_wave" in dictionary.as_string()
    assert "cses_housing_value_dictionary_v3" in category.as_string()
    assert "cses-housing-interface-v3" in category.as_string()
    assert "source_submodule" in category.as_string()
    assert "cses_alignment.cses_source_variable" in recovery.LINK_TARGET_SQL
    assert "HHHousing.dta" in recovery.LINK_TARGET_SQL
    assert "'2013'" in recovery.LINK_TARGET_SQL
