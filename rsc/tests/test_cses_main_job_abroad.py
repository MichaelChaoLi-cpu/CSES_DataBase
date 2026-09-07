"""Abroad is a location question with its own route, not a seasonal subset."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'rsc/cses_db'))
from organize_cses_questionnaires import digest  # noqa: E402
from review_cses_main_job_abroad import (  # noqa: E402
    FIELD,
    LAYOUTS,
    OUTPUT,
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
        pytest.skip('Review snapshot unavailable')
    return json.loads(path.read_text())


def test_exact_question_meaning_and_options(located):
    qs,earlier=located
    assert {q['survey_wave'] for q in qs}==set(LAYOUTS)
    assert {r['survey_wave'] for r in earlier}=={'2004','2009'}
    assert all(not r['matches'] for r in earlier)
    for q in qs:
        assert q['field']==FIELD and q['source_variable'].lower()=='q15_c10d'
        assert 'done in a foreign country?' in q['question_text']
        assert [(o['source_code'],o['label_as_printed'].strip()) for o in q['options']]==[(1,'Yes'),(2,'No')]
        assert q['option_count']==2 and not q['whole_variable_certified']


def test_whole_year_bypass_and_question_qualifications(located):
    for q in located[0]:
        assert not q['whole_year_or_seasonal_answer_required']
        assert '>>10d' in q['prior_whole_year_question']['options'][0]['label_as_printed'].replace(' ','')
    q=next(q for q in located[0] if q['survey_wave']=='2021')
    assert 'temporary absent' in q['gate_text']
    assert 'unpaid work' in q['prior_whole_year_question']['second_screen_text']
    assert next(q for q in located[0] if q['survey_wave']=='2014')['documentation_status']=='provisional'


def test_binary_polarity_and_nonbinary_nulls():
    pd.testing.assert_series_equal(recode(pd.Series([1,2,4,8,None,'1','2',1.5])),
        pd.Series([1,0,pd.NA,pd.NA,pd.NA,1,0,pd.NA],dtype='Int8'))


def test_route_does_not_read_whole_year_or_seasonal():
    f=pd.DataFrame({'age':pd.Series([20,20,20,4,pd.NA],dtype='Int16'),
        'worked_at_least_one_hour_past_7_days':pd.Series([1,0,0,1,1],dtype='Int8'),
        'second_work_screening_source_code':pd.Series([pd.NA,1,2,pd.NA,pd.NA],dtype='Int8')})
    expected=pd.Series([True,True,False,False,pd.NA],dtype='boolean')
    pd.testing.assert_series_equal(route(f,'2016'),expected)
    f['main_job_works_whole_year']=1
    f['main_job_was_usual_past_7_days']=pd.NA
    pd.testing.assert_series_equal(route(f,'2016'),expected)


@pytest.mark.parametrize('wave',['2004','2007','2009','2017','2019'])
def test_unverified_route_not_borrowed(wave):
    assert route(pd.DataFrame(),wave) is None


def test_counts_and_exclusions(snapshot):
    c=snapshot['scope_counts']
    assert (c['batch_fields'],c['cumulative_reviewed_ec_fields'],c['remaining_ec_fields'])==(1,20,19)
    assert (c['rows'],c['nonnull'],c['yes'],c['no'])==(332903,123829,3086,120743)
    assert c['raw_nonnull']==123832 and c['inherited_nonbinary_exclusions']==3
    assert c['raw_field_wave_mappings']==7 and c['question_wave_correspondences']==5
    for p in snapshot['profiles']:
        assert p['raw_to_canonical_equal']
        assert p['nonnull']==p['yes']+p['no']
        assert p['rows']==p['nonnull']+p['null']
        assert p['raw_nonnull']==p['nonnull']+sum(p['discarded_raw_values'].values())
    assert {p['survey_wave']:p['discarded_raw_values'] for p in snapshot['profiles'] if p['discarded_raw_values']}=={'2019':{'4.0':2,'8.0':1}}


def test_route_exceptions_and_seasonal_independence(snapshot):
    ps=[p for p in snapshot['profiles'] if p['survey_wave'] in LAYOUTS]
    assert sum(p['nonnull_outside_known_route'] for p in ps)==6
    assert sum(p['nonnull_route_unknown'] for p in ps)==1
    assert sum(p['within_route_null'] for p in ps)==279
    assert sum(p['nonnull_with_whole_year_yes'] for p in ps)==57996
    assert sum(p['nonnull_without_seasonal_response'] for p in ps)==58139
    for p in ps:
        assert p['nonnull']==sum(p[k] for k in ['nonnull_within_route','nonnull_outside_known_route','nonnull_route_unknown'])


def test_partial_2019_wording_is_not_complete_question(snapshot):
    p=next(p for p in snapshot['profiles'] if p['survey_wave']=='2019')
    assert p['fresh_stata_metadata']['variable_label'].endswith('done in a foreign co')
    assert p['fresh_stata_metadata']['value_labels']=={'1':'Yes','2':'No'}
    assert p['literal_route_records'] is None
    assert '2019' not in {q['survey_wave'] for q in snapshot['questions']}


def test_read_only_verification_and_preserved_snapshots(snapshot):
    db=snapshot['database_check']
    assert db['transaction_read_only'] and db['all_selected_cells_equal']
    assert len(db['columns'])==13 and len(db['relations'])==2 and db['rows_per_relation']==332903
    assert not db['full_relation_validation']
    for k in ['database_mutated','canonical_data_mutated','individual_records_saved','new_question_links_published']:
        assert not snapshot[k]
    assert snapshot['implementation_sha256']==digest((ROOT/SELF).read_bytes())
    for name,sha in snapshot['frozen_inputs'].items():
        assert digest((ROOT/name).read_bytes())==sha
    assert len(snapshot['source_verification']['sources'])==7
    assert all(s['all_sheets_equal'] for s in snapshot['source_verification']['sources'])
    assert not snapshot['source_verification']['workbooks_modified']


def test_document_reproducible(snapshot):
    assert document(snapshot)==(ROOT/'docs/cses-main-job-abroad.md').read_text()
