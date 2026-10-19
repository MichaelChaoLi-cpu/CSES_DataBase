#!/usr/bin/env python3
"""Publish additive literacy and observed schooling-years interfaces with rollback safety."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd
from align_cses_additional_literacy_years import COVERAGE, OUT, ROOT, RULE, TARGETS, VERSION, VIEW, summary
from align_cses_additional_school import KEYS, require
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put
from psycopg import sql
from psycopg.types.json import Jsonb
from publish_cses_2025_age import APPEND, digest, snapshot, unchanged
from publish_cses_geography_interface import SCHEMAS, connect, fingerprint

BACKUP = ROOT/'data/backups/cses_additional_literacy_years_v1/before_literacy_years.dump'
SUPPORT = ['rsc/cses_db/publish_cses_2025_age.py','rsc/cses_db/publish_cses_geography_interface.py',
    'rsc/cses_db/cache_cses_questionnaires.py','rsc/cses_db/align_cses_additional_school.py',
    'rsc/cses_db/validate_cses_additional_literacy_years.py']
RULE_TYPES = {'survey_wave':'text','target':'text','source_variables':'text[]','source_variable_labels':'jsonb',
    'native_value_labels':'jsonb','source_available':'boolean','mode':'text','minimum_age':'integer',
    'maximum_years':'integer','questionnaire_path':'text','questionnaire_sha256':'text',
    'questionnaire_locator':'text','qualification':'text','mapping_version':'text'}


def checked():
    e = json.loads((OUT/'evidence.json').read_text())
    for p,sha in e['inputs'].items():
        require(file_sha(ROOT/p)==sha,'Input changed: '+p)
    for name,key in [('expected.parquet','expected_sha256'),('rules.json','rules_sha256')]:
        require(file_sha(OUT/name)==e[key],'Artifact changed: '+name)
    f = pd.read_parquet(OUT/'expected.parquet')
    rules = json.loads((OUT/'rules.json').read_text())
    require(len(f)==212779 and not f.duplicated(KEYS).any() and len(rules)==20,'Unexpected grain')
    receipt = json.loads((OUT/'independent-local-checks.json').read_text())
    require(receipt['passed'] and receipt['validator_sha256']==file_sha(ROOT/SUPPORT[-1]) and
        receipt['expected_sha256']==e['expected_sha256'] and receipt['rules_sha256']==e['rules_sha256'],
        'Matching independent native acceptance required')
    return f,rules,e


def rule_query(rules):
    columns = ','.join(f'{k} {v}' for k,v in RULE_TYPES.items())
    return f'SELECT * FROM jsonb_to_recordset({sql.Literal(json.dumps(rules)).as_string()}::jsonb) AS r({columns})'


def person_query(columns,relation=RULE):
    statuses = []
    qualifications = []
    for target in TARGETS:
        x = f'{target}_source_value'
        if target=='years':
            inner = """WHEN school_ever_native_code IS NOT NULL AND school_ever_native_code NOT IN (1,2) THEN 'unrecognized_ever_attendance_code'
              WHEN school_ever_native_code IS NULL THEN 'ever_attendance_unresolved'
              WHEN school_ever_native_code=2 AND years_source_value IS NULL THEN 'documented_skip_no_years_value'
              WHEN school_ever_native_code=2 THEN 'years_value_outside_ever_attendance_route'
              WHEN years_numeric_guard_failed THEN 'outside_integer_0_30_guard'
              WHEN years_exceed_source_age THEN 'years_exceed_source_age'
              WHEN years_source_value IS NULL THEN 'missing_years_after_ever_yes'
              ELSE 'observed_years'"""
            value = 'years_source_value::bigint'
            validstatus = "'observed_years'"
        elif target=='combined':
            inner = """WHEN survey_wave IN ('2023','2025') THEN CASE
              WHEN (read_source_value IS NOT NULL AND read_source_value NOT IN (1,2)) OR
                   (write_source_value IS NOT NULL AND write_source_value NOT IN (1,2)) THEN 'unrecognized_component_code'
              WHEN read_source_value IS NULL OR write_source_value IS NULL THEN 'missing_component_response'
              ELSE 'derived_both_valid_read_and_write' END
              WHEN combined_source_value IS NULL THEN 'missing_response'
              WHEN combined_source_value NOT IN (1,2) THEN 'unrecognized_native_binary_code'
              ELSE 'observed_binary'"""
            value = "CASE WHEN survey_wave IN ('2023','2025') THEN (read_source_value=1 AND write_source_value=1)::integer ELSE (combined_source_value=1)::integer END"
            validstatus = "'observed_binary','derived_both_valid_read_and_write'"
        else:
            inner = f"WHEN {x} IS NULL THEN 'missing_response' WHEN {x} NOT IN (1,2) THEN 'unrecognized_native_binary_code' ELSE 'observed_binary'"
            value = f'({x}=1)::integer'
            validstatus = "'observed_binary'"
        statuses.append(f"CASE WHEN NOT {target}_source_available THEN 'not_collected_in_selected_education_source' "
            f"WHEN education_age_eligible IS NULL THEN 'unknown_age_eligibility' "
            f"WHEN NOT education_age_eligible THEN 'outside_questionnaire_age_range' "
            f"WHEN NOT education_record_linked THEN 'missing_education_record' {inner} END::text AS {target}_status")
        qualifications.extend([f'CASE WHEN {target}_status IN ({validstatus}) THEN {value} END AS {target}_qualified',
            f'coalesce({target}_source_available AND education_age_eligible AND education_record_linked,false) AS {target}_target_applicable'])
    return f"""WITH inputs AS (SELECT s.survey_wave,s.household_key,s.record_key,
      s.age_for_school_analysis AS age_for_education_analysis,s.age_selection_status,s.questionnaire_minimum_age,
      s.school_age_eligible AS education_age_eligible,s.education_record_linked,s.school_ever_native_code,
      CASE WHEN rc.mode='observed_binary' THEN (e.source_values->>rc.source_variables[1])::double precision END AS combined_source_value,
      (e.source_values->>rr.source_variables[1])::double precision AS read_source_value,
      (e.source_values->>rw.source_variables[1])::double precision AS write_source_value,
      (e.source_values->>ry.source_variables[1])::double precision AS years_source_value,
      rc.source_available AS combined_source_available,rr.source_available AS read_source_available,
      rw.source_available AS write_source_available,ry.source_available AS years_source_available
      FROM cses_analysis.cses_additional_school_attendance_v1 s
      LEFT JOIN cses_data.cses_additional_ed_v1 e USING(survey_wave,household_key,record_key)
      JOIN {relation} rc ON s.survey_wave=rc.survey_wave AND rc.target='combined'
      JOIN {relation} rr ON s.survey_wave=rr.survey_wave AND rr.target='read'
      JOIN {relation} rw ON s.survey_wave=rw.survey_wave AND rw.target='write'
      JOIN {relation} ry ON s.survey_wave=ry.survey_wave AND ry.target='years'),
      flags AS (SELECT *,years_source_value IS NOT NULL AND NOT
        (years_source_value BETWEEN 0 AND 30 AND years_source_value=floor(years_source_value)) AS years_numeric_guard_failed,
        coalesce(years_source_value>age_for_education_analysis,false) AS years_exceed_source_age FROM inputs),
      statuses AS (SELECT *,{','.join(statuses)} FROM flags),
      qualified AS (SELECT *,{','.join(qualifications)} FROM statuses),
      final AS (SELECT *,years_target_applicable AND coalesce(school_ever_native_code=1,false) AS years_expected_by_route,
        combined_status='derived_both_valid_read_and_write' AS combined_derived_from_components,
        coalesce(write_source_value=1 AND read_source_value=2,false) AS write_yes_read_no_warning,
        false AS literacy_instrument_equivalence_certified,false AS years_imputation_performed,
        '{VERSION}'::text AS literacy_years_release FROM qualified)
      SELECT {','.join(columns)} FROM final"""


def coverage_query():
    return f"""SELECT s.survey_wave,a.age_band,b.target,b.available AS source_available,
      count(*) AS members_in_age_band,count(*) FILTER(WHERE b.applicable) AS target_applicable_members,
      count(*) FILTER(WHERE b.expected) AS expected_response_by_route,count(b.source) AS source_non_null,
      count(b.qualified) AS qualified_records,
      CASE WHEN b.target<>'years' THEN count(*) FILTER(WHERE b.qualified=1) END AS qualified_yes,
      CASE WHEN b.target<>'years' THEN count(*) FILTER(WHERE b.qualified=0) END AS qualified_no,
      count(*) FILTER(WHERE b.expected AND b.qualified IS NULL) AS unresolved_expected_response,
      count(*) FILTER(WHERE b.status LIKE 'unrecognized_%') AS unrecognized_response_records,
      count(*) FILTER(WHERE b.target='combined' AND combined_derived_from_components) AS derived_combined,
      count(*) FILTER(WHERE b.target='years' AND years_status='documented_skip_no_years_value') AS documented_years_skips,
      count(*) FILTER(WHERE b.target='years' AND years_exceed_source_age) AS years_age_conflicts
      FROM {VIEW} s CROSS JOIN LATERAL (VALUES
        ('questionnaire_age_eligible',education_age_eligible),('ages_15_plus',age_for_education_analysis>=15)) a(age_band,inband)
      CROSS JOIN LATERAL (VALUES
        ('combined',combined_source_available,combined_target_applicable,combined_target_applicable,combined_source_value,combined_qualified,combined_status),
        ('read',read_source_available,read_target_applicable,read_target_applicable,read_source_value,read_qualified,read_status),
        ('write',write_source_available,write_target_applicable,write_target_applicable,write_source_value,write_qualified,write_status),
        ('years',years_source_available,years_target_applicable,years_expected_by_route,years_source_value,years_qualified,years_status)
      ) b(target,available,applicable,expected,source,qualified,status)
      WHERE a.inband GROUP BY s.survey_wave,a.age_band,b.target,b.available"""


def definitions(f):
    return {VIEW:person_query(list(f)),COVERAGE:coverage_query()}


def absent(conn):
    require(not conn.execute("SELECT 1 FROM pg_event_trigger WHERE evtenabled<>'D'").fetchone(),'Active DDL trigger')
    for r in [RULE,VIEW,COVERAGE]:
        require(conn.execute('SELECT to_regclass(%s) r',(r,)).fetchone()['r'] is None,'Target exists; validate, do not overwrite: '+r)
    require(not conn.execute('SELECT 1 FROM cses_meta.cses_alignment_release WHERE mapping_version=%s',(VERSION,)).fetchone(),'Release exists')


def checks(conn,f,rules,e,published=True):
    query = f'SELECT * FROM {VIEW}' if published else person_query(list(f),'('+rule_query(rules)+')')
    live = pd.DataFrame(conn.execute(sql.SQL('SELECT * FROM ({}) v ORDER BY survey_wave COLLATE "C",household_key COLLATE "C",record_key COLLATE "C"').format(sql.SQL(query))).fetchall()).astype(f.dtypes.to_dict())
    pd.testing.assert_frame_equal(live,f,check_exact=True)
    require(summary(live)==e['summary'],'Denominators differ')
    if published:
        require(conn.execute(f'SELECT * FROM {RULE} ORDER BY survey_wave,target').fetchall()==sorted(rules,key=lambda r:(r['survey_wave'],r['target'])),'Rules differ')
        require(conn.execute(f'SELECT * FROM {COVERAGE} ORDER BY survey_wave,age_band,target').fetchall()==sorted(e['summary'],key=lambda r:(r['survey_wave'],r['age_band'],r['target'])),'SQL coverage differs')
    return {'all_cells_match':True,'records':len(f),'rule_rows':len(rules),
        'qualified_records':{t:int(live[f'{t}_qualified'].notna().sum()) for t in TARGETS}}


def prepare():
    f,rules,e = checked()
    require(not BACKUP.exists() and not (OUT/'execution.json').exists(),'Existing preparation; preserve it')
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        absent(conn)
        result = checks(conn,f,rules,e,False)
        before = snapshot(conn)
    BACKUP.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['/opt/homebrew/bin/pg_dump','-d','mda','-Fc',*[f'--schema={s}' for s in SCHEMAS],f'--file={BACKUP}'],check=True,timeout=300)
    subprocess.run(['/opt/homebrew/bin/pg_restore','--file=/dev/null',str(BACKUP)],check=True,timeout=300)
    plan = {'version':VERSION,'before':before,'preflight':result,'evidence_sha256':file_sha(OUT/'evidence.json'),
        'script_sha256':file_sha(Path(__file__)),'support_sha256':{p:file_sha(ROOT/p) for p in SUPPORT},
        'backup':str(BACKUP.relative_to(ROOT)),'backup_sha256':file_sha(BACKUP),
        'full_backup_decompression_verified':True,'definitions':definitions(f)}
    put(OUT/'execution.json',encoded(plan))
    return {'prepared':True,**result}


def register(conn,f,e,plan,result):
    rid = conn.execute("""INSERT INTO cses_meta.cses_alignment_release(mapping_version,status,description,specification_sha256,approved_at)
      VALUES(%s,'approved',%s,%s,now()) RETURNING alignment_release_id""",(VERSION,
      'Observed combined legacy literacy, separate modern components and marked conjunction; observed completed years, no skip or attainment imputation.',file_sha(OUT/'evidence.json'))).fetchone()['alignment_release_id']
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
          RETURNING storage_table_id""",(schema,name,'alignment_rules' if relation==RULE else 'alignment_summary',grain,key,n,cols,
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
      Jsonb({RULE:20,VIEW:len(f),COVERAGE:40}),Jsonb({'checks':result,'previous_rows_preserved':True,'backup_sha256':plan['backup_sha256']})))
    return rid


