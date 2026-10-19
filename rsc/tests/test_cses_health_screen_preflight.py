"""Safety and SQL-contract tests for non-publishing health preparation."""
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'rsc/cses_db'))
from audit_cses_health_release import full_no_range  # noqa: E402
from cses_health_screen_sql import (  # noqa: E402
    RELATIONS,
    RULE,
    SOURCE,
    VIEW,
    coverage_query,
    matrix_query,
    orphan_query,
    person_query,
    source_query,
)
from prepare_cses_health_screen_interface import rehearse  # noqa: E402
from rehearse_cses_health_screen_v3 import VIEW_ORDER  # noqa: E402
from rehearse_cses_health_screen_v3 import rehearse as rehearse_v3  # noqa: E402


@pytest.mark.parametrize(('wave','added'),[
    ('1999',['p8c16','p8c17','p8c18']),
    ('2004',['q14a08','q14a09','q14a10','q14a11','q14a12']),
    ('2017',[]),('2025',[]),
])
def test_full_skip_range_is_narrow(wave,added):
    assert full_no_range({'survey_wave':wave,'no_followups':['x']})==['x',*added]


def test_source_preserves_all_native_records_and_variants():
    q = source_query('test_rules')
    assert 'UNION ALL' in q and 'test_rules' in q
    assert 'source_variant_conflict' not in q  # Never discard whole 2023 respondent for a different field.
    assert 'cses_health_screen_additional_source_v1' in q
    assert 'branch_11_native' in q


def test_scalar_priority_and_no_imputation():
    q = person_query(['survey_wave','screen_status'],'test_sources','test_rules')
    positions = [q.index(s) for s in ['WHEN NOT screen_available','WHEN NOT form_scope_reviewed',
        'WHEN NOT health_linked','WHEN NOT hh_link_matched','WHEN screen_native IS NULL',
        "WHEN rule->'missing_codes'",'WHEN screen_binary_native IS NULL',
        'WHEN source_form_code_conflict','WHEN screen_variant_conflict','WHEN no_with_followup']]
    assert positions==sorted(positions)
    assert 'LEFT JOIN test_sources' in q
    assert 'false AS screen_imputed' in q and 'false AS cross_wave_equivalence_certified' in q


def test_coverage_has_three_age_bands():
    q = coverage_query('members')
    assert all(x in q for x in ['all_members','ages_6_17','ages_15_plus'])
    assert 'FILTER(WHERE inside)' in q and 'GROUP BY survey_wave,age_band' in q


def test_matrix_and_orphans_preserve_native_evidence():
    assert 'screen_native_counts' in matrix_query() and 'screen_status_counts' in matrix_query()
    assert 'NOT EXISTS' in orphan_query() and 'record_key=s.record_key' in orphan_query()
    assert len(RELATIONS)==7 and len(set(RELATIONS))==7
    assert RULE in RELATIONS and SOURCE in RELATIONS and VIEW in RELATIONS


def test_rehearsal_never_commits_or_registers():
    q = inspect.getsource(rehearse)
    assert 'conn.rollback()' in q and 'conn.commit(' not in q
    assert 'cses_meta.cses_alignment_release' not in q
    assert "choices=['build','prepare','rehearse']" in inspect.getsource(__import__('prepare_cses_health_screen_interface'))


def test_v3_ddl_follows_dependencies_not_json_sort_order():
    assert VIEW_ORDER[0]==SOURCE and VIEW_ORDER[1]==VIEW
    assert set(VIEW_ORDER)==set(RELATIONS)-{RULE,'cses_data.cses_health_screen_additional_source_v1'}
    q = inspect.getsource(rehearse_v3)
    assert 'for relation in VIEW_ORDER:' in q
    assert "parent['definitions'].items()" not in q


def test_v3_has_only_unconditional_rollback():
    q = inspect.getsource(rehearse_v3)
    assert 'conn.rollback()' in q and 'conn.commit(' not in q
    assert 'cses_meta.cses_alignment_release' not in q
