#!/usr/bin/env python3
"""Publish the approved EC recovery and missing/topcode interpretation additively."""
from __future__ import annotations

import argparse
import copy
import io
import json
import os
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

import pandas as pd
from cses_baseline_metadata import canonical_sha256, connect_database
from cses_employment import employment_sources, prepare_wave_sources, source_value
from cses_hh_hl_common import AlignmentContext, snake_case
from cses_lineage_graph import GraphBuilder, _node_id
from organize_cses_questionnaires import digest, write_once
from plan_cses_age_topcode import checked_review, qualify, require
from psycopg import sql
from publish_cses_age_topcode import read_only
from review_cses_education import normalize_legacy_source_paths
from review_cses_employment_hours_status import clean_numeric, data_review, evidence, registry, variable_entry

SELF = "rsc/cses_db/publish_cses_employment_correction.py"
VERSION = "cses-employment-recovery-qualified-v1"
DIRECTORY = "data/processing/cses/employment_corrected_v1"
RELEASE = f"data/releases/{VERSION}"
REVIEW = "data/processing/cses/employment_hours_status_review_v1/review.json"
REVIEW_SHA = "077c6e78e6a64ba5fccd44041f856fa4db7cceca85d46a251bdf94cd31288ae2"
GRAPH = "data/lineage/cses_lineage_graph_v12.json"
GRAPH_SHA = "74d6dc71e1ea36f36a51ab3ddac369ef5a0ab3d84132c8c9f4feb3d0d5972641"
VIEW, RULE, TABLE = "cses_ec_aligned_v1", "cses_ec_correction_rule_v1", "cses_ec_secondary_days_recovery_v1"
VIEWS, OBJECTS = [VIEW, RULE], [VIEW, RULE, TABLE]
DAY = "secondary_days_worked_last_month"
STATUS = ["main_employment_status_source_code", "secondary_employment_status_source_code"]
INTERPRETED = ["main_employment_status_interpreted", "secondary_employment_status_interpreted"]
MISSING = ["main_status_2004_is_labelled_missing", "secondary_status_2004_is_labelled_missing"]
HOUR = "total_hours_worked_past_7_days"
EXTRAS = ["secondary_days_before_recovery", "secondary_days_recovery_version", *INTERPRETED, *MISSING,
          "total_hours_2004_is_topcoded", "total_hours_2004_lower_bound", "total_hours_2004_exact", "total_hours_2004_status"]
RECOVERY_COLUMNS = ["survey_wave", "person_id", DAY, "source_row_id"]


def corrected(frame, recovery):
    require(not set(EXTRAS) & set(frame.columns), "Correction columns already exist")
    require(not recovery[RECOVERY_COLUMNS].isna().any().any(), "Recovery values and keys must be present")
    require(not recovery.duplicated(["survey_wave", "person_id"]).any(), "Duplicate recovery key")
    require(recovery.survey_wave.eq("2009").all() and recovery[DAY].between(0, 31).all()
            and recovery[DAY].mod(1).eq(0).all(), "Recovery outside approved wave/domain")
    joined = frame.merge(recovery.rename(columns={DAY: "__recovered"}), on=["survey_wave", "person_id", "source_row_id"],
                         how="left", validate="one_to_one", sort=False)
    recovered = joined.pop("__recovered").astype("Int16")
    joined = joined.astype(frame.dtypes.to_dict())
    require(int(recovered.notna().sum()) == len(recovery), "Recovery row identity not found in base")
    require(joined.loc[recovered.notna(), DAY].isna().all(), "Never overwrite existing secondary days")
    joined[EXTRAS[0]] = joined[DAY]
    joined[DAY] = joined[DAY].combine_first(recovered)
    joined[EXTRAS[1]] = pd.Series(pd.NA, index=joined.index, dtype="string").mask(recovered.notna(), VERSION)
    scope = joined.survey_wave.eq("2004")
    for source, target, flag in zip(STATUS, INTERPRETED, MISSING, strict=True):
        missing = scope & joined[source].eq(9).fillna(False)
        joined[target] = joined[source].mask(missing)
        joined[flag] = joined[source].eq(9).astype("boolean").where(scope & joined[source].notna())
    hours = joined[HOUR]
    valid = scope & hours.between(0, 96).fillna(False)
    top = valid & hours.eq(96).fillna(False)
    joined[EXTRAS[6]] = hours.eq(96).astype("boolean").where(valid)
    joined[EXTRAS[7]] = hours.where(valid).astype("Int16")
    joined[EXTRAS[8]] = hours.where(valid & ~top).astype("Int16")
    state = pd.Series("outside_rule_scope", index=joined.index, dtype="string")
    state.loc[scope] = "unexpected_2004_code"
    state.loc[valid] = "reported_hours"
    state.loc[top] = "topcoded_96_plus"
    state.loc[scope & hours.isna()] = "missing_hours"
    joined[EXTRAS[9]] = state
    restored = joined[list(frame.columns)].copy()
    restored[DAY] = joined[EXTRAS[0]]
    pd.testing.assert_frame_equal(restored, frame.reset_index(drop=True), check_exact=True)
    return joined[[*frame.columns, *EXTRAS]]


