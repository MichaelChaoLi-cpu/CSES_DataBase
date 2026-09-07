#!/usr/bin/env python3
"""Publish the approved 30-record ED correction as a versioned additive interface."""
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
from cses_hh_hl_common import snake_case
from cses_lineage_graph import GraphBuilder, _node_id
from organize_cses_questionnaires import digest, write_once
from plan_cses_age_topcode import checked_review, qualify, require
from psycopg import sql
from publish_cses_age_topcode import protected as age_protected
from publish_cses_age_topcode import read_only
from review_cses_education import normalize_legacy_source_paths

SELF = "rsc/cses_db/publish_cses_education_correction.py"
VERSION = "cses-education-current-postgraduate-v1"
DIRECTORY = "data/processing/cses/education_corrected_v1"
RELEASE = f"data/releases/{VERSION}"
REVIEW = "data/processing/cses/education_review_v1/review.json"
REVIEW_SHA = "84a0b5a99c9f7daa0b2a73baab4429d4e3b5f7477a8a66034a5683c6018a1916"
GRAPH = "data/lineage/cses_lineage_graph_v11.json"
GRAPH_SHA = "d5531f4fa4eaabfc06049d2ac449a0817fe8e7860b3333a878be5617fbdec677"
VIEW = "cses_ed_aligned_v1"
RULE = "cses_ed_current_level_rule_v1"
VIEWS = [VIEW, RULE]
FIELD = "current_education_level_harmonized"
EXTRAS = ["current_level_before_correction", "current_level_correction_version", "current_level_evidence_status"]
COUNTS = {"2013": 6, "2014": 18, "2016": 6}


def correction_mask(frame):
    return (frame.survey_wave.isin(COUNTS) & frame.current_education_level_source_code.eq(21)
            & frame.currently_attending_school.eq(1) & frame[FIELD].eq(7)).fillna(False)


def corrected(frame):
    result = frame.copy()
    mask = correction_mask(frame)
    result[EXTRAS[0]] = frame[FIELD]
    result[FIELD] = result[FIELD].mask(mask, 6)
    result[EXTRAS[1]] = pd.Series(pd.NA, index=frame.index, dtype="string").mask(mask, VERSION)
    status = pd.Series("unchanged_not_newly_certified", index=frame.index, dtype="string")
    status.loc[frame.survey_wave.eq("2017") & frame.current_education_level_source_code.eq(21).fillna(False)] = "unresolved_2017_no_household_form"
    status.loc[mask] = "corrected_source_questionnaire"
    status.loc[mask & frame.survey_wave.eq("2014")] = "corrected_user_approved_2014_draft"
    result[EXTRAS[2]] = status
    return result


