#!/usr/bin/env python3
"""Read-only EC hours, workdays and status review; preserve all frozen releases."""
from __future__ import annotations

import argparse
import io
import json
import re
from pathlib import Path

from organize_cses_questionnaires import digest, write_once
from review_cses_education import BASE, load_inputs, selected_sources, value_counts, verify_workbooks
from review_cses_employment_screening import BUILDER, BUILDER_SHA
from review_cses_employment_screening import LAYOUT as SCREEN_LAYOUT
from review_cses_questionnaires import parse_options, require

SELF = "rsc/cses_db/review_cses_employment_hours_status.py"
OUTPUT = "data/processing/cses/employment_hours_status_review_v1"
PRIOR = "data/processing/cses/employment_screening_review_v1/review.json"
PRIOR_SHA = "aedcd983cd2936f9eda895480150e09102677bb8cb3f157c88f7d7b1977fbf19"
FIELDS = ["total_hours_worked_past_7_days", "main_hours_worked_past_7_days",
          "secondary_hours_worked_past_7_days", "main_days_worked_last_month",
          "secondary_days_worked_last_month", "main_employment_status_source_code",
          "secondary_employment_status_source_code"]
HOURS, DAYS, STATUS = FIELDS[:3], FIELDS[3:5], FIELDS[5:]
CONTEXT = ["survey_wave", "person_id", "age", "hl_link_matched",
           "worked_at_least_one_hour_past_7_days", "second_work_screening_source_code",
           "additional_jobs_count", "total_occupations_past_7_days", "main_occupation_source_code"]


def layouts(wave):
    """Seven field locators: sheet, text, printed code, unit/options; repeated 2004 rows explicit."""
    if wave == "2004":
        return [("13 Econ. Status", *v) for v in [
            ("P5", "P15", "P14"), ("X29", "X42", "X41"), ("X29", "X42", "X41"),
            ("AA29", "AA42", "AA41"), ("AA29", "AA42", "AA41"),
            ("AD29", "AD42", "AD32"), ("AD29", "AD42", "AD32")]]
    if wave == "2009":
        return [(f"15 Econo_Status_{s}", *v) for s, v in [
            (2, ("R4", "R16", "R15")), (1, ("BX8", "BX16", "BX15")),
            (2, ("C4", "C16", "C15")), (1, ("CD4", "CD16", "CD15")),
            (2, ("G4", "G16", "G15")), (1, ("BP4", "BP16", "BP9")), (1, ("EO4", "EO16", "EO8"))]]
    if wave == "2021":
        return [(s, *v) for s, v in [
            ("15 Current Econo-4", ("AN12", "AN25", "AN24")),
            ("15 Current Econo-2", ("C17", "C24", "C23")),
            ("15 Current Econo-4", ("C16", "C25", "C24")),
            ("15 Current Econo-2", ("G11", "G24", "G23")),
            ("15 Current Econo-4", ("G12", "G25", "G24")),
            ("15 Current Eco-1", ("BN4", "BN17", "BN9")),
            ("15 Current Econo-3", ("AU4", "AU16", "AU7"))]]
    require(wave in {"2011-12", "2013", "2014", "2016"}, "No borrowed layout for missing forms")
    day = "CB" if wave == "2011-12" else "BZ"
    return [(f"15 Econo_Status_{s}", *v) for s, v in [
        (2, ("AN6", "AN19", "AN18")), (1, ("BV10" if wave == "2011-12" else "BV12", "BV19", "BV18")),
        (2, ("C10", "C19", "C18")), (1, (f"{day}6", f"{day}19", f"{day}18")),
        (2, ("G6", "G19", "G18")), (1, ("BN6", "BN19", "BN11")), (1, ("EX6", "EX19", "EX10"))]]


def gate_cells(wave):
    if wave == "2004":
        return {"13 Econ. Status": ["AS4", "AS9", "AS11", "AS15", "C29", "C43", "C44", "F12", "F13", "L12", "L13"]}
    if wave == "2009":
        return {"15 Econo_Status_1": ["BX4", "CJ4", "CJ13", "CJ16", "G13", "Q14"],
                "15 Econo_Status_2": ["K4"]}
    if wave == "2021":
        return {"15 Current Econo-2": ["C11", "AE11", "AE19", "AE24"],
                "15 Current Econo-4": ["C12", "W12"], "15 Current Eco-1": ["F14", "P15"]}
    count = "CW" if wave == "2011-12" else "CX"
    return {"15 Econo_Status_1": ["BV6", f"{count}6", f"{count}{16 if wave == '2011-12' else 14}", f"{count}19", "F16", "P17"],
            "15 Econo_Status_2": ["C6", "U6" if wave == "2011-12" else "W6"]}


