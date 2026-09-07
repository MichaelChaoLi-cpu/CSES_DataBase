#!/usr/bin/env python3
"""Add explicit missing-code interpretations and intact 2007 job-index evidence."""
from __future__ import annotations

import argparse
import copy
import io
import json
import os
import subprocess
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd
from cses_baseline_metadata import canonical_sha256, connect_database
from cses_hh_hl_common import AlignmentContext, clean_string, snake_case, standardize_source
from cses_lineage_graph import GraphBuilder, _node_id
from inventory_cses_archives import discover_sources
from organize_cses_questionnaires import digest, write_once
from plan_cses_age_topcode import checked_review, require
from psycopg import sql
from publish_cses_age_topcode import read_only
from review_cses_education import normalize_legacy_source_paths
from review_cses_employment_classification import (
    EMPLOYER,
    FIELDS,
    PINS,
    SUP_ARCHIVE,
    SUP_MEMBER,
    data_review,
    evidence,
    special_labels,
    supplemental_2007,
    width_for,
)
from review_cses_employment_hours_status import registry

SELF = "rsc/cses_db/publish_cses_classification_correction.py"
VERSION = "cses-employment-classification-qualified-v1"
DIRECTORY = "data/processing/cses/employment_classification_corrected_v1"
RELEASE = f"data/releases/{VERSION}"
REVIEW = "data/processing/cses/employment_classification_review_v1/review.json"
REVIEW_SHA = "e26b6d86ba717cab287a2bddb4f2d9f2869281d04fd38ddf230902973b3bd4cd"
GRAPH = "data/lineage/cses_lineage_graph_v13.json"
TABLE, JOBS, VIEW, RULE = "cses_ec_jobs_2007_source_v1", "cses_ec_jobs_2007_v1", "cses_ec_classification_v1", "cses_ec_classification_rule_v1"
OBJECTS = [TABLE, JOBS, VIEW, RULE]
VIEWS = [JOBS, VIEW, RULE]
INTERPRETED = [f.replace("_source_code", "_interpreted_code") for f in FIELDS]
FLAGS = [f.replace("_source_code", "_is_explicit_labelled_missing") for f in FIELDS]
JOB_COLUMNS = ["survey_wave", "person_id", "household_id", "pkid", "q13b_c01", "q13b_ocid",
               "q13bc02b", "q13bc03b", "q13bc07", "source_archive", "source_member", "source_row_id", "source_sha256"]
JOB_TYPES = ["text", "text", "text", "text", "smallint", "smallint", "text", "text", "smallint", "text", "text", "text", "text"]


def qualified(before, rules):
    after = before.copy()
    require(not set(INTERPRETED + FLAGS) & set(before), "Qualification already applied")
    for field, target, flag in zip(FIELDS, INTERPRETED, FLAGS, strict=True):
        selected = [r for r in rules if r['canonical_field'] == field]
        missing = pd.Series(False, index=before.index)
        scope = pd.Series(False, index=before.index)
        for r in selected:
            wave = before.survey_wave.eq(r['survey_wave'])
            scope |= wave
            missing |= wave & before[field].astype('string').eq(r['source_code']).fillna(False)
        after[target] = before[field].mask(missing)
        after[flag] = missing.astype('boolean').where(scope & before[field].notna())
    pd.testing.assert_frame_equal(after[list(before)], before, check_exact=True)
    return after[[*before.columns, *INTERPRETED, *FLAGS]]