def view_query(columns, recovery_relation=None):
    expressions = [sql.SQL("coalesce(b.{day},r.{day}) AS {day}").format(day=sql.Identifier(DAY))
                   if c == DAY else sql.Identifier("b", c) for c in columns]
    expressions += [sql.SQL("b.{} AS {}").format(sql.Identifier(DAY), sql.Identifier(EXTRAS[0])),
        sql.SQL("CASE WHEN r.person_id IS NOT NULL THEN {}::text ELSE NULL END AS {}").format(sql.Literal(VERSION), sql.Identifier(EXTRAS[1]))]
    for source, target in zip(STATUS, INTERPRETED, strict=True):
        expressions.append(sql.SQL("CASE WHEN b.survey_wave='2004' AND b.{s}=9 THEN NULL ELSE b.{s} END::smallint AS {t}")
                           .format(s=sql.Identifier(source), t=sql.Identifier(target)))
    for source, target in zip(STATUS, MISSING, strict=True):
        expressions.append(sql.SQL("CASE WHEN b.survey_wave='2004' THEN b.{s}=9 ELSE NULL END::boolean AS {t}")
                           .format(s=sql.Identifier(source), t=sql.Identifier(target)))
    expressions += [sql.SQL("CASE WHEN b.survey_wave='2004' AND b.{h} BETWEEN 0 AND 96 THEN b.{h}=96 ELSE NULL END::boolean AS {t}")
                    .format(h=sql.Identifier(HOUR), t=sql.Identifier(EXTRAS[6])),
        sql.SQL("CASE WHEN b.survey_wave='2004' AND b.{h} BETWEEN 0 AND 96 THEN b.{h} ELSE NULL END::smallint AS {t}")
                    .format(h=sql.Identifier(HOUR), t=sql.Identifier(EXTRAS[7])),
        sql.SQL("CASE WHEN b.survey_wave='2004' AND b.{h} BETWEEN 0 AND 95 THEN b.{h} ELSE NULL END::smallint AS {t}")
                    .format(h=sql.Identifier(HOUR), t=sql.Identifier(EXTRAS[8])),
        sql.SQL("CASE WHEN b.survey_wave<>'2004' THEN 'outside_rule_scope' WHEN b.{h} IS NULL THEN 'missing_hours' WHEN b.{h}=96 THEN 'topcoded_96_plus' WHEN b.{h} BETWEEN 0 AND 95 THEN 'reported_hours' ELSE 'unexpected_2004_code' END::text AS {t}")
                    .format(h=sql.Identifier(HOUR), t=sql.Identifier(EXTRAS[9]))]
    return sql.SQL("SELECT {} FROM cses_analysis.cses_ec_age_v1 b LEFT JOIN {} r ON b.survey_wave=r.survey_wave AND b.person_id=r.person_id AND b.source_row_id=r.source_row_id").format(
        sql.SQL(",").join(expressions), recovery_relation or sql.Identifier("cses_analysis", TABLE)).as_string()


