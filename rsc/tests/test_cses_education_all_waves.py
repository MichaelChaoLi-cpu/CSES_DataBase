"""A unified schema is not blanket equivalence or permission to publish."""
import inspect
import json
import sys
from itertools import product
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'rsc/cses_db'))
from pilot_cses_education_all_waves import TARGETS, coverage, level_definitions  # noqa: E402
from pilot_cses_education_all_waves_v2 import qualify  # noqa: E402
from validate_cses_education_all_waves import database_acceptance, equal  # noqa: E402
from validate_cses_education_all_waves_v2 import decide  # noqa: E402

WAVES = ['1996','1997','1999','2004','2007','2009','2011-12','2013','2014','2016','2017','2019','2021','2023','2025']


def record(wave='2025',**changes):
    legacy = wave in ['1996','1997','1999']
    row = {'survey_wave':wave,'age_for_analysis':20,'minimum_age':None if wave=='2017' else 5 if legacy or wave in ['2004','2007'] else 3,
        'education_linked':True,'form_scope_reviewed':wave!='2017','skip_supported':wave!='1996' and wave!='2017',
        'combined_mode':'observed_combined' if legacy else 'derived_components',
        'combined_native':1 if legacy else None,'read_native':None if legacy else 1,'write_native':None if legacy else 1,
        'ever_native':None if wave=='1996' else 1,'attendance_native':1,'highest_native':6,
        'current_native':None if wave=='1996' else 7,'years_native':None if legacy or wave=='2004' else 8}
    for t in TARGETS:
        row[t+'_available'] = (not legacy if t in ['read','write'] else not(legacy or wave=='2004') if t=='years'
            else wave!='1996' if t in ['ever','current'] else True)
    return {**row,**changes}


def projection(*rows):
    f = pd.DataFrame(rows)
    for c in ['age_for_analysis','minimum_age']+[t+'_native' for t in TARGETS]:
        f[c] = f[c].astype(float)
    return qualify(f)


def test_2016_current_18_is_not_later_masters():
    f = projection(record('2016',current_native=18),record('2021',current_native=18))
    assert f.current_qualified.tolist()==['continuing_undergraduate_studies','masters']


def test_2007_highest_and_current_13_are_different():
    f = projection(record('2007',highest_native=13,current_native=13))
    assert f.highest_qualified.iloc[0]=='lower_secondary_certificate'
    assert f.current_qualified.iloc[0]=='technical_vocational_pre_secondary'


def test_2014_postgraduate_has_published_report_support_but_no_degree_subtype():
    f = projection(record('2014',current_native=21))
    assert f.current_qualified.iloc[0]=='postgraduate_unspecified'
    assert f.current_general_grade.isna().all()


def test_2019_current_20_other_not_completed_doctorate():
    f = projection(record('2019',highest_native=20,current_native=20))
    assert f.highest_qualified.iloc[0]=='doctorate'
    assert f.current_qualified.iloc[0]=='other_unspecified'


def test_2017_raw_responses_and_members_remain_without_false_form_certification():
    f = projection(record('2017',current_native=21))
    assert len(f)==1 and f.current_native.iloc[0]==21
    for t in TARGETS:
        assert f[t+'_qualified'].isna().all()
        assert f[t+'_status'].iloc[0]=='unverified_same_wave_form_scope'
    q = next(r for r in coverage(f) if r['age_band']=='questionnaire_universe')
    assert q['age_band_members'] is None and q['source_available']


@pytest.mark.parametrize('wave',['1996','1997','1999'])
def test_legacy_combined_is_not_split(wave):
    f = projection(record(wave))
    assert f.combined_qualified.iloc[0]==1 and not f.combined_derived.iloc[0]
    assert f.read_qualified.isna().all() and f.write_qualified.isna().all() and f.years_qualified.isna().all()


def test_undefined_writing_zero_not_inferred_from_reading_no():
    f = projection(record(read_native=2,write_native=0))
    assert f.read_qualified.iloc[0]==0
    assert f.write_qualified.isna().all() and f.combined_qualified.isna().all()