def view_query(columns, rules):
    expressions = [sql.Identifier('b', c) for c in columns]
    flags = []
    for field, target, flag in zip(FIELDS, INTERPRETED, FLAGS, strict=True):
        selected = [r for r in rules if r['canonical_field'] == field]
        conditions = [sql.SQL('(b.survey_wave={} AND b.{}::text={})').format(
            sql.Literal(r['survey_wave']), sql.Identifier(field), sql.Literal(r['source_code'])) for r in selected]
        condition = sql.SQL(' OR ').join(conditions)
        expressions.append(sql.SQL('CASE WHEN {} THEN NULL ELSE b.{} END AS {}').format(condition, sql.Identifier(field), sql.Identifier(target)))
        waves = sorted({r['survey_wave'] for r in selected})
        flags.append(sql.SQL('CASE WHEN b.survey_wave IN ({}) AND b.{} IS NOT NULL THEN ({}) ELSE NULL END::boolean AS {}').format(
            sql.SQL(',').join(map(sql.Literal, waves)), sql.Identifier(field), condition, sql.Identifier(flag)))
    return sql.SQL('SELECT {} FROM cses_analysis.cses_ec_aligned_v1 b').format(sql.SQL(',').join(expressions + flags)).as_string()


def jobs_query(relation=None):
    return sql.SQL("""SELECT j.*,b.total_occupations_past_7_days,
      (j.q13b_ocid>b.total_occupations_past_7_days)::boolean AS index_exceeds_reported_job_count,
      (j.q13b_ocid=2 AND NOT bool_or(j.q13b_ocid=1) OVER (PARTITION BY j.survey_wave,j.person_id))::boolean AS index_2_without_index_1,
      'unverified_primary_secondary_meaning'::text AS job_index_interpretation
      FROM {} j JOIN cses_analysis.cses_ec_aligned_v1 b
      ON j.survey_wave=b.survey_wave AND j.person_id=b.person_id AND j.household_id=b.household_id""").format(
          relation or sql.Identifier('cses_analysis', TABLE)).as_string()


