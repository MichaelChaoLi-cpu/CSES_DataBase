"""Safe additive geography interface and exact recovery source invariants."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
from publish_cses_geography_interface import COVERAGE, HH, HL, SHA, definitions, source_rows  # noqa: E402


def test_recovery_rows_have_source_keys_and_no_psu_imputation():
    rows = source_rows()
    assert len(rows) == 14984
    assert len({(r[0],r[1]) for r in rows}) == len(rows)
    assert len({r[2] for r in rows}) == 900
    assert len({tuple(r[3:7]) for r in rows}) == 867
    assert all(r[0] == '2004' and r[8] == SHA and r[7] > 0 for r in rows)
    assert all(len(code) == 2 and code.isdigit() for r in rows for code in r[3:7])


def test_views_are_additive_left_joins_not_map_identity_claims():
    queries = definitions()
    assert set(queries) == {HH, HL, COVERAGE}
    assert 'LEFT JOIN cses_data.cses_geography_2004_source_v1' in queries[HH]
    assert 'h.household_id=s.household_id' in queries[HH]
    assert 'p.household_id=g.household_id' in queries[HL]
    assert 'p.survey_wave=g.survey_wave' in queries[HL]
    assert 'false AS historical_identity_verified' in queries[HH]
    assert 'not_verified_no_village_geometry_reference' in queries[HH]
    assert 'not_evaluated_in_this_interface' in queries[HH]
    assert not any(word in '\n'.join(queries.values()).upper() for word in ['DELETE ', 'UPDATE ', 'DROP '])