def source_plan(root):
    checked_review(root)
    require(digest((root / REVIEW).read_bytes()) == REVIEW_SHA, "Approved hours/status review changed")
    review = json.loads((root / REVIEW).read_text())
    for path, key in [("rsc/cses_db/review_cses_employment_hours_status.py", "implementation_sha256"),
                      ("rsc/cses_db/cses_employment.py", "employment_builder_sha256"),
                      ("data/processing/cses/final_EC_CSES.parquet", "canonical_parquet_sha256")]:
        require(digest((root / path).read_bytes()) == review[key], "Frozen review dependency changed")
    require(digest((root / GRAPH).read_bytes()) == GRAPH_SHA, "Prior graph changed")
    q, _ = evidence(root)
    original, profiles, sources, diagnostics, candidate = data_review(root, q)
    require([profiles, sources, diagnostics, candidate] == [review[k] for k in ["profiles", "raw_sources", "wave_counts", "missing_alias_candidate"]], "Fresh raw reproduction differs from review")
    raw_sources = next(s for w, s in employment_sources(root) if w == "2009")
    keys, aligned = prepare_wave_sources(AlignmentContext(root=root), "2009", raw_sources)
    keys = keys.rename(columns=snake_case)
    raw, column = source_value(aligned, ["q15_c17"])
    require(column == "q15_c17", "Exact recovery variable required")
    values = clean_numeric(raw, 31, (98, 99))
    base = original.loc[original.survey_wave.eq("2009")].set_index("person_id").loc[keys.person_id].reset_index()
    values = values.mask(base.total_occupations_past_7_days.notna() & base.total_occupations_past_7_days.lt(2))
    recovery = keys[["survey_wave", "person_id", "source_row_id"]].copy()
    recovery[DAY] = values
    recovery = recovery.loc[values.notna(), RECOVERY_COLUMNS].sort_values(["survey_wave", "person_id"]).reset_index(drop=True)
    recovery = recovery.astype(original[RECOVERY_COLUMNS].dtypes.to_dict())
    require(len(recovery) == 13830, "Exact 13830-row recovery required")
    before = qualify(original, "age")
    after = corrected(before, recovery)
    require(after.shape == (332903, 74), "Unexpected corrected EC grain")
    require([int(after[c].fillna(False).sum()) for c in MISSING] == [185, 71], "Exact labelled-missing scope changed")
    require(int(after[EXTRAS[6]].fillna(False).sum()) == 6, "Exact six hours topcodes required")
    require(not after[EXTRAS[9]].eq("unexpected_2004_code").any(), "Unexpected 2004 hour code")
    rules = []
    for rule_id, wave, field, name, kind, count in [
        ("01_secondary_days", "2009", DAY, "q15_c17", "recover_omitted_source_alias", 13830),
        ("02_main_status", "2004", STATUS[0], "q13b06_1", "labelled_missing_9_interpretation", 185),
        ("03_secondary_status", "2004", STATUS[1], "q13b06_2", "labelled_missing_9_interpretation", 71),
        ("04_total_hours", "2004", HOUR, "q13a05", "topcoded_96_plus", 6)]:
        entry = variable_entry(registry(root), wave, name)
        question = next(x for x in q if x["survey_wave"] == wave and x["field"] == field)
        file = "::".join(p for p in [entry["archive_relative_path"], entry["member_path"], entry["nested_member_path"]] if p)
        source = next(s for w in sources if w["survey_wave"] == wave for s in w["sources"] if s["source_file"] == file)
        rules.append({"rule_id": rule_id, "survey_wave": wave, "canonical_field": field,
            "source_variable_id": entry["source_variable_id"], "source_variable": name, "rule_kind": kind, "affected_cells_or_records": count,
            "data_source_file": file, "data_source_sha256": source["sha256"],
            "questionnaire_file": question["source_file"], "questionnaire_sha256": question["source_sha256"],
            "source_sheet": question["source_sheet"], "source_cell": question["question_text_cell"],
            "source_value_label": None if wave == "2009" else entry["value_labels"]["96" if field == HOUR else "9"],
            "release_id": VERSION, "review_sha256": REVIEW_SHA,
            "qualification": "Same-wave original data and reviewed questionnaire; no cross-wave transfer. Original physical data retained."})
    rule_query = sql.SQL("SELECT * FROM jsonb_to_recordset({}::jsonb) AS r(rule_id text,survey_wave text,canonical_field text,source_variable_id bigint,source_variable text,rule_kind text,affected_cells_or_records integer,data_source_file text,data_source_sha256 text,questionnaire_file text,questionnaire_sha256 text,source_sheet text,source_cell text,source_value_label text,release_id text,review_sha256 text,qualification text)").format(sql.Literal(json.dumps(rules, sort_keys=True))).as_string()
    plan = {"release_id": VERSION, "implementation_sha256": digest((root / SELF).read_bytes()), "review_sha256": REVIEW_SHA,
        "queries": {VIEW: view_query(before.columns), RULE: rule_query}, "rules": rules, "rows": 332903,
        "columns": list(after.columns), "new_objects": OBJECTS, "recovered_cells": 13830, "labelled_missing_cells": {"main": 185, "secondary": 71},
        "hours_topcoded_records": 6, "original_age_topcoded_records": int(after.age_2004_is_topcoded.fillna(False).sum()),
        "recovery_values_sha256": canonical_sha256(recovery.to_dict("records")),
        "existing_physical_changes": 0, "existing_interfaces_replaced": 0, "new_recovery_table_rows": 13830}
    return plan, after, recovery


