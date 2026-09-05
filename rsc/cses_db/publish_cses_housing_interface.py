#!/usr/bin/env python3
"""Prepare, publish and validate two additive, version-selected housing views."""

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
from correct_cses_housing_lighting import compare_database_to_local, write_json
from cses_baseline_metadata import canonical_sha256, connect_database, sha256_file
from cses_hh_hl_common import snake_case
from cses_lineage_graph import GraphBuilder, _node_id, build_lineage_graph, read_lineage_snapshot
from psycopg import sql
from publish_cses_value_mappings import (
    DIRECTORY as DICTIONARY_DIRECTORY,
)
from publish_cses_value_mappings import (
    RELEASE as DICTIONARY_RELEASE,
)
from publish_cses_value_mappings import (
    existing_records,
    expected_records,
    inputs,
    protected_snapshot,
    read_only,
)
from record_cses_value_mapping_decisions import require

RELEASE = "cses-housing-interface-v1"
DIRECTORY = f"data/releases/{RELEASE}"
VIEWS = ("cses_housing_value_dictionary_v1", "cses_housing_categories_v1")
FIELDS = {"tenure": "dwelling_tenure_source_code", "cooking_fuel": "main_cooking_fuel_source_code",
          "lighting": "main_lighting_source_code"}
SUFFIXES = ("category", "label", "match_status", "variable_mapping_id", "evidence")
EXTRAS = ["housing_dictionary_version"] + [f"{p}_{s}" for p in FIELDS for s in SUFFIXES]
SCHEMA = "cses_analysis"
SELF = "rsc/cses_db/publish_cses_housing_interface.py"
INVENTORY = "data/processing/cses/readiness_inventory_v1/inventory.json"
INVENTORY_SHA = "d5290547cb0c352d4cbde9122744a7f910814a69c6321ccfe50108319ce2f1d0"


def source_archive(path):
    # Comparison only: preserve the inherited database path in every output row.
    return "data/raw/" + path[len("data/raw/CSE/"):] if path.startswith("data/raw/CSE/") else path


def source_member(key):
    return "::".join(v for v in (key["member_path"], key["nested_member_path"]) if v)


def normalized_code(value):
    if pd.isna(value):
        return None
    return str(int(value)) if float(value).is_integer() else str(value)


def row_evidence(row, notes):
    return {"review_row_id": row["review_row_id"], "source_key": row["source_key"],
            "source_evidence": row["evidence"], "questionnaire_option": row["questionnaire_option"],
            "historical_flags": row["historical_flags"], "review_reasons": row["review_reasons"],
            "interpretation_notes": notes, "semantic_status": "approved_with_retained_qualifications"}


def approved_payload(plan):
    identities = {}
    for item in plan["database_plan"]["planned_variable_mappings"]:
        mapping = item["planned_mapping"]
        for value in item["value_mappings"]:
            identities[value["review_row_id"]] = mapping
    result = []
    for row in plan["approved_rows"]:
        m = identities[row["review_row_id"]]
        result.append({"dataset_id": m["dataset_id"], "canonical_variable_id": m["canonical_variable_id"],
                       "source_value": row["source_code"], "evidence": row_evidence(row, plan["interpretation_notes"])})
    require(len(result) == 140 and len({(r["dataset_id"], r["canonical_variable_id"], r["source_value"])
                                     for r in result}) == 140, "Approved dictionary keys must be unique")
    return result


def dictionary_query(plan):
    return sql.SQL("""WITH accepted AS (
      SELECT * FROM jsonb_to_recordset({payload}::jsonb)
        AS e(dataset_id bigint, canonical_variable_id bigint, source_value text, evidence jsonb)
    )
    SELECT s.survey_wave, c.canonical_name, a.relative_path AS source_archive,
           concat_ws('::', nullif(d.member_path,''), nullif(d.nested_member_path,'')) AS source_submodule,
           m.dataset_id, m.canonical_variable_id, m.variable_mapping_id,
           r.mapping_version AS dictionary_version, v.source_value, v.source_label,
           v.canonical_value AS category, v.canonical_label AS label, e.evidence
    FROM accepted e
    JOIN cses_alignment.cses_variable_mapping m
      ON m.dataset_id=e.dataset_id AND m.canonical_variable_id=e.canonical_variable_id
    JOIN cses_meta.cses_alignment_release r USING(alignment_release_id)
    JOIN cses_alignment.cses_value_mapping v ON v.variable_mapping_id=m.variable_mapping_id AND v.source_value=e.source_value
    JOIN cses_alignment.cses_canonical_variable c ON c.canonical_variable_id=m.canonical_variable_id
    JOIN cses_meta.cses_dataset d ON d.dataset_id=m.dataset_id
    JOIN cses_meta.cses_survey s ON s.survey_id=d.survey_id
    JOIN cses_meta.cses_source_archive a ON a.source_archive_id=d.source_archive_id
    WHERE r.mapping_version={release} AND r.status='approved' AND m.alignment_status='approved'
      AND v.alignment_status='approved' AND c.target_table='final_HO_CSES'
    """).format(payload=sql.Literal(json.dumps(approved_payload(plan), ensure_ascii=False, sort_keys=True)),
                 release=sql.Literal(DICTIONARY_RELEASE))


