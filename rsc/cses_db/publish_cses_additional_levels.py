#!/usr/bin/env python3
"""Publish a literal level dictionary and additive, field-specific analysis views."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd
from align_cses_additional_levels import BOOK, COVERAGE, OUT, ROOT, VERSION, VIEW, summary
from align_cses_additional_school import KEYS, require
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put
from psycopg import sql
from psycopg.types.json import Jsonb
from publish_cses_2025_age import APPEND, digest, snapshot, unchanged
from publish_cses_geography_interface import SCHEMAS, connect, fingerprint

BACKUP = ROOT/'data/backups/cses_additional_levels_v1/before_education_levels.dump'
SUPPORT = ['rsc/cses_db/publish_cses_2025_age.py','rsc/cses_db/publish_cses_geography_interface.py',
           'rsc/cses_db/cache_cses_questionnaires.py','rsc/cses_db/align_cses_additional_school.py']
BOOK_TYPES = {'survey_wave':'text','target':'text','source_code':'integer','source_variable':'text',
    'native_value_label':'text','semantic_family':'text','response_kind':'text','general_grade':'integer',
    'questionnaire_code':'integer','questionnaire_meaning':'text','qualification':'text',
    'source_form_code_differs':'boolean','source_label_provenance':'text','questionnaire_path':'text',
    'questionnaire_sha256':'text','questionnaire_locator':'text','mapping_version':'text'}


def checked():
    e = json.loads((OUT/'evidence.json').read_text())
    for p,sha in e['inputs'].items():
        require(file_sha(ROOT/p)==sha,'Input changed: '+p)
    for name,key in [('expected.parquet','expected_sha256'),('codebook.json','codebook_sha256')]:
        require(file_sha(OUT/name)==e[key],'Artifact changed: '+name)
    f = pd.read_parquet(OUT/'expected.parquet')
    book = json.loads((OUT/'codebook.json').read_text())
    require(len(f)==212779 and not f.duplicated(KEYS).any() and len(book)==188,'Unexpected grain')
    return f,book,e


def book_query(book):
    columns = ','.join(f'{k} {v}' for k,v in BOOK_TYPES.items())
    return f'SELECT * FROM jsonb_to_recordset({sql.Literal(json.dumps(book)).as_string()}::jsonb) AS b({columns})'


def person_query(columns, relation=BOOK):
    mappings = []
    for target,alias in [('highest','h'),('current','c')]:
        for field in ['semantic_family','response_kind','general_grade','native_value_label']:
            mappings.append(f'{alias}.{field} AS {target}_source_{field}')
        mappings.append(f'coalesce({alias}.source_form_code_differs,false) AS {target}_source_form_code_differs')
    return f"""WITH inputs AS (SELECT s.survey_wave,s.household_key,s.record_key,s.age_for_school_analysis,
      s.school_age_eligible,s.education_record_linked,s.school_concept_scope,s.school_current_observed,
      s.school_ever_observed,s.school_current_native_code,s.school_ever_native_code,s.school_route_conflict,
      s.school_invalid_response_code,s.school_highest_level_source_code AS highest_source_code,
      s.school_current_level_source_code AS current_source_code,{','.join(mappings)},
      s.school_ever_native_code IS NOT NULL AND s.school_ever_native_code NOT IN (1,2) AS invalid_ever,
      s.school_current_native_code IS NOT NULL AND s.school_current_native_code NOT IN (1,2) AS invalid_current
      FROM cses_analysis.cses_additional_school_attendance_v1 s
      LEFT JOIN {relation} h ON s.survey_wave=h.survey_wave AND h.target='highest' AND s.school_highest_level_source_code=h.source_code
      LEFT JOIN {relation} c ON s.survey_wave=c.survey_wave AND c.target='current' AND s.school_current_level_source_code=c.source_code),
      hints AS (SELECT *,highest_source_code IS NOT NULL AND
        coalesce(highest_source_response_kind NOT IN ('none','unknown'),true) AS high_hint,
        current_source_code IS NOT NULL AND coalesce(current_source_response_kind NOT IN ('none','unknown'),true) AS current_hint,
        school_route_conflict OR school_invalid_response_code AS highest_other_item_warning FROM inputs),
      flags AS (SELECT *,coalesce(school_ever_observed=0 AND (school_current_observed=1 OR high_hint OR current_hint),false) AS gate_conflict,
        coalesce(school_age_eligible AND education_record_linked,false) AS highest_target_applicable,
        survey_wave<>'1996' AS current_target_available FROM hints),
      statuses AS (SELECT *,CASE
        WHEN school_age_eligible IS NULL THEN 'unknown_age_eligibility'
        WHEN NOT school_age_eligible THEN 'outside_questionnaire_age_range'
        WHEN NOT education_record_linked THEN 'missing_education_record'
        WHEN invalid_ever THEN 'unrecognized_ever_attendance_code'
        WHEN gate_conflict THEN 'never_attended_route_conflict'
        WHEN highest_source_response_kind='unknown' THEN 'explicit_unknown_highest'
        WHEN highest_source_code IS NOT NULL AND highest_source_response_kind IS NULL THEN 'unrecognized_highest_code'
        WHEN highest_source_code IS NULL AND school_ever_observed=0 THEN 'derived_never_attended_from_documented_skip'
        WHEN highest_source_code IS NULL AND school_ever_observed=1 THEN 'missing_highest_after_ever_yes'
        WHEN highest_source_code IS NULL THEN 'missing_highest_gate_unresolved'
        WHEN school_ever_observed IS NULL AND survey_wave<>'1996' THEN 'observed_highest_gate_missing'
        WHEN highest_other_item_warning THEN 'observed_highest_other_item_warning'
        ELSE 'observed_highest' END::text AS highest_level_status,
      CASE WHEN NOT current_target_available THEN 'not_collected_in_selected_education_source'
        WHEN school_age_eligible IS NULL THEN 'unknown_age_eligibility'
        WHEN NOT school_age_eligible THEN 'outside_questionnaire_age_range'
        WHEN NOT education_record_linked THEN 'missing_education_record'
        WHEN invalid_ever OR invalid_current THEN 'unrecognized_attendance_gate_code'
        WHEN school_ever_observed=0 AND school_current_observed=1 THEN 'never_attended_route_conflict'
        WHEN school_current_observed IS NULL THEN 'current_attendance_unresolved'
        WHEN school_current_observed=0 AND current_source_code IS NOT NULL THEN 'current_code_outside_attendance_route'
        WHEN school_current_observed=0 THEN 'not_currently_attending'
        WHEN current_source_code IS NOT NULL AND current_source_response_kind IS NULL THEN 'unrecognized_current_level_code'
        WHEN current_source_response_kind='unknown' THEN 'explicit_unknown_current_level'
        WHEN current_source_response_kind='none' THEN 'none_not_a_current_level'
        WHEN current_source_code IS NULL THEN 'missing_current_level_after_yes'
        ELSE 'observed_current_level' END::text AS current_level_status,
        coalesce(current_target_available AND highest_target_applicable AND school_current_observed=1,false) AS current_target_applicable
      FROM flags), qualified AS (SELECT *,
        CASE WHEN highest_level_status LIKE 'observed_highest%' THEN highest_source_semantic_family
          WHEN highest_level_status='derived_never_attended_from_documented_skip' THEN 'never_attended' ELSE NULL END AS highest_qualified_family,
        CASE WHEN highest_level_status LIKE 'observed_highest%' THEN highest_source_general_grade ELSE NULL END AS highest_qualified_general_grade,
        highest_level_status='derived_never_attended_from_documented_skip' AS highest_derived_from_skip,
        CASE WHEN current_level_status='observed_current_level' THEN current_source_semantic_family ELSE NULL END AS current_qualified_family,
        CASE WHEN current_level_status='observed_current_level' THEN current_source_general_grade ELSE NULL END AS current_qualified_general_grade
      FROM statuses), final AS (SELECT *,highest_qualified_family IS NOT NULL AS highest_family_usable,
        current_qualified_family IS NOT NULL AS current_family_usable,false AS education_isced_equivalence_certified,
        '{VERSION}'::text AS education_levels_release FROM qualified)
      SELECT {','.join(columns)} FROM final"""


def coverage_query():
    return f"""SELECT s.survey_wave,b.target,b.available AS target_available,count(*) AS roster_members,
      count(*) FILTER(WHERE school_age_eligible) AS age_eligible_members,
      count(*) FILTER(WHERE b.applicable) AS target_applicable_members,count(b.source_code) AS source_non_null,
      count(b.family) AS qualified_family_records,count(b.grade) AS qualified_general_grade_records,
      count(*) FILTER(WHERE b.applicable AND b.family IS NULL) AS unresolved_applicable_records,
      count(*) FILTER(WHERE b.derived) AS derived_never_attended,
      count(*) FILTER(WHERE b.renumbered) AS source_form_renumbered_records,
      count(*) FILTER(WHERE b.kind='unknown') AS explicit_unknown_responses
      FROM {VIEW} s CROSS JOIN LATERAL (VALUES
        ('highest',true,highest_target_applicable,highest_source_code,highest_qualified_family,
         highest_qualified_general_grade,highest_derived_from_skip,highest_source_form_code_differs,highest_source_response_kind),
        ('current',current_target_available,current_target_applicable,current_source_code,current_qualified_family,
         current_qualified_general_grade,false,current_source_form_code_differs,current_source_response_kind)
      ) b(target,available,applicable,source_code,family,grade,derived,renumbered,kind)
      GROUP BY s.survey_wave,b.target,b.available"""


def definitions(f):
    return {VIEW:person_query(list(f)),COVERAGE:coverage_query()}


def absent(conn):
    require(not conn.execute("SELECT 1 FROM pg_event_trigger WHERE evtenabled<>'D'").fetchone(),'Active DDL trigger')
    for r in [BOOK,VIEW,COVERAGE]:
        require(conn.execute('SELECT to_regclass(%s) r',(r,)).fetchone()['r'] is None,'Target exists; validate rather than overwrite: '+r)
    require(not conn.execute('SELECT 1 FROM cses_meta.cses_alignment_release WHERE mapping_version=%s',(VERSION,)).fetchone(),'Release exists')


def checks(conn,f,book,e,published=True):
    query = f'SELECT * FROM {VIEW}' if published else person_query(list(f),'('+book_query(book)+')')
    records = conn.execute(sql.SQL('SELECT * FROM ({}) v ORDER BY survey_wave COLLATE "C",household_key COLLATE "C",record_key COLLATE "C"').format(sql.SQL(query))).fetchall()
    live = pd.DataFrame(records).astype(f.dtypes.to_dict())
    pd.testing.assert_frame_equal(live,f,check_exact=True)
    require(summary(live)==e['summary'],'Denominators differ')
    if published:
        actual = conn.execute(f'SELECT * FROM {BOOK} ORDER BY survey_wave,target,source_code').fetchall()
        require(actual==sorted(book,key=lambda r:(r['survey_wave'],r['target'],r['source_code'])),'Codebook differs')
        coverage = conn.execute(f'SELECT * FROM {COVERAGE} ORDER BY survey_wave,target').fetchall()
        require(coverage==sorted(e['summary'],key=lambda r:(r['survey_wave'],r['target'])),'SQL coverage differs')
    return {'all_cells_match':True,'records':len(f),'codebook_entries':len(book),
        'highest_family_records':int(live.highest_family_usable.sum()),'current_family_records':int(live.current_family_usable.sum())}


def prepare():
    f,book,e = checked()
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        absent(conn)
        result = checks(conn,f,book,e,False)
        before = snapshot(conn)
    require(not BACKUP.exists() and not (OUT/'execution.json').exists(),'Existing preparation; preserve it')
    BACKUP.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['/opt/homebrew/bin/pg_dump','-d','mda','-Fc',*[f'--schema={s}' for s in SCHEMAS],f'--file={BACKUP}'],check=True,timeout=300)
    subprocess.run(['/opt/homebrew/bin/pg_restore','--file=/dev/null',str(BACKUP)],check=True,timeout=300)
    plan = {'version':VERSION,'before':before,'preflight':result,'evidence_sha256':file_sha(OUT/'evidence.json'),
        'script_sha256':file_sha(Path(__file__)),'support_sha256':{p:file_sha(ROOT/p) for p in SUPPORT},
        'backup':str(BACKUP.relative_to(ROOT)),'backup_sha256':file_sha(BACKUP),
        'full_backup_decompression_verified':True,'definitions':definitions(f)}
    put(OUT/'execution.json',encoded(plan))
    return {'prepared':True,**result}


def register(conn,f,book,e,plan,result):
    rid = conn.execute("""INSERT INTO cses_meta.cses_alignment_release(mapping_version,status,description,specification_sha256,approved_at)
      VALUES(%s,'approved',%s,%s,now()) RETURNING alignment_release_id""",(VERSION,
        'Highest attainment and current study kept separate; native dictionary plus qualified families and ordinary grades, no ISCED/degree equivalence.',
        file_sha(OUT/'evidence.json'))).fetchone()['alignment_release_id']
    spec = json.loads((ROOT/'rsc/specs/cses_additional_waves_v1.json').read_text())['waves']
    datasets = conn.execute("""SELECT s.survey_wave,d.member_path,d.dataset_id FROM cses_meta.cses_dataset d
      JOIN cses_meta.cses_survey s USING(survey_id) WHERE s.survey_wave=ANY(%s)""",(list(spec),)).fetchall()
    for relation,grain,key in [(BOOK,'field_wave_source_code',['survey_wave','target','source_code']),
                               (VIEW,'person_wave',KEYS),(COVERAGE,'field_wave',['survey_wave','target'])]:
        schema,name = relation.split('.')
        n = conn.execute(sql.SQL('SELECT count(*) n FROM {}').format(sql.Identifier(schema,name))).fetchone()['n']
        cols = conn.execute('SELECT count(*) n FROM information_schema.columns WHERE table_schema=%s AND table_name=%s',(schema,name)).fetchone()['n']
        sid = conn.execute("""INSERT INTO cses_meta.cses_storage_table(table_schema,table_name,object_family,module_code,
          analytical_grain,natural_key,row_count,column_count,relation_fingerprint) VALUES(%s,%s,%s,'ED',%s,%s,%s,%s,%s)
          RETURNING storage_table_id""",(schema,name,'source_dictionary' if relation==BOOK else 'alignment_summary',
          grain,key,n,cols,digest(fingerprint(conn,schema,name)))).fetchone()['storage_table_id']
        for wave,cfg in spec.items():
            members = {cfg['modules']['ED']['member']:'source'}
            if relation!=BOOK:
                members[cfg['modules']['HL']['member']] = 'source'
                if wave=='2025':
                    members['S00_HHcover.dta'] = 'validation'
            for member,role in members.items():
                found = [d for d in datasets if d['survey_wave']==wave and d['member_path']==member]
                require(len(found)==1,'Source dataset registration differs')
                count = conn.execute(sql.SQL('SELECT count(*) n FROM {} WHERE survey_wave=%s').format(sql.Identifier(schema,name)),(wave,)).fetchone()['n']
                conn.execute("""INSERT INTO cses_meta.cses_dataset_output(dataset_id,storage_table_id,alignment_release_id,contribution_role,output_row_count)
                  VALUES(%s,%s,%s,%s,%s)""",(found[0]['dataset_id'],sid,rid,role,count))
    conn.execute("""INSERT INTO cses_meta.cses_load_run(alignment_release_id,run_scope,source_manifest_sha256,status,row_counts,
      validation_summary,finished_at) VALUES(%s,%s,%s,'loaded',%s,%s,now())""",(rid,VERSION,file_sha(OUT/'evidence.json'),
      Jsonb({BOOK:188,VIEW:len(f),COVERAGE:10}),Jsonb({'checks':result,'previous_rows_preserved':True,'backup_sha256':plan['backup_sha256']})))
    return rid


def publish(rehearse=False):
    f,book,e = checked()
    plan = json.loads((OUT/'execution.json').read_text())
    require(plan['script_sha256']==file_sha(Path(__file__)) and plan['evidence_sha256']==file_sha(OUT/'evidence.json'),'Prepared code/evidence changed')
    require(plan['backup_sha256']==file_sha(BACKUP) and plan['definitions']==definitions(f),'Backup/SQL changed')
    require(all(file_sha(ROOT/p)==sha for p,sha in plan['support_sha256'].items()),'Support changed')
    if not rehearse:
        rehearsal = json.loads((OUT/'rehearsal.json').read_text())
        require(not rehearsal['committed'] and rehearsal['execution_sha256']==file_sha(OUT/'execution.json'),'Matching rollback rehearsal required')
    with connect(False) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(VERSION,))
        for relation in plan['before']['physical']:
            conn.execute(sql.SQL('LOCK TABLE {} IN {} MODE').format(sql.Identifier(*relation.split('.')),
                         sql.SQL('SHARE ROW EXCLUSIVE' if relation in APPEND else 'SHARE')))
        absent(conn)
        unchanged(conn,plan['before'])
        cols = sql.SQL(',').join(sql.SQL('{} {}').format(sql.Identifier(k),sql.SQL(v)) for k,v in BOOK_TYPES.items())
        conn.execute(sql.SQL('CREATE TABLE {} ({},PRIMARY KEY(survey_wave,target,source_code))').format(sql.Identifier(*BOOK.split('.')),cols))
        with conn.cursor().copy(sql.SQL('COPY {} ({}) FROM STDIN').format(sql.Identifier(*BOOK.split('.')),
             sql.SQL(',').join(map(sql.Identifier,BOOK_TYPES)))) as copy:
            for r in book:
                copy.write_row([r[k] for k in BOOK_TYPES])
        for relation,query in definitions(f).items():
            conn.execute(sql.SQL('CREATE VIEW {} AS ').format(sql.Identifier(*relation.split('.')))+sql.SQL(query))
        for relation in [BOOK,VIEW,COVERAGE]:
            conn.execute(sql.SQL('GRANT SELECT ON {} TO mda_readonly').format(sql.Identifier(*relation.split('.'))))
            conn.execute(sql.SQL('COMMENT ON {} {} IS {}').format(sql.SQL('TABLE' if relation==BOOK else 'VIEW'),
                sql.Identifier(*relation.split('.')),sql.Literal(VERSION+': native labels/codes retained; attainment versus current study distinct; not ISCED or degree equivalence.')))
        result = checks(conn,f,book,e)
        rid = register(conn,f,book,e,plan,result)
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
    f,book,e = checked()
    plan = json.loads((OUT/'execution.json').read_text())
    pub = json.loads((OUT/'published.json').read_text())
    require(pub['committed'],'No confirmed publication')
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        unchanged(conn,plan['before'])
        conn.execute('SET LOCAL ROLE mda_readonly')
        require(conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on','Read-only required')
        result = checks(conn,f,book,e)
        metadata = conn.execute("""SELECT count(DISTINCT o.storage_table_id) AS outputs,count(*) AS edges FROM cses_meta.cses_dataset_output o
          JOIN cses_meta.cses_alignment_release r USING(alignment_release_id) WHERE r.mapping_version=%s""",(VERSION,)).fetchone()
        require(metadata=={'outputs':3,'edges':25},'Source-output metadata differs')
        require(conn.execute('SELECT status FROM cses_meta.cses_load_run WHERE alignment_release_id=%s',(pub['release_id'],)).fetchall()==[{'status':'loaded'}],'Load registry differs')
    result = {'validated':True,'role':'mda_readonly','read_only':True,'previous_rows_and_interfaces_unchanged':True,
              'checks':result,'metadata':metadata,'published_sha256':file_sha(OUT/'published.json')}
    put(OUT/'validated.json',encoded(result))
    return result


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['check','prepare','rehearse','publish','validate'])
    action = p.parse_args().action
    if action=='check':
        f,b,e = checked()
        with connect() as c:
            c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            c.execute('SET LOCAL ROLE mda_readonly')
            result = checks(c,f,b,e,False)
    else:
        result = {'prepare':prepare,'rehearse':lambda:publish(True),'publish':publish,'validate':validate}[action]()
    print(json.dumps(result,indent=2))
