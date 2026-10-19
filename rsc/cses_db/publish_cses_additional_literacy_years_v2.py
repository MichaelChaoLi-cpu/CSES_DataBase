#!/usr/bin/env python3
"""Correct storage-family registration without changing the frozen first execution plan."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from align_cses_additional_literacy_years import COVERAGE, OUT, ROOT, RULE, VERSION, VIEW
from align_cses_additional_school import KEYS, require
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put
from psycopg import sql
from psycopg.types.json import Jsonb
from publish_cses_2025_age import APPEND, digest, snapshot, unchanged
from publish_cses_additional_literacy_years import (
    RULE_TYPES,
    SUPPORT,
    absent,
    checked,
    checks,
    definitions,
)
from publish_cses_geography_interface import SCHEMAS, connect, fingerprint

BACKUP = ROOT/'data/backups/cses_additional_literacy_years_v2/before_literacy_years.dump'
EXECUTION = OUT/'execution-v2.json'
REHEARSAL = OUT/'rehearsal-v2.json'
SUPPORT_V2 = SUPPORT+['rsc/cses_db/publish_cses_additional_literacy_years.py']


def storage_family(relation):
    require(relation in [RULE,VIEW,COVERAGE],'Unreviewed output')
    return 'source_dictionary' if relation==RULE else 'alignment_summary'


def prepare():
    f,rules,e = checked()
    first = json.loads((OUT/'execution.json').read_text())
    require(first['script_sha256']==file_sha(ROOT/SUPPORT_V2[-1]),'Frozen first-attempt script changed')
    require(file_sha(ROOT/first['backup'])==first['backup_sha256'],'First backup changed')
    require(not BACKUP.exists() and not EXECUTION.exists(),'Existing v2 preparation; preserve it')
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        absent(conn)
        unchanged(conn,first['before'])
        result = checks(conn,f,rules,e,False)
        before = snapshot(conn)
    BACKUP.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['/opt/homebrew/bin/pg_dump','-d','mda','-Fc',*[f'--schema={s}' for s in SCHEMAS],f'--file={BACKUP}'],check=True,timeout=300)
    subprocess.run(['/opt/homebrew/bin/pg_restore','--file=/dev/null',str(BACKUP)],check=True,timeout=300)
    plan = {'version':VERSION,'publication_revision':2,'before':before,'preflight':result,
        'evidence_sha256':file_sha(OUT/'evidence.json'),'script_sha256':file_sha(Path(__file__)),
        'support_sha256':{p:file_sha(ROOT/p) for p in SUPPORT_V2},'backup':str(BACKUP.relative_to(ROOT)),
        'backup_sha256':file_sha(BACKUP),'full_backup_decompression_verified':True,'definitions':definitions(f),
        'supersedes_execution_sha256':file_sha(OUT/'execution.json'),
        'first_attempt_failure':'Rollback rehearsal rejected unsupported storage object_family alignment_rules; source_dictionary is the existing allowed family. First plan/code/backup retained; no schema constraint changed.',
        'storage_families':{r:storage_family(r) for r in [RULE,VIEW,COVERAGE]}}
    put(EXECUTION,encoded(plan))
    return {'prepared':True,'publication_revision':2,**result}


def register(conn,f,plan,result):
    rid = conn.execute("""INSERT INTO cses_meta.cses_alignment_release(mapping_version,status,description,specification_sha256,approved_at)
      VALUES(%s,'approved',%s,%s,now()) RETURNING alignment_release_id""",(VERSION,
      'Observed combined legacy literacy, separate modern components and marked conjunction; observed years only. Publisher revision 2 uses existing storage families.',file_sha(OUT/'evidence.json'))).fetchone()['alignment_release_id']
    spec = json.loads((ROOT/'rsc/specs/cses_additional_waves_v1.json').read_text())['waves']
    datasets = conn.execute("""SELECT s.survey_wave,d.member_path,d.dataset_id FROM cses_meta.cses_dataset d
      JOIN cses_meta.cses_survey s USING(survey_id) WHERE s.survey_wave=ANY(%s)""",(list(spec),)).fetchall()
    for relation,grain,key in [(RULE,'field_wave',['survey_wave','target']),(VIEW,'person_wave',KEYS),
                               (COVERAGE,'field_wave_age_band',['survey_wave','age_band','target'])]:
        schema,name = relation.split('.')
        n = conn.execute(f'SELECT count(*) n FROM {relation}').fetchone()['n']
        cols = conn.execute('SELECT count(*) n FROM information_schema.columns WHERE table_schema=%s AND table_name=%s',(schema,name)).fetchone()['n']
        sid = conn.execute("""INSERT INTO cses_meta.cses_storage_table(table_schema,table_name,object_family,module_code,
          analytical_grain,natural_key,row_count,column_count,relation_fingerprint) VALUES(%s,%s,%s,'ED',%s,%s,%s,%s,%s)
          RETURNING storage_table_id""",(schema,name,storage_family(relation),grain,key,n,cols,
          digest(fingerprint(conn,schema,name)))).fetchone()['storage_table_id']
        for wave,cfg in spec.items():
            members = {cfg['modules']['ED']['member']:'source'}
            if relation!=RULE:
                members[cfg['modules']['HL']['member']] = 'source'
                if wave=='2025':
                    members['S00_HHcover.dta'] = 'validation'
            for member,role in members.items():
                found = [d for d in datasets if d['survey_wave']==wave and d['member_path']==member]
                require(len(found)==1,'Source dataset registration differs')
                count = conn.execute(f'SELECT count(*) n FROM {relation} WHERE survey_wave=%s',(wave,)).fetchone()['n']
                conn.execute("""INSERT INTO cses_meta.cses_dataset_output(dataset_id,storage_table_id,alignment_release_id,contribution_role,output_row_count)
                  VALUES(%s,%s,%s,%s,%s)""",(found[0]['dataset_id'],sid,rid,role,count))
    conn.execute("""INSERT INTO cses_meta.cses_load_run(alignment_release_id,run_scope,source_manifest_sha256,status,row_counts,
      validation_summary,finished_at) VALUES(%s,%s,%s,'loaded',%s,%s,now())""",(rid,VERSION,file_sha(OUT/'evidence.json'),
      Jsonb({RULE:20,VIEW:len(f),COVERAGE:40}),Jsonb({'checks':result,'previous_rows_preserved':True,'backup_sha256':plan['backup_sha256'],'publication_revision':2})))
    return rid


def publish(rehearse=False):
    f,rules,e = checked()
    plan = json.loads(EXECUTION.read_text())
    require(plan['script_sha256']==file_sha(Path(__file__)) and plan['evidence_sha256']==file_sha(OUT/'evidence.json'),'Prepared code/evidence changed')
    require(plan['backup_sha256']==file_sha(BACKUP) and plan['definitions']==definitions(f),'Backup/SQL changed')
    require(all(file_sha(ROOT/p)==sha for p,sha in plan['support_sha256'].items()),'Support changed')
    require(plan['storage_families']=={r:storage_family(r) for r in [RULE,VIEW,COVERAGE]},'Storage family changed')
    if not rehearse:
        prior = json.loads(REHEARSAL.read_text())
        require(not prior['committed'] and prior['execution_sha256']==file_sha(EXECUTION),'Matching v2 rollback rehearsal required')
    with connect(False) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(VERSION,))
        for relation in plan['before']['physical']:
            conn.execute(sql.SQL('LOCK TABLE {} IN {} MODE').format(sql.Identifier(*relation.split('.')),
                sql.SQL('SHARE ROW EXCLUSIVE' if relation in APPEND else 'SHARE')))
        absent(conn)
        unchanged(conn,plan['before'])
        columns = sql.SQL(',').join(sql.SQL('{} {}').format(sql.Identifier(k),sql.SQL(v)) for k,v in RULE_TYPES.items())
        conn.execute(sql.SQL('CREATE TABLE {} ({},PRIMARY KEY(survey_wave,target))').format(sql.Identifier(*RULE.split('.')),columns))
        with conn.cursor().copy(sql.SQL('COPY {} ({}) FROM STDIN').format(sql.Identifier(*RULE.split('.')),
             sql.SQL(',').join(map(sql.Identifier,RULE_TYPES)))) as copy:
            for row in rules:
                copy.write_row([Jsonb(row[k]) if RULE_TYPES[k]=='jsonb' else row[k] for k in RULE_TYPES])
        for relation,query in definitions(f).items():
            conn.execute(sql.SQL('CREATE VIEW {} AS ').format(sql.Identifier(*relation.split('.')))+sql.SQL(query))
        for relation in [RULE,VIEW,COVERAGE]:
            conn.execute(sql.SQL('GRANT SELECT ON {} TO mda_readonly').format(sql.Identifier(*relation.split('.'))))
            conn.execute(sql.SQL('COMMENT ON {} {} IS {}').format(sql.SQL('TABLE' if relation==RULE else 'VIEW'),
                sql.Identifier(*relation.split('.')),sql.Literal(VERSION+': literacy instruments remain distinct; observed years only; original answers retained.')))
        result = checks(conn,f,rules,e)
        rid = register(conn,f,plan,result)
        unchanged(conn,plan['before'])
        if rehearse:
            conn.rollback()
    if rehearse:
        with connect() as conn:
            absent(conn)
            unchanged(conn,plan['before'])
    result = {'committed':not rehearse,'release_id':rid,'publication_revision':2,'checks':result,'execution_sha256':file_sha(EXECUTION)}
    put(REHEARSAL if rehearse else OUT/'published.json',encoded(result))
    return result


def validate():
    f,rules,e = checked()
    plan = json.loads(EXECUTION.read_text())
    pub = json.loads((OUT/'published.json').read_text())
    require(pub['committed'] and pub['execution_sha256']==file_sha(EXECUTION),'No confirmed v2 publication')
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        unchanged(conn,plan['before'])
        conn.execute('SET LOCAL ROLE mda_readonly')
        require(conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on','Read-only required')
        result = checks(conn,f,rules,e)
        metadata = conn.execute("""SELECT count(DISTINCT o.storage_table_id) outputs,count(*) edges FROM cses_meta.cses_dataset_output o
          JOIN cses_meta.cses_alignment_release r USING(alignment_release_id) WHERE r.mapping_version=%s""",(VERSION,)).fetchone()
        require(metadata=={'outputs':3,'edges':25},'Source-output metadata differs')
        require(conn.execute('SELECT status FROM cses_meta.cses_load_run WHERE alignment_release_id=%s',(pub['release_id'],)).fetchall()==[{'status':'loaded'}],'Load registry differs')
        families = conn.execute('SELECT table_schema,table_name,object_family FROM cses_meta.cses_storage_table WHERE (table_schema||%s||table_name)=ANY(%s)',('.',list(plan['storage_families']))).fetchall()
        require({r['table_schema']+'.'+r['table_name']:r['object_family'] for r in families}==plan['storage_families'],'Registered storage families differ')
    result = {'validated':True,'publication_revision':2,'role':'mda_readonly','read_only':True,
        'previous_rows_and_interfaces_unchanged':True,'checks':result,'metadata':metadata,
        'published_sha256':file_sha(OUT/'published.json')}
    put(OUT/'validated.json',encoded(result))
    return result


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['check','prepare','rehearse','publish','validate'])
    action = p.parse_args().action
    result = checked()[2] if action=='check' else prepare() if action=='prepare' else publish(action=='rehearse') if action in ['rehearse','publish'] else validate()
    print(json.dumps(result,indent=2))