def local_plan(root):
    checked_review(root)
    require(digest((root / REVIEW).read_bytes()) == REVIEW_SHA, 'Frozen classification review changed')
    review = json.loads((root / REVIEW).read_text())
    require(digest((root / 'rsc/cses_db/review_cses_employment_classification.py').read_bytes()) == review['implementation_sha256'], 'Review implementation changed')
    for path, sha in {**PINS, **review['frozen_inputs_sha256']}.items():
        require(digest((root / path).read_bytes()) == sha, f'Frozen input changed: {path}')
    questions, _ = evidence(root)
    original, profiles, sources, waves = data_review(root, questions, review['source_verification']['classification_codebook'])
    require([profiles, sources, waves] == [review[k] for k in ['profiles','raw_sources','wave_counts']], 'Raw reproduction differs from review')
    require(supplemental_2007(root, original) == review['supplemental_2007'], 'Supplement evidence changed')
    before = pd.read_parquet(root / 'data/processing/cses/employment_corrected_v1/final_EC_CSES.parquet')
    rules = []
    for source in sources:
        for field in source['fields']:
            labels = (field['fresh_stata_metadata'] or {}).get('value_labels') or {}
            for code, label in special_labels(labels).items():
                f, wave = field['field'], source['survey_wave']
                code = code if f in EMPLOYER else code.zfill(width_for(f, wave))
                rules.append({'rule_id': f'{wave}:{f}:{code}', 'survey_wave': wave, 'canonical_field': f,
                    'source_variable_id': field['source_variable_id'], 'source_variable': field['source_variable'],
                    'source_code': code, 'source_label': label,
                    'affected_cells': int((before.survey_wave.eq(wave) & before[f].astype('string').eq(code).fillna(False)).sum()),
                    'release_id': VERSION, 'review_sha256': REVIEW_SHA})
    rules.sort(key=lambda r: r['rule_id'])
    require(len(rules) == 14 and sum(r['affected_cells'] for r in rules) == 774, 'Exact 14 rules / 774 cells required')
    after = qualified(before, rules)
    require(after.shape == (332903, 86), 'Unexpected qualified view size')
    source = next(s for s in discover_sources(root) if s.archive_members == (SUP_MEMBER,))
    ctx = AlignmentContext(root=root)
    raw = ctx.load(source)
    keys = standardize_source(ctx, source, '2007', 'EC').rename(columns=snake_case)
    jobs = keys[['survey_wave','person_id','household_id']].copy()
    jobs['pkid'] = clean_string(raw.pkid)
    for c in ['q13b_c01','q13b_ocid','q13bc07']:
        jobs[c] = raw[c].astype('Int16')
    for c in ['q13bc02b','q13bc03b']:
        jobs[c] = raw[c].astype('string')  # Raw spelling, no padding or inferred recoding.
    jobs['source_archive'] = pd.Series(SUP_ARCHIVE, index=jobs.index, dtype='string')
    jobs['source_member'] = pd.Series(SUP_MEMBER, index=jobs.index, dtype='string')
    jobs['source_row_id'] = keys.source_row_id
    jobs['source_sha256'] = pd.Series(digest(source.read_bytes()), index=jobs.index, dtype='string')
    jobs = jobs[JOB_COLUMNS].sort_values(['survey_wave','person_id','q13b_ocid']).reset_index(drop=True)
    require(len(jobs) == 11949 and not jobs.duplicated(['survey_wave','person_id','q13b_ocid']).any(), 'Invalid job grain')
    require(not jobs.drop(columns=['q13bc07']).isna().any().any() and int(jobs.q13bc07.isna().sum()) == 27, 'Unexpected source missingness')
    base = before.set_index(['survey_wave','person_id']).loc[pd.MultiIndex.from_frame(jobs[['survey_wave','person_id']])].reset_index()
    pd.testing.assert_series_equal(jobs.household_id, base.household_id, check_names=False)
    enriched = jobs.copy()
    enriched['total_occupations_past_7_days'] = base.total_occupations_past_7_days
    enriched['index_exceeds_reported_job_count'] = jobs.q13b_ocid.gt(base.total_occupations_past_7_days).astype('boolean')
    has_first = jobs.q13b_ocid.eq(1).groupby([jobs.survey_wave,jobs.person_id]).transform('any')
    enriched['index_2_without_index_1'] = (jobs.q13b_ocid.eq(2) & ~has_first).astype('boolean')
    enriched['job_index_interpretation'] = pd.Series('unverified_primary_secondary_meaning', index=jobs.index, dtype='string')
    require(int(enriched.index_exceeds_reported_job_count.sum()) == 65 and int(enriched.index_2_without_index_1.sum()) == 21, 'Exception scope changed')
    dictionaries = {}
    with zipfile.ZipFile(root / SUP_ARCHIVE) as z:
        for leaf in ['dbo_c_typeemployer.dta','dbo_c_occu.dta']:
            member = 'CSES 2007/HH data/CSES 2007/code/' + leaf
            payload = z.read(member)
            df = pd.read_stata(io.BytesIO(payload), convert_categoricals=False)
            dictionaries[leaf] = {'member': member, 'sha256': digest(payload), 'rows': len(df),
                'english_labels': {str(int(c)): t for c, t in zip(df.employercode, df.descr_eng, strict=True)} if 'employercode' in df else {},
                'binding_status': 'companion_codebook_not_embedded_variable_assignment'}
    rule_query = sql.SQL('SELECT * FROM jsonb_to_recordset({}::jsonb) AS r(rule_id text,survey_wave text,canonical_field text,source_variable_id bigint,source_variable text,source_code text,source_label text,affected_cells integer,release_id text,review_sha256 text)').format(sql.Literal(json.dumps(rules, sort_keys=True))).as_string()
    plan = {'release_id': VERSION, 'implementation_sha256': digest((root / SELF).read_bytes()), 'review_sha256': REVIEW_SHA,
        'rules': rules, 'queries': {VIEW: view_query(before.columns, rules), JOBS: jobs_query(), RULE: rule_query},
        'rows': len(after), 'columns': list(after), 'source_job_rows': len(jobs), 'job_people': jobs.person_id.nunique(),
        'labelled_missing_cells': 774, 'retained_unlabelled_cells': 12, 'job_count_conflict_rows': 65, 'index2_without_index1': 21,
        'job_values_sha256': canonical_sha256(json.loads(jobs.to_json(orient='records'))),
        'job_source_sha256': digest(source.read_bytes()),
        'supplemental_dictionaries': dictionaries, 'new_objects': OBJECTS,
        'wide_2007_recovery_performed': False, 'existing_physical_data_changed': False, 'existing_interfaces_replaced': False}
    return plan, after, jobs, enriched