def source_plan(root):
    checked_review(root)
    require(digest((root / REVIEW).read_bytes()) == REVIEW_SHA, "Accepted education review changed")
    review = json.loads((root / REVIEW).read_text())
    for file, key in [("rsc/cses_db/review_cses_education.py", "implementation_sha256"),
                      ("rsc/specs/cses_education_review_v1.json", "spec_sha256"),
                      ("rsc/cses_db/cses_education.py", "education_builder_sha256")]:
        require(digest((root / file).read_bytes()) == review[key], "Accepted education implementation changed")
    require(digest((root / GRAPH).read_bytes()) == GRAPH_SHA, "Prior graph changed")
    original = pd.read_parquet(root / "data/processing/cses/final_ED_CSES.parquet").rename(columns=snake_case)
    frame = qualify(original, "age")
    mask = correction_mask(frame)
    require(frame.loc[mask].groupby("survey_wave").size().to_dict() == COUNTS, "Exact 30-row scope changed")
    after = corrected(frame)
    require(len(after) == 343204 and len(after.columns) == 37, "Wrong corrected interface grain")
    preserved = after[list(frame.columns)].copy()
    preserved[FIELD] = after[EXTRAS[0]]
    pd.testing.assert_frame_equal(preserved, frame, check_exact=True)
    rules = []
    for wave in COUNTS:
        q = next(r for r in review["questions"] if r["survey_wave"] == wave and r["canonical_field"] == "current_education_level_source_code")
        option = next(o for o in q["options"] if o["source_code"] == 21)
        require(option["label_as_printed"] == "Postgraduate studies", "Source meaning changed")
        rules.append({"survey_wave": wave, "source_code": 21, "old_group": 7, "new_group": 6,
            "source_label": option["label_as_printed"], "source_file": q["source_file"], "source_sha256": q["source_sha256"],
            "source_sheet": q["source_sheet"], "source_cell": q["options_cell"], "source_variable_id": q["source_variable_id"],
            "documentation_status": q["documentation_status"], "release_id": VERSION, "review_sha256": REVIEW_SHA,
            "approval": "User requested correction after review of 30 rows, including 18 supported by the 2014 draft; 2017 excluded."})
    condition = "b.survey_wave IN ('2013','2014','2016') AND b.current_education_level_source_code=21 AND b.currently_attending_school=1 AND b.current_education_level_harmonized=7"
    expressions = [sql.SQL(f"CASE WHEN {condition} THEN 6::smallint ELSE b.current_education_level_harmonized END AS current_education_level_harmonized")
                   if c == FIELD else sql.Identifier("b", c) for c in frame.columns]
    expressions += [sql.SQL("b.current_education_level_harmonized AS current_level_before_correction"),
        sql.SQL("CASE WHEN {} THEN {}::text ELSE NULL::text END AS current_level_correction_version").format(sql.SQL(condition), sql.Literal(VERSION)),
        sql.SQL("CASE WHEN ({c}) AND b.survey_wave='2014' THEN 'corrected_user_approved_2014_draft' WHEN {c} THEN 'corrected_source_questionnaire' WHEN b.survey_wave='2017' AND b.current_education_level_source_code=21 THEN 'unresolved_2017_no_household_form' ELSE 'unchanged_not_newly_certified' END::text AS current_level_evidence_status").format(c=sql.SQL(condition))]
    query = sql.SQL("SELECT {} FROM cses_analysis.cses_ed_age_v1 b").format(sql.SQL(",").join(expressions)).as_string()
    rule_query = sql.SQL("SELECT * FROM jsonb_to_recordset({}::jsonb) AS r(survey_wave text,source_code integer,old_group integer,new_group integer,source_label text,source_file text,source_sha256 text,source_sheet text,source_cell text,source_variable_id bigint,documentation_status text,release_id text,review_sha256 text,approval text)").format(sql.Literal(json.dumps(rules, ensure_ascii=False, sort_keys=True))).as_string()
    plan = {"release_id": VERSION, "review_sha256": REVIEW_SHA, "implementation_sha256": digest((root / SELF).read_bytes()),
        "queries": {VIEW: query, RULE: rule_query}, "rules": rules, "changed_counts": COUNTS,
        "target_keys_sha256": canonical_sha256(frame.loc[mask, ["survey_wave", "person_id", "source_row_id"]].to_dict("records")),
        "rows": len(after), "columns": list(after.columns), "physical_data_changes": 0, "corrected_view_cells": 30,
        "existing_interfaces_replaced": 0, "new_views": 2, "provisional_rows": 18, "unresolved_2017_rows": 8}
    return plan, after


def protected(conn):
    physical = age_protected(conn)["physical_relations"]
    structure = conn.execute("""SELECT n.nspname,c.relname,c.relkind,c.oid::bigint,c.relowner::bigint,c.relacl::text,c.reloptions,
      obj_description(c.oid,'pg_class') AS comment,a.attnum,a.attname,a.attnotnull,format_type(a.atttypid,a.atttypmod) AS type,
      col_description(c.oid,a.attnum) AS column_comment,CASE WHEN c.relkind='v' THEN pg_get_viewdef(c.oid,true) END AS definition
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
      WHERE (n.nspname IN ('cses_meta','cses_alignment','cses_data','cses_analysis') OR
        (n.nspname='public' AND c.relname IN (SELECT table_name FROM cses_meta.cses_storage_table)))
      AND c.relkind IN ('r','v','m') AND NOT (n.nspname='cses_analysis' AND c.relname=ANY(%s))
      ORDER BY n.nspname,c.relname,a.attnum""", (VIEWS,)).fetchall()
    return {"physical_relations": physical, "structure_sha256": canonical_sha256(structure)}


