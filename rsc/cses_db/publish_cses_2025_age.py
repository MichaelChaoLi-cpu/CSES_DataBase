#!/usr/bin/env python3
"""Add a source-preserving 2025 age bridge; never replace frozen v1 outputs."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path

import pandas as pd
from build_cses_additional_waves import encoded, scalar, source_keys
from cache_cses_questionnaires import file_sha, put
from psycopg import sql
from publish_cses_geography_interface import SCHEMAS, connect, fingerprint

ROOT = Path(__file__).resolve().parents[2]
VERSION = 'cses-2025-age-source-v1'
OUT = ROOT / 'data/releases' / VERSION
BACKUP = ROOT / 'data/backups/cses_2025_age_v1/before_2025_age.dump'
SPEC = ROOT / 'rsc/specs/cses_additional_waves_v1.json'
QUESTION = ROOT / 'data/processed/cses_questionnaires/additional_waves_v1/2025/text/CSES2025_Household_Questionnaire_ENG.json'
TABLE = 'cses_data.cses_2025_age_source_v1'
VIEW = 'cses_analysis.cses_2025_person_age_v1'
RULE = 'cses_alignment.cses_2025_age_rule_v1'
KEYS = ['survey_wave', 'household_key', 'record_key']
TYPES = {
    'survey_wave': 'text', 'household_key': 'text', 'record_key': 'text',
    'source_row_number': 'integer', 'native_calculated_age': 'integer',
    'manual_age_source_value': 'integer', 'first_visit_calendar_age_check': 'integer',
    'native_minus_first_visit_check': 'integer', 'first_visit_check_status': 'text',
    'source_archive_sha256': 'text', 'source_member': 'text', 'source_member_sha256': 'text',
}
# These four registries receive append-only rows; their previous contents stay protected.
APPEND = {'cses_meta.cses_alignment_release': 'alignment_release_id',
          'cses_meta.cses_storage_table': 'storage_table_id',
          'cses_meta.cses_dataset_output': 'storage_table_id',
          'cses_meta.cses_load_run': 'load_run_id'}


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def calendar_check(roster, cover):
    """A diagnostic, NOT a claim that first visit is the native formula's reference."""
    require(not cover.interview__id.duplicated().any(), 'Duplicate household cover key')
    f = roster.merge(cover[['interview__id', 's01q12_visit1']], on='interview__id',
                     how='left', validate='many_to_one', indicator=True)
    require(f['_merge'].eq('both').all(), 'Roster missing household cover')
    birth = pd.to_datetime(dict(year=f.q01ac04c, month=f.q01ac04b, day=f.q01ac04a), errors='coerce')
    visit = pd.to_datetime(f.s01q12_visit1, errors='coerce', format='mixed')
    valid = birth.notna() & visit.notna()
    birthday_pending = ((visit.dt.month < birth.dt.month) |
                        ((visit.dt.month == birth.dt.month) & (visit.dt.day < birth.dt.day)))
    age = (visit.dt.year - birth.dt.year - birthday_pending.astype(int)).where(valid).astype('Int64')
    delta = (f.age - age).astype('Int64')
    status = pd.Series('matches_first_visit_calendar_age', index=f.index, dtype='string')
    status.loc[valid & delta.ne(0)] = 'differs_from_first_visit_calendar_age'
    status.loc[birth.isna()] = 'incomplete_or_invalid_birth_date'
    status.loc[birth.notna() & visit.isna()] = 'missing_or_invalid_first_visit_date'
    return age, delta, status


