#!/usr/bin/env python3
"""Additive, exact-checked publication of the accepted fifteen-wave education pilot."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd
from align_cses_additional_school import KEYS, ROOT, require
from build_cses_additional_waves import encoded, parquet_bytes, scalar
from cache_cses_questionnaires import file_sha, put
from cses_education_all_waves_sql import (
    BOOK,
    COVERAGE,
    MATRIX,
    NATURAL_KEYS,
    ORPHAN,
    PHYSICAL_TYPES,
    RELATIONS,
    RULE,
    SOURCE,
    TARGETS,
    VIEW,
    coverage_query,
    matrix_query,
    person_query,
)
from pilot_cses_education_all_waves import EXTRA
from psycopg import sql
from psycopg.types.json import Jsonb
from publish_cses_2025_age import APPEND, digest, snapshot, unchanged
from publish_cses_geography_interface import SCHEMAS, connect, fingerprint

VERSION = 'cses-education-all-waves-interface-v1'
SPEC = ROOT/'rsc/specs/cses_education_all_waves_publication_v1.json'
PILOT = ROOT/'data/processing/cses/education_all_waves_pilot_v2'
OUT = ROOT/'data/releases'/VERSION
BACKUP = ROOT/'data/backups/cses_education_all_waves_v1/before_unified_education.dump'
SUPPORT = ['rsc/cses_db/cses_education_all_waves_sql.py',
    'rsc/cses_db/publish_cses_2025_age.py','rsc/cses_db/publish_cses_geography_interface.py',
    'rsc/cses_db/validate_cses_education_unified.py',
    'rsc/cses_db/align_cses_additional_school.py','rsc/cses_db/build_cses_additional_waves.py',
    'rsc/cses_db/cache_cses_questionnaires.py']
FILES = {SOURCE:'source.parquet',ORPHAN:'orphan.parquet',RULE:'rules.json',BOOK:'book.json'}


def records(frame):
    return [{k:scalar(v) for k,v in r.items()} for r in frame.to_dict('records')]


def ordered(rows, keys):
    return sorted(rows,key=lambda r:tuple(r[k] for k in keys))


def build():
    spec = json.loads(SPEC.read_text())
    require(spec['publication_authorized'] and not spec['existing_outputs_replaceable'],'Scope not authorized')
    require(file_sha(PILOT/'report.json')==spec['pilot_report_sha256'],'Accepted report changed')
    report = json.loads((PILOT/'report.json').read_text())
    for p,sha in report['inputs'].items():
        require(file_sha(ROOT/p)==sha,'Accepted input changed: '+p)
    for p,sha in report['artifacts'].items():
        require(file_sha(PILOT/p)==sha,'Accepted artifact changed: '+p)
    accepted = json.loads((PILOT/'database-validation.json').read_text())
    require(accepted['passed'] and accepted['report_sha256']==file_sha(PILOT/'report.json') and
        accepted['database']['geography_mismatches']==0,'Accepted pilot validation required')
    f = pd.read_parquet(PILOT/'members.parquet')
    source = f.loc[~f.survey_wave.isin(EXTRA),list(PHYSICAL_TYPES[SOURCE])].copy()
    orphan = pd.read_parquet(PILOT/'orphan_education.parquet')[list(PHYSICAL_TYPES[ORPHAN])]
    matrix = json.loads((PILOT/'matrix.json').read_text())
    rules = [{k:r[k] for k in PHYSICAL_TYPES[RULE]} for r in matrix]
    book = json.loads((PILOT/'level_codebook.json').read_text())
    for relation,frame in [(SOURCE,source),(ORPHAN,orphan)]:
        put(OUT/FILES[relation],parquet_bytes(frame))
    for relation,rows in [(RULE,rules),(BOOK,book)]:
        put(OUT/FILES[relation],encoded(rows))
    inputs = {**report['inputs'],str(SPEC.relative_to(ROOT)):file_sha(SPEC),
        str((PILOT/'report.json').relative_to(ROOT)):file_sha(PILOT/'report.json'),
        str((PILOT/'database-validation.json').relative_to(ROOT)):file_sha(PILOT/'database-validation.json')}
    for p,sha in report['artifacts'].items():
        inputs[str((PILOT/p).relative_to(ROOT))] = sha
    evidence = {'version':VERSION,'inputs':inputs,
        'artifacts':{name:file_sha(OUT/name) for name in FILES.values()},
        'counts':{SOURCE:len(source),ORPHAN:len(orphan),RULE:len(rules),BOOK:len(book),
                  VIEW:len(f),COVERAGE:360,MATRIX:120},
        'coverage':report['coverage'],'matrix':matrix,'pilot_preserved':True}
    put(OUT/'evidence.json',encoded(evidence))
    return evidence['counts']


def checked():
    e = json.loads((OUT/'evidence.json').read_text())
    for p,sha in e['inputs'].items():
        require(file_sha(ROOT/p)==sha,'Input changed: '+p)
    for p,sha in e['artifacts'].items():
        require(file_sha(OUT/p)==sha,'Artifact changed: '+p)
    f = pd.read_parquet(PILOT/'members.parquet')
    tables = {r:pd.read_parquet(OUT/name) if name.endswith('parquet') else json.loads((OUT/name).read_text())
              for r,name in FILES.items()}
    require(len(f)==571699 and not f.duplicated(KEYS).any(),'Roster grain changed')
    require({r:len(t) for r,t in tables.items()}=={r:e['counts'][r] for r in tables},'Physical grain changed')
    return f,tables,e


def definitions(f):
    return {VIEW:person_query(list(f)),COVERAGE:coverage_query(),MATRIX:matrix_query()}


def staging(tables):
    """Read-only typed array CTEs; no scratch tables and no giant SQL literals."""
    ctes,params,names = [],[],{}
    for i,(relation,types) in enumerate(PHYSICAL_TYPES.items()):
        name = 'stage_'+str(i)
        names[relation] = name
        rows = records(tables[relation]) if isinstance(tables[relation],pd.DataFrame) else tables[relation]
        placeholders = ','.join('%s::'+v+'[]' for v in types.values())
        ctes.append(f'{name} AS MATERIALIZED (SELECT * FROM unnest({placeholders}) AS u({",".join(types)}))')
        params.extend([[r[k] for r in rows] for k in types])
    return ','.join(ctes),params,names


def compare_person(conn,query,params,f):
    offset = 0
    with conn.cursor(name='education_exact_cells') as cursor:
        cursor.execute(query+' ORDER BY survey_wave COLLATE "C",household_key COLLATE "C",record_key COLLATE "C"',params)
        while rows := cursor.fetchmany(5000):
            actual = pd.DataFrame(rows).astype(f.dtypes.to_dict())
            expected = f.iloc[offset:offset+len(rows)].reset_index(drop=True)
            pd.testing.assert_frame_equal(actual,expected,check_exact=True)
            offset += len(rows)
    require(offset==len(f),'Person row count differs')


def checks(conn,f,tables,e,published=True):
    if published:
        compare_person(conn,f'SELECT * FROM {VIEW}',None,f)
        for relation,expected in tables.items():
            expected = records(expected) if isinstance(expected,pd.DataFrame) else expected
            query = f'SELECT * FROM {relation} ORDER BY '+','.join(NATURAL_KEYS[relation])
            if relation==SOURCE:
                expected_frame = tables[relation].sort_values(KEYS).reset_index(drop=True)
                compare_person(conn,f'SELECT * FROM {relation}',None,expected_frame)
            else:
                require(conn.execute(query).fetchall()==ordered(expected,NATURAL_KEYS[relation]),'Physical output differs: '+relation)
        for relation,expected in [(COVERAGE,e['coverage']),(MATRIX,e['matrix'])]:
            require(conn.execute(f'SELECT * FROM {relation} ORDER BY '+','.join(NATURAL_KEYS[relation])).fetchall()
                ==ordered(expected,NATURAL_KEYS[relation]),'SQL summary differs: '+relation)
    else:
        ctes,params,names = staging(tables)
        person = person_query(list(f),names[SOURCE],names[RULE],names[BOOK])
        prefix = 'WITH '+ctes+','+f'stage_members AS MATERIALIZED ({person}) '
        compare_person(conn,prefix+'SELECT * FROM stage_members',params,f)
        for relation,query,expected in [
            (COVERAGE,coverage_query('stage_members',names[RULE]),e['coverage']),
            (MATRIX,matrix_query('stage_members',names[RULE],names[ORPHAN]),e['matrix'])]:
            actual = conn.execute(prefix+'SELECT * FROM ('+query+') q ORDER BY '+','.join(NATURAL_KEYS[relation]),params).fetchall()
            require(actual==ordered(expected,NATURAL_KEYS[relation]),'Preflight summary differs: '+relation)
    return {'all_cells_match':True,'roster_records':len(f),'columns':len(f.columns),
        'matrix_rows':120,'denominator_rows':360,'orphans':4,
        'qualified_records':{t:int(f[t+'_qualified'].notna().sum()) for t in TARGETS}}


def source_datasets(conn):
    rows = conn.execute('SELECT d.dataset_id,s.survey_wave,d.member_path,d.nested_member_path FROM cses_meta.cses_dataset d JOIN cses_meta.cses_survey s USING(survey_id)').fetchall()
    alignment = json.loads((ROOT/'data/processing/cses/questionnaire_alignment_v1/alignment.json').read_text())
    f = pd.read_parquet(ROOT/'data/processing/cses/final_HL_CSES.parquet')
    from cses_hh_hl_common import snake_case
    f = f.rename(columns=snake_case)
    found = {}
    for wave,g in f.groupby('survey_wave'):
        for kind in ['HL','ED']:
            links = [r for r in alignment['source_links'] if r['survey_wave']==wave and
                (r['module_code']=='household_members' and r['member_path']==g.source_submodule.iloc[0].split('::')[0]
                 if kind=='HL' else r['module_code']=='education' and ['final_ED_CSES','can_read'] in r['canonical_keys'])]
            ids = {r['dataset_id'] for r in links}
            require(len(ids)==1,'Ambiguous frozen dataset: '+wave+kind)
            link = links[0]
            match = [r for r in rows if r['dataset_id']==link['dataset_id'] and r['survey_wave']==wave
                and r['member_path']==link['member_path'] and (r['nested_member_path'] or '')==(link['nested_member_path'] or '')]
            require(len(match)==1,'Historical source identity differs')
            found[wave,kind] = match[0]['dataset_id']
    spec = json.loads((ROOT/'rsc/specs/cses_additional_waves_v1.json').read_text())['waves']
    for wave,cfg in spec.items():
        members = {kind:cfg['modules'][kind]['member'] for kind in ['HL','ED']}
        if wave=='2025':
            members['cover'] = 'S00_HHcover.dta'
        for kind,member in members.items():
            match = [r for r in rows if r['survey_wave']==wave and r['member_path']==member]
            require(len(match)==1,'Additional source identity differs')
            found[wave,kind] = match[0]['dataset_id']
    return found


def edges(datasets,tables,f):
    waves = sorted(f.survey_wave.unique())
    result = {}
    for relation in RELATIONS:
        pairs = []
        for wave in waves:
            if relation==SOURCE and wave in EXTRA or relation==ORPHAN and wave not in ['2013','2014'] or relation==BOOK and wave=='2017':
                continue
            kinds = ['ED'] if relation in [ORPHAN,RULE,BOOK] else ['HL','ED']
            if relation in [VIEW,COVERAGE,MATRIX] and wave=='2025':
                kinds += ['cover']
            for kind in kinds:
                item = (wave,datasets[wave,kind],'validation' if kind=='cover' else 'source')
                if item not in pairs:
                    pairs.append(item)
        result[relation] = pairs
    require(sum(map(len,result.values()))==141,'Expected 141 source-output edges')
    return result


def absent(conn):
    require(not conn.execute("SELECT 1 FROM pg_event_trigger WHERE evtenabled<>'D'").fetchone(),'Active DDL trigger')
    for r in RELATIONS:
        require(conn.execute('SELECT to_regclass(%s) r',(r,)).fetchone()['r'] is None,'Target exists: '+r)
    require(not conn.execute('SELECT 1 FROM cses_meta.cses_alignment_release WHERE mapping_version=%s',(VERSION,)).fetchone(),'Release exists')


def prepare():
    f,tables,e = checked()
    require(not BACKUP.exists() and not (OUT/'execution.json').exists(),'Existing preparation; preserve it')
    acceptance = json.loads((OUT/'independent-local.json').read_text())
    require(acceptance['passed'] and acceptance['evidence_sha256']==file_sha(OUT/'evidence.json') and
        acceptance['validator_sha256']==file_sha(ROOT/SUPPORT[3]),'Independent native/scalar acceptance required')
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        absent(conn)
        links = edges(source_datasets(conn),tables,f)
        result = checks(conn,f,tables,e,False)
        before = snapshot(conn)
    BACKUP.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['/opt/homebrew/bin/pg_dump','-d','mda','-Fc',*[f'--schema={s}' for s in SCHEMAS],f'--file={BACKUP}'],check=True,timeout=600)
    subprocess.run(['/opt/homebrew/bin/pg_restore','--file=/dev/null',str(BACKUP)],check=True,timeout=600)
    plan = {'version':VERSION,'before':before,'preflight':result,'edges':links,
        'evidence_sha256':file_sha(OUT/'evidence.json'),'script_sha256':file_sha(Path(__file__)),
        'support_sha256':{p:file_sha(ROOT/p) for p in SUPPORT},'backup':str(BACKUP.relative_to(ROOT)),
        'backup_sha256':file_sha(BACKUP),'full_backup_decompression_verified':True,'definitions':definitions(f),
        'independent_local_sha256':file_sha(OUT/'independent-local.json')}
    put(OUT/'execution.json',encoded(plan))
    return {'prepared':True,**result}


def register(conn,f,tables,e,plan,result):
    links = edges(source_datasets(conn),tables,f)
    require(json.loads(json.dumps(links))==plan['edges'],'Source edges changed')
    rid = conn.execute("""INSERT INTO cses_meta.cses_alignment_release(mapping_version,status,description,specification_sha256,approved_at)
      VALUES(%s,'approved',%s,%s,now()) RETURNING alignment_release_id""",(VERSION,
      'Fifteen-wave roster-spine education interface; 2017 strict values withheld; unresolved positive-years inferences excluded; native values and orphan records preserved.',file_sha(OUT/'evidence.json'))).fetchone()['alignment_release_id']
    for relation in RELATIONS:
        schema,name = relation.split('.')
        frame = tables.get(relation)
        if isinstance(frame,list):
            counts = pd.DataFrame(frame).groupby('survey_wave').size().to_dict()
        elif isinstance(frame,pd.DataFrame):
            counts = frame.groupby('survey_wave').size().to_dict()
        else:
            counts = f.groupby('survey_wave').size().to_dict() if relation==VIEW else {w:24 if relation==COVERAGE else 8 for w in f.survey_wave.unique()}
        cols = conn.execute('SELECT count(*) n FROM information_schema.columns WHERE table_schema=%s AND table_name=%s',(schema,name)).fetchone()['n']
        sid = conn.execute("""INSERT INTO cses_meta.cses_storage_table(table_schema,table_name,object_family,module_code,
          analytical_grain,natural_key,row_count,column_count,relation_fingerprint) VALUES(%s,%s,%s,'ED',%s,%s,%s,%s,%s)
          RETURNING storage_table_id""",(schema,name,'source_dictionary' if relation in PHYSICAL_TYPES else 'alignment_summary',
          'person_wave' if relation in [SOURCE,ORPHAN,VIEW] else 'field_wave_age_band' if relation==COVERAGE else 'field_wave_code' if relation==BOOK else 'field_wave',
          NATURAL_KEYS[relation],e['counts'][relation],cols,digest(fingerprint(conn,schema,name)))).fetchone()['storage_table_id']
        for wave,dataset,role in links[relation]:
            conn.execute("""INSERT INTO cses_meta.cses_dataset_output(dataset_id,storage_table_id,alignment_release_id,contribution_role,output_row_count)
              VALUES(%s,%s,%s,%s,%s)""",(dataset,sid,rid,role,int(counts[wave])))
    conn.execute("""INSERT INTO cses_meta.cses_load_run(alignment_release_id,run_scope,source_manifest_sha256,status,row_counts,
      validation_summary,finished_at) VALUES(%s,%s,%s,'loaded',%s,%s,now())""",(rid,VERSION,file_sha(OUT/'evidence.json'),
      Jsonb(e['counts']),Jsonb({'checks':result,'previous_rows_preserved':True,'backup_sha256':plan['backup_sha256']})))
    return rid


def publish(rehearse=False):
    f,tables,e = checked()
    plan = json.loads((OUT/'execution.json').read_text())
    require(plan['script_sha256']==file_sha(Path(__file__)) and plan['evidence_sha256']==file_sha(OUT/'evidence.json'),'Prepared code/evidence changed')
    require(plan['backup_sha256']==file_sha(BACKUP) and plan['definitions']==definitions(f),'Backup/SQL changed')
    require(all(file_sha(ROOT/p)==sha for p,sha in plan['support_sha256'].items()),'Support changed')
    require(plan['independent_local_sha256']==file_sha(OUT/'independent-local.json'),'Independent acceptance changed')
    if not rehearse:
        receipt = json.loads((OUT/'rehearsal.json').read_text())
        require(not receipt['committed'] and receipt['execution_sha256']==file_sha(OUT/'execution.json'),'Matching rollback rehearsal required')
    with connect(False) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(VERSION,))
        for relation in plan['before']['physical']:
            conn.execute(sql.SQL('LOCK TABLE {} IN {} MODE').format(sql.Identifier(*relation.split('.')),
                sql.SQL('SHARE ROW EXCLUSIVE' if relation in APPEND else 'SHARE')))
        absent(conn)
        unchanged(conn,plan['before'])
        for relation,types in PHYSICAL_TYPES.items():
            cols = ','.join(k+' '+v for k,v in types.items())
            conn.execute(f'CREATE TABLE {relation} ({cols},PRIMARY KEY({",".join(NATURAL_KEYS[relation])}))')
            rows = records(tables[relation]) if isinstance(tables[relation],pd.DataFrame) else tables[relation]
            with conn.cursor().copy(f'COPY {relation} ({",".join(types)}) FROM STDIN') as copy:
                for r in rows:
                    copy.write_row([r[k] for k in types])
        for relation,query in definitions(f).items():
            conn.execute(f'CREATE VIEW {relation} AS '+query)
        for relation in RELATIONS:
            conn.execute(f'GRANT SELECT ON {relation} TO mda_readonly')
            conn.execute(sql.SQL('COMMENT ON {} {} IS {}').format(sql.SQL('TABLE' if relation in PHYSICAL_TYPES else 'VIEW'),
                sql.Identifier(*relation.split('.')),sql.Literal(VERSION+': 2017 strict qualification withheld; no blanket equivalence certification; native answers preserved.')))
        result = checks(conn,f,tables,e)
        rid = register(conn,f,tables,e,plan,result)
        unchanged(conn,plan['before'])
        if rehearse:
            conn.rollback()
    if rehearse:
        with connect() as conn:
            absent(conn)
            unchanged(conn,plan['before'])
    result = {'committed':not rehearse,'release_id':rid,'checks':result,'execution_sha256':file_sha(OUT/'execution.json')}
    put(OUT/('rehearsal.json' if rehearse else 'published.json'),encoded(result))
    return result


def validate():
    f,tables,e = checked()
    plan = json.loads((OUT/'execution.json').read_text())
    pub = json.loads((OUT/'published.json').read_text())
    require(pub['committed'] and pub['execution_sha256']==file_sha(OUT/'execution.json'),'Confirmed publication required')
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        unchanged(conn,plan['before'])
        conn.execute('SET LOCAL ROLE mda_readonly')
        require(conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on','Read-only required')
        result = checks(conn,f,tables,e)
        metadata = conn.execute('SELECT count(DISTINCT storage_table_id) outputs,count(*) edges FROM cses_meta.cses_dataset_output WHERE alignment_release_id=%s',(pub['release_id'],)).fetchone()
        require(metadata=={'outputs':7,'edges':141},'Metadata grain differs')
        require(conn.execute('SELECT status FROM cses_meta.cses_load_run WHERE alignment_release_id=%s',(pub['release_id'],)).fetchall()==[{'status':'loaded'}],'Load registry differs')
    result = {'validated':True,'role':'mda_readonly','read_only':True,'previous_rows_and_interfaces_unchanged':True,
        'checks':result,'metadata':metadata,'published_sha256':file_sha(OUT/'published.json')}
    put(OUT/'validated.json',encoded(result))
    return result


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['build','check','prepare','rehearse','publish','validate'])
    action = p.parse_args().action
    result = build() if action=='build' else checked()[2]['counts'] if action=='check' else prepare() if action=='prepare' else publish(action=='rehearse') if action in ['rehearse','publish'] else validate()
    print(json.dumps(result,indent=2))