def category_query(dictionary):
    columns = [sql.SQL("h.*"), sql.SQL("{}::text AS housing_dictionary_version").format(sql.Literal(DICTIONARY_RELEASE))]
    joins = []
    for prefix, field in FIELDS.items():
        alias = sql.Identifier(prefix)
        for attribute in ("category", "label", "variable_mapping_id", "evidence"):
            columns.append(sql.SQL("{}.{} AS {}").format(alias, sql.Identifier(attribute), sql.Identifier(f"{prefix}_{attribute}")))
        columns.append(sql.SQL("CASE WHEN h.{} IS NULL THEN 'source_null' WHEN {}.variable_mapping_id IS NULL "
            "THEN 'unmapped_nonnull' ELSE 'matched' END::text AS {}").format(
                sql.Identifier(field), alias, sql.Identifier(f"{prefix}_match_status")))
        joins.append(sql.SQL("LEFT JOIN dictionary {alias} ON {alias}.survey_wave=h.survey_wave "
            "AND {alias}.canonical_name={field} AND {alias}.source_value=h.{column}::text "
            "AND {alias}.source_archive=regexp_replace(h.source_archive,'^data/raw/CSE/','data/raw/') "
            "AND {alias}.source_submodule=h.source_submodule").format(alias=alias, field=sql.Literal(field), column=sql.Identifier(field)))
    return sql.SQL("WITH dictionary AS ({}) SELECT {} FROM cses_data.\"final_HO_CSES\" h {}").format(
        dictionary, sql.SQL(", ").join(columns), sql.SQL(" ").join(joins))


def baseline(connection, correction):
    state = protected_snapshot(connection, correction)[0]
    # Mirror the accepted structural projection, excluding ONLY the two newly authorized views.
    structure = connection.execute("""
      SELECT n.nspname, c.relname, c.relkind, c.oid::bigint, c.relowner::bigint, c.relacl::text,
             a.attnum, a.attname, format_type(a.atttypid,a.atttypmod) AS type, a.attnotnull,
             col_description(c.oid,a.attnum) AS comment,
             CASE WHEN c.relkind='v' THEN pg_get_viewdef(c.oid,true) END AS view_definition
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
      WHERE (n.nspname IN ('cses_meta','cses_alignment','cses_data','cses_analysis')
        OR (n.nspname='public' AND c.relname IN (SELECT table_name FROM cses_meta.cses_storage_table)))
        AND c.relkind IN ('r','v') AND NOT (n.nspname=%s AND c.relname=ANY(%s))
      ORDER BY n.nspname,c.relname,a.attnum
    """, (SCHEMA, list(VIEWS))).fetchall()
    state["structure_sha256"] = canonical_sha256(structure)
    return state


def context(root):
    plan, execution, execution_hash, correction = inputs(root, root / DICTIONARY_DIRECTORY)
    require(sha256_file(root / INVENTORY) == INVENTORY_SHA, "Accepted inventory changed")
    return plan, execution, expected_records(plan, execution, execution_hash), correction


def check_base(connection, expected, correction, desired, root):
    require(existing_records(connection) == desired, "Existing dictionary release changed")
    require(baseline(connection, correction) == expected, "Protected pre-existing database state changed")
    compare_database_to_local(connection, correction, root / "data/processing/cses/final_HO_CSES.parquet")


def expected_index(plan):
    index = {}
    for row in plan["approved_rows"]:
        k = row["source_key"]
        key = (row["survey_wave"], k["archive_relative_path"], source_member(k), row["canonical_name"], row["source_code"])
        require(key not in index, "Ambiguous source-code meaning")
        index[key] = row
    return index