def registry(root):
    return json.loads((root / BASE / "registry.json").read_text())["source_variables"]


def variable_entry(entries, wave, name):
    matches = [v for v in entries if v["survey_wave"] == wave and v["module_code"] == "employment_current"
               and v["variable_name"].lower() == name.lower()]
    require(len(matches) == 1, f"Unique registered employment variable required: {wave}/{name}")
    return matches[0]


def evidence(root):
    spec, alignment, inventory, extracts = load_inputs(root)
    sheets = {s["source_file"]: s["sheets"] for s in extracts}
    entries = registry(root)
    questions, universes = [], []
    for source in selected_sources(spec, inventory):
        wave = source["survey_wave"]
        cells = sheets[source["source_file"]]
        gates = {sn: {c: cells[sn][c] for c in cols} for sn, cols in gate_cells(wave).items()}
        screen = SCREEN_LAYOUT[wave]
        universes.append({"survey_wave": wave, "minimum_age": screen["minimum_age"],
            "source_file": source["source_file"], "source_sha256": source["source_sha256"],
            "population_instructions": {c: cells[screen['sheets'][0]][c] for c in [screen['universe'], screen['respondent']]},
            "population_sheet": screen["sheets"][0], "gate_cells": gates,
            "documentation_status": source["documentation_status"]})
        for field, (sn, text, code, unit) in zip(FIELDS, layouts(wave), strict=True):
            cell = cells[sn]
            links = [link for link in alignment["source_links"] if link["survey_wave"] == wave
                     and ["final_EC_CSES", field] in link["canonical_keys"]]
            missing_alias = wave == "2009" and field == FIELDS[4]
            require(len(links) == (0 if missing_alias else 1), "Unexpected historical source-link count")
            entry = variable_entry(entries, wave, "q15_c17" if missing_alias else links[0]["variable_name"])
            number = re.fullmatch(r"\((\d+[a-z]?)\)", cell[code].strip())[1]
            raw_suffix = re.search(r"(\d+[a-z]?)(?:_([12]))?$", entry["variable_name"].lower())
            require(raw_suffix is not None and raw_suffix[1].lstrip("0") == number.lstrip("0"), "Printed/raw question mismatch")
            repeated = wave == "2004" and field != FIELDS[0]
            if repeated:
                require(raw_suffix[2] == ("2" if field.startswith("secondary") else "1"), "Repeated job row mismatch")
                require(cells[sn]["C43"] == "1º" and cells[sn]["C44"] == "2º", "Primary/secondary row labels changed")
            candidate = [q for q in inventory["questions"] if q["source_file"] == source["source_file"]
                         and q["source_sheet"] == sn and q["question_code_cell"] == code]
            require(len(candidate) == 1 and text in candidate[0]["text_cell_candidates"], "Question locator must be exact")
            if links and links[0]["candidate_ids"]:
                require(candidate[0]["candidate_id"] in links[0]["candidate_ids"], "Existing candidate identity changed")
            options = parse_options({unit: cell[unit]}) if field in STATUS else []
            if field in STATUS:
                require({o["source_code"] for o in options} == {1, 2, 3, 4, 5}, "Five printed status codes required")
            else:
                require(cell[unit] == ("HOURS" if field in HOURS else "DAYS"), "Numeric unit changed")
                require(("past 7 days" if field in HOURS else "past month") in " ".join(cell[text].split()), "Reference period changed")
            questions.append({"survey_wave": wave, "field": field, "source_file": source["source_file"],
                "source_sha256": source["source_sha256"], "source_sheet": sn,
                "question_text_cell": text, "question_code_cell": code, "unit_or_options_cell": unit,
                "question_text": cell[text], "printed_code": cell[code], "unit_or_options_text": cell[unit],
                "options": options, "option_count": 5 if field in STATUS else None,
                "response_kind": "categorical_source_code" if field in STATUS else "numeric_entry_not_fixed_choices",
                "source_variable_id": entry["source_variable_id"], "source_variable": entry["variable_name"],
                "candidate_id": candidate[0]["candidate_id"], "original_candidate_ids": [] if missing_alias else links[0]["candidate_ids"],
                "correspondence_basis": "recovered_q15_c17_missing_builder_alias" if missing_alias else
                    "repeated_2004_primary_secondary_rows" if repeated else
                    "explicit_2009_printed_A_released_C_subsection" if wave == "2009" else "exact_existing_candidate",
                "canonical_mapping_missing": missing_alias, "documentation_status": source["documentation_status"],
                "minimum_age": screen["minimum_age"], "whole_variable_certified": False, "publication_approved": False})
    require(len(questions) == 49 and len({q['candidate_id'] for q in questions}) == 46, "49 correspondences / 46 printed items required")
    return questions, universes


