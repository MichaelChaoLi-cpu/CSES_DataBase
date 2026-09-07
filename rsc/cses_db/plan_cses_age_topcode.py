#!/usr/bin/env python3
"""Prepare additive age-qualification queries. This program cannot publish DDL/DML."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from cses_baseline_metadata import canonical_sha256, connect_database
from cses_hh_hl_common import snake_case
from organize_cses_questionnaires import digest, encoded, write_once
from psycopg import sql

SELF = "rsc/cses_db/plan_cses_age_topcode.py"
REVIEW = "data/processing/cses/questionnaire_review_v1/review.json"
REVIEW_SHA = "5b2b46488f09504731bf87dcc22b6ba5a6a7993e7a0659ddd8a8c285f8b39eca"
DIRECTORY = "data/processing/cses/age_topcode_v1"
VERSION = "cses-age-2004-topcode-v1"
SCHEMA = "cses_analysis"
RULE_VIEW = "cses_age_2004_rule_v1"
TARGETS = {
    "final_HL_CSES": ("cses_hl_age_v1", "age", "person_id"),
    "final_ED_CSES": ("cses_ed_age_v1", "age", "person_id"),
    "final_EC_CSES": ("cses_ec_age_v1", "age", "person_id"),
    "final_HH_CSES": ("cses_hh_head_age_v1", "household_head_age", "household_id"),
}
EXTRAS = ["age_2004_is_topcoded", "age_2004_lower_bound", "age_2004_exact_years", "age_2004_status"]
COMMENTS = {
    "age_2004_is_topcoded": "2004 only: true means documented code 96 (age 96+); false means valid completed age 0-95. NULL for missing age or other waves. Not a global no-topcoding assertion.",
    "age_2004_lower_bound": "2004 only: lower bound in completed years; 96 for documented 96+. NULL for missing/out-of-scope/unexpected values. Not exact age when top-coded.",
    "age_2004_exact_years": "2004 only: exact reported completed years 0-95; NULL for 96+, missing age, other waves or unexpected codes. Filtering on this column alone excludes top-coded older people.",
    "age_2004_status": "outside_rule_scope, missing_age, topcoded_96_plus, reported_completed_years, or unexpected_2004_code. Do not interpret outside_rule_scope as evidence of no topcoding.",
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def checked_review(root):
    payload = (root / REVIEW).read_bytes()
    require(digest(payload) == REVIEW_SHA, "Accepted review changed")
    review = json.loads(payload)
    require(digest((root / "rsc/cses_db/review_cses_questionnaires.py").read_bytes()) == review["implementation_sha256"], "Review implementation changed")
    require(digest((root / "rsc/cses_db/cses_hh_hl_common.py").read_bytes()) == review["member_builder_sha256"], "Historical member builder changed")
    require(digest((root / "rsc/specs/cses_questionnaire_review_v1.json").read_bytes()) == review["spec_sha256"], "Review specification changed")
    for name, sha in review["input_sha256"].items():
        require(digest((root / "data/processing/cses/questionnaire_alignment_v1" / name).read_bytes()) == sha, f"Questionnaire baseline changed: {name}")
    inventory = json.loads((root / "data/processing/cses/questionnaire_alignment_v1/source_inventory.json").read_text())
    for path, sha in inventory["archive_sha256"].items():
        require(digest((root / path).read_bytes()) == sha, f"Raw archive changed: {path}")
    for table in review["age_impact"]["tables"]:
        require(digest((root / table["path"]).read_bytes()) == table["sha256"], f"Canonical Parquet changed: {table['table']}")
    return review


def qualify(frame, column):
    """Independent vectorized implementation; no cross-wave age rule is inferred."""
    age = frame[column]
    scope = frame["survey_wave"].eq("2004")
    valid = scope & age.between(0, 96).fillna(False) & age.mod(1).eq(0).fillna(False)
    top = valid & age.eq(96).fillna(False)
    result = frame.copy()
    result[EXTRAS[0]] = age.eq(96).astype("boolean").where(valid, pd.NA)
    result[EXTRAS[1]] = age.where(valid).astype("Int16")
    result[EXTRAS[2]] = age.where(valid & ~top).astype("Int16")
    status = pd.Series("outside_rule_scope", index=frame.index, dtype="string")
    status.loc[scope] = "unexpected_2004_code"
    status.loc[valid] = "reported_completed_years"
    status.loc[top] = "topcoded_96_plus"
    status.loc[scope & age.isna()] = "missing_age"
    result[EXTRAS[3]] = status
    return result


def age_query(table):
    require(table in TARGETS, "Unapproved target table")
    _, field, _ = TARGETS[table]
    return sql.SQL("""SELECT b.*,
      CASE WHEN b.survey_wave='2004' AND b.{age} BETWEEN 0 AND 96
           THEN b.{age}=96 ELSE NULL END::boolean AS age_2004_is_topcoded,
      CASE WHEN b.survey_wave='2004' AND b.{age} BETWEEN 0 AND 96
           THEN b.{age} ELSE NULL END::smallint AS age_2004_lower_bound,
      CASE WHEN b.survey_wave='2004' AND b.{age} BETWEEN 0 AND 95
           THEN b.{age} ELSE NULL END::smallint AS age_2004_exact_years,
      CASE WHEN b.survey_wave IS DISTINCT FROM '2004' THEN 'outside_rule_scope'
           WHEN b.{age} IS NULL THEN 'missing_age'
           WHEN b.{age}=96 THEN 'topcoded_96_plus'
           WHEN b.{age} BETWEEN 0 AND 95 THEN 'reported_completed_years'
           ELSE 'unexpected_2004_code' END::text AS age_2004_status
      FROM cses_data.{table} b""").format(age=sql.Identifier(field), table=sql.Identifier(table)).as_string()


def rule_records(review):
    member = next(r for r in review["reviewed_member_fields"] if r["survey_wave"] == "2004" and r["canonical_name"] == "age")
    return [{"target_table": table, "source_age_column": column, "analysis_view": view,
             "rule_version": VERSION, "survey_wave": "2004", "top_code": 96, "age_lower_bound": 96,
             "source_file": member["source_file"], "source_sha256": member["source_sha256"],
             "source_sheet": member["source_sheet"], "source_cell": member["age_instruction_cell"],
             "source_instruction": member["age_instruction"], "review_sha256": REVIEW_SHA,
             "scope_note": "2004 source roster age, propagated to ED/EC or unique household head. Other waves not certified. Preserve existing age and historical metadata; this rule is an additive qualification."}
            for table, (view, column, _) in TARGETS.items()]


def rule_query(review):
    return sql.SQL("""SELECT * FROM jsonb_to_recordset({payload}::jsonb) AS r(
        target_table text, source_age_column text, analysis_view text, rule_version text,
        survey_wave text, top_code smallint, age_lower_bound smallint, source_file text,
        source_sha256 text, source_sheet text, source_cell text, source_instruction text,
        review_sha256 text, scope_note text)""").format(
            payload=sql.Literal(json.dumps(rule_records(review), ensure_ascii=False, sort_keys=True))).as_string()


def proposed_ddl(queries):
    statements = ["-- PROPOSAL ONLY. This file is not executed by the planner.",
                  "-- Requires explicit scoped publication approval, fresh preflight, backup and transactional validation."]
    for view, query in queries.items():
        name = sql.Identifier(SCHEMA, view)
        statements.append(sql.SQL("CREATE VIEW {} WITH (security_barrier=true) AS ").format(name).as_string() + query + ";")
        comment = f"{VERSION}: additive 2004 age-96+ qualification. Existing values unchanged. Evidence: {SCHEMA}.{RULE_VIEW}; review SHA256 {REVIEW_SHA}."
        statements.append(sql.SQL("COMMENT ON VIEW {} IS {};").format(name, sql.Literal(comment)).as_string())
        if view != RULE_VIEW:
            for column, description in COMMENTS.items():
                statements.append(sql.SQL("COMMENT ON COLUMN {} IS {};").format(
                    sql.Identifier(SCHEMA, view, column), sql.Literal(description)).as_string())
        statements.append(sql.SQL("GRANT SELECT ON {} TO mda_readonly;").format(name).as_string())
    return "\n\n".join(statements) + "\n"


def statistics(frame, age):
    return {"rows": len(frame), "status_counts": {str(k): int(v) for k, v in frame[EXTRAS[3]].value_counts().sort_index().items()},
            "topcoded_rows": int(frame[EXTRAS[0]].fillna(False).sum()),
            "original_age_unchanged": True,
            "age_65_plus_unchanged_in_2004": bool(frame.loc[frame.survey_wave.eq("2004"), age].ge(65).fillna(False).equals(
                frame.loc[frame.survey_wave.eq("2004"), EXTRAS[1]].ge(65).fillna(False)))}


def local_projection(root, table):
    _, age, key = TARGETS[table]
    frame = pd.read_parquet(root / f"data/processing/cses/{table}.parquet").rename(columns=snake_case)
    require(not set(EXTRAS).intersection(frame.columns), "New columns collide with existing columns")
    frame = frame[["survey_wave", key, age]].copy()
    require(not frame[["survey_wave", key]].isna().any().any(), "Missing natural key")
    require(not frame.duplicated(["survey_wave", key]).any(), "Duplicate natural key")
    projected = qualify(frame, age)
    require(not projected[EXTRAS[3]].eq("unexpected_2004_code").any(), "Unexpected 2004 age blocks release")
    return projected


def local_plan(root, review):
    queries = {view: age_query(table) for table, (view, _, _) in TARGETS.items()}
    queries[RULE_VIEW] = rule_query(review)
    stats, sets = {}, {}
    for table, (_, age, key) in TARGETS.items():
        projected = local_projection(root, table)
        stats[table] = statistics(projected, age)
        require(stats[table]["topcoded_rows"] == (0 if table == "final_HH_CSES" else 3), "Topcode count drift")
        require(stats[table]["age_65_plus_unchanged_in_2004"], "Older-age grouping changed")
        if key == "person_id":
            sets[table] = set(projected.loc[projected[EXTRAS[0]].fillna(False), key])
    require(sets["final_HL_CSES"] == sets["final_ED_CSES"] == sets["final_EC_CSES"], "Affected people differ between HL/ED/EC")
    return {"plan_id": VERSION, "database": "mda", "schema": SCHEMA,
            "review_sha256": REVIEW_SHA, "implementation_sha256": digest((root / SELF).read_bytes()),
            "input_tables": review["age_impact"]["tables"], "queries": queries,
            "query_sha256": {name: digest(q.encode()) for name, q in queries.items()}, "local_statistics": stats,
            "distinct_affected_people": len(sets["final_HL_CSES"]), "same_people_in_hl_ed_ec": True,
            "prospective_rule_records": rule_records(review), "new_view_count": 5,
            "new_physical_tables": 0, "existing_data_updates": 0, "existing_metadata_updates": 0,
            "new_question_links": 0, "new_schemas": 0, "database_publication_approved": False,
            "database_mutated": False, "git_dvc_archived": False,
            "publication_requirements": ["Explicit approval for these five new views only; no blanket questionnaire publication.",
                "Fresh protected-state comparison, no target-name conflicts, no active DDL event triggers.",
                "Verified external backup and transactional creation/comments/SELECT grants; rollback on mismatch.",
                "Independent post-publication checks, append-only provenance/lineage and role-access validation."]}


def database_preflight(root, plan):
    """Run only SELECT/SHOW and transaction-local settings, including prospective queries."""
    with connect_database({"dbname": "mda"}) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        conn.execute("SET LOCAL statement_timeout='55s'")
        require(conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on", "Read-only transaction required")
        for name in plan["queries"]:
            row = conn.execute("SELECT to_regclass(%s)::text AS name", (SCHEMA + "." + name,)).fetchone()
            require(row["name"] is None, f"Proposed target already exists: {name}")
        require(not conn.execute("SELECT evtname FROM pg_event_trigger WHERE evtenabled <> 'D'").fetchall(), "Active DDL event triggers need separate review")
        require(conn.execute("SELECT rolname FROM pg_roles WHERE rolname='mda_readonly'").fetchone(), "Existing reader role missing")
        observed_stats = {}
        for table, (view, age, key) in TARGETS.items():
            expected = local_projection(root, table)
            projection = ["survey_wave", key, age, *EXTRAS]
            query = sql.SQL("SELECT {} FROM ({}) prospective ORDER BY survey_wave, {}").format(
                sql.SQL(", ").join(map(sql.Identifier, projection)), sql.SQL(plan["queries"][view]), sql.Identifier(key))
            rows = conn.execute(query).fetchall()
            actual = pd.DataFrame.from_records(rows, columns=projection)
            for column in projection:
                actual[column] = actual[column].astype(expected[column].dtype)
            pd.testing.assert_frame_equal(actual.reset_index(drop=True),
                expected.sort_values(["survey_wave", key]).reset_index(drop=True), check_exact=True)
            observed_stats[table] = statistics(actual, age)
        rules = conn.execute(plan["queries"][RULE_VIEW]).fetchall()
        require(rules == plan["prospective_rule_records"], "Rule view differs from inspected source evidence")
        metadata = conn.execute("""SELECT canonical_variable_id,target_table,canonical_name,canonical_definition
          FROM cses_alignment.cses_canonical_variable
          WHERE (target_table=ANY(%s) AND canonical_name='age')
             OR (target_table='final_HH_CSES' AND canonical_name='household_head_age')
          ORDER BY canonical_variable_id""", (list(TARGETS)[:3],)).fetchall()
        require(len(metadata) == 4, "Expected four existing age canonical definitions")
        structure = conn.execute("""SELECT n.nspname,c.relname,c.relkind,c.oid::bigint,c.relowner::bigint,
          c.relacl::text,c.reloptions::text,a.attnum,a.attname,format_type(a.atttypid,a.atttypmod) AS type,
          col_description(c.oid,a.attnum) AS column_comment,obj_description(c.oid,'pg_class') AS relation_comment,
          CASE WHEN c.relkind='v' THEN pg_get_viewdef(c.oid,true) END AS definition
          FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
          JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
          WHERE n.nspname IN ('cses_meta','cses_alignment','cses_data','cses_analysis','public')
            AND c.relkind IN ('r','v','m') ORDER BY n.nspname,c.relname,a.attnum""").fetchall()
        return {"plan_id": VERSION, "transaction_read_only": True, "database_mutated": False,
                "prospective_views_created": 0, "prospective_queries_checked": 5,
                "database_statistics": observed_stats, "all_projected_rows_equal_local": True,
                "rule_rows": len(rules), "existing_age_metadata": metadata,
                "protected_structure_sha256": canonical_sha256(structure),
                "protected_structure_column_records": len(structure),
                "query_sha256": plan["query_sha256"], "implementation_sha256": plan["implementation_sha256"],
                "scope_note": "Read-only prospective-query validation; not a publication record or full database backup. Fresh apply-time protected content/structure checks remain required."}


def save_package(output, products):
    for name, value in products.items():
        path = output / name
        payload = value.encode() if isinstance(value, str) else encoded(value)
        require(not path.exists() or path.read_bytes() == payload, f"Refusing changed historical output: {path}")
    for name, value in products.items():
        write_once(output / name, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, default=Path(DIRECTORY))
    parser.add_argument("--check-database", action="store_true", help="Read-only prospective-query comparison; never publishes views")
    args = parser.parse_args()
    review = checked_review(args.root)
    plan = local_plan(args.root, review)
    products = {"plan.json": plan, "proposed_views.sql": proposed_ddl(plan["queries"])}
    if args.check_database:
        products["database_preflight.json"] = database_preflight(args.root, plan)
    save_package(args.root / args.output, products)
    print(json.dumps({"distinct_affected_people": 3, "proposed_views": 5,
                      "database_read_only_checked": args.check_database, "database_mutated": False}))


if __name__ == "__main__":
    main()