def expected_match(index, wave, archive, member, field, code):
    key = normalized_code(code)
    if key is None:
        return "source_null", None, None
    row = index.get((wave, source_archive(archive), member, field, key))
    if row is None:
        return "unmapped_nonnull", None, None
    return "matched", row["approved_canonical_value"], row["approved_canonical_label"]


def query_checks(connection, dictionary, categories, plan, root):
    expected = expected_index(plan)
    entries = connection.execute(sql.SQL("SELECT * FROM ({}) q ORDER BY dataset_id,canonical_variable_id,source_value").format(dictionary)).fetchall()
    require(len(entries) == 140, "Dictionary row count differs")
    actual_keys = set()
    for row in entries:
        key = (row["survey_wave"], row["source_archive"], row["source_submodule"], row["canonical_name"], row["source_value"])
        require(key not in actual_keys and key in expected, "Duplicated/unapproved dictionary key")
        actual_keys.add(key)
        approved = expected[key]
        require((row["category"], row["label"], row["source_label"]) == (
            approved["approved_canonical_value"], approved["approved_canonical_label"], approved["source_label"] or None), "Dictionary value differs")
        require(row["dictionary_version"] == DICTIONARY_RELEASE and
                row["evidence"] == row_evidence(approved, plan["interpretation_notes"]), "Dictionary qualifications differ")
    require(actual_keys == set(expected), "Missing approved dictionary entry")
    dictionary_ids = {(r["survey_wave"], r["source_archive"], r["source_submodule"], r["canonical_name"], r["source_value"]):
                      r["variable_mapping_id"] for r in entries}
    checks = connection.execute(sql.SQL("WITH q AS ({}) SELECT count(*) AS rows, "
        "count(*)-count(DISTINCT (survey_wave,household_id)) AS duplicate_keys, "
        "count(*) FILTER (WHERE survey_wave IS NULL OR household_id IS NULL) AS null_keys, "
        "count(*) FILTER (WHERE hh_link_matched=0) AS hh_unmatched FROM q").format(categories)).fetchone()
    require(checks == {"rows": 77922, "duplicate_keys": 0, "null_keys": 0, "hh_unmatched": 19}, "Housing cardinality/linkage differs")
    differences = connection.execute(sql.SQL("WITH q AS ({}) SELECT count(*) AS n FROM q "
        "FULL JOIN cses_data.\"final_HO_CSES\" h USING(survey_wave,household_id) "
        "WHERE (to_jsonb(q)-{}::text[]) IS DISTINCT FROM to_jsonb(h)").format(categories, sql.Literal(EXTRAS))).fetchone()["n"]
    require(differences == 0, "An original housing value changed or row disappeared")
    local = pd.read_parquet(root / "data/processing/cses/final_HO_CSES.parquet").rename(columns=snake_case)
    local_keys = set(zip(local.survey_wave, local.household_id, strict=True))
    summaries = []
    for prefix, field in FIELDS.items():
        columns = ["survey_wave", "household_id", "source_archive", "source_submodule", field,
                   f"{prefix}_category", f"{prefix}_label", f"{prefix}_match_status", f"{prefix}_variable_mapping_id"]
        rows = connection.execute(sql.SQL("SELECT {} FROM ({}) q").format(
            sql.SQL(",").join(map(sql.Identifier, columns)), categories)).fetchall()
        require({(r["survey_wave"], r["household_id"]) for r in rows} == local_keys, "Housing identities differ")
        counts = Counter()
        for row in rows:
            expected_values = expected_match(expected, row["survey_wave"], row["source_archive"], row["source_submodule"], field, row[field])
            require((row[f"{prefix}_match_status"], row[f"{prefix}_category"], row[f"{prefix}_label"]) == expected_values,
                    f"Per-record category/status differs: {field}")
            key = (row["survey_wave"], source_archive(row["source_archive"]), row["source_submodule"], field, normalized_code(row[field]))
            require(row[f"{prefix}_variable_mapping_id"] == dictionary_ids.get(key), "Wrong dictionary rule provenance")
            counts[(row["survey_wave"], expected_values[0])] += 1
        # Validate evidence references separately without transferring repeated JSON for every household.
        condition = sql.SQL("SELECT count(*) AS n FROM ({cat}) q LEFT JOIN ({dic}) d ON d.variable_mapping_id=q.{mid} "
            "AND d.source_value=q.{field}::text WHERE q.{evidence} IS DISTINCT FROM d.evidence").format(
                cat=categories, dic=dictionary, mid=sql.Identifier(f"{prefix}_variable_mapping_id"),
                field=sql.Identifier(field), evidence=sql.Identifier(f"{prefix}_evidence"))
        require(connection.execute(condition).fetchone()["n"] == 0, "Wrong per-row evidence")
        summaries += [{"field": field, "survey_wave": wave, "match_status": status, "rows": count}
                      for (wave, status), count in sorted(counts.items())]
    return {**checks, "original_column_count": 50, "output_column_count": 66,
            "original_values_unchanged": True, "per_record_categories_validated": True,
            "dictionary_entries": len(entries), "dictionary_sha256": canonical_sha256(entries), "coverage": summaries}