def build():
    spec = json.loads(SPEC.read_text())['waves']['2025']
    archive = ROOT / spec['archive']
    require(file_sha(archive) == spec['sha256'], 'Archive fingerprint changed')
    member = spec['modules']['HL']['member']
    with zipfile.ZipFile(archive) as z:
        payload = z.read(member)
        cover_bytes = z.read('S00_HHcover.dta')
        form_sha = hashlib.sha256(z.read('CSES2025_Household_Questionnaire_ENG.xlsm')).hexdigest()
    with pd.io.stata.StataReader(io.BytesIO(payload), convert_categoricals=False) as reader:
        labels = reader.variable_labels()
        require(labels['age'] == 'Calculated age', 'Native age label changed')
        roster = reader.read()
    cover = pd.read_stata(io.BytesIO(cover_bytes), convert_categoricals=False)
    require(len(roster) == 51775, 'Unexpected roster count')
    age = roster.age
    require(age.notna().all() and age.ge(0).all() and age.mod(1).eq(0).all(), 'Invalid native calculated age')
    overlap = roster.q01ac05a.notna()
    require(age.loc[overlap].eq(roster.loc[overlap, 'q01ac05a']).all(), 'Native/manual age disagreement')
    calendar_age, delta, status = calendar_check(roster, cover)
    frame = pd.DataFrame({'survey_wave': '2025',
        'household_key': source_keys(roster, spec['household_key'], '2025'),
        'record_key': source_keys(roster, spec['household_key'] + [spec['person_key']], '2025'),
        'source_row_number': range(1, len(roster) + 1),
        'native_calculated_age': age.astype('Int64'),
        'manual_age_source_value': roster.q01ac05a.astype('Int64'),
        'first_visit_calendar_age_check': calendar_age, 'native_minus_first_visit_check': delta,
        'first_visit_check_status': status, 'source_archive_sha256': spec['sha256'],
        'source_member': member, 'source_member_sha256': hashlib.sha256(payload).hexdigest()})
    require(not frame[KEYS].isna().any().any() and not frame.duplicated(KEYS).any(), 'Invalid source key')
    question = json.loads(QUESTION.read_text())['sheets']['01 A_ Initial (2)']
    summary = {'records': len(frame), 'households': int(frame.household_key.nunique()),
        'native_age_non_null': int(age.notna().sum()), 'native_age_min': int(age.min()),
        'native_age_max': int(age.max()), 'manual_non_null': int(overlap.sum()),
        'manual_disagreements': 0, 'age_6_17': int(age.between(6, 17).sum()),
        'first_visit_check_counts': {str(k): int(v) for k, v in status.value_counts().items()},
        'native_minus_first_visit_counts': {str(k): int(v) for k, v in delta.dropna().value_counts().items()}}
    evidence = {'version': VERSION, 'inputs': {str(SPEC.relative_to(ROOT)): file_sha(SPEC),
        spec['archive']: spec['sha256'], str(QUESTION.relative_to(ROOT)): file_sha(QUESTION)},
        'source_member': member, 'source_member_sha256': hashlib.sha256(payload).hexdigest(),
        'cover_member': 'S00_HHcover.dta', 'cover_member_sha256': hashlib.sha256(cover_bytes).hexdigest(),
        'questionnaire_member_sha256': form_sha,
        'questionnaire_locator': {'sheet': '01 A_ Initial (2)',
            'cells': {c: question[c] for c in ['Z5', 'AA8', 'AF5', 'AF9']}},
        'source_labels': {k: labels[k] for k in ['age', 'q01ac05a']}, 'summary': summary,
        'contract': {'selected_native_field': 'age', 'old_manual_field_preserved': 'q01ac05a',
            'imputation_performed': False, 'formula_verified': False, 'reference_date_verified': False,
            'topcode_semantics_verified': False, 'cross_wave_equivalence_certified': False,
            'calendar_check_is_diagnostic_only': True,
            'wave_label_is_not_calendar_year_filter': True}}
    frame = frame[list(TYPES)].sort_values(KEYS).reset_index(drop=True)
    buffer = io.BytesIO()
    frame.to_parquet(buffer, index=False)
    put(OUT / 'source.parquet', buffer.getvalue())
    evidence['source_parquet_sha256'] = file_sha(OUT / 'source.parquet')
    put(OUT / 'evidence.json', encoded(evidence))
    return evidence


