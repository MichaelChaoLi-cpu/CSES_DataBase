"""Orphan diagnosis respects original key encoding without inventing matches."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cses_db"))
from audit_cses_housing_orphans import identifier_matches  # noqa: E402


def test_checks_padded_household_and_person_prefix_independently():
    frame = pd.DataFrame({"hhid": [100209, None], "persid": [None, 10020901]})
    assert identifier_matches(frame, "2009", {"0100209"}) == {"0100209": {0, 1}}


def test_does_not_invent_nearby_household_match():
    frame = pd.DataFrame({"hhid": [100208, 100210], "persid": [10020801, 10021001]})
    assert identifier_matches(frame, "2009", {"0100209"}) == {"0100209": set()}


def test_2004_variable_width_is_preserved():
    frame = pd.DataFrame({"hhid": [201010, 1200904]})
    assert identifier_matches(frame, "2004", {"201010", "1200904"}) == {"201010": {0}, "1200904": {1}}
