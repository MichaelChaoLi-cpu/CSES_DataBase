"""Final EC batch: exact coverage, source evidence, independent recodes and qualified routes."""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
from organize_cses_questionnaires import digest  # noqa: E402
from review_cses_employment_remaining import (  # noqa: E402
    BINARY,
    FIELDS,
    METHODS,
    OUTPUT,
    PRIOR_FIELDS,
    SELF,
    coverage,
    document,
    evidence,
    field_document,
    locator,
    numeric,
    route,
    transform,
)


@pytest.fixture(scope="module")
def snapshot():
    path = ROOT / OUTPUT / "review.json"
    if not path.exists():
        pytest.skip("Review snapshot unavailable")
    return json.loads(path.read_text())


def sample(n=4):
    names = list(
        dict.fromkeys(
            FIELDS
            + [
                "age",
                "worked_at_least_one_hour_past_7_days",
                "second_work_screening_source_code",
                "actively_seeking_work",
                "main_employment_status_source_code",
                "secondary_employment_status_source_code",
            ]
        )
    )
    f = pd.DataFrame({k: pd.Series([pd.NA] * n, dtype="Int16") for k in names})
    f["age"] = 20
    f["worked_at_least_one_hour_past_7_days"] = pd.Series([1] * n, dtype="Int16")
    return f


def test_exact_39_field_union():
    assert len(coverage()) == 39
    assert len(FIELDS) == 19 and len(PRIOR_FIELDS) == 20
    assert not set(FIELDS) & set(PRIOR_FIELDS)


@pytest.mark.parametrize("field", sorted(BINARY))
def test_binary_polarity_invalid_and_null(field):
    raw = pd.Series([1, 2, 0, 3, 98, 99, None])
    pd.testing.assert_series_equal(
        transform(raw, field, raw.index), pd.Series([1, 0, pd.NA, pd.NA, pd.NA, pd.NA, pd.NA], dtype="Int8")
    )


def test_numeric_domains_are_not_questionnaire_choices():
    raw = pd.Series([0, 10, 11, 98, 99, 168, 169, -1, 1.5, None])
    assert transform(raw, FIELDS[0], raw.index).notna().tolist() == [True, True] + [False] * 8
    assert transform(raw, FIELDS[14], raw.index).notna().tolist() == [
        True,
        True,
        True,
        False,
        False,
        True,
        False,
        False,
        False,
        False,
    ]
    assert numeric(pd.Series([96, 97, 98, 99, 100]), 97, [98, 99]).notna().tolist() == [True, True, False, False, False]
    assert transform(pd.Series([9, 0]), METHODS[0], pd.RangeIndex(2)).tolist() == [9, 0]


def test_money_preserves_zero_and_fractional_amounts():
    raw = pd.Series([0, 1.5, -1, 9999999, 99999999, 999999999, None])
    value = transform(raw, FIELDS[4], raw.index)
    assert value.iloc[:2].tolist() == [0, 1.5] and value.iloc[2:].isna().all()


def test_secondary_year_and_seasonal_routes():
    f = sample()
    f[FIELDS[0]] = pd.Series([1, 0, 1, pd.NA], dtype="Int16")
    f[FIELDS[2]] = pd.Series([0, 0, 1, 0], dtype="Int16")
    assert route(f, "2016", FIELDS[2], {}).tolist() == [True, False, True, pd.NA]
    assert route(f, "2016", FIELDS[3], {}).tolist() == [True, False, False, pd.NA]


def test_reason_for_fewer_hours_does_not_require_available_yes():
    f = sample()
    f[FIELDS[5]] = pd.Series([2, 2, 1, 3], dtype="Int16")
    f[FIELDS[8]] = pd.Series([1, 0, 1, 1], dtype="Int16")
    assert route(f, "2021", FIELDS[9], {}).tolist() == [True, True, False, False]
    assert route(f, "2021", FIELDS[10], {}).tolist() == [True, False, False, False]


def test_salary_either_job_employee_and_work_screen():
    f = sample()
    f["main_employment_status_source_code"] = pd.Series([1, 3, 3, 1], dtype="Int16")
    f["secondary_employment_status_source_code"] = pd.Series([3, 1, 3, 1], dtype="Int16")
    f.loc[3, "worked_at_least_one_hour_past_7_days"] = 0
    f.loc[3, "second_work_screening_source_code"] = 2
    assert route(f, "2009", FIELDS[4], {}).tolist() == [True, True, False, False]


def test_nonseeking_reason_skip_and_latest_duration_threshold():
    f = sample(5)
    f["worked_at_least_one_hour_past_7_days"] = 0
    f["second_work_screening_source_code"] = 2
    f["actively_seeking_work"] = 0
    f[FIELDS[16]] = pd.Series([1, 6, 9, 1, 0], dtype="Int16")
    f[FIELDS[17]] = pd.Series([12, 1, 13, 0, 1], dtype="Int16")
    assert route(f, "2016", FIELDS[18], {}).tolist() == [True, False, False, True, pd.NA]
    f["actively_seeking_work"] = 1
    assert not route(f, "2016", FIELDS[17], {}).fillna(False).any()


