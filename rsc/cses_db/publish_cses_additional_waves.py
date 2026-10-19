#!/usr/bin/env python3
"""Additive, backed-up publication of five reviewed CSES wave candidates.

Never updates legacy tables, shared boundaries, or immutable candidate evidence.
Native source values and qualified analytical fields remain distinct.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path

import pandas as pd
from build_cses_additional_waves import combine_tables, encoded, source_keys, verify
from cache_cses_questionnaires import file_sha, put
from psycopg import sql
from psycopg.types.json import Jsonb
from publish_cses_geography_interface import SCHEMAS, connect, fingerprint
from test_cses_geography_local import code_components

ROOT = Path(__file__).resolve().parents[2]
VERSION = "cses-additional-waves-qualified-v1"
OUT = ROOT / "data/releases" / VERSION
PLAN = OUT / "execution-v2.json"
REHEARSAL = OUT / "rehearsal-v2.json"
BASE = ROOT / "data/processing/cses"
CANDIDATE = BASE / "additional_waves_v1"
BACKUP = ROOT / "data/backups/cses_additional_v1/before_additional_waves.dump"
MODULES = ("HH", "HL", "ED", "EC", "HO", "HEALTH", "SURVEY_DATE")
SUPPLEMENTS = {
    ("2023", "EC"): "additional_wave_review_v1/EC_2023_unique_candidate.parquet",
    ("2023", "HEALTH"): "additional_wave_review_v1/HEALTH_2023_qualified_candidate.parquet",
    ("1996", "HL"): "additional_age_review_v1/HL_1996_age_qualified.parquet",
    ("1999", "HL"): "additional_age_review_v1/HL_1999_age_qualified.parquet",
    ("1999", "ED"): "education_1999_route_review_v1/ED_1999_route_review.parquet",
}
REVIEW_SCRIPTS = {
    "additional_wave_review_v1": ("reviewer_sha256", "review_cses_2023_conflicts.py"),
    "additional_age_review_v1": ("builder_sha256", "qualify_cses_legacy_age.py"),
    "education_1999_route_review_v1": ("builder_sha256", "audit_cses_1999_school_routes.py"),
}


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def name(value):
    result = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not result or len(result.encode()) > 63:
        raise ValueError(f"Invalid PostgreSQL identifier: {value}")
    return result


def catalog_labels(entries):
    """Match the existing source-variable catalog's code-to-label object contract."""
    result = {}
    for entry in entries:
        value = entry['source_value']
        key = str(int(value)) if isinstance(value,(int,float)) and float(value).is_integer() else str(value)
        if key in result:
            raise ValueError('Duplicate value-label code')
        result[key] = entry['label']
    return result or None


def table(module):
    return "cses_additional_" + module.lower() + "_v1"


def verified_evidence():
    verify(ROOT)
    paths = [CANDIDATE / "manifest.json"]
    original = json.loads(paths[0].read_text())
    paths += [CANDIDATE / p for p in original["artifacts"] if p.endswith(".json")]
    for directory, (hash_field, script) in REVIEW_SCRIPTS.items():
        manifest_path = BASE / directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        if file_sha(ROOT / "rsc/cses_db" / script) != manifest[hash_field]:
            raise ValueError("Review code changed: " + script)
        if "candidate_manifest_sha256" in manifest:
            if manifest["candidate_manifest_sha256"] != file_sha(CANDIDATE / "manifest.json"):
                raise ValueError("Review candidate changed")
        for relative, expected in manifest["artifacts"].items():
            path = BASE / directory / relative
            if file_sha(path) != expected:
                raise ValueError("Review artifact changed: " + str(path))
            if relative.endswith(".json"):
                paths.append(path)
        paths.append(manifest_path)
    word = ROOT / 'data/processed/cses_questionnaires/additional_waves_v1/legacy_word_text_v1'
    word_manifest = json.loads((word / 'manifest.json').read_text())
    age_manifest = json.loads((BASE / 'additional_age_review_v1/manifest.json').read_text())
    route_manifest = json.loads((BASE / 'education_1999_route_review_v1/manifest.json').read_text())
    if file_sha(word / 'manifest.json') != age_manifest['word_text_manifest_sha256']:
        raise ValueError('Age questionnaire evidence changed')
    for relative, expected in word_manifest['artifacts'].items():
        if file_sha(word / relative) != expected:
            raise ValueError('Legacy questionnaire text changed')
    if (file_sha(word / '1999/QuestENG_Form3Page.json') != route_manifest['questionnaire_text_sha256']
            or file_sha(CANDIDATE / 'tables/1999/ED.parquet') != route_manifest['source_table_sha256']):
        raise ValueError('School-route source changed')
    paths.append(word / 'manifest.json')
    # Publish full provenance documents, including inventories and special-missing ledgers.
    return pd.DataFrame([{"artifact_path": str(p.relative_to(ROOT)), "sha256": file_sha(p),
                          "payload": json.loads(p.read_text())} for p in sorted(set(paths))])


