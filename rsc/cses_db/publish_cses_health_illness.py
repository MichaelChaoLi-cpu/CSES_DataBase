#!/usr/bin/env python3
"""Add the reviewed HEALTH illness release without changing historical rows.

prepare -> apply --rollback-test -> apply -> validate. A matching execution
fingerprint gates writes. Source codes and version-qualified flags are immutable.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

import pandas as pd
from cses_baseline_metadata import canonical_sha256, connect_database
from cses_lineage_graph import GraphBuilder, _node_id, build_lineage_graph, read_lineage_snapshot
from organize_cses_questionnaires import digest, write_once
from plan_cses_health_illness import BASELINES, KEY_COLUMNS, canonical_keys, link_keys
from psycopg import sql
from psycopg.types.json import Jsonb
from publish_cses_age_topcode import read_only

VERSION = "cses-health-illness-qualified-v1"
RELEASE = f"data/releases/{VERSION}"
SELF = "rsc/cses_db/publish_cses_health_illness.py"
PRE = "data/processing/cses/health_illness_preflight_v1"
SCREEN = "data/processing/cses/health_recent_illness_v1"
TYPE = "data/processing/cses/health_illness_type_v1"
KHM = "data/processing/cses/health_illness_type_khmer_v2"
INTAKE = "data/processed/cses_health/v1"
GRAPH = "data/lineage/cses_lineage_graph_v14.json"
SOURCE = "cses_health_illness_source_v1"
REVIEW = "cses_health_illness_review_v1"
REGISTRY = "cses_health_illness_evidence_v1"
VIEW = "cses_health_illness_v1"
FIELDS = "cses_health_illness_native_fields_v1"
TABLES = [SOURCE, REVIEW, REGISTRY]
VIEWS = [VIEW, FIELDS]
OBJECTS = [("cses_data", SOURCE), ("cses_data", REVIEW), ("cses_alignment", REGISTRY),
           ("cses_analysis", VIEW), ("cses_analysis", FIELDS)]
JSON_COLUMNS = {"raw_record", "source_member_chain", "raw_type_answers", "source_type_variables"}
APPEND_KEYS = {
    "cses_meta.cses_dataset": "dataset_id",
    "cses_meta.cses_alignment_release": "alignment_release_id",
    "cses_meta.cses_storage_table": "storage_table_id",
    "cses_meta.cses_dataset_output": "dataset_id",
    "cses_meta.cses_load_run": "load_run_id",
    "cses_alignment.cses_source_variable": "source_variable_id",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(root, path):
    return json.loads((root / path).read_text())


def sha(root, path):
    return digest((root / path).read_bytes())


def verify_manifest(root, directory, name="manifest.json"):
    manifest = read(root, f"{directory}/{name}")
    for path, expected in manifest["artifacts"].items():
        require(sha(root, f"{directory}/{path}") == expected, f"Artifact changed: {directory}/{path}")
    for key in ("input_sha256", "implementation_sha256"):
        pins = manifest.get(key, {})
        if isinstance(pins, str):
            require(directory == PRE and sha(root, "rsc/cses_db/plan_cses_health_illness.py") == pins,
                    "Preflight implementation changed")
            continue
        for path, expected in pins.items():
            require(sha(root, path) == expected, f"Pinned input changed: {path}")
    return manifest


def descriptor(frame):
    result = []
    for name, dtype in frame.dtypes.items():
        kind = str(dtype).lower()
        if name in JSON_COLUMNS:
            dbtype = "jsonb"
        elif "bool" in kind:
            dbtype = "boolean"
        elif "float" in kind:
            dbtype = "double precision"
        elif "int" in kind:
            dbtype = "bigint" if name == "source_row_number" else "smallint"
        elif "string" in kind:
            dbtype = "text"
        else:
            raise ValueError(f"Unsupported dtype for {name}: {dtype}")
        result.append({"name": name, "type": dbtype, "nullable": bool(frame[name].isna().any())})
    return result


def local(root):
    pre = verify_manifest(root, PRE, "plan.json")
    for directory in (SCREEN, TYPE, KHM):
        verify_manifest(root, directory)
    require(sha(root, GRAPH) == "0ad1cbb8b5651fbabf13c479ee6cbe24e85d794b6e45f519f258940a80b053da", "Graph changed")
    source = pd.read_parquet(root / PRE / "illness_source.parquet")
    review = pd.read_parquet(root / KHM / "illness_type.parquet")
    require(source.shape == (358859, 14) and review.shape == (358859, 41), "Unexpected source/review shape")
    shared = [c for c in source if c in review]
    pd.testing.assert_frame_equal(source[shared], review[shared], check_exact=True, check_dtype=False)
    require(not source.duplicated(["source_id", "source_row_number"]).any(), "Duplicate source rows")
    require(not source.duplicated(KEY_COLUMNS["hl"]).any(), "Duplicate person-wave keys")
    require(int(review.strict_screening_eligible.sum()) == 134977, "Screening drift")
    require(int(review.within_wave_eligible_with_qualifications.sum()) == 11074, "Type eligibility drift")
    unresolved = review.survey_wave.eq("2021") & review.raw_type_code.between(22, 73).fillna(False)
    require(int(unresolved.sum()) == 1053 and review.loc[unresolved, "category"].isna().all(), "Unknowns interpreted")
    require(not review.loc[unresolved, "within_wave_eligible_with_qualifications"].any(), "Unknowns eligible")
    intake = read(root, f"{INTAKE}/manifest.json")
    sources = [s for s in intake["sources"] if s["topic"] == "illness_care"]
    require({s["source_id"] for s in sources} == set(source.source_id), "Wrong source set")
    variables = read(root, f"{PRE}/source_variables.json")
    require(len(variables) == 248, "Native catalog drift")
    screening = {r["survey_wave"]: r for r in read(root, f"{SCREEN}/wave_review.json")}
    types = {r["survey_wave"]: r for r in read(root, f"{TYPE}/wave_review.json")}
    evidence = []
    for s in sources:
        require(s["extended_missing_cells"] == 0, "Extended missing unsupported")
        for p in (s["parquet_path"], s["variables_path"]):
            require(sha(root, f"{INTAKE}/{p}") == intake["artifacts"][p], "Native cache changed")
        fields = [v for v in variables if v["source_id"] == s["source_id"]]
        require(len(fields) == s["source_columns"], "Incomplete native fields")
        evidence.append({"source_id": s["source_id"], "survey_wave": s["survey_wave"],
                         "source_sha256": s["source_sha256"], "fields": fields,
                         "screening_v1": screening[s["survey_wave"]], "illness_type_v1": types[s["survey_wave"]],
                         "khmer_v2": read(root, f"{KHM}/questionnaire_evidence.json") if s["survey_wave"] == "2021" else None,
                         "recovered_codes_v2": read(root, f"{KHM}/recovered_codes.json") if s["survey_wave"] == "2021" else [],
                         "qualification": "Two reviewed concepts, not full cross-wave equivalence; retain row-level flags."})
    return source, review, sources, evidence, pre


def absent(conn, sources):
    for schema, name in OBJECTS:
        require(conn.execute("SELECT to_regclass(%s) AS x", (f"{schema}.{name}",)).fetchone()["x"] is None,
                f"Target already exists: {schema}.{name}; never overwrite")
    require(not conn.execute("SELECT 1 FROM cses_meta.cses_alignment_release WHERE mapping_version=%s", (VERSION,)).fetchone(),
            "Release already registered")
    require(not conn.execute("SELECT 1 FROM pg_event_trigger WHERE evtenabled<>'D'").fetchone(), "Active DDL trigger")
    for s in sources:
        a = conn.execute("SELECT * FROM cses_meta.cses_source_archive WHERE relative_path=%s",
                         (s["archive_relative_path"],)).fetchone()
        require(a is not None, "Missing archive")
        require(not conn.execute("SELECT 1 FROM cses_meta.cses_dataset WHERE source_archive_id=%s AND member_path=%s "
                                 "AND nested_member_path=%s", (a["source_archive_id"], s["member_chain"][0],
                                                              "::".join(s["member_chain"][1:]))).fetchone(), "Source already registered")


def fingerprint(conn, schema, name, predicate="TRUE"):
    return conn.execute(sql.SQL("SELECT count(*) AS rows, encode(sha256(convert_to(coalesce(string_agg(h,'' "
        "ORDER BY h),''),'UTF8')),'hex') AS sha256 FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,"
        "'UTF8')),'hex') h FROM {} t WHERE {}) hashes").format(sql.Identifier(schema, name), sql.SQL(predicate))).fetchone()


def catalog(conn, names=None):
    rows = conn.execute("""SELECT n.nspname AS schema,c.relname AS name,c.oid::bigint,c.relkind,
      c.relowner::bigint,c.relacl::text,c.reloptions,obj_description(c.oid,'pg_class') AS comment,
      CASE WHEN c.relkind='v' THEN pg_get_viewdef(c.oid,true) END AS view_definition,
      a.attnum,a.attname,format_type(a.atttypid,a.atttypmod) AS type,a.attnotnull,
      col_description(c.oid,a.attnum) AS column_comment,
      (SELECT jsonb_agg(pg_get_constraintdef(x.oid) ORDER BY x.conname) FROM pg_constraint x WHERE x.conrelid=c.oid) AS constraints,
      (SELECT jsonb_agg(pg_get_indexdef(i.indexrelid) ORDER BY i.indexrelid) FROM pg_index i WHERE i.indrelid=c.oid) AS indexes
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
      WHERE n.nspname IN ('cses_data','cses_analysis','cses_meta','cses_alignment') AND c.relkind IN ('r','v','p','m')
      ORDER BY 1,2,a.attnum""").fetchall()
    return [r for r in rows if names is None or [r["schema"], r["name"]] in names]


def protected(conn, baseline=None):
    definitions = catalog(conn, None if baseline is None else baseline["names"])
    names = sorted({(r["schema"], r["name"]) for r in definitions if r["relkind"] == "r"})
    limits = {} if baseline is None else baseline["limits"]
    if baseline is None:
        for relation, key in APPEND_KEYS.items():
            limits[relation] = conn.execute(sql.SQL("SELECT coalesce(max({}),0) AS n FROM {}").format(
                sql.Identifier(key), sql.Identifier(*relation.split(".")))).fetchone()["n"]
    counts = {}
    for schema, name in names:
        relation = f"{schema}.{name}"
        where = f'"{APPEND_KEYS[relation]}" <= {int(limits[relation])}' if relation in limits else "TRUE"
        counts[relation] = fingerprint(conn, schema, name, where)
    return {"names": sorted([list(p) for p in {(r["schema"], r["name"]) for r in definitions}]),
            "definitions": definitions, "limits": limits, "rows": counts}


def spines(conn, root, source):
    frames = {}
    for kind, table in [("hh", "final_HH_CSES"), ("hl", "final_HL_CSES")]:
        rows = conn.execute(sql.SQL("SELECT {} FROM {}").format(sql.SQL(",").join(map(sql.Identifier, KEY_COLUMNS[kind])),
                                                                  sql.Identifier("cses_data", table))).fetchall()
        frames[kind] = canonical_keys(pd.DataFrame(rows), kind)
        pd.testing.assert_frame_equal(frames[kind], canonical_keys(pd.read_parquet(root / BASELINES[kind]), kind), check_exact=True)
    linked = link_keys(source[KEY_COLUMNS["hl"]], frames["hh"], frames["hl"])
    for col in ["hh_link_matched", "hl_link_status", "roster_household_id"]:
        pd.testing.assert_series_equal(linked[col], source[col], check_exact=True, check_dtype=False)


def load_frame(conn, name, frame, columns):
    with conn.cursor().copy(sql.SQL("COPY {} ({}) FROM STDIN").format(sql.Identifier("cses_data", name),
           sql.SQL(",").join(sql.Identifier(c["name"]) for c in columns))) as writer:
        for row in frame.itertuples(index=False, name=None):
            values = []
            for value, col in zip(row, columns, strict=True):
                if pd.isna(value):
                    value = None
                elif col["type"] == "jsonb":
                    value = Jsonb(json.loads(value))
                elif col["type"] in ("bigint", "smallint"):
                    value = int(value)
                elif col["type"] == "boolean":
                    value = bool(value)
                values.append(value)
            writer.write_row(values)


def compare(conn, schema, name, expected):
    # Wave-sized batches bound memory. Never print respondent values on mismatch.
    for wave in sorted(expected.survey_wave.unique()):
        want = expected[expected.survey_wave.eq(wave)].sort_values(["source_id", "source_row_number"]).reset_index(drop=True)
        rows = conn.execute(sql.SQL("SELECT {} FROM {} WHERE survey_wave=%s ORDER BY source_id,source_row_number").format(
            sql.SQL(",").join(map(sql.Identifier, expected.columns)), sql.Identifier(schema, name)), (wave,)).fetchall()
        got = pd.DataFrame(rows, columns=expected.columns)
        require(len(got) == len(want), f"Row count differs in {name}/{wave}")
        for col in expected:
            if col in JSON_COLUMNS:
                require(got[col].tolist() == want[col].map(json.loads).tolist(), f"JSON mismatch: {name}/{wave}/{col}")
            else:
                got[col] = got[col].astype(want[col].dtype)
                require(got[col].equals(want[col]), f"Cell mismatch: {name}/{wave}/{col}")
    require(conn.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(schema, name))).fetchone()["n"] == len(expected),
            "Unexpected extra wave")


def evidence_rows(conn, release_id, sources, evidence):
    result = []
    for s, e in zip(sources, evidence, strict=True):
        a = conn.execute("SELECT a.*,s.survey_wave FROM cses_meta.cses_source_archive a JOIN cses_meta.cses_survey s USING(survey_id) "
                         "WHERE relative_path=%s", (s["archive_relative_path"],)).fetchone()
        require(a["survey_wave"] == s["survey_wave"], "Archive wave mismatch")
        row = conn.execute("""INSERT INTO cses_meta.cses_dataset
          (source_archive_id,survey_id,member_path,nested_member_path,module_code,source_grain,row_count,column_count,read_status)
          VALUES (%s,%s,%s,%s,'HEALTH','person_wave',%s,%s,'readable') RETURNING dataset_id""",
          (a["source_archive_id"], a["survey_id"], s["member_chain"][0], "::".join(s["member_chain"][1:]),
           s["source_records"], s["source_columns"])).fetchone()
        dataset = row["dataset_id"]
        for f in e["fields"]:
            conn.execute("""INSERT INTO cses_alignment.cses_source_variable
              (dataset_id,variable_name,variable_position,storage_type,variable_label,value_labels,alignment_status)
              VALUES (%s,%s,%s,%s,%s,%s,'documented')""", (dataset, f["variable_name"], f["variable_position"],
              "stata_" + str(f["stata_storage_type"]), f["variable_label"],
              Jsonb({v["source_value"]: v["label"] for v in f["value_labels"]})))
        conn.execute(sql.SQL("INSERT INTO {} VALUES (%s,%s,%s,%s,%s,%s)").format(sql.Identifier("cses_alignment", REGISTRY)),
                     (s["source_id"], dataset, release_id, s["survey_wave"], s["source_sha256"], Jsonb(e)))
        result.append({"source_id": s["source_id"], "dataset_id": dataset, "rows": s["source_records"]})
    return result


def registry_ddl():
    return sql.SQL("""CREATE TABLE {} (source_id text PRIMARY KEY,
      dataset_id bigint NOT NULL UNIQUE REFERENCES cses_meta.cses_dataset,
      alignment_release_id bigint NOT NULL REFERENCES cses_meta.cses_alignment_release,
      survey_wave text NOT NULL UNIQUE, source_sha256 text NOT NULL CHECK(source_sha256 ~ '^[0-9a-f]{{64}}$'),
      evidence jsonb NOT NULL CHECK(jsonb_typeof(evidence)='object'))""").format(sql.Identifier("cses_alignment", REGISTRY))


def create(conn, root, source, review, sources, evidence, execution_sha):
    # The old design stays historical; its exact reviewed DDL is executed only here.
    conn.execute((root / PRE / "proposed_schema.sql").read_text())
    desc = descriptor(review)
    defs = [sql.SQL("{} {} {}").format(sql.Identifier(c["name"]), sql.SQL(c["type"]),
             sql.SQL("" if c["nullable"] else "NOT NULL")) for c in desc]
    defs.append(sql.SQL(f"PRIMARY KEY(source_id,source_row_number), UNIQUE(survey_wave,household_id,person_id), "
        f"FOREIGN KEY(source_id,source_row_number) REFERENCES cses_data.{SOURCE}(source_id,source_row_number), "
        "CHECK(recent_illness_injury_30d IN (0,1)), CHECK(native_screen_present IN (0,1)), "
        "CHECK(NOT strict_screening_eligible OR (recent_illness_injury_30d IS NOT NULL AND hl_link_status='matched')), "
        "CHECK(NOT within_wave_eligible_with_qualifications OR category IS NOT NULL), "
        "CHECK(NOT version_qualified_analysis_eligible OR (survey_wave='2021' AND raw_type_code IN (19,20,21)))"))
    conn.execute(sql.SQL("CREATE TABLE {} ({})").format(sql.Identifier("cses_data", REVIEW), sql.SQL(",").join(defs)))
    conn.execute(registry_ddl())
    load_frame(conn, SOURCE, source, read(root, "rsc/specs/cses_health_illness_table_v1.json")["columns"])
    load_frame(conn, REVIEW, review, desc)
    rid = conn.execute("""INSERT INTO cses_meta.cses_alignment_release
      (mapping_version,status,description,specification_sha256,approved_at) VALUES (%s,'approved',%s,%s,now())
      RETURNING alignment_release_id""", (VERSION,
      "User-authorized additive source and qualified review publication. Not all-wave equivalence; unknowns preserved.",
      execution_sha)).fetchone()["alignment_release_id"]
    datasets = evidence_rows(conn, rid, sources, evidence)
    for schema, name in OBJECTS[:3]:
        cols = catalog(conn, [[schema, name]])
        count = 10 if name == REGISTRY else 358859
        fingerprint_definition = canonical_sha256({"algorithm": "health-column-contract-v1", "columns":
            [{k: c[k] for k in ("attnum", "attname", "type", "attnotnull")} for c in cols], "row_count": count})
        sid = conn.execute("""INSERT INTO cses_meta.cses_storage_table
          (table_schema,table_name,object_family,module_code,analytical_grain,natural_key,row_count,column_count,relation_fingerprint)
          VALUES (%s,%s,%s,'HEALTH',%s,%s,%s,%s,%s) RETURNING storage_table_id""",
          (schema, name, "source_dictionary" if name == REGISTRY else "final",
           "source_dataset" if name == REGISTRY else "person_wave",
           ["source_id"] if name == REGISTRY else ["survey_wave", "household_id", "person_id"], count, len(cols),
           fingerprint_definition)).fetchone()["storage_table_id"]
        for d in datasets:
            conn.execute("INSERT INTO cses_meta.cses_dataset_output "
                         "(dataset_id,storage_table_id,alignment_release_id,contribution_role,output_row_count) VALUES (%s,%s,%s,'source',%s)",
                         (d["dataset_id"], sid, rid, count))
    conn.execute(sql.SQL("CREATE VIEW {} WITH (security_barrier=true) AS SELECT * FROM {}").format(
        sql.Identifier("cses_analysis", VIEW), sql.Identifier("cses_data", REVIEW)))
    conn.execute(sql.SQL("""CREATE VIEW {} WITH (security_barrier=true) AS
      SELECT r.source_id,r.survey_wave,r.dataset_id,v.source_variable_id,v.variable_name,v.variable_position,
        v.variable_label,v.value_labels,r.source_sha256,'cses_data'::text AS target_schema,
        {}::text AS target_table,'raw_record'::text AS target_column,ARRAY[v.variable_name]::text[] AS json_path,
        'native_storage_only_not_semantic_alignment'::text AS mapping_status
      FROM {} r JOIN cses_alignment.cses_source_variable v USING(dataset_id)""").format(
        sql.Identifier("cses_analysis", FIELDS), sql.Literal(SOURCE), sql.Identifier("cses_alignment", REGISTRY)))
    for schema, name in OBJECTS:
        kind = "VIEW" if name in VIEWS else "TABLE"
        conn.execute(sql.SQL("COMMENT ON {} {} IS {}").format(sql.SQL(kind), sql.Identifier(schema, name),
            sql.Literal(f"{VERSION}; execution {execution_sha}; raw codes intact; two reviewed concepts, not ten-wave equivalence. "
                        "2021 codes 19-21 Khmer-version qualified; 22-73 unresolved. Consult evidence and eligibility flags.")))
        conn.execute(sql.SQL("GRANT SELECT ON {} TO mda_readonly").format(sql.Identifier(schema, name)))
    # Per-column qualifications keep the analysis contract discoverable in SQL clients.
    comments = {"category": "Within-family category, NOT a common all-wave disease scale. Unknown codes remain NULL.",
        "within_wave_eligible_with_qualifications": "Use within wave and type_family only; includes Khmer-2021 qualification. Not pooled prevalence.",
        "strict_screening_eligible": "Conservative form-supported 30-day subset: 2009/2013/2016/2021; linkage/branch flags excluded.",
        "source_label_km_v2": "Exact Khmer form labels for 2021 codes 19-21; English gloss is a review translation.",
        "person_id": "Wave-local person identifier, not a longitudinal ID. Household reports may be proxy responses."}
    for name in (REVIEW, VIEW):
        for col, comment in comments.items():
            conn.execute(sql.SQL("COMMENT ON COLUMN {} IS {}").format(
                sql.Identifier("cses_data" if name == REVIEW else "cses_analysis", name, col), sql.Literal(comment)))
    result = checks(conn, root, source, review, evidence)
    conn.execute("""INSERT INTO cses_meta.cses_load_run
      (alignment_release_id,run_scope,source_manifest_sha256,code_git_revision,status,row_counts,validation_summary,finished_at)
      VALUES (%s,%s,%s,%s,'loaded',%s,%s,now())""", (rid, VERSION, sha(root, f"{INTAKE}/manifest.json"),
      subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
      Jsonb({SOURCE: 358859, REVIEW: 358859, REGISTRY: 10, "native_variables": 248}),
      Jsonb({"release_id": VERSION, "execution_sha256": execution_sha, "checks": result,
             "dirty_worktree_code_pinned_in_execution": True, "git_dvc_archived": False})))
    return result


def checks(conn, root, source, review, evidence):
    compare(conn, "cses_data", SOURCE, source)
    compare(conn, "cses_data", REVIEW, review)
    compare(conn, "cses_analysis", VIEW, review)
    spines(conn, root, source)
    rows = conn.execute(sql.SQL("SELECT evidence FROM {} ORDER BY source_id").format(
        sql.Identifier("cses_alignment", REGISTRY))).fetchall()
    require([r["evidence"] for r in rows] == sorted(evidence, key=lambda e: e["source_id"]), "Evidence mismatch")
    native = conn.execute(sql.SQL("SELECT * FROM {} ORDER BY source_id,variable_position").format(
        sql.Identifier("cses_analysis", FIELDS))).fetchall()
    want = sorted([f for e in evidence for f in e["fields"]], key=lambda f: (f["source_id"], f["variable_position"]))
    require(len(native) == len(want) == 248, "Native map count")
    for got, f in zip(native, want, strict=True):
        require(all(got[k] == f[k] for k in ("source_id", "survey_wave", "variable_name", "variable_position", "variable_label")),
                "Native metadata differs")
        require(got["value_labels"] == {v["source_value"]: v["label"] for v in f["value_labels"]}, "Native labels differ")
        require(got["json_path"] == [f["variable_name"]], "Native location differs")
    conn.execute("SET LOCAL ROLE mda_readonly")
    try:
        for schema, name in OBJECTS:
            n = conn.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(schema, name))).fetchone()["n"]
            require(n == (10 if name == REGISTRY else 248 if name == FIELDS else 358859), "Reader row count mismatch")
    finally:
        conn.execute("RESET ROLE")
    return {"source_rows": 358859, "review_rows": 358859, "source_datasets": 10, "native_fields": 248,
            "all_source_and_review_cells_exact": True, "evidence_exact": True, "reader_access_verified": True,
            "strict_screening_eligible": 134977, "within_wave_type_eligible_with_qualifications": 11074,
            "health_without_roster": 5, "roster_without_health": 66, "unresolved_2021_type_records": 1053}


def prepare(root, backup_dir):
    require(not (root / RELEASE / "execution.json").exists(), "Already prepared")
    source, review, sources, evidence, _ = local(root)
    with connect_database({"dbname": "mda"}) as conn:
        read_only(conn)
        absent(conn, sources)
        spines(conn, root, source)
        baseline = protected(conn)
        archives = read(root, f"{INTAKE}/manifest.json")["archive_sha256"]
        for row in conn.execute("SELECT relative_path,sha256 FROM cses_meta.cses_source_archive").fetchall():
            require(archives[row["relative_path"]] == row["sha256"], "Registered archive hash drift")
        for schema in ("cses_data", "cses_alignment", "cses_analysis"):
            require(conn.execute("SELECT has_schema_privilege('mda_readonly',%s,'USAGE') AS ok", (schema,)).fetchone()["ok"],
                    "Missing reader schema access")
    print("Read-only preflight passed: all live HH/HL keys and 37 historical physical tables fingerprinted", flush=True)
    require(backup_dir is not None and backup_dir.is_dir(), "Explicit existing external backup directory required")
    require(not backup_dir.resolve().is_relative_to(root.resolve()), "Backup must be outside the repository")
    fd, name = tempfile.mkstemp(prefix="mda_cses_health_", suffix=".dump", dir=backup_dir)
    os.close(fd)
    os.chmod(name, 0o600)
    args = ["pg_dump", "-d", "mda", "--format=custom", f"--file={name}"]
    # Only metadata will be appended. Survey data remain untouched and hash-protected.
    args += [f"--table={t}" for t in APPEND_KEYS]
    subprocess.run(args, check=True, timeout=55)
    subprocess.run(["pg_restore", "--file=/dev/null", name], check=True, timeout=55)
    toc = subprocess.check_output(["pg_restore", "--list", name], text=True)
    require(all(f"TABLE DATA {t.replace('.', ' ')} " in toc for t in APPEND_KEYS), "Incomplete backup")
    paths = [SELF, GRAPH, "rsc/cses_db/cses_baseline_metadata.py", "rsc/cses_db/cses_lineage_graph.py",
             "rsc/cses_db/organize_cses_questionnaires.py", "rsc/cses_db/plan_cses_health_illness.py",
             "rsc/cses_db/publish_cses_age_topcode.py", "rsc/specs/cses_health_illness_table_v1.json",
             f"{INTAKE}/manifest.json"]
    paths += [str(p.relative_to(root)) for d in (PRE, SCREEN, TYPE, KHM) for p in (root / d).iterdir() if p.is_file()]
    manifest = {"release_id": VERSION, "approval": "User: 可以入库 (2026-09-07). Source + qualified screening/type results only.",
        "file_sha256": {p: sha(root, p) for p in sorted(paths)}, "protected_before": baseline,
        "backup": {"path": name, "sha256": sha(root, name),
                   "scope": "Six append-target metadata tables including data; no survey microdata mutated.",
                   "full_decompression_verified": True},
        "review_columns": descriptor(review), "objects": OBJECTS, "historical_metadata_rows_preserved": True,
        "rollback_sequence_gaps_allowed": True, "git_dvc_archived": False}
    write_once(root / RELEASE / "execution.json", manifest)
    print("execution_sha256=" + sha(root, f"{RELEASE}/execution.json"), flush=True)


def execution(root, confirmation=None):
    manifest = read(root, f"{RELEASE}/execution.json")
    fingerprint = sha(root, f"{RELEASE}/execution.json")
    require(manifest["release_id"] == VERSION, "Wrong release")
    if confirmation is not None:
        require(confirmation == fingerprint, "Execution confirmation mismatch")
    for p, expected in manifest["file_sha256"].items():
        require(sha(root, p) == expected, f"Execution input changed: {p}")
    require(sha(root, manifest["backup"]["path"]) == manifest["backup"]["sha256"], "Backup changed")
    return manifest, fingerprint


def apply(root, confirmation, rollback_test):
    require(confirmation is not None, "Execution fingerprint required")
    manifest, fingerprint = execution(root, confirmation)
    require(not (root / RELEASE / "import.json").exists(), "Already imported; validate instead")
    if not rollback_test:
        require(read(root, f"{RELEASE}/rollback_test.json")["execution_sha256"] == fingerprint, "Rehearsal required")
    source, review, sources, evidence, _ = local(root)
    with connect_database({"dbname": "mda"}) as conn:
        conn.execute("SET LOCAL statement_timeout='55s'")
        conn.execute("SET LOCAL lock_timeout='15s'")
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (VERSION,))
        absent(conn, sources)
        for relation in sorted(manifest["protected_before"]["rows"]):
            conn.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(sql.Identifier(*relation.split("."))))
        require(protected(conn, manifest["protected_before"]) == manifest["protected_before"], "Historical state changed")
        result = create(conn, root, source, review, sources, evidence, fingerprint)
        require(protected(conn, manifest["protected_before"]) == manifest["protected_before"], "Historical rows/definitions changed")
        objects = catalog(conn, [list(p) for p in OBJECTS])
        if rollback_test:
            conn.rollback()
        else:
            conn.commit()
    if rollback_test:
        with connect_database({"dbname": "mda"}) as conn:
            read_only(conn)
            absent(conn, sources)
            require(protected(conn, manifest["protected_before"]) == manifest["protected_before"], "Rollback drift")
        write_once(root / RELEASE / "rollback_test.json", {"execution_sha256": fingerprint, "checks": result,
            "all_five_objects_and_metadata_rows_rolled_back": True, "identity_sequence_gaps_expected": True})
        print("Rollback rehearsal passed, all source/review cells and metadata checked", flush=True)
    else:
        write_once(root / RELEASE / "import.json", {"execution_sha256": fingerprint, "checks": result,
                   "objects": objects, "database_mutated": True, "historical_rows_and_definitions_preserved": True})
        print("Published HEALTH: three physical tables, two views, ten datasets and 248 native fields", flush=True)


def export_graph(conn, root, fingerprint):
    prior = read(root, GRAPH)
    fresh = build_lineage_graph(read_lineage_snapshot(conn), subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip())
    builder = GraphBuilder()
    old_ids = {n["id"] for n in prior["nodes"]}
    for n in prior["nodes"]:
        builder.add_node(n["id"], n["type"], **n["properties"])
    for e in prior["edges"]:
        builder.add_edge(e["type"], e["source"], e["target"], **e["properties"])
    new_ids = {n["id"] for n in fresh["nodes"]} - old_ids
    for n in fresh["nodes"]:
        if n["id"] in new_ids:
            builder.add_node(n["id"], n["type"], **n["properties"])
    for e in fresh["edges"]:
        if e["source"] in new_ids or e["target"] in new_ids:
            builder.add_edge(e["type"], e["source"], e["target"], **e["properties"])
    for view, origin in [(VIEW, ("cses_data", REVIEW)), (FIELDS, ("cses_alignment", REGISTRY))]:
        node = _node_id("analysis_view", "cses_analysis", view)
        builder.add_node(node, "analysis_view", schema="cses_analysis", name=view, interface_release=VERSION)
        builder.add_edge("schema_exposes_analysis_view", _node_id("schema", "cses_analysis"), node)
        builder.add_edge("relation_feeds_analysis_view", _node_id("storage_table", *origin), node)
    builder.add_edge("review_preserves_source_rows", _node_id("storage_table", "cses_data", SOURCE),
                     _node_id("storage_table", "cses_data", REVIEW), execution_sha256=fingerprint)
    builder.add_edge("evidence_qualifies_review", _node_id("storage_table", "cses_alignment", REGISTRY),
                     _node_id("storage_table", "cses_data", REVIEW), concepts=2, all_wave_equivalence=False)
    graph = copy.deepcopy(prior)
    graph["nodes"], graph["edges"] = builder.finish()
    graph["source"]["health_extension"] = {"release_id": VERSION, "execution_sha256": fingerprint,
        "previous_graph_sha256": sha(root, GRAPH), "existing_nodes_and_edges_preserved": True}
    for key in ("dataset_with_output_count", "dataset_without_output_count", "storage_output_coverage",
                "storage_without_dataset_outputs", "value_mapping_count"):
        graph["summary"][key] = fresh["summary"][key]
    graph["checks"] = fresh["checks"]
    graph["checks"]["health_uses_analysis_views_not_public_compatibility_aliases"] = True
    graph["summary"].update(node_count=len(graph["nodes"]), edge_count=len(graph["edges"]),
        node_type_counts=dict(sorted(Counter(n["type"] for n in graph["nodes"]).items())),
        edge_type_counts=dict(sorted(Counter(e["type"] for e in graph["edges"]).items())))
    write_once(root / "data/lineage/cses_lineage_graph_v15.json", graph)
    return {"nodes": len(graph["nodes"]), "edges": len(graph["edges"])}


def validate(root):
    manifest, fingerprint = execution(root)
    imported = read(root, f"{RELEASE}/import.json")
    require(imported["execution_sha256"] == fingerprint, "Wrong import evidence")
    source, review, _, evidence, _ = local(root)
    with connect_database({"dbname": "mda"}) as conn:
        read_only(conn)
        require(catalog(conn, [list(p) for p in OBJECTS]) == imported["objects"], "Published definitions changed")
        require(protected(conn, manifest["protected_before"]) == manifest["protected_before"], "Historical rows changed")
        result = checks(conn, root, source, review, evidence)
        require(result == imported["checks"], "Independent checks differ")
        registered = conn.execute("""SELECT count(*) AS outputs FROM cses_meta.cses_dataset_output o
          JOIN cses_meta.cses_alignment_release r USING(alignment_release_id) WHERE mapping_version=%s""", (VERSION,)).fetchone()
        require(registered["outputs"] == 30, "Expected thirty dataset-output edges")
        run = conn.execute("SELECT status,validation_summary FROM cses_meta.cses_load_run WHERE run_scope=%s", (VERSION,)).fetchall()
        require(len(run) == 1 and run[0]["status"] == "loaded" and
                run[0]["validation_summary"]["execution_sha256"] == fingerprint, "Load-run drift")
        graph = export_graph(conn, root, fingerprint)
    write_once(root / RELEASE / "validation.json", {"execution_sha256": fingerprint, "checks": result,
        "validation_passed": True, "transaction_read_only": True, "graph_v15": graph,
        "historical_rows_and_definitions_preserved": True})
    print(json.dumps({"validation_passed": True, "checks": result, "graph_v15": graph}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["local", "prepare", "apply", "validate"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--execution-sha256")
    parser.add_argument("--rollback-test", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()
    if args.mode == "local":
        source, review, sources, evidence, _ = local(args.root)
        print(json.dumps({"source_rows": len(source), "review_rows": len(review), "sources": len(sources), "evidence": len(evidence)}))
    elif args.mode == "prepare":
        prepare(args.root, args.backup_dir)
    elif args.mode == "apply":
        apply(args.root, args.execution_sha256, args.rollback_test)
    else:
        validate(args.root)


if __name__ == "__main__":
    main()