def view_records(connection):
    records = []
    for name in VIEWS:
        record = connection.execute("SELECT c.oid::bigint,c.relkind,c.relowner::bigint,c.relacl::text,c.reloptions, "
            "pg_get_viewdef(c.oid,true) AS definition,obj_description(c.oid) AS comment "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=%s",
            (SCHEMA, name)).fetchone()
        if record:
            require(record["relkind"] == "v", "Target is not an ordinary view")
            records.append({"name": name, **record})
    return records


def checked_execution(root):
    path = root / DIRECTORY / "execution.json"
    manifest = json.loads(path.read_text())
    require(manifest["release_id"] == RELEASE and manifest["views"] == list(VIEWS), "Wrong interface execution manifest")
    for name, digest in manifest["implementation_sha256"].items():
        require(sha256_file(root / name) == digest, f"Interface implementation changed: {name}")
    return manifest, sha256_file(path)


def prepare(root, backup_dir):
    directory = root / DIRECTORY
    require(not (directory / "execution.json").exists(), "Execution already prepared; preserve its evidence")
    plan, execution, desired, correction = context(root)
    dic = dictionary_query(plan)
    cat = category_query(dic)
    with connect_database({"dbname": "mda"}) as connection:
        read_only(connection)
        require(not view_records(connection), "New view names must be absent")
        require(not connection.execute("SELECT 1 FROM pg_event_trigger WHERE evtenabled <> 'D'").fetchone(), "Unexpected DDL event trigger")
        check_base(connection, execution["protected_before"], correction, desired, root)
        print("protected_baseline_passed=True; checking prospective views", flush=True)
        checks = query_checks(connection, dic, cat, plan, root)
        require(connection.execute("SELECT has_schema_privilege('mda_readonly','cses_analysis','USAGE') AS ok").fetchone()["ok"], "Reader schema access absent")
        query_hashes = {"dictionary": canonical_sha256(dic.as_string(connection)), "categories": canonical_sha256(cat.as_string(connection))}
    require(backup_dir.is_dir(), "Existing external backup directory required")
    fd, filename = tempfile.mkstemp(prefix="mda_cses_housing_interface_v1_", suffix=".dump", dir=backup_dir)
    os.close(fd)
    os.chmod(filename, 0o600)
    subprocess.run(["pg_dump", "-d", "mda", "--format=custom", "--schema-only", "--schema=cses_analysis", f"--file={filename}"], check=True)
    subprocess.run(["pg_restore", "--file=/dev/null", filename], check=True)
    backup = {"path": filename, "sha256": sha256_file(Path(filename)), "scope": "cses_analysis schema definitions only; no data; additive views have no prior contents",
              "full_decompression_verified": True}
    paths = set(execution["implementation_sha256"]) | {SELF, INVENTORY}
    manifest = {"release_id": RELEASE, "views": list(VIEWS), "database_mutated": False,
        "authorized_actions": "Create exactly two absent analysis views, comments and SELECT grants to existing mda_readonly; no table DML, replacement or schema creation",
        "implementation_sha256": {p: sha256_file(root / p) for p in sorted(paths)}, "query_sha256": query_hashes,
        "dictionary_execution_sha256": sha256_file(root / DICTIONARY_DIRECTORY / "execution.json"),
        "protected_before": execution["protected_before"], "preflight": checks, "backup": backup,
        "code_base_git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "code_provenance": "Exact file hashes; new interface code is not yet Git-archived", "targets_absent": True}
    write_json(directory / "execution.json", manifest)
    print(f"preflight_passed=True execution_sha256={sha256_file(directory / 'execution.json')}", flush=True)


def live_queries():
    return tuple(sql.SQL("SELECT * FROM {}.{}").format(sql.Identifier(SCHEMA), sql.Identifier(n)) for n in VIEWS)


def apply(root, confirmation):
    manifest, digest = checked_execution(root)
    require(confirmation == digest, "Literal execution hash required")
    require(sha256_file(Path(manifest["backup"]["path"])) == manifest["backup"]["sha256"], "Backup changed")
    plan, execution, desired, correction = context(root)
    dic = dictionary_query(plan)
    cat = category_query(sql.SQL("SELECT * FROM {}.{}").format(sql.Identifier(SCHEMA), sql.Identifier(VIEWS[0])))
    with connect_database({"dbname": "mda"}) as connection:
        connection.execute("SET LOCAL statement_timeout='55s'")
        connection.execute("SET LOCAL lock_timeout='15s'")
        connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (RELEASE,))
        require(not view_records(connection), "Refusing to replace an existing view; use validate for completed publication")
        require(not connection.execute("SELECT 1 FROM pg_event_trigger WHERE evtenabled <> 'D'").fetchone(), "Unexpected DDL event trigger")
        for item in manifest["protected_before"]["protected_relations"]:
            connection.execute(sql.SQL("LOCK TABLE {}.{} IN SHARE ROW EXCLUSIVE MODE").format(
                sql.Identifier(item["schema_name"]), sql.Identifier(item["table_name"])))
        check_base(connection, manifest["protected_before"], correction, desired, root)
        print("protected_baseline_passed=True; creating two views", flush=True)
        for name, query in zip(VIEWS, (dic, cat), strict=True):
            connection.execute(sql.SQL("CREATE VIEW {}.{} WITH (security_barrier=true) AS {}").format(
                sql.Identifier(SCHEMA), sql.Identifier(name), query))
            connection.execute(sql.SQL("COMMENT ON VIEW {}.{} IS {}").format(sql.Identifier(SCHEMA), sql.Identifier(name),
                sql.Literal(f"{RELEASE}; execution SHA-256 {digest}; dictionary {DICTIONARY_RELEASE}; preserves source codes and qualifications; no analytical denominator implied.")))
            connection.execute(sql.SQL("GRANT SELECT ON {}.{} TO mda_readonly").format(sql.Identifier(SCHEMA), sql.Identifier(name)))
        checks = query_checks(connection, *live_queries(), plan, root)
        require(checks == manifest["preflight"], "Published interface differs from preflight")
        check_base(connection, manifest["protected_before"], correction, desired, root)
        records = view_records(connection)
        connection.execute("SET LOCAL ROLE mda_readonly")
        reader = [connection.execute(sql.SQL("SELECT count(*) AS n FROM {}.{}").format(sql.Identifier(SCHEMA), sql.Identifier(name))).fetchone()["n"] for name in VIEWS]
        require(reader == [140, 77922], "Reader counts differ")
        connection.execute("RESET ROLE")
    write_json(root / DIRECTORY / "import.json", {"release_id": RELEASE, "execution_sha256": digest,
        "database_mutated": True, "created_views": records, "checks": checks, "reader_counts": reader,
        "protected_before_after_equal": True, "table_data_mutated": False})
    print("published=True new_views=2 physical_data_mutated=False", flush=True)