def project(frame):
    """Preserve each wave's native scalar types before any cross-wave concatenation."""
    raw = [c for c in frame if c.startswith("source__")]
    values = [{c[8:]: clean(v) for c, v in zip(raw, row, strict=True)}
              for row in frame[raw].itertuples(index=False, name=None)]
    result = frame.drop(columns=raw).rename(columns={c: name(c) for c in frame if c not in raw})
    if result.columns.duplicated().any():
        raise ValueError("Column name collision")
    result["source_values"] = values
    return result


def geography(spec, household, roster):
    frames = []
    for wave, cfg in spec["waves"].items():
        archive = ROOT / cfg["archive"]
        if file_sha(archive) != cfg["sha256"]:
            raise ValueError("Archive changed: " + wave)
        member = cfg["modules"]["HL"]["member"]
        columns = (["pro", "dis", "com", "vil"] if wave in {"1997", "1999"}
                   else ["province_id", "district_id", "commune_id", "village_id"] if wave == "2025"
                   else ["province", "district", "commune", "village"])
        with zipfile.ZipFile(archive) as z:
            raw = pd.read_stata(io.BytesIO(z.read(member)), convert_categoricals=False,
                                columns=list(dict.fromkeys(cfg["household_key"] + [cfg["person_key"]] + columns)))
        keys = source_keys(raw, cfg["household_key"] + [cfg["person_key"]], wave)
        if set(keys) != set(roster.loc[roster.survey_wave.eq(wave), "record_key"]):
            raise ValueError("Geography roster key mismatch")
        geo = code_components(raw, columns).rename(columns={f"admin{i}": f"admin{i}_code" for i in range(1, 5)})
        geo["household_key"] = source_keys(raw, cfg["household_key"], wave)
        geo["survey_wave"] = wave
        geo["source_row_number"] = range(1, len(raw) + 1)
        if geo.isna().any().any():
            raise ValueError("Missing native geography")
        for col in [f"admin{i}_code" for i in range(1, 5)]:
            if geo.groupby("household_key")[col].nunique().ne(1).any():
                raise ValueError("Household geography conflict")
        source_rows = geo.groupby("household_key").source_row_number.agg(list)
        geo = geo.drop_duplicates("household_key").drop(columns="source_row_number")
        geo["source_row_numbers"] = geo.household_key.map(source_rows)
        geo["source_member"] = member
        geo["source_archive"] = cfg["archive"]
        geo["source_archive_sha256"] = cfg["sha256"]
        frames.append(geo)
    result = pd.concat(frames, ignore_index=True)
    if set(result.household_key) != set(household.household_key):
        raise ValueError("Geography does not cover every household")
    return result


