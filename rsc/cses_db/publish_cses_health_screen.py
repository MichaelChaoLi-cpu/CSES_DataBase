#!/usr/bin/env python3
"""Publish exactly the accepted health objects with additive, fully checked lineage metadata."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd
import prepare_cses_health_screen_interface as prior
import rehearse_cses_health_screen_v3 as rehearsal
from align_cses_additional_school import KEYS, ROOT, require
from build_cses_additional_waves import encoded, scalar
from cache_cses_questionnaires import file_sha, put
from cses_health_screen_sql import ADDITIONAL, COVERAGE, MATRIX, ORPHAN, RELATIONS, RULE, SOURCE, SOURCE_TYPES, VIEW
from cses_hh_hl_common import snake_case
from psycopg import sql
from psycopg.types.json import Jsonb
from publish_cses_2025_age import APPEND, digest, snapshot, unchanged
from publish_cses_geography_interface import SCHEMAS, connect, fingerprint

VERSION = 'cses-health-screen-interface-v1'
SPEC = ROOT/'rsc/specs/cses_health_screen_publication_v1.json'
OUT = ROOT/'data/releases'/VERSION
BACKUP = ROOT/'data/backups/cses_health_screen_publication_v1/before_health_screen.dump'
EXTRA = {'1996','1997','1999','2023','2025'}
VIEW_ORDER = [SOURCE,VIEW,COVERAGE,MATRIX,ORPHAN]
NATURAL_KEYS = {r:KEYS for r in [ADDITIONAL,SOURCE,VIEW,ORPHAN]} | {
    RULE:['survey_wave'],MATRIX:['survey_wave'],COVERAGE:['survey_wave','age_band']}
SUPPORT = list(dict.fromkeys([*prior.SUPPORT,'rsc/cses_db/prepare_cses_health_screen_interface.py',
    'rsc/cses_db/rehearse_cses_health_screen_v3.py','rsc/cses_db/cses_hh_hl_common.py']))


def build():
    spec = json.loads(SPEC.read_text())
    require(spec['publication_authorized'] and not spec['existing_outputs_replaceable'],'Publication not authorized')
    f,source,orphan,rules,parent = rehearsal.checked_parent()
    require(spec['pilot_report_sha256']==file_sha(prior.PILOT/'report.json'),'Accepted pilot changed')
    require(spec['preflight_execution_sha256']==file_sha(prior.OUT/'execution.json'),'Accepted preflight changed')
    require(spec['object_rehearsal_sha256']==file_sha(rehearsal.OUT/'rehearsal.json'),'Accepted rehearsal changed')
    accepted = json.loads((rehearsal.OUT/'rehearsal.json').read_text())
    execution = json.loads((rehearsal.OUT/'execution.json').read_text())
    require(accepted['rehearsed'] and not accepted['committed'] and accepted['new_objects_remaining']==0
        and accepted['checks']['all_cell_mismatches']==0,'Successful object rehearsal required')
    require(accepted['execution_sha256']==file_sha(rehearsal.OUT/'execution.json')
        and execution['script_sha256']==file_sha(Path(rehearsal.__file__)),'Object rehearsal code changed')
    for n in ['rules.json','additional_source.parquet']:
        put(OUT/n,(prior.OUT/n).read_bytes())
    inputs = {str(p.relative_to(ROOT)):file_sha(p) for p in [SPEC,prior.OUT/'execution.json',
        prior.OUT/'evidence.json',rehearsal.OUT/'execution.json',rehearsal.OUT/'rehearsal.json']}
    e = {'version':VERSION,'publication_authorized':True,'inputs':inputs,
        'artifacts':{n:file_sha(OUT/n) for n in ['rules.json','additional_source.parquet']},
        'counts':json.loads((prior.OUT/'evidence.json').read_text())['counts'],
        'pilot_report_sha256':spec['pilot_report_sha256'],'view_dependency_order':VIEW_ORDER,
        'limitations_unchanged':True,'historical_outputs_preserved':True}
    put(OUT/'evidence.json',encoded(e))
    return e['counts']


def checked():
    e = json.loads((OUT/'evidence.json').read_text())
    require(e['publication_authorized'],'Publication not authorized')
    for p,sha in e['inputs'].items():
        require(file_sha(ROOT/p)==sha,'Publication input changed: '+p)
    for n,sha in e['artifacts'].items():
        require(file_sha(OUT/n)==sha,'Publication artifact changed: '+n)
    f,source,orphan,rules,parent = rehearsal.checked_parent()
    require(e['view_dependency_order']==VIEW_ORDER==rehearsal.VIEW_ORDER,'Dependency order changed')
    require(file_sha(OUT/'additional_source.parquet')==file_sha(prior.OUT/'additional_source.parquet')
        and json.loads((OUT/'rules.json').read_text())==rules,'Approved source/rules changed')
    return f,source,orphan,rules,parent,e


def source_manifest(conn,rules):
    catalog = conn.execute('''SELECT d.dataset_id,s.survey_wave,d.member_path,d.nested_member_path,d.row_count,
      a.relative_path AS archive,a.sha256 AS archive_sha256 FROM cses_meta.cses_dataset d
      JOIN cses_meta.cses_survey s USING(survey_id) JOIN cses_meta.cses_source_archive a USING(source_archive_id)''').fetchall()
    wanted = {}
    for kind in ['HH','HL']:
        f = pd.read_parquet(ROOT/f'data/processing/cses/final_{kind}_CSES.parquet').rename(columns=snake_case)
        for wave,g in f.groupby('survey_wave'):
            paths = g.source_submodule.unique().tolist()
            require(len(paths)==1,'Ambiguous historical roster source')
            wanted[wave,kind] = paths[0].split('::')
    extra = json.loads((ROOT/'rsc/specs/cses_additional_waves_v1.json').read_text())['waves']
    for wave,c in extra.items():
        for kind in ['HH','HL']:
            wanted[wave,kind] = [c['modules'][kind]['member']]
    lookup = {r['survey_wave']:r['rule'] for r in rules}
    for wave,r in lookup.items():
        wanted[wave,'HEALTH'] = r['source_member_chain']
    wanted['2023','alternate'] = ['S13A_PersonIllness.dta']
    wanted['2025','cover'] = ['S00_HHcover.dta']
    hashes,result = {},[]
    for (wave,kind),chain in sorted(wanted.items()):
        archive = lookup[wave]['source_archive']
        if archive not in hashes:
            hashes[archive] = file_sha(ROOT/archive)
        require(len(chain) in [1,2],'Unsupported nested source identity')
        match = [r for r in catalog if r['survey_wave']==wave and r['archive']==archive
            and r['archive_sha256']==hashes[archive] and r['member_path']==chain[0]
            and (r['nested_member_path'] or '')==('' if len(chain)==1 else chain[1])]
        require(len(match)==1,'Source catalog identity not unique: '+wave+'/'+kind)
        result.append({**match[0],'purpose':kind})
    require(len(result)==47,'Expected 45 primary source identities plus alternate/cover')
    return result


def lineage(manifest):
    lookup = {(r['survey_wave'],r['purpose']):r['dataset_id'] for r in manifest}
    waves = sorted({r['survey_wave'] for r in manifest})
    edges = {}
    for relation in RELATIONS:
        links = []
        for wave in waves:
            if relation==ADDITIONAL and wave not in EXTRA:
                continue
            kinds = ['HEALTH'] if relation==RULE else ['HH','HEALTH'] if relation in [ADDITIONAL,SOURCE] else ['HH','HL','HEALTH']
            if wave=='2023' and relation!=RULE:
                kinds += ['alternate']
            if wave=='2025' and relation in [VIEW,COVERAGE,MATRIX]:
                kinds += ['cover']
            # One edge per actual dataset. Shared HH/HL, 1996 HL/HEALTH and 2025 HH/cover
            # are not double-counted; all purposes remain in the local lineage manifest.
            by_dataset = {}
            for kind in kinds:
                dataset = lookup[wave,kind]
                role = 'validation' if kind in ['alternate','cover'] else 'source'
                old = by_dataset.get(dataset)
                by_dataset[dataset] = 'source' if role=='source' or old=='source' else 'validation'
            links.extend({'survey_wave':wave,'dataset_id':d,'contribution_role':role} for d,role in sorted(by_dataset.items()))
        edges[relation] = links
    require(sum(map(len,edges.values()))==197,'Expected 197 unique source-output edges')
    return edges


def wave_counts(f,source,orphan):
    waves = sorted(f.survey_wave.unique())
    member = {str(w):int(n) for w,n in f.groupby('survey_wave').size().items()}
    native = {str(w):int(n) for w,n in source.groupby('survey_wave').size().items()}
    unmatched = {w:int(orphan.survey_wave.eq(w).sum()) for w in waves}
    return {RULE:dict.fromkeys(waves,1),ADDITIONAL:{w:n for w,n in native.items() if w in EXTRA},
        SOURCE:native,VIEW:member,COVERAGE:dict.fromkeys(waves,3),MATRIX:dict.fromkeys(waves,1),ORPHAN:unmatched}


def absent(conn):
    prior.absent(conn)
    require(not conn.execute('SELECT 1 FROM cses_meta.cses_alignment_release WHERE mapping_version=%s',(VERSION,)).fetchone(),'Release already registered')
    for relation in RELATIONS:
        require(not conn.execute('SELECT 1 FROM cses_meta.cses_storage_table WHERE table_schema=%s AND table_name=%s',tuple(relation.split('.'))).fetchone(),'Storage target already registered')
    require(not conn.execute('SELECT 1 FROM cses_meta.cses_load_run WHERE run_scope=%s',(VERSION,)).fetchone(),'Load already registered')


def prepare():
    f,source,orphan,rules,parent,e = checked()
    require(not BACKUP.exists() and not (OUT/'execution.json').exists(),'Preparation exists; preserve it')
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute("SET LOCAL statement_timeout='180s'")
        absent(conn)
        manifest = source_manifest(conn,rules)
        edges = lineage(manifest)
        before = snapshot(conn)
        require(before==parent['before'],'Database baseline drift; review before publication')
    BACKUP.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['/opt/homebrew/bin/pg_dump','-d','mda','-Fc',*[f'--schema={s}' for s in SCHEMAS],f'--file={BACKUP}'],check=True,timeout=600)
    subprocess.run(['/opt/homebrew/bin/pg_restore','--file=/dev/null',str(BACKUP)],check=True,timeout=600)
    with connect() as conn:
        conn.execute("SET LOCAL statement_timeout='180s'")
        unchanged(conn,before)
    put(OUT/'source-lineage.json',encoded({'source_identities':manifest,'edges':edges}))
    plan = {'version':VERSION,'publication_authorized':True,'before':before,
        'script_sha256':file_sha(Path(__file__)),'support_sha256':{p:file_sha(ROOT/p) for p in SUPPORT},
        'evidence_sha256':file_sha(OUT/'evidence.json'),'lineage_sha256':file_sha(OUT/'source-lineage.json'),
        'backup':str(BACKUP.relative_to(ROOT)),'backup_sha256':file_sha(BACKUP),'backup_bytes':BACKUP.stat().st_size,
        'full_backup_decompression_verified':True,'backup_restore_into_server_tested':False,
        'definitions':parent['definitions'],'view_dependency_order':VIEW_ORDER,
        'wave_counts':wave_counts(f,source,orphan),'source_edges':197,'objects':7}
    put(OUT/'execution.json',encoded(plan))
    return {'prepared':True,'objects':7,'source_edges':197,'backup_bytes':plan['backup_bytes']}


def checked_plan():
    values = checked()
    plan = json.loads((OUT/'execution.json').read_text())
    require(plan['publication_authorized'] and plan['script_sha256']==file_sha(Path(__file__)),'Prepared publisher changed')
    require(plan['evidence_sha256']==file_sha(OUT/'evidence.json') and plan['lineage_sha256']==file_sha(OUT/'source-lineage.json'),'Prepared evidence changed')
    require(plan['backup_sha256']==file_sha(BACKUP),'Prepared backup changed')
    require(all(file_sha(ROOT/p)==sha for p,sha in plan['support_sha256'].items()),'Prepared support changed')
    require(plan['definitions']==values[4]['definitions'] and plan['view_dependency_order']==VIEW_ORDER,'Prepared SQL/order changed')
    return (*values,plan)


def data_checks(conn,f,source,orphan,rules,plan):
    result = prior.checks(conn,f,source,orphan,rules,True)
    expected_cov = sorted(json.loads((prior.PILOT/'coverage.json').read_text()),key=lambda r:(r['survey_wave'],r['age_band']))
    require(conn.execute(f'SELECT * FROM {COVERAGE} ORDER BY survey_wave,age_band').fetchall()==expected_cov,'Stored coverage view differs')
    approved_matrix = {r['survey_wave']:r for r in json.loads((prior.PILOT/'matrix.json').read_text())}
    actual_matrix = conn.execute(f'SELECT * FROM {MATRIX} ORDER BY survey_wave').fetchall()
    require(len(actual_matrix)==15,'Stored matrix grain differs')
    for r in actual_matrix:
        require(all(r[k]==v for k,v in approved_matrix[r['survey_wave']].items() if k in r),'Stored matrix differs')
        require(r['rule']==next(t['rule'] for t in rules if t['survey_wave']==r['survey_wave']),'Stored matrix rules differ')
    prior.compare(conn,f'SELECT * FROM {ORPHAN}',None,orphan)
    for relation in RELATIONS:
        schema,name = relation.split('.')
        columns = conn.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position',(schema,name)).fetchall()
        expected_columns = list(f) if relation==VIEW else list(source) if relation in [SOURCE,ADDITIONAL,ORPHAN] else ['survey_wave','rule','verified_form_path'] if relation==RULE else list(expected_cov[0]) if relation==COVERAGE else None
        if expected_columns is not None:
            require(set(r['column_name'] for r in columns)==set(expected_columns) and len(columns)==len(expected_columns),'Output columns differ: '+relation)
        counts = conn.execute(f'SELECT survey_wave,count(*) n FROM {relation} GROUP BY survey_wave').fetchall()
        actual = {r['survey_wave']:r['n'] for r in counts}
        require(actual=={w:n for w,n in plan['wave_counts'][relation].items() if n},'Per-wave output grain differs')
        duplicate = conn.execute(f'SELECT 1 FROM {relation} GROUP BY {",".join(NATURAL_KEYS[relation])} HAVING count(*)>1 LIMIT 1').fetchone()
        require(not duplicate,'Duplicate output key: '+relation)
        privileges = conn.execute("SELECT has_table_privilege('mda_readonly',%s,'SELECT') s,has_table_privilege('mda_readonly',%s,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') w",(relation,relation)).fetchone()
        require(privileges=={'s':True,'w':False},'Read-only grants differ')
    return {**result,'actual_summary_views_checked':True,'source_output_edges':197,'read_only_grants_checked':7}


def register(conn,e,plan,result):
    lineage_doc = json.loads((OUT/'source-lineage.json').read_text())
    rid = conn.execute('''INSERT INTO cses_meta.cses_alignment_release(mapping_version,status,description,specification_sha256,approved_at)
      VALUES(%s,'approved',%s,%s,now()) RETURNING alignment_release_id''',(VERSION,
        'Fifteen-wave native-preserving health screen; eight strict30d waves; 2017 unverified and 2019 disputed codes withheld; source orphans separate.',file_sha(OUT/'evidence.json'))).fetchone()['alignment_release_id']
    storage = {}
    for relation in RELATIONS:
        schema,name = relation.split('.')
        cols = conn.execute('SELECT count(*) n FROM information_schema.columns WHERE table_schema=%s AND table_name=%s',(schema,name)).fetchone()['n']
        family = 'source_dictionary' if relation in [RULE,ADDITIONAL,SOURCE,ORPHAN] else 'alignment_summary'
        grain = 'wave' if relation in [RULE,MATRIX] else 'wave_age_band' if relation==COVERAGE else 'person_wave'
        fp = digest(fingerprint(conn,schema,name))
        sid = conn.execute('''INSERT INTO cses_meta.cses_storage_table(table_schema,table_name,object_family,module_code,
          analytical_grain,natural_key,row_count,column_count,relation_fingerprint) VALUES(%s,%s,%s,'HEALTH',%s,%s,%s,%s,%s)
          RETURNING storage_table_id''',(schema,name,family,grain,NATURAL_KEYS[relation],e['counts'][relation],cols,fp)).fetchone()['storage_table_id']
        storage[relation] = {'storage_table_id':sid,'row_count':e['counts'][relation],'column_count':cols,'relation_fingerprint':fp,
            'object_family':family,'analytical_grain':grain}
        for edge in lineage_doc['edges'][relation]:
            conn.execute('''INSERT INTO cses_meta.cses_dataset_output(dataset_id,storage_table_id,alignment_release_id,contribution_role,output_row_count)
              VALUES(%s,%s,%s,%s,%s)''',(edge['dataset_id'],sid,rid,edge['contribution_role'],plan['wave_counts'][relation][edge['survey_wave']]))
    conn.execute('''INSERT INTO cses_meta.cses_load_run(alignment_release_id,run_scope,source_manifest_sha256,status,row_counts,validation_summary,finished_at)
      VALUES(%s,%s,%s,'loaded',%s,%s,now())''',(rid,VERSION,file_sha(OUT/'evidence.json'),Jsonb(e['counts']),
        Jsonb({'checks':result,'previous_rows_preserved':True,'backup_sha256':plan['backup_sha256'],'lineage_sha256':plan['lineage_sha256']})))
    return rid,storage


def metadata_checks(conn,rid,storage,e,plan,verify_fingerprints=False):
    release = conn.execute('SELECT mapping_version,status,specification_sha256 FROM cses_meta.cses_alignment_release WHERE alignment_release_id=%s',(rid,)).fetchone()
    require(release=={'mapping_version':VERSION,'status':'approved','specification_sha256':file_sha(OUT/'evidence.json')},'Release registry differs')
    actual = conn.execute('''SELECT table_schema||'.'||table_name AS relation,storage_table_id,row_count,column_count,relation_fingerprint,object_family,analytical_grain,module_code,natural_key
      FROM cses_meta.cses_storage_table WHERE storage_table_id=ANY(%s)''',([v['storage_table_id'] for v in storage.values()],)).fetchall()
    require(len(actual)==7,'Storage registry grain differs')
    for r in actual:
        relation = r.pop('relation')
        require(r.pop('module_code')=='HEALTH' and r.pop('natural_key')==NATURAL_KEYS[relation] and r==storage[relation],'Storage registry differs')
        if verify_fingerprints:
            require(storage[relation]['relation_fingerprint']==digest(fingerprint(conn,*relation.split('.'))),'Published fingerprint differs')
    expected = []
    for relation,edges in json.loads((OUT/'source-lineage.json').read_text())['edges'].items():
        for edge in edges:
            expected.append({'dataset_id':edge['dataset_id'],'storage_table_id':storage[relation]['storage_table_id'],
                'contribution_role':edge['contribution_role'],'output_row_count':plan['wave_counts'][relation][edge['survey_wave']]})
    actual_edges = conn.execute('SELECT dataset_id,storage_table_id,contribution_role,output_row_count FROM cses_meta.cses_dataset_output WHERE alignment_release_id=%s',(rid,)).fetchall()
    def order(r):
        return r['storage_table_id'],r['dataset_id'],r['contribution_role']
    require(sorted(actual_edges,key=order)==sorted(expected,key=order),'Source-output edges differ')
    loads = conn.execute('SELECT run_scope,source_manifest_sha256,status,row_counts,validation_summary FROM cses_meta.cses_load_run WHERE alignment_release_id=%s',(rid,)).fetchall()
    require(len(loads)==1 and loads[0]['run_scope']==VERSION and loads[0]['status']=='loaded'
        and loads[0]['source_manifest_sha256']==file_sha(OUT/'evidence.json') and loads[0]['row_counts']==e['counts']
        and loads[0]['validation_summary']['lineage_sha256']==plan['lineage_sha256'],'Load registry differs')
    return {'outputs':7,'source_output_edges':len(actual_edges),'loaded_runs':1,'release_status':'approved'}


def publish(rehearse=False):
    f,source,orphan,rules,parent,e,plan = checked_plan()
    if not rehearse:
        receipt = json.loads((OUT/'rehearsal.json').read_text())
        require(receipt['rehearsed'] and not receipt['committed'] and receipt['full_registration_rehearsed']
            and receipt['execution_sha256']==file_sha(OUT/'execution.json'),'Matching full rollback rehearsal required')
    with connect(False) as conn:
        conn.execute("SET LOCAL statement_timeout='180s'")
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(prior.VERSION,))
        for relation in plan['before']['physical']:
            mode = 'SHARE ROW EXCLUSIVE' if relation in APPEND else 'SHARE'
            conn.execute(sql.SQL('LOCK TABLE {} IN {} MODE').format(sql.Identifier(*relation.split('.')),sql.SQL(mode)))
        absent(conn)
        unchanged(conn,plan['before'])
        manifest = source_manifest(conn,rules)
        expected = json.loads((OUT/'source-lineage.json').read_text())
        require(manifest==expected['source_identities'] and lineage(manifest)==expected['edges'],'Registered source identity drift')
        conn.execute(f'CREATE TABLE {RULE} (survey_wave text PRIMARY KEY,rule jsonb NOT NULL,verified_form_path text)')
        for r in rules:
            conn.execute(f'INSERT INTO {RULE} VALUES(%s,%s,%s)',(r['survey_wave'],Jsonb(r['rule']),r['verified_form_path']))
        conn.execute(f'CREATE TABLE {ADDITIONAL} ({",".join(k+" "+v for k,v in SOURCE_TYPES.items())},PRIMARY KEY({",".join(KEYS)}))')
        extra = pd.read_parquet(OUT/'additional_source.parquet')
        with conn.cursor().copy(f'COPY {ADDITIONAL} ({",".join(SOURCE_TYPES)}) FROM STDIN') as copy:
            for row in extra.itertuples(index=False,name=None):
                copy.write_row([scalar(v) for v in row])
        for relation in VIEW_ORDER:
            conn.execute(f'CREATE VIEW {relation} AS '+plan['definitions'][relation])
        for relation in RELATIONS:
            conn.execute(f'GRANT SELECT ON {relation} TO mda_readonly')
            conn.execute(sql.SQL('COMMENT ON {} {} IS {}').format(sql.SQL('TABLE' if relation in [RULE,ADDITIONAL] else 'VIEW'),
                sql.Identifier(*relation.split('.')),sql.Literal(VERSION+': native values preserved; 2017 unverified and 2019 strict values withheld; no imputation or blanket equivalence.')))
        conn.execute('SET LOCAL ROLE mda_readonly')
        result = data_checks(conn,f,source,orphan,rules,plan)
        conn.execute('RESET ROLE')
        rid,storage = register(conn,e,plan,result)
        metadata = metadata_checks(conn,rid,storage,e,plan)
        unchanged(conn,plan['before'])
        if rehearse:
            conn.rollback()
    if rehearse:
        with connect() as conn:
            conn.execute("SET LOCAL statement_timeout='180s'")
            absent(conn)
            unchanged(conn,plan['before'])
    receipt = {'rehearsed':rehearse,'committed':not rehearse,'release_id':rid,
        'full_registration_rehearsed':True,'checks':result,'metadata':metadata,'storage':storage,
        'old_rows_definitions_permissions_unchanged':True,'execution_sha256':file_sha(OUT/'execution.json')}
    put(OUT/('rehearsal.json' if rehearse else 'published.json'),encoded(receipt))
    return {k:v for k,v in receipt.items() if k!='storage'}


def validate():
    f,source,orphan,rules,parent,e,plan = checked_plan()
    pub = json.loads((OUT/'published.json').read_text())
    require(pub['committed'] and pub['execution_sha256']==file_sha(OUT/'execution.json'),'Confirmed publication required')
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute("SET LOCAL statement_timeout='180s'")
        unchanged(conn,plan['before'])
        conn.execute('SET LOCAL ROLE mda_readonly')
        require(conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on','Read-only required')
        require(source_manifest(conn,rules)==json.loads((OUT/'source-lineage.json').read_text())['source_identities'],'Source identity drift')
        result = data_checks(conn,f,source,orphan,rules,plan)
        metadata = metadata_checks(conn,pub['release_id'],pub['storage'],e,plan,True)
    receipt = {'validated':True,'read_only':True,'role':'mda_readonly','checks':result,'metadata':metadata,
        'old_rows_definitions_permissions_unchanged':True,'published_sha256':file_sha(OUT/'published.json')}
    put(OUT/'validated.json',encoded(receipt))
    return receipt


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['build','prepare','rehearse','publish','validate'])
    action = p.parse_args().action
    result = build() if action=='build' else prepare() if action=='prepare' else publish(action=='rehearse') if action in ['rehearse','publish'] else validate()
    print(json.dumps(result,indent=2))