def plan_files(root):
    plan, after, recovery = source_plan(root)
    write_once(root / DIRECTORY / "plan.json", plan)
    for name, frame in [("final_EC_CSES.parquet", after), ("secondary_days_recovery.parquet", recovery)]:
        payload = io.BytesIO()
        frame.to_parquet(payload, index=False)
        path = root / DIRECTORY / name
        if path.exists():
            require(path.read_bytes() == payload.getvalue(), "Versioned Parquet differs")
        else:
            path.write_bytes(payload.getvalue())
    return plan, after, recovery


def object_state(conn):
    columns = conn.execute("""SELECT c.relname,c.relkind,c.oid::bigint,c.relowner::bigint,c.relacl::text,c.reloptions,
      CASE WHEN c.relkind='v' THEN pg_get_viewdef(c.oid,true) END AS definition,obj_description(c.oid,'pg_class') AS comment,
      a.attnum,a.attname,a.attnotnull,format_type(a.atttypid,a.atttypmod) AS type,col_description(c.oid,a.attnum) AS column_comment
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
      WHERE n.nspname='cses_analysis' AND c.relname=ANY(%s) ORDER BY c.relname,a.attnum""", (OBJECTS,)).fetchall()
    constraints = conn.execute("""SELECT c.conname,c.contype,pg_get_constraintdef(c.oid,true) AS definition FROM pg_constraint c
      JOIN pg_class r ON r.oid=c.conrelid JOIN pg_namespace n ON n.oid=r.relnamespace
      WHERE n.nspname='cses_analysis' AND r.relname=ANY(%s) ORDER BY c.conname""", (OBJECTS,)).fetchall()
    return {"columns": columns, "constraints": constraints}


def protected(conn):
    relations = conn.execute("""SELECT n.nspname AS schema_name,c.relname AS table_name,c.oid::bigint,c.relowner::bigint,c.relacl::text
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('cses_meta','cses_alignment','cses_data','cses_analysis') AND c.relkind='r'
      AND NOT (n.nspname='cses_analysis' AND c.relname=%s) ORDER BY n.nspname,c.relname""", (TABLE,)).fetchall()
    require(len(relations) == 35, "Expected 35 pre-existing physical relations")
    for row in relations:
        row.update(conn.execute(sql.SQL("""SELECT count(*) AS rows,encode(sha256(convert_to(coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') AS sha256
          FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS h FROM {} t) hashes""")
          .format(sql.Identifier(row["schema_name"], row["table_name"]))).fetchone())
    structure = conn.execute("""SELECT n.nspname,c.relname,c.relkind,c.oid::bigint,c.relowner::bigint,c.relacl::text,c.reloptions,
      obj_description(c.oid,'pg_class') AS comment,a.attnum,a.attname,a.attnotnull,format_type(a.atttypid,a.atttypmod) AS type,
      col_description(c.oid,a.attnum) AS column_comment,CASE WHEN c.relkind='v' THEN pg_get_viewdef(c.oid,true) END AS definition
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
      WHERE (n.nspname IN ('cses_meta','cses_alignment','cses_data','cses_analysis') OR
        (n.nspname='public' AND c.relname IN (SELECT table_name FROM cses_meta.cses_storage_table)))
      AND c.relkind IN ('r','v','m') AND NOT (n.nspname='cses_analysis' AND c.relname=ANY(%s))
      ORDER BY n.nspname,c.relname,a.attnum""", (OBJECTS,)).fetchall()
    indexes = conn.execute("""SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes
      WHERE schemaname IN ('cses_meta','cses_alignment','cses_data','cses_analysis')
      AND NOT (schemaname='cses_analysis' AND tablename=%s) ORDER BY 1,2,3""", (TABLE,)).fetchall()
    return {"physical_relations": relations, "structure_sha256": canonical_sha256(structure), "indexes_sha256": canonical_sha256(indexes)}


