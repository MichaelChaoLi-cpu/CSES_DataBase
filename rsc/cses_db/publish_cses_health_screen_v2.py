#!/usr/bin/env python3
"""Health publication revision: exact ordered-key proof, analyzed new tables, frozen SQL."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import publish_cses_health_screen as frozen
from align_cses_additional_school import KEYS, require
from build_cses_additional_waves import encoded, scalar
from cache_cses_questionnaires import file_sha, put
from cses_health_screen_sql import ADDITIONAL, COVERAGE, MATRIX, ORPHAN, RELATIONS, RULE, SOURCE, SOURCE_TYPES, VIEW
from psycopg import sql
from psycopg.types.json import Jsonb
from publish_cses_2025_age import APPEND, unchanged
from publish_cses_geography_interface import connect

OUT = frozen.OUT
EXECUTION = OUT/'execution-v2.json'


def build():
    values = frozen.checked_plan()
    plan = {**values[-1],'executor_revision':2,'script_sha256':file_sha(Path(__file__)),
        'parent_execution_sha256':file_sha(OUT/'execution.json'),
        'frozen_publisher_sha256':file_sha(Path(frozen.__file__)),
        'change':'Exact ordered full-row equality to unique native keys proves database-key uniqueness; avoid the redundant LIMIT anti-join aggregation. Analyze only the two new tables.',
        'superseded_attempt':'Full-registration v1 rehearsal timed out in the redundant orphan uniqueness query; transaction rolled back before registration.'}
    put(EXECUTION,encoded(plan))
    return {'prepared':True,'executor_revision':2,'objects':7,'source_edges':197,'backup_reused_after_hash_verification':True}


def checked_plan():
    values = frozen.checked_plan()
    plan = json.loads(EXECUTION.read_text())
    require(plan['publication_authorized'] and plan['script_sha256']==file_sha(Path(__file__)),'Prepared v2 code changed')
    require(plan['parent_execution_sha256']==file_sha(OUT/'execution.json')
        and plan['frozen_publisher_sha256']==file_sha(Path(frozen.__file__)),'Frozen parent changed')
    for key in ['before','definitions','wave_counts','backup_sha256','lineage_sha256','evidence_sha256']:
        require(plan[key]==values[-1][key],'Prepared content changed: '+key)
    return (*values[:-1],plan)


def data_checks(conn,f,source,orphan,rules,plan):
    # Full ordered-row equality below compares every actual key and every cell, including
    # cardinality. A duplicate database key cannot match a unique complete expected sequence.
    for frame in [f,source,orphan]:
        require(not frame[KEYS].isna().any().any() and not frame.duplicated(KEYS).any(),'Expected native key sequence is not unique')
    result = frozen.prior.checks(conn,f,source,orphan,rules,True)
    covariance = json.loads((frozen.prior.PILOT/'coverage.json').read_text())
    require(not pd.DataFrame(covariance).duplicated(['survey_wave','age_band']).any(),'Expected coverage keys duplicate')
    expected_cov = sorted(covariance,key=lambda r:(r['survey_wave'],r['age_band']))
    actual_cov = conn.execute(f'SELECT * FROM {COVERAGE} ORDER BY survey_wave,age_band').fetchall()
    require(actual_cov==expected_cov,'Stored coverage rows/keys differ')
    approved_matrix = {r['survey_wave']:r for r in json.loads((frozen.prior.PILOT/'matrix.json').read_text())}
    actual_matrix = conn.execute(f'SELECT * FROM {MATRIX} ORDER BY survey_wave').fetchall()
    require(len(actual_matrix)==15 and len({r['survey_wave'] for r in actual_matrix})==15,'Stored matrix keys differ')
    for r in actual_matrix:
        require(all(r[k]==v for k,v in approved_matrix[r['survey_wave']].items() if k in r),'Stored matrix differs')
        require(r['rule']==next(t['rule'] for t in rules if t['survey_wave']==r['survey_wave']),'Stored matrix rules differ')
    frozen.prior.compare(conn,f'SELECT * FROM {ORPHAN}',None,orphan)
    for relation in RELATIONS:
        schema,name = relation.split('.')
        columns = conn.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position',(schema,name)).fetchall()
        expected_columns = list(f) if relation==VIEW else list(source) if relation in [SOURCE,ADDITIONAL,ORPHAN] else ['survey_wave','rule','verified_form_path'] if relation==RULE else list(expected_cov[0]) if relation==COVERAGE else list(actual_matrix[0])
        require(set(r['column_name'] for r in columns)==set(expected_columns) and len(columns)==len(expected_columns),'Output columns differ: '+relation)
        # Counts are derived from the exact, complete outputs above, not another expensive
        # evaluation of the orphan anti-join with a different optimizer row goal.
        actual_counts = dict.fromkeys([r['survey_wave'] for r in rules],1) if relation in [RULE,MATRIX] else {
            str(w):int(n) for w,n in (f if relation==VIEW else source.loc[source.survey_wave.isin(frozen.EXTRA)] if relation==ADDITIONAL else source if relation==SOURCE else orphan if relation==ORPHAN else pd.DataFrame(actual_cov)).groupby('survey_wave').size().items()}
        require({w:n for w,n in actual_counts.items() if n}=={w:n for w,n in plan['wave_counts'][relation].items() if n},'Exact per-wave cardinality differs')
        privileges = conn.execute("SELECT has_table_privilege('mda_readonly',%s,'SELECT') s,has_table_privilege('mda_readonly',%s,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') w",(relation,relation)).fetchone()
        require(privileges=={'s':True,'w':False},'Read-only grants differ')
    return {**result,'actual_summary_views_checked':True,'source_output_edges':197,'read_only_grants_checked':7,
        'unique_database_keys_proved_by_exact_complete_row_equality':True,'publication_execution_sha256':file_sha(EXECUTION)}


def publish(rehearse=False):
    f,source,orphan,rules,parent,e,plan = checked_plan()
    if not rehearse:
        receipt = json.loads((OUT/'rehearsal-v2.json').read_text())
        require(receipt['rehearsed'] and not receipt['committed'] and receipt['full_registration_rehearsed']
            and receipt['execution_sha256']==file_sha(EXECUTION),'Matching full v2 rehearsal required')
    with connect(False) as conn:
        conn.execute("SET LOCAL statement_timeout='180s'")
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(frozen.prior.VERSION,))
        for relation in plan['before']['physical']:
            mode = 'SHARE ROW EXCLUSIVE' if relation in APPEND else 'SHARE'
            conn.execute(sql.SQL('LOCK TABLE {} IN {} MODE').format(sql.Identifier(*relation.split('.')),sql.SQL(mode)))
        frozen.absent(conn)
        unchanged(conn,plan['before'])
        manifest = frozen.source_manifest(conn,rules)
        expected = json.loads((OUT/'source-lineage.json').read_text())
        require(manifest==expected['source_identities'] and frozen.lineage(manifest)==expected['edges'],'Source catalog drift')
        conn.execute(f'CREATE TABLE {RULE} (survey_wave text PRIMARY KEY,rule jsonb NOT NULL,verified_form_path text)')
        for r in rules:
            conn.execute(f'INSERT INTO {RULE} VALUES(%s,%s,%s)',(r['survey_wave'],Jsonb(r['rule']),r['verified_form_path']))
        conn.execute(f'CREATE TABLE {ADDITIONAL} ({",".join(k+" "+v for k,v in SOURCE_TYPES.items())},PRIMARY KEY({",".join(KEYS)}))')
        extra = pd.read_parquet(OUT/'additional_source.parquet')
        with conn.cursor().copy(f'COPY {ADDITIONAL} ({",".join(SOURCE_TYPES)}) FROM STDIN') as copy:
            for row in extra.itertuples(index=False,name=None):
                copy.write_row([scalar(v) for v in row])
        for relation in [RULE,ADDITIONAL]:
            conn.execute(f'ANALYZE {relation}')
        for relation in frozen.VIEW_ORDER:
            conn.execute(f'CREATE VIEW {relation} AS '+plan['definitions'][relation])
        for relation in RELATIONS:
            conn.execute(f'GRANT SELECT ON {relation} TO mda_readonly')
            conn.execute(sql.SQL('COMMENT ON {} {} IS {}').format(sql.SQL('TABLE' if relation in [RULE,ADDITIONAL] else 'VIEW'),
                sql.Identifier(*relation.split('.')),sql.Literal(frozen.VERSION+': native values preserved; 2017 unverified and 2019 strict values withheld; no imputation or blanket equivalence.')))
        conn.execute('SET LOCAL ROLE mda_readonly')
        result = data_checks(conn,f,source,orphan,rules,plan)
        conn.execute('RESET ROLE')
        rid,storage = frozen.register(conn,e,plan,result)
        metadata = frozen.metadata_checks(conn,rid,storage,e,plan)
        unchanged(conn,plan['before'])
        if rehearse:
            conn.rollback()
    if rehearse:
        with connect() as conn:
            conn.execute("SET LOCAL statement_timeout='180s'")
            frozen.absent(conn)
            unchanged(conn,plan['before'])
    receipt = {'executor_revision':2,'rehearsed':rehearse,'committed':not rehearse,'release_id':rid,
        'full_registration_rehearsed':True,'checks':result,'metadata':metadata,'storage':storage,
        'old_rows_definitions_permissions_unchanged':True,'execution_sha256':file_sha(EXECUTION)}
    put(OUT/('rehearsal-v2.json' if rehearse else 'published.json'),encoded(receipt))
    return {k:v for k,v in receipt.items() if k!='storage'}


def validate():
    f,source,orphan,rules,parent,e,plan = checked_plan()
    pub = json.loads((OUT/'published.json').read_text())
    require(pub['committed'] and pub['execution_sha256']==file_sha(EXECUTION),'Matching commit required')
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute("SET LOCAL statement_timeout='180s'")
        unchanged(conn,plan['before'])
        conn.execute('SET LOCAL ROLE mda_readonly')
        require(conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on','Read-only required')
        require(frozen.source_manifest(conn,rules)==json.loads((OUT/'source-lineage.json').read_text())['source_identities'],'Source identity drift')
        result = data_checks(conn,f,source,orphan,rules,plan)
        metadata = frozen.metadata_checks(conn,pub['release_id'],pub['storage'],e,plan,True)
        summary = conn.execute('SELECT validation_summary FROM cses_meta.cses_load_run WHERE alignment_release_id=%s',(pub['release_id'],)).fetchone()['validation_summary']
        require(summary['checks']['publication_execution_sha256']==file_sha(EXECUTION),'Load execution provenance differs')
    receipt = {'validated':True,'executor_revision':2,'read_only':True,'role':'mda_readonly','checks':result,
        'metadata':metadata,'old_rows_definitions_permissions_unchanged':True,'published_sha256':file_sha(OUT/'published.json')}
    put(OUT/'validated.json',encoded(receipt))
    return receipt


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['build','rehearse','publish','validate'])
    action = p.parse_args().action
    print(json.dumps(build() if action=='build' else publish(action=='rehearse') if action in ['rehearse','publish'] else validate(),indent=2))
