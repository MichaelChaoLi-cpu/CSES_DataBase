#!/usr/bin/env python3
"""Transactional publication of exactly five approved additive age views."""
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
from cses_lineage_graph import GraphBuilder, _node_id
from organize_cses_questionnaires import digest, write_once
from plan_cses_age_topcode import (
    COMMENTS,
    DIRECTORY,
    EXTRAS,
    REVIEW_SHA,
    RULE_VIEW,
    SCHEMA,
    TARGETS,
    VERSION,
    checked_review,
    database_preflight,
    local_plan,
    local_projection,
    require,
    statistics,
)
from psycopg import sql

SELF = "rsc/cses_db/publish_cses_age_topcode.py"
PLAN_SHA = "cfcf46ba2e2f060782bf7e5c4a7f885fc310bf856e614049e1fdd7fdd1b6b48a"
RELEASE_DIR = f"data/releases/{VERSION}"
VIEWS = [v[0] for v in TARGETS.values()] + [RULE_VIEW]
GRAPH = "data/lineage/cses_lineage_graph_v10.json"


def read_only(conn):
    conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    conn.execute("SET LOCAL statement_timeout='55s'")
    require(conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on", "Read-only required")


def plan_checked(root):
    require(digest((root / DIRECTORY / "plan.json").read_bytes()) == PLAN_SHA, "Approved plan changed")
    plan = json.loads((root / DIRECTORY / "plan.json").read_text())
    require(local_plan(root, checked_review(root)) == plan, "Approved implementation/evidence changed")
    require(set(plan["queries"]) == set(VIEWS), "Exactly five approved targets required")
    return plan


def views(conn):
    return conn.execute("""SELECT c.relname,c.oid::bigint,c.relkind,c.relowner::bigint,c.relacl::text,c.reloptions,
      pg_get_viewdef(c.oid,true) AS definition,obj_description(c.oid,'pg_class') AS comment,
      a.attnum,a.attname,format_type(a.atttypid,a.atttypmod) AS type,col_description(c.oid,a.attnum) AS column_comment
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
      WHERE n.nspname=%s AND c.relname=ANY(%s) ORDER BY c.relname,a.attnum""", (SCHEMA, VIEWS)).fetchall()


def absent(conn):
    found = conn.execute("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=ANY(%s)", (SCHEMA, VIEWS)).fetchall()
    require(not found, "Target exists; never replace or retry an uncertain commit blindly")
    require(not conn.execute("SELECT 1 FROM pg_event_trigger WHERE evtenabled<>'D'").fetchone(), "Active DDL event trigger")


def protected(conn):
    relations = conn.execute("""SELECT n.nspname AS schema_name,c.relname AS table_name,c.oid::bigint,c.relowner::bigint,c.relacl::text
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('cses_meta','cses_alignment','cses_data','cses_analysis') AND c.relkind='r'
      ORDER BY n.nspname,c.relname""").fetchall()
    require(len(relations) == 35, "Protected CSES physical-table scope changed")
    for r in relations:
        r.update(conn.execute(sql.SQL("""SELECT count(*) AS rows, encode(sha256(convert_to(
          coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') AS sha256 FROM
          (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS h FROM {} t) hashed""")
          .format(sql.Identifier(r["schema_name"], r["table_name"]))).fetchone())
    structure = conn.execute("""SELECT n.nspname,c.relname,c.relkind,c.oid::bigint,c.relowner::bigint,c.relacl::text,c.reloptions,
      obj_description(c.oid,'pg_class') AS comment,a.attnum,a.attname,a.attnotnull,
      format_type(a.atttypid,a.atttypmod) AS type,col_description(c.oid,a.attnum) AS column_comment,
      CASE WHEN c.relkind='v' THEN pg_get_viewdef(c.oid,true) END AS definition
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
      WHERE (n.nspname IN ('cses_meta','cses_alignment','cses_data','cses_analysis') OR
        (n.nspname='public' AND c.relname IN (SELECT table_name FROM cses_meta.cses_storage_table)))
      AND c.relkind IN ('r','v','m') AND NOT (n.nspname=%s AND c.relname=ANY(%s))
      ORDER BY n.nspname,c.relname,a.attnum""", (SCHEMA, VIEWS)).fetchall()
    return {"physical_relations": relations, "structure_sha256": canonical_sha256(structure)}


def checks(conn, root, plan):
    result = {}
    for table, (view, age, key) in TARGETS.items():
        expected = local_projection(root, table)
        projection = ["survey_wave", key, age, *EXTRAS]
        rows = conn.execute(sql.SQL("SELECT {} FROM {} ORDER BY survey_wave, {}").format(
            sql.SQL(',').join(map(sql.Identifier, projection)), sql.Identifier(SCHEMA, view), sql.Identifier(key))).fetchall()
        actual = pd.DataFrame.from_records(rows, columns=projection)
        for column in projection:
            actual[column] = actual[column].astype(expected[column].dtype)
        pd.testing.assert_frame_equal(actual, expected.sort_values(["survey_wave", key]).reset_index(drop=True), check_exact=True)
        result[table] = statistics(actual, age)
        # Verify every original column/row against the physical base, preserving duplicates if any.
        columns = conn.execute("SELECT attname FROM pg_attribute WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped ORDER BY attnum", (f'cses_data."{table}"',)).fetchall()
        column_sql = sql.SQL(',').join(sql.Identifier(c["attname"]) for c in columns)
        mismatch = conn.execute(sql.SQL("""WITH b AS (SELECT {cols} FROM {base}), v AS (SELECT {cols} FROM {view})
          SELECT EXISTS((SELECT * FROM b EXCEPT ALL SELECT * FROM v) UNION ALL
                        (SELECT * FROM v EXCEPT ALL SELECT * FROM b)) AS mismatch""").format(
            cols=column_sql, base=sql.Identifier("cses_data", table), view=sql.Identifier(SCHEMA, view))).fetchone()
        require(not mismatch["mismatch"], "Original columns/rows changed by interface")
    rules = conn.execute(sql.SQL("SELECT * FROM {} ORDER BY target_table").format(sql.Identifier(SCHEMA, RULE_VIEW))).fetchall()
    require(rules == sorted(plan["prospective_rule_records"], key=lambda r: r["target_table"]), "Evidence rule mismatch")
    require(result == plan["local_statistics"], "Published statistics differ from approved plan")
    conn.execute("SET LOCAL ROLE mda_readonly")
    try:
        counts = {view: conn.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(SCHEMA, view))).fetchone()["n"] for view in VIEWS}
    finally:
        conn.execute("RESET ROLE")
    require(counts == {**{view: plan["local_statistics"][table]["rows"] for table, (view, _, _) in TARGETS.items()}, RULE_VIEW: 4}, "Reader access/count mismatch")
    return {"statistics": result, "reader_counts": counts, "all_original_columns_equal": True, "rule_rows": 4}