def absent(conn):
    require(not conn.execute("SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='cses_analysis' AND c.relname=ANY(%s)", (OBJECTS,)).fetchone(), "Target exists; never replace or blindly retry uncertain commits")
    require(not conn.execute("SELECT 1 FROM pg_event_trigger WHERE evtenabled<>'D'").fetchone(), "Active DDL event trigger")


def checks(conn, expected, recovery, plan, published):
    if published:
        query = f"SELECT * FROM cses_analysis.{VIEW}"
        actual_recovery = pd.DataFrame(conn.execute(sql.SQL("SELECT * FROM {} ORDER BY survey_wave,person_id").format(sql.Identifier("cses_analysis", TABLE))).fetchall()).astype(recovery.dtypes.to_dict())
        pd.testing.assert_frame_equal(actual_recovery, recovery, check_exact=True)
    else:
        payload = sql.Literal(recovery.to_json(orient="records"))
        cte = sql.SQL("WITH recovered AS (SELECT * FROM jsonb_to_recordset({}::jsonb) AS r(survey_wave text,person_id text,secondary_days_worked_last_month smallint,source_row_id text)) ").format(payload).as_string()
        query = cte + view_query([c for c in expected if c not in EXTRAS], sql.Identifier("recovered"))
    live = pd.DataFrame(conn.execute(sql.SQL("SELECT * FROM ({}) checked ORDER BY survey_wave,person_id").format(sql.SQL(query))).fetchall()).astype(expected.dtypes.to_dict())
    live.source_archive = normalize_legacy_source_paths(live.source_archive)
    pd.testing.assert_frame_equal(live, expected.sort_values(["survey_wave", "person_id"]).reset_index(drop=True), check_exact=True)
    query = f"SELECT * FROM cses_analysis.{RULE}" if published else plan["queries"][RULE]
    require(conn.execute(sql.SQL("SELECT * FROM ({}) rules ORDER BY rule_id").format(sql.SQL(query))).fetchall() == plan["rules"], "Rule evidence differs")
    if published:
        conn.execute("SET LOCAL ROLE mda_readonly")
        try:
            counts = {v: conn.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier("cses_analysis", v))).fetchone()["n"] for v in OBJECTS}
        finally:
            conn.execute("RESET ROLE")
        require(counts == {VIEW: 332903, RULE: 4, TABLE: 13830}, "Readonly access/count mismatch")
    return {"rows": len(live), "columns": len(live.columns), "recovered_days": int(live[EXTRAS[1]].notna().sum()),
            "main_labelled_missing": int(live[MISSING[0]].fillna(False).sum()), "secondary_labelled_missing": int(live[MISSING[1]].fillna(False).sum()),
            "hours_topcoded": int(live[EXTRAS[6]].fillna(False).sum()), "age_topcoded_preserved": int(live.age_2004_is_topcoded.fillna(False).sum()),
            "all_projected_cells_match": True, "known_archive_prefix_normalized_for_comparison_only": True}