def plan_files(root):
    plan, after, jobs, enriched = local_plan(root)
    write_once(root / DIRECTORY / 'plan.json', plan)
    for name, frame in [('final_EC_CSES.parquet',after),('jobs_2007_source.parquet',jobs),('jobs_2007.parquet',enriched)]:
        payload = io.BytesIO()
        frame.to_parquet(payload, index=False)
        path = root / DIRECTORY / name
        if path.exists():
            require(path.read_bytes() == payload.getvalue(), 'Versioned Parquet changed')
        else:
            path.write_bytes(payload.getvalue())
    return plan, after, jobs, enriched


def state(conn, targets=True):
    predicate = 'AND' if targets else 'AND NOT'
    cols = conn.execute(f"""SELECT n.nspname,c.relname,c.relkind,c.oid::bigint,c.relowner::bigint,c.relacl::text,c.reloptions,
      obj_description(c.oid,'pg_class') AS comment,a.attnum,a.attname,a.attnotnull,format_type(a.atttypid,a.atttypmod) AS type,
      col_description(c.oid,a.attnum) AS column_comment,CASE WHEN c.relkind='v' THEN pg_get_viewdef(c.oid,true) END AS definition
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
      WHERE (n.nspname IN ('cses_meta','cses_alignment','cses_data','cses_analysis') OR
        (n.nspname='public' AND c.relname IN (SELECT table_name FROM cses_meta.cses_storage_table)))
      AND c.relkind IN ('r','v','m') {predicate} (n.nspname='cses_analysis' AND c.relname=ANY(%s)) ORDER BY 1,2,a.attnum""", (OBJECTS,)).fetchall()
    constraints = conn.execute(f"""SELECT n.nspname,r.relname,c.conname,c.contype,pg_get_constraintdef(c.oid,true) AS definition
      FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid JOIN pg_namespace n ON n.oid=r.relnamespace
      WHERE n.nspname IN ('cses_meta','cses_alignment','cses_data','cses_analysis')
      {predicate} (n.nspname='cses_analysis' AND r.relname=ANY(%s)) ORDER BY 1,2,3""", (OBJECTS,)).fetchall()
    indexes = conn.execute(f"""SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes
      WHERE schemaname IN ('cses_meta','cses_alignment','cses_data','cses_analysis')
      {predicate} (schemaname='cses_analysis' AND tablename=ANY(%s)) ORDER BY 1,2,3""", (OBJECTS,)).fetchall()
    return {'columns': cols, 'constraints': constraints, 'indexes': indexes}


def protected(conn):
    rows = conn.execute("""SELECT n.nspname AS schema_name,c.relname AS table_name,c.oid::bigint,c.relowner::bigint,c.relacl::text
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('cses_meta','cses_alignment','cses_data','cses_analysis') AND c.relkind='r'
      AND NOT (n.nspname='cses_analysis' AND c.relname=%s) ORDER BY 1,2""", (TABLE,)).fetchall()
    require(len(rows) == 36, 'Exactly 36 prior physical tables must be protected')
    for row in rows:
        row.update(conn.execute(sql.SQL("""SELECT count(*) AS rows,encode(sha256(convert_to(coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') AS sha256
          FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS h FROM {} t) hashes""").format(
              sql.Identifier(row['schema_name'],row['table_name']))).fetchone())
    return {'physical_relations': rows, 'structure_sha256': canonical_sha256(state(conn, False))}


def absent(conn):
    require(not conn.execute("SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='cses_analysis' AND c.relname=ANY(%s)", (OBJECTS,)).fetchone(), 'New objects already exist; never overwrite or retry uncertain commits blindly')
    require(not conn.execute("SELECT 1 FROM pg_event_trigger WHERE evtenabled<>'D'").fetchone(), 'Active DDL event trigger')