def views(conn):
    return conn.execute("""SELECT c.relname,c.oid::bigint,c.relowner::bigint,c.relacl::text,c.reloptions,
      pg_get_viewdef(c.oid,true) AS definition,obj_description(c.oid,'pg_class') AS comment,
      a.attnum,a.attname,format_type(a.atttypid,a.atttypmod) AS type,col_description(c.oid,a.attnum) AS column_comment
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
      WHERE n.nspname='cses_analysis' AND c.relname=ANY(%s) ORDER BY c.relname,a.attnum""", (VIEWS,)).fetchall()


def absent(conn):
    require(not views(conn), "Target already exists; inspect uncertain commits, never replace")
    require(not conn.execute("SELECT 1 FROM pg_event_trigger WHERE evtenabled<>'D'").fetchone(), "Active DDL trigger")


def checks(conn, expected, plan, published):
    query = f"SELECT * FROM cses_analysis.{VIEW}" if published else plan["queries"][VIEW]
    live = pd.DataFrame(conn.execute(sql.SQL("SELECT * FROM ({}) v ORDER BY survey_wave,person_id").format(sql.SQL(query))).fetchall()).astype(expected.dtypes.to_dict())
    live.source_archive = normalize_legacy_source_paths(live.source_archive)
    pd.testing.assert_frame_equal(live, expected.sort_values(["survey_wave", "person_id"]).reset_index(drop=True), check_exact=True)
    query = f"SELECT * FROM cses_analysis.{RULE}" if published else plan["queries"][RULE]
    require(conn.execute(sql.SQL("SELECT * FROM ({}) r ORDER BY survey_wave").format(sql.SQL(query))).fetchall() == plan["rules"], "Rule records differ")
    if published:
        conn.execute("SET LOCAL ROLE mda_readonly")
        try:
            counts = {v: conn.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier("cses_analysis", v))).fetchone()["n"] for v in VIEWS}
        finally:
            conn.execute("RESET ROLE")
        require(counts == {VIEW: 343204, RULE: 3}, "Readonly reader access/count mismatch")
    return {"rows": len(live), "columns": len(live.columns), "changed_cells": 30, "changed_counts": COUNTS,
            "all_projected_cells_match": True, "known_archive_prefix_normalized_for_comparison_only": True,
            "age_qualification_preserved": True, "unresolved_2017_unchanged": 8}


def plan_files(root):
    plan, expected = source_plan(root)
    write_once(root / DIRECTORY / "plan.json", plan)
    payload = io.BytesIO()
    expected.to_parquet(payload, index=False)
    file = root / DIRECTORY / "final_ED_CSES.parquet"
    if file.exists():
        require(file.read_bytes() == payload.getvalue(), "Versioned corrected Parquet differs")
    else:
        file.write_bytes(payload.getvalue())
    return plan, expected


