"""One-field review preserves binary polarity, nullable routes and publication scope."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'rsc/cses_db'))
from organize_cses_questionnaires import digest  # noqa: E402
from review_cses_main_job_whole_year import (  # noqa: E402
    FIELD,
    OUTPUT,
    PINS,
    SELF,
    document,
    evidence,
    recode,
    route,
)


@pytest.fixture(scope='module')
def located():
    if not (ROOT/'data/processing/cses/questionnaire_alignment_v1/source_cells.json').exists():
        pytest.skip('Questionnaire evidence unavailable')
    return evidence(ROOT)


@pytest.fixture(scope='module')
def snapshot():
    path=ROOT/OUTPUT/'review.json'
    if not path.exists():
        pytest.skip('Review artifact unavailable')
    return json.loads(path.read_text())


def test_five_questions_two_earlier_forms_and_two_options(located):
    qs,absent=located
    assert len(qs)==5 and {a['survey_wave'] for a in absent}=={'2004','2009'}
    for q in qs:
        assert q['field']==FIELD and q['option_count']==2
        assert {o['source_code'] for o in q['options']}=={1,2}
        assert '>>10d' in q['options'][0]['label_as_printed'].replace(' ','')
        assert not q['whole_variable_certified']


def test_draft_and_2021_gate_conflict_remain_explicit(located):
    qs=located[0]
    assert next(q for q in qs if q['survey_wave']=='2014')['documentation_status']=='provisional'
    q=next(q for q in qs if q['survey_wave']=='2021')
    assert q['2021_gate_text_mentions_temporary_absence_despite_unpaid_second_screen']
    assert 'unpaid work' in q['second_screen_text']
    assert 'temporary absent' in q['route_cells']['K11']


def test_polarity_null_and_invalid_codes():
    pd.testing.assert_series_equal(recode(pd.Series([1,2,0,9,None,'1','2','bad',1.5])),
        pd.Series([1,0,pd.NA,pd.NA,pd.NA,1,0,pd.NA,pd.NA],dtype='Int8'))


def test_or_screen_gate_not_first_screen_only():
    f=pd.DataFrame({'age':pd.Series([20,20,4,pd.NA],dtype='Int16'),
        'worked_at_least_one_hour_past_7_days':pd.Series([0,0,1,1],dtype='Int8'),
        'second_work_screening_source_code':pd.Series([1,2,pd.NA,pd.NA],dtype='Int8')})
    pd.testing.assert_series_equal(route(f,'2016'),pd.Series([True,False,False,pd.NA],dtype='boolean'))


@pytest.mark.parametrize('wave',['2004','2007','2009','2017','2019'])
def test_unavailable_or_unverified_route_not_borrowed(wave):
    assert route(pd.DataFrame(),wave) is None


def test_scope_and_raw_reproduction(snapshot):
    s=snapshot['scope_counts']
    assert (s['batch_fields'],s['cumulative_reviewed_ec_fields'],s['remaining_ec_fields'])==(1,18,21)
    assert (s['nonnull'],s['yes'],s['no'])==(124104,85793,38311)
    assert s['raw_field_wave_mappings']==7 and s['field_wave_profiles']==10
    for p in snapshot['profiles']:
        assert p['raw_to_canonical_equal'] and p['raw_nonnull']==p['nonnull']
        assert p['yes']+p['no']==p['nonnull'] and p['nonnull']+p['null']==p['rows']
        assert not p['discarded_raw_values']


def test_route_exceptions_retained_not_deleted(snapshot):
    ps=[p for p in snapshot['profiles'] if p['literal_route_records'] is not None]
    assert sum(p['nonnull_outside_known_route'] for p in ps)==5
    assert sum(p['nonnull_route_unknown'] for p in ps)==1
    assert sum(p['within_route_null'] for p in ps)==41
    for p in ps:
        assert p['nonnull']==p['nonnull_within_route']+p['nonnull_outside_known_route']+p['nonnull_route_unknown']


def test_frozen_dependencies_and_no_publication(snapshot):
    for path,sha in PINS.items():
        assert digest((ROOT/path).read_bytes())==sha
    assert snapshot['implementation_sha256']==digest((ROOT/SELF).read_bytes())
    assert not any(snapshot[k] for k in ['database_mutated','canonical_data_mutated','individual_records_saved','new_question_links_published'])


def test_workbook_and_live_verification(snapshot):
    assert len(snapshot['source_verification']['sources'])==7
    assert all(s['all_sheets_equal'] for s in snapshot['source_verification']['sources'])
    check=snapshot['database_check']
    assert check['transaction_read_only'] and check['all_selected_cells_equal']
    assert len(check['columns'])==11 and len(check['relations'])==2
    assert not check['full_relation_validation']


def test_document_is_reproducible(snapshot):
    assert document(snapshot)==(ROOT/'docs/cses-main-job-whole-year.md').read_text()