def checked():
    evidence = json.loads((OUT / 'evidence.json').read_text())
    for relative, sha in evidence['inputs'].items():
        require(file_sha(ROOT / relative) == sha, 'Input changed: ' + relative)
    require(file_sha(OUT / 'source.parquet') == evidence['source_parquet_sha256'], 'Source bridge changed')
    frame = pd.read_parquet(OUT / 'source.parquet')
    require(list(frame) == list(TYPES) and len(frame) == 51775 and not frame.duplicated(KEYS).any(), 'Invalid bridge')
    return frame, evidence


def definitions():
    return {VIEW: f"""SELECT p.*,a.native_calculated_age AS age_for_analysis,
      'age'::text AS age_selected_native_variable,'native_calculated_age_formula_unverified'::text AS age_selection_status,
      false AS age_formula_verified,false AS age_reference_date_verified,false AS age_topcode_semantics_verified,
      a.first_visit_calendar_age_check,a.native_minus_first_visit_check,a.first_visit_check_status,
      a.source_archive_sha256 AS age_source_archive_sha256,a.source_member_sha256 AS age_source_member_sha256,
      '{VERSION}'::text AS age_release
      FROM cses_data.cses_additional_hl_v1 p JOIN {TABLE} a USING(survey_wave,household_key,record_key)
      WHERE p.survey_wave='2025'""",
      RULE: f"""SELECT '2025'::text AS survey_wave,'{VIEW}'::text AS target_relation,
      'age_for_analysis'::text AS target_variable,'S01A_HHmember.dta'::text AS source_member,
      'age'::text AS source_variable,'Calculated age'::text AS source_label,
      'q01ac05a'::text AS preserved_manual_variable,false AS imputation_performed,
      false AS formula_verified,false AS reference_date_verified,false AS topcode_semantics_verified,
      'First-visit calendar age is diagnostic, not a replacement or certified native reference date.'::text AS qualification,
      'data/releases/{VERSION}/evidence.json'::text AS evidence_path,
      '{file_sha(OUT / 'evidence.json')}'::text AS evidence_sha256,'{VERSION}'::text AS mapping_version"""}


def rows(frame):
    return [[None if pd.isna(v) else scalar(v) for v in row]
            for row in frame.itertuples(index=False, name=None)]


def structure(conn):
    return conn.execute("""SELECT n.nspname,c.relname,c.relkind,c.relowner::bigint,c.relacl::text,c.reloptions,
      obj_description(c.oid,'pg_class') AS comment,a.attnum,a.attname,a.attnotnull,
      format_type(a.atttypid,a.atttypmod) AS type,col_description(c.oid,a.attnum) AS column_comment,
      CASE WHEN c.relkind='v' THEN pg_get_viewdef(c.oid,true) END AS definition
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
      WHERE (n.nspname=ANY(%s) OR (n.nspname='public' AND c.relname IN
        (SELECT table_name FROM cses_meta.cses_storage_table))) AND c.relkind IN ('r','v','m')
      ORDER BY n.nspname,c.relname,a.attnum""", (SCHEMAS,)).fetchall()


def prefix_fingerprint(conn, relation, column, cutoff):
    return conn.execute(sql.SQL("""SELECT count(*) AS rows,md5(coalesce(string_agg(h,'' ORDER BY h),'')) AS rows_md5
      FROM (SELECT md5(to_jsonb(t)::text) h FROM {} t WHERE {} <= %s) q""").format(
        sql.Identifier(*relation.split('.')), sql.Identifier(column)), (cutoff,)).fetchone()


def snapshot(conn):
    relations = conn.execute("""SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname=ANY(%s) AND c.relkind IN ('r','m') ORDER BY 1,2""", (SCHEMAS,)).fetchall()
    physical = {}
    for r in relations:
        relation = r['nspname'] + '.' + r['relname']
        value = fingerprint(conn, r['nspname'], r['relname'])
        if relation in APPEND:
            cutoff = conn.execute(sql.SQL('SELECT coalesce(max({}),0) AS n FROM {}').format(
                sql.Identifier(APPEND[relation]), sql.Identifier(*relation.split('.')))).fetchone()['n']
            value['prefix_column'], value['cutoff'] = APPEND[relation], cutoff
        physical[relation] = value
    return {'physical': physical, 'structure': structure(conn)}


