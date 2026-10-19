"""Recent-health questions require a period, concept, source and denominator contract."""
import inspect
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'rsc/cses_db'))
import pilot_cses_health_all_waves as pilot  # noqa: E402
from pilot_cses_health_all_waves_v2 import promote_rules  # noqa: E402
from validate_cses_education_all_waves import equal  # noqa: E402
from validate_cses_health_all_waves import decide  # noqa: E402


def rule(wave):
    r = dict(json.loads(pilot.SPEC.read_text())['waves'][wave],survey_wave=wave)
    r['mapping'] = {} if wave in ['1996','2017'] else {'1':1,'2':1,'3':0} if wave in ['2019','2021','2023','2025'] else {'1':1,'2':0}
    r['missing_codes'] = [9] if wave=='2004' else []
    r.setdefault('no_followups',[] if wave in ['1996','2017'] else ['q13bc2b','q13bc03','q13bc04','q13bc05','q13bc06'])
    r['injury_only'] = r['no_followups'][:2] if wave in ['2019','2021','2023','2025'] else []
    return r


def row(wave='2025',code=1,**changes):
    return {'survey_wave':wave,'household_key':'hh','record_key':'person','screen_native':float('nan') if code is None else float(code),
        'age_for_analysis':20.,'health_linked':True,'hh_link_matched':True,
        'screen_variant_conflict':False,'followup_variant_conflict':False,
        **{c:float('nan') for c in pilot.BRANCHES},**changes}


def classify(wave='2025',code=1,**changes):
    return pilot.qualify(pd.DataFrame([row(wave,code,**changes)]),[rule(wave)]).iloc[0]


@pytest.mark.parametrize('wave',['1997','1999','2004','2007'])
def test_four_week_broader_concepts_do_not_become_30days(wave):
    r = classify(wave)
    assert r.screen_qualified==1 and r.reference_period_days==28
    assert pd.isna(r.illness_injury_30d_candidate) and pd.isna(r.illness_injury_30d_qualified)


def test_code_two_changes_meaning_in_modern_sources():
    assert classify('2016',2).screen_qualified==0
    assert classify('2025',2).illness_injury_30d_qualified==1


def test_1996_not_collected_is_not_healthy():
    r = classify('1996',None)
    assert r.screen_status=='not_collected_in_selected_source' and pd.isna(r.screen_qualified)


def test_2017_not_transferred_from_2016():
    r = classify('2017',1)
    assert r.screen_native==1 and pd.isna(r.screen_binary_native)
    assert r.screen_status=='unverified_same_wave_form_scope' and pd.isna(r.illness_injury_30d_qualified)


def test_2019_native_injury_printed_no_conflict_not_adjudicated():
    r = classify('2019',2)
    assert r.screen_binary_native==1 and r.source_form_code_conflict
    assert pd.isna(r.screen_qualified) and pd.isna(r.illness_injury_30d_candidate)
    assert classify('2019',1).illness_injury_30d_candidate==1
    assert pd.isna(classify('2019',1).illness_injury_30d_qualified)


def test_combined_2011_wave_retains_candidate_not_strict_default():
    r = classify('2011-12',1)
    assert r.illness_injury_30d_candidate==1 and pd.isna(r.illness_injury_30d_qualified)


def test_2014_published_appendix_supports_candidate_promotion():
    assert classify('2014',1).illness_injury_30d_qualified==1


def test_missing_row_explicit_missing_and_invalid_code_differ():
    assert classify(code=1,health_linked=False).screen_status=='missing_health_source_record'
    assert classify('2004',9).screen_status=='explicit_missing_code'
    assert classify('1997',7).screen_status=='unrecognized_native_code'
    assert classify(code=None).screen_status=='source_null'


def test_conflicts_do_not_rewrite_the_screen():
    r = classify('2023',3,branch_1_native=9.)
    assert r.screen_native==3 and r.screen_binary_native==0 and r.no_with_followup
    assert pd.isna(r.screen_qualified)
    assert classify('2023',2,branch_2_native=2.).injury_with_illness_only


def test_downstream_variant_conflict_does_not_discard_a_clean_screen():
    r = classify('2023',1,followup_variant_conflict=True)
    assert r.illness_injury_30d_qualified==1 and r.followup_variant_conflict
    assert pd.isna(classify('2023',1,screen_variant_conflict=True).screen_qualified)


def test_age_is_not_a_health_screen_eligibility_cutoff():
    assert classify('2025',1,age_for_analysis=0.).illness_injury_30d_qualified==1


def test_vector_and_scalar_policies_agree_across_all_wave_states():
    for wave in json.loads(pilot.SPEC.read_text())['waves']:
        r = rule(wave)
        rows = [row(wave,code,record_key=str(i),health_linked=linked,branch_1_native=branch)
            for i,(code,linked,branch) in enumerate((c,link,b) for c in [None,0,1,2,3,7,9] for link in [True,False] for b in [float('nan'),1.])]
        f = pilot.qualify(pd.DataFrame(rows),[r])
        for x in f.itertuples(index=False):
            expected = decide(x,r)
            assert all(equal(getattr(x,k),v) for k,v in expected.items())


def test_pilot_has_no_database_or_version_control_mutation_path():
    spec = json.loads(pilot.SPEC.read_text())
    assert not spec['database_publication_authorized'] and not spec['historical_outputs_mutable']
    source = inspect.getsource(pilot)
    assert 'psycopg' not in source and 'connect(' not in source
    assert all(x not in source for x in ['git push','dvc push','CREATE TABLE','INSERT INTO'])


def test_2012_evidence_promotes_only_combined_wave_without_rewriting_first_rules():
    before = [rule(w) for w in json.loads(pilot.SPEC.read_text())['waves']]
    spec = {'form_path':'same-year-2012.pdf','review':'matching question, universe, period and options'}
    after = promote_rules(before,spec)
    assert not next(r for r in before if r['survey_wave']=='2011-12')['strict_30d']
    assert next(r for r in after if r['survey_wave']=='2011-12')['strict_30d']
    assert [r for r in before if r['survey_wave']!='2011-12']==[r for r in after if r['survey_wave']!='2011-12']
    assert not next(r for r in after if r['survey_wave']=='2019')['strict_30d']


def test_matching_2012_form_changes_strict_result_not_native_or_candidate():
    original = rule('2011-12')
    revised = promote_rules([original],{'form_path':'2012.pdf','review':'matching source evidence'})
    f = pd.DataFrame([row('2011-12',1),row('2011-12',2,record_key='person2')])
    a,b = pilot.qualify(f,[original]),pilot.qualify(f,revised)
    pd.testing.assert_series_equal(a.screen_native,b.screen_native)
    pd.testing.assert_series_equal(a.illness_injury_30d_candidate,b.illness_injury_30d_candidate)
    assert a.illness_injury_30d_qualified.isna().all()
    assert b.illness_injury_30d_qualified.tolist()==[1,0]