def build_frames():
    evidence = verified_evidence()
    spec = json.loads((ROOT / "rsc/specs/cses_additional_waves_v1.json").read_text())
    frames = {}
    inputs = {}
    coercions = {}
    for module in MODULES:
        parts = []
        for wave, cfg in spec["waves"].items():
            if module not in cfg["modules"]:
                continue
            path = (BASE / SUPPLEMENTS[wave, module] if (wave, module) in SUPPLEMENTS
                    else CANDIDATE / "tables" / wave / (module + ".parquet"))
            inputs[str(path.relative_to(ROOT))] = file_sha(path)
            parts.append(project(pd.read_parquet(path)))
        frame, converted = combine_tables(parts)
        # Scope qualifications are deliberately not propagated to unreviewed waves.
        for field in ["age_qualification_status", "route_review_status", "first_provider_evidence_status"]:
            if field in frame:
                frame[field] = frame[field].fillna("not_reviewed_in_this_release")
        if frame.record_key.isna().any() or frame.record_key.duplicated().any() or frame.missing_key.any():
            raise ValueError("Invalid published record key: " + module)
        if not frame.hh_link_matched.all() or ("hl_link_matched" in frame and not frame.hl_link_matched.all()):
            raise ValueError("Unmatched candidate key: " + module)
        frames["cses_data." + table(module)] = frame
        coercions[module] = converted
    hh = frames["cses_data." + table("HH")]
    hl = frames["cses_data." + table("HL")]
    for module in MODULES:
        frame = frames["cses_data." + table(module)]
        if not set(frame.household_key) <= set(hh.household_key):
            raise ValueError("Household foreign key failure")
        if module in {"ED", "EC", "HEALTH"}:
            links = frame.merge(hl[["record_key", "household_key"]], on="record_key", validate="one_to_one", suffixes=("", "_roster"))
            if len(links) != len(frame) or not links.household_key.eq(links.household_key_roster).all():
                raise ValueError("Person/household correspondence failure")
    frames["cses_data." + table("GEO")] = geography(spec, hh, hl)
    # Preserve all 51,917 pre-fold EC rows in addition to the 51,914 qualified rows.
    raw_path = CANDIDATE / "tables/2023/EC.parquet"
    inputs[str(raw_path.relative_to(ROOT))] = file_sha(raw_path)
    frames["cses_data.cses_additional_ec_2023_source_v1"] = project(pd.read_parquet(raw_path))
    frames["cses_meta.cses_additional_evidence_v1"] = evidence
    alignment = json.loads((CANDIDATE / "field_alignment.json").read_text())
    frames["cses_alignment.cses_additional_field_mapping_v1"] = pd.DataFrame([
        {"survey_wave": r["wave"], "module_code": r["module"], "target_field": name(r["target"]),
         "source_member": r["source_member"], "source_variable": r["source_variable"],
         "cross_wave_equivalence": r["cross_wave_equivalence"], "evidence": r} for r in alignment])
    dependencies = ['build_cses_additional_waves.py','cache_cses_questionnaires.py',
                    'publish_cses_geography_interface.py','test_cses_geography_local.py']
    return frames, {"inputs": inputs, "text_coercions": coercions, "evidence_sha256": digest(evidence.to_dict("records")),
                    "dependency_sha256": {p:file_sha(ROOT/'rsc/cses_db'/p) for p in dependencies},
                    "geography_test_sha256": file_sha(BASE/'geography_feasibility_v1/summary.json')}


def primary_key(relation):
    if relation.endswith("evidence_v1"):
        return ["artifact_path"]
    if relation.endswith("field_mapping_v1"):
        return ["survey_wave", "module_code", "target_field"]
    if relation.endswith("ec_2023_source_v1"):
        return ["survey_wave", "source_row_number"]
    if relation.endswith("geo_v1"):
        return ["survey_wave", "household_key"]
    return ["survey_wave", "record_key"]


def prepared_rows(frame, key):
    kinds = {}
    for column in frame:
        values = frame[column].dropna()
        types = {type(clean(v)) for v in values}
        if types <= {bool} and types:
            kind = "boolean"
        elif types <= {int} and types:
            kind = "bigint"
        elif types <= {float, int} and types:
            kind = "double precision"
        elif types <= {dict, list} and types:
            kind = "jsonb"
        elif types <= {str}:
            kind = "text"
        else:
            raise ValueError(f"Unsupported types for {column}: {types}")
        kinds[column] = kind
    rows = []
    for row in frame.sort_values(key).itertuples(index=False, name=None):
        result = [clean(v) for v in row]
        for i, kind in enumerate(kinds.values()):
            if result[i] is not None and kind == "double precision":
                result[i] = float(result[i])
        rows.append(result)
    return kinds, rows