def unchanged(conn, before):
    for relation, expected in before['physical'].items():
        actual = (prefix_fingerprint(conn, relation, expected['prefix_column'], expected['cutoff'])
                  if 'cutoff' in expected else fingerprint(conn, *relation.split('.')))
        require(actual == {k: expected[k] for k in ['rows', 'rows_md5']}, 'Previous rows changed: ' + relation)
    old_names = {(r['nspname'], r['relname']) for r in before['structure']}
    require([r for r in structure(conn) if (r['nspname'], r['relname']) in old_names] == before['structure'],
            'Previous relation definition/columns/privileges changed')


def absent(conn):
    require(not conn.execute("SELECT 1 FROM pg_event_trigger WHERE evtenabled<>'D'").fetchone(), 'Active DDL event trigger')
    for relation in [TABLE, VIEW, RULE]:
        require(conn.execute('SELECT to_regclass(%s) r', (relation,)).fetchone()['r'] is None,
                'Target exists; validate instead of replacing: ' + relation)
    require(not conn.execute('SELECT 1 FROM cses_meta.cses_alignment_release WHERE mapping_version=%s',
                             (VERSION,)).fetchone(), 'Release already registered')


def validate(conn, frame):
    actual = conn.execute(sql.SQL('SELECT * FROM {} ORDER BY survey_wave,household_key,record_key').format(
        sql.Identifier(*TABLE.split('.')))).fetchall()
    require([list(r.values()) for r in actual] == rows(frame), 'Published source bridge differs')
    n = conn.execute(f"""SELECT count(*) n,count(DISTINCT (survey_wave,household_key,record_key)) u,
      count(age_for_analysis) age_n,count(age_source_value) manual_n,
      count(*) FILTER(WHERE age_source_value IS DISTINCT FROM manual_age_source_value) manual_mismatch
      FROM {VIEW} v JOIN {TABLE} a USING(survey_wave,household_key,record_key)""").fetchone()
    require(n == {'n': 51775, 'u': 51775, 'age_n': 51775, 'manual_n': 165, 'manual_mismatch': 0}, 'Join/manual preservation failed')
    columns = conn.execute("SELECT attname FROM pg_attribute WHERE attrelid='cses_data.cses_additional_hl_v1'::regclass AND attnum>0 AND NOT attisdropped ORDER BY attnum").fetchall()
    projection = sql.SQL(',').join(sql.Identifier(r['attname']) for r in columns)
    mismatch = conn.execute(sql.SQL("""WITH b AS (SELECT {cols} FROM cses_data.cses_additional_hl_v1 WHERE survey_wave='2025'),
      v AS (SELECT {cols} FROM {view}) SELECT EXISTS((SELECT * FROM b EXCEPT ALL SELECT * FROM v)
      UNION ALL (SELECT * FROM v EXCEPT ALL SELECT * FROM b)) AS mismatch""").format(
        cols=projection, view=sql.Identifier(*VIEW.split('.')))).fetchone()['mismatch']
    require(not mismatch, 'Old roster columns changed in interface')
    return n


def prepare():
    frame, evidence = checked()
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        absent(conn)
        before = snapshot(conn)
    require(not BACKUP.exists() and not (OUT / 'execution.json').exists(), 'Existing preparation; never overwrite backup')
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['/opt/homebrew/bin/pg_dump', '-d', 'mda', '-Fc',
                    *[f'--schema={s}' for s in SCHEMAS], f'--file={BACKUP}'], check=True, timeout=300)
    subprocess.run(['/opt/homebrew/bin/pg_restore', '--file=/dev/null', str(BACKUP)], check=True, timeout=300)
    plan = {'version': VERSION, 'before': before, 'summary': evidence['summary'],
        'evidence_sha256': file_sha(OUT / 'evidence.json'), 'script_sha256': file_sha(Path(__file__)),
        'backup': str(BACKUP.relative_to(ROOT)), 'backup_sha256': file_sha(BACKUP),
        'full_backup_decompression_verified': True, 'definitions': definitions()}
    put(OUT / 'execution.json', encoded(plan))
    return {'prepared': True, 'rows': len(frame), 'backup': plan['backup']}


