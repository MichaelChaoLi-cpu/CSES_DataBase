"""Qualified classifications and 2007 source recovery never infer a job-role crosswalk."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'rsc/cses_db'))
import publish_cses_classification_correction as pub  # noqa: E402
from cses_archive_source_policy import archive_source_policy  # noqa: E402
from review_cses_employment_hours_status import registry  # noqa: E402


@pytest.fixture(scope='module')
def built():
    if not (ROOT/pub.REVIEW).exists():
        pytest.skip('Local source evidence unavailable')
    with archive_source_policy():
        return pub.local_plan(ROOT)


def test_exact_qualified_scope(built):
    plan,after,jobs,enriched = built
    assert after.shape==(332903,86) and jobs.shape==(11949,13) and enriched.shape==(11949,17)
    assert len(plan['rules'])==14 and sum(r['affected_cells'] for r in plan['rules'])==774
    assert int(after[pub.FLAGS].fillna(False).sum().sum())==774
    assert not plan['wide_2007_recovery_performed']


def test_all_74_preexisting_columns_unchanged(built):
    before = pd.read_parquet(ROOT/'data/processing/cses/employment_corrected_v1/final_EC_CSES.parquet')
    pd.testing.assert_frame_equal(built[1][list(before)],before,check_exact=True)
    assert built[1].loc[built[1].survey_wave.eq('2007'),pub.FIELDS].isna().all().all()


def test_only_known_codes_in_known_waves_interpreted_null(built):
    plan,frame,_,_ = built
    for source,target in zip(pub.FIELDS,pub.INTERPRETED,strict=True):
        lost = frame[source].notna() & frame[target].isna()
        assert lost.sum()==sum(r['affected_cells'] for r in plan['rules'] if r['canonical_field']==source)
        pd.testing.assert_series_equal(frame.loc[~lost,source],frame.loc[~lost,target],check_names=False)


def test_valid_zero_industry_not_missing(built):
    frame=built[1]
    for source,target,n in [(pub.FIELDS[1],pub.INTERPRETED[1],14515),(pub.FIELDS[4],pub.INTERPRETED[4],920)]:
        selected=frame.survey_wave.eq('2004') & frame[source].eq('00')
        assert selected.sum()==n and frame.loc[selected,target].eq('00').all()


def test_unlabelled_codes_not_guessed(built):
    review=json.loads((ROOT/pub.REVIEW).read_text())
    frame=built[1]
    n=0
    for p in review['profiles']:
        for code,count in (p['nonnull_with_no_embedded_label'] or {}).items():
            target=pub.INTERPRETED[pub.FIELDS.index(p['field'])]
            selected=frame.survey_wave.eq(p['survey_wave']) & frame[p['field']].eq(code)
            assert selected.sum()==count and frame.loc[selected,target].eq(code).all()
            n+=count
    assert n==12


def test_flags_outside_evidence_scope_are_null(built):
    frame=built[1]
    assert frame.loc[~frame.survey_wave.isin(['2004','2019','2021']),pub.FLAGS].isna().all().all()
    for source,flag in zip(pub.FIELDS,pub.FLAGS,strict=True):
        assert frame.loc[frame[source].isna(),flag].isna().all()


def test_raw_job_keys_values_and_missingness_preserved(built):
    jobs=built[2]
    assert jobs.person_id.nunique()==10174
    assert jobs.q13b_ocid.value_counts().to_dict()=={1:10153,2:1796}
    assert not jobs.duplicated(['survey_wave','person_id','q13b_ocid']).any()
    assert jobs.q13bc07.isna().sum()==27
    assert jobs.q13bc02b.eq('1').sum()==64  # No silent code padding in raw source table.
    assert jobs.source_row_id.nunique()==11949
    assert jobs.source_sha256.nunique()==1


def test_job_conflicts_retained_not_suppressed(built):
    enriched=built[3]
    assert enriched.index_exceeds_reported_job_count.sum()==65
    assert enriched.index_2_without_index_1.sum()==21
    assert enriched.job_index_interpretation.eq('unverified_primary_secondary_meaning').all()
    assert enriched.q13bc02b.notna().sum()==11949


def test_2007_dictionaries_do_not_certify_job_index_meaning(built):
    d=built[0]['supplemental_dictionaries']
    assert d['dbo_c_occu.dta']['rows']==0
    assert d['dbo_c_typeemployer.dta']['rows']==10
    assert d['dbo_c_typeemployer.dta']['english_labels']['7']=='Self-employed farm'


def test_graph_extension_preserves_every_old_element(built):
    prior=json.loads((ROOT/pub.GRAPH).read_text())
    deps=[{'view_name':v,'source_schema':'cses_analysis','source_relation':s} for v,s in sorted([
        (pub.VIEW,'cses_ec_aligned_v1'),(pub.JOBS,'cses_ec_aligned_v1'),(pub.JOBS,pub.TABLE)])]
    graph=pub.graph_extension(prior,'test',built[0],deps,registry(ROOT))
    nodes={n['id']:n for n in graph['nodes']}
    for n in prior['nodes']:
        assert nodes[n['id']]==n
    assert all(e in graph['edges'] for e in prior['edges'])
    assert len(graph['nodes'])==len(prior['nodes'])+5
    assert len(graph['edges'])==len(prior['edges'])+23
    assert all(e['source'] in nodes and e['target'] in nodes for e in graph['edges'])


def test_sql_is_additive_and_wave_scoped(built):
    query=built[0]['queries'][pub.VIEW]
    assert 'cses_ec_aligned_v1' in query and 'CASE WHEN' in query
    assert 'UPDATE' not in query and 'DELETE' not in query
    assert 'unverified_primary_secondary_meaning' in built[0]['queries'][pub.JOBS]


def test_duplicate_qualification_rejected(built):
    with pytest.raises(ValueError,match='already applied'):
        pub.qualified(built[1],built[0]['rules'])
