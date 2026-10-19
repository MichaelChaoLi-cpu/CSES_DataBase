#!/usr/bin/env python3
"""Backed-up additive geography release; never updates legacy survey tables."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path

import pandas as pd
import psycopg
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from retest_cses_2004_geography import FIELDS, SHA, attach_cover

ROOT = Path(__file__).resolve().parents[2]
VERSION = "cses-geography-interface-v1"
DIR = ROOT / "data/releases" / VERSION
BACKUP = ROOT / "data/backups/cses_geo_v1/cses_before_geography.dump"
TABLE = "cses_geography_2004_source_v1"
HH = "cses_household_geography_v1"
HL = "cses_person_geography_v1"
COVERAGE = "cses_geography_coverage_v1"
SCHEMAS = ["cses_data", "cses_analysis", "cses_meta", "cses_alignment"]
MEMBER = "CSES 2004/Stata 2004/2004hh_s99_singlequestions.dta"


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def connect(readonly=True):
    return psycopg.connect(dbname="mda", connect_timeout=5, row_factory=dict_row,
                          options=f"-c default_transaction_read_only={'on' if readonly else 'off'} -c statement_timeout=55000 -c lock_timeout=5000")


def source_rows():
    archive = ROOT / "data/raw/CSES 2004.zip"
    if file_sha(archive) != SHA:
        raise ValueError("Archive fingerprint mismatch")
    with zipfile.ZipFile(archive) as z:
        cover = pd.read_stata(io.BytesIO(z.read(MEMBER)), convert_categoricals=False)
        roster = pd.read_stata(io.BytesIO(z.read("CSES 2004/Stata 2004/2004hh_s01a_hhmembers.dta")), convert_categoricals=False)
    linked = attach_cover(roster, cover)
    if len(linked) != 74719:
        raise ValueError("Unexpected source roster size")
    complete = cover[FIELDS].notna().all(axis=1)
    result = []
    for i, r in cover.loc[complete].iterrows():
        values = [int(r[c]) for c in FIELDS]
        if any(r[c] != v or not 1 <= v <= 99 for c, v in zip(FIELDS, values, strict=True)):
            raise ValueError("Invalid local administrative component")
        result.append(["2004", str(int(r.hhid)).zfill(6), str(int(r.q40_psu)).zfill(4),
                       *[str(v).zfill(2) for v in values], int(i) + 1, SHA, MEMBER])
    if len(result) != 14984:
        raise ValueError("Unexpected complete household count")
    return sorted(result, key=lambda r: r[1])


def definitions():
    # Source columns keep the legacy format; qualified components are distinct.
    components = []
    for name in ["province", "district", "commune", "village"]:
        components.append(f"CASE WHEN h.survey_wave='2004' THEN s.{name}_component ELSE lpad(h.{name}_code::integer::text,2,'0') END AS {name}_component")
    hh = f"""WITH components AS (
      SELECT h.survey_wave,h.survey_year,h.household_id,h.psu,
      h.province_code AS province_code_legacy,h.district_code AS district_code_legacy,
      h.commune_code AS commune_code_legacy,h.village_code AS village_code_legacy,
      {','.join(components)},
      CASE WHEN h.survey_wave='2004' AND s.household_id IS NOT NULL THEN 'recovered_q40_cover'
           WHEN h.survey_wave='2004' THEN 'missing_q40_source' ELSE 'legacy_household_source' END AS geography_source_status,
      coalesce(s.source_member,h.source_submodule) AS geography_source_member,
      s.source_row_number AS recovery_source_row_number,s.source_archive_sha256 AS recovery_source_sha256
      FROM cses_data."final_HH_CSES" h LEFT JOIN cses_data.{TABLE} s
      ON h.survey_wave=s.survey_wave AND h.household_id=s.household_id),
      keys AS (SELECT *,province_component AS admin1_code,
      province_component||district_component AS admin2_code,
      province_component||district_component||commune_component AS admin3_code,
      province_component||district_component||commune_component||village_component AS admin4_code FROM components)
      SELECT k.*,k.admin4_code IS NOT NULL AS complete_source_geography,
      a2.admin2_code IS NOT NULL AS district_polygon_code_matched,
      a3.admin3_code IS NOT NULL AS commune_polygon_code_matched,
      a2.admin2_name AS district_reference_name,a3.admin3_name AS commune_reference_name,
      a2.boundary_date AS district_boundary_date,a2.valid_on AS district_reference_valid_on,
      a3.boundary_date AS commune_boundary_date,a3.valid_on AS commune_reference_valid_on,
      CASE WHEN k.admin4_code IS NULL THEN 'missing_source_codes' WHEN a3.admin3_code IS NOT NULL THEN 'commune_code_match'
           WHEN a2.admin2_code IS NOT NULL THEN 'district_code_match' ELSE 'no_county_or_commune_code_match' END AS boundary_match_status,
      'not_evaluated_in_this_interface'::text AS village_directory_status,
      'not_verified_no_village_geometry_reference'::text AS village_geometry_status,
      false AS historical_identity_verified,'{VERSION}'::text AS geography_release
      FROM keys k LEFT JOIN public.dim_admin2_cambodia a2 ON k.admin2_code=a2.admin2_code
        AND a2.geometry_geojson->>'type' IN ('Polygon','MultiPolygon')
      LEFT JOIN public.dim_admin3_cambodia a3 ON k.admin3_code=a3.admin3_code
        AND a3.geometry_geojson->>'type' IN ('Polygon','MultiPolygon')"""
    fields = ["province_component", "district_component", "commune_component", "village_component",
              "admin1_code", "admin2_code", "admin3_code", "admin4_code", "complete_source_geography",
              "geography_source_status", "geography_source_member", "recovery_source_row_number", "recovery_source_sha256",
              "district_polygon_code_matched", "commune_polygon_code_matched", "district_reference_name", "commune_reference_name",
              "district_boundary_date", "district_reference_valid_on", "commune_boundary_date", "commune_reference_valid_on",
              "boundary_match_status", "village_directory_status", "village_geometry_status", "historical_identity_verified", "geography_release"]
    hl = f"""SELECT p.survey_wave,p.survey_year,p.person_id,p.household_id,p.psu,
      p.province_code AS province_code_legacy,p.district_code AS district_code_legacy,
      p.commune_code AS commune_code_legacy,p.village_code AS village_code_legacy,
      g.household_id IS NOT NULL AS household_link_matched,
      CASE WHEN g.household_id IS NULL THEN 'household_not_found'
           WHEN p.psu IS DISTINCT FROM g.psu OR p.province_code IS DISTINCT FROM g.province_code_legacy THEN 'source_context_conflict'
           ELSE 'matched' END AS household_link_status,
      {','.join('g.'+f for f in fields)}
      FROM cses_data."final_HL_CSES" p LEFT JOIN cses_analysis.{HH} g
      ON p.survey_wave=g.survey_wave AND p.household_id=g.household_id"""
    coverage = f"""SELECT survey_wave,count(*) AS roster_records,
      count(*) FILTER(WHERE household_link_matched) AS household_linked_records,
      count(*) FILTER(WHERE complete_source_geography) AS complete_geography_records,
      count(*) FILTER(WHERE district_polygon_code_matched) AS district_polygon_matched_records,
      count(*) FILTER(WHERE commune_polygon_code_matched) AS commune_polygon_matched_records,
      count(*) FILTER(WHERE household_link_status='source_context_conflict') AS context_conflict_records,
      count(DISTINCT admin4_code) AS distinct_source_village_codes,
      'village_geometry_not_verified'::text AS village_geometry_status
      FROM cses_analysis.{HL} GROUP BY survey_wave"""
    return {HH: hh, HL: hl, COVERAGE: coverage}


def fingerprint(conn, schema, table):
    return conn.execute(sql.SQL("SELECT count(*) AS rows,md5(coalesce(string_agg(h,'' ORDER BY h),'')) AS rows_md5 FROM (SELECT md5(to_jsonb(t)::text) h FROM {} t) q")
                        .format(sql.Identifier(schema, table))).fetchone()


def preflight(conn):
    if conn.execute("SELECT 1 FROM pg_event_trigger WHERE evtenabled<>'D'").fetchone():
        raise ValueError("Unexpected active event trigger")
    for schema, names in [("cses_data", [TABLE]), ("cses_analysis", [HH, HL, COVERAGE])]:
        if conn.execute("SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=ANY(%s)", (schema, names)).fetchone():
            raise ValueError("Target exists; validate rather than overwrite")
    for t, key in [("final_HH_CSES", "household_id"), ("final_HL_CSES", "person_id")]:
        bad = conn.execute(sql.SQL("SELECT 1 FROM cses_data.{} GROUP BY survey_wave,{} HAVING count(*)>1 OR survey_wave IS NULL OR {} IS NULL LIMIT 1")
                           .format(sql.Identifier(t), sql.Identifier(key), sql.Identifier(key))).fetchone()
        if bad:
            raise ValueError("Base natural key failure")
    return {t: fingerprint(conn, "cses_data", t) for t in ["final_HH_CSES", "final_HL_CSES", "dim_geo_CSES"]}


def protected(conn):
    relations = conn.execute("SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=ANY(%s) AND c.relkind='r' AND n.nspname IN ('cses_data','cses_analysis') ORDER BY 1,2", (SCHEMAS,)).fetchall()
    return {r['nspname']+'.'+r['relname']: fingerprint(conn, r['nspname'], r['relname']) for r in relations if r['relname'] != TABLE}


def validate(conn, rows):
    actual = conn.execute(f"SELECT * FROM cses_data.{TABLE} ORDER BY household_id").fetchall()
    if [list(r.values()) for r in actual] != rows:
        raise ValueError("Published source rows mismatch")
    for name, base, key in [(HH, "final_HH_CSES", "household_id"), (HL, "final_HL_CSES", "person_id")]:
        n = conn.execute(sql.SQL("SELECT count(*) n,count(DISTINCT (survey_wave,{})) u FROM cses_analysis.{}").format(sql.Identifier(key), sql.Identifier(name))).fetchone()
        old = conn.execute(sql.SQL("SELECT count(*) n FROM cses_data.{}").format(sql.Identifier(base))).fetchone()
        if n['n'] != old['n'] or n['u'] != n['n']:
            raise ValueError("Interface multiplied or lost records")
    coverage = conn.execute(f"SELECT * FROM cses_analysis.{COVERAGE} ORDER BY survey_wave").fetchall()
    for r in coverage:
        if r['context_conflict_records'] or r['household_linked_records'] != r['roster_records'] or r['complete_geography_records'] != r['roster_records']:
            raise ValueError("Incomplete or conflicting person geography")
    corrected = next(r for r in coverage if r['survey_wave'] == '2004')
    if (corrected['roster_records'], corrected['district_polygon_matched_records'], corrected['commune_polygon_matched_records'], corrected['distinct_source_village_codes']) != (74719,70247,65544,867):
        raise ValueError("2004 publication differs from local feasibility test")
    return coverage


def prepare():
    rows = source_rows()
    with connect() as conn:
        before = preflight(conn)
        hh = conn.execute('SELECT household_id,psu,province_code FROM cses_data."final_HH_CSES" WHERE survey_wave=\'2004\' ORDER BY household_id').fetchall()
        if [[r['household_id'],r['psu'],r['province_code']] for r in hh] != [[r[1],r[2],r[3]] for r in rows]:
            raise ValueError("Recovered household keys/context differ from database")
        datasets = conn.execute("SELECT dataset_id FROM cses_meta.cses_dataset WHERE member_path=%s", (MEMBER,)).fetchall()
        if len(datasets) != 1:
            raise ValueError("Source dataset registration not unique")
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    if BACKUP.exists():
        raise ValueError("Backup exists; do not overwrite")
    subprocess.run(["pg_dump", "-d", "mda", "-Fc", *[f"--schema={s}" for s in SCHEMAS], f"--file={BACKUP}"], check=True, timeout=300)
    subprocess.run(["pg_restore", "--file=/dev/null", str(BACKUP)], check=True, timeout=300)
    plan = {"version": VERSION, "source_sha256": SHA, "source_rows_sha256": digest(rows),
            "script_sha256": file_sha(Path(__file__)), "definitions": definitions(), "before": before,
            "source_dataset_id": datasets[0]['dataset_id'],
            "backup": {"path": str(BACKUP), "sha256": file_sha(BACKUP), "schemas": SCHEMAS, "full_decompression_verified": True},
            "scope": "Add one source table and three views; append release/load/storage/source-edge metadata; preserve legacy physical tables and public interfaces."}
    put(DIR / "execution.json", encoded(plan))
    return {"backup": plan['backup'], "source_rows": len(rows), "targets": [TABLE, *definitions()]}


def publish():
    plan = json.loads((DIR / "execution.json").read_text())
    rows = source_rows()
    if plan['script_sha256'] != file_sha(Path(__file__)) or plan['source_rows_sha256'] != digest(rows) or plan['backup']['sha256'] != file_sha(BACKUP):
        raise ValueError("Prepared code, source or backup changed")
    with connect(False) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (VERSION,))
        conn.execute('LOCK TABLE cses_data."final_HH_CSES",cses_data."final_HL_CSES",cses_data."dim_geo_CSES" IN SHARE MODE')
        if preflight(conn) != plan['before']:
            raise ValueError("Base data changed after preparation")
        before = protected(conn)
        conn.execute(f"""CREATE TABLE cses_data.{TABLE} (
          survey_wave text NOT NULL CHECK(survey_wave='2004'),household_id text NOT NULL,psu text NOT NULL,
          province_component text NOT NULL CHECK(province_component ~ '^[0-9]{{2}}$'),
          district_component text NOT NULL CHECK(district_component ~ '^[0-9]{{2}}$'),
          commune_component text NOT NULL CHECK(commune_component ~ '^[0-9]{{2}}$'),
          village_component text NOT NULL CHECK(village_component ~ '^[0-9]{{2}}$'),
          source_row_number integer NOT NULL CHECK(source_row_number>0),source_archive_sha256 text NOT NULL,
          source_member text NOT NULL,PRIMARY KEY(survey_wave,household_id),UNIQUE(source_archive_sha256,source_member,source_row_number))""")
        with conn.cursor().copy(f"COPY cses_data.{TABLE} FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)
        conn.execute(f"CREATE INDEX ON cses_data.{TABLE}(survey_wave,psu)")
        for name, query in definitions().items():
            conn.execute(sql.SQL("CREATE VIEW {} AS ").format(sql.Identifier("cses_analysis", name)) + sql.SQL(query))
            conn.execute(sql.SQL("COMMENT ON VIEW {} IS {}").format(sql.Identifier("cses_analysis", name),
                         sql.Literal("Additive CSES geography v1. Preserves roster/household records. Code matches are not historical identity; village geometry unverified. Boundary references retain their own dates.")))
        coverage = validate(conn, rows)
        if protected(conn) != before:
            raise ValueError("Protected legacy data changed")
        rid = conn.execute("INSERT INTO cses_meta.cses_alignment_release(mapping_version,status,description,specification_sha256,approved_at) VALUES(%s,'approved',%s,%s,now()) RETURNING alignment_release_id",
                           (VERSION, plan['scope'], digest(plan))).fetchone()['alignment_release_id']
        sid = conn.execute("INSERT INTO cses_meta.cses_storage_table(table_schema,table_name,object_family,module_code,analytical_grain,natural_key,row_count,column_count,relation_fingerprint) VALUES('cses_data',%s,'geography','GEO','household_wave',%s,%s,10,%s) RETURNING storage_table_id",
                           (TABLE, ['survey_wave','household_id'],len(rows),digest(rows))).fetchone()['storage_table_id']
        conn.execute("INSERT INTO cses_meta.cses_dataset_output(dataset_id,storage_table_id,alignment_release_id,contribution_role,output_row_count) VALUES(%s,%s,%s,'source',%s)",
                     (plan['source_dataset_id'],sid,rid,len(rows)))
        conn.execute("INSERT INTO cses_meta.cses_load_run(alignment_release_id,run_scope,source_manifest_sha256,status,row_counts,validation_summary,finished_at) VALUES(%s,%s,%s,'loaded',%s,%s,now())",
                     (rid,VERSION,digest(plan),Jsonb({TABLE:len(rows)}),Jsonb({'coverage':coverage,'legacy_physical_data_unchanged':True,'backup_sha256':plan['backup']['sha256']})))
        conn.execute(sql.SQL("COMMENT ON TABLE {} IS {}").format(sql.Identifier('cses_data',TABLE),
                     sql.Literal("2004 q40 cover geography; exact household join, no PSU imputation. Original archive/member/row preserved. Release "+VERSION)))
        conn.execute(f"ANALYZE cses_data.{TABLE}")
    result = {'release_id':rid,'coverage':coverage,'protected_fingerprints':before,'execution_sha256':file_sha(DIR/'execution.json'),
              'database_modified':True,'legacy_tables_modified':False}
    put(DIR / "published.json", encoded(result))
    return result


def postflight():
    result = json.loads((DIR / "published.json").read_text())
    with connect() as conn:
        coverage = validate(conn,source_rows())
        if protected(conn) != result['protected_fingerprints']:
            raise ValueError("Legacy data changed since publication")
    put(DIR / "validated.json", encoded({'coverage':coverage,'legacy_data_unchanged':True,'published_sha256':file_sha(DIR/'published.json')}))
    return {'validated':True,'waves':len(coverage),'coverage':coverage}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','publish','validate'])
    action = parser.parse_args().action
    print(json.dumps({'prepare':prepare,'publish':publish,'validate':postflight}[action](),indent=2))