def register(conn, plan, checks):
    rid = conn.execute("""INSERT INTO cses_meta.cses_alignment_release(mapping_version,status,description,
      specification_sha256,approved_at) VALUES(%s,'approved',%s,%s,now()) RETURNING alignment_release_id""",
      (VERSION, '2025 native calculated-age selection; formula/reference date/topcode unverified; originals unchanged.',
       file_sha(OUT / 'evidence.json'))).fetchone()['alignment_release_id']
    datasets = conn.execute("""SELECT d.dataset_id,d.member_path FROM cses_meta.cses_dataset d
      JOIN cses_meta.cses_survey s USING(survey_id) WHERE s.survey_wave='2025'
      AND d.member_path IN ('S01A_HHmember.dta','S00_HHcover.dta')""").fetchall()
    require(len(datasets) == 2, 'Expected existing roster/cover dataset registrations')
    for relation in [TABLE, VIEW, RULE]:
        schema, name = relation.split('.')
        count = conn.execute(sql.SQL('SELECT count(*) n FROM {}').format(sql.Identifier(schema, name))).fetchone()['n']
        columns = conn.execute('SELECT count(*) n FROM information_schema.columns WHERE table_schema=%s AND table_name=%s',
                               (schema, name)).fetchone()['n']
        sid = conn.execute("""INSERT INTO cses_meta.cses_storage_table(table_schema,table_name,object_family,
          module_code,analytical_grain,natural_key,row_count,column_count,relation_fingerprint)
          VALUES(%s,%s,%s,'HL',%s,%s,%s,%s,%s) RETURNING storage_table_id""",
          (schema, name, 'alignment_summary' if relation == RULE else 'final',
           'field_wave' if relation == RULE else 'person_wave', ['survey_wave','target_variable'] if relation == RULE else KEYS,
           count, columns, digest(fingerprint(conn, schema, name)))).fetchone()['storage_table_id']
        for d in datasets:
            conn.execute("""INSERT INTO cses_meta.cses_dataset_output(dataset_id,storage_table_id,alignment_release_id,
              contribution_role,output_row_count) VALUES(%s,%s,%s,%s,%s)""",
              (d['dataset_id'], sid, rid, 'source' if d['member_path'] == 'S01A_HHmember.dta' else 'validation', count))
    conn.execute("""INSERT INTO cses_meta.cses_load_run(alignment_release_id,run_scope,source_manifest_sha256,status,
      row_counts,validation_summary,finished_at) VALUES(%s,%s,%s,'loaded',%s::jsonb,%s::jsonb,now())""",
      (rid, VERSION, file_sha(OUT / 'evidence.json'), json.dumps({TABLE: 51775, VIEW: 51775, RULE: 1}),
       json.dumps({'checks': checks, 'original_rows_preserved': True, 'backup_sha256': plan['backup_sha256']})))
    return rid