def prepare(root, backup_dir):
    require(not (root / RELEASE / "execution.json").exists(), "Preserve execution record")
    plan, expected = plan_files(root)
    with connect_database({"dbname": "mda"}) as conn:
        read_only(conn)
        absent(conn)
        result = checks(conn, expected, plan, False)
        baseline = protected(conn)
        require(conn.execute("SELECT has_schema_privilege('mda_readonly','cses_analysis','USAGE') AS ok").fetchone()["ok"], "Missing reader schema access")
    print("Preflight: exact 30 corrected cells; 35 physical tables protected", flush=True)
    require(backup_dir.is_dir(), "Existing explicit backup directory required")
    fd, name = tempfile.mkstemp(prefix="mda_cses_ed_correction_", suffix=".dump", dir=backup_dir)
    os.close(fd)
    os.chmod(name, 0o600)
    subprocess.run(["pg_dump", "-d", "mda", "--format=custom", "--schema-only", "--schema=cses_analysis", f"--file={name}"], check=True, timeout=55)
    subprocess.run(["pg_restore", "--file=/dev/null", name], check=True, timeout=55)
    paths = [SELF, REVIEW, GRAPH, DIRECTORY + "/plan.json", DIRECTORY + "/final_ED_CSES.parquet",
             "rsc/cses_db/publish_cses_age_topcode.py", "rsc/cses_db/plan_cses_age_topcode.py",
             "rsc/cses_db/review_cses_education.py", "rsc/cses_db/cses_lineage_graph.py"]
    manifest = {"release_id": VERSION, "approval": "User: 修正，然后就下一个; exact 30 reviewed rows, 2014 draft retained, 2017 excluded; additive corrected interface announced.",
        "file_sha256": {p: digest((root / p).read_bytes()) for p in paths}, "protected_before": baseline,
        "backup": {"path": name, "sha256": digest(Path(name).read_bytes()), "full_decompression_verified": True, "scope": "cses_analysis schema definitions; no respondent data"},
        "preflight": result, "git_base_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "git_dvc_archived": False, "database_mutated": False}
    write_once(root / RELEASE / "execution.json", manifest)
    print("execution_sha256=" + digest((root / RELEASE / "execution.json").read_bytes()), flush=True)


def execution(root):
    payload = (root / RELEASE / "execution.json").read_bytes()
    manifest = json.loads(payload)
    require(manifest["release_id"] == VERSION, "Wrong release")
    for p, sha in manifest["file_sha256"].items():
        require(digest((root / p).read_bytes()) == sha, f"Execution input changed: {p}")
    plan, expected = source_plan(root)
    require(plan == json.loads((root / DIRECTORY / "plan.json").read_text()), "Prepared plan changed")
    return manifest, digest(payload), plan, expected


def apply(root, confirmation, rollback_test):
    manifest, sha, plan, expected = execution(root)
    require(confirmation == sha, "Verified execution hash required")
    require(digest(Path(manifest["backup"]["path"]).read_bytes()) == manifest["backup"]["sha256"], "Backup changed")
    require(not (root / RELEASE / "import.json").exists(), "Already published; validate instead")
    if not rollback_test:
        rehearsal = json.loads((root / RELEASE / "rollback_test.json").read_text())
        require(rehearsal == {"execution_sha256": sha, "two_views_rolled_back": True, "protected_state_unchanged": True}, "Successful matching rollback rehearsal required")
    with connect_database({"dbname": "mda"}) as conn:
        conn.execute("SET LOCAL statement_timeout='55s'")
        conn.execute("SET LOCAL lock_timeout='15s'")
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (VERSION,))
        absent(conn)
        for r in manifest["protected_before"]["physical_relations"]:
            conn.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(sql.Identifier(r["schema_name"], r["table_name"])))
        require(protected(conn) == manifest["protected_before"], "Protected state changed since prepare")
        for view in VIEWS:
            conn.execute(sql.SQL("CREATE VIEW {} WITH (security_barrier=true) AS {}").format(sql.Identifier("cses_analysis", view), sql.SQL(plan["queries"][view])))
            comment = f"{VERSION}; execution {sha}; 30 corrected view values, original physical tables unchanged; 2014 draft qualification retained; 2017 excluded."
            conn.execute(sql.SQL("COMMENT ON VIEW {} IS {}").format(sql.Identifier("cses_analysis", view), sql.Literal(comment)))
            conn.execute(sql.SQL("GRANT SELECT ON {} TO mda_readonly").format(sql.Identifier("cses_analysis", view)))
        for field, text in {FIELD: "Current-level grouping corrected from 7=Other to 6=Higher education for approved 2013/2014/2016 source code 21 only. Highest-completed grouping unchanged.",
            EXTRAS[0]: "Original inherited current-level grouping before this correction, for every row.",
            EXTRAS[1]: "Correction release on the 30 changed rows; NULL otherwise, not a global semantic approval.",
            EXTRAS[2]: "Source-questionnaire, user-approved 2014 draft, unresolved 2017 or unchanged/not-newly-certified status."}.items():
            conn.execute(sql.SQL("COMMENT ON COLUMN {} IS {}").format(sql.Identifier("cses_analysis", VIEW, field), sql.Literal(text)))
        result = checks(conn, expected, plan, True)
        require(protected(conn) == manifest["protected_before"], "Pre-existing data or interfaces changed")
        definitions = views(conn)
        if rollback_test:
            conn.rollback()
        else:
            conn.commit()
    if rollback_test:
        with connect_database({"dbname": "mda"}) as conn:
            read_only(conn)
            absent(conn)
            require(protected(conn) == manifest["protected_before"], "Rollback state mismatch")
        write_once(root / RELEASE / "rollback_test.json", {"execution_sha256": sha, "two_views_rolled_back": True, "protected_state_unchanged": True})
        print("Rollback rehearsal passed", flush=True)
    else:
        write_once(root / RELEASE / "import.json", {"execution_sha256": sha, "views": definitions, "checks": result,
            "database_mutated": True, "physical_data_mutated": False})
        print("Published corrected ED interface and three evidence rules", flush=True)


