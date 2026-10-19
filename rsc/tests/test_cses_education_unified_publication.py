"""Publication stays additive and separates source facts from qualified indicators."""
import inspect
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'rsc/cses_db'))
import cses_education_all_waves_sql as policy  # noqa: E402
import publish_cses_education_unified as publisher  # noqa: E402
from pilot_cses_education_all_waves import EXTRA  # noqa: E402


def test_native_bridge_has_no_copied_qualified_outcomes():
    assert len(policy.SOURCE_TYPES)==12
    assert not any('qualified' in k or 'status' in k for k in policy.SOURCE_TYPES)
    assert 'years_native' in policy.SOURCE_TYPES


def test_seven_unique_additive_targets_with_natural_keys():
    assert len(set(policy.RELATIONS))==7
    assert set(policy.NATURAL_KEYS)==set(policy.RELATIONS)
    assert len(policy.PHYSICAL_TYPES)==4
    source = inspect.getsource(publisher.publish)
    assert 'CREATE VIEW' in source and 'CREATE TABLE' in source
    assert 'CREATE OR REPLACE' not in source and 'DROP ' not in source
    assert 'unchanged(conn' in source and 'conn.rollback()' in source


def test_person_sql_preserves_2017_and_two_conflict_guards():
    query = policy.person_query(['survey_wave','record_key'])
    assert "survey_wave<>'2017'" not in query
    assert query.count("THEN 'never_attended_positive_years_conflict'")==2
    assert "'unverified_same_wave_form_scope'" in query
    assert 'false AS cross_wave_equivalence_certified' in query
    assert 'false AS years_imputed' in query


def test_unknown_questionnaire_universe_not_zero_and_orphans_counted():
    assert "r.minimum_age IS NULL THEN NULL" in policy.coverage_query()
    assert 'n.linked+coalesce(o.rows,0)' in policy.matrix_query()
    assert policy.ORPHAN in policy.matrix_query()


def test_source_output_edges_have_exact_identity_and_cover_validation():
    waves = sorted(EXTRA|{'2004','2007','2009','2011-12','2013','2014','2016','2017','2019','2021'})
    datasets = {(w,k):i*10+j for i,w in enumerate(waves) for j,k in enumerate(['HL','ED','cover'])}
    datasets['1996','ED'] = datasets['1996','HL']
    edges = publisher.edges(datasets,{},pd.DataFrame({'survey_wave':waves}))
    assert sum(map(len,edges.values()))==141
    assert len(edges[policy.SOURCE])==20 and len(edges[policy.ORPHAN])==2
    assert len(edges[policy.BOOK])==14
    assert all(len(edges[r])==30 for r in [policy.VIEW,policy.COVERAGE,policy.MATRIX])
    assert sum(role=='validation' for rows in edges.values() for _,_,role in rows)==3


def test_staging_is_parameterized_and_read_only():
    tables = {r:[{k:None for k in fields}] for r,fields in policy.PHYSICAL_TYPES.items()}
    query,params,names = publisher.staging(tables)
    assert len(names)==4 and len(params)==sum(len(t) for t in policy.PHYSICAL_TYPES.values())
    assert 'unnest(' in query and '%s::' in query
    assert not any(k in query.upper() for k in ['CREATE ','INSERT ','UPDATE ','DELETE ','TEMP '])


def test_publication_authorization_does_not_rewrite_historical_pilot_scope():
    spec = json.loads(publisher.SPEC.read_text())
    old = json.loads((publisher.ROOT/'rsc/specs/cses_education_all_waves_pilot_v1.json').read_text())
    assert spec['publication_authorized'] and not spec['existing_outputs_replaceable']
    assert not old['database_publication_authorized']