def row_digest(rows):
    h = hashlib.sha256()
    for row in rows:
        h.update(json.dumps(list(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
        h.update(b"\n")
    return h.hexdigest()


def ordered_keys(columns, key):
    # Python's Unicode ordering and PostgreSQL's locale-sensitive ordering differ
    # for punctuation in artifact paths. C collation is deterministic UTF-8 order.
    return sql.SQL(',').join(sql.SQL('{} COLLATE "C"').format(sql.Identifier(c))
                             if columns[c] == 'text' else sql.Identifier(c) for c in key)


def definitions():
    new = f"""SELECT p.survey_wave,p.record_key,p.household_key,'additional_native_json'::text AS key_namespace,
      g.admin1_code,g.admin2_code,g.admin3_code,g.admin4_code,
      a2.admin2_code IS NOT NULL AS district_polygon_code_matched,
      a3.admin3_code IS NOT NULL AS commune_polygon_code_matched,
      a2.boundary_date AS district_boundary_date,a2.valid_on AS district_reference_valid_on,
      a3.boundary_date AS commune_boundary_date,a3.valid_on AS commune_reference_valid_on,
      false AS historical_identity_verified,'not_verified_no_village_geometry_reference'::text AS village_geometry_status,
      '{VERSION}'::text AS geography_release
      FROM cses_data.{table('HL')} p JOIN cses_data.{table('GEO')} g USING(survey_wave,household_key)
      LEFT JOIN public.dim_admin2_cambodia a2 ON g.admin2_code=a2.admin2_code AND a2.geometry_geojson->>'type' IN ('Polygon','MultiPolygon')
      LEFT JOIN public.dim_admin3_cambodia a3 ON g.admin3_code=a3.admin3_code AND a3.geometry_geojson->>'type' IN ('Polygon','MultiPolygon')"""
    union = """SELECT survey_wave,person_id AS record_key,household_id AS household_key,'legacy_id'::text AS key_namespace,
      admin1_code,admin2_code,admin3_code,admin4_code,district_polygon_code_matched,commune_polygon_code_matched,
      district_boundary_date,district_reference_valid_on,commune_boundary_date,commune_reference_valid_on,
      historical_identity_verified,village_geometry_status,geography_release
      FROM cses_analysis.cses_person_geography_v1 UNION ALL SELECT * FROM cses_analysis.cses_additional_person_geography_v1"""
    coverage = """SELECT survey_wave,count(*) AS roster_records,count(DISTINCT household_key) AS households,
      count(*) FILTER(WHERE admin4_code IS NOT NULL) AS complete_geography_records,
      count(*) FILTER(WHERE district_polygon_code_matched) AS district_polygon_matched_records,
      count(*) FILTER(WHERE commune_polygon_code_matched) AS commune_polygon_matched_records,
      count(DISTINCT admin4_code) AS distinct_source_village_codes
      FROM cses_analysis.cses_person_geography_v2 GROUP BY survey_wave"""
    return {"cses_additional_person_geography_v1": new, "cses_person_geography_v2": union,
            "cses_geography_coverage_v2": coverage}


def protected(conn):
    records = conn.execute("SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('cses_data','cses_analysis') AND c.relkind='r' ORDER BY 1,2").fetchall()
    return {r['nspname'] + '.' + r['relname']: fingerprint(conn, r['nspname'], r['relname']) for r in records}


def check_protected(conn, before):
    for relation, expected in before.items():
        if fingerprint(conn, *relation.split('.')) != expected:
            raise ValueError("Existing data changed: " + relation)


def preflight(conn, frames):
    if conn.execute("SELECT 1 FROM pg_event_trigger WHERE evtenabled<>'D'").fetchone():
        raise ValueError("Unexpected event trigger")
    for relation in [*frames, *['cses_analysis.' + v for v in definitions()]]:
        if conn.execute("SELECT to_regclass(%s) AS relation", (relation,)).fetchone()['relation']:
            raise ValueError("Target already exists: " + relation)
    if conn.execute("SELECT 1 FROM cses_meta.cses_survey WHERE survey_wave=ANY(%s)", (['1996','1997','1999','2023','2025'],)).fetchone():
        raise ValueError("Wave metadata already registered")


def write_frames(conn, frames):
    summaries = {}
    for relation, frame in frames.items():
        key = primary_key(relation)
        kinds, rows = prepared_rows(frame, key)
        identifier = sql.Identifier(*relation.split('.'))
        columns = sql.SQL(',').join(sql.SQL('{} {}').format(sql.Identifier(c), sql.SQL(t)) for c, t in kinds.items())
        conn.execute(sql.SQL('CREATE TABLE {} ({}, PRIMARY KEY ({}))').format(identifier, columns, sql.SQL(',').join(map(sql.Identifier, key))))
        with conn.cursor().copy(sql.SQL('COPY {} FROM STDIN').format(identifier)) as copy:
            for row in rows:
                copy.write_row([Jsonb(v) if v is not None and k == 'jsonb' else v for v, k in zip(row, kinds.values(), strict=True)])
        conn.execute(sql.SQL('COMMENT ON TABLE {} IS {}').format(identifier, sql.Literal(
            VERSION + ': reviewed native-field projection, not blanket cross-wave equivalence. See cses_alignment.cses_additional_field_mapping_v1 and cses_meta.cses_additional_evidence_v1.')))
        for column in kinds:
            note = ('Native selected source fields; original scalar types retained per wave.' if column == 'source_values'
                    else 'Wave-specific native code; do not interpret as a harmonized classification.' if column.endswith('source_code')
                    else 'Original candidate flag retained; qualification columns may supersede its interpretation.' if column in {'duplicate_key','unique_source_record_eligible','alignment_status','age_interpretation'}
                    else 'Not reviewed outside explicitly qualified waves.' if 'qualified' in column
                    else 'No universal cross-wave equivalence asserted; consult field mapping evidence.')
            conn.execute(sql.SQL('COMMENT ON COLUMN {}.{} IS {}').format(identifier,sql.Identifier(column),sql.Literal(note)))
        summaries[relation] = {'rows':len(rows),'columns':kinds,'row_sha256':row_digest(rows)}
        print('Loaded ' + relation + ': ' + str(len(rows)), flush=True)
    # Only new relations receive strict foreign keys: all candidates passed exact link checks.
    for module in MODULES:
        rel = sql.Identifier('cses_data',table(module))
        conn.execute(sql.SQL('CREATE INDEX ON {} (survey_wave,household_key)').format(rel))
        if module == 'HH':
            conn.execute(sql.SQL('ALTER TABLE {} ADD UNIQUE(survey_wave,household_key), ADD CHECK(record_key=household_key)').format(rel))
    conn.execute(sql.SQL('ALTER TABLE {} ADD UNIQUE(survey_wave,record_key,household_key)').format(sql.Identifier('cses_data',table('HL'))))
    for module in (*MODULES[1:], 'GEO'):
        conn.execute(sql.SQL('ALTER TABLE {} ADD FOREIGN KEY(survey_wave,household_key) REFERENCES {}(survey_wave,household_key)').format(sql.Identifier('cses_data',table(module)),sql.Identifier('cses_data',table('HH'))))
    for module in ['ED','EC','HEALTH']:
        conn.execute(sql.SQL('ALTER TABLE {} ADD FOREIGN KEY(survey_wave,record_key,household_key) REFERENCES {}(survey_wave,record_key,household_key)').format(sql.Identifier('cses_data',table(module)),sql.Identifier('cses_data',table('HL'))))
    for level in range(1,5):
        conn.execute(sql.SQL('CREATE INDEX ON {} ({})').format(sql.Identifier('cses_data',table('GEO')),sql.Identifier(f'admin{level}_code')))
    for query_name, query in definitions().items():
        conn.execute(sql.SQL('CREATE VIEW {} AS ').format(sql.Identifier('cses_analysis',query_name)) + sql.SQL(query))
        conn.execute(sql.SQL('COMMENT ON VIEW {} IS {}').format(sql.Identifier('cses_analysis',query_name),sql.Literal('Additive geography interface: village codes are not verified historical geographic identities; no village geometry claimed. Keys are wave-specific, not longitudinal person identifiers.')))
    return summaries


def validate(conn, summaries):
    for relation, expected in summaries.items():
        query = sql.SQL('SELECT * FROM {} ORDER BY {}').format(sql.Identifier(*relation.split('.')),ordered_keys(expected['columns'],primary_key(relation)))
        with conn.cursor(name='check_additional') as cursor:
            cursor.execute(query)
            actual = row_digest(list(r.values()) for r in cursor)
        count = conn.execute(sql.SQL('SELECT count(*) n FROM {}').format(sql.Identifier(*relation.split('.')))).fetchone()['n']
        if count != expected['rows'] or actual != expected['row_sha256']:
            raise ValueError('Database/source content mismatch: ' + relation)
    coverage = conn.execute('SELECT * FROM cses_analysis.cses_geography_coverage_v2 ORDER BY survey_wave').fetchall()
    if len(coverage) != 15 or sum(r['roster_records'] for r in coverage) != 571699:
        raise ValueError('Geography union row loss or multiplication')
    original = json.loads((BASE/'geography_feasibility_v1/summary.json').read_text())
    for r in coverage:
        if r['survey_wave'] not in {'1996','1997','1999','2023','2025'}:
            continue
        expected = next(x for x in original['waves'] if x['wave'] == r['survey_wave'])
        for target, source in [('roster_records','roster_records'),('complete_geography_records','complete_village_code_records'),('district_polygon_matched_records','admin2_polygon_code_matched_records'),('commune_polygon_matched_records','admin3_polygon_code_matched_records')]:
            if r[target] != expected[source]:
                raise ValueError('Geography differs from independent test')
    return coverage


def register(conn, summaries, plan, coverage):
    spec = json.loads((ROOT/'rsc/specs/cses_additional_waves_v1.json').read_text())
    rid = conn.execute("INSERT INTO cses_meta.cses_alignment_release(mapping_version,status,description,specification_sha256,approved_at) VALUES(%s,'approved',%s,%s,now()) RETURNING alignment_release_id",
                       (VERSION,'Five additional waves; qualified native projections, not universally harmonized; additive storage and geography.',digest(plan))).fetchone()['alignment_release_id']
    archives = {}
    surveys = {}
    for wave, cfg in spec['waves'].items():
        surveys[wave] = conn.execute("INSERT INTO cses_meta.cses_survey(dataset_name,survey_wave,nominal_survey_year,release_status) VALUES(%s,%s,%s,'reviewed') RETURNING survey_id",('CSES '+wave,wave,int(wave))).fetchone()['survey_id']
        path = ROOT/cfg['archive']
        with zipfile.ZipFile(path) as z:
            members = len(z.infolist())
        archives[wave] = conn.execute("INSERT INTO cses_meta.cses_source_archive(survey_id,relative_path,sha256,size_bytes,archive_member_count,inventory_status) VALUES(%s,%s,%s,%s,%s,'validated') RETURNING source_archive_id",(surveys[wave],cfg['archive'],cfg['sha256'],path.stat().st_size,members)).fetchone()['source_archive_id']
    datasets = {}
    for d in json.loads((CANDIDATE/'datasets.json').read_text()):
        datasets[d['wave'],d['member']] = conn.execute("INSERT INTO cses_meta.cses_dataset(source_archive_id,survey_id,member_path,row_count,column_count,read_status) VALUES(%s,%s,%s,%s,%s,'readable') RETURNING dataset_id",(archives[d['wave']],surveys[d['wave']],d['member'],d['rows'],d['columns'])).fetchone()['dataset_id']
    with conn.cursor().copy('COPY cses_alignment.cses_source_variable(dataset_id,variable_name,variable_position,storage_type,variable_label,value_labels,alignment_status) FROM STDIN') as copy:
        for v in json.loads((CANDIDATE/'variables.json').read_text()):
            labels = catalog_labels(v['value_labels'])
            copy.write_row([datasets[v['wave'],v['member']],v['name'],v['position'],'stata_'+str(v['storage_type']),v['label'],Jsonb(labels) if labels is not None else None,'documented'])
    for relation, summary in summaries.items():
        schema, rel = relation.split('.')
        module = next((m for m in (*MODULES,'GEO') if table(m)==rel),None)
        family = 'geography' if module == 'GEO' else 'final' if module else 'source_dictionary'
        sid = conn.execute("INSERT INTO cses_meta.cses_storage_table(table_schema,table_name,object_family,module_code,analytical_grain,natural_key,row_count,column_count,relation_fingerprint) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING storage_table_id",(schema,rel,family,module,'person_wave' if module in {'HL','ED','EC','HEALTH'} else 'household_wave' if module else 'source_evidence',primary_key(relation),summary['rows'],len(summary['columns']),summary['row_sha256'])).fetchone()['storage_table_id']
        if module or rel.endswith('ec_2023_source_v1'):
            for wave,cfg in spec['waves'].items():
                source_module = 'HL' if module=='GEO' else module or 'EC'
                if source_module not in cfg['modules'] or (module is None and wave!='2023'):
                    continue
                member = cfg['modules'][source_module]['member']
                n = conn.execute(sql.SQL('SELECT count(*) n FROM {} WHERE survey_wave=%s').format(sql.Identifier(schema,rel)),(wave,)).fetchone()['n']
                conn.execute("INSERT INTO cses_meta.cses_dataset_output(dataset_id,storage_table_id,alignment_release_id,contribution_role,output_row_count) VALUES(%s,%s,%s,'source',%s)",(datasets[wave,member],sid,rid,n))
                # HH roster counts are derived from the separate person roster.
                if module == 'HH':
                    roster_member = cfg['modules']['HL']['member']
                    if roster_member != member:
                        conn.execute("INSERT INTO cses_meta.cses_dataset_output(dataset_id,storage_table_id,alignment_release_id,contribution_role,output_row_count) VALUES(%s,%s,%s,'source',%s)",(datasets[wave,roster_member],sid,rid,n))
                # The qualified 2023 provider fields also retain the alternate illness source.
                if module == 'HEALTH' and wave == '2023':
                    conn.execute("INSERT INTO cses_meta.cses_dataset_output(dataset_id,storage_table_id,alignment_release_id,contribution_role,output_row_count) VALUES(%s,%s,%s,'source',%s)",(datasets[wave,'S13A_PersonIllness.dta'],sid,rid,n))
    validate_catalog(conn)
    conn.execute("INSERT INTO cses_meta.cses_load_run(alignment_release_id,run_scope,source_manifest_sha256,status,row_counts,validation_summary,finished_at) VALUES(%s,%s,%s,'loaded',%s,%s,now())",(rid,VERSION,digest(plan),Jsonb({r:s['rows'] for r,s in summaries.items()}),Jsonb({'legacy_unchanged':True,'coverage':coverage,'backup_sha256':plan['backup_sha256']})))
    return rid


def validate_catalog(conn):
    counts = conn.execute("""SELECT count(*) AS variables,
      count(*) FILTER(WHERE sv.value_labels IS NOT NULL AND jsonb_typeof(sv.value_labels)<>'object') AS invalid_labels
      FROM cses_alignment.cses_source_variable sv JOIN cses_meta.cses_dataset d USING(dataset_id)
      JOIN cses_meta.cses_survey s USING(survey_id) WHERE s.survey_wave=ANY(%s)""",(['1996','1997','1999','2023','2025'],)).fetchone()
    if counts != {'variables':5427,'invalid_labels':0}:
        raise ValueError('Source-variable catalog mismatch')
    count = conn.execute("SELECT count(*) n FROM cses_meta.cses_dataset d JOIN cses_meta.cses_survey s USING(survey_id) WHERE s.survey_wave=ANY(%s)",(['1996','1997','1999','2023','2025'],)).fetchone()['n']
    if count != 173:
        raise ValueError('Source-dataset catalog mismatch')


def prepare():
    frames, inputs = build_frames()
    with connect() as conn:
        preflight(conn,frames)
        before = protected(conn)
        reference = {f'public.dim_admin{level}_cambodia':fingerprint(conn,'public',f'dim_admin{level}_cambodia') for level in [2,3]}
    BACKUP.parent.mkdir(parents=True,exist_ok=True)
    if BACKUP.exists():
        original = json.loads((OUT/'execution.json').read_text())
        if file_sha(BACKUP) != original['backup_sha256'] or before != original['before']:
            raise ValueError('Existing backup or protected data changed')
    else:
        subprocess.run(['/opt/homebrew/bin/pg_dump','-d','mda','-Fc',*[f'--schema={s}' for s in SCHEMAS],f'--file={BACKUP}'],check=True,timeout=300)
    subprocess.run(['/opt/homebrew/bin/pg_restore','--file=/dev/null',str(BACKUP)],check=True,timeout=300)
    plan = {'version':VERSION,'inputs':inputs,'before':before,'reference':reference,'backup':str(BACKUP),'backup_sha256':file_sha(BACKUP),'full_backup_decompression_verified':True,'script_sha256':file_sha(Path(__file__)),'definitions':definitions()}
    put(PLAN,encoded(plan))
    return {'prepared':True,'tables':{r:len(f) for r,f in frames.items()},'backup':str(BACKUP)}


def publish(rehearse=False):
    plan = json.loads(PLAN.read_text())
    frames, inputs = build_frames()
    if inputs != plan['inputs'] or file_sha(Path(__file__)) != plan['script_sha256'] or file_sha(BACKUP) != plan['backup_sha256']:
        raise ValueError('Prepared source, code or backup changed')
    if not rehearse:
        rehearsal = json.loads(REHEARSAL.read_text())
        if rehearsal['execution_sha256'] != file_sha(PLAN):
            raise ValueError('Matching rollback rehearsal required')
    with connect(False) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(VERSION,))
        for relation in [*plan['before'],*plan['reference']]:
            conn.execute(sql.SQL('LOCK TABLE {} IN SHARE MODE').format(sql.Identifier(*relation.split('.'))))
        conn.execute('LOCK TABLE cses_meta.cses_survey,cses_meta.cses_source_archive,cses_meta.cses_dataset IN SHARE ROW EXCLUSIVE MODE')
        preflight(conn,frames)
        check_protected(conn,plan['before'])
        check_protected(conn,plan['reference'])
        summaries = write_frames(conn,frames)
        coverage = validate(conn,summaries)
        check_protected(conn,plan['before'])
        check_protected(conn,plan['reference'])
        rid = register(conn,summaries,plan,coverage)
        for relation in frames:
            conn.execute(sql.SQL('ANALYZE {}').format(sql.Identifier(*relation.split('.'))))
        if rehearse:
            conn.rollback()
    result = {'release_id':rid,'committed':not rehearse,'summaries':summaries,'coverage':coverage,'execution_sha256':file_sha(PLAN)}
    put(REHEARSAL if rehearse else OUT/'published.json',encoded(result))
    return {'committed':not rehearse,'release_id':rid,'coverage':coverage}


def postflight():
    plan = json.loads(PLAN.read_text())
    publication = json.loads((OUT/'published.json').read_text())
    with connect() as conn:
        coverage = validate(conn,publication['summaries'])
        check_protected(conn,plan['before'])
        check_protected(conn,plan['reference'])
        validate_catalog(conn)
        loaded = conn.execute("SELECT status FROM cses_meta.cses_load_run WHERE alignment_release_id=%s",(publication['release_id'],)).fetchall()
        if loaded != [{'status':'loaded'}]:
            raise ValueError('Load registry mismatch')
    result = {'validated':True,'coverage':coverage,'legacy_data_unchanged':True,'published_sha256':file_sha(OUT/'published.json')}
    put(OUT/'validated.json',encoded(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','rehearse','publish','validate','local-check'])
    action = parser.parse_args().action
    if action == 'local-check':
        frames, _ = build_frames()
        result = {r:{'rows':len(f),'types':prepared_rows(f,primary_key(r))[0]} for r,f in frames.items()}
    else:
        result = {'prepare':prepare,'rehearse':lambda:publish(True),'publish':publish,'validate':postflight}[action]()
    print(json.dumps(result,indent=2))