def validate(root):
    manifest, sha, plan, expected = execution(root)
    imported = json.loads((root / RELEASE / "import.json").read_text())
    require(imported["execution_sha256"] == sha, "Import execution mismatch")
    with connect_database({"dbname": "mda"}) as conn:
        read_only(conn)
        require(views(conn) == imported["views"], "Published interface changed")
        require(protected(conn) == manifest["protected_before"], "Protected state changed")
        result = checks(conn, expected, plan, True)
        require(result == imported["checks"], "Independent validation differs")
    write_once(root / RELEASE / "validation.json", {"execution_sha256": sha, "checks": result,
        "validation_passed": True, "transaction_read_only": True, "database_mutated": False})
    print("Independent ED correction validation passed", flush=True)


def export(root, output):
    manifest, sha, _, _ = execution(root)
    validation = json.loads((root / RELEASE / "validation.json").read_text())
    require(validation["validation_passed"] and validation["execution_sha256"] == sha, "Independent validation required")
    with connect_database({"dbname": "mda"}) as conn:
        read_only(conn)
        require(views(conn) == json.loads((root / RELEASE / "import.json").read_text())["views"], "Interface changed before export")
        dependencies = conn.execute("""SELECT DISTINCT v.relname AS view_name,n.nspname AS source_schema,c.relname AS source_relation
          FROM pg_class v JOIN pg_namespace vn ON vn.oid=v.relnamespace JOIN pg_rewrite r ON r.ev_class=v.oid
          JOIN pg_depend d ON d.objid=r.oid AND d.classid='pg_rewrite'::regclass JOIN pg_class c ON c.oid=d.refobjid AND d.refclassid='pg_class'::regclass
          JOIN pg_namespace n ON n.oid=c.relnamespace WHERE vn.nspname='cses_analysis' AND v.relname=ANY(%s) AND c.oid<>v.oid ORDER BY 1,2,3""", (VIEWS,)).fetchall()
    require(dependencies == [{"view_name": VIEW, "source_schema": "cses_analysis", "source_relation": "cses_ed_age_v1"}], "Unexpected dependency")
    prior = json.loads((root / GRAPH).read_text())
    builder = GraphBuilder()
    for n in prior["nodes"]:
        builder.add_node(n["id"], n["type"], **n["properties"])
    for e in prior["edges"]:
        builder.add_edge(e["type"], e["source"], e["target"], **e["properties"])
    for name in VIEWS:
        node = _node_id("analysis_view", "cses_analysis", name)
        builder.add_node(node, "analysis_view", schema="cses_analysis", name=name, interface_release=VERSION, execution_sha256=sha)
        builder.add_edge("schema_exposes_analysis_view", _node_id("schema", "cses_analysis"), node)
    builder.add_edge("relation_feeds_analysis_view", _node_id("analysis_view", "cses_analysis", "cses_ed_age_v1"), _node_id("analysis_view", "cses_analysis", VIEW))
    builder.add_edge("documented_rule_corrects_view", _node_id("analysis_view", "cses_analysis", RULE), _node_id("analysis_view", "cses_analysis", VIEW), corrected_rows=30, draft_rows=18)
    result = copy.deepcopy(prior)
    result["nodes"], result["edges"] = builder.finish()
    result["source"]["education_correction_extension"] = {"execution_sha256": sha, "previous_graph_sha256": manifest["file_sha256"][GRAPH]}
    result["summary"].update(node_count=len(result["nodes"]), edge_count=len(result["edges"]),
        node_type_counts=dict(sorted(Counter(n["type"] for n in result["nodes"]).items())),
        edge_type_counts=dict(sorted(Counter(e["type"] for e in result["edges"]).items())))
    write_once(output / "cses_lineage_graph_v12.json", result)
    write_once(output / "cses_education_correction_topology_v1.json", {"dependencies": dependencies, "summary": result["summary"], "execution_sha256": sha})
    print(f"Graph v12: {len(result['nodes'])} nodes / {len(result['edges'])} edges", flush=True)


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