def prepare(root, backup_dir):
    require(not (root / RELEASE / "execution.json").exists(), "Preserve existing execution record")
    plan, after, recovery = plan_files(root)
    with connect_database({"dbname": "mda"}) as conn:
        read_only(conn)
        absent(conn)
        result = checks(conn, after, recovery, plan, False)
        baseline = protected(conn)
        require(conn.execute("SELECT has_schema_privilege('mda_readonly','cses_analysis','USAGE') AS ok").fetchone()["ok"], "Missing reader schema access")
    print("Read-only preflight passed; 35 historical physical tables protected", flush=True)
    require(backup_dir.is_dir(), "Explicit existing backup directory required")
    fd, name = tempfile.mkstemp(prefix="mda_cses_ec_correction_", suffix=".dump", dir=backup_dir)
    os.close(fd)
    os.chmod(name, 0o600)
    subprocess.run(["pg_dump", "-d", "mda", "--format=custom", "--schema-only", "--schema=cses_analysis", f"--file={name}"], check=True, timeout=55)
    subprocess.run(["pg_restore", "--file=/dev/null", name], check=True, timeout=55)
    paths = [SELF, REVIEW, GRAPH, DIRECTORY + "/plan.json", DIRECTORY + "/final_EC_CSES.parquet", DIRECTORY + "/secondary_days_recovery.parquet",
             "rsc/cses_db/review_cses_employment_hours_status.py", "rsc/cses_db/review_cses_employment_screening.py",
             "rsc/cses_db/publish_cses_age_topcode.py", "rsc/cses_db/plan_cses_age_topcode.py", "rsc/cses_db/review_cses_education.py",
             "rsc/cses_db/cses_lineage_graph.py", "rsc/cses_db/cses_baseline_metadata.py", "rsc/cses_db/organize_cses_questionnaires.py"]
    manifest = {"release_id": VERSION, "approval": "User: 好的，继续 after scoped proposal of 13830 recovered days, 256 labelled-missing status cells and six 96+ hours records. Additive table/views announced.",
        "file_sha256": {p: digest((root / p).read_bytes()) for p in paths}, "protected_before": baseline, "preflight": result,
        "backup": {"path": name, "sha256": digest(Path(name).read_bytes()), "full_decompression_verified": True, "scope": "cses_analysis schema only; no respondent data"},
        "git_base_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(), "git_dvc_archived": False}
    write_once(root / RELEASE / "execution.json", manifest)
    print("execution_sha256=" + digest((root / RELEASE / "execution.json").read_bytes()), flush=True)


def execution(root):
    payload = (root / RELEASE / "execution.json").read_bytes()
    manifest = json.loads(payload)
    require(manifest["release_id"] == VERSION, "Wrong execution release")
    for name, sha in manifest["file_sha256"].items():
        require(digest((root / name).read_bytes()) == sha, f"Execution input changed: {name}")
    plan, expected, recovery = source_plan(root)
    require(plan == json.loads((root / DIRECTORY / "plan.json").read_text()), "Prepared plan changed")
    return manifest, digest(payload), plan, expected, recovery


def apply(root, confirmation, rollback_test=False):
    manifest, sha, plan, expected, recovery = execution(root)
    require(confirmation == sha, "Verified execution hash required")
    require(digest(Path(manifest["backup"]["path"]).read_bytes()) == manifest["backup"]["sha256"], "Backup changed")
    require(not (root / RELEASE / "import.json").exists(), "Already published; validate instead")
    if not rollback_test:
        require(json.loads((root / RELEASE / "rollback_test.json").read_text()) ==
                {"execution_sha256": sha, "three_objects_rolled_back": True, "protected_state_unchanged": True}, "Matching rollback rehearsal required")
    with connect_database({"dbname": "mda"}) as conn:
        conn.execute("SET LOCAL statement_timeout='55s'")
        conn.execute("SET LOCAL lock_timeout='15s'")
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (VERSION,))
        absent(conn)
        for r in manifest["protected_before"]["physical_relations"]:
            conn.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(sql.Identifier(r["schema_name"], r["table_name"])))
        require(protected(conn) == manifest["protected_before"], "Protected state changed before publication")
        conn.execute(sql.SQL("CREATE TABLE {} (survey_wave text NOT NULL CHECK(survey_wave='2009'),person_id text NOT NULL,secondary_days_worked_last_month smallint NOT NULL CHECK(secondary_days_worked_last_month BETWEEN 0 AND 31),source_row_id text NOT NULL,PRIMARY KEY(survey_wave,person_id))").format(sql.Identifier("cses_analysis", TABLE)))
        with conn.cursor().copy(sql.SQL("COPY {} (survey_wave,person_id,secondary_days_worked_last_month,source_row_id) FROM STDIN").format(sql.Identifier("cses_analysis", TABLE))) as writer:
            for wave, person, days, row_id in recovery.itertuples(index=False, name=None):
                writer.write_row((str(wave), str(person), int(days), str(row_id)))
        for view in VIEWS:
            conn.execute(sql.SQL("CREATE VIEW {} WITH (security_barrier=true) AS {}").format(sql.Identifier("cses_analysis", view), sql.SQL(plan["queries"][view])))
        for name in OBJECTS:
            kind = sql.SQL("TABLE" if name == TABLE else "VIEW")
            comment = f"{VERSION}; execution {sha}; review {REVIEW_SHA}; 13830 recovered days; 185+71 labelled-missing status cells; six 96+ hours records; original tables and historical interfaces unchanged."
            conn.execute(sql.SQL("COMMENT ON {} {} IS {}").format(kind, sql.Identifier("cses_analysis", name), sql.Literal(comment)))
            conn.execute(sql.SQL("GRANT SELECT ON {} TO mda_readonly").format(sql.Identifier("cses_analysis", name)))
        for field in EXTRAS:
            comment = f"{VERSION}; see cses_analysis.{RULE}. Qualifications are wave-specific, not a global comparability assertion."
            conn.execute(sql.SQL("COMMENT ON COLUMN {} IS {}").format(sql.Identifier("cses_analysis", VIEW, field), sql.Literal(comment)))
        result = checks(conn, expected, recovery, plan, True)
        require(protected(conn) == manifest["protected_before"], "Historical data/interfaces changed during publication")
        state = object_state(conn)
        if rollback_test:
            conn.rollback()
        else:
            conn.commit()
    if rollback_test:
        with connect_database({"dbname": "mda"}) as conn:
            read_only(conn)
            absent(conn)
            require(protected(conn) == manifest["protected_before"], "Rollback state mismatch")
        write_once(root / RELEASE / "rollback_test.json", {"execution_sha256": sha, "three_objects_rolled_back": True, "protected_state_unchanged": True})
        print("Rollback rehearsal passed", flush=True)
    else:
        write_once(root / RELEASE / "import.json", {"execution_sha256": sha, "object_state": state, "checks": result,
            "new_physical_recovery_rows": 13830, "existing_physical_data_mutated": False, "database_mutated": True})
        print("Published EC recovery table, corrected interface and four source rules", flush=True)


