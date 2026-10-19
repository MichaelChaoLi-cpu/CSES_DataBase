"""Qualified denominators must not overwrite reports or silently resolve conflicts."""
import sys
from itertools import product
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'rsc/cses_db'))
from align_cses_additional_school import qualify, summary  # noqa: E402
from validate_cses_additional_school import decide, equal  # noqa: E402


def row(**changes):
    result = {'survey_wave':'1997','age_for_school_analysis':10.0,'questionnaire_minimum_age':5,
              'school_current_native_code':None,'school_ever_native_code':2,
              'school_current_observed':None,'school_ever_observed':0,
              'school_highest_level_source_code':None,'school_current_level_source_code':None,
              'education_record_linked':True,'skip_supported':True,
              'school_concept_scope':'school_system_with_separate_nonformal_item'}
    return {**result, **changes}


def frame(*records):
    f = pd.DataFrame(records)
    for c in ['school_current_observed','school_ever_observed']:
        f[c] = f[c].astype('Int64')
    for c in ['school_current_native_code','school_ever_native_code','school_highest_level_source_code',
              'school_current_level_source_code','age_for_school_analysis']:
        f[c] = f[c].astype(float)
    return f


def test_documented_skip_is_derived_not_an_observed_no():
    original = frame(row())
    after = qualify(original)
    assert after.school_attendance_qualified.iloc[0] == 0
    assert after.school_attendance_derived_from_skip.iloc[0]
    assert original.school_current_observed.isna().all()
    assert after.school_current_observed.isna().all()


@pytest.mark.parametrize('changes', [
    {'school_current_observed':1,'school_current_native_code':1},
    {'school_highest_level_source_code':2},
    {'school_current_level_source_code':1},
    {'school_ever_observed':1,'school_ever_native_code':1,'school_current_observed':0,
     'school_current_native_code':2,'school_current_level_source_code':3},
])
def test_route_conflicts_never_become_definite_answers(changes):
    f = qualify(frame(row(**changes)))
    assert f.school_route_conflict.iloc[0]
    assert f.school_attendance_qualified.isna().all()
    assert f.school_route_status.iloc[0] == 'unresolved_route_conflict'


@pytest.mark.parametrize('changes', [
    {'school_current_native_code':0},
    {'school_ever_native_code':3,'school_ever_observed':None,'school_current_native_code':2,'school_current_observed':0},
])
def test_invalid_native_code_is_not_a_skip_or_no(changes):
    f = qualify(frame(row(**changes)))
    assert f.school_invalid_response_code.iloc[0]
    assert f.school_attendance_qualified.isna().all()
    assert not f.school_attendance_derived_from_skip.iloc[0]


def test_neutral_zero_grade_differs_from_modern_preschool_zero():
    f = qualify(frame(row(school_current_level_source_code=0),
                      row(survey_wave='2025',questionnaire_minimum_age=3,school_current_level_source_code=0)))
    assert f.school_attendance_qualified.iloc[0] == 0
    assert pd.isna(f.school_attendance_qualified.iloc[1])
    assert f.school_route_conflict.tolist() == [False,True]


def test_age_universe_and_absent_records_remain_separate():
    f = qualify(frame(row(age_for_school_analysis=0),row(education_record_linked=False),
                      row(age_for_school_analysis=None)))
    assert f.school_route_status.tolist() == ['outside_questionnaire_age_range',
                                            'missing_education_record','unknown_age_eligibility']
    assert f.school_attendance_qualified.isna().all()


def test_valid_current_answer_with_missing_gate_is_visible_and_flagged():
    f = qualify(frame(row(school_ever_native_code=None,school_ever_observed=None,
                          school_current_native_code=1,school_current_observed=1)))
    assert f.school_attendance_qualified.iloc[0] == 1
    assert f.school_gate_missing_with_current_observed.iloc[0]


def test_missing_grade_does_not_erase_valid_current_yes():
    f = qualify(frame(row(school_ever_native_code=1,school_ever_observed=1,
                          school_current_native_code=1,school_current_observed=1)))
    assert f.school_attendance_qualified.iloc[0] == 1
    assert f.school_current_grade_missing.iloc[0]


def test_1996_has_no_never_attended_inference():
    f = qualify(frame(row(survey_wave='1996',skip_supported=False,school_ever_native_code=None,
                          school_ever_observed=None)))
    assert f.school_attendance_qualified.isna().all()


def test_summary_keeps_unknowns_and_all_member_bounds():
    f = qualify(frame(row(),row(school_current_native_code=1,school_current_observed=1,
                                school_ever_native_code=1,school_ever_observed=1),
                      row(school_current_native_code=0)))
    r = next(r for r in summary(f) if r['age_band']=='ages_6_17')
    assert (r['members'],r['qualified_yes'],r['qualified_no'],r['unknown_or_excluded']) == (3,1,1,1)
    assert r['qualified_unweighted_yes_pct'] == 50
    assert r['missingness_lower_bound_pct'] == 33.333333
    assert r['missingness_upper_bound_pct'] == 66.666667


def test_unreviewed_waves_fail_closed():
    with pytest.raises(ValueError,match='Unreviewed wave'):
        qualify(frame(row(survey_wave='2017')))


def test_scalar_acceptance_and_vector_projection_agree_on_576_route_combinations():
    cases, expected = [], []
    for wave,age,current,ever,highest,grade in product(['1997','2025'],[0,10],
                                                     [None,0,1,2],[None,0,1,2],[None,0,2],[None,0,2]):
        minimum = 5 if wave=='1997' else 3
        rule = {'skip_supported':True,'neutral_highest_codes':[0] if wave=='1997' else [88,98,-98],
                'neutral_current_codes':[0] if wave=='1997' else [98,-98]}
        cases.append(row(survey_wave=wave,age_for_school_analysis=age,questionnaire_minimum_age=minimum,
                         school_current_native_code=current,school_ever_native_code=ever,
                         school_current_observed={1:1,2:0}.get(current),school_ever_observed={1:1,2:0}.get(ever),
                         school_highest_level_source_code=highest,school_current_level_source_code=grade))
        expected.append(decide(age,minimum,True,current,ever,highest,grade,rule))
    actual = qualify(frame(*cases))
    assert len(actual)==576
    for r,want in zip(actual.itertuples(index=False),expected,strict=True):
        assert all(equal(getattr(r,k),v) for k,v in want.items())