def clean_numeric(values, upper, sentinels=()):
    import pandas as pd

    numeric = pd.to_numeric(values, errors="coerce")
    valid = numeric.between(0, upper) & numeric.mod(1).eq(0) & ~numeric.isin(sentinels)
    return numeric.where(valid).astype("Int16")


def literal_route(frame, field, wave):
    if wave not in SCREEN_LAYOUT:
        return None
    age = frame.age.ge(SCREEN_LAYOUT[wave]["minimum_age"])
    first = frame.worked_at_least_one_hour_past_7_days.eq(1)
    work = first | frame.second_work_screening_source_code.eq(1)
    if wave == "2004":
        if field == FIELDS[0]:
            return age & work
        return age & frame.total_occupations_past_7_days.ge(2 if field.startswith("secondary") else 1)
    if field in [FIELDS[1], FIELDS[3]]:
        return age & (work if wave == "2021" else first)
    if field.startswith("secondary") or field == FIELDS[0]:
        # Printed Q11=0 skips directly to Q20, including Q19 total hours.
        return age & work & frame.additional_jobs_count.ge(1)
    return age & work


def stata_metadata(source):
    import pandas as pd

    with pd.io.stata.StataReader(io.BytesIO(source.read_bytes()), convert_categoricals=False) as reader:
        names = reader.variable_labels()
        label_sets = reader.value_labels()
        assigned = dict(zip(reader._varlist, reader._lbllist, strict=True))
        return {name: {"variable_label": label or None,
                "value_labels": {str(int(k)): v for k, v in label_sets.get(assigned[name], {}).items()} or None}
                for name, label in names.items()}