def checks(conn, plan, after, jobs, enriched, published):
    def compare(query, expected, order):
        live = pd.DataFrame(conn.execute(sql.SQL('SELECT * FROM ({}) v ORDER BY {}').format(sql.SQL(query), sql.SQL(',').join(map(sql.Identifier,order)))).fetchall()).astype(expected.dtypes.to_dict())
        if 'source_archive' in live:
            live.source_archive = normalize_legacy_source_paths(live.source_archive)
        pd.testing.assert_frame_equal(live, expected.sort_values(order).reset_index(drop=True), check_exact=True)
    compare(f'SELECT * FROM cses_analysis.{VIEW}' if published else plan['queries'][VIEW], after, ['survey_wave','person_id'])
    if published:
        compare(f'SELECT * FROM cses_analysis.{TABLE}', jobs, ['survey_wave','person_id','q13b_ocid'])
        query = f'SELECT * FROM cses_analysis.{JOBS}'
    else:
        definitions = sql.SQL(',').join(sql.SQL('{} {}').format(sql.Identifier(c),sql.SQL(t)) for c,t in zip(JOB_COLUMNS,JOB_TYPES,strict=True))
        cte = sql.SQL('WITH source_jobs AS (SELECT * FROM jsonb_to_recordset({}::jsonb) AS j({})) ').format(
            sql.Literal(jobs.to_json(orient='records')), definitions).as_string()
        query = cte + jobs_query(sql.Identifier('source_jobs'))
    compare(query, enriched, ['survey_wave','person_id','q13b_ocid'])
    query = f'SELECT * FROM cses_analysis.{RULE}' if published else plan['queries'][RULE]
    require(conn.execute(sql.SQL('SELECT * FROM ({}) r ORDER BY rule_id').format(sql.SQL(query))).fetchall() == plan['rules'], 'Rule view mismatch')
    if published:
        conn.execute('SET LOCAL ROLE mda_readonly')
        try:
            counts = {v: conn.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(sql.Identifier('cses_analysis',v))).fetchone()['n'] for v in OBJECTS}
        finally:
            conn.execute('RESET ROLE')
        require(counts == {TABLE:11949,JOBS:11949,VIEW:332903,RULE:14}, 'Read-only role counts differ')
    return {'rows':332903,'columns':86,'all_projected_cells_match':True,'source_job_rows':11949,'job_view_columns':17,
        'labelled_missing_cells':int(after[FLAGS].fillna(False).sum().sum()),'job_count_conflicts':65,'index2_without_index1':21,
        'wide_2007_recovery_performed':False,'original_interfaces_preserved':True}