def validate(root):
    manifest, sha, plan, expected, recovery = execution(root)
    imported = json.loads((root / RELEASE / "import.json").read_text())
    require(imported["execution_sha256"] == sha, "Import execution mismatch")
    with connect_database({"dbname": "mda"}) as conn:
        read_only(conn)
        require(object_state(conn) == imported["object_state"], "Published object structure changed")
        require(protected(conn) == manifest["protected_before"], "Protected historical state changed")
        result = checks(conn, expected, recovery, plan, True)
        require(result == imported["checks"], "Independent checks differ")
    write_once(root / RELEASE / "validation.json", {"execution_sha256": sha, "checks": result, "validation_passed": True,
        "transaction_read_only": True, "database_mutated": False})
    print("Independent EC correction validation passed", flush=True)


def graph_extension(prior, plan, sha, entries, dependencies):
    builder = GraphBuilder()
    for n in prior["nodes"]:
        builder.add_node(n["id"], n["type"], **n["properties"])
    for e in prior["edges"]:
        builder.add_edge(e["type"], e["source"], e["target"], **e["properties"])
    nodes = {name: _node_id("analysis_recovery_table" if name == TABLE else "analysis_view", "cses_analysis", name) for name in OBJECTS}
    for name, node in nodes.items():
        kind = "analysis_recovery_table" if name == TABLE else "analysis_view"
        builder.add_node(node, kind, schema="cses_analysis", name=name, interface_release=VERSION, execution_sha256=sha)
        builder.add_edge("schema_exposes_" + kind, _node_id("schema", "cses_analysis"), node)
    builder.add_edge("relation_feeds_analysis_view", _node_id("analysis_view", "cses_analysis", "cses_ec_age_v1"), nodes[VIEW])
    builder.add_edge("relation_feeds_analysis_view", nodes[TABLE], nodes[VIEW])
    builder.add_edge("documented_rule_corrects_view", nodes[RULE], nodes[VIEW], rule_count=4)
    for rule in plan["rules"]:
        entry = next(v for v in entries if v["source_variable_id"] == rule["source_variable_id"])
        datasets = [n for n in prior["nodes"] if n["type"] == "dataset" and n["properties"]["member_path"] == entry["member_path"]
                    and n["properties"]["nested_member_path"] == entry["nested_member_path"]
                    and Path(n["properties"]["archive_relative_path"]).name == Path(entry["archive_relative_path"]).name]
        require(len(datasets) == 1, "Exact source dataset graph node required")
        source = _node_id("source_variable", datasets[0]["id"], entry["variable_name"])
        builder.add_edge("source_variable_supports_recovery" if rule["survey_wave"] == "2009" else "source_variable_supports_interpretation",
                         source, nodes[TABLE] if rule["survey_wave"] == "2009" else nodes[RULE], rule_id=rule["rule_id"], review_sha256=REVIEW_SHA)
    graph = copy.deepcopy(prior)
    graph["nodes"], graph["edges"] = builder.finish()
    graph["source"]["employment_correction_extension"] = {"execution_sha256": sha, "previous_graph_sha256": GRAPH_SHA, "verified_dependencies": dependencies}
    graph["summary"].update(node_count=len(graph["nodes"]), edge_count=len(graph["edges"]),
        node_type_counts=dict(sorted(Counter(n["type"] for n in graph["nodes"]).items())),
        edge_type_counts=dict(sorted(Counter(e["type"] for e in graph["edges"]).items())))
    return graph