def publish(rehearse=False):
    frame, _ = checked()
    plan = json.loads((OUT / 'execution.json').read_text())
    require(file_sha(Path(__file__)) == plan['script_sha256'], 'Prepared script changed')
    require(file_sha(OUT / 'evidence.json') == plan['evidence_sha256'], 'Prepared evidence changed')
    require(file_sha(BACKUP) == plan['backup_sha256'] and definitions() == plan['definitions'], 'Backup/definitions changed')
    if not rehearse:
        rehearsal = json.loads((OUT / 'rehearsal.json').read_text())
        require(rehearsal['execution_sha256'] == file_sha(OUT / 'execution.json') and not rehearsal['committed'], 'Matching rollback rehearsal required')
    with connect(False) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (VERSION,))
        for relation in plan['before']['physical']:
            conn.execute(sql.SQL('LOCK TABLE {} IN {} MODE').format(sql.Identifier(*relation.split('.')),
                         sql.SQL('SHARE ROW EXCLUSIVE' if relation in APPEND else 'SHARE')))
        absent(conn)
        unchanged(conn, plan['before'])
        columns = sql.SQL(',').join(sql.SQL('{} {}').format(sql.Identifier(k), sql.SQL(v + ' NOT NULL' if k not in
            ['manual_age_source_value', 'first_visit_calendar_age_check', 'native_minus_first_visit_check'] else v)) for k, v in TYPES.items())
        conn.execute(sql.SQL("CREATE TABLE {} ({}, PRIMARY KEY (survey_wave,household_key,record_key), CHECK(survey_wave='2025'), CHECK(native_calculated_age>=0))").format(
            sql.Identifier(*TABLE.split('.')), columns))
        with conn.cursor().copy(sql.SQL('COPY {} FROM STDIN').format(sql.Identifier(*TABLE.split('.')))) as copy:
            for row in rows(frame):
                copy.write_row(row)
        for relation, query in definitions().items():
            conn.execute(sql.SQL('CREATE VIEW {} AS ').format(sql.Identifier(*relation.split('.'))) + sql.SQL(query))
        for relation in [TABLE, VIEW, RULE]:
            conn.execute(sql.SQL('GRANT SELECT ON {} TO mda_readonly').format(sql.Identifier(*relation.split('.'))))
            conn.execute(sql.SQL('COMMENT ON {} {} IS {}').format(sql.SQL('TABLE' if relation == TABLE else 'VIEW'),
                sql.Identifier(*relation.split('.')), sql.Literal('2025 native age selection only. Formula, reference date and topcode unverified; first-visit comparison is diagnostic. See ' + VERSION)))
        checks = validate(conn, frame)
        rid = register(conn, plan, checks)
        unchanged(conn, plan['before'])
        conn.execute(sql.SQL('ANALYZE {}').format(sql.Identifier(*TABLE.split('.'))))
        if rehearse:
            conn.rollback()
    if rehearse:
        with connect() as conn:
            absent(conn)
            unchanged(conn, plan['before'])
    result = {'committed': not rehearse, 'release_id': rid, 'checks': checks,
              'execution_sha256': file_sha(OUT / 'execution.json')}
    put(OUT / ('rehearsal.json' if rehearse else 'published.json'), encoded(result))
    return result


def postflight():
    frame, evidence = checked()
    plan = json.loads((OUT / 'execution.json').read_text())
    publication = json.loads((OUT / 'published.json').read_text())
    require(publication['committed'], 'No confirmed publication')
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        unchanged(conn, plan['before'])
        conn.execute('SET LOCAL ROLE mda_readonly')
        require(conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only'] == 'on', 'Read-only required')
        checks = validate(conn, frame)
        require(conn.execute(f'SELECT evidence_sha256 FROM {RULE}').fetchone()['evidence_sha256'] == file_sha(OUT / 'evidence.json'), 'Rule evidence mismatch')
        load = conn.execute('SELECT status FROM cses_meta.cses_load_run WHERE alignment_release_id=%s', (publication['release_id'],)).fetchall()
        require(load == [{'status': 'loaded'}], 'Load registry mismatch')
    result = {'validated': True, 'read_role': 'mda_readonly', 'read_only': True,
        'all_previous_rows_and_interfaces_unchanged': True, 'checks': checks, 'summary': evidence['summary'],
        'publication_sha256': file_sha(OUT / 'published.json')}
    put(OUT / 'validated.json', encoded(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'prepare', 'rehearse', 'publish', 'validate'])
    action = parser.parse_args().action
    result = {'build': build, 'prepare': prepare, 'rehearse': lambda: publish(True),
              'publish': publish, 'validate': postflight}[action]()
    print(json.dumps(result, indent=2))