def prepare(root, backup_dir):
    require(not (root / RELEASE / 'execution.json').exists(), 'Execution already prepared')
    plan, after, jobs, enriched = plan_files(root)
    with connect_database({'dbname':'mda'}) as conn:
        read_only(conn)
        absent(conn)
        result = checks(conn,plan,after,jobs,enriched,False)
        baseline = protected(conn)
        require(conn.execute("SELECT has_schema_privilege('mda_readonly','cses_analysis','USAGE') AS ok").fetchone()['ok'], 'Reader schema access missing')
    print('Read-only preflight matched 86 columns and all 11949 source job rows', flush=True)
    require(backup_dir.is_dir(), 'Existing explicit backup directory required')
    fd, name = tempfile.mkstemp(prefix='mda_cses_classification_',suffix='.dump',dir=backup_dir)
    os.close(fd)
    os.chmod(name,0o600)
    subprocess.run(['pg_dump','-d','mda','--format=custom','--schema-only','--schema=cses_analysis',f'--file={name}'],check=True,timeout=55)
    subprocess.run(['pg_restore','--file=/dev/null',name],check=True,timeout=55)
    paths = [SELF,REVIEW,GRAPH, DIRECTORY+'/plan.json',DIRECTORY+'/final_EC_CSES.parquet',DIRECTORY+'/jobs_2007_source.parquet',DIRECTORY+'/jobs_2007.parquet',
        'rsc/cses_db/review_cses_employment_classification.py','rsc/cses_db/review_cses_employment_hours_status.py',
        'rsc/cses_db/review_cses_education.py','rsc/cses_db/plan_cses_age_topcode.py','rsc/cses_db/publish_cses_age_topcode.py',
        'rsc/cses_db/cses_employment.py','rsc/cses_db/cses_hh_hl_common.py','rsc/cses_db/inventory_cses_archives.py',
        'rsc/cses_db/organize_cses_questionnaires.py','rsc/cses_db/cses_baseline_metadata.py','rsc/cses_db/cses_lineage_graph.py']
    manifest = {'release_id':VERSION,'approval':'User: 好的，修正. Bounded additive interpretation and full 2007 job-index source recovery; no inferred main/secondary mapping.',
        'file_sha256':{p:digest((root/p).read_bytes()) for p in paths},'protected_before':baseline,'preflight':result,
        'backup':{'path':name,'sha256':digest(Path(name).read_bytes()),'scope':'cses_analysis schema only; no respondent data','full_decompression_verified':True},
        'git_base_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'git_dvc_archived':False}
    write_once(root/RELEASE/'execution.json',manifest)
    print('execution_sha256='+digest((root/RELEASE/'execution.json').read_bytes()),flush=True)


def execution(root):
    payload = (root/RELEASE/'execution.json').read_bytes()
    manifest = json.loads(payload)
    require(manifest['release_id'] == VERSION,'Wrong release')
    for path,sha in manifest['file_sha256'].items():
        require(digest((root/path).read_bytes()) == sha,f'Execution input changed: {path}')
    plan,after,jobs,enriched = local_plan(root)
    require(plan == json.loads((root/DIRECTORY/'plan.json').read_text()),'Plan changed')
    return manifest,digest(payload),plan,after,jobs,enriched


def apply(root, confirmation, rollback_test):
    manifest,sha,plan,after,jobs,enriched = execution(root)
    require(confirmation == sha,'Matching execution hash required')
    require(digest(Path(manifest['backup']['path']).read_bytes()) == manifest['backup']['sha256'],'Backup changed')
    require(not (root/RELEASE/'import.json').exists(),'Already published; validate instead')
    rehearsal = {'execution_sha256':sha,'four_objects_rolled_back':True,'protected_state_unchanged':True}
    if not rollback_test:
        require(json.loads((root/RELEASE/'rollback_test.json').read_text()) == rehearsal,'Rollback rehearsal required')
    with connect_database({'dbname':'mda'}) as conn:
        conn.execute("SET LOCAL statement_timeout='55s'")
        conn.execute("SET LOCAL lock_timeout='15s'")
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(VERSION,))
        absent(conn)
        for r in manifest['protected_before']['physical_relations']:
            conn.execute(sql.SQL('LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE').format(sql.Identifier(r['schema_name'],r['table_name'])))
        require(protected(conn) == manifest['protected_before'],'Protected state changed')
        definitions = [sql.SQL('{} {} {}').format(sql.Identifier(c),sql.SQL(t),sql.SQL('' if c=='q13bc07' else 'NOT NULL')) for c,t in zip(JOB_COLUMNS,JOB_TYPES,strict=True)]
        definitions += [sql.SQL("CHECK (survey_wave='2007'), CHECK(q13b_ocid IN (1,2)), CHECK(q13bc07 BETWEEN 1 AND 10), PRIMARY KEY(survey_wave,person_id,q13b_ocid), UNIQUE(source_row_id)")]
        conn.execute(sql.SQL('CREATE TABLE {} ({})').format(sql.Identifier('cses_analysis',TABLE),sql.SQL(',').join(definitions)))
        with conn.cursor().copy(sql.SQL('COPY {} ({}) FROM STDIN').format(sql.Identifier('cses_analysis',TABLE),sql.SQL(',').join(map(sql.Identifier,JOB_COLUMNS)))) as writer:
            for row in jobs.itertuples(index=False,name=None):
                writer.write_row(tuple(None if pd.isna(v) else int(v) if t=='smallint' else str(v) for v,t in zip(row,JOB_TYPES,strict=True)))
        for view in VIEWS:
            conn.execute(sql.SQL('CREATE VIEW {} WITH (security_barrier=true) AS {}').format(sql.Identifier('cses_analysis',view),sql.SQL(plan['queries'][view])))
        for name in OBJECTS:
            comment = f'{VERSION}; execution {sha}; review {REVIEW_SHA}; original codes and interfaces unchanged; 774 explicit missing interpretations; intact 11949-row 2007 source; job indices not certified main/secondary.'
            conn.execute(sql.SQL('COMMENT ON {} {} IS {}').format(sql.SQL('TABLE' if name==TABLE else 'VIEW'),sql.Identifier('cses_analysis',name),sql.Literal(comment)))
            conn.execute(sql.SQL('GRANT SELECT ON {} TO mda_readonly').format(sql.Identifier('cses_analysis',name)))
        result = checks(conn,plan,after,jobs,enriched,True)
        require(protected(conn) == manifest['protected_before'],'Historical state changed during publication')
        objects = state(conn)
        if rollback_test:
            conn.rollback()
        else:
            conn.commit()
    if rollback_test:
        with connect_database({'dbname':'mda'}) as conn:
            read_only(conn)
            absent(conn)
            require(protected(conn) == manifest['protected_before'],'Rollback failed to preserve state')
        write_once(root/RELEASE/'rollback_test.json',rehearsal)
        print('Rollback rehearsal passed',flush=True)
    else:
        write_once(root/RELEASE/'import.json',{'execution_sha256':sha,'object_state':objects,'checks':result,
            'database_mutated':True,'existing_physical_data_mutated':False,'new_source_job_rows':11949})
        print('Published four additive objects; no historical objects replaced',flush=True)


