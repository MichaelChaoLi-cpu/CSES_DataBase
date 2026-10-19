"""The pilot must not turn routing/missingness into observed answers."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'rsc/cses_db'))
from experiment_cses_alignment import age_summary, equality_errors, school_summary  # noqa: E402


def test_school_denominators_and_sensitivity_are_separate():
    d = pd.DataFrame({'currently_attending_school':[1,0,None,None],
                      'ever_attended_school':[1,1,0,1],'education_linked':[True]*4})
    r = school_summary(d)
    assert r['records']==4 and r['missing']==2 and r['other_missing']==1
    assert r['observed_response_yes_pct']==50
    assert r['all_person_lower_bound_pct']==25
    assert r['all_person_upper_bound_pct']==75
    assert r['sensitivity_never_skip_as_no_pct']==33.3333
    assert d.currently_attending_school.isna().sum()==2


def test_empty_band_is_not_zero_percent():
    d = pd.DataFrame(columns=['currently_attending_school','ever_attended_school','education_linked'])
    assert school_summary(d)['observed_response_yes_pct'] is None


def test_age_missing_invalid_and_topcode_values_are_distinct():
    r = age_summary(pd.Series([0,98,99,None,-98,3.5]))
    assert r['missing']==1 and r['value_98']==1 and r['value_99']==1
    assert r['noninteger_or_outside_0_120']==2
    assert equality_errors(pd.Series([1,None]),pd.Series([1,None]))==0