def publish(rehearse=False):
    f,rules,e = checked()
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
        cols = sql.SQL(',').join(sql.SQL('{} {}').format(sql.Identifier(k),sql.SQL(v)) for k,v in RULE_TYPES.items())
        conn.execute(sql.SQL('CREATE TABLE {} ({},PRIMARY KEY(survey_wave,target))').format(sql.Identifier(*RULE.split('.')),cols))
        with conn.cursor().copy(sql.SQL('COPY {} ({}) FROM STDIN').format(sql.Identifier(*RULE.split('.')),
             sql.SQL(',').join(map(sql.Identifier,RULE_TYPES)))) as copy:
            for r in rules:
                copy.write_row([Jsonb(r[k]) if RULE_TYPES[k]=='jsonb' else r[k] for k in RULE_TYPES])
        for relation,query in definitions(f).items():
            conn.execute(sql.SQL('CREATE VIEW {} AS ').format(sql.Identifier(*relation.split('.')))+sql.SQL(query))
        for relation in [RULE,VIEW,COVERAGE]:
            conn.execute(sql.SQL('GRANT SELECT ON {} TO mda_readonly').format(sql.Identifier(*relation.split('.'))))
            conn.execute(sql.SQL('COMMENT ON {} {} IS {}').format(sql.SQL('TABLE' if relation==RULE else 'VIEW'),
                sql.Identifier(*relation.split('.')),sql.Literal(VERSION+': literacy instruments remain distinct; observed years only; original answers retained.')))
        result = checks(conn,f,rules,e)
        rid = register(conn,f,e,plan,result)
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
    f,rules,e = checked()
    plan = json.loads((OUT/'execution.json').read_text())
    pub = json.loads((OUT/'published.json').read_text())
    require(pub['committed'],'No confirmed publication')
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        unchanged(conn,plan['before'])
        conn.execute('SET LOCAL ROLE mda_readonly')
        require(conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on','Read-only required')
        result = checks(conn,f,rules,e)
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
    result = checked()[2] if action=='check' else prepare() if action=='prepare' else publish(action=='rehearse') if action in ['rehearse','publish'] else validate()
    print(json.dumps(result,indent=2))