def validate(root):
    manifest, digest = checked_execution(root)
    plan, execution, desired, correction = context(root)
    imported = json.loads((root / DIRECTORY / "import.json").read_text())
    require(imported["execution_sha256"] == digest, "Import execution binding differs")
    with connect_database({"dbname": "mda"}) as connection:
        read_only(connection)
        require(view_records(connection) == imported["created_views"], "View definition/identity/permissions changed")
        check_base(connection, manifest["protected_before"], correction, desired, root)
        checks = query_checks(connection, *live_queries(), plan, root)
        require(checks == manifest["preflight"] == imported["checks"], "Independent interface validation differs")
        connection.execute("SET LOCAL ROLE mda_readonly")
        reader = [connection.execute(sql.SQL("SELECT count(*) AS n FROM {}.{}").format(sql.Identifier(SCHEMA), sql.Identifier(name))).fetchone()["n"] for name in VIEWS]
        require(reader == [140, 77922], "Reader access differs")
    write_json(root / DIRECTORY / "validation.json", {"release_id": RELEASE, "execution_sha256": digest,
        "import_sha256": sha256_file(root / DIRECTORY / "import.json"), "validation_passed": True,
        "transaction_read_only": True, "database_mutated": False, "protected_existing_tables": 35,
        "checks": checks, "reader_counts": reader})
    print("validation_passed=True database_mutated=False", flush=True)


