"""Native age selection must not silently become a reference-date correction."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'rsc/cses_db'))
from publish_cses_2025_age import rows  # noqa: E402
from publish_cses_2025_age_v2 import calendar_check  # noqa: E402


def roster():
    return pd.DataFrame({'interview__id': ['abc'] * 4, 'q01ac04a': [20, 21, -98, 30],
                         'q01ac04b': [6, 6, -98, 2], 'q01ac04c': [2000, 2000, -98, 2000],
                         'age': [25, 25, 60, 25]})


def test_birthdays_mismatches_and_invalid_dates_stay_separate():
    raw = roster()
    original = raw.copy(deep=True)
    cover = pd.DataFrame({'interview__id': ['abc'], 's01q12_visit1': ['2025-06-20T12:34:56']})
    age, delta, status = calendar_check(raw, cover)
    assert age.iloc[:2].tolist() == [25, 24]
    assert delta.iloc[:2].tolist() == [0, 1]
    assert age.iloc[2:].isna().all()
    assert status.tolist() == ['matches_first_visit_calendar_age',
                              'differs_from_first_visit_calendar_age',
                              'incomplete_or_invalid_birth_date', 'incomplete_or_invalid_birth_date']
    pd.testing.assert_frame_equal(raw, original)


def test_unparseable_visit_is_not_zero_age():
    cover = pd.DataFrame({'interview__id': ['abc'], 's01q12_visit1': ['']})
    age, delta, status = calendar_check(roster(), cover)
    assert age.isna().all() and delta.isna().all()
    assert status.iloc[0] == 'missing_or_invalid_first_visit_date'
    assert status.iloc[2] == 'incomplete_or_invalid_birth_date'


def test_missing_or_duplicate_cover_fails_closed():
    cover = pd.DataFrame({'interview__id': ['other'], 's01q12_visit1': ['2025-01-01']})
    with pytest.raises(ValueError, match='missing household'):
        calendar_check(roster(), cover)
    with pytest.raises(ValueError, match='Duplicate'):
        calendar_check(roster(), pd.concat([cover, cover]))


def test_copy_keeps_nullable_integer_and_native_zero():
    frame = pd.DataFrame({'native': pd.Series([0, 105], dtype='Int64'),
                          'manual': pd.Series([pd.NA, 105], dtype='Int64')})
    assert rows(frame) == [[0, None], [105, 105]]


@pytest.mark.parametrize('day,month,year', [(-98, 6, 2000), (15, -98, 2000),
                                         (-98, -98, 2000), (0, 6, 2000),
                                         (15, 0, 2000), (20.5, 6, 2000), (29, 2, 2001)])
def test_unknown_or_normalized_birth_components_never_become_real_dates(day, month, year):
    raw = pd.DataFrame({'interview__id': ['abc'], 'q01ac04a': [day],
                        'q01ac04b': [month], 'q01ac04c': [year], 'age': [25]})
    cover = pd.DataFrame({'interview__id': ['abc'], 's01q12_visit1': ['2025-06-20']})
    age, delta, status = calendar_check(raw, cover)
    assert age.isna().all() and delta.isna().all()
    assert status.tolist() == ['incomplete_or_invalid_birth_date']
