#!/usr/bin/env python3
"""Review four EC screening families without inventing a common employment denominator."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from organize_cses_questionnaires import digest, write_once
from review_cses_education import BASE, load_inputs, selected_sources, value_counts, verify_workbooks
from review_cses_questionnaires import parse_options, require

SELF = "rsc/cses_db/review_cses_employment_screening.py"
BUILDER = "rsc/cses_db/cses_employment.py"
BUILDER_SHA = "4ba6fb4377cfc636528e918cd35a6ae01221f24d9330f36e850896837c604d7a"
OUTPUT = "data/processing/cses/employment_screening_review_v1"
FIELDS = ["worked_at_least_one_hour_past_7_days", "second_work_screening_source_code", "actively_seeking_work", "available_for_work"]
LATER = {"sheets": ["15 Econo_Status_1", "15 Econo_Status_1", "15 Econo_Status_2", "15 Econo_Status_2"],
         "texts": [["F6"], ["P6"], ["CM11"], ["CX6"]], "codes": ["F19", "P19", "CM19", "CX19"],
         "options": [["F16", "F17"], ["P16", "P17"], ["CM16"], ["CX12"]],
         "universe": "A5", "respondent": "A3", "seek_gate": "CM6", "minimum_age": 5}
LAYOUT = {
    "2004": {"sheets": ["13 Econ. Status"] * 4, "texts": [["F5"], ["K5"], ["AA5"], ["W5"]],
             "codes": ["F15", "K15", "AA15", "W15"], "options": [["F12", "F13"], ["L12", "L13"], ["AA12"], ["W12"]],
             "universe": "B3", "respondent": "AA1", "seek_gate": "AA5", "minimum_age": 10},
    "2009": {"sheets": ["15 Econo_Status_1", "15 Econo_Status_1", "15 Econo_Status_2", "15 Econo_Status_2"],
             "texts": [["G4"], ["Q4"], ["BW9"], ["CH4"]], "codes": ["G16", "Q16", "BW16", "CH16"],
             "options": [["G13", "G14"], ["Q13", "Q14"], ["BW13"], ["CH10"]],
             "universe": "B3", "respondent": "O1", "seek_gate": "BW4", "minimum_age": 5},
    "2011-12": LATER, "2013": LATER, "2014": LATER, "2016": LATER,
    "2021": {"sheets": ["15 Current Eco-1", "15 Current Eco-1", "15 Current Econo-4", "15 Current Econo-4"],
             "texts": [["F4", "F7"], ["P4", "P7"], ["CM17"], ["CX12"]], "codes": ["F17", "P17", "CM25", "CX25"],
             "options": [["F14", "F15"], ["P14", "P15"], ["CM22"], ["CX18"]],
             "universe": "B3", "respondent": "L1", "seek_gate": "CM12", "minimum_age": 5},
}


def semantics(wave, field):
    if wave not in LAYOUT:
        return "unverified_household_form"
    if field == FIELDS[0]:
        return "paid_work_including_business_holiday_note" if wave == "2021" else "any_work_including_farm_and_household_business"
    if field == FIELDS[1]:
        return "unpaid_work_if_no_paid_work" if wave == "2021" else "temporarily_absent_job_or_economic_activity_if_no_work"
    if field == FIELDS[2]:
        return "seeking_past_7_days" if wave == "2004" else "seeking_past_4_weeks"
    return "available_past_7_days" if wave == "2004" else "available_past_7_days_or_start_within_next_2_weeks"


def evidence(root):
    spec, alignment, inventory, extracts = load_inputs(root)
    cells = {s["source_file"]: s["sheets"] for s in extracts}
    rows, universes = [], []
    for source in selected_sources(spec, inventory):
        wave = source["survey_wave"]
        layout = LAYOUT[wave]
        sheets = cells[source["source_file"]]
        first = sheets[layout["sheets"][0]]
        require(f"aged {layout['minimum_age']} years and older" in first[layout["universe"]], "Minimum-age instruction differs")
        universes.append({"survey_wave": wave, "minimum_age": layout["minimum_age"],
            "source_file": source["source_file"], "source_sheet": layout["sheets"][0],
            "instructions": {c: first[c] for c in [layout["universe"], layout["respondent"]]},
            "seek_gate_cell": layout["seek_gate"], "seek_gate_sheet": layout["sheets"][2],
            "seek_gate_text": sheets[layout["sheets"][2]][layout["seek_gate"]],
            "documentation_status": source["documentation_status"]})
        for index, field in enumerate(FIELDS):
            sheet_name = layout["sheets"][index]
            sheet = sheets[sheet_name]
            code_cell = layout["codes"][index]
            text_cells = layout["texts"][index]
            links = [r for r in alignment["source_links"] if r["survey_wave"] == wave and r["module_code"] == "employment_current"
                     and ["final_EC_CSES", field] in r["canonical_keys"]]
            require(len(links) == 1, "Unique source-field identity required")
            link = links[0]
            printed_number = int(re.fullmatch(r"\((\d+)\)", sheet[code_cell].strip())[1])
            require(int(re.search(r"(\d+)$", link["variable_name"])[1]) == printed_number, "Printed question number differs from source suffix")
            candidates = [q for q in inventory["questions"] if q["source_file"] == source["source_file"]
                          and q["source_sheet"] == sheet_name and q["question_code_cell"] == code_cell]
            require(len(candidates) == 1 and text_cells[0] in candidates[0]["text_cell_candidates"], "Explicit question locator is not unique")
            opts = parse_options({c: sheet[c] for c in layout["options"][index]})
            require({o["source_code"] for o in opts} == {1, 2}, "Two Yes/No source options required")
            text = "\n".join(sheet[c] for c in text_cells)
            if index == 1:
                require(("unpaid work" if wave == "2021" else "temporarily absent") in text, "Second-screen meaning changed")
            if index == 2:
                require(("past 7 days" if wave == "2004" else "4 weeks") in text, "Search period changed")
            if index == 3 and wave != "2004":
                require("2 weeks" in text, "Future availability window missing")
            rows.append({"survey_wave": wave, "field": field, "source_variable_id": link["source_variable_id"],
                "source_variable": link["variable_name"], "data_source": {k: link[k] for k in ["dataset_id", "archive_relative_path", "member_path", "nested_member_path"]},
                "source_file": source["source_file"], "source_sha256": source["source_sha256"], "source_sheet": sheet_name,
                "question_code_cell": code_cell, "question_text_cells": text_cells, "question_text": text,
                "original_text_cells": {c: sheet[c] for c in text_cells}, "options": opts,
                "option_cells": {c: sheet[c] for c in layout["options"][index]}, "candidate_id": candidates[0]["candidate_id"],
                "correspondence_basis": "explicit printed section 15, question number, question wording and released field; 2009 A/C subsection-letter discrepancy retained"
                    if wave == "2009" else "explicit source cell and existing candidate correspondence",
                "original_heuristic_candidate_ids": link["candidate_ids"], "meaning": semantics(wave, field),
                "minimum_age": layout["minimum_age"], "documentation_status": source["documentation_status"],
                "whole_variable_certified": False, "publication_approved": False})
    require(len(rows) == 28, "Exactly 28 screening question-wave records required")
    return rows, universes


def route_mask(frame, field, wave):
    """Literal questionnaire route only; never labels people as unemployed."""
    import pandas as pd

    if wave not in LAYOUT:
        return None
    mask = frame.age.ge(LAYOUT[wave]["minimum_age"])
    first_no = frame[FIELDS[0]].eq(0)
    second_no = frame[FIELDS[1]].eq(2)
    if field == FIELDS[1]:
        mask &= first_no
    elif field in FIELDS[2:]:
        mask &= first_no & second_no
        if field == FIELDS[3] and wave != "2004":
            # The search No branch skips to Q31, bypassing availability Q28.
            mask &= frame[FIELDS[2]].eq(1)
    require(isinstance(mask, pd.Series), "Boolean route required")
    return mask


def data_review(root):
    import pandas as pd
    from cses_employment import ALIASES, employment_sources, prepare_wave_sources, source_value
    from cses_hh_hl_common import AlignmentContext, snake_case

    frame = pd.read_parquet(root / "data/processing/cses/final_EC_CSES.parquet").rename(columns=snake_case)
    require(frame.shape == (332903, 60) and not frame.duplicated(["survey_wave", "person_id"]).any(), "EC grain changed")
    require(not frame[["survey_wave", "person_id"]].isna().any().any(), "Missing EC key")
    aliases = {snake_case(k): v for k, v in ALIASES.items()}
    profiles, source_rows, summaries = [], [], []
    for wave, sources in employment_sources(root):
        context = AlignmentContext(root=root)
        keys, aligned = prepare_wave_sources(context, wave, sources)
        keys = keys.rename(columns=snake_case)
        current = frame.loc[frame.survey_wave.eq(wave)].set_index("person_id")
        require(set(current.index) == set(keys.person_id) and len(current) == len(keys), "Source/EC person keys differ")
        current = current.loc[keys.person_id].reset_index()
        for key in ["household_id", "source_row_id", "source_archive", "source_submodule"]:
            require(current[key].equals(keys[key].astype(current[key].dtype)), "Source identity changed")
        raw_counts = []
        for field in FIELDS:
            values, column = source_value(aligned, aliases[field])
            require(column is not None, "Required screening source field missing")
            values = pd.to_numeric(values, errors="coerce")
            expected = values.where(values.isin([1, 2])) if field == FIELDS[1] else values.map({1: 1, 2: 0})
            pd.testing.assert_series_equal(expected.astype(current[field].dtype), current[field], check_names=False)
            raw_counts.append({"field": field, "source_variable": column, "raw_values": value_counts(values),
                               "raw_null": int(values.isna().sum()), "invalid_nonnull_codes": value_counts(values.loc[values.notna() & ~values.isin([1, 2])]),
                               "raw_to_canonical_equal": True})
            route = route_mask(current, field, wave)
            observed = current[field].notna()
            profiles.append({"survey_wave": wave, "field": field, "rows": len(current), "nonnull": int(observed.sum()),
                "null": int((~observed).sum()), "values": value_counts(current[field]), "meaning": semantics(wave, field),
                "literal_route_records": int(route.fillna(False).sum()) if route is not None else None,
                "nonnull_in_literal_route": int((observed & route.fillna(False)).sum()) if route is not None else None,
                "nonnull_outside_known_route": int((observed & route.eq(False).fillna(False)).sum()) if route is not None else None,
                "route_unknown_records": int(route.isna().sum()) if route is not None else None,
                "analytical_denominator_certified": False})
        minimum = LAYOUT.get(wave, {}).get("minimum_age")
        summaries.append({"survey_wave": wave, "rows": len(current), "minimum_age": minimum,
            "at_or_above_minimum_age": int(current.age.ge(minimum).sum()) if minimum is not None else None,
            "below_minimum_age": int(current.age.lt(minimum).sum()) if minimum is not None else None,
            "age_missing": int(current.age.isna().sum()), "hl_unmatched": int(current.hl_link_matched.eq(0).sum()),
            "first_yes": int(current[FIELDS[0]].eq(1).sum()), "second_yes": int(current[FIELDS[1]].eq(1).sum()),
            "second_yes_after_first_no": int((current[FIELDS[0]].eq(0) & current[FIELDS[1]].eq(1)).sum()),
            "both_screens_no": int((current[FIELDS[0]].eq(0) & current[FIELDS[1]].eq(2)).sum()),
            "actual_interview_respondents": None})
        source_rows.append({"survey_wave": wave, "sources": [{"source_file": s.display_name(root), "sha256": digest(s.read_bytes())} for s in sources], "fields": raw_counts})
    return frame, profiles, source_rows, summaries


def check_database(frame):
    import pandas as pd
    from cses_baseline_metadata import connect_database
    from psycopg import sql

    columns = ["survey_wave", "person_id", "age", "hl_link_matched", *FIELDS]
    with connect_database({"dbname": "mda"}) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        conn.execute("SET LOCAL statement_timeout='55s'")
        require(conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on", "Readonly required")
        live = pd.DataFrame(conn.execute(sql.SQL('SELECT {} FROM cses_data."final_EC_CSES" ORDER BY survey_wave,person_id').format(
            sql.SQL(",").join(map(sql.Identifier, columns)))).fetchall()).astype(frame[columns].dtypes.to_dict())
        pd.testing.assert_frame_equal(live, frame[columns].sort_values(["survey_wave", "person_id"]).reset_index(drop=True), check_exact=True)
    return {"selected_columns": columns, "rows": len(frame), "all_selected_values_equal": True,
            "not_a_full_60_field_validation": True, "transaction_read_only": True, "database_mutated": False}


def make_review(root, verification, check_live):
    from plan_cses_age_topcode import checked_review

    checked_review(root)
    require(digest((root / BUILDER).read_bytes()) == BUILDER_SHA, "Frozen employment builder changed")
    verified = json.loads(verification.read_text())
    require(verified["source_cells_sha256"] == digest((root / BASE / "source_cells.json").read_bytes()), "Workbook verification baseline changed")
    require(verified["implementation_sha256"] == digest((root / "rsc/cses_db/review_cses_education.py").read_bytes()), "Workbook verifier implementation changed")
    require(len(verified["sources"]) == 7 and all(s["all_sheets_equal"] for s in verified["sources"]), "Seven freshly checked workbooks required")
    questions, universes = evidence(root)
    frame, profiles, sources, summaries = data_review(root)
    return {"review_id": "cses-employment-screening-review-v1", "implementation_sha256": digest((root / SELF).read_bytes()),
        "employment_builder_sha256": BUILDER_SHA, "canonical_parquet_sha256": digest((root / "data/processing/cses/final_EC_CSES.parquet").read_bytes()),
        "source_verification": verified, "questions": questions, "universes": universes, "profiles": profiles,
        "raw_sources": sources, "wave_counts": summaries, "database_check": check_database(frame) if check_live else {"performed": False},
        "scope_counts": {"physical_fields": 60, "employment_fields": 39, "reviewed_field_families": 4,
            "remaining_employment_field_families": 35, "question_wave_reviews": 28, "field_wave_profiles": 40, "rows": len(frame)},
        "database_mutated": False, "canonical_data_mutated": False, "individual_records_saved": False,
        "whole_module_certified": False, "form_gaps": ["2007", "2017", "2019"]}


def md(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def documents(r):
    lines = ["# CSES employment screening alignment brief", "", "Local review of four screening families; no EC database or canonical-data changes.", "",
        "EC contains **332,903 member-wave records and 60 fields**: 39 employment fields and 21 context/identity/provenance fields. "
        "This first batch checks four families, 28 question-wave correspondences in seven English forms, and 40 field-wave data profiles. "
        "The remaining 35 employment families are not certified by this work. The 2014 draft and 2007/2017/2019 household-form gaps remain visible.", "",
        "## Confirmed meaning changes", "", "| Field | 2004 | 2009–2016 inspected forms | 2021 |", "| --- | --- | --- | --- |",
        "| worked_at_least_one_hour_past_7_days | Any work, including farm/household business | Any work including farm/household business | Paid work; note also includes business owners or workers on holiday |",
        "| second_work_screening_source_code | Job temporarily absent, if no work | Job/economic activity temporarily absent, if no work | Unpaid work, if no paid work |",
        "| actively_seeking_work | Past seven days | Past four weeks | Past four weeks |",
        "| available_for_work | During past seven days | Past seven days OR able to start within next two weeks | Past seven days OR able to start within next two weeks |", "",
        "The second screen is intentionally retained as raw 1=Yes / 2=No; it must not be labeled uniformly as temporary absence. "
        "The other three fields use harmonized 1=Yes / 0=No. The printed binary option lists agree, but their meanings and routes do not. "
        "Do not calculate a comparable employment rate from the first question alone, or classify both-screen-No records as unemployed without a separate definition.", "",
        "All 2021 continuation notes were included: the paid-work holiday note is in F7 and the unpaid farm/household-business examples in P7. "
        "Only reading the question headline would omit these qualifications.", "",
        "## Four 2009 links recovered from a subsection-letter mismatch", "",
        "The printed form has section 15, subsection A and questions 3/4/26/28, whereas released variables use q15_c03/c04/c26/c28. "
        "The earlier prefix matcher therefore supplied no candidate links. This review records explicit same-wave sheet/cell, printed number, wording "
        "and source-variable correspondence for those four fields. It does not rewrite the old heuristic workbench or publish new database links.", "",
        "## Population and screening counts", "",
        "| Wave | EC records | Printed minimum age | At/above minimum | Below minimum | Missing age | Unmatched HL |", "| --- | ---: | --- | ---: | ---: | ---: | ---: |"]
    for w in r["wave_counts"]:
        lines.append("| " + " | ".join([w["survey_wave"], *[f"{w[k]:,}" if w[k] is not None else "Not verified" for k in
            ["rows", "minimum_age", "at_or_above_minimum_age", "below_minimum_age", "age_missing", "hl_unmatched"]]]) + " |")
    lines += ["", "Questionnaire eligibility is age 10+ in 2004 and 5+ in the six inspected later waves. "
        "No age cutoff is borrowed for the three form gaps. The instructions request individual interviews, but these data counts do not establish "
        "actual interview-respondent counts. The two unmatched EC records are retained; ages may use released fallback data when no HL link exists.", "",
        "| Wave | First screen Yes | Second screen Yes after first No | Both screens No |", "| --- | ---: | ---: | ---: |"]
    for w in r["wave_counts"]:
        lines.append(f"| {w['survey_wave']} | {w['first_yes']:,} | {w['second_yes_after_first_no']:,} | {w['both_screens_no']:,} |")
    lines += ["", "These are unweighted released response combinations across all table rows, not certified employment/unemployment counts. "
        "2004 general sampling weights remain unavailable. Missing/invalid codes and structural skips are not converted to No.", "",
        "## Routing and limits", "",
        "- First-screen Yes skips the second question and proceeds to job details (question 5).",
        "- The second-screen No branch goes to availability question 7 in 2004; in later forms it goes to job-search question 26.",
        "- Later question 26 applies when both screens are No; a No search answer skips to question 31 and bypasses availability question 28. "
        "Therefore availability non-null counts cannot serve as the denominator for every non-worker.",
        "- For the 2004 availability profile, the diagnostic route uses both screens No. The search question explicitly refers to no work and no job. "
        "Other downstream underemployment/job-detail routes are outside this four-question batch.",
        "- Values recorded outside literal routes are retained and counted, not automatically deleted or recoded.", "",
        "## Evidence and reproducibility", "",
        "[Field-wave counts and source locators](cses-employment-screening-field-waves.md) include non-null counts, literal-route counts and recorded values outside routes. "
        "[Machine-readable evidence](../data/processing/cses/employment_screening_review_v1/review.json) retains original wording, split option cells, source hashes, raw code frequencies and qualifications.", "",
        "Original seven workbooks were freshly re-extracted with macro-disabled legacy conversion and all sheets compared with frozen cells. "
        "All four source transformations were reproduced across ten waves, including the two-file 2004 person merge. "
        + ("A forced read-only database transaction compared every selected value across 332,903 rows: four screening fields, wave/person key, age and HL-link flag. " if r["database_check"].get("all_selected_values_equal") else "No live database validation is claimed. ")
        + "This is not a fresh full-row validation of the remaining EC fields. No individual records are written to the reports.", "",
        "```mermaid", "flowchart LR", '    F["7 original questionnaires"] --> Q["28 located screening questions"]',
        '    R["10-wave released employment data"] --> C["40 field-wave comparisons"]',
        '    Q --> D["Meaning, age and route qualifiers"]', '    C --> D', '    D --> N["Next: hours, status, occupation and industry"]', "```", "",
        "This local review diagram does not replace the published database graph v12.", "",
        "Reproduce the original-workbook check with the bundled Python runtime: "
        "`rsc/cses_db/review_cses_employment_screening.py --verify-workbooks --soffice /path/to/bundled/soffice`. "
        "Then run `.venv/bin/python rsc/cses_db/review_cses_employment_screening.py --check-database`. "
        "Changed snapshots require a fresh `--output` directory.", "",
        "Next review the remaining 35 employment families, beginning with working hours and job status, then occupation/industry classifications, "
        "pay and job-search detail. No new pooled labour-force definition has been adopted. "
        "Spreadsheet guidance informed split-option/continuation-note inspection and preservation of original questionnaire files.", ""]
    detail = ["# CSES employment screening field-wave profiles", "", "Companion to the [screening brief](cses-employment-screening-alignment.md). "
        "These are diagnostic record counts, not adopted statistical denominators. Unknown routes are not classified as outside-route records.", ""]
    for field in FIELDS:
        detail += [f"## {field}", "", "| Wave | Records | Non-null | Null | Literal-route records | Non-null in route | Non-null outside known route | Route unknown |",
                   "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for p in r["profiles"]:
            if p["field"] == field:
                detail.append("| " + " | ".join([p["survey_wave"], *[f"{p[k]:,}" if p[k] is not None else "Not assessed" for k in
                    ["rows", "nonnull", "null", "literal_route_records", "nonnull_in_literal_route", "nonnull_outside_known_route", "route_unknown_records"]]]) + " |")
        detail.append("")
    detail += ["## Original question locators", "", "All four question families have two printed options, 1=Yes and 2=No. "
               "The canonical second screen retains 1/2; the other three use 1/0. The 2014 draft is not promoted to a final questionnaire.", "",
               "| Wave | Field | Sheet | Text cells | Option cells | Source status |", "| --- | --- | --- | --- | --- | --- |"]
    for q in r["questions"]:
        detail.append(f"| {q['survey_wave']} | {q['field']} | {q['source_sheet']} | {', '.join(q['question_text_cells'])} | {', '.join(q['option_cells'])} | {q['documentation_status']} |")
    detail += ["", "## Raw codes outside 1/2", "", "Their existing canonical values are NULL; a specific missingness reason is not inferred.", "",
               "| Wave | Field | Raw code | Records |", "| --- | --- | ---: | ---: |"]
    for s in r["raw_sources"]:
        for f in s["fields"]:
            for code, n in f["invalid_nonnull_codes"].items():
                detail.append(f"| {s['survey_wave']} | {f['field']} | {code} | {n} |")
    detail.append("")
    return "\n".join(lines), "\n".join(detail)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, default=Path(OUTPUT))
    parser.add_argument("--docs-dir", type=Path, default=Path("docs"))
    parser.add_argument("--verify-workbooks", action="store_true")
    parser.add_argument("--soffice")
    parser.add_argument("--check-database", action="store_true")
    args = parser.parse_args()
    output = args.root / args.output
    if args.verify_workbooks:
        require(args.soffice, "Bundled converter path required")
        write_once(output / "source_verification.json", verify_workbooks(args.root, args.soffice))
    else:
        result = make_review(args.root, output / "source_verification.json", args.check_database)
        brief, detail = documents(result)
        write_once(output / "review.json", result)
        write_once(args.root / args.docs_dir / "cses-employment-screening-alignment.md", brief)
        write_once(args.root / args.docs_dir / "cses-employment-screening-field-waves.md", detail)
        print(json.dumps(result["scope_counts"]))


if __name__ == "__main__":
    main()
