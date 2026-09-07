"""EC hours/status review must preserve numeric meaning, source rows and release boundaries."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
from cses_archive_source_policy import archive_source_policy  # noqa: E402
from review_cses_employment_hours_status import (  # noqa: E402
    FIELDS,
    STATUS,
    clean_numeric,
    data_review,
    evidence,
    literal_route,
)


@pytest.fixture(scope="module")
def located():
    if not (ROOT / "data/processing/cses/questionnaire_alignment_v1/source_cells.json").exists():
        pytest.skip("Frozen questionnaire evidence is not available")
    return evidence(ROOT)


def test_seven_fields_49_links_46_distinct_printed_items(located):
    questions, universes = located
    assert len(FIELDS) == 7 and len(questions) == 49 and len(universes) == 7
    assert len({q['candidate_id'] for q in questions}) == 46
    assert not any(q['whole_variable_certified'] or q['publication_approved'] for q in questions)


def test_numeric_entries_are_not_fixed_choice_questions(located):
    for q in located[0]:
        assert q['option_count'] == (5 if q['field'] in STATUS else None)
        if q['field'] in STATUS:
            assert {o['source_code'] for o in q['options']} == {1, 2, 3, 4, 5}
        else:
            assert q['options'] == []


def test_2004_main_secondary_share_printed_item_not_source_identity(located):
    rows = [q for q in located[0] if q['survey_wave'] == '2004']
    for first, second in [(1, 2), (3, 4), (5, 6)]:
        assert rows[first]['candidate_id'] == rows[second]['candidate_id']
        assert rows[first]['source_variable'].endswith('_1')
        assert rows[second]['source_variable'].endswith('_2')
        assert rows[first]['source_variable_id'] != rows[second]['source_variable_id']


def test_2009_omitted_alias_is_explicit_candidate_only(located):
    q = next(q for q in located[0] if q['canonical_mapping_missing'])
    assert q['survey_wave'] == '2009' and q['field'] == FIELDS[4]
    assert q['source_variable'] == 'q15_c17' and q['source_variable_id'] == 989
    assert q['original_candidate_ids'] == []
    assert q['question_code_cell'] == 'G16' and q['unit_or_options_cell'] == 'G15'


def test_2009_prefix_mismatch_does_not_rewrite_old_links(located):
    assert all(q['original_candidate_ids'] == [] for q in located[0] if q['survey_wave'] == '2009')


def test_draft_and_three_missing_form_routes_not_promoted(located):
    assert all(q['documentation_status'] == 'provisional' for q in located[0] if q['survey_wave'] == '2014')
    assert not {'2007', '2017', '2019'} & {q['survey_wave'] for q in located[0]}


def sample():
    return pd.DataFrame({
        'age': pd.Series([20, 20, 20, 20, 3, pd.NA], dtype='Int16'),
        'worked_at_least_one_hour_past_7_days': pd.Series([1, 0, 1, 0, 1, 1], dtype='Int8'),
        'second_work_screening_source_code': pd.Series([pd.NA, 1, pd.NA, 2, pd.NA, pd.NA], dtype='Int8'),
        'additional_jobs_count': pd.Series([0, 1, 1, 0, 1, 1], dtype='Int16'),
        'total_occupations_past_7_days': pd.Series([1, 2, 2, 0, 2, 2], dtype='Int16')})


def test_2021_main_hours_and_days_include_second_screen_yes():
    for field in [FIELDS[1], FIELDS[3]]:
        assert not literal_route(sample(), field, '2016').iloc[1]
        assert literal_route(sample(), field, '2021').iloc[1]


def test_total_hours_question_bypassed_by_zero_additional_jobs():
    assert not literal_route(sample(), FIELDS[0], '2009').iloc[0]
    assert literal_route(sample(), FIELDS[0], '2004').iloc[0]
    assert literal_route(sample(), FIELDS[0], '2021').iloc[2]


def test_2004_secondary_route_requires_two_occupations():
    assert not literal_route(sample(), FIELDS[2], '2004').iloc[0]
    assert literal_route(sample(), FIELDS[2], '2004').iloc[1]


def test_unknown_age_and_missing_forms_remain_unknown():
    assert pd.isna(literal_route(sample(), FIELDS[1], '2021').iloc[-1])
    for wave in ['2007', '2017', '2019']:
        assert literal_route(sample(), FIELDS[1], wave) is None


def test_cleaner_reproduces_old_rule_without_certifying_sentinels():
    raw = pd.Series([0, 96, 98, 99, 168, 169, -1, 3.5, pd.NA])
    assert clean_numeric(raw, 168, (98, 99)).tolist() == [0, 96, pd.NA, pd.NA, 168, pd.NA, pd.NA, pd.NA, pd.NA]
    assert clean_numeric(pd.Series([1, 5, 9, 99]), 9999).tolist() == [1, 5, 9, 99]


@pytest.fixture(scope="module")
def reproduced(located):
    if not (ROOT / 'data/processing/cses/final_EC_CSES.parquet').exists():
        pytest.skip('DVC-owned EC data unavailable')
    with archive_source_policy():
        return data_review(ROOT, located[0])


def test_all_70_profiles_reproduce_frozen_baseline(reproduced):
    frame, profiles, sources, _, _ = reproduced
    assert frame.shape == (332903, 60) and len(profiles) == 70
    assert sum(p['source_variable'] is not None for p in profiles) == 63
    assert all(f['raw_to_canonical_equal'] for s in sources for f in s['fields'])
    assert all(p['nonnull'] + p['null'] == p['rows'] for p in profiles)
    assert all(p['non_null_raw_before_cleaning'] - p['discarded_by_numeric_cleaner'] - p['suppressed_by_job_count'] == p['nonnull'] for p in profiles)


def test_2009_recovery_does_not_fill_original(reproduced):
    frame, _, _, _, candidate = reproduced
    assert candidate['raw_nonnull'] == candidate['candidate_nonnull_after_existing_cleaning_and_secondary_gate'] == 13830
    assert candidate['secondary_suppressed'] == 0 and candidate['proposed_only']
    assert frame.loc[frame.survey_wave.eq('2009'), FIELDS[4]].isna().all()


def test_2004_missing_status_codes_and_total_hours_topcode(reproduced):
    _, profiles, sources, diagnostics, _ = reproduced
    statuses = [p for p in profiles if p['survey_wave'] == '2004' and p['field'] in STATUS]
    assert [p['retained_labelled_missing']['9'] for p in statuses] == [185, 71]
    assert next(w['total_hours_2004_96_plus'] for w in diagnostics if w['survey_wave'] == '2004') == 6
    field = next(f for s in sources if s['survey_wave'] == '2004' for f in s['fields'] if f['field'] == FIELDS[0])
    assert field['fresh_stata_metadata']['value_labels']['96'] == '96 and more hours'


def test_2019_status_labels_not_misrepresented_as_form_routes(reproduced):
    rows = [p for p in reproduced[1] if p['survey_wave'] == '2019' and p['field'] in STATUS]
    assert all(p['option_count'] == 5 and p['option_basis'] == 'embedded_stata_labels' and p['literal_route_records'] is None for p in rows)


def test_hours_reconciliation_counts_and_exclusion(reproduced):
    counts = {w['survey_wave']: w for w in reproduced[3]}
    assert counts['2004']['three_hour_fields_nonnull'] == 7492
    assert counts['2004']['exact_hour_comparison_excludes_topcode'] == 7491
    assert {w: p['total_less_than_main_plus_secondary'] for w, p in counts.items() if p['total_less_than_main_plus_secondary']} == {'2004': 1798, '2019': 310, '2021': 304}
