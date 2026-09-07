#!/usr/bin/env python3
"""Plan 15 reviewed question links and seven identifier provenance rows; no DB writes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cses_baseline_metadata import connect_database
from organize_cses_questionnaires import digest, write_once
from plan_cses_age_topcode import checked_review, require
from psycopg import sql

SELF = "rsc/cses_db/plan_cses_questionnaire_batch.py"
OUTPUT = "data/processing/cses/questionnaire_batch_v1"
VIEW = "cses_source_identifier_provenance_v1"
QUESTION_IDS = {100, 101, 206, 207, 313, 316, 412, 415, 1857}
SEX_IDS = {14, 890, 1118, 1947, 2298, 3649}


def build(root):
    review = checked_review(root)
    registry = json.loads((root / "data/processing/cses/questionnaire_alignment_v1/registry.json").read_text())
    source_vars = {r["source_variable_id"]: r for r in registry["source_variables"]}
    instruments = {r["source_file"]: r for r in registry["instruments"]}
    chosen = [r for r in review["ambiguity_resolutions"] if r["role"] == "interview_question"]
    chosen += [r for r in review["reviewed_member_fields"] if r["publication_class"] == "ready_for_question_link_plan"]
    require({r["source_variable_id"] for r in chosen} == QUESTION_IDS | SEX_IDS and len(chosen) == 15, "Wrong reviewed question scope")
    questions = []
    for r in chosen:
        sv = source_vars[r["source_variable_id"]]
        instrument = instruments[r["source_file"]]
        require(sv["question_id"] is None and instrument["survey_wave"] == sv["survey_wave"], "Existing or cross-wave link")
        require(instrument["documentation_status"] != "provisional", "Draft excluded from direct question batch")
        sex = r["source_variable_id"] in SEX_IDS
        options = r["simple_options_checked"] if sex else None
        question = {"instrument_id": instrument["instrument_id"], "question_code": sv["variable_name"].lower(),
            "question_text": r["question_text"] if sex else r["reviewed_text"], "section_name": r["source_sheet"],
            "sequence_number": None, "source_page": None, "response_options": options, "skip_instruction": None,
            "question_grain": "household-member-wave" if sex or sv["module_code"] in {"education", "employment_current"}
                else "household-plot-wave" if sv["module_code"] == "agriculture_land" else "household-wave",
            "repeat_context": {"source_sheet": r["source_sheet"], "question_text_cell": r["text_cell"],
                "question_code_cell": r["question_code_cell"] if sex else r["code_cell"],
                "source_sha256": r["source_sha256"], "review_source_variable_id": sv["source_variable_id"],
                "review_scope": "question correspondence only; no whole-variable semantic approval",
                "universe_and_options_note": "1=Male, 2=Female; original roster membership definition retained" if sex
                    else "Other option and routing contexts remain in accepted review; no complete option certification here"},
            "is_exact_question_text": True, "documentation_status": "documented"}
        questions.append({"source_variable_id": sv["source_variable_id"], "survey_wave": sv["survey_wave"],
            "source_key": {k: sv[k] for k in ("dataset_id", "archive_relative_path", "member_path", "nested_member_path", "variable_name")},
            "question": question, "link_update": {"question_link_status": "reviewed", "question_link_role": "direct_response"},
            "expected_before": {k: sv[k] for k in ("question_id", "question_link_status", "question_link_role", "alignment_status")}})
    identifiers = [{k: r[k] for k in ("source_variable_id", "survey_wave", "variable_name", "data_source", "source_file",
        "source_sha256", "documentation_status", "reviewed_text", "candidate_decisions", "qualifications")}
        for r in review["ambiguity_resolutions"] if r["role"] == "repeat_identifier"]
    require(len(identifiers) == 7 and sum(len(r["candidate_decisions"]) for r in identifiers) == 32, "Identifier scope drift")
    query = sql.SQL("""SELECT p.* FROM jsonb_to_recordset({payload}::jsonb) AS p(
      source_variable_id bigint,survey_wave text,variable_name text,data_source jsonb,source_file text,
      source_sha256 text,documentation_status text,reviewed_text text,candidate_decisions jsonb,qualifications jsonb)
      JOIN cses_alignment.cses_source_variable sv ON sv.source_variable_id=p.source_variable_id
        AND sv.dataset_id=(p.data_source->>'dataset_id')::bigint AND sv.variable_name=p.variable_name""").format(
            payload=sql.Literal(json.dumps(identifiers, ensure_ascii=False, sort_keys=True))).as_string()
    return {"plan_id": "cses-questionnaire-reviewed-batch-v1", "review_sha256": digest((root / "data/processing/cses/questionnaire_review_v1/review.json").read_bytes()),
            "implementation_sha256": digest((root / SELF).read_bytes()), "questions_and_links": sorted(questions, key=lambda r: r["source_variable_id"]),
            "identifier_provenance": identifiers, "identifier_view": f"cses_analysis.{VIEW}", "identifier_query": query,
            "proposed_counts": {"new_questions": 15, "source_variable_link_updates": 15, "new_identifier_view": 1,
                "identifier_rows": 7, "header_occurrences": 32, "new_alignment_release": 1, "new_load_run": 1,
                "physical_data_changes": 0, "new_instruments": 0, "new_schemas": 0, "constraint_changes": 0},
            "publication_approved": False, "database_mutated": False,
            "approval_scope": "A future named metadata release, 15 new questions/15 links and one identifier view; no other candidates or semantic mapping approvals.",
            "qualifications": ["The 2014 identifier stays draft/provisional.", "Sex correspondence is checked for six source waves, not all ten.",
                "Identifiers never become questions; existing source-variable check constraints remain unchanged.",
                "Question registration does not certify options, universe or analytical denominators for all nine non-sex questions."]}


def preflight(plan):
    with connect_database({"dbname": "mda"}) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        conn.execute("SET LOCAL statement_timeout='30s'")
        require(conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on", "Read-only required")
        for r in plan["questions_and_links"]:
            before = conn.execute("SELECT question_id,question_link_status,question_link_role,alignment_status FROM cses_alignment.cses_source_variable WHERE source_variable_id=%s", (r["source_variable_id"],)).fetchone()
            require(before == r["expected_before"], "Source link changed since accepted review")
            identity = conn.execute("""SELECT sv.dataset_id,a.relative_path AS archive_relative_path,d.member_path,
              d.nested_member_path,sv.variable_name FROM cses_alignment.cses_source_variable sv
              JOIN cses_meta.cses_dataset d USING(dataset_id) JOIN cses_meta.cses_source_archive a USING(source_archive_id)
              WHERE sv.source_variable_id=%s""", (r["source_variable_id"],)).fetchone()
            require(identity == r["source_key"], "Source-variable identity drift")
            instrument = conn.execute("SELECT source_sha256::text FROM cses_alignment.cses_instrument WHERE instrument_id=%s", (r["question"]["instrument_id"],)).fetchone()
            require(instrument and instrument["source_sha256"] == r["question"]["repeat_context"]["source_sha256"], "Instrument hash drift")
            require(not conn.execute("SELECT 1 FROM cses_alignment.cses_question WHERE instrument_id=%s AND question_code=%s", (r["question"]["instrument_id"], r["question"]["question_code"])).fetchone(), "Question identity already exists")
        require(conn.execute("SELECT to_regclass(%s)::text AS relation", (plan["identifier_view"],)).fetchone()["relation"] is None, "Identifier view exists")
        rows = conn.execute(plan["identifier_query"]).fetchall()
        require(sorted(rows, key=lambda r: r["source_variable_id"]) == sorted(plan["identifier_provenance"], key=lambda r: r["source_variable_id"]), "Identifier provenance query mismatch")
        current = conn.execute("""SELECT (SELECT count(*) FROM cses_alignment.cses_question) AS questions,
          (SELECT count(*) FROM cses_alignment.cses_source_variable WHERE question_id IS NOT NULL) AS links,
          (SELECT count(*) FROM cses_meta.cses_alignment_release) AS releases,
          (SELECT count(*) FROM cses_meta.cses_load_run) AS runs""").fetchone()
        require(current == {"questions": 171, "links": 296, "releases": 9, "runs": 9}, "Current catalog baseline changed")
    return {"transaction_read_only": True, "database_mutated": False, "checks_passed": True, "current_counts": current,
            "planned_after_counts": {"questions": 186, "links": 311, "releases": 10, "runs": 10}, "identifier_rows_checked": 7}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--check-database", action="store_true")
    parser.add_argument("--output", type=Path, default=Path(OUTPUT))
    args = parser.parse_args()
    plan = build(args.root)
    if args.check_database:
        plan["preflight"] = preflight(plan)
    write_once(args.root / args.output / "plan.json", plan)
    print(json.dumps(plan["proposed_counts"]))


if __name__ == "__main__":
    main()
