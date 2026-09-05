#!/usr/bin/env python3
"""Publish the user-approved 2016-to-2017 housing dictionary transfer additively."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

import pandas as pd
from correct_cses_housing_lighting import database_snapshot, write_json
from cses_baseline_metadata import canonical_sha256, connect_database, sha256_file
from cses_hh_hl_common import snake_case
from cses_lineage_graph import GraphBuilder, _node_id, build_lineage_graph, read_lineage_snapshot
from inventory_cses_archives import DataSource
from psycopg import sql
from publish_cses_housing_interface import FIELDS, category_query, normalized_code, source_archive
from publish_cses_value_mappings import TABLES, frozen_plan, insert_records, read_only
from record_cses_value_mapping_decisions import require

RELEASE = "cses-housing-2017-from-2016-v1"
DIRECTORY = f"data/releases/{RELEASE}"
SPEC = "rsc/specs/cses_housing_2017_from_2016_v1.json"
SELF = "rsc/cses_db/publish_cses_housing_2017.py"
VIEWS = ("cses_housing_value_dictionary_v2", "cses_housing_categories_v2")
HO = "data/processing/cses/final_HO_CSES.parquet"
HO_SHA = "e0dae1a43267250b22fd8e18070b4a9243cd8f451fd40511ac4f7666e4b4826d"
REVIEW = "data/processing/cses/value_mapping_review_v1/review.json"
REVIEW_SHA = "aec4d1184e3675ec30b69e79291c41c5838edebc9be45d42f3b0e1bc68fdd81f"
COUNTS = {"alignment_releases": 1, "variable_mappings": 3, "value_mappings": 21, "load_runs": 1}


def check_structure(reference, target):
    ref = [c.lower() for c in reference]
    other = [c.lower() for c in target]
    require(len(ref) == len(set(ref)) == 32 and ref == other,
            "2016/2017 raw columns must match in order, ignoring case only")
    return ref


def check_codes(observed, options):
    require(set(observed) <= set(options), "Target contains a code absent from the 2016 dictionary")


def local_plan(root):
    spec = json.loads((root / SPEC).read_text())
    require(spec["release_id"] == RELEASE and spec["reference_wave"] == "2016"
            and spec["target_wave"] == "2017" and spec["new_views"] == list(VIEWS)
            and spec["fields"] == list(FIELDS.values()), "Transfer scope changed")
    require(sha256_file(root / HO) == HO_SHA and sha256_file(root / REVIEW) == REVIEW_SHA,
            "Pinned housing/review changed")
    approved = frozen_plan(root)
    review = json.loads((root / REVIEW).read_text())
    frames, sources = {}, {}
    for wave in ("2016", "2017"):
        p = next(p for p in review["profiles"] if p["survey_wave"] == wave)
        archive_sha = next(r["evidence"]["archive_sha256"] for r in review["code_rows"]
                           if r["survey_wave"] == wave)
        require(sha256_file(root / p["archive_relative_path"]) == archive_sha, "Raw archive changed")
        chain = tuple(v for v in (p["member_path"], p["nested_member_path"]) if v)
        payload = DataSource(root / p["archive_relative_path"], chain).read_bytes()
        require(hashlib.sha256(payload).hexdigest() == p["member_sha256"], "Raw member changed")
        with pd.io.stata.StataReader(io.BytesIO(payload), convert_categoricals=False) as reader:
            require(not reader.value_labels(), "Unexpected source labels need a new review")
            frames[wave] = reader.read()
        sources[wave] = {"archive": p["archive_relative_path"], "archive_sha256": archive_sha,
                         "member_chain": list(chain), "member_sha256": p["member_sha256"]}
    columns = check_structure(frames["2016"].columns, frames["2017"].columns)
    require(len(frames["2017"]) == spec["expected_target_rows"] == 3840, "Target row count changed")
    local = pd.read_parquet(root / HO).rename(columns=snake_case)
    target = local.loc[local.survey_wave.eq("2017")].reset_index(drop=True)
    row_ids = target.source_row_id.str.rsplit(":", n=1).str[-1].astype(int)
    require(sorted(row_ids) == list(range(1, 3841)), "Raw-to-local rows not bijective")
    require(target.source_archive.map(source_archive).eq(sources["2017"]["archive"]).all()
            and target.source_submodule.eq("::".join(sources["2017"]["member_chain"])).all(),
            "Local source identity differs")
    raw = frames["2017"].iloc[row_ids.to_numpy() - 1].reset_index(drop=True)
    rows, coverage = [], []
    for field in FIELDS.values():
        p = next(p for p in review["profiles"] if p["survey_wave"] == "2017" and p["canonical_name"] == field)
        pd.testing.assert_series_equal(raw[p["source_variable"]].astype("Float64"),
                                       target[field].astype("Float64"), check_names=False)
        selected = [r for r in approved["approved_rows"] if r["survey_wave"] == "2016"
                    and r["canonical_name"] == field]
        observed = {normalized_code(k): int(v) for k, v in target[field].value_counts().items()}
        check_codes(observed, [r["source_code"] for r in selected])
        nulls = int(target[field].isna().sum())
        require(nulls == spec["expected_target_nulls"][field], "Target null count changed")
        coverage.append({"field": field, "rows": 3840, "nonnull": 3840 - nulls,
                         "nulls": nulls, "observed_codes": observed})
        for r in selected:
            rows.append({"field": field, "source_variable": p["source_variable"],
                         "source_code": r["source_code"], "category": r["approved_canonical_value"],
                         "label": r["approved_canonical_label"], "source_label": None,
                         "observed_count": observed.get(r["source_code"], 0),
                         "evidence": {"approval_basis": spec["approval_basis"], "decision": spec["decision"],
                             "target_wave": "2017", "reference_wave": "2016",
                             "target_questionnaire_verified": False, "reference_review_row_id": r["review_row_id"],
                             "reference_evidence": r["evidence"], "reference_option": r["questionnaire_option"],
                             "reference_historical_flags": r["historical_flags"],
                             "policy": spec["policy"], "source_evidence": sources}})
    require(len(rows) == spec["expected_dictionary_entries"] == 21
            and sum(r["observed_count"] > 0 for r in rows) == spec["expected_observed_code_combinations"] == 16,
            "Dictionary scope changed")
    return {"release_id": RELEASE, "spec_sha256": sha256_file(root / SPEC), "rows": rows,
            "sources": sources, "ordered_columns_case_insensitive": columns, "coverage": coverage,
            "raw_codes_unchanged": True, "questionnaire_recovery_claimed": False}


def predecessors(connection):
    rows = connection.execute("""SELECT m.variable_mapping_id,m.dataset_id,m.canonical_variable_id,
      m.source_variable_names,m.source_kind,m.transformation_rule,m.alignment_status,r.mapping_version,
      c.canonical_name,a.relative_path,d.member_path,d.nested_member_path
      FROM cses_alignment.cses_variable_mapping m
      JOIN cses_meta.cses_alignment_release r USING(alignment_release_id)
      JOIN cses_alignment.cses_canonical_variable c USING(canonical_variable_id)
      JOIN cses_meta.cses_dataset d USING(dataset_id)
      JOIN cses_meta.cses_source_archive a USING(source_archive_id)
      JOIN cses_meta.cses_survey s ON s.survey_id=d.survey_id
      WHERE s.survey_wave='2017' AND c.target_table='final_HO_CSES' AND c.canonical_name=ANY(%s)
        AND r.mapping_version<>%s ORDER BY c.canonical_name""", (list(FIELDS.values()), RELEASE)).fetchall()
    require(len(rows) == 3 and all(r["mapping_version"] == "cses-variable-catalog-v1" for r in rows),
            "Unexpected predecessor mappings")
    return rows


def protected(connection, root):
    correction = json.loads((root / "rsc/specs/cses_housing_lighting_missing_v1.json").read_text())
    state = database_snapshot(connection, correction)
    require(len(state["protected_relations"]) == 35, "Protected physical table set changed")
    for item in state["protected_relations"]:
        schema, table = item["schema_name"], item["table_name"]
        if (schema, table) not in TABLES:
            continue
        if table == "cses_alignment_release":
            predicate = "t.mapping_version<>%s"
        elif table == "cses_value_mapping":
            predicate = "t.variable_mapping_id NOT IN (SELECT m.variable_mapping_id FROM cses_alignment.cses_variable_mapping m JOIN cses_meta.cses_alignment_release r USING(alignment_release_id) WHERE r.mapping_version=%s)"
        else:
            predicate = "t.alignment_release_id IS NULL OR t.alignment_release_id NOT IN (SELECT alignment_release_id FROM cses_meta.cses_alignment_release WHERE mapping_version=%s)"
        item.update(connection.execute(sql.SQL("SELECT count(*) AS row_count, encode(sha256(convert_to("
            "coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') AS sha256 FROM "
            "(SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS h FROM {} t WHERE {}) x")
            .format(sql.Identifier(schema, table), sql.SQL(predicate)), (RELEASE,)).fetchone())
    structure = connection.execute("""SELECT n.nspname,c.relname,c.relkind,c.oid::bigint,c.relowner::bigint,
      c.relacl::text,c.reloptions,obj_description(c.oid) AS relation_comment,a.attnum,a.attname,
      format_type(a.atttypid,a.atttypmod) AS type,a.attnotnull,col_description(c.oid,a.attnum) AS comment,
      CASE WHEN c.relkind='v' THEN pg_get_viewdef(c.oid,true) END AS view_definition
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
      WHERE (n.nspname IN ('cses_meta','cses_alignment','cses_data','cses_analysis') OR
        (n.nspname='public' AND c.relname IN (SELECT table_name FROM cses_meta.cses_storage_table)))
      AND c.relkind IN ('r','v') AND NOT(n.nspname='cses_analysis' AND c.relname=ANY(%s))
      ORDER BY n.nspname,c.relname,a.attnum""", (list(VIEWS),)).fetchall()
    state["structure_sha256"] = canonical_sha256(structure)
    return state


def dictionary_query(plan):
    payload = [{"field": r["field"], "source_code": r["source_code"], "evidence": r["evidence"]}
               for r in plan["rows"]]
    return sql.SQL("""SELECT * FROM cses_analysis.cses_housing_value_dictionary_v1 UNION ALL
      SELECT '2017'::text,c.canonical_name,a.relative_path,
        concat_ws('::',nullif(d.member_path,''),nullif(d.nested_member_path,'')),
        m.dataset_id,m.canonical_variable_id,m.variable_mapping_id,r.mapping_version,
        v.source_value,v.source_label,v.canonical_value,v.canonical_label,e.evidence
      FROM jsonb_to_recordset({payload}::jsonb) AS e(field text,source_code text,evidence jsonb)
      JOIN cses_alignment.cses_canonical_variable c ON c.canonical_name=e.field AND c.target_table='final_HO_CSES'
      JOIN cses_alignment.cses_variable_mapping m USING(canonical_variable_id)
      JOIN cses_meta.cses_alignment_release r USING(alignment_release_id)
      JOIN cses_alignment.cses_value_mapping v ON v.variable_mapping_id=m.variable_mapping_id AND v.source_value=e.source_code
      JOIN cses_meta.cses_dataset d USING(dataset_id)
      JOIN cses_meta.cses_survey s ON s.survey_id=d.survey_id
      JOIN cses_meta.cses_source_archive a USING(source_archive_id)
      WHERE r.mapping_version={release} AND s.survey_wave='2017' AND r.status='approved'
        AND m.alignment_status='approved' AND v.alignment_status='approved'"""
    ).format(payload=sql.Literal(json.dumps(payload, ensure_ascii=False, sort_keys=True)), release=sql.Literal(RELEASE))


def view_queries(plan):
    dictionary = dictionary_query(plan)
    # Reuse the exact v1 join and null rules; replace only the composite-interface version label.
    inner = category_query(sql.SQL("SELECT * FROM cses_analysis.{}").format(sql.Identifier(VIEWS[0])))
    text = inner.as_string().replace("'cses-housing-value-mapping-v1'::text AS housing_dictionary_version",
                                   "'cses-housing-interface-v2'::text AS housing_dictionary_version")
    require(text != inner.as_string(), "Expected version label not found")
    return dictionary, sql.SQL(text)


def desired(plan, manifest, digest):
    mappings, values = [], []
    for p in manifest["predecessors"]:
        fields = ("dataset_id", "canonical_variable_id", "source_variable_names", "source_kind")
        mappings.append({**{k: p[k] for k in fields}, "alignment_status": "approved",
                         "transformation_rule": p["transformation_rule"] + " " +
                         "User-approved transfer of the 2016 value dictionary to 2017; "
                         "case-insensitive ordered raw structure matched; no recovered 2017 questionnaire claimed."})
        for row in plan["rows"]:
            if row["field"] == p["canonical_name"]:
                values.append({"dataset_id": p["dataset_id"], "canonical_variable_id": p["canonical_variable_id"],
                               "source_value": row["source_code"], "source_label": None,
                               "canonical_value": row["category"], "canonical_label": row["label"],
                               "alignment_status": "approved"})
    return {"release": {"mapping_version": RELEASE, "status": "approved",
                        "description": "User-approved 2016-to-2017 housing dictionary transfer; 21 options, 3 rules; raw data unchanged.",
                        "specification_sha256": plan["spec_sha256"]},
            "mappings": sorted(mappings, key=canonical_sha256), "values": sorted(values, key=canonical_sha256),
            "run": {"run_scope": RELEASE, "source_manifest_sha256": canonical_sha256(plan),
                    "code_git_revision": None, "dvc_revision": None, "status": "loaded", "row_counts": COUNTS,
                    "validation_summary": {"execution_sha256": digest,
                        "implementation_sha256": manifest["implementation_sha256"],
                        "code_provenance": "Exact file hashes; publication implementation not yet Git/DVC archived",
                        "predecessors": manifest["predecessors"], "approval_basis": "user_approved_cross_wave_transfer",
                        "plan_sha256": canonical_sha256(plan), "backup": manifest["backup"],
                        "physical_data_unchanged": True, "target_questionnaire_verified": False}}}


def records(connection):
    r = connection.execute("SELECT alignment_release_id,mapping_version,status,description,specification_sha256::text "
                           "FROM cses_meta.cses_alignment_release WHERE mapping_version=%s", (RELEASE,)).fetchone()
    if r is None:
        return None
    identity = r.pop("alignment_release_id")
    mappings = connection.execute("SELECT dataset_id,canonical_variable_id,source_variable_names,source_kind,"
        "transformation_rule,alignment_status FROM cses_alignment.cses_variable_mapping WHERE alignment_release_id=%s",
        (identity,)).fetchall()
    values = connection.execute("SELECT m.dataset_id,m.canonical_variable_id,v.source_value,v.source_label,"
        "v.canonical_value,v.canonical_label,v.alignment_status FROM cses_alignment.cses_value_mapping v "
        "JOIN cses_alignment.cses_variable_mapping m USING(variable_mapping_id) WHERE m.alignment_release_id=%s",
        (identity,)).fetchall()
    runs = connection.execute("SELECT run_scope,source_manifest_sha256::text,code_git_revision,dvc_revision,status,"
        "row_counts,validation_summary,finished_at IS NOT NULL AS finished FROM cses_meta.cses_load_run "
        "WHERE alignment_release_id=%s", (identity,)).fetchall()
    require(len(runs) == 1 and runs[0].pop("finished"), "Exactly one finished load run required")
    require(connection.execute("SELECT approved_at IS NOT NULL AS ok FROM cses_meta.cses_alignment_release "
                               "WHERE alignment_release_id=%s", (identity,)).fetchone()["ok"], "Approval date absent")
    return {"release": r, "mappings": sorted(mappings, key=canonical_sha256),
            "values": sorted(values, key=canonical_sha256), "run": runs[0]}


def view_records(connection):
    return connection.execute("SELECT c.relname,c.oid::bigint,c.relkind,c.relowner::bigint,c.relacl::text,"
        "c.reloptions,pg_get_viewdef(c.oid,true) AS definition,obj_description(c.oid) AS comment "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='cses_analysis' AND c.relname=ANY(%s) ORDER BY c.relname", (list(VIEWS),)).fetchall()


def validate_views(connection, root, plan):
    dictionary = connection.execute("SELECT * FROM cses_analysis.cses_housing_value_dictionary_v2 "
                                    "ORDER BY survey_wave,canonical_name,source_value").fetchall()
    require(len(dictionary) == 161, "Expected 140 retained plus 21 new dictionary rows")
    transferred = [r for r in dictionary if r["survey_wave"] == "2017"]
    expected = {(r["field"], r["source_code"]): r for r in plan["rows"]}
    require(len(transferred) == 21 and {(r["canonical_name"], r["source_value"]) for r in transferred} == set(expected),
            "Transferred dictionary keys differ")
    for r in transferred:
        e = expected[r["canonical_name"], r["source_value"]]
        require((r["category"], r["label"], r["source_label"], r["evidence"], r["dictionary_version"]) ==
                (e["category"], e["label"], None, e["evidence"], RELEASE), "Transferred value or evidence changed")
    unchanged = connection.execute("""SELECT count(*) AS n FROM (
      (SELECT * FROM cses_analysis.cses_housing_value_dictionary_v2 WHERE survey_wave<>'2017'
       EXCEPT ALL SELECT * FROM cses_analysis.cses_housing_value_dictionary_v1)
      UNION ALL
      (SELECT * FROM cses_analysis.cses_housing_value_dictionary_v1 EXCEPT ALL
       SELECT * FROM cses_analysis.cses_housing_value_dictionary_v2 WHERE survey_wave<>'2017')) d""").fetchone()["n"]
    require(unchanged == 0, "Prior dictionary rows changed")
    rows = connection.execute("SELECT * FROM cses_analysis.cses_housing_categories_v2").fetchall()
    frame = pd.DataFrame(rows)
    require(len(frame) == 77922 and len(frame.columns) == 66
            and not frame.duplicated(["survey_wave", "household_id"]).any(), "Housing cardinality changed")
    local = pd.read_parquet(root / HO).rename(columns=snake_case)
    original = frame[list(local.columns)].copy()
    original.source_archive = original.source_archive.map(source_archive)
    for col in local:
        original[col] = original[col].astype(local[col].dtype)
    keys = ["survey_wave", "household_id"]
    pd.testing.assert_frame_equal(original.sort_values(keys).reset_index(drop=True),
                                  local.sort_values(keys).reset_index(drop=True), check_exact=True)
    index = {(r["survey_wave"], r["source_archive"], r["source_submodule"], r["canonical_name"], r["source_value"]): r
             for r in dictionary}
    require(len(index) == 161, "Duplicate dictionary key")
    coverage = []
    for prefix, field in FIELDS.items():
        counts = {"matched": 0, "source_null": 0, "unmapped_nonnull": 0}
        for r in rows:
            code = normalized_code(r[field])
            e = index.get((r["survey_wave"], source_archive(r["source_archive"]), r["source_submodule"], field, code))
            status = "source_null" if code is None else "matched" if e is not None else "unmapped_nonnull"
            require(r[f"{prefix}_match_status"] == status, "Match status differs")
            for attribute in ("category", "label", "variable_mapping_id", "evidence"):
                require(r[f"{prefix}_{attribute}"] == (e[attribute] if e else None), "Category/lineage differs")
            require(r["housing_dictionary_version"] == "cses-housing-interface-v2", "Interface version differs")
            if r["survey_wave"] == "2017":
                counts[status] += 1
        require(counts["unmapped_nonnull"] == 0, "Unmapped 2017 observed code")
        coverage.append({"field": field, **counts})
    require(int(frame.hh_link_matched.eq(0).sum()) == 19, "Housing orphan count changed")
    return {"dictionary_rows": 161, "housing_rows": 77922, "housing_columns": 66,
            "2017_coverage": coverage, "physical_values_unchanged": True,
            "prior_dictionary_unchanged": True, "dictionary_sha256": canonical_sha256(dictionary)}


def safety(connection):
    require(not connection.execute("SELECT 1 FROM pg_event_trigger WHERE evtenabled<>'D'").fetchone(), "Unexpected DDL trigger")
    for schema, table in TABLES:
        require(not connection.execute("SELECT 1 FROM pg_trigger WHERE tgrelid=%s::regclass AND NOT tgisinternal",
                                       (f'{schema}."{table}"',)).fetchone(), "Unexpected metadata trigger")


def prepare(root, backup_dir):
    directory = root / DIRECTORY
    require(not (directory / "execution.json").exists(), "Execution already frozen")
    plan = local_plan(root)
    from publish_cses_housing_interface import validate as validate_v1
    validate_v1(root)
    with connect_database({"dbname": "mda"}) as c:
        read_only(c)
        require(records(c) is None and not view_records(c), "New release/view names must be absent")
        safety(c)
        c.execute(sql.SQL("EXPLAIN {}").format(dictionary_query(plan))).fetchall()
        c.execute(sql.SQL("EXPLAIN {}").format(category_query(dictionary_query(plan)))).fetchall()
        before = protected(c, root)
        prior = predecessors(c)
        for p in prior:
            require(p["relative_path"] == plan["sources"]["2017"]["archive"]
                    and [p["member_path"]] == plan["sources"]["2017"]["member_chain"]
                    and not p["nested_member_path"], "Target dataset identity differs")
            require(p["source_variable_names"] == [next(r["source_variable"] for r in plan["rows"]
                                                       if r["field"] == p["canonical_name"])], "Source rule differs")
    require(backup_dir.is_dir(), "Existing external backup directory required")
    backups = []
    for scope in ("metadata", "analysis_schema"):
        fd, name = tempfile.mkstemp(prefix=f"mda_cses_2017_{scope}_", suffix=".dump", dir=backup_dir)
        os.close(fd)
        os.chmod(name, 0o600)
        args = ["pg_dump", "-d", "mda", "--format=custom", f"--file={name}"]
        args += ([f'--table={s}."{t}"' for s, t in TABLES] if scope == "metadata"
                 else ["--schema-only", "--schema=cses_analysis"])
        subprocess.run(args, check=True)
        toc = subprocess.check_output(["pg_restore", "--list", name], text=True)
        if scope == "metadata":
            require(all(f"TABLE DATA {s} {t} " in toc for s, t in TABLES), "Incomplete backup")
        subprocess.run(["pg_restore", "--file=/dev/null", name], check=True)
        backups.append({"path": name, "sha256": sha256_file(Path(name)), "scope": scope, "decompression_verified": True})
    paths = set(frozen_plan(root)["provenance"]["implementation_sha256"]) | {
        SELF, SPEC, HO, REVIEW, "rsc/cses_db/publish_cses_housing_interface.py",
        "rsc/cses_db/publish_cses_value_mappings.py", "rsc/cses_db/correct_cses_housing_lighting.py",
        "rsc/cses_db/cses_lineage_graph.py", "data/lineage/cses_lineage_graph_v7.json"}
    manifest = {"release_id": RELEASE, "plan": plan, "predecessors": prior, "protected_before": before,
                "backup": backups, "implementation_sha256": {p: sha256_file(root / p) for p in sorted(paths)},
                "authorized_record_counts": COUNTS, "views": list(VIEWS), "database_mutated": False}
    write_json(directory / "execution.json", manifest)
    print(f"execution_sha256={sha256_file(directory / 'execution.json')}", flush=True)


def checked(root):
    path = root / DIRECTORY / "execution.json"
    manifest = json.loads(path.read_text())
    require(manifest["release_id"] == RELEASE and manifest["views"] == list(VIEWS)
            and manifest["authorized_record_counts"] == COUNTS, "Execution scope differs")
    for p, digest in manifest["implementation_sha256"].items():
        require(sha256_file(root / p) == digest, f"Pinned file changed: {p}")
    require(local_plan(root) == manifest["plan"], "Source evidence changed")
    return manifest, sha256_file(path)


def apply(root, confirmation):
    manifest, digest = checked(root)
    require(confirmation == digest, "Explicit execution hash required")
    for b in manifest["backup"]:
        require(sha256_file(Path(b["path"])) == b["sha256"], "Backup changed")
    planned = desired(manifest["plan"], manifest, digest)
    with connect_database({"dbname": "mda"}) as c:
        c.execute("SET LOCAL statement_timeout='55s'")
        c.execute("SET LOCAL lock_timeout='15s'")
        c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (RELEASE,))
        for r in manifest["protected_before"]["protected_relations"]:
            c.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(sql.Identifier(r["schema_name"], r["table_name"])))
        safety(c)
        require(protected(c, root) == manifest["protected_before"], "Pre-existing database changed")
        require(predecessors(c) == manifest["predecessors"], "Predecessors changed")
        if records(c) is None:
            require(not view_records(c), "Refusing to replace existing views")
            insert_records(c, planned)
            for name, query in zip(VIEWS, view_queries(manifest["plan"]), strict=True):
                c.execute(sql.SQL("CREATE VIEW cses_analysis.{} WITH (security_barrier=true) AS {}").format(sql.Identifier(name), query))
                c.execute(sql.SQL("COMMENT ON VIEW cses_analysis.{} IS {}").format(sql.Identifier(name),
                    sql.Literal(f"{RELEASE}; execution {digest}; 2017 uses user-approved 2016 definitions; source data and v1 retained.")))
                c.execute(sql.SQL("GRANT SELECT ON cses_analysis.{} TO mda_readonly").format(sql.Identifier(name)))
        require(records(c) == planned, "Published metadata differs")
        checks = validate_views(c, root, manifest["plan"])
        require(protected(c, root) == manifest["protected_before"], "Pre-existing state changed during publication")
        views = view_records(c)
        require(len(views) == 2, "Expected two views")
        c.execute("SET LOCAL ROLE mda_readonly")
        require(c.execute("SELECT count(*) AS n FROM cses_analysis.cses_housing_categories_v2").fetchone()["n"] == 77922,
                "Reader access differs")
        c.execute("RESET ROLE")
    write_json(root / DIRECTORY / "import.json", {"release_id": RELEASE, "execution_sha256": digest,
               "checks": checks, "views": views, "database_mutated": True,
               "records_sha256": canonical_sha256(planned), "protected_existing_state_unchanged": True})
    print("published=True metadata_rows=26 new_views=2 physical_data_unchanged=True", flush=True)


def validate(root):
    manifest, digest = checked(root)
    imported = json.loads((root / DIRECTORY / "import.json").read_text())
    require(imported["execution_sha256"] == digest, "Import binding differs")
    with connect_database({"dbname": "mda"}) as c:
        read_only(c)
        require(records(c) == desired(manifest["plan"], manifest, digest), "Release records changed")
        require(view_records(c) == imported["views"], "View identities, definitions or privileges changed")
        require(protected(c, root) == manifest["protected_before"], "Pre-existing state changed")
        checks = validate_views(c, root, manifest["plan"])
        require(checks == imported["checks"], "Independent validation differs")
    write_json(root / DIRECTORY / "validation.json", {"release_id": RELEASE, "validation_passed": True,
               "execution_sha256": digest, "import_sha256": sha256_file(root / DIRECTORY / "import.json"),
               "transaction_read_only": True, "database_mutated": False, "checks": checks})
    print("validation_passed=True", flush=True)


def export(root):
    manifest, digest = checked(root)
    imported = json.loads((root / DIRECTORY / "import.json").read_text())
    validation = json.loads((root / DIRECTORY / "validation.json").read_text())
    require(validation["validation_passed"] and validation["execution_sha256"] == digest
            and validation["import_sha256"] == sha256_file(root / DIRECTORY / "import.json"),
            "Successful independent validation required before lineage export")
    prior = json.loads((root / "data/lineage/cses_lineage_graph_v7.json").read_text())
    with connect_database({"dbname": "mda"}) as c:
        read_only(c)
        require(records(c) == desired(manifest["plan"], manifest, digest)
                and view_records(c) == imported["views"], "Live release differs before export")
        graph = build_lineage_graph(read_lineage_snapshot(c), prior["source"]["exporter_code_git_revision"])
        dependencies = c.execute("""SELECT DISTINCT v.relname AS view_name,n.nspname AS source_schema,c.relname AS source_relation
          FROM pg_class v JOIN pg_namespace vn ON vn.oid=v.relnamespace
          JOIN pg_rewrite r ON r.ev_class=v.oid JOIN pg_depend d ON d.objid=r.oid AND d.classid='pg_rewrite'::regclass
          JOIN pg_class c ON c.oid=d.refobjid AND d.refclassid='pg_class'::regclass JOIN pg_namespace n ON n.oid=c.relnamespace
          WHERE vn.nspname='cses_analysis' AND v.relname=ANY(%s) AND c.oid<>v.oid ORDER BY 1,2,3""", (list(VIEWS),)).fetchall()
    builder = GraphBuilder()
    for n in graph["nodes"]:
        builder.add_node(n["id"], n["type"], **n["properties"])
    for e in graph["edges"]:
        builder.add_edge(e["type"], e["source"], e["target"], **e["properties"])
    for n in prior["nodes"]:
        if n["type"] in {"analysis_view", "metadata_relation"}:
            builder.add_node(n["id"], n["type"], **n["properties"])
    for e in prior["edges"]:
        if e["type"] in {"schema_exposes_analysis_view", "schema_contains_metadata_relation", "relation_feeds_analysis_view"}:
            builder.add_edge(e["type"], e["source"], e["target"], **e["properties"])
    for name in VIEWS:
        identity = _node_id("analysis_view", "cses_analysis", name)
        builder.add_node(identity, "analysis_view", schema="cses_analysis", name=name,
                         interface_release=RELEASE, execution_sha256=digest)
        builder.add_edge("schema_exposes_analysis_view", _node_id("schema", "cses_analysis"), identity)
    for d in dependencies:
        schema, name = d["source_schema"], d["source_relation"]
        if schema == "cses_analysis":
            origin = _node_id("analysis_view", schema, name)
        else:
            matches = [n for n in graph["nodes"] if n["type"] == "storage_table"
                       and n["properties"].get("table_schema") == schema and n["properties"].get("table_name") == name]
            if matches:
                origin = matches[0]["id"]
            else:
                origin = _node_id("metadata_relation", schema, name)
                builder.add_node(origin, "metadata_relation", table_schema=schema, table_name=name)
                builder.add_edge("schema_contains_metadata_relation", _node_id("schema", schema), origin)
        builder.add_edge("relation_feeds_analysis_view", origin, _node_id("analysis_view", "cses_analysis", d["view_name"]))
    builder.add_edge("dictionary_transferred_by_user_decision",
                     _node_id("alignment_release", "cses-housing-value-mapping-v1"),
                     _node_id("alignment_release", RELEASE), reference_wave="2016", target_wave="2017",
                     fields=list(FIELDS.values()), target_questionnaire_verified=False,
                     specification_sha256=manifest["plan"]["spec_sha256"])
    graph["nodes"], graph["edges"] = builder.finish()
    graph["summary"].update(node_count=len(graph["nodes"]), edge_count=len(graph["edges"]),
        node_type_counts=dict(sorted(Counter(n["type"] for n in graph["nodes"]).items())),
        edge_type_counts=dict(sorted(Counter(e["type"] for e in graph["edges"]).items())))
    graph["source"]["housing_2017_transfer"] = {"release_id": RELEASE, "execution_sha256": digest,
        "implementation_sha256": sha256_file(root / SELF), "prior_graph_sha256": sha256_file(root / "data/lineage/cses_lineage_graph_v7.json")}
    write_json(root / "data/lineage/cses_lineage_graph_v8.json", graph)
    write_json(root / "data/lineage/cses_housing_interface_topology_v2.json",
               {"release_id": RELEASE, "dependencies": dependencies, "summary": graph["summary"],
                "database_mutated": False, "transaction_read_only": True})
    print(f"graph_exported=True nodes={len(graph['nodes'])} edges={len(graph['edges'])}", flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("plan", "prepare", "apply", "validate", "export"))
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--backup-dir", type=Path)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--execution-sha256")
    args = p.parse_args()
    root = args.root.resolve()
    if args.mode == "plan":
        plan = local_plan(root)
        write_json(root / DIRECTORY / "plan.json", plan)
        print(json.dumps({"entries": len(plan["rows"]), "coverage": plan["coverage"]}))
    elif args.mode == "prepare":
        require(args.backup_dir is not None, "Explicit backup directory required")
        prepare(root, args.backup_dir)
    elif args.mode == "apply":
        require(args.apply and args.execution_sha256, "Explicit apply flag and hash required")
        apply(root, args.execution_sha256)
    elif args.mode == "validate":
        validate(root)
    else:
        export(root)


if __name__ == "__main__":
    main()
