#!/usr/bin/env python3
"""Replay the frozen health preflight in dependency order, always rolling back."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import prepare_cses_health_screen_interface as prior
from align_cses_additional_school import KEYS, ROOT, require
from build_cses_additional_waves import encoded, scalar
from cache_cses_questionnaires import file_sha, put
from cses_health_screen_sql import ADDITIONAL, COVERAGE, MATRIX, ORPHAN, RELATIONS, RULE, SOURCE, SOURCE_TYPES, VIEW
from psycopg import sql
from psycopg.types.json import Jsonb
from publish_cses_2025_age import unchanged
from publish_cses_geography_interface import connect

OUT = ROOT/'data/releases/cses-health-screen-interface-rehearsal-v3'
# Never infer DDL order from a JSON object: canonical encoding sorts its keys.
VIEW_ORDER = [SOURCE,VIEW,COVERAGE,MATRIX,ORPHAN]


def checked_parent():
    f,source,orphan,rules,e = prior.checked()
    plan = json.loads((prior.OUT/'execution.json').read_text())
    require(not plan['publication_authorized'],'No publication authority')
    require(plan['script_sha256']==file_sha(Path(prior.__file__)),'Frozen parent code changed')
    require(plan['evidence_sha256']==file_sha(prior.OUT/'evidence.json'),'Frozen evidence changed')
    require(all(file_sha(ROOT/p)==sha for p,sha in plan['support_sha256'].items()),'Frozen support changed')
    require(plan['backup_sha256']==file_sha(prior.BACKUP),'Frozen backup changed')
    require(plan['definitions']==prior.definitions(f) and set(VIEW_ORDER)==set(plan['definitions']),'Frozen SQL changed')
    return f,source,orphan,rules,plan


def build():
    checked_parent()
    plan = {'publication_authorized':False,'script_sha256':file_sha(Path(__file__)),
        'parent_execution_path':str((prior.OUT/'execution.json').relative_to(ROOT)),
        'parent_execution_sha256':file_sha(prior.OUT/'execution.json'),
        'view_dependency_order':VIEW_ORDER,'formal_registry_rehearsed':False,
        'change':'Explicit dependency order only; frozen SQL, evidence, backup and eligibility unchanged.',
        'prior_attempt':'Transaction aborted on CREATE VIEW dependency; no successful rehearsal receipt.'}
    put(OUT/'execution.json',encoded(plan))
    return {'prepared':True,'commits_permitted':False,'view_dependency_order':VIEW_ORDER}


def rehearse():
    f,source,orphan,rules,parent = checked_parent()
    plan = json.loads((OUT/'execution.json').read_text())
    require(not plan['publication_authorized'] and plan['script_sha256']==file_sha(Path(__file__)),'Rehearsal code changed')
    require(plan['parent_execution_sha256']==file_sha(prior.OUT/'execution.json'),'Parent execution changed')
    require(plan['view_dependency_order']==VIEW_ORDER,'Dependency order changed')
    with connect(False) as conn:
        conn.execute("SET LOCAL statement_timeout='180s'")
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(prior.VERSION,))
        for relation in parent['before']['physical']:
            conn.execute(sql.SQL('LOCK TABLE {} IN SHARE MODE').format(sql.Identifier(*relation.split('.'))))
        prior.absent(conn)
        unchanged(conn,parent['before'])
        conn.execute(f'CREATE TABLE {RULE} (survey_wave text PRIMARY KEY,rule jsonb NOT NULL,verified_form_path text)')
        for r in rules:
            conn.execute(f'INSERT INTO {RULE} VALUES(%s,%s,%s)',(r['survey_wave'],Jsonb(r['rule']),r['verified_form_path']))
        conn.execute(f'CREATE TABLE {ADDITIONAL} ({",".join(k+" "+v for k,v in SOURCE_TYPES.items())},PRIMARY KEY({",".join(KEYS)}))')
        extra = pd.read_parquet(prior.OUT/'additional_source.parquet')
        with conn.cursor().copy(f'COPY {ADDITIONAL} ({",".join(SOURCE_TYPES)}) FROM STDIN') as copy:
            for row in extra.itertuples(index=False,name=None):
                copy.write_row([scalar(v) for v in row])
        for relation in VIEW_ORDER:
            conn.execute(f'CREATE VIEW {relation} AS '+parent['definitions'][relation])
        for relation in RELATIONS:
            conn.execute(f'GRANT SELECT ON {relation} TO mda_readonly')
        conn.execute('SET LOCAL ROLE mda_readonly')
        result = prior.checks(conn,f,source,orphan,rules,True)
        conn.execute('RESET ROLE')
        unchanged(conn,parent['before'])
        conn.rollback()
    with connect() as conn:
        prior.absent(conn)
        unchanged(conn,parent['before'])
    receipt = {'rehearsed':True,'committed':False,'new_objects_remaining':0,
        'old_rows_definitions_permissions_unchanged':True,'formal_registry_rehearsed':False,
        'checks':result,'execution_sha256':file_sha(OUT/'execution.json'),
        'parent_execution_sha256':plan['parent_execution_sha256']}
    put(OUT/'rehearsal.json',encoded(receipt))
    return receipt


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['build','rehearse'])
    print(json.dumps(build() if p.parse_args().action=='build' else rehearse(),indent=2))