def test_years_structural_skip_is_not_zero_and_never_blocks_valid_literacy():
    f = projection(record(ever_native=2,attendance_native=None,highest_native=None,current_native=None,years_native=None))
    assert f.years_qualified.isna().all() and not f.years_imputed.any()
    assert f.years_status.iloc[0]=='documented_skip_no_years_value'
    assert f.read_qualified.iloc[0]==1
    assert f.attendance_qualified.iloc[0]==0 and f.highest_qualified.iloc[0]=='never_attended'


def test_positive_years_blocks_never_attended_and_current_no_inference():
    f = projection(record('2009',ever_native=2,attendance_native=None,highest_native=None,current_native=None,years_native=2))
    assert f.never_attended_positive_years_warning.iloc[0]
    assert f.highest_qualified.isna().all() and f.attendance_qualified.isna().all()
    assert f.highest_status.iloc[0]=='never_attended_positive_years_conflict'
    assert f.read_qualified.iloc[0]==1 and f.ever_qualified.iloc[0]==0


def test_years_above_age_and_fractional_years_excluded_not_rounded():
    f = projection(record(age_for_analysis=4,years_native=5),record(years_native=8.5))
    assert f.years_qualified.isna().all()
    assert f.years_status.tolist()==['years_exceed_source_age','outside_integer_0_30_guard']
    assert f.years_native.tolist()==[5,8.5]


def test_2004_90_none_98_unknown_and_99_unrecognized_are_separate():
    f = projection(record('2004',highest_native=90),record('2004',highest_native=98),record('2004',highest_native=99))
    assert f.highest_qualified.iloc[0]=='none_unspecified'
    assert f.highest_status.tolist()==['observed','explicit_unknown_response','unrecognized_level_code']


def test_1999_99_is_none_not_unknown_and_zero_is_preschool():
    f = projection(record('1999',highest_native=99),record('1999',highest_native=0))
    assert f.highest_qualified.tolist()==['none_unspecified','preschool_kindergarten']


def test_invalid_current_gate_does_not_discard_valid_highest():
    f = projection(record(attendance_native=9))
    assert f.highest_qualified.iloc[0]=='general_school_grade' and f.highest_general_grade.iloc[0]==6
    assert f.attendance_qualified.isna().all() and f.current_qualified.isna().all()


def test_never_attended_current_yes_conflict_flagged():
    f = projection(record(ever_native=2))
    assert f.never_attended_route_conflict.iloc[0]
    assert f.attendance_qualified.isna().all() and f.highest_qualified.isna().all()


def test_common_age_band_does_not_override_source_2007_minimum_five():
    f = projection(record('2007',age_for_analysis=4))
    assert f.read_status.iloc[0]=='outside_questionnaire_age_range'
    assert f.read_qualified.isna().all()


def test_missing_record_not_dropped_or_imputed():
    f = projection(record(education_linked=False))
    assert len(f)==1 and f.read_status.iloc[0]=='missing_education_record'
    assert f.read_qualified.isna().all()


def test_pilot_has_no_database_publication_authority():
    spec = json.loads((Path(__file__).resolve().parents[1]/'specs/cses_education_all_waves_pilot_v1.json').read_text())
    assert not spec['database_publication_authorized'] and not spec['historical_outputs_mutable']
    source = inspect.getsource(database_acceptance)
    assert 'REPEATABLE READ READ ONLY' in source and 'SET LOCAL ROLE mda_readonly' in source
    assert 'conn.commit(' not in source


def test_scalar_vector_agree_on_4860_fifteen_wave_gate_level_combinations():
    cases = [record(wave,age_for_analysis=age,ever_native=ever,attendance_native=current,highest_native=highest,current_native=level)
        for wave,age,ever,current,highest,level in product(WAVES,[None,4,20],[None,0,1,2],[None,1,2],[None,0,18],[None,0,18])]
    assert len(cases)==4860
    expected = []
    raw = pd.DataFrame(cases)
    for r in raw.itertuples(index=False):
        def entry(target,code):
            return level_definitions(r.survey_wave,target).get(code)
        expected.append(decide(r,entry('highest',r.highest_native),entry('current',r.current_native)))
    actual = projection(*cases)
    for row,want in zip(actual.itertuples(index=False),expected,strict=True):
        assert all(equal(getattr(row,k),v) for k,v in want.items())