def execution(root):
    path = root / RELEASE_DIR / "execution.json"
    manifest = json.loads(path.read_text())
    require(manifest["plan_sha256"] == PLAN_SHA and manifest["views"] == VIEWS, "Wrong execution scope")
    for path_name, sha in manifest["file_sha256"].items():
        require(digest((root / path_name).read_bytes()) == sha, f"Execution input changed: {path_name}")
    return manifest, digest(path.read_bytes())


def prepare(root, backup_dir):
    require(not (root / RELEASE_DIR / "execution.json").exists(), "Preserve existing execution record")
    plan = plan_checked(root)
    database_preflight(root, plan)
    with connect_database({"dbname": "mda"}) as conn:
        read_only(conn)
        absent(conn)
        baseline = protected(conn)
        require(conn.execute("SELECT has_schema_privilege('mda_readonly','cses_analysis','USAGE') AS ok").fetchone()["ok"], "Reader schema access missing")
    print("Fresh preflight and 35-table fingerprints verified", flush=True)
    require(backup_dir.is_dir(), "Existing external backup directory required")
    fd, filename = tempfile.mkstemp(prefix="mda_cses_age_2004_analysis_", suffix=".dump", dir=backup_dir)
    os.close(fd)
    os.chmod(filename, 0o600)
    subprocess.run(["pg_dump", "-d", "mda", "--format=custom", "--schema-only", "--schema=cses_analysis", f"--file={filename}"], check=True, timeout=55)
    subprocess.run(["pg_restore", "--file=/dev/null", filename], check=True, timeout=55)
    paths = [SELF, "rsc/cses_db/plan_cses_age_topcode.py", "rsc/cses_db/organize_cses_questionnaires.py",
             "rsc/cses_db/cses_lineage_graph.py", "rsc/cses_db/cses_baseline_metadata.py", GRAPH,
             DIRECTORY + "/plan.json"]
    manifest = {"release_id": VERSION, "plan_sha256": PLAN_SHA, "views": VIEWS,
        "approval": "User explicitly approved publication of these five additive views, comments and reader grants.",
        "file_sha256": {p: digest((root / p).read_bytes()) for p in paths}, "protected_before": baseline,
        "backup": {"path": filename, "sha256": digest(Path(filename).read_bytes()), "full_decompression_verified": True,
                   "scope": "cses_analysis schema definitions only; no respondent data; additive views have no prior contents"},
        "git_base_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "new_code_git_archived": False, "database_mutated": False}
    write_once(root / RELEASE_DIR / "execution.json", manifest)
    print("execution_sha256=" + digest((root / RELEASE_DIR / "execution.json").read_bytes()), flush=True)


def apply(root, confirmation, rollback_test=False):
    plan = plan_checked(root)
    manifest, sha = execution(root)
    require(confirmation == sha, "Literal verified execution hash required")
    require(digest(Path(manifest["backup"]["path"]).read_bytes()) == manifest["backup"]["sha256"], "Backup changed")
    require(not (root / RELEASE_DIR / "import.json").exists(), "Publication already recorded; validate instead")
    with connect_database({"dbname": "mda"}) as conn:
        conn.execute("SET LOCAL statement_timeout='55s'")
        conn.execute("SET LOCAL lock_timeout='15s'")
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (VERSION,))
        absent(conn)
        for r in manifest["protected_before"]["physical_relations"]:
            conn.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(sql.Identifier(r["schema_name"], r["table_name"])))
        require(protected(conn) == manifest["protected_before"], "Protected database state changed since preflight")
        print("Protected-state recheck passed; creating five views in one transaction", flush=True)
        for name in VIEWS:
            conn.execute(sql.SQL("CREATE VIEW {} WITH (security_barrier=true) AS {}").format(sql.Identifier(SCHEMA, name), sql.SQL(plan["queries"][name])))
            comment = f"{VERSION}; execution SHA256 {sha}; review SHA256 {REVIEW_SHA}; 2004 only; original ages unchanged. Evidence in {SCHEMA}.{RULE_VIEW}."
            conn.execute(sql.SQL("COMMENT ON VIEW {} IS {}").format(sql.Identifier(SCHEMA, name), sql.Literal(comment)))
            if name != RULE_VIEW:
                for column, description in COMMENTS.items():
                    conn.execute(sql.SQL("COMMENT ON COLUMN {} IS {}").format(sql.Identifier(SCHEMA, name, column), sql.Literal(description)))
            conn.execute(sql.SQL("GRANT SELECT ON {} TO mda_readonly").format(sql.Identifier(SCHEMA, name)))
        results = checks(conn, root, plan)
        require(protected(conn) == manifest["protected_before"], "Protected state changed after view creation")
        records = views(conn)
        if rollback_test:
            conn.rollback()
            print("Rollback rehearsal completed; no views committed", flush=True)
        else:
            conn.commit()
    if rollback_test:
        with connect_database({"dbname": "mda"}) as conn:
            read_only(conn)
            absent(conn)
            require(protected(conn) == manifest["protected_before"], "Rollback did not restore pre-existing state")
        write_once(root / RELEASE_DIR / "rollback_test.json", {"execution_sha256": sha, "five_views_rolled_back": True, "protected_state_unchanged": True})
    else:
        write_once(root / RELEASE_DIR / "import.json", {"execution_sha256": sha, "created_views": records,
            "checks": results, "database_mutated": True, "physical_data_mutated": False,
            "protected_before_after_equal": True})
        print("Published five views; original data and historical interfaces unchanged", flush=True)


