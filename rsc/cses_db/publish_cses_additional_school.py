#!/usr/bin/env python3
"""Backed-up, additive school views; no original attendance answer is updated."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd
from align_cses_additional_school import COVERAGE, KEYS, OUT, ROOT, RULE, VERSION, VIEW, require, summary
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put
from psycopg import sql
from psycopg.types.json import Jsonb
from publish_cses_2025_age import APPEND, digest, snapshot, unchanged
from publish_cses_geography_interface import SCHEMAS, connect, fingerprint

BACKUP = ROOT/'data/backups/cses_additional_school_v1/before_school_attendance.dump'
SUPPORT = ['rsc/cses_db/publish_cses_geography_interface.py', 'rsc/cses_db/cache_cses_questionnaires.py']


def checked():
    evidence = json.loads((OUT/'evidence.json').read_text())
    for relative, expected in evidence['inputs'].items():
        require(file_sha(ROOT/relative) == expected, 'Input changed: '+relative)
    require(file_sha(OUT/'expected.parquet') == evidence['expected_sha256'], 'Expected projection changed')
    frame = pd.read_parquet(OUT/'expected.parquet')
    require(len(frame) == 212779 and not frame.duplicated(KEYS).any(), 'Roster grain mismatch')
    return frame, evidence


def rule_query(evidence):
    payload = sql.Literal(json.dumps(evidence['rules'])).as_string()
    return f"""SELECT r.*,'{file_sha(OUT/'evidence.json')}'::text AS evidence_sha256,
      'data/releases/{VERSION}/evidence.json'::text AS evidence_path
      FROM jsonb_to_recordset({payload}::jsonb) AS r(survey_wave text,questionnaire_minimum_age integer,
      skip_supported boolean,concept_scope text,current_variable text,ever_variable text,education_member text,
      neutral_highest_codes integer[],neutral_current_codes integer[],questionnaire_path text,
      questionnaire_sha256 text,locator text,holiday_instruction_explicit boolean,
      cross_wave_equivalence_certified boolean,mapping_version text)"""


def person_query(columns, rule_relation=RULE):
    # SQL implementation deliberately separate from the local pandas classifier.
    query = f"""WITH inputs AS (
      SELECT p.survey_wave,p.household_key,p.record_key,p.age_source_value::double precision,
      CASE WHEN p.survey_wave='2025' THEN a.age_for_analysis ELSE p.age_source_value END::double precision AS age_for_school_analysis,
      CASE WHEN p.survey_wave='2025' THEN 'native_calculated_age_formula_unverified'
        ELSE 'published_source_age_no_new_exact_age_certification' END::text AS age_selection_status,
      a.first_visit_check_status AS age_first_visit_check_status,
      e.currently_attending_school::bigint AS school_current_observed,e.ever_attended_school::bigint AS school_ever_observed,
      e.highest_education_level_source_code::double precision AS school_highest_level_source_code,
      e.current_education_level_source_code::double precision AS school_current_level_source_code,
      (e.source_values->>r.current_variable)::double precision AS school_current_native_code,
      (e.source_values->>r.ever_variable)::double precision AS school_ever_native_code,
      e.record_key IS NOT NULL AS education_record_linked,r.questionnaire_minimum_age,
      r.concept_scope AS school_concept_scope,r.skip_supported,r.neutral_highest_codes,r.neutral_current_codes
      FROM cses_data.cses_additional_hl_v1 p JOIN {rule_relation} r USING(survey_wave)
      LEFT JOIN cses_data.cses_additional_ed_v1 e USING(survey_wave,household_key,record_key)
      LEFT JOIN cses_analysis.cses_2025_person_age_v1 a USING(survey_wave,household_key,record_key)),
      flags AS (SELECT *,age_for_school_analysis>=questionnaire_minimum_age AS school_age_eligible,
      (school_current_native_code IS NOT NULL AND school_current_native_code NOT IN (1,2)) OR
        (school_ever_native_code IS NOT NULL AND school_ever_native_code NOT IN (1,2)) AS school_invalid_response_code,
      coalesce(school_ever_observed=0 AND school_current_observed=1,false) AS school_ever_no_current_yes,
      coalesce(school_ever_observed=0 AND
        ((school_highest_level_source_code IS NOT NULL AND NOT school_highest_level_source_code=ANY(neutral_highest_codes)) OR
         (school_current_level_source_code IS NOT NULL AND NOT school_current_level_source_code=ANY(neutral_current_codes))),false) AS school_never_with_history_response,
      coalesce(school_current_observed=0 AND school_current_level_source_code IS NOT NULL AND
        NOT school_current_level_source_code=ANY(neutral_current_codes),false) AS school_not_current_with_current_grade,
      coalesce(skip_supported AND school_current_observed=1 AND school_current_level_source_code IS NULL,false) AS school_current_grade_missing,
      skip_supported AND school_ever_observed IS NULL AND school_current_observed IS NOT NULL AS school_gate_missing_with_current_observed
      FROM inputs), conflicts AS (SELECT *,
      school_ever_no_current_yes OR school_never_with_history_response OR school_not_current_with_current_grade AS school_route_conflict,
      coalesce(education_record_linked AND NOT school_age_eligible,false) AS education_record_outside_age_universe FROM flags),
      statuses AS (SELECT *,CASE
        WHEN age_for_school_analysis IS NULL THEN 'unknown_age_eligibility'
        WHEN NOT school_age_eligible THEN 'outside_questionnaire_age_range'
        WHEN NOT education_record_linked THEN 'missing_education_record'
        WHEN school_invalid_response_code THEN 'unrecognized_native_response_code'
        WHEN school_route_conflict THEN 'unresolved_route_conflict'
        WHEN school_gate_missing_with_current_observed THEN 'observed_current_gate_missing'
        WHEN school_current_observed IS NOT NULL THEN 'observed_current'
        WHEN skip_supported AND school_ever_observed=0 THEN 'documented_skip_inferred_no'
        WHEN skip_supported AND school_ever_observed IS NULL THEN 'unanswered_gate_and_current'
        WHEN skip_supported AND school_ever_observed=1 THEN 'unanswered_current_after_ever_yes'
        ELSE 'unanswered_current_attendance' END::text AS school_route_status FROM conflicts),
      qualified AS (SELECT *,CASE WHEN school_route_status IN ('observed_current','observed_current_gate_missing')
        THEN school_current_observed WHEN school_route_status='documented_skip_inferred_no' THEN 0 ELSE NULL END::bigint AS school_attendance_qualified,
      school_route_status='documented_skip_inferred_no' AS school_attendance_derived_from_skip,
      false AS school_cross_wave_equivalence_certified,'{VERSION}'::text AS school_release FROM statuses),
      final AS (SELECT *,school_attendance_qualified IS NOT NULL AS qualified_denominator_eligible FROM qualified)
      SELECT {','.join(columns)} FROM final"""
    return query


def coverage_query():
    return f"""WITH b AS (SELECT s.*,band.age_band FROM {VIEW} s CROSS JOIN LATERAL
      (VALUES ('questionnaire_age_eligible',s.school_age_eligible),
      ('ages_6_17',s.age_for_school_analysis BETWEEN 6 AND 17),
      ('ages_10_14',s.age_for_school_analysis BETWEEN 10 AND 14)) AS band(age_band,included) WHERE band.included),
      counts AS (SELECT survey_wave,age_band,school_concept_scope AS concept_scope,count(*) AS members,
      count(*) FILTER(WHERE school_attendance_qualified=1) AS qualified_yes,
      count(*) FILTER(WHERE school_attendance_qualified=0) AS qualified_no,
      count(school_attendance_qualified) AS qualified_denominator,
      count(*) FILTER(WHERE school_attendance_qualified IS NULL) AS unknown_or_excluded,
      count(*) FILTER(WHERE school_attendance_derived_from_skip) AS inferred_no,
      count(*) FILTER(WHERE school_route_conflict) AS route_conflicts,
      count(*) FILTER(WHERE school_invalid_response_code) AS invalid_code_records,
      count(*) FILTER(WHERE school_current_observed=1) AS observed_yes,count(school_current_observed) AS observed_nonnull
      FROM b GROUP BY survey_wave,age_band,school_concept_scope)
      SELECT *,round(100.0*qualified_yes/nullif(qualified_denominator,0),6)::double precision AS qualified_unweighted_yes_pct,
      round(100.0*observed_yes/nullif(observed_nonnull,0),6)::double precision AS observed_only_yes_pct,
      round(100.0*qualified_yes/nullif(members,0),6)::double precision AS missingness_lower_bound_pct,
      round(100.0*(qualified_yes+unknown_or_excluded)/nullif(members,0),6)::double precision AS missingness_upper_bound_pct FROM counts"""


def definitions(frame, evidence):
    return {RULE: rule_query(evidence), VIEW: person_query(list(frame)), COVERAGE: coverage_query()}


def absent(conn):
    require(not conn.execute("SELECT 1 FROM pg_event_trigger WHERE evtenabled<>'D'").fetchone(), 'Active DDL event trigger')
    for relation in [RULE,VIEW,COVERAGE]:
        require(conn.execute('SELECT to_regclass(%s) r',(relation,)).fetchone()['r'] is None, 'Target exists; validate, never replace: '+relation)
    require(not conn.execute('SELECT 1 FROM cses_meta.cses_alignment_release WHERE mapping_version=%s',(VERSION,)).fetchone(), 'Release already registered')


def checks(conn, frame, evidence, published=True):
    query = f'SELECT * FROM {VIEW}' if published else person_query(list(frame), '('+rule_query(evidence)+')')
    result = conn.execute(sql.SQL('SELECT * FROM ({}) v ORDER BY survey_wave COLLATE "C",household_key COLLATE "C",record_key COLLATE "C"').format(sql.SQL(query))).fetchall()
    live = pd.DataFrame(result).astype(frame.dtypes.to_dict())
    pd.testing.assert_frame_equal(live, frame, check_exact=True)
    require(summary(live) == evidence['summary'], 'Live denominators differ')
    if published:
        rows = conn.execute(f'SELECT * FROM {COVERAGE} ORDER BY survey_wave,age_band').fetchall()
        require(rows == sorted(evidence['summary'], key=lambda r:(r['survey_wave'],r['age_band'])), 'SQL coverage differs')
        rs = conn.execute(f'SELECT survey_wave,questionnaire_sha256,evidence_sha256 FROM {RULE} ORDER BY survey_wave').fetchall()
        require(rs == [{'survey_wave':r['survey_wave'],'questionnaire_sha256':r['questionnaire_sha256'],
                        'evidence_sha256':file_sha(OUT/'evidence.json')} for r in evidence['rules']], 'Questionnaire rule differs')
    return {'all_cells_match':True, 'records':len(live), 'qualified_records':int(live.qualified_denominator_eligible.sum()),
            'inferred_no':int(live.school_attendance_derived_from_skip.sum()), 'age_band_rows':len(evidence['summary'])}


def prepare():
    frame, evidence = checked()
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        absent(conn)
        result = checks(conn, frame, evidence, False)
        before = snapshot(conn)
    require(not BACKUP.exists() and not (OUT/'execution.json').exists(), 'Existing preparation; preserve it')
    BACKUP.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['/opt/homebrew/bin/pg_dump','-d','mda','-Fc',*[f'--schema={s}' for s in SCHEMAS],f'--file={BACKUP}'],check=True,timeout=300)
    subprocess.run(['/opt/homebrew/bin/pg_restore','--file=/dev/null',str(BACKUP)],check=True,timeout=300)
    plan = {'version':VERSION, 'before':before, 'preflight':result, 'evidence_sha256':file_sha(OUT/'evidence.json'),
            'script_sha256':file_sha(Path(__file__)), 'support_sha256':{p:file_sha(ROOT/p) for p in SUPPORT},
            'backup':str(BACKUP.relative_to(ROOT)), 'backup_sha256':file_sha(BACKUP),
            'full_backup_decompression_verified':True, 'definitions':definitions(frame,evidence)}
    put(OUT/'execution.json',encoded(plan))
    return {'prepared':True,**result}


def register(conn, frame, evidence, plan, result):
    rid = conn.execute("""INSERT INTO cses_meta.cses_alignment_release(mapping_version,status,description,specification_sha256,approved_at)
      VALUES(%s,'approved',%s,%s,now()) RETURNING alignment_release_id""",(VERSION,
      'School attendance with questionnaire age ranges, explicit skip derivation and conservative conflict exclusions; no unrestricted equivalence.',
      file_sha(OUT/'evidence.json'))).fetchone()['alignment_release_id']
    datasets = conn.execute("""SELECT s.survey_wave,d.dataset_id,d.member_path FROM cses_meta.cses_dataset d
      JOIN cses_meta.cses_survey s USING(survey_id) WHERE s.survey_wave=ANY(%s)""",(list(frame.survey_wave.unique()),)).fetchall()
    sources = json.loads((ROOT/'rsc/specs/cses_additional_waves_v1.json').read_text())['waves']
    for relation, grain, key in [(VIEW,'person_wave',KEYS),(RULE,'field_wave',['survey_wave']),
                                  (COVERAGE,'wave_age_band',['survey_wave','age_band'])]:
        schema, name = relation.split('.')
        n = conn.execute(sql.SQL('SELECT count(*) n FROM {}').format(sql.Identifier(schema,name))).fetchone()['n']
        cols = conn.execute('SELECT count(*) n FROM information_schema.columns WHERE table_schema=%s AND table_name=%s',(schema,name)).fetchone()['n']
        sid = conn.execute("""INSERT INTO cses_meta.cses_storage_table(table_schema,table_name,object_family,module_code,
          analytical_grain,natural_key,row_count,column_count,relation_fingerprint) VALUES(%s,%s,'alignment_summary','ED',%s,%s,%s,%s,%s)
          RETURNING storage_table_id""",(schema,name,grain,key,n,cols,digest(fingerprint(conn,schema,name)))).fetchone()['storage_table_id']
        for w,cfg in sources.items():
            members = {cfg['modules']['HL']['member']:'source', cfg['modules']['ED']['member']:'source'}
            if w == '2025' and relation != RULE:
                members['S00_HHcover.dta'] = 'validation'
            for member,role in members.items():
                matched = [d for d in datasets if d['survey_wave']==w and d['member_path']==member]
                require(len(matched)==1, 'Expected unique existing source dataset')
                count = conn.execute(sql.SQL('SELECT count(*) n FROM {} WHERE survey_wave=%s').format(sql.Identifier(schema,name)),(w,)).fetchone()['n']
                conn.execute("""INSERT INTO cses_meta.cses_dataset_output(dataset_id,storage_table_id,alignment_release_id,contribution_role,output_row_count)
                  VALUES(%s,%s,%s,%s,%s)""",(matched[0]['dataset_id'],sid,rid,role,count))
    conn.execute("""INSERT INTO cses_meta.cses_load_run(alignment_release_id,run_scope,source_manifest_sha256,status,
      row_counts,validation_summary,finished_at) VALUES(%s,%s,%s,'loaded',%s,%s,now())""",
      (rid,VERSION,file_sha(OUT/'evidence.json'),Jsonb({VIEW:len(frame),RULE:5,COVERAGE:15}),
       Jsonb({'checks':result,'previous_rows_preserved':True,'backup_sha256':plan['backup_sha256']})))
    return rid


def publish(rehearse=False):
    frame,evidence = checked()
    plan = json.loads((OUT/'execution.json').read_text())
    require(plan['script_sha256']==file_sha(Path(__file__)) and plan['evidence_sha256']==file_sha(OUT/'evidence.json'), 'Prepared implementation/evidence changed')
    require(plan['backup_sha256']==file_sha(BACKUP) and plan['definitions']==definitions(frame,evidence), 'Backup/SQL changed')
    require(all(file_sha(ROOT/p)==sha for p,sha in plan['support_sha256'].items()), 'Support implementation changed')
    if not rehearse:
        rehearsal = json.loads((OUT/'rehearsal.json').read_text())
        require(not rehearsal['committed'] and rehearsal['execution_sha256']==file_sha(OUT/'execution.json'), 'Matching rollback rehearsal required')
    with connect(False) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(VERSION,))
        for relation in plan['before']['physical']:
            conn.execute(sql.SQL('LOCK TABLE {} IN {} MODE').format(sql.Identifier(*relation.split('.')),
                         sql.SQL('SHARE ROW EXCLUSIVE' if relation in APPEND else 'SHARE')))
        absent(conn)
        unchanged(conn,plan['before'])
        for relation,query in definitions(frame,evidence).items():
            conn.execute(sql.SQL('CREATE VIEW {} AS ').format(sql.Identifier(*relation.split('.')))+sql.SQL(query))
            conn.execute(sql.SQL('GRANT SELECT ON {} TO mda_readonly').format(sql.Identifier(*relation.split('.'))))
            conn.execute(sql.SQL('COMMENT ON VIEW {} IS {}').format(sql.Identifier(*relation.split('.')),
                sql.Literal(VERSION+': source answers unchanged; derived skip No explicit; conflicts/unknowns retained; no blanket comparability.')))
        result = checks(conn,frame,evidence)
        rid = register(conn,frame,evidence,plan,result)
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
    frame,evidence = checked()
    plan = json.loads((OUT/'execution.json').read_text())
    publication = json.loads((OUT/'published.json').read_text())
    require(publication['committed'], 'No confirmed publication')
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        unchanged(conn,plan['before'])
        conn.execute('SET LOCAL ROLE mda_readonly')
        require(conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on', 'Read-only required')
        result = checks(conn,frame,evidence)
        counts = conn.execute("""SELECT count(DISTINCT o.storage_table_id) AS outputs,count(*) AS edges
          FROM cses_meta.cses_dataset_output o JOIN cses_meta.cses_alignment_release r USING(alignment_release_id)
          WHERE r.mapping_version=%s""",(VERSION,)).fetchone()
        # 1996 uses one source dataset for both HL and ED: one shared edge per output.
        require(counts=={'outputs':3,'edges':29}, 'Source-output metadata differs')
        require(conn.execute('SELECT status FROM cses_meta.cses_load_run WHERE alignment_release_id=%s',(publication['release_id'],)).fetchall()==[{'status':'loaded'}], 'Load registry differs')
    result = {'validated':True,'role':'mda_readonly','read_only':True,'previous_rows_and_interfaces_unchanged':True,
              'checks':result,'metadata':counts,'published_sha256':file_sha(OUT/'published.json')}
    put(OUT/'validated.json',encoded(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['check','prepare','rehearse','publish','validate'])
    action = parser.parse_args().action
    if action=='check':
        f,e = checked()
        with connect() as c:
            c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            c.execute('SET LOCAL ROLE mda_readonly')
            result = checks(c,f,e,False)
    else:
        result = {'prepare':prepare,'rehearse':lambda:publish(True),'publish':publish,'validate':validate}[action]()
    print(json.dumps(result,indent=2))