def export(root, output_dir):
    manifest, digest = checked_execution(root)
    imported = json.loads((root / DIRECTORY / "import.json").read_text())
    with connect_database({"dbname": "mda"}) as connection:
        read_only(connection)
        require(view_records(connection) == imported["created_views"], "View state changed before export")
        prior = json.loads((root / "data/lineage/cses_lineage_graph_v6.json").read_text())
        graph = build_lineage_graph(read_lineage_snapshot(connection), prior["source"]["exporter_code_git_revision"])
        require(graph == prior, "Base catalog graph changed")
        dependencies = connection.execute("""SELECT DISTINCT v.relname AS view_name,n.nspname AS source_schema,c.relname AS source_relation
          FROM pg_class v JOIN pg_namespace vn ON vn.oid=v.relnamespace
          JOIN pg_rewrite r ON r.ev_class=v.oid JOIN pg_depend d ON d.objid=r.oid AND d.classid='pg_rewrite'::regclass
          JOIN pg_class c ON c.oid=d.refobjid AND d.refclassid='pg_class'::regclass JOIN pg_namespace n ON n.oid=c.relnamespace
          WHERE vn.nspname=%s AND v.relname=ANY(%s) AND c.oid<>v.oid ORDER BY 1,2,3""", (SCHEMA, list(VIEWS))).fetchall()
    builder = GraphBuilder()
    for node in graph["nodes"]:
        builder.add_node(node["id"], node["type"], **node["properties"])
    for edge in graph["edges"]:
        builder.add_edge(edge["type"], edge["source"], edge["target"], **edge["properties"])
    for name in VIEWS:
        builder.add_node(_node_id("analysis_view", SCHEMA, name), "analysis_view", schema=SCHEMA, name=name,
                         interface_release=RELEASE, execution_sha256=digest)
        builder.add_edge("schema_exposes_analysis_view", _node_id("schema", SCHEMA), _node_id("analysis_view", SCHEMA, name))
    for item in dependencies:
        schema, name = item["source_schema"], item["source_relation"]
        if name in VIEWS and schema == SCHEMA:
            origin = _node_id("analysis_view", schema, name)
        else:
            matching = [n for n in graph["nodes"] if n["type"] == "storage_table" and
                        n["properties"].get("table_schema") == schema and n["properties"].get("table_name") == name]
            if matching:
                origin = matching[0]["id"]
            else:
                origin = _node_id("metadata_relation", schema, name)
                builder.add_node(origin, "metadata_relation", table_schema=schema, table_name=name)
                builder.add_edge("schema_contains_metadata_relation", _node_id("schema", schema), origin)
        builder.add_edge("relation_feeds_analysis_view", origin, _node_id("analysis_view", SCHEMA, item["view_name"]))
    result = copy.deepcopy(graph)
    result["nodes"], result["edges"] = builder.finish()
    result["source"]["housing_interface_extension"] = {"release_id": RELEASE, "execution_sha256": digest,
        "implementation_sha256": sha256_file(root / SELF), "dependencies_verified": True}
    result["summary"].update(node_count=len(result["nodes"]), edge_count=len(result["edges"]),
        node_type_counts=dict(sorted(Counter(n["type"] for n in result["nodes"]).items())),
        edge_type_counts=dict(sorted(Counter(e["type"] for e in result["edges"]).items())))
    write_json(output_dir / "cses_lineage_graph_v7.json", result)
    overview = {"interface_views": list(VIEWS), "dependencies": dependencies, "summary": result["summary"],
                "database_mutated": False, "transaction_read_only": True}
    write_json(output_dir / "cses_housing_interface_topology_v1.json", overview)
    print(f"graph_exported=True nodes={len(result['nodes'])} edges={len(result['edges'])}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "apply", "validate", "export"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--execution-sha256")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.mode == "prepare":
        require(args.backup_dir is not None, "Explicit backup directory required")
        prepare(root, args.backup_dir)
    elif args.mode == "apply":
        require(args.apply and args.execution_sha256, "Apply flag and literal hash required")
        apply(root, args.execution_sha256)
    elif args.mode == "validate":
        validate(root)
    else:
        export(root, (root / args.output_dir) if args.output_dir else root / "data/lineage")


if __name__ == "__main__":
    main()
