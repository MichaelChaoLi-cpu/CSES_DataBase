"""Keep combined literacy, separate components, skips and observed years distinct."""
import sys
from itertools import product
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'rsc/cses_db'))
from align_cses_additional_literacy_years import COVERAGE, RULE, VIEW, qualify, summary  # noqa: E402
from publish_cses_additional_literacy_years import person_query  # noqa: E402
from publish_cses_additional_literacy_years_v2 import storage_family  # noqa: E402
from validate_cses_additional_literacy_years import decide, equal  # noqa: E402


def record(**changes):
    return {**{'survey_wave':'2025','age_for_education_analysis':20,'education_age_eligible':True,
        'education_record_linked':True,'school_ever_native_code':1,'combined_source_value':None,
        'read_source_value':1,'write_source_value':1,'years_source_value':8},**changes}


def project(*rows):
    f = pd.DataFrame(rows)
    f.education_age_eligible = f.education_age_eligible.astype('boolean')
    for c in ['age_for_education_analysis','school_ever_native_code','combined_source_value',
              'read_source_value','write_source_value','years_source_value']:
        f[c] = f[c].astype(float)
    return qualify(f)


@pytest.mark.parametrize('wave',['1996','1997','1999'])
def test_legacy_combined_never_splits_or_invents_years(wave):
    f = project(record(survey_wave=wave,combined_source_value=1,read_source_value=None,
        write_source_value=None,years_source_value=None))
    assert f.combined_qualified.iloc[0]==1
    assert not f.combined_derived_from_components.iloc[0]
    for target in ['read','write','years']:
        assert f[f'{target}_qualified'].isna().all()
        assert f[f'{target}_status'].iloc[0]=='not_collected_in_selected_education_source'


@pytest.mark.parametrize('read,write,want',[(1,1,1),(1,2,0),(2,1,0),(2,2,0)])
def test_modern_combined_requires_both_valid_components(read,write,want):
    f = project(record(read_source_value=read,write_source_value=write))
    assert f.combined_qualified.iloc[0]==want and f.combined_derived_from_components.iloc[0]
    assert pd.isna(f.combined_source_value.iloc[0])


@pytest.mark.parametrize('reading',[1,2,None])
def test_undefined_writing_zero_never_becomes_no_or_known_combined(reading):
    f = project(record(read_source_value=reading,write_source_value=0))
    assert f.write_qualified.isna().all() and f.combined_qualified.isna().all()
    assert f.write_status.iloc[0]=='unrecognized_native_binary_code'


def test_missing_component_not_filled_from_other_no():
    f = project(record(read_source_value=2,write_source_value=None))
    assert f.read_qualified.iloc[0]==0 and f.combined_qualified.isna().all()


def test_literacy_independent_of_ever_attended():
    f = project(record(school_ever_native_code=2,years_source_value=None))
    assert f.read_qualified.iloc[0]==1 and f.combined_qualified.iloc[0]==1
    assert f.years_qualified.isna().all()
    assert f.years_status.iloc[0]=='documented_skip_no_years_value'
    assert not f.years_expected_by_route.iloc[0]


def test_recorded_zero_years_kept_but_skipped_null_never_imputed_zero():
    f = project(record(years_source_value=0),record(school_ever_native_code=2,years_source_value=None))
    assert f.years_qualified.iloc[0]==0 and pd.isna(f.years_qualified.iloc[1])
    assert not f.years_imputation_performed.any()


@pytest.mark.parametrize('years',[-1,1.5,31,98,99])
def test_years_integer_range_is_explicit_guard(years):
    f = project(record(age_for_education_analysis=100,years_source_value=years))
    assert f.years_status.iloc[0]=='outside_integer_0_30_guard'
    assert f.years_qualified.isna().all()


def test_years_above_age_excluded_not_corrected():
    f = project(record(age_for_education_analysis=4,years_source_value=5))
    assert f.years_source_value.iloc[0]==5 and f.years_exceed_source_age.iloc[0]
    assert f.years_status.iloc[0]=='years_exceed_source_age' and f.years_qualified.isna().all()


@pytest.mark.parametrize('ever,status',[(2,'years_value_outside_ever_attendance_route'),
    (None,'ever_attendance_unresolved'),(3,'unrecognized_ever_attendance_code')])
def test_years_need_valid_ever_yes(ever,status):
    f = project(record(school_ever_native_code=ever))
    assert f.years_status.iloc[0]==status and f.years_qualified.isna().all()
    assert f.read_qualified.iloc[0]==1


def test_age_or_record_exclusions_preserve_native_values():
    f = project(record(education_age_eligible=False),record(education_age_eligible=None),
                record(education_record_linked=False))
    assert f.read_qualified.isna().all() and f.years_qualified.isna().all()
    assert f.read_source_value.eq(1).all()
    assert f.read_status.tolist()==['outside_questionnaire_age_range','unknown_age_eligibility','missing_education_record']


def test_coverage_separates_age_eligible_from_expected_years_and_skips():
    f = project(record(),record(school_ever_native_code=2,years_source_value=None))
    rows = summary(f)
    assert len(rows)==8
    y = next(r for r in rows if r['age_band']=='questionnaire_age_eligible' and r['target']=='years')
    assert y['target_applicable_members']==2 and y['expected_response_by_route']==1
    assert y['qualified_records']==1 and y['documented_years_skips']==1
    assert y['qualified_yes'] is None


def test_sql_reads_native_json_and_does_not_replace_history():
    query = person_query(['survey_wave','years_qualified'])
    assert 'source_values' in query and 'school_ever_native_code' in query
    assert 'CREATE OR REPLACE' not in query and 'UPDATE ' not in query
    assert '(read_source_value=1 AND write_source_value=1)::integer' in query
    assert '(read_source_value=1 AND write_source_value=1)::bigint' not in query


def test_scalar_vector_agree_on_4000_boundary_combinations():
    cases,expected = [],[]
    for wave,ever,read,write,years in product(['1996','1997','1999','2023','2025'],
        [None,0,1,2,3],[None,0,1,2],[None,0,1,2],[None,-1,0,5,8,8.5,30,31,98,99]):
        combined = read if wave in ['1996','1997','1999'] else None
        cases.append(record(survey_wave=wave,school_ever_native_code=ever,combined_source_value=combined,
            read_source_value=read,write_source_value=write,years_source_value=years))
        expected.append(decide(wave,20,True,ever,combined,read,write,years))
    actual = project(*cases)
    assert len(actual)==4000
    for row,want in zip(actual.itertuples(index=False),expected,strict=True):
        assert all(equal(getattr(row,k),v) for k,v in want.items())


def test_publication_uses_existing_storage_family_vocabulary():
    assert storage_family(RULE)=='source_dictionary'
    assert storage_family(VIEW)==storage_family(COVERAGE)=='alignment_summary'
    with pytest.raises(ValueError,match='Unreviewed'):
        storage_family('public.anything')
