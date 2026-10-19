"""Do not mix attainment with current study, source None with unknown, or certificates with grades."""
import sys
from itertools import product
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'rsc/cses_db'))
from align_cses_additional_levels import definitions_for, qualify  # noqa: E402
from validate_cses_additional_levels import decide, equal, parent_flags  # noqa: E402


def codebook():
    return [{'survey_wave':w,'target':t,'source_code':c,'native_value_label':str(c),
             'source_form_code_differs':c!=m['questionnaire_code'],**m}
            for w in ['1996','1997','1999','2023','2025'] for t in ['highest','current']
            for c,m in definitions_for(w,t).items()]


def record(**changes):
    return {**{'survey_wave':'2025','highest_source_code':6,'current_source_code':7,
        'school_ever_observed':1,'school_current_observed':1,'school_ever_native_code':1,
        'school_current_native_code':1,'school_route_conflict':False,'school_invalid_response_code':False,
        'school_age_eligible':True,'education_record_linked':True},**changes}


def projection(*rows):
    f = pd.DataFrame(rows)
    for c in ['school_ever_observed','school_current_observed']:
        f[c] = f[c].astype('Int64')
    for c in ['highest_source_code','current_source_code','school_ever_native_code','school_current_native_code']:
        f[c] = f[c].astype(float)
    f.school_age_eligible = f.school_age_eligible.astype('boolean')
    return qualify(f,codebook())


def test_all_nine_dictionaries_have_188_entries():
    b = codebook()
    assert len(b)==188
    assert len({(r['survey_wave'],r['target'],r['source_code']) for r in b})==188


def test_same_modern_code_18_means_bachelor_completed_but_masters_current():
    f = projection(record(highest_source_code=18,current_source_code=18))
    assert f.highest_qualified_family.iloc[0]=='bachelor'
    assert f.current_qualified_family.iloc[0]=='masters'
    assert f.highest_qualified_general_grade.isna().all()


def test_1996_code_12_is_certificate_not_grade_12():
    f = projection(record(survey_wave='1996',highest_source_code=12,current_source_code=None,
                          school_ever_observed=None,school_ever_native_code=None))
    assert f.highest_qualified_family.iloc[0]=='secondary_certificate_unspecified'
    assert f.highest_qualified_general_grade.isna().all()
    assert f.current_level_status.iloc[0]=='not_collected_in_selected_education_source'


def test_1999_zero_is_preschool_99_none_is_not_unknown():
    f = projection(record(survey_wave='1999',highest_source_code=0,current_source_code=0),
                   record(survey_wave='1999',highest_source_code=99,current_source_code=99))
    assert f.highest_qualified_family.tolist()==['preschool_kindergarten','none_unspecified']
    assert f.current_qualified_family.iloc[0]=='preschool_kindergarten'
    assert pd.isna(f.current_qualified_family.iloc[1])
    assert f.current_level_status.iloc[1]=='none_not_a_current_level'


@pytest.mark.parametrize('wave,code',[('1996',99),('2023',98),('2025',-98)])
def test_unknown_codes_do_not_become_none_attainment(wave,code):
    f = projection(record(survey_wave=wave,highest_source_code=code))
    assert f.highest_level_status.iloc[0]=='explicit_unknown_highest'
    assert f.highest_qualified_family.isna().all()


def test_none_does_not_create_zero_years_or_zero_grade():
    f = projection(record(survey_wave='1997',highest_source_code=0,current_source_code=0))
    assert f.highest_qualified_family.iloc[0]=='none_unspecified'
    assert f.highest_qualified_general_grade.isna().all()
    assert f.current_qualified_family.isna().all()


def test_skip_derivation_never_fills_a_current_level():
    f = projection(record(highest_source_code=None,current_source_code=None,
                          school_ever_observed=0,school_ever_native_code=2,
                          school_current_observed=None,school_current_native_code=None))
    assert f.highest_qualified_family.iloc[0]=='never_attended'
    assert f.highest_derived_from_skip.iloc[0]
    assert f.current_qualified_family.isna().all()
    assert pd.isna(f.highest_source_code.iloc[0])


