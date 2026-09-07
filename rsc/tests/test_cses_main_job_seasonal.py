"""Seasonal semantic correction is evidence-qualified, additive and read-only."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'rsc/cses_db'))
from organize_cses_questionnaires import digest  # noqa: E402
from review_cses_main_job_seasonal import (  # noqa: E402
    CURRENT,
    EXTRAS,
    LAYOUTS,
    LEGACY,
    OUTPUT,
    ROUTE,
    SELF,
    STATUS,
    TARGET,
    YEAR,
    document,
    evidence,
    project,
    projection_sql,
    recode,
    route,
)


@pytest.fixture(scope='module')
def snapshot():
    path=ROOT/OUTPUT/'review.json'
    if not path.exists():
        pytest.skip('Review artifact unavailable')
    return json.loads(path.read_text())


def example(waves):
    n=len(waves)
    return pd.DataFrame({'survey_wave':waves,'age':pd.Series([20]*n,dtype='Int16'),
        'worked_at_least_one_hour_past_7_days':pd.Series([1]*n,dtype='Int8'),
        'second_work_screening_source_code':pd.Series([pd.NA]*n,dtype='Int8'),
        LEGACY:pd.Series([1]*n,dtype='Int8'),YEAR:pd.Series([0]*n,dtype='Int8')})


def test_exact_question_definition_and_gate():
    if not (ROOT/'data/processing/cses/questionnaire_alignment_v1/source_cells.json').exists():
        pytest.skip('Questionnaire evidence unavailable')
    qs,_=evidence(ROOT)
    assert {q['survey_wave'] for q in qs}==set(LAYOUTS)
    for q in qs:
        assert q['source_variable'].lower()=='q15_c10c'
        assert 'seasonal?' in q['question_text']
        assert 'reoccurring every year' in q['definition']
        assert q['gate_text'].strip()=='If Col. 10b = 2'
        assert q['option_count']==2 and not q['whole_variable_certified']


def test_binary_polarity_is_not_reversed():
    assert recode(pd.Series([1,2])).tolist()==[1,0]
    assert recode(pd.Series([0,9,1.5,None])).isna().all()


def test_additive_projection_retains_outside_route_answers():
    f=example(['2016']*4)
    f[YEAR]=pd.Series([0,1,pd.NA,0],dtype='Int8')
    f.loc[3,'age']=4
    result=project(f)
    pd.testing.assert_frame_equal(result[list(f)],f)
    assert result[TARGET].tolist()==[1,1,1,1]
    pd.testing.assert_series_equal(result[ROUTE],pd.Series([True,False,pd.NA,False],dtype='boolean',name=ROUTE))
    assert len(result.columns)==len(f.columns)+3


def test_evidence_status_and_no_cross_wave_imputation():
    f=example(['2011-12','2013','2014','2016','2021','2017','2019','2004','2007','2009'])
    result=project(f)
    assert result[TARGET].notna().tolist()==[True]*5+[False]*5
    assert result.loc[2,STATUS]=='questionnaire_draft'
    assert result.loc[5,STATUS]=='questionnaire_semantics_unverified'
    assert result.loc[6,STATUS]=='binary_labels_only_question_text_truncated'
    assert result.loc[7:,STATUS].eq('no_selected_source_column').all()
    assert result.loc[5:,ROUTE].isna().all()
    pd.testing.assert_frame_equal(result[list(f)],f)


def test_second_screen_and_unknown_gate():
    f=example(['2021']*3)
    f['worked_at_least_one_hour_past_7_days']=pd.Series([0,0,0],dtype='Int8')
    f['second_work_screening_source_code']=pd.Series([1,2,pd.NA],dtype='Int8')
    pd.testing.assert_series_equal(route(f,'2021'),pd.Series([True,False,pd.NA],dtype='boolean'))
    assert route(pd.DataFrame(),'2017') is None
    assert route(pd.DataFrame(),'2019') is None


def test_projection_cannot_overwrite_existing_alias():
    with pytest.raises(ValueError,match='already contains'):
        project(project(example(['2016'])))


def test_scope_counts_and_raw_preservation(snapshot):
    c=snapshot['scope_counts']
    assert (c['batch_fields'],c['cumulative_reviewed_ec_fields'],c['remaining_ec_fields'])==(1,19,20)
    assert (c['stored_nonnull'],c['stored_yes'],c['stored_no'],c['supported_alias_nonnull'])==(38176,28138,10038,29061)
    assert c['raw_source_waves']==7 and c['question_wave_correspondences']==5
    for p in snapshot['profiles']:
        assert p['nonnull']==p['yes']+p['no']
        assert p['rows']==p['nonnull']+p['null']
        assert all(f['raw_to_canonical_equal'] for f in p['fields'])
        assert not p['fields'][1]['discarded_values']
        assert p['fields'][0]['raw_nonnull']==p['nonnull']+sum(p['fields'][0]['discarded_values'].values())
    assert c['raw_nonnull']==38189 and c['inherited_nonbinary_exclusions']==13
    excluded={p['survey_wave']:p['fields'][0]['discarded_values'] for p in snapshot['profiles'] if p['fields'][0]['discarded_values']}
    assert excluded=={'2019':{'0.0':7,'3.0':4,'6.0':1},'2021':{'3.0':1}}


def test_route_exceptions_are_counted_not_deleted(snapshot):
    c=snapshot['scope_counts']
    assert c['whole_year_yes_with_response']==165
    assert c['whole_year_yes_and_seasonal_yes']==49
    assessed=[p for p in snapshot['profiles'] if p['aligned_semantic_value_available']]
    assert sum(p['whole_year_yes_with_response'] for p in assessed)==121
    assert sum(p['nonnull_outside_known_route'] for p in assessed)==124
    assert sum(p['nonnull_route_unknown'] for p in assessed)==16
    for p in assessed:
        assert p['nonnull']==sum(p[k] for k in ['nonnull_inside_route','nonnull_outside_known_route','nonnull_route_unknown'])


def test_2019_truncated_label_not_mistaken_for_question(snapshot):
    p=next(p for p in snapshot['profiles'] if p['survey_wave']=='2019')
    meta=p['fields'][0]['fresh_stata_metadata']
    assert 'seasonal' not in meta['variable_label'].lower()
    assert meta['value_labels']=={'1':'Yes','2':'No'}
    assert not p['aligned_semantic_value_available'] and p['nonnull']==7083


def test_read_only_database_verification_and_frozen_dependencies(snapshot):
    check=snapshot['database_check']
    assert check['transaction_read_only'] and check['all_selected_values_match'] and check['all_projection_values_match']
    assert (check['local_projection_rows'],check['local_projection_columns'])==(332903,89)
    assert not check['persistent_database_objects_created']
    for k in ['database_mutated','canonical_data_mutated','old_field_renamed','persistent_alias_published','individual_records_saved_in_review']:
        assert not snapshot[k]
    for path,sha in snapshot['frozen_inputs'].items():
        assert digest((ROOT/path).read_bytes())==sha
    assert digest((ROOT/SELF).read_bytes())==snapshot['implementation_sha256']
    assert all(s['all_sheets_equal'] for s in snapshot['source_verification']['sources'])


def test_full_local_projection_preserves_all_86_columns(snapshot):
    old=pd.read_parquet(ROOT/CURRENT)
    new=pd.read_parquet(ROOT/OUTPUT/'local_semantic_projection.parquet')
    assert list(new)==list(old)+EXTRAS
    pd.testing.assert_frame_equal(new[list(old)],old,check_exact=True)
    pd.testing.assert_frame_equal(new,project(old),check_exact=True)
    assert digest((ROOT/OUTPUT/'local_semantic_projection.parquet').read_bytes())==snapshot['local_projection_sha256']


def test_document_and_sql_reproducible(snapshot):
    assert document(snapshot)==(ROOT/'docs/cses-main-job-seasonal.md').read_text()
    sql_path = ROOT / 'rsc/sql/cses_main_job_seasonal_projection.sql'
    # SQL is a generated, Git-ignored output. Validate the reproducible query even
    # on a fresh checkout where that optional artifact has not been materialized.
    sql = sql_path.read_text() if sql_path.exists() else 'BEGIN READ ONLY;\n' + projection_sql() + ';\nROLLBACK;'
    assert projection_sql() in sql and 'READ ONLY;' in sql
    assert all(word not in projection_sql().upper() for word in ['UPDATE ','CREATE ','ALTER ','DELETE '])
