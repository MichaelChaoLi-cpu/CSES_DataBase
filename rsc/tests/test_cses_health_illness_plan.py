"""HEALTH table design separates source preservation, linkage and approval."""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cses_db"))
from plan_cses_health_illness import (  # noqa: E402
    canonical_keys,
    check_raw_roundtrip,
    evidence_status,
    link_keys,
    proposed_ddl,
    raw_json_records,
    source_keys,
)

SPEC = json.loads((Path(__file__).resolve().parents[1] / "specs/cses_health_illness_table_v1.json").read_text())


def test_spec_does_not_approve_or_create_an_analysis_table():
    assert SPEC["database_publication_authorized"] is False
    assert SPEC["target_schema"] == "cses_data"
    assert len(SPEC["columns"]) == 14
    assert sum(SPEC["expected_source_records"].values()) == 358859
    assert SPEC["foreign_keys"] == []
    assert next(c for c in SPEC["columns"] if c["name"] == "raw_record")["type"] == "jsonb"


def test_existing_minimum_id_widths_are_reused_without_truncation():
    keys = source_keys(pd.DataFrame({"HHID": [12345.0, 12345678.0], "PERSID": [1234501.0, 1234567801.0]}), "2004")
    assert keys.household_id.tolist() == ["012345", "12345678"]
    assert keys.person_id.tolist() == ["01234501", "1234567801"]


@pytest.mark.parametrize("bad", [None, "abc", -1, 2.5])
def test_invalid_ids_fail_without_silent_null_or_guess(bad):
    with pytest.raises(ValueError, match="Invalid"):
        source_keys(pd.DataFrame({"hhid": [bad], "persid": [101]}), "2017")


def test_normalization_collisions_fail():
    with pytest.raises(ValueError, match="Duplicate"):
        source_keys(pd.DataFrame({"hhid": ["1", "0000001"], "persid": ["101", "000000101"]}), "2017")


def test_duplicate_roster_person_is_not_arbitrarily_deduplicated():
    frame = pd.DataFrame({"Survey Wave": ["2017"] * 2, "Household ID": ["h1", "h2"], "Person ID": ["p", "p"]})
    with pytest.raises(ValueError, match="Ambiguous"):
        canonical_keys(frame, "hl")


def test_link_status_distinguishes_absence_conflict_and_household_missing():
    keys = pd.DataFrame(
        {"survey_wave": ["2017"] * 4, "household_id": ["h1", "h1", "h1", "h9"], "person_id": ["p1", "p2", "p3", "p4"]},
        dtype="string",
    )
    hh = pd.DataFrame({"survey_wave": ["2017"], "household_id": ["h1"]}, dtype="string")
    hl = pd.DataFrame(
        {"survey_wave": ["2017"] * 2, "household_id": ["h1", "h2"], "person_id": ["p1", "p2"]}, dtype="string"
    )
    result = link_keys(keys, hh, hl)
    assert result.person_id.tolist() == ["p1", "p2", "p3", "p4"]
    assert result.hl_link_status.tolist() == [
        "matched",
        "household_conflict",
        "person_not_in_roster",
        "person_not_in_roster",
    ]
    assert result.hh_link_matched.tolist() == [True, True, True, False]
    assert pd.isna(result.roster_household_id.iloc[2])
    assert len(result) == 4


def test_links_do_not_cross_waves():
    keys = pd.DataFrame({"survey_wave": ["2017"], "household_id": ["h1"], "person_id": ["p1"]}, dtype="string")
    hl = keys.assign(survey_wave="2016")
    result = link_keys(keys, hl[["survey_wave", "household_id"]], hl)
    assert result.hl_link_status.iloc[0] == "person_not_in_roster"
    assert not result.hh_link_matched.iloc[0]


def test_raw_case_sentinels_nulls_strings_and_float_precision_survive():
    native = pd.DataFrame(
        {
            "Q13BC02": [9.0, 98.0, 99.0, float("nan")],
            "weight": [1.2345678901234567, 9.876543210987654, 0.0, -0.1234567890123456],
            "label": ["", "001", "កម្ពុជា", 'quote " and \\'],
        }
    )
    records = raw_json_records(native)
    check_raw_roundtrip(native, records)
    assert json.loads(records.iloc[0])["Q13BC02"] == 9
    assert json.loads(records.iloc[3])["Q13BC02"] is None
    assert "q13bc02" not in json.loads(records.iloc[0])


def test_infinite_raw_value_is_not_silently_serialized_as_invalid_json():
    with pytest.raises(ValueError):
        raw_json_records(pd.DataFrame({"q": [float("inf")]}))


@pytest.mark.parametrize(
    ("sources", "expected"),
    [
        ([], "household_form_not_located"),
        ([{"instrument_type": "village_questionnaire"}], "household_form_not_located"),
        ([{"instrument_type": "forms_bundle"}], "image_bundle_not_transcribed"),
        (
            [
                {
                    "instrument_type": "household_questionnaire",
                    "language_code": "en",
                    "registered_instrument_id": 1,
                    "documentation_status": "provisional",
                }
            ],
            "draft_form_available",
        ),
        (
            [
                {
                    "instrument_type": "household_questionnaire",
                    "language_code": "en",
                    "registered_instrument_id": 1,
                    "documentation_status": "verified",
                }
            ],
            "form_available_unreviewed_for_health",
        ),
    ],
)
def test_form_availability_does_not_certify_health_questions(sources, expected):
    library = {"sources": [{**s, "survey_wave": "2017"} for s in sources]}
    assert evidence_status(library, "2017") == expected


def test_2016_form_is_not_transferred_to_2017():
    library = {
        "sources": [
            {
                "survey_wave": "2016",
                "instrument_type": "household_questionnaire",
                "language_code": "en",
                "registered_instrument_id": 1,
                "documentation_status": "verified",
            }
        ]
    }
    assert evidence_status(library, "2017") == "household_form_not_located"


def test_ddl_is_new_source_table_only_and_has_no_fk_or_replacement():
    ddl = proposed_ddl(SPEC)
    assert 'CREATE TABLE "cses_data"."cses_health_illness_source_v1"' in ddl
    assert 'PRIMARY KEY ("source_id", "source_row_number")' in ddl
    assert 'UNIQUE ("survey_wave", "household_id", "person_id")' in ddl
    assert "DROP " not in ddl and "REFERENCES " not in ddl and "OR REPLACE" not in ddl
    assert "DESIGN ONLY" in ddl and "native_codes_not_harmonized" in ddl