def validate(root):
    manifest,sha,plan,after,jobs,enriched = execution(root)
    imported = json.loads((root/RELEASE/'import.json').read_text())
    require(imported['execution_sha256'] == sha,'Wrong import')
    with connect_database({'dbname':'mda'}) as conn:
        read_only(conn)
        require(state(conn) == imported['object_state'],'Object definitions changed')
        require(protected(conn) == manifest['protected_before'],'Historical state changed')
        result = checks(conn,plan,after,jobs,enriched,True)
        require(result == imported['checks'],'Independent results differ')
    write_once(root/RELEASE/'validation.json',{'execution_sha256':sha,'validation_passed':True,'checks':result,'transaction_read_only':True,'database_mutated':False})
    print('Independent validation passed',flush=True)


def graph_extension(prior, sha, plan, dependencies, entries):
    builder = GraphBuilder()
    for node in prior['nodes']:
        builder.add_node(node['id'],node['type'],**node['properties'])
    for edge in prior['edges']:
        builder.add_edge(edge['type'],edge['source'],edge['target'],**edge['properties'])
    nodes = {}
    for name in OBJECTS:
        kind = 'analysis_source_table' if name==TABLE else 'analysis_view'
        nodes[name] = _node_id(kind,'cses_analysis',name)
        builder.add_node(nodes[name],kind,schema='cses_analysis',name=name,interface_release=VERSION,execution_sha256=sha)
        builder.add_edge('schema_exposes_'+kind,_node_id('schema','cses_analysis'),nodes[name])
    for dep in dependencies:
        name = dep['source_relation']
        origin = nodes[name] if name in nodes else _node_id('analysis_view','cses_analysis',name)
        builder.add_edge('relation_feeds_analysis_view',origin,nodes[dep['view_name']])
    builder.add_edge('documented_rule_corrects_view',nodes[RULE],nodes[VIEW],rule_count=14)
    source = _node_id('source_artifact',SUP_ARCHIVE,SUP_MEMBER)
    builder.add_node(source,'source_artifact',archive_relative_path=SUP_ARCHIVE,member_path=SUP_MEMBER,
        source_sha256=plan['job_source_sha256'],
        registered_dataset=False,source_grain='person/job-index',row_count=11949)
    builder.add_edge('source_artifact_feeds_analysis_source',source,nodes[TABLE],review_sha256=REVIEW_SHA)
    for rule in plan['rules']:
        entry = next(e for e in entries if e['source_variable_id']==rule['source_variable_id'])
        datasets = [n for n in prior['nodes'] if n['type']=='dataset' and n['properties']['member_path']==entry['member_path']
            and n['properties']['nested_member_path']==entry['nested_member_path']
            and Path(n['properties']['archive_relative_path']).name==Path(entry['archive_relative_path']).name]
        require(len(datasets)==1,'Unique rule source dataset required')
        origin = _node_id('source_variable',datasets[0]['id'],entry['variable_name'])
        builder.add_edge('source_variable_supports_interpretation',origin,nodes[RULE],rule_id=rule['rule_id'],review_sha256=REVIEW_SHA)
    graph = copy.deepcopy(prior)
    graph['nodes'],graph['edges'] = builder.finish()
    graph['source']['classification_extension'] = {'execution_sha256':sha,'previous_graph_sha256':PINS[GRAPH],'verified_dependencies':dependencies}
    graph['summary'].update(node_count=len(graph['nodes']),edge_count=len(graph['edges']),
        node_type_counts=dict(sorted(Counter(n['type'] for n in graph['nodes']).items())),
        edge_type_counts=dict(sorted(Counter(e['type'] for e in graph['edges']).items())))
    return graph