def data_review(root, questions):
    import pandas as pd
    from cses_employment import ALIASES, employment_sources, prepare_wave_sources, source_value
    from cses_hh_hl_common import AlignmentContext, clean_code, snake_case

    frame = pd.read_parquet(root / "data/processing/cses/final_EC_CSES.parquet").rename(columns=snake_case)
    require(frame.shape == (332903, 60) and not frame.duplicated(["survey_wave", "person_id"]).any(), "EC grain changed")
    require(not frame[["survey_wave", "person_id"]].isna().any().any(), "EC keys cannot be null")
    aliases = {snake_case(k): v for k, v in ALIASES.items()}
    entries = registry(root)
    profiles, sources, diagnostics, missing_alias = [], [], [], None
    for wave, raw_sources in employment_sources(root):
        ctx = AlignmentContext(root=root)
        keys, aligned = prepare_wave_sources(ctx, wave, raw_sources)
        keys = keys.rename(columns=snake_case)
        current = frame.loc[frame.survey_wave.eq(wave)].set_index("person_id")
        require(len(current) == len(keys) and set(current.index) == set(keys.person_id), "Raw source key mismatch")
        current = current.loc[keys.person_id].reset_index()
        for key in ["household_id", "source_archive", "source_submodule", "source_row_id"]:
            require(current[key].equals(keys[key].astype(current[key].dtype)), "Source provenance mismatch")
        fresh_metadata = {}
        for source in raw_sources:
            fresh_metadata.update(stata_metadata(source))
        # Reproduce the secondary suppression dependency independently from raw counts.
        raw_count, _ = source_value(aligned, aliases["total_occupations_past_7_days" if wave in {"2004", "2007"} else "additional_jobs_count"])
        require(raw_count is not None, "Job-count gate source missing")
        count = clean_numeric(raw_count, 10)
        if wave not in {"2004", "2007"}:
            main_raw, _ = source_value(aligned, aliases["main_occupation_source_code"])
            main, _ = clean_code(main_raw, 3)
            pd.testing.assert_series_equal(main.astype(current.main_occupation_source_code.dtype), current.main_occupation_source_code, check_names=False)
            pd.testing.assert_series_equal(count, current.additional_jobs_count, check_names=False)
            count = (count + 1).where(main.notna()).astype("Int16")
        pd.testing.assert_series_equal(count, current.total_occupations_past_7_days, check_names=False)
        no_secondary = count.notna() & count.lt(2)
        source_fields = []
        for field in FIELDS:
            raw, column = source_value(aligned, aliases[field])
            suppressed = 0
            before = pd.Series(pd.NA, index=current.index, dtype="Int16")
            meta = None
            if column is not None:
                entry = variable_entry(entries, wave, column)
                meta = fresh_metadata[column]
                require(meta == {k: entry[k] for k in ["variable_label", "value_labels"]}, "Fresh Stata labels differ from registry")
                if wave == "2004":
                    label_code = "9" if field in STATUS else "99"
                    require(meta["value_labels"][label_code] == "missing", "2004 explicit missing label changed")
                    if field == FIELDS[0]:
                        require(meta["value_labels"]["96"] == "96 and more hours", "2004 hours topcode label changed")
                before = clean_numeric(raw, 168 if field in HOURS else 31 if field in DAYS else 9999,
                                       (98, 99) if field not in STATUS else ())
            expected = before.copy()
            if field.startswith("secondary"):
                suppressed = int((no_secondary & before.notna()).sum())
                expected = expected.mask(no_secondary)
            pd.testing.assert_series_equal(expected.astype(current[field].dtype), current[field], check_names=False)
            raw_num = pd.to_numeric(raw, errors="coerce") if raw is not None else before
            q = next((q for q in questions if q["survey_wave"] == wave and q["field"] == field), None)
            labels = (meta or {}).get("value_labels") or {}
            source_fields.append({"field": field, "source_variable": column, "source_variable_id": entry["source_variable_id"] if column else None,
                "fresh_stata_metadata": meta, "raw_values": value_counts(raw_num), "raw_null": int(raw_num.isna().sum()),
                "existing_cleaner_discarded_codes": value_counts(raw_num.loc[raw_num.notna() & before.isna()]),
                "existing_secondary_suppression_count": suppressed, "raw_to_canonical_equal": True})
            route = literal_route(current, field, wave)
            observed = current[field].notna()
            profiles.append({"survey_wave": wave, "field": field, "rows": len(current), "source_variable": column,
                "nonnull": int(observed.sum()), "null": int((~observed).sum()), "values": value_counts(current[field]),
                "minimum": int(current[field].min()) if observed.any() else None,
                "maximum": int(current[field].max()) if observed.any() else None,
                "option_count": q["option_count"] if q else 5 if field in STATUS and wave == "2019" else None,
                "option_basis": "questionnaire" if q and field in STATUS else "embedded_stata_labels" if field in STATUS and wave == "2019" else None,
                "literal_route_records": int(route.fillna(False).sum()) if route is not None else None,
                "nonnull_in_route": int((observed & route.fillna(False)).sum()) if route is not None else None,
                "nonnull_outside_known_route": int((observed & route.eq(False).fillna(False)).sum()) if route is not None else None,
                "route_unknown": int(route.isna().sum()) if route is not None else None,
                "non_null_raw_before_cleaning": int(raw_num.notna().sum()), "discarded_by_numeric_cleaner": int((raw_num.notna() & before.isna()).sum()),
                "suppressed_by_job_count": suppressed,
                "status_codes_outside_printed_1_to_5": value_counts(current[field].loc[observed & ~current[field].isin(range(1, 6))]) if field in STATUS and (q or wave == "2019") else None,
                "retained_labelled_missing": {code: int(current[field].eq(int(code)).sum()) for code, label in labels.items() if label.lower() == "missing"},
                "whole_variable_certified": False})
        if wave == "2009":
            recovered, column = source_value(aligned, ["q15_c17"])
            require(column == "q15_c17" and current[FIELDS[4]].isna().all(), "Missing-alias baseline changed")
            recovered_entry = variable_entry(entries, wave, column)
            require(fresh_metadata[column] == {k: recovered_entry[k] for k in ["variable_label", "value_labels"]}, "Recovered source labels changed")
            proposed = clean_numeric(recovered, 31, (98, 99)).mask(no_secondary)
            missing_alias = {"survey_wave": wave, "field": FIELDS[4], "source_variable": column,
                "source_variable_id": variable_entry(entries, wave, column)["source_variable_id"],
                "raw_nonnull": int(recovered.notna().sum()), "raw_values": value_counts(recovered),
                "candidate_nonnull_after_existing_cleaning_and_secondary_gate": int(proposed.notna().sum()),
                "secondary_suppressed": int((recovered.notna() & no_secondary).sum()),
                "canonical_nonnull": 0, "current_alias_list": aliases[FIELDS[4]],
                "fresh_stata_metadata": fresh_metadata[column], "proposed_only": True}
        complete = current[HOURS].notna().all(axis=1)
        total, main, second = [current[f] for f in HOURS]
        topcoded = current.survey_wave.eq("2004") & total.eq(96)
        exact_comparable = complete & ~topcoded.fillna(False)
        diagnostics.append({"survey_wave": wave, "rows": len(current),
            "any_batch_value": int(current[FIELDS].notna().any(axis=1).sum()),
            "all_seven_nonnull": int(current[FIELDS].notna().all(axis=1).sum()),
            "hl_unmatched": int(current.hl_link_matched.eq(0).sum()), "missing_age": int(current.age.isna().sum()),
            "three_hour_fields_nonnull": int(complete.sum()), "exact_hour_comparison_excludes_topcode": int(exact_comparable.sum()),
            "total_less_than_main_plus_secondary": int((exact_comparable & total.lt(main + second)).sum()),
            "total_equals_main_plus_secondary": int((exact_comparable & total.eq(main + second)).sum()),
            "total_greater_than_main_plus_secondary": int((exact_comparable & total.gt(main + second)).sum()),
            "total_hours_2004_96_plus": int(topcoded.sum()),
            "actual_interview_respondents": None})
        sources.append({"survey_wave": wave, "sources": [{"source_file": s.display_name(root), "sha256": digest(s.read_bytes())} for s in raw_sources],
                        "fields": source_fields, "secondary_gate_reproduced_from_raw": True})
    require(len(profiles) == 70 and missing_alias is not None, "Incomplete seven-field batch")
    require(sum(p["source_variable"] is not None for p in profiles) == 63, "Existing mapping count differs")
    return frame, profiles, sources, diagnostics, missing_alias


