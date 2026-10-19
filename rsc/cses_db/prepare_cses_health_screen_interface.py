#!/usr/bin/env python3
"""Prepare and rollback-test health objects. Deliberately has NO publication/commit action."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd
from align_cses_additional_school import KEYS, ROOT, require
from audit_cses_health_release import CACHE, PILOT
from audit_cses_health_release import OUT as AUDIT
from build_cses_additional_waves import encoded, parquet_bytes, scalar
from cache_cses_questionnaires import file_sha, put, verify_manifest
from cses_health_screen_sql import (
    ADDITIONAL,
    COVERAGE,
    MATRIX,
    ORPHAN,
    RELATIONS,
    RULE,
    SOURCE,
    SOURCE_TYPES,
    VIEW,
    coverage_query,
    matrix_query,
    orphan_query,
    person_query,
    source_query,
)
from psycopg import sql
from psycopg.types.json import Jsonb
from publish_cses_2025_age import snapshot, unchanged
from publish_cses_geography_interface import SCHEMAS, connect

VERSION = 'cses-health-screen-interface-preflight-v2'
OUT = ROOT/'data/releases'/VERSION
BACKUP = ROOT/'data/backups/cses_health_screen_preflight_v2/before_health_screen.dump'
SUPPORT = ['rsc/cses_db/cses_health_screen_sql.py','rsc/cses_db/audit_cses_health_release.py',
    'rsc/cses_db/publish_cses_2025_age.py','rsc/cses_db/publish_cses_geography_interface.py',
    'rsc/cses_db/align_cses_additional_school.py','rsc/cses_db/build_cses_additional_waves.py',
    'rsc/cses_db/cache_cses_questionnaires.py']


def build():
    audit = json.loads((AUDIT/'report.json').read_text())
    require(audit['passed'] and audit['additional_negative_skip_conflicts']==0,'Annual audit required')
    require(audit['annual_sha256']==file_sha(AUDIT/'annual.json'),'Annual audit changed')
    pilot = json.loads((PILOT/'report.json').read_text())
    require(audit['pilot_report_sha256']==file_sha(PILOT/'report.json'),'Accepted pilot changed')
    receipt = json.loads((PILOT/'database-validation.json').read_text())
    require(receipt['passed'] and receipt['report_sha256']==file_sha(PILOT/'report.json'),'Independent acceptance required')
    inputs = {**pilot['inputs'],**audit['inputs']}
    for n,sha in pilot['artifacts'].items():
        inputs[str((PILOT/n).relative_to(ROOT))] = sha
    gaps = ROOT/'data/processing/cses/health_database_input_audit_v1/report.json'
    require(json.loads(gaps.read_text())['screen_value_mismatches']==0,'Database input audit required')
    for p in [AUDIT/'report.json',AUDIT/'annual.json',PILOT/'report.json',PILOT/'database-validation.json',gaps]:
        inputs[str(p.relative_to(ROOT))] = file_sha(p)
    for p,sha in inputs.items():
        require(file_sha(ROOT/p)==sha,'Input changed: '+p)
    verify_manifest(CACHE)
    annual = {r['survey_wave']:r for r in json.loads((AUDIT/'annual.json').read_text())}
    rules = [{'survey_wave':r['survey_wave'],'rule':r,
        'verified_form_path':annual[r['survey_wave']]['verified_form_path']}
        for r in json.loads((PILOT/'rules.json').read_text())]
    put(OUT/'rules.json',encoded(rules))
    source = pd.read_parquet(PILOT/'sources.parquet')
    extra = source.loc[source.survey_wave.isin(['1996','1997','1999','2023','2025']),list(SOURCE_TYPES)]
    require(len(extra)==212779,'Additional native-input grain differs')
    put(OUT/'additional_source.parquet',parquet_bytes(extra))
    e = {'version':VERSION,'publication_authorized':False,'inputs':inputs,
        'rule_sha256':file_sha(OUT/'rules.json'),'additional_source_sha256':file_sha(OUT/'additional_source.parquet'),
        'pilot_report_sha256':file_sha(PILOT/'report.json'),
        'counts':{RULE:15,ADDITIONAL:212779,SOURCE:571638,VIEW:571699,COVERAGE:45,MATRIX:15,ORPHAN:5},
        'scope':'Seven proposed additive objects only; no formal publication or metadata registration authorized.',
        'rehearsal_excludes':['Formal release registration','Production commit','Persistent grants or new objects']}
    put(OUT/'evidence.json',encoded(e))
    return e['counts']


def checked():
    e = json.loads((OUT/'evidence.json').read_text())
    require(not e['publication_authorized'],'This tool cannot publish')
    for p,sha in e['inputs'].items():
        require(file_sha(ROOT/p)==sha,'Input changed: '+p)
    require(e['rule_sha256']==file_sha(OUT/'rules.json'),'Rules changed')
    require(e['additional_source_sha256']==file_sha(OUT/'additional_source.parquet'),'Native bridge changed')
    verify_manifest(CACHE)
    f,source,orphan = [pd.read_parquet(PILOT/n).sort_values(KEYS).reset_index(drop=True)
        for n in ['members.parquet','sources.parquet','orphan_health.parquet']]
    require(len(f)==571699 and len(source)==571638 and len(orphan)==5,'Accepted grains changed')
    return f,source,orphan,json.loads((OUT/'rules.json').read_text()),e


def definitions(f):
    return {SOURCE:source_query(),VIEW:person_query(list(f)),COVERAGE:coverage_query(),
        MATRIX:matrix_query(),ORPHAN:orphan_query()}


def compare(conn,query,params,expected):
    offset = 0
    with conn.cursor(name='health_exact_cells') as c:
        c.execute(query+' ORDER BY survey_wave COLLATE "C",household_key COLLATE "C",record_key COLLATE "C"',params)
        while rows := c.fetchmany(5000):
            actual = pd.DataFrame(rows)[list(expected)].astype(expected.dtypes.to_dict())
            pd.testing.assert_frame_equal(actual,expected.iloc[offset:offset+len(rows)].reset_index(drop=True),check_exact=True)
            offset += len(rows)
    require(offset==len(expected),'Exact row count differs')


def checks(conn,f,source,orphan,rules,persistent=False):
    if persistent:
        prefix,params = '',None
        sr,mr,rr = SOURCE,VIEW,RULE
        require(conn.execute(f'SELECT * FROM {RULE} ORDER BY survey_wave').fetchall()==rules,'Persisted rules differ')
        compare(conn,f'SELECT * FROM {ADDITIONAL}',None,source.loc[source.survey_wave.isin(['1996','1997','1999','2023','2025'])].reset_index(drop=True))
    else:
        rr,sr,mr = 'stage_rule','stage_source','stage_members'
        extra = source.loc[source.survey_wave.isin(['1996','1997','1999','2023','2025'])]
        placeholders = ','.join('%s::'+v+'[]' for v in SOURCE_TYPES.values())
        prefix = f'''WITH {rr} AS MATERIALIZED (
          SELECT * FROM jsonb_to_recordset(%s::jsonb) AS t(survey_wave text,rule jsonb,verified_form_path text)),
          stage_additional AS MATERIALIZED (SELECT * FROM unnest({placeholders}) AS u({','.join(SOURCE_TYPES)})),
          {sr} AS MATERIALIZED ({source_query(rr,'stage_additional')}),
          {mr} AS MATERIALIZED ({person_query(list(f),sr,rr)}) '''
        params = [Jsonb(rules),*[[scalar(v) for v in extra[k]] for k in SOURCE_TYPES]]
    compare(conn,prefix+f'SELECT * FROM {sr}',params,source)
    compare(conn,prefix+f'SELECT * FROM {mr}',params,f)
    compare(conn,prefix+orphan_query(sr),params,orphan)
    coverage = conn.execute(prefix+'SELECT * FROM ('+coverage_query(mr)+') q ORDER BY survey_wave,age_band',params).fetchall()
    expected = sorted(json.loads((PILOT/'coverage.json').read_text()),key=lambda r:(r['survey_wave'],r['age_band']))
    require(coverage==expected,'Age-band coverage differs')
    matrix = conn.execute(prefix+'SELECT * FROM ('+matrix_query(mr,sr,rr)+') q ORDER BY survey_wave',params).fetchall()
    approved = {r['survey_wave']:r for r in json.loads((PILOT/'matrix.json').read_text())}
    for r in matrix:
        require(all(r[k]==v for k,v in approved[r['survey_wave']].items() if k in r),'Matrix statistics differ: '+r['survey_wave'])
        require(r['rule']==next(v['rule'] for v in rules if v['survey_wave']==r['survey_wave']),'Matrix rule differs')
    geo = conn.execute(f'''{prefix}SELECT count(*) n,count(*) FILTER(WHERE g.record_key IS NULL) missing
      FROM {mr} m LEFT JOIN cses_analysis.cses_person_geography_v2 g USING(survey_wave,household_key,record_key)''',params).fetchone()
    require(geo=={'n':571699,'missing':0},'Geography key cardinality differs')
    return {'passed':True,'source_rows_exact':len(source),'member_rows_exact':len(f),
        'member_columns_exact':len(f.columns),'all_cell_mismatches':0,'orphans_exact':len(orphan),
        'coverage_rows_exact':45,'matrix_rows_exact':15,'geography_keys_exact':571699,
        'strict_30d_records':308955,'strict_30d_yes':56262}


def absent(conn):
    require(not conn.execute("SELECT 1 FROM pg_event_trigger WHERE evtenabled<>'D'").fetchone(),'Active DDL trigger')
    for r in RELATIONS:
        require(conn.execute('SELECT to_regclass(%s) r',(r,)).fetchone()['r'] is None,'Target already exists: '+r)


def prepare():
    f,source,orphan,rules,e = checked()
    require(not BACKUP.exists() and not (OUT/'execution.json').exists(),'Preparation exists; preserve it')
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute("SET LOCAL statement_timeout='180s'")
        absent(conn)
        conn.execute('SET LOCAL ROLE mda_readonly')
        result = checks(conn,f,source,orphan,rules)
        conn.execute('RESET ROLE')
        before = snapshot(conn)
    BACKUP.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['/opt/homebrew/bin/pg_dump','-d','mda','-Fc',*[f'--schema={s}' for s in SCHEMAS],f'--file={BACKUP}'],check=True,timeout=600)
    subprocess.run(['/opt/homebrew/bin/pg_restore','--file=/dev/null',str(BACKUP)],check=True,timeout=600)
    with connect() as conn:
        unchanged(conn,before)
    plan = {'version':VERSION,'before':before,'preflight':result,'publication_authorized':False,
        'evidence_sha256':file_sha(OUT/'evidence.json'),'script_sha256':file_sha(Path(__file__)),
        'support_sha256':{p:file_sha(ROOT/p) for p in SUPPORT},'definitions':definitions(f),
        'backup':str(BACKUP.relative_to(ROOT)),'backup_sha256':file_sha(BACKUP),
        'backup_bytes':BACKUP.stat().st_size,'full_backup_decompression_verified':True,
        'backup_restore_into_server_tested':False,'formal_registry_rehearsed':False}
    put(OUT/'execution.json',encoded(plan))
    return {'prepared':True,**result,'backup_bytes':plan['backup_bytes']}


def rehearse():
    f,source,orphan,rules,e = checked()
    plan = json.loads((OUT/'execution.json').read_text())
    require(not plan['publication_authorized'],'Production commit forbidden')
    require(plan['script_sha256']==file_sha(Path(__file__)) and plan['evidence_sha256']==file_sha(OUT/'evidence.json'),'Prepared code/evidence changed')
    require(all(file_sha(ROOT/p)==sha for p,sha in plan['support_sha256'].items()),'Prepared support changed')
    require(plan['backup_sha256']==file_sha(BACKUP) and plan['definitions']==definitions(f),'Prepared backup/SQL changed')
    with connect(False) as conn:
        conn.execute("SET LOCAL statement_timeout='180s'")
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(VERSION,))
        for r in plan['before']['physical']:
            conn.execute(sql.SQL('LOCK TABLE {} IN SHARE MODE').format(sql.Identifier(*r.split('.'))))
        absent(conn)
        unchanged(conn,plan['before'])
        conn.execute(f'CREATE TABLE {RULE} (survey_wave text PRIMARY KEY,rule jsonb NOT NULL,verified_form_path text)')
        for r in rules:
            conn.execute(f'INSERT INTO {RULE} VALUES(%s,%s,%s)',(r['survey_wave'],Jsonb(r['rule']),r['verified_form_path']))
        conn.execute(f'CREATE TABLE {ADDITIONAL} ({",".join(k+" "+v for k,v in SOURCE_TYPES.items())},PRIMARY KEY({",".join(KEYS)}))')
        extra = pd.read_parquet(OUT/'additional_source.parquet')
        with conn.cursor().copy(f'COPY {ADDITIONAL} ({",".join(SOURCE_TYPES)}) FROM STDIN') as copy:
            for row in extra.itertuples(index=False,name=None):
                copy.write_row([scalar(v) for v in row])
        for relation,query in plan['definitions'].items():
            conn.execute(f'CREATE VIEW {relation} AS '+query)
        for relation in RELATIONS:
            conn.execute(f'GRANT SELECT ON {relation} TO mda_readonly')
        conn.execute('SET LOCAL ROLE mda_readonly')
        result = checks(conn,f,source,orphan,rules,True)
        conn.execute('RESET ROLE')
        unchanged(conn,plan['before'])
        conn.rollback()  # Unconditional: no path in this tool can commit created objects.
    with connect() as conn:
        absent(conn)
        unchanged(conn,plan['before'])
    receipt = {'rehearsed':True,'committed':False,'new_objects_remaining':0,
        'formal_registry_rehearsed':False,'old_rows_definitions_permissions_unchanged':True,
        'checks':result,'execution_sha256':file_sha(OUT/'execution.json')}
    put(OUT/'rehearsal.json',encoded(receipt))
    return receipt


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['build','prepare','rehearse'])
    action = p.parse_args().action
    print(json.dumps(build() if action=='build' else prepare() if action=='prepare' else rehearse(),indent=2))
