"""Classification audit preserves raw codes, missingness and publication boundaries."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
from organize_cses_questionnaires import digest  # noqa: E402
from review_cses_employment_classification import (  # noqa: E402
    EMPLOYER,
    FIELDS,
    OUTPUT,
    PINS,
    SELF,
    classification,
    documents,
    evidence,
    literal_route,
    special_labels,
    width_for,
)


@pytest.fixture(scope="module")
def located():
    if not (ROOT / "data/processing/cses/questionnaire_alignment_v1/source_cells.json").exists():
        pytest.skip("Local questionnaire evidence unavailable")
    return evidence(ROOT)


@pytest.fixture(scope="module")
def snapshot():
    path = ROOT / OUTPUT / "review.json"
    if not path.exists():
        pytest.skip("Local classification snapshot unavailable")
    return json.loads(path.read_text())


def test_six_fields_42_correspondences_39_items(located):
    qs, us = located
    assert len(FIELDS) == 6 and len(qs) == 42 and len(us) == 7
    assert len({q['candidate_id'] for q in qs}) == 39
    assert not any(q['whole_variable_certified'] for q in qs)


def test_classification_is_coded_description_not_fixed_choices(located):
    for q in located[0]:
        if q['field'] in EMPLOYER:
            assert q['option_count'] == (10 if q['survey_wave'] == '2004' else 8)
        else:
            assert q['option_count'] is None and q['options'] == []
            assert q['question_text_cell'] != q['detail_cell']


def test_2004_repeated_rows_keep_distinct_source_ids(located):
    qs = [q for q in located[0] if q['survey_wave'] == '2004']
    for left, right in zip(qs[:3], qs[3:], strict=True):
        assert left['candidate_id'] == right['candidate_id']
        assert left['source_variable_id'] != right['source_variable_id']
        assert left['source_variable'].endswith('1') and right['source_variable'].endswith('2')


def test_2009_prefix_and_missing_forms_not_silently_borrowed(located):
    assert all(q['original_candidate_ids'] == [] for q in located[0] if q['survey_wave'] == '2009')
    assert not {'2007','2017','2019'} & {q['survey_wave'] for q in located[0]}
    assert all(q['documentation_status'] == 'provisional' for q in located[0] if q['survey_wave'] == '2014')


def test_same_employer_code_has_changed_meaning(located):
    qs = [q for q in located[0] if q['field'] == FIELDS[2]]
    old = next(q for q in qs if q['survey_wave'] == '2004')
    new = next(q for q in qs if q['survey_wave'] == '2021')
    assert 'farm' in old['options'][6]['label_as_printed']
    assert 'Embassies' in new['options'][6]['label_as_printed']


def test_formatter_preserves_leading_zero_and_long_codes():
    raw = pd.Series(['11','011','1111',' 1.00 ', '99','999','0','-1','1.5','abc',None])
    expected = pd.Series(['011','011','1111','001','099','999','000',pd.NA,pd.NA,pd.NA,pd.NA], dtype='string')
    pd.testing.assert_series_equal(classification(raw, 3), expected)
    assert classification(pd.Series(['99']), 2).iloc[0] == '99'
    assert classification(pd.Series(['99']), 4).iloc[0] == '0099'


def test_width_is_not_revision_or_universal_missing_rule():
    assert width_for(FIELDS[1], '2004') == 2
    assert width_for(FIELDS[1], '2009') == 4
    assert special_labels({'999':'Occupation not stated','99':'missing','9':'Other'}) == {'999':'Occupation not stated','99':'missing'}
    assert special_labels({'999':'valid named category'}) == {}


def sample():
    return pd.DataFrame({
        'age': pd.Series([20,20,20,3,pd.NA], dtype='Int16'),
        'worked_at_least_one_hour_past_7_days': pd.Series([1,0,0,1,1], dtype='Int8'),
        'second_work_screening_source_code': pd.Series([pd.NA,1,2,pd.NA,pd.NA], dtype='Int8'),
        'additional_jobs_count': pd.Series([0,1,0,1,1], dtype='Int16'),
        'total_occupations_past_7_days': pd.Series([1,2,0,2,2], dtype='Int16')})


def test_main_details_include_second_screen_yes_not_hours_gate():
    assert literal_route(sample(), FIELDS[0], '2016').iloc[1]
    assert not literal_route(sample(), FIELDS[3], '2016').iloc[0]
    assert not literal_route(sample(), FIELDS[0], '2016').iloc[3]
    assert pd.isna(literal_route(sample(), FIELDS[0], '2016').iloc[4])


@pytest.mark.parametrize('wave',['2007','2017','2019'])
def test_missing_forms_have_no_adopted_route(wave):
    assert literal_route(sample(), FIELDS[0], wave) is None


def test_2004_literal_part_b_gate():
    assert literal_route(sample(), FIELDS[0], '2004').iloc[0]
    assert not literal_route(sample(), FIELDS[3], '2004').iloc[0]
    assert literal_route(sample(), FIELDS[3], '2004').iloc[1]


def test_snapshot_scope_and_arithmetic(snapshot):
    s = snapshot['scope_counts']
    assert (s['cumulative_reviewed_fields'],s['remaining_employment_fields']) == (17,22)
    assert s['field_wave_profiles'] == 60 and s['existing_raw_field_wave_mappings'] == 54
    for p in snapshot['profiles']:
        assert p['nonnull'] + p['null'] == p['rows']
        assert p['raw_nonnull'] - p['cleaner_removed'] - p['secondary_suppressed'] == p['nonnull']
        assert sum(p['values'].values()) == p['nonnull']
        assert p['nonnull_excluding_explicit_labelled_missing'] + p['labelled_missing_count'] == p['nonnull']


def test_supplemental_job_grain_does_not_become_published_recovery(snapshot):
    s = snapshot['supplemental_2007']
    assert (s['rows'],s['persons'],s['secondary_persons_without_main_job_row']) == (11949,10174,21)
    assert s['duplicate_person_job_keys'] == s['unmatched_ec_keys'] == s['household_conflicts'] == 0
    assert s['industry_codes_absent_from_dictionary'] == {}
    for p in s['candidate_fields']:
        assert not p['published']
        assert p['candidate_nonnull_before_gate'] == p['candidate_nonnull_known_count_supports_job'] + p['nonnull_known_count_conflict'] + p['nonnull_job_count_unknown']
    assert [p['nonnull_known_count_conflict'] for p in s['candidate_fields']] == [0,0,0,65,65,65]


def test_frozen_inputs_and_review_implementation(snapshot):
    assert snapshot['implementation_sha256'] == digest((ROOT / SELF).read_bytes())
    for path, sha in PINS.items():
        assert digest((ROOT / path).read_bytes()) == sha
    assert not any(snapshot[k] for k in ['database_mutated','canonical_data_mutated','individual_records_saved',
        'classification_crosswalk_published','supplemental_recovery_published'])


def test_original_workbooks_codebook_and_live_scope(snapshot):
    v = snapshot['source_verification']
    assert len(v['sources']) == 7 and all(s['all_sheets_equal'] for s in v['sources'])
    assert 'Sheet3' in v['classification_codebook']['cells']
    assert v['classification_codebook']['dictionaries']['ISCO']['011'] == 'Armed forces occupations'
    db = snapshot['database_check']
    assert db['transaction_read_only'] and db['all_selected_values_equal']
    assert len(db['selected_columns']) == 17 and len(db['relations']) == 2
    assert not db['full_relation_validation']


def test_labelled_missing_exceptions_and_valid_zero(snapshot):
    assert sum(p['labelled_missing_count'] for p in snapshot['profiles']) == 774
    assert sum(sum((p['nonnull_with_no_embedded_label'] or {}).values()) for p in snapshot['profiles']) == 12
    industry = next(p for p in snapshot['profiles'] if p['survey_wave'] == '2004' and p['field'] == FIELDS[1])
    assert industry['zero_code_cells'] == 14515
    assert '00' not in industry['labelled_missing_or_not_stated']
    assert all(c['code_sets_equal'] for c in snapshot['codebook_label_comparisons'])
    assert all(c['all_labels_equal_after_whitespace_normalization'] for c in snapshot['codebook_label_comparisons'])
    assert all(c['all_literal_labels_equal'] for c in snapshot['codebook_label_comparisons'] if c['codebook_sheet'] == 'ISIC')


def test_docs_are_reproducible(snapshot):
    brief, details = documents(snapshot)
    assert (ROOT / 'docs/cses-employment-classification-alignment.md').read_text() == brief
    assert (ROOT / 'docs/cses-employment-classification-field-waves.md').read_text() == details