def export(root, output):
    _, sha, plan, expected, recovery = execution(root)
    valid = json.loads((root / RELEASE / "validation.json").read_text())
    require(valid["validation_passed"] and valid["execution_sha256"] == sha, "Independent validation required before graph export")
    with connect_database({"dbname": "mda"}) as conn:
        read_only(conn)
        require(object_state(conn) == json.loads((root / RELEASE / "import.json").read_text())["object_state"], "Object state changed before export")
        checks(conn, expected, recovery, plan, True)
        deps = conn.execute("""SELECT DISTINCT v.relname AS view_name,n.nspname AS source_schema,c.relname AS source_relation
          FROM pg_class v JOIN pg_namespace vn ON vn.oid=v.relnamespace JOIN pg_rewrite r ON r.ev_class=v.oid
          JOIN pg_depend d ON d.objid=r.oid AND d.classid='pg_rewrite'::regclass JOIN pg_class c ON c.oid=d.refobjid AND d.refclassid='pg_class'::regclass
          JOIN pg_namespace n ON n.oid=c.relnamespace WHERE vn.nspname='cses_analysis' AND v.relname=ANY(%s) AND c.oid<>v.oid ORDER BY 1,2,3""", (VIEWS,)).fetchall()
    require(deps == [{"view_name": VIEW, "source_schema": "cses_analysis", "source_relation": name} for name in ["cses_ec_age_v1", TABLE]], "Unexpected SQL dependencies")
    graph = graph_extension(json.loads((root / GRAPH).read_text()), plan, sha, registry(root), deps)
    write_once(output / "cses_lineage_graph_v13.json", graph)
    write_once(output / "cses_employment_correction_topology_v1.json", {"execution_sha256": sha, "dependencies": deps, "summary": graph["summary"]})
    print(f"Graph v13: {len(graph['nodes'])} nodes / {len(graph['edges'])} edges", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["plan", "prepare", "apply", "validate", "export"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--execution-sha256")
    parser.add_argument("--rollback-test", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "plan":
        plan_files(args.root)
    elif args.mode == "prepare":
        require(args.backup_dir is not None, "Explicit backup directory required")
        prepare(args.root, args.backup_dir)
    elif args.mode == "apply":
        apply(args.root, args.execution_sha256, args.rollback_test)
    elif args.mode == "validate":
        validate(args.root)
    else:
        export(args.root, args.output or args.root / "data/lineage")


if __name__ == "__main__":
    main()