def check_database(frame):
    import pandas as pd
    from cses_baseline_metadata import connect_database
    from psycopg import sql

    columns = CONTEXT + FIELDS
    with connect_database({"dbname": "mda"}) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        conn.execute("SET LOCAL statement_timeout='55s'")
        require(conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on", "Read-only required")
        live = pd.DataFrame(conn.execute(sql.SQL('SELECT {} FROM cses_data."final_EC_CSES" ORDER BY survey_wave,person_id').format(
            sql.SQL(",").join(map(sql.Identifier, columns)))).fetchall()).astype(frame[columns].dtypes.to_dict())
        pd.testing.assert_frame_equal(live, frame[columns].sort_values(["survey_wave", "person_id"]).reset_index(drop=True), check_exact=True)
    return {"rows": len(frame), "selected_columns": columns, "all_selected_values_equal": True,
            "transaction_read_only": True, "database_mutated": False, "full_60_field_validation": False}


def make_review(root, verification, live):
    from plan_cses_age_topcode import checked_review

    checked_review(root)
    require(digest((root / PRIOR).read_bytes()) == PRIOR_SHA, "Preserved screening review changed")
    prior = json.loads((root / PRIOR).read_text())
    require(digest((root / "rsc/cses_db/review_cses_employment_screening.py").read_bytes()) == prior["implementation_sha256"], "Frozen screening implementation changed")
    require(digest((root / BUILDER).read_bytes()) == BUILDER_SHA, "Frozen employment builder changed")
    verified = json.loads(verification.read_text())
    require(verified["source_cells_sha256"] == digest((root / BASE / "source_cells.json").read_bytes()), "Workbook baseline changed")
    require(verified["implementation_sha256"] == digest((root / "rsc/cses_db/review_cses_education.py").read_bytes()), "Workbook verifier changed")
    require(len(verified["sources"]) == 7 and all(s["all_sheets_equal"] for s in verified["sources"]), "Seven fresh workbook checks required")
    questions, universes = evidence(root)
    frame, profiles, sources, diagnostics, recovery = data_review(root, questions)
    return {"review_id": "cses-employment-hours-status-review-v1", "implementation_sha256": digest((root / SELF).read_bytes()),
        "employment_builder_sha256": BUILDER_SHA, "prior_screening_review_sha256": PRIOR_SHA,
        "canonical_parquet_sha256": digest((root / "data/processing/cses/final_EC_CSES.parquet").read_bytes()),
        "source_verification": verified, "questions": questions, "universes": universes,
        "profiles": profiles, "raw_sources": sources, "wave_counts": diagnostics, "missing_alias_candidate": recovery,
        "database_check": check_database(frame) if live else {"performed": False},
        "scope_counts": {"rows": len(frame), "physical_fields": 60, "employment_fields": 39, "batch_fields": 7,
            "cumulative_reviewed_fields": 11, "remaining_employment_fields": 28, "question_wave_correspondences": 49,
            "distinct_printed_items": 46, "field_wave_profiles": 70, "existing_raw_field_wave_mappings": 63,
            "recovered_missing_aliases": 1, "fully_certified_all_ten_wave_fields": 0},
        "database_mutated": False, "canonical_data_mutated": False, "individual_records_saved": False,
        "new_value_publication_approved": False}


def documents(r):
    return render_brief(r), render_details(r)


def render_brief(r):
    lines = ["# CSES employment hours, workdays and status", "",
        "This second EC batch reviews seven fields across 332,903 member-wave records. Together with the "
        "[screening batch](cses-employment-screening-alignment.md), 11 of 39 employment fields have now been examined; "
        "28 remain outside these batches. Reviewed does not mean fully comparable: **none of these seven fields is certified across all ten waves**. "
        "The original 60-column EC table, baseline Parquet and database catalog are unchanged.", "",
        "## Fields and response types", "", "| Field | Recorded quantity | Printed choices |", "| --- | --- | --- |"]
    for f in FIELDS:
        lines.append(f"| `{f}` | {'Weekly hours' if f in HOURS else 'Workdays in past month' if f in DAYS else 'Employment status for the named job'} | "
                     + ("Five categories, 1–5, in all seven inspected forms" if f in STATUS else "Numeric entry, not a fixed-choice question") + " |")
    lines += ["", "Status labels are Employee (Paid employee in 2004), Employer, Own account worker/self-employed, "
        "Unpaid/contributing family worker, and Other. Exact wording is retained in the evidence. This is a job-level status, "
        "not employer ownership and not a labour-force classification. Fresh 2019 Stata labels separately support its five status codes, "
        "but do not establish missing household-form routes. The 2014 draft remains provisional; 2007/2017 lack verified household forms "
        "and the 2019 image-form transcription remains pending.", "",
        "## Findings requiring a follow-up release", "",
        f"1. **2009 secondary workdays were not mapped.** Original `q15_c17` (source variable 989) contains {r['missing_alias_candidate']['raw_nonnull']:,} "
        f"non-null values. All {r['missing_alias_candidate']['candidate_nonnull_after_existing_cleaning_and_secondary_gate']:,} remain eligible after the existing numeric and secondary-job rules. "
        "The canonical field is entirely NULL because its alias list omits `q15_c17`. The questionnaire locates the item at "
        "`15 Econo_Status_2!G4/G16`, unit `G15`. This is a missing mapping, not evidence that the question was not collected. "
        "The recovery is proposed only; no values were filled."]
    missing = [p for p in r["profiles"] if p["survey_wave"] == "2004" and p["field"] in STATUS]
    topcode = next(w["total_hours_2004_96_plus"] for w in r["wave_counts"] if w["survey_wave"] == "2004")
    lines += [f"2. **2004 status code 9 is labelled missing in the original Stata files.** It remains as a raw code in "
        f"{missing[0]['retained_labelled_missing'].get('9', 0):,} main-job and {missing[1]['retained_labelled_missing'].get('9', 0):,} secondary-job canonical cells. "
        "It must not be treated as a sixth employment category. These are field-cell counts that may overlap in people; "
        "a future qualified analysis overlay can expose NULL while preserving original codes.",
        f"3. **2004 total-hours code 96 means 96 or more hours**, according to its fresh Stata value label. "
        f"There are {topcode:,} such records. Preserve 96 as the lower bound; exact weekly hours are unknown. "
        "Do not read these as exactly 96 or as an ordinary missing code. The existing table has not yet gained a hours-topcode qualifier.",
        "4. The inherited hourly cleaner drops 98/99 in every wave. Only wave/variable-specific labels establish their meanings. "
        "Located hour-question cells do not document a universal 98/99 convention. The detail report shows the affected raw codes; "
        "do not automatically restore or reinterpret unlabelled values.", "",
        "Three-field hours reconciliation also finds total below main plus secondary in 1,798 records in 2004, "
        "310 in 2019 and 304 in 2021, after excluding the identified top-coded totals. These 2,412 inconsistencies "
        "need source-level follow-up; no component is overwritten and no cause is inferred here.", "",
        "## Population, routing and interpretation", "",
        "Printed eligibility is age 10+ in 2004 and 5+ in the six inspected later forms. Age/route rules are unknown for "
        "2007/2017/2019, not borrowed from neighbours. These counts are unweighted table records, not actual interview respondents.", "",
        "- 2004 repeats three Part B columns in primary and secondary job rows. Six source variables map to three printed items, "
        "with `C43=1º` / `C44=2º` and `_1` / `_2` suffixes retaining the job identity.",
        "- Main-job hours and monthly days in the inspected 2009–2016 forms require first-screen Yes. "
        "The 2021 gate accepts first OR second screen Yes, including the unpaid-work branch.",
        "- In inspected 2009–2021 forms, Q11=0 skips to Q20, bypassing the secondary-job block **and Q19 total hours**. "
        "Hence the literal Q19 route is not all workers. Released values outside this printed route are retained and counted. "
        "Do not substitute main hours for missing total hours without an explicit derivation rule.",
        "- Existing cleaning removes secondary-job values when the canonical number of occupations is known to be below two. "
        "Unknown job counts do not trigger that suppression. Its raw count and main-occupation dependencies were reproduced; "
        "their broader semantics are not newly certified.",
        "- Total weekly hours may include jobs beyond the main and secondary job. A positive difference is not automatically an error. "
        "The reconciliation requires all three values and excludes 2004 top-coded totals; missing components are not replaced with zero.", "",
        "| Wave | EC records | Any of seven non-null | All seven non-null | Unmatched HL |", "| --- | ---: | ---: | ---: | ---: |"]
    for w in r["wave_counts"]:
        lines.append(f"| {w['survey_wave']} | {w['rows']:,} | {w['any_batch_value']:,} | {w['all_seven_nonnull']:,} | {w['hl_unmatched']:,} |")
    lines += ["", "All-seven completeness is a diagnostic, not a recommended analysis sample: secondary fields are structurally inapplicable "
        "for many records. The 2007 selected source does not provide six job-detail aliases; those fields remain NULL, "
        "without claiming no other archive could contain related information. 2004 general sampling weights remain unavailable.", "",
        "## Evidence and verification", "",
        "[Field-wave denominators and source locators](cses-employment-hours-status-field-waves.md) include original non-null counts, "
        "numeric-cleaning exclusions, secondary suppression, literal-route diagnostics and exact printed option cells. "
        "[Machine-readable review](../data/processing/cses/employment_hours_status_review_v1/review.json) retains original labels, "
        "49 field/question correspondences (46 distinct printed items), 70 profiles and source hashes. "
        "Seven original questionnaires were freshly re-extracted, all sheets compared with frozen cells, and original Stata labels re-read. "
        "All 63 existing raw-field mappings were reproduced, alongside the separately proposed missing 2009 alias.", "",
        ("A forced read-only database comparison matched all selected values across 332,903 records and 16 columns "
         "(seven reviewed fields plus nine identity/context/dependency columns). This is not a full 60-column validation."
         if r["database_check"].get("all_selected_values_equal") else "Live database validation was not performed."), "",
        "```mermaid", "flowchart LR", '    Q["7 original forms + Stata labels"] --> E["49 correspondences / 46 printed items"]',
        '    R["11 released data files"] --> C["63 reproduced mappings + 1 omitted alias"]',
        '    E --> D["Work periods, job rows, routes and missing/top codes"]', '    C --> D',
        '    D --> P["Proposed corrections; no database write"]', "```", "",
        "This local review topology does not modify published database graph v12. Earlier screening/education reviews and publishers "
        "remain frozen. Spreadsheet guidance informed unit checks, repeated-row mapping and preservation of raw observations.", "",
        "Reproduce original-workbook verification using the bundled runtime with "
        "`rsc/cses_db/review_cses_employment_hours_status.py --verify-workbooks --soffice /path/to/bundled/soffice`, then run "
        "`.venv/bin/python rsc/cses_db/review_cses_employment_hours_status.py --check-database`. Use a fresh `--output` and "
        "`--docs-dir` for a changed review snapshot. No Git/DVC archival is implied.", "",
        "Next prepare a bounded correction proposal for the omitted 2009 alias, 2004 labelled missing status and 2004 hours topcoding. "
        "Occupation/industry and employer type follow as the next new field batch. No physical-data or metadata publication occurs in this review.", ""]
    return "\n".join(lines)


def render_details(r):
    lines = ["# CSES employment hours and status field-wave profiles", "",
        "Companion to the [batch brief](cses-employment-hours-status-alignment.md). Counts are member-wave records, not actual interview respondents. "
        "Routes are diagnostics, not adopted statistical denominators. Numeric-cleaner and secondary-gate removals are disjoint stages.", ""]
    for f in FIELDS:
        lines += [f"## {f}", "", "| Wave | Rows | Raw non-null | Canonical non-null | NULL | Numeric removals | Secondary removals | In route | Non-null outside known route | Route unknown |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for p in r["profiles"]:
            if p["field"] != f:
                continue
            ks = ["rows", "non_null_raw_before_cleaning", "nonnull", "null", "discarded_by_numeric_cleaner", "suppressed_by_job_count",
                  "literal_route_records", "nonnull_outside_known_route", "route_unknown"]
            lines.append("| " + " | ".join([p["survey_wave"], *[f"{p[k]:,}" if p[k] is not None else "Not assessed" for k in ks]]) + " |")
        lines.append("")
    lines += ["The 2009 secondary-days raw column is omitted by the existing alias list; its row above describes the "
              "existing transformation (no selected raw column). The separate recovery below exposes the actual original values.", "",
              "## Source question locators", "", "Status has five printed options. Hours/days are numeric entries without a fixed option count. "
              "The 2004 main/secondary pairs share a printed item but use distinct repeated job rows.", "",
              "| Wave | Field | Source variable | Sheet | Text / code / unit or options | Evidence |",
              "| --- | --- | --- | --- | --- | --- |"]
    for q in r["questions"]:
        lines.append(f"| {q['survey_wave']} | {q['field']} | {q['source_variable']} | {q['source_sheet']} | "
                     f"{q['question_text_cell']} / {q['question_code_cell']} / {q['unit_or_options_cell']} | {q['documentation_status']} |")
    lines += ["", "## Codes removed by the inherited numeric cleaner", "",
              "Listed codes are not automatically certified missing. In 2004 the fresh labels explicitly identify 99 as missing for "
              "the five numeric fields. The inspected numeric-question cells do not define a universal 98/99 convention.", "",
              "| Wave | Field | Raw value | Cells | Embedded label |", "| --- | --- | ---: | ---: | --- |"]
    for src in r["raw_sources"]:
        for f in src["fields"]:
            labels = (f["fresh_stata_metadata"] or {}).get("value_labels") or {}
            for code, n in f["existing_cleaner_discarded_codes"].items():
                lines.append(f"| {src['survey_wave']} | {f['field']} | {code} | {n:,} | {labels.get(code, 'Not labelled')} |")
    lines += ["", "## Retained status codes outside printed 1–5", "", "| Wave | Field | Code | Cells |", "| --- | --- | ---: | ---: |"]
    for p in r["profiles"]:
        for code, n in (p["status_codes_outside_printed_1_to_5"] or {}).items():
            lines.append(f"| {p['survey_wave']} | {p['field']} | {code} | {n:,} |")
    lines += ["", "## Status value counts", "", "Original codes, not a pooled status dictionary. "
              "Codes 1–5 have source-questionnaire support in seven waves and embedded-label support in 2019; "
              "2017 meanings remain unverified despite matching numeric codes. Other includes retained missing code 9 in 2004. "
              "Counts are before any proposed analysis recode.", "",
              "| Wave | Job | Code 1 | Code 2 | Code 3 | Code 4 | Code 5 | Other code | NULL |",
              "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for p in r["profiles"]:
        if p["field"] in STATUS:
            numbers = [p["values"].get(str(code), 0) for code in range(1, 6)]
            numbers += [p["nonnull"] - sum(numbers), p["null"]]
            lines.append("| " + " | ".join([p["survey_wave"], p["field"].split('_')[0], *[f"{n:,}" for n in numbers]]) + " |")
    recovery = r["missing_alias_candidate"]
    lines += ["", "## Omitted 2009 secondary-days source", "",
              f"`q15_c17` has {recovery['raw_nonnull']:,} non-null original values and "
              f"{recovery['candidate_nonnull_after_existing_cleaning_and_secondary_gate']:,} proposed recoverable cells. "
              f"The existing secondary gate would suppress {recovery['secondary_suppressed']:,} of the raw values. "
              "The canonical field is currently all NULL. The source question is verified; no correction is published here.", "",
              "## Hours reconciliation", "", "Complete three-field rows only; exclude 2004 total=96 because it is top-coded. "
              "Greater-than can include third and further jobs and is not automatically an error. Less-than is a retained inconsistency, "
              "not an instruction to overwrite any component.", "",
              "| Wave | Complete, excluding topcode | Total < main + secondary | Equal | Greater | 2004 total 96+ |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for w in r["wave_counts"]:
        lines.append("| " + " | ".join([w['survey_wave'], *[f"{w[k]:,}" for k in ["exact_hour_comparison_excludes_topcode",
            "total_less_than_main_plus_secondary", "total_equals_main_plus_secondary", "total_greater_than_main_plus_secondary", "total_hours_2004_96_plus"]]]) + " |")
    return "\n".join(lines) + "\n"


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
        require(args.soffice, "Explicit bundled converter required")
        write_once(output / "source_verification.json", verify_workbooks(args.root, args.soffice))
    else:
        result = make_review(args.root, output / "source_verification.json", args.check_database)
        brief, details = documents(result)
        write_once(output / "review.json", result)
        write_once(args.root / args.docs_dir / "cses-employment-hours-status-alignment.md", brief)
        write_once(args.root / args.docs_dir / "cses-employment-hours-status-field-waves.md", details)
        print(json.dumps(result["scope_counts"]))


if __name__ == "__main__":
    main()