def validate(root):
    plan = plan_checked(root)
    manifest, sha = execution(root)
    imported = json.loads((root / RELEASE_DIR / "import.json").read_text())
    require(imported["execution_sha256"] == sha, "Import execution mismatch")
    with connect_database({"dbname": "mda"}) as conn:
        read_only(conn)
        require(views(conn) == imported["created_views"], "Published definitions, comments or permissions changed")
        require(protected(conn) == manifest["protected_before"], "Protected data/structure changed")
        result = checks(conn, root, plan)
        require(result == imported["checks"], "Independent results differ")
    report = {"validation_passed": True, "execution_sha256": sha,
              "import_sha256": digest((root / RELEASE_DIR / "import.json").read_bytes()),
              "checks": result, "protected_existing_tables": 35, "transaction_read_only": True, "database_mutated": False}
    write_once(root / RELEASE_DIR / "validation.json", report)
    print("Independent validation passed", flush=True)


def export(root, output):
    manifest, sha = execution(root)
    imported = json.loads((root / RELEASE_DIR / "import.json").read_text())
    validation = json.loads((root / RELEASE_DIR / "validation.json").read_text())
    require(validation["validation_passed"] and validation["execution_sha256"] == sha, "Independent validation required")
    with connect_database({"dbname": "mda"}) as conn:
        read_only(conn)
        require(views(conn) == imported["created_views"], "View state changed before graph export")
        dependencies = conn.execute("""SELECT DISTINCT v.relname AS view_name,n.nspname AS source_schema,c.relname AS source_relation
          FROM pg_class v JOIN pg_namespace vn ON vn.oid=v.relnamespace
          JOIN pg_rewrite r ON r.ev_class=v.oid JOIN pg_depend d ON d.objid=r.oid AND d.classid='pg_rewrite'::regclass
          JOIN pg_class c ON c.oid=d.refobjid AND d.refclassid='pg_class'::regclass JOIN pg_namespace n ON n.oid=c.relnamespace
          WHERE vn.nspname=%s AND v.relname=ANY(%s) AND c.oid<>v.oid ORDER BY 1,2,3""", (SCHEMA, VIEWS)).fetchall()
    require({(r["view_name"], r["source_schema"], r["source_relation"]) for r in dependencies} ==
            {(v[0], "cses_data", t) for t, v in TARGETS.items()}, "Unexpected database view dependencies")
    prior = json.loads((root / GRAPH).read_text())
    builder = GraphBuilder()
    for n in prior["nodes"]:
        builder.add_node(n["id"], n["type"], **n["properties"])
    for e in prior["edges"]:
        builder.add_edge(e["type"], e["source"], e["target"], **e["properties"])
    for name in VIEWS:
        node = _node_id("analysis_view", SCHEMA, name)
        builder.add_node(node, "analysis_view", schema=SCHEMA, name=name, interface_release=VERSION, execution_sha256=sha)
        builder.add_edge("schema_exposes_analysis_view", _node_id("schema", SCHEMA), node)
    for d in dependencies:
        candidates = [n for n in prior["nodes"] if n["type"] == "storage_table" and n["properties"].get("table_schema") == d["source_schema"] and n["properties"].get("table_name") == d["source_relation"]]
        require(len(candidates) == 1, "Base physical table graph node not unique")
        builder.add_edge("relation_feeds_analysis_view", candidates[0]["id"], _node_id("analysis_view", SCHEMA, d["view_name"]))
        builder.add_edge("documented_rule_qualifies_view", _node_id("analysis_view", SCHEMA, RULE_VIEW),
                         _node_id("analysis_view", SCHEMA, d["view_name"]), basis="logical evidence, not a SQL join")
    result = copy.deepcopy(prior)
    result["nodes"], result["edges"] = builder.finish()
    result["source"]["age_topcode_extension"] = {"execution_sha256": sha, "previous_graph_sha256": manifest["file_sha256"][GRAPH], "implementation_sha256": digest((root / SELF).read_bytes())}
    result["summary"].update(node_count=len(result["nodes"]), edge_count=len(result["edges"]),
        node_type_counts=dict(sorted(Counter(n["type"] for n in result["nodes"]).items())),
        edge_type_counts=dict(sorted(Counter(e["type"] for e in result["edges"]).items())))
    write_once(output / "cses_lineage_graph_v11.json", result)
    write_once(output / "cses_age_topcode_topology_v1.json", {"views": VIEWS, "dependencies": dependencies,
        "logical_rule_edges": 4, "summary": result["summary"], "transaction_read_only": True, "database_mutated": False})
    print(f"Graph v11 exported: {len(result['nodes'])} nodes, {len(result['edges'])} edges", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "apply", "validate", "export"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--execution-sha256")
    parser.add_argument("--rollback-test", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        require(args.backup_dir is not None, "Explicit external backup directory required")
        prepare(args.root, args.backup_dir)
    elif args.mode == "apply":
        apply(args.root, args.execution_sha256, args.rollback_test)
    elif args.mode == "validate":
        validate(args.root)
    else:
        export(args.root, args.output or args.root / "data/lineage")


if __name__ == "__main__":
    main()
