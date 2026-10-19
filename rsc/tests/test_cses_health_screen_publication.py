"""Formal health publication must preserve scope and deduplicate true source identities."""
import inspect
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'rsc/cses_db'))
import publish_cses_health_screen as p  # noqa: E402
import publish_cses_health_screen_v2 as v2  # noqa: E402

WAVES = ['1996','1997','1999','2004','2007','2009','2011-12','2013','2014','2016','2017','2019','2021','2023','2025']


def identities():
    rows = []
    for i,w in enumerate(WAVES):
        ids = {'HH':i*10+1,'HL':i*10+2,'HEALTH':i*10+3}
        if w not in p.EXTRA:
            ids['HL'] = ids['HH']
        if w=='1996':
            ids['HL'] = ids['HEALTH']
        if w=='2023':
            ids['alternate'] = i*10+4
        if w=='2025':
            ids['cover'] = ids['HH']
        rows.extend({'survey_wave':w,'purpose':kind,'dataset_id':did} for kind,did in ids.items())
    return rows


def test_lineage_has_197_unique_edges():
    edges = p.lineage(identities())
    assert {r:len(v) for r,v in edges.items()}=={
        p.RULE:15,p.ADDITIONAL:11,p.SOURCE:31,p.VIEW:35,p.COVERAGE:35,p.MATRIX:35,p.ORPHAN:35}
    for rows in edges.values():
        assert len(rows)==len({(r['dataset_id'],r['contribution_role']) for r in rows})


def test_source_bridge_only_new_waves():
    rows = p.lineage(identities())[p.ADDITIONAL]
    assert {r['survey_wave'] for r in rows}==p.EXTRA
    assert {r['survey_wave'] for r in p.lineage(identities())[p.RULE]}==set(WAVES)


def test_shared_2025_cover_is_not_a_second_edge():
    rows = [r for r in p.lineage(identities())[p.VIEW] if r['survey_wave']=='2025']
    assert len(rows)==3 and all(r['contribution_role']=='source' for r in rows)


def test_2023_alternate_is_validation_not_screen_replacement():
    rows = [r for r in p.lineage(identities())[p.VIEW] if r['survey_wave']=='2023']
    assert len(rows)==4 and sum(r['contribution_role']=='validation' for r in rows)==1


def test_wave_counts_retain_zero_orphan_years():
    f = pd.DataFrame({'survey_wave':['2007','2007','2014']})
    s = pd.DataFrame({'survey_wave':['2007','2014','2014']})
    o = pd.DataFrame({'survey_wave':['2014']})
    counts = p.wave_counts(f,s,o)
    assert counts[p.ORPHAN]=={'2007':0,'2014':1}
    assert counts[p.COVERAGE]=={'2007':3,'2014':3}


def test_commit_requires_full_matching_rehearsal():
    q = inspect.getsource(p.publish)
    assert "receipt['full_registration_rehearsed']" in q and "receipt['execution_sha256']" in q
    assert 'if rehearse:\n            conn.rollback()' in q
    assert 'for relation in VIEW_ORDER:' in q
    assert 'SHARE ROW EXCLUSIVE' in q
    assert 'CREATE OR REPLACE' not in q and 'DROP TABLE' not in q and 'UPDATE cses_' not in q


def test_post_publication_validation_is_read_only():
    q = inspect.getsource(p.validate)
    assert 'REPEATABLE READ READ ONLY' in q and 'SET LOCAL ROLE mda_readonly' in q
    assert 'metadata_checks(conn' in q and 'data_checks(conn' in q


def test_actual_summary_views_are_checked():
    q = inspect.getsource(p.data_checks)
    assert "SELECT * FROM {COVERAGE}" in q and "SELECT * FROM {MATRIX}" in q and "SELECT * FROM {ORPHAN}" in q
    assert 'has_table_privilege' in q and 'HAVING count(*)>1' in q


def test_v2_unique_keys_follow_complete_exact_comparison():
    q = inspect.getsource(v2.data_checks)
    assert 'frame.duplicated(KEYS)' in q and 'frozen.prior.checks(' in q
    assert 'frozen.prior.compare(' in q and 'actual_cov==expected_cov' in q
    assert 'len({r[\'survey_wave\'] for r in actual_matrix})==15' in q
    assert 'HAVING count(*)>1 LIMIT 1' not in q


def test_v2_preserves_frozen_payload_and_full_rehearsal_gate():
    q = inspect.getsource(v2.publish)
    assert 'ANALYZE {relation}' in q and 'for relation in [RULE,ADDITIONAL]:' in q
    assert "plan['definitions'][relation]" in q and 'frozen.register(' in q
    assert "receipt['full_registration_rehearsed']" in q and 'conn.rollback()' in q