def export(root, output):
    manifest,sha,plan,after,jobs,enriched = execution(root)
    valid = json.loads((root/RELEASE/'validation.json').read_text())
    require(valid['validation_passed'] and valid['execution_sha256']==sha,'Independent validation required')
    with connect_database({'dbname':'mda'}) as conn:
        read_only(conn)
        require(state(conn)==json.loads((root/RELEASE/'import.json').read_text())['object_state'],'Published state changed')
        require(protected(conn)==manifest['protected_before'],'Historical state changed')
        checks(conn,plan,after,jobs,enriched,True)
        deps = conn.execute("""SELECT DISTINCT v.relname AS view_name,n.nspname AS source_schema,c.relname AS source_relation
          FROM pg_class v JOIN pg_namespace vn ON vn.oid=v.relnamespace JOIN pg_rewrite r ON r.ev_class=v.oid
          JOIN pg_depend d ON d.objid=r.oid AND d.classid='pg_rewrite'::regclass JOIN pg_class c ON c.oid=d.refobjid AND d.refclassid='pg_class'::regclass
          JOIN pg_namespace n ON n.oid=c.relnamespace WHERE vn.nspname='cses_analysis' AND v.relname=ANY(%s) AND c.oid<>v.oid ORDER BY 1,2,3""", (VIEWS,)).fetchall()
    expected = [{'view_name':v,'source_schema':'cses_analysis','source_relation':s} for v,s in sorted([(VIEW,'cses_ec_aligned_v1'),(JOBS,'cses_ec_aligned_v1'),(JOBS,TABLE)])]
    require(deps==expected,'Unexpected SQL dependencies')
    graph = graph_extension(json.loads((root/GRAPH).read_text()),sha,plan,deps,registry(root))
    write_once(output/'cses_lineage_graph_v14.json',graph)
    write_once(output/'cses_classification_correction_topology_v1.json',{'execution_sha256':sha,'dependencies':deps,'summary':graph['summary']})
    print(f"Graph v14: {len(graph['nodes'])} nodes / {len(graph['edges'])} edges",flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['plan','prepare','apply','validate','export'])
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--backup-dir',type=Path)
    parser.add_argument('--execution-sha256')
    parser.add_argument('--rollback-test',action='store_true')
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    if args.mode=='plan':
        plan_files(args.root)
    elif args.mode=='prepare':
        require(args.backup_dir is not None,'Explicit backup directory required')
        prepare(args.root,args.backup_dir)
    elif args.mode=='apply':
        apply(args.root,args.execution_sha256,args.rollback_test)
    elif args.mode=='validate':
        validate(args.root)
    else:
        export(args.root,args.output or args.root/'data/lineage')


if __name__=='__main__':
    main()