def test_2004_desired_hours_has_broader_route():
    f = sample()
    f["worked_at_least_one_hour_past_7_days"] = pd.Series([1, 1, 0, 0], dtype="Int16")
    f["second_work_screening_source_code"] = pd.Series([pd.NA, pd.NA, 2, 2], dtype="Int16")
    f["actively_seeking_work"] = pd.Series([pd.NA, pd.NA, 1, 0], dtype="Int16")
    assert route(f, "2004", FIELDS[14], {"q13a06": pd.Series([2, 1, None, None])}).tolist() == [True, False, True, True]
    assert route(f, "2016", FIELDS[14], {}).fillna(False).tolist() == [False, False, True, False]


@pytest.mark.parametrize("wave", ["2007", "2017", "2019"])
def test_missing_form_routes_not_borrowed(wave):
    for field in FIELDS:
        assert route(pd.DataFrame(), wave, field, {}) is None


def test_earlier_missing_aliases_not_fabricated():
    assert locator("2009", 6) is None and locator("2009", 10) is None and locator("2009", 15) is None
    assert locator("2004", 4) is None


def test_question_evidence_shared_slots_and_secondary_naming(snapshot):
    q, _, related = evidence(ROOT)
    assert q == snapshot["questions"] and len(q) == 111 and len(related) == 9
    slots = [r for r in q if r["field"] in METHODS]
    assert len(slots) == 21
    assert len({(r["survey_wave"], r["candidate_id"]) for r in slots}) == 7
    for r in q:
        if r["field"] == FIELDS[3]:
            assert any("seasonal?" in t for t in r["literal_cells"].values())
            assert any("17b = 2" in t for t in r["literal_cells"].values())
    for r in q:
        if r["survey_wave"] == "2021" and r["field"] in [FIELDS[10], FIELDS[15]]:
            assert any("98" in t and "know" in t for t in r["literal_cells"].values())


def test_190_profiles_and_all_source_reproductions(snapshot):
    c = snapshot["scope_counts"]
    assert (c["batch_fields"], c["cumulative_reviewed_ec_fields"], c["remaining_ec_fields"]) == (19, 39, 0)
    assert len(snapshot["profiles"]) == 190 and c["source_field_wave_mappings"] == 154
    for p in snapshot["profiles"]:
        assert p["raw_to_canonical_equal"] and p["nonnull"] + p["null"] == p["rows"]
        if p["route_assessed"]:
            assert p["nonnull"] == sum(
                p[k] for k in ["nonnull_inside_route", "nonnull_outside_route", "nonnull_route_unknown"]
            )
        if not p["derived"]:
            assert (
                p["raw_nonnull"]
                == p["nonnull"] + sum(p["cleaner_exclusions"].values()) + p["secondary_count_suppressed"]
            )
        if p["field"] in BINARY:
            assert not p["stored_outside_documented_options"]


def test_exact_special_codes_and_suppression(snapshot):
    p = {(p["survey_wave"], p["field"]): p for p in snapshot["profiles"]}
    assert p["2004", FIELDS[1]]["labelled_special_codes"]["9"]["stored_count"] == 244
    assert p["2004", METHODS[0]]["stored_outside_documented_options"] == {"9": 4}
    assert p["2004", METHODS[1]]["stored_outside_documented_options"] == {"0": 293}
    assert p["2004", METHODS[2]]["stored_outside_documented_options"] == {"0": 105}
    assert p["2019", FIELDS[16]]["stored_outside_documented_options"] == {"0": 2}
    assert p["2021", FIELDS[2]]["secondary_count_suppressed"] == 11
    assert p["2021", FIELDS[3]]["secondary_count_suppressed"] == 3
    assert sum(sum(v["cleaner_exclusions"].values()) for v in p.values()) == 661


def test_supplemental_calendar_years_not_converted(snapshot):
    s = snapshot["supplemental_raw_columns"]
    assert len(s) == 15 and all(not r["used_to_fill_canonical"] for r in s)
    for col in ["q15_c25b", "q15_c30b"]:
        r = next(r for r in s if r["survey_wave"] == "2009" and r["source_variable"] == col)
        assert any(float(k) >= 1900 for k in r["raw_values"])
    old = next(r for r in s if r["survey_wave"] == "2004" and r["source_variable"] == "q13a06")
    assert old["fresh_stata_metadata"]["value_labels"] == {"1": "same", "2": "less", "3": "more", "9": "missing"}


def test_live_database_and_frozen_outputs(snapshot):
    db = snapshot["database_check"]
    assert db["transaction_read_only"] and db["all_selected_cells_equal"]
    assert len(db["columns"]) == 35 and len(db["relations"]) == 2 and db["rows_per_relation"] == 332903
    assert not db["full_relation_validation"]
    for flag in [
        "database_mutated",
        "canonical_data_mutated",
        "new_question_links_published",
        "individual_records_saved",
        "corrections_published",
    ]:
        assert not snapshot[flag]
    assert digest((ROOT / SELF).read_bytes()) == snapshot["implementation_sha256"]
    for name, sha in snapshot["frozen_inputs"].items():
        assert digest((ROOT / name).read_bytes()) == sha
    assert all(v["all_sheets_equal"] for v in snapshot["source_verification"]["sources"])


def test_docs_reproducible(snapshot):
    assert document(snapshot) == (ROOT / "docs/cses-employment-remaining-review.md").read_text()
    assert field_document(snapshot) == (ROOT / "docs/cses-employment-remaining-field-waves.md").read_text()