def test_never_attended_does_not_override_preschool_or_positive_grade():
    f = projection(record(survey_wave='1999',highest_source_code=0,school_ever_observed=0,school_ever_native_code=2))
    assert f.highest_level_status.iloc[0]=='never_attended_route_conflict'
    assert f.highest_qualified_family.isna().all()


def test_bad_current_gate_does_not_discard_valid_highest_attainment():
    f = projection(record(school_current_observed=None,school_current_native_code=0,
                          school_invalid_response_code=True))
    assert f.highest_qualified_general_grade.iloc[0]==6
    assert f.highest_level_status.iloc[0]=='observed_highest_other_item_warning'
    assert f.current_qualified_family.isna().all()


def test_current_no_with_recorded_grade_is_flagged_not_silently_used():
    f = projection(record(school_current_observed=0,school_current_native_code=2))
    assert f.current_level_status.iloc[0]=='current_code_outside_attendance_route'
    assert f.current_qualified_family.isna().all()
    assert f.highest_qualified_general_grade.iloc[0]==6


def test_no_imputation_of_current_grade_from_highest():
    f = projection(record(current_source_code=None))
    assert f.current_qualified_general_grade.isna().all()
    assert f.current_level_status.iloc[0]=='missing_current_level_after_yes'


def test_source_form_aliases_remain_explicit():
    f = projection(record(highest_source_code=96,current_source_code=96))
    assert f.highest_qualified_family.iloc[0]=='other_unspecified'
    assert f.highest_source_form_code_differs.iloc[0]
    assert f.current_source_form_code_differs.iloc[0]
    assert f.current_source_code.iloc[0]==96


def test_age_and_missing_source_records_do_not_receive_levels():
    f = projection(record(school_age_eligible=False),record(education_record_linked=False))
    assert f.highest_qualified_family.isna().all() and f.current_qualified_family.isna().all()
    assert f.highest_level_status.tolist()==['outside_questionnaire_age_range','missing_education_record']


def test_unrecognized_grade_is_not_a_new_school_year():
    f = projection(record(highest_source_code=97,current_source_code=14))
    assert f.highest_level_status.iloc[0]=='unrecognized_highest_code'
    assert f.current_level_status.iloc[0]=='unrecognized_current_level_code'
    assert f.highest_qualified_general_grade.isna().all()


def test_unreviewed_scope_fails_closed():
    with pytest.raises(ValueError,match='Unreviewed'):
        definitions_for('2017','highest')


def test_independent_scalar_and_vector_rules_agree_on_3600_code_combinations():
    book = codebook()
    lookup = {(r['survey_wave'],r['target'],r['source_code']):r for r in book}
    cases,expected = [],[]
    for wave,high,level,ever,current in product(['1996','1997','1999','2023','2025'],
        [None,0,6,12,18,99,88,96,-98],[None,0,7,18,99],[None,0,1,2],[None,0,1,2]):
        route,invalid = parent_flags(wave,high,level,ever,current)
        cases.append(record(survey_wave=wave,highest_source_code=high,current_source_code=level,
            school_ever_observed={1:1,2:0}.get(ever),school_current_observed={1:1,2:0}.get(current),
            school_ever_native_code=ever,school_current_native_code=current,
            school_route_conflict=route,school_invalid_response_code=invalid))
        expected.append(decide(wave,True,True,ever,current,high,level,
                               lookup.get((wave,'highest',high)),lookup.get((wave,'current',level))))
    actual = projection(*cases)
    assert len(actual)==3600
    for r,want in zip(actual.itertuples(index=False),expected,strict=True):
        assert all(equal(getattr(r,k),v) for k,v in want.items())
