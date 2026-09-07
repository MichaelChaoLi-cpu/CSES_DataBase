#!/usr/bin/env python3
"""Audit the final 19 EC fields; findings only, with frozen releases unchanged."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from organize_cses_questionnaires import digest, write_once
from review_cses_education import BASE, load_inputs, normalize_legacy_source_paths, selected_sources, verify_workbooks
from review_cses_employment_classification import FIELDS as CLASS_FIELDS
from review_cses_employment_hours_status import FIELDS as HOURS_FIELDS
from review_cses_employment_hours_status import registry, stata_metadata, variable_entry
from review_cses_employment_screening import FIELDS as SCREEN_FIELDS
from review_cses_employment_screening import LAYOUT as SCREEN
from review_cses_main_job_seasonal import CURRENT, CURRENT_SHA
from review_cses_main_job_whole_year import CONTEXT, EXECUTION, PINS, counts
from review_cses_questionnaires import parse_options, require

SELF = "rsc/cses_db/review_cses_employment_remaining.py"
OUTPUT = "data/processing/cses/employment_remaining_review_v1"
PRIOR = "data/processing/cses/main_job_abroad_review_v1/review.json"
PRIOR_SHA = "8f37b738b54a2d53e6f75836aef8f845ec22474861ad30d871e75174002031a4"
FIELDS = [
    "additional_jobs_count",
    "total_occupations_past_7_days",
    "secondary_job_works_whole_year",
    "secondary_job_was_usual_past_7_days",
    "monthly_salary_wages_riel",
    "preferred_hours_change_source_code",
    "hours_less_preferred",
    "hours_more_preferred",
    "available_for_additional_work",
    "reason_working_fewer_hours_source_code",
    "months_working_fewer_hours",
    "job_search_method_1_source_code",
    "job_search_method_2_source_code",
    "job_search_method_3_source_code",
    "desired_weekly_hours",
    "months_actively_seeking_work",
    "reason_not_actively_seeking_source_code",
    "months_out_of_work",
    "latest_work_seasonal",
]
PRIOR_FIELDS = (
    SCREEN_FIELDS
    + HOURS_FIELDS
    + CLASS_FIELDS
    + ["main_job_works_whole_year", "main_job_was_usual_past_7_days", "main_job_was_abroad"]
)
BINARY = {FIELDS[i] for i in [2, 3, 8, 18]}
CATEGORICAL = {FIELDS[i] for i in [5, 9, 11, 12, 13, 16]}
HOURS = {FIELDS[i] for i in [6, 7, 14]}
DURATIONS = {FIELDS[i] for i in [10, 15, 17]}
METHODS = FIELDS[11:14]
ITEMS = [
    "11",
    "11",
    "17b",
    "17c",
    "20",
    "21",
    "22a",
    "22b",
    "23",
    "24",
    "25",
    "27a",
    "27b",
    "27c",
    "29",
    "30",
    "31",
    "32",
    "33",
]
MEANINGS = [
    "Additional jobs/economic activities beyond the main job in the past seven days. Zero means no additional job.",
    "Total occupation count: directly reported in 2004/2007; later derived as additional jobs plus one only when a main occupation code is present.",
    "Whether the secondary occupation is worked throughout the whole year.",
    "Whether the secondary occupation during the past seven days is seasonal. The legacy word usual is a naming error, not a polarity error.",
    "Salary/wages last month from all jobs/economic activities, cash or in kind, nominal Cambodian riel. Not household income, not main-job-only income.",
    "Preference for fewer, more or unchanged hours, conditional on corresponding income changes in 2009 onward.",
    "Number of hours to subtract from the past-seven-day hours, not the desired total.",
    "Number of hours to add to the past-seven-day hours, not the desired total.",
    "Availability to work more hours during the past seven days or start within two weeks, if more hours are preferred.",
    "Reason for working fewer hours than preferred, if more hours are preferred; not restricted to those available for extra work.",
    "Months of working fewer hours than desired while available for more work; zero is less than one month in later inspected forms.",
    "First recorded job-search method slot, not a ranking or a separate question.",
    "Second optional recorded job-search method slot, not a ranking or a separate question.",
    "Third optional recorded job-search method slot, not a ranking or a separate question.",
    "Desired total weekly hours. In 2004 both workers wanting different hours and nonworkers can reach the item; later forms route jobseekers here.",
    "Months out of work and actively looking for work, distinct from total months out of work.",
    "Reason for not actively seeking work in the past four weeks; codes 6–8 bypass the later out-of-work items in 2011 onward.",
    "Total months out of work, looking or not looking, reached through the non-seeking route in the inspected later forms.",
    "Whether the latest job was seasonal, asked after less than 13 months out of work in the inspected later forms. Not current main/secondary seasonality.",
]


def coverage():
    from cses_employment import EC_MODULE_COLUMNS
    from cses_hh_hl_common import snake_case

    all_fields = [snake_case(f) for f in EC_MODULE_COLUMNS]
    require(len(PRIOR_FIELDS) == len(set(PRIOR_FIELDS)) == 20, "Previous field set changed")
    require(len(FIELDS) == len(set(FIELDS)) == 19 and not set(FIELDS) & set(PRIOR_FIELDS), "Final batch overlaps")
    require(set(all_fields) == set(PRIOR_FIELDS + FIELDS), "Exactly all 39 EC fields must be covered")
    return all_fields


def locator(wave, index):
    """Explicit question and shared-text anchors, not inferred from nearby headings."""
    if wave == "2004":
        return {
            1: ("13 Econ. Status", "AS15", "AS", "12"),
            11: ("13 Econ. Status", "AD15", "AD", "9a"),
            12: ("13 Econ. Status", "AF15", "AD", "9b"),
            13: ("13 Econ. Status", "AH15", "AD", "9c"),
            14: ("13 Econ. Status", "AJ15", "AJ", "10"),
        }.get(index)
    if wave == "2009":
        cols = {0: "CJ", 1: "CJ", 4: "W", 5: "AM", 8: "AX", 9: "BD", 11: "CB", 12: "CD", 13: "CF", 14: "CM", 16: "CV"}
        if index not in cols:
            return None
        return (
            "15 Econo_Status_1" if index in [0, 1] else "15 Econo_Status_2",
            cols[index] + "16",
            "CB" if index in [11, 12, 13] else cols[index],
            ITEMS[index],
        )
    if wave not in ["2011-12", "2013", "2014", "2016", "2021"]:
        return None
    cols = ["CW" if wave == "2011-12" else "CX"] * 2 + [
        "K" if wave == "2011-12" else "J",
        "P" if wave == "2011-12" else "M",
        "AS",
        "BA",
        "BG",
        "BL",
        "BQ",
        "BY",
        "CE",
        "CR",
        "CT",
        "CV",
        "DC",
        "DQ",
        "DW",
        "EF",
        "EL",
    ]
    row = 19
    sheet = "15 Econo_Status_1" if index in [0, 1] else "15 Econo_Status_2"
    if wave == "2021":
        cols[:2] = ["AE", "AE"]
        cols[15:] = ["DL", "DR", "EA", "EG"]
        row = 24 if index in [0, 1] else 25
        sheet = "15 Current Econo-2" if index in [0, 1] else "15 Current Econo-4"
    return sheet, cols[index] + str(row), "CR" if index in [11, 12, 13] else cols[index], ITEMS[index]


def block(cells, col, row, minrow):
    return {
        c: t for c, t in cells.items() if re.sub(r"\d", "", c) == col and minrow <= int(re.search(r"\d+", c)[0]) <= row
    }


def evidence(root):
    spec, alignment, inventory, extracts = load_inputs(root)
    sheets = {s["source_file"]: s["sheets"] for s in extracts}
    questions, universes, related = [], [], []
    for source in selected_sources(spec, inventory):
        wave = source["survey_wave"]
        ws = sheets[source["source_file"]]
        screen = SCREEN[wave]
        sn = screen["sheets"][0]
        universes.append(
            {
                "survey_wave": wave,
                "source_file": source["source_file"],
                "source_sheet": sn,
                "minimum_age": screen["minimum_age"],
                "cells": {c: ws[sn][c] for c in [screen["universe"], screen["respondent"]]},
                "documentation_status": source["documentation_status"],
                "screen_gate": {c: ws[screen["sheets"][2]][c] for c in [screen["seek_gate"], *screen["options"][2]]},
            }
        )
        for j, field in enumerate(FIELDS):
            loc = locator(wave, j)
            if loc is None:
                continue
            sn, code, col, number = loc
            cells = ws[sn]
            row = int(re.search(r"\d+", code)[0])
            require(cells[code].strip() == f"({number})", f"Printed number mismatch: {wave}/{field}")
            candidate_code = col + str(row) if field in METHODS else code
            q = [
                q
                for q in inventory["questions"]
                if q["source_file"] == source["source_file"]
                and q["source_sheet"] == sn
                and q["question_code_cell"] == candidate_code
            ]
            require(len(q) == 1, "Unique exact question candidate required")
            links = [
                r
                for r in alignment["source_links"]
                if r["survey_wave"] == wave and ["final_EC_CSES", field] in r["canonical_keys"]
            ]
            if j == 1 and wave != "2004":
                links = [
                    r
                    for r in alignment["source_links"]
                    if r["survey_wave"] == wave and ["final_EC_CSES", FIELDS[0]] in r["canonical_keys"]
                ]
            require(len(links) == 1, f"Unique source mapping required: {wave}/{field}")
            link = links[0]
            text = block(cells, col, row, 11 if wave == "2021" else 4)
            text[code] = cells[code]
            opt_cells = {c: t for c, t in text.items() if re.search(r"(?m)^\s*\d+\s*=", t)}
            opts = parse_options(opt_cells) if field in BINARY | CATEGORICAL else []
            expected = (
                set(range(1, 7))
                if field in METHODS
                else {1, 2, 3}
                if j in [5, 9]
                else set(range(1, 10))
                if j == 16
                else {1, 2}
                if field in BINARY
                else set()
            )
            require({o["source_code"] for o in opts} == expected, f"Choice set changed: {wave}/{field}")
            questions.append(
                {
                    "survey_wave": wave,
                    "field": field,
                    "meaning": MEANINGS[j],
                    "source_file": source["source_file"],
                    "source_sha256": source["source_sha256"],
                    "source_sheet": sn,
                    "question_code_cell": code,
                    "printed_number": number,
                    "literal_cells": text,
                    "options": opts,
                    "option_count": len(opts) if opts else None,
                    "response_kind": "categorical" if opts else "numeric_or_derived_count",
                    "candidate_id": q[0]["candidate_id"],
                    "candidate_code_cell": candidate_code,
                    "shared_question_with_individual_slot": field in METHODS,
                    "historical_candidate_ids": link["candidate_ids"],
                    "source_variable": link["variable_name"],
                    "source_variable_id": link["source_variable_id"],
                    "mapping_basis": "derived total from additional count + main occupation presence"
                    if j == 1 and wave != "2004"
                    else "exact printed item and raw alias; shared method wording for three slots",
                    "documentation_status": source["documentation_status"],
                    "whole_variable_certified": False,
                }
            )
        # Related earlier items are not automatically equated or used to fill canonical NULLs.
        rel = {
            "2004": [
                ("13 Econ. Status", "S15", "S", 4),
                ("13 Econ. Status", "AM15", "AM", 4),
                ("13 Econ. Status", "AP15", "AP", 4),
                ("13 Econ. Status", "AQ42", "AQ", 29),
            ],
            "2009": [
                ("15 Econo_Status_2", "AS16", "AS", 4),
                ("15 Econo_Status_2", "BJ16", "BJ", 4),
                ("15 Econo_Status_2", "BN16", "BN", 4),
                ("15 Econo_Status_2", "CP16", "CP", 4),
                ("15 Econo_Status_2", "CS16", "CS", 4),
            ],
        }.get(wave, [])
        for sn, code, col, minrow in rel:
            related.append(
                {
                    "survey_wave": wave,
                    "source_file": source["source_file"],
                    "source_sha256": source["source_sha256"],
                    "source_sheet": sn,
                    "question_code_cell": code,
                    "literal_cells": block(ws[sn], col, int(re.search(r"\d+", code)[0]), minrow),
                    "used_to_fill_canonical": False,
                }
            )
        # Preserve the bypasses and gates not in the same column as a reviewed question.
        if wave != "2004":
            sn = "15 Current Econo-4" if wave == "2021" else "15 Econo_Status_2"
            cs = ws[sn]
            gates = ["C12"] if wave == "2021" else ["C6"] if wave != "2009" else []
            universes[-1]["secondary_gate"] = {c: cs[c] for c in gates}
    return questions, universes, related


def numeric(values, upper, sentinels=(), dtype="Int16"):
    import pandas as pd

    n = pd.to_numeric(values, errors="coerce")
    return n.where(n.ge(0) & n.le(upper) & n.mod(1).eq(0) & ~n.isin(sentinels)).astype(dtype)


def transform(raw, field, index):
    import pandas as pd

    dtype = "Int8" if field in BINARY else "Float64" if field == FIELDS[4] else "Int16"
    if raw is None:
        return pd.Series(pd.NA, index=index, dtype=dtype)
    if field in BINARY:
        return pd.to_numeric(raw, errors="coerce").map({1: 1, 2: 0}).astype(dtype)
    if field == FIELDS[4]:
        n = pd.to_numeric(raw, errors="coerce")
        return n.mask(n.lt(0) | n.isin([9999999, 99999999, 999999999])).astype(dtype)
    if field in HOURS:
        return numeric(raw, 168, [98, 99])
    if field in DURATIONS:
        return numeric(raw, 97, [98, 99])
    return numeric(raw, 10 if field in FIELDS[:2] else 9999)


def route(f, wave, field, raw_extras):
    """Literal questionnaire route with nullable unknowns; never a data filter."""
    if wave not in SCREEN or locator(wave, FIELDS.index(field)) is None:
        return None
    age = f.age.ge(SCREEN[wave]["minimum_age"])
    work = f.worked_at_least_one_hour_past_7_days.eq(1) | f.second_work_screening_source_code.eq(1)
    nonwork = f.worked_at_least_one_hour_past_7_days.eq(0) & f.second_work_screening_source_code.eq(2)
    seek = f.actively_seeking_work.eq(1)
    pref = f[FIELDS[5]]
    if wave == "2004":
        if field == FIELDS[1]:
            return age
        if field in METHODS:
            return age & nonwork & seek
        # Workers preferring less/more jump to 10; nonworkers reach 10 after 8/9.
        preference = numeric(raw_extras["q13a06"], 9)
        return age & ((work & (preference.eq(2) | preference.eq(3))) | nonwork)
    employed = age & work
    if field in FIELDS[:2]:
        return employed
    if field in FIELDS[2:4]:
        base = employed & f[FIELDS[0]].ge(1)
        return base if field == FIELDS[2] else base & f[FIELDS[2]].eq(0)
    if field == FIELDS[4]:
        return employed & (f.main_employment_status_source_code.eq(1) | f.secondary_employment_status_source_code.eq(1))
    if field == FIELDS[5]:
        return employed
    if field == FIELDS[6]:
        return employed & pref.eq(1)
    if field in [FIELDS[7], FIELDS[8], FIELDS[9]]:
        return employed & pref.eq(2)
    if field == FIELDS[10]:
        return employed & pref.eq(2) & f[FIELDS[8]].eq(1)
    if field in METHODS + [FIELDS[14], FIELDS[15]]:
        return age & nonwork & seek
    base = age & nonwork & f.actively_seeking_work.eq(0)
    if field == FIELDS[16]:
        return base
    # Printed 6-8 bypass out-of-work duration and latest-seasonal item.
    reason = f[FIELDS[16]]
    allowed = reason.isin([1, 2, 3, 4, 5, 9]).astype("boolean").mask(reason.isna() | ~reason.isin(range(1, 10)))
    base &= allowed
    return base if field == FIELDS[17] else base & f[FIELDS[17]].lt(13)


SUPPLEMENTAL = {
    "2004": ["q13a06", "q13a11a", "q13a11b", "q13b08_1", "q13b08_2"],
    "2007": ["q13ac06", "q13ac09", "q13ac10", "q13ac13a", "q13ac13b"],
    "2009": ["q15_c22", "q15_c25a", "q15_c25b", "q15_c30a", "q15_c30b"],
}


def special_labels(meta):
    if not meta or not meta["value_labels"]:
        return {}
    return {
        k: v
        for k, v in meta["value_labels"].items()
        if any(x in v.lower() for x in ["missing", "don't know", "not stated", "no more ways"])
    }


def data_review(root, questions):
    import pandas as pd
    from cses_employment import ALIASES, employment_sources, prepare_wave_sources, source_value
    from cses_hh_hl_common import AlignmentContext, clean_code, snake_case

    frame = pd.read_parquet(root / "data/processing/cses/final_EC_CSES.parquet").rename(columns=snake_case)
    require(
        frame.shape == (332903, 60) and not frame.duplicated(["survey_wave", "person_id"]).any(),
        "Frozen EC grain changed",
    )
    aliases = {snake_case(k): v for k, v in ALIASES.items()}
    entries = registry(root)
    profiles = []
    supplemental = []
    wave_checks = []
    evidence_lookup = {(q["survey_wave"], q["field"]): q for q in questions}
    for wave, sources in employment_sources(root):
        keys, aligned = prepare_wave_sources(AlignmentContext(root=root), wave, sources)
        keys = keys.rename(columns=snake_case)
        f = frame.loc[frame.survey_wave.eq(wave)].set_index("person_id")
        require(len(f) == len(keys) and set(f.index) == set(keys.person_id), "Source key mismatch")
        f = f.loc[keys.person_id].reset_index()
        for col in ["household_id", "source_archive", "source_submodule", "source_row_id"]:
            pd.testing.assert_series_equal(keys[col].astype(f[col].dtype), f[col], check_names=False)
        rawmeta = {k: v for s in sources for k, v in stata_metadata(s).items()}
        extras = {}
        for alias in SUPPLEMENTAL.get(wave, []):
            raw, col = source_value(aligned, [alias])
            require(col is not None, f"Supplemental source missing: {wave}/{alias}")
            extras[alias] = raw
            supplemental.append(
                {
                    "survey_wave": wave,
                    "source_variable": col,
                    "nonnull": int(raw.notna().sum()),
                    "raw_values": counts(raw),
                    "fresh_stata_metadata": rawmeta[col],
                    "used_to_fill_canonical": False,
                    "source_variable_id": variable_entry(entries, wave, col)["source_variable_id"],
                }
            )
        mainraw, _ = source_value(aligned, aliases["main_occupation_source_code"])
        main = pd.Series(pd.NA, index=f.index, dtype="string") if mainraw is None else clean_code(mainraw, 3)[0]
        pd.testing.assert_series_equal(main, f.main_occupation_source_code, check_names=False)
        raws = {}
        before = {}
        names = {}
        for field in FIELDS:
            raw, col = source_value(
                aligned, aliases[FIELDS[0] if field == FIELDS[1] and wave not in ["2004", "2007"] else field]
            )
            raws[field] = raw
            names[field] = col
            if field == FIELDS[1] and wave not in ["2004", "2007"]:
                before[field] = (before[FIELDS[0]] + 1).where(main.notna()).astype("Int16")
            else:
                before[field] = transform(raw, field, f.index)
            final = before[field].copy()
            if field in FIELDS[2:4]:
                total = before[FIELDS[1]]
                final = final.mask(total.notna() & total.lt(2))
            pd.testing.assert_series_equal(final, f[field], check_names=False)
        # Cross-field diagnostics are counts, never exported identifiers or automatic corrections.
        meth = f[METHODS]
        subst = meth.where(meth.isin(range(1, 7)))
        dup = (
            subst[METHODS[0]].eq(subst[METHODS[1]])
            | subst[METHODS[0]].eq(subst[METHODS[2]])
            | subst[METHODS[1]].eq(subst[METHODS[2]])
        ).fillna(False)
        wave_checks.append(
            {
                "survey_wave": wave,
                "rows": len(f),
                "duplicate_substantive_search_method_records": int(dup.sum()),
                "later_search_slot_without_first_substantive": int(
                    (subst[METHODS[0]].isna() & subst[METHODS[1:]].notna().any(axis=1)).sum()
                ),
                "secondary_whole_year_yes_with_seasonal_response": int(
                    (f[FIELDS[2]].eq(1) & f[FIELDS[3]].notna()).sum()
                ),
                "both_less_and_more_hours_reported": int(f[FIELDS[6:8]].notna().all(axis=1).sum()),
                "hours_less_exceeds_total_worked": int(f[FIELDS[6]].gt(f.total_hours_worked_past_7_days).sum()),
                "total_count_raw_labelled_missing_9": int(f[FIELDS[1]].eq(9).sum()) if wave == "2004" else None,
                "hl_unmatched": int(f.hl_link_matched.eq(0).sum()),
            }
        )
        source_info = [{"source_file": s.display_name(root), "sha256": digest(s.read_bytes())} for s in sources]
        for field in FIELDS:
            raw, col = raws[field], names[field]
            meta = rawmeta[col] if col else None
            entry = variable_entry(entries, wave, col) if col else None
            if meta:
                require(meta == {k: entry[k] for k in ["variable_label", "value_labels"]}, "Fresh Stata labels differ")
            val = f[field]
            observed = val.notna()
            pre = before[field]
            derived = field == FIELDS[1] and wave not in ["2004", "2007"]
            mask = route(f, wave, field, extras)
            q = evidence_lookup.get((wave, field))
            allowed = {o["source_code"] for o in q["options"]} if q else set()
            if not allowed and field in CATEGORICAL | BINARY and meta and meta["value_labels"]:
                allowed = {
                    int(k)
                    for k, v in meta["value_labels"].items()
                    if not any(t in v.lower() for t in ["missing", "know", "no more"])
                }
            stored_allowed = {1, 0} if field in BINARY and allowed == {1, 2} else allowed
            labelled = special_labels(meta)
            numeric_raw = pd.to_numeric(raw, errors="coerce") if raw is not None else None
            labels_count = {
                code: {
                    "label": label,
                    "raw_count": int(numeric_raw.eq(float(code)).sum()),
                    "stored_count": int(val.eq(float(code)).sum()) if field not in BINARY and not derived else None,
                }
                for code, label in labelled.items()
            }
            profiles.append(
                {
                    "survey_wave": wave,
                    "field": field,
                    "rows": len(f),
                    "source_variable": col,
                    "source_variable_id": entry["source_variable_id"] if entry else None,
                    "source_files": source_info,
                    "fresh_stata_metadata": meta,
                    "raw_values": counts(raw) if raw is not None else {},
                    "raw_nonnull": int(raw.notna().sum()) if raw is not None else 0,
                    "nonnull": int(observed.sum()),
                    "null": int((~observed).sum()),
                    "observed_distinct": int(val.nunique()),
                    "min": float(val.min()) if observed.any() else None,
                    "max": float(val.max()) if observed.any() else None,
                    "stored_values": counts(val),
                    "raw_to_canonical_equal": True,
                    "derived": derived,
                    "cleaner_exclusions": counts(raw.loc[raw.notna() & pre.isna()])
                    if raw is not None and not derived
                    else {},
                    "derivation_missing_main_with_count": int((before[FIELDS[0]].notna() & main.isna()).sum())
                    if derived
                    else None,
                    "secondary_count_suppressed": int((pre.notna() & val.isna()).sum()) if field in FIELDS[2:4] else 0,
                    "labelled_special_codes": labels_count,
                    "stored_outside_documented_options": counts(val.loc[observed & ~val.isin(stored_allowed)])
                    if allowed
                    else {},
                    "choice_count": len(allowed) if allowed else None,
                    "choice_evidence": "complete_questionnaire"
                    if q and q["options"]
                    else "embedded_stata_labels"
                    if allowed
                    else "numeric_or_no_verified_dictionary",
                    "full_question_located": q is not None,
                    "route_assessed": mask is not None,
                    "literal_route_records": int(mask.fillna(False).sum()) if mask is not None else None,
                    "nonnull_inside_route": int((observed & mask.fillna(False)).sum()) if mask is not None else None,
                    "nonnull_outside_route": int((observed & mask.eq(False).fillna(False)).sum())
                    if mask is not None
                    else None,
                    "nonnull_route_unknown": int((observed & mask.isna()).sum()) if mask is not None else None,
                    "null_inside_route": int((~observed & mask.fillna(False)).sum()) if mask is not None else None,
                }
            )
        print(f"{wave}: all 19 fields reproduced", flush=True)
    return frame, profiles, supplemental, wave_checks


def check_database(frame):
    import pandas as pd
    from cses_baseline_metadata import connect_database
    from psycopg import sql
    from publish_cses_age_topcode import read_only

    columns = list(
        dict.fromkeys(
            CONTEXT
            + FIELDS
            + [
                "main_occupation_source_code",
                "main_employment_status_source_code",
                "secondary_employment_status_source_code",
                "actively_seeking_work",
                "available_for_work",
                "total_hours_worked_past_7_days",
            ]
        )
    )
    expected = frame[columns].sort_values(["survey_wave", "person_id"]).reset_index(drop=True)
    relations = [("cses_data", "final_EC_CSES"), ("cses_analysis", "cses_ec_classification_v1")]
    with connect_database({"dbname": "mda"}) as conn:
        read_only(conn)
        for schema, name in relations:
            query = sql.SQL("SELECT {} FROM {} ORDER BY survey_wave,person_id").format(
                sql.SQL(",").join(map(sql.Identifier, columns)), sql.Identifier(schema, name)
            )
            live = pd.DataFrame(conn.execute(query).fetchall()).astype(expected.dtypes.to_dict())
            live.source_archive = normalize_legacy_source_paths(live.source_archive)
            pd.testing.assert_frame_equal(live, expected, check_exact=True)
    return {
        "transaction_read_only": True,
        "all_selected_cells_equal": True,
        "columns": columns,
        "relations": [".".join(r) for r in relations],
        "rows_per_relation": len(frame),
        "full_relation_validation": False,
    }


def make_review(root, verification, live):
    from plan_cses_age_topcode import checked_review

    coverage()
    checked_review(root)
    pins = {**PINS, PRIOR: PRIOR_SHA, CURRENT: CURRENT_SHA}
    for path, sha in pins.items():
        require(digest((root / path).read_bytes()) == sha, f"Frozen input changed: {path}")
    prior = json.loads((root / PRIOR).read_text())
    require(
        digest((root / "rsc/cses_db/review_cses_main_job_abroad.py").read_bytes()) == prior["implementation_sha256"],
        "Prior review helper changed",
    )
    for path, sha in {**prior["frozen_inputs"], **json.loads((root / EXECUTION).read_text())["file_sha256"]}.items():
        require(digest((root / path).read_bytes()) == sha, f"Published input changed: {path}")
    verified = json.loads(verification.read_text())
    require(
        verified["source_cells_sha256"] == digest((root / BASE / "source_cells.json").read_bytes()),
        "Frozen questionnaire cells changed",
    )
    require(
        verified["implementation_sha256"] == digest((root / "rsc/cses_db/review_cses_education.py").read_bytes()),
        "Workbook verifier changed",
    )
    require(
        len(verified["sources"]) == 7 and all(s["all_sheets_equal"] for s in verified["sources"]),
        "Seven fresh workbook checks required",
    )
    questions, universes, related = evidence(root)
    frame, profiles, supplemental, wave_checks = data_review(root, questions)
    profile_lookup = {(p["survey_wave"], p["field"]): p for p in profiles}
    for q in questions:
        p = profile_lookup[(q["survey_wave"], q["field"])]
        require(q["source_variable_id"] == p["source_variable_id"], "Question/data source identity mismatch")
    summaries = []
    for field, meaning in zip(FIELDS, MEANINGS, strict=True):
        ps = [p for p in profiles if p["field"] == field]
        summaries.append(
            {
                "field": field,
                "meaning": meaning,
                "review_completed": True,
                "nonnull": sum(p["nonnull"] for p in ps),
                "source_waves": [p["survey_wave"] for p in ps if p["source_variable"]],
                "question_waves": [p["survey_wave"] for p in ps if p["full_question_located"]],
                "cleaner_exclusions": sum(sum(p["cleaner_exclusions"].values()) for p in ps),
                "secondary_count_suppressed": sum(p["secondary_count_suppressed"] for p in ps),
                "outside_options": sum(sum(p["stored_outside_documented_options"].values()) for p in ps),
                "nonnull_outside_route": sum(p["nonnull_outside_route"] or 0 for p in ps),
                "nonnull_route_unknown": sum(p["nonnull_route_unknown"] or 0 for p in ps),
                "whole_variable_certified": False,
            }
        )
    return {
        "review_id": "cses-employment-remaining-review-v1",
        "implementation_sha256": digest((root / SELF).read_bytes()),
        "frozen_inputs": pins,
        "source_verification": verified,
        "fields": FIELDS,
        "previous_fields": PRIOR_FIELDS,
        "questions": questions,
        "universes": universes,
        "related_question_evidence": related,
        "profiles": profiles,
        "supplemental_raw_columns": supplemental,
        "wave_checks": wave_checks,
        "summaries": summaries,
        "scope_counts": {
            "batch_fields": 19,
            "previous_fields": 20,
            "cumulative_reviewed_ec_fields": 39,
            "remaining_ec_fields": 0,
            "field_wave_profiles": len(profiles),
            "question_field_wave_correspondences": len(questions),
            "source_field_wave_mappings": sum(p["source_variable"] is not None for p in profiles),
            "rows": len(frame),
            "fully_certified_all_ten_wave_fields": 0,
        },
        "database_check": check_database(frame) if live else {"performed": False},
        "database_mutated": False,
        "canonical_data_mutated": False,
        "new_question_links_published": False,
        "individual_records_saved": False,
        "corrections_published": False,
    }


NOTES = [
    "The 0–10 retention bound is an inherited implementation rule, not a printed maximum. Do not confuse additional jobs with total jobs. No counts are imputed for 2004/2007.",
    "2004 code 9 is explicitly labelled missing but remains 9 in 244 stored records. Later totals depend on a present main occupation code and are not a direct answer to a total-count question. Unknown counts must not be filled with zero.",
    "Two Yes/No choices. Eleven valid 2021 raw answers were suppressed by the inherited known-total-below-two rule; one nonbinary 2019 raw value was excluded. This review preserves both the source archive and existing cleaned results.",
    "The complete questions say seasonal, not usual. Keep the legacy name for compatibility until an additive correction is published. Whole-year Yes skips this item; do not invert whole-year work to construct it. Three valid 2021 raw answers were suppressed by the count rule.",
    "The recorded amount covers all jobs, including in-kind wages, in nominal riel. Eligibility is employee status in either main or secondary occupation. The 2004 archive has separate job-level wages; they cannot simply be called the later all-job total.",
    "2009 onward: 1=Less, 2=More, 3=Unchanged. The related 2004 question uses 1=Same, 2=Less, 3=More and lacks the explicit income-change condition. It requires a qualified crosswalk, not direct code reuse.",
    "Later forms explicitly ask for the reduction, not desired total hours. The 2009 single q15_c22 field is omitted by the split-column aliases and has a shorter more/less question; recovery requires a separate interpretation decision.",
    "Later forms explicitly ask for the additional hours, not desired total hours. The 2009 combined field is not automatically split or treated as an increment in this review.",
    "The past-seven-days/next-two-weeks availability window and more-hours preference gate are explicit in six inspected forms. One 2019 code 0 was previously converted to NULL. NULL is not No.",
    "Three options: temporary illness, not enough work available, other reasons. Ask when more hours are preferred, regardless of whether more work is currently possible. Do not impose availability Yes from the following duration question.",
    "For 2011 onward this is a month duration, with less than one month entered as 0. In 2019/2021 code 98 is explicitly labelled unknown. The omitted 2009 month/year pair contains calendar-like years and cannot be multiplied into a duration.",
    "Six substantive search methods. Four 2004 code-9 values are explicitly missing but remain stored. The slots form one multiple-response question; blank optional slots do not imply a missing interview.",
    "Six substantive methods, with 2004 code 0 explicitly meaning no more ways recorded (293 records). Treat 0 as an empty slot in a future interpreted interface, not a seventh method.",
    "Six substantive methods, with 2004 code 0 explicitly meaning no more ways recorded (105 records). Preserve slot order without claiming it is an importance ranking.",
    "Desired total weekly hours have a broader 2004 route than later jobseeker-only wording. The 263 excluded 2004 code-99 values are labelled missing. The 168-hour bound and exclusion of 98 elsewhere remain inherited rules, not universally documented questionnaire limits.",
    "The active-search duration is not the same as total months out of work. The 2009 q15_c30a/b pair is omitted by the single-column alias and its year component contains calendar-like years. Do not calculate months without resolving that inconsistency.",
    "Nine printed reasons in the six inspected 2009+ forms. Two stored 2019 zeros have no meaning in the printed/embedded 1–9 dictionary. The 2007 archive has a related q13ac10 column, but its household question and routing remain unverified.",
    "2011+ printed item includes looking and not looking for work, but is reached via not-seeking and reason codes other than 6–8. It is not a universal duration for everyone without work. Most excluded 98 values are labelled unknown; one 2019 code 99 lacks that label.",
    "Two Yes/No choices, under the non-seeking/reason route and less than 13 months out of work. The latest job is not necessarily the main or secondary current job. Four nonbinary raw codes were previously excluded.",
]


def compact_counts(values):
    return ", ".join(f"{k}: {n:,}" for k, n in values.items()) or "None"


def field_document(r):
    lines = [
        "# Final 19 employment fields: wave-by-wave evidence",
        "",
        "[Summary and findings](cses-employment-remaining-review.md)",
        "",
        "All counts are unweighted member-wave observations. They are not actual interview respondents or unique longitudinal people. "
        "Numeric fields do not have a fixed number of choices. Distinct observed values are not questionnaire options. "
        "Route checks only cover located complete questions. Blank optional search slots are allowed. "
        "2014 is a draft; 2021 inherits the screening wording conflict. No routes are transferred to 2007/2017/2019.",
        "",
    ]
    for field, meaning, note in zip(FIELDS, MEANINGS, NOTES, strict=True):
        ps = [p for p in r["profiles"] if p["field"] == field]
        lines += [
            f"## {field}",
            "",
            meaning,
            "",
            note,
            "",
            "| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |",
            "| --- | ---: | ---: | --- | --- | --- |",
        ]
        for p in ps:
            choice = (
                str(p["choice_count"]) + " (" + p["choice_evidence"] + ")"
                if p["choice_count"]
                else "Numeric"
                if field not in BINARY | CATEGORICAL
                else "Unverified"
            )
            lines.append(
                f"| {p['survey_wave']} | {p['nonnull']:,} / {p['rows']:,} | {p['observed_distinct']} | {choice} | {p['source_variable'] or 'No selected alias'} | {'Draft' if p['survey_wave'] == '2014' else 'Yes' if p['full_question_located'] else 'No'} |"
            )
        lines += [
            "",
            "| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
        for p in ps:

            def fmt(k):
                return f"{p[k]:,}" if p[k] is not None else "Not assessed"

            lines.append(
                f"| {p['survey_wave']} | {compact_counts(p['cleaner_exclusions'])} | {p['secondary_count_suppressed']} | {fmt('nonnull_outside_route')} | {fmt('nonnull_route_unknown')} | {fmt('null_inside_route')} |"
            )
        lines += [
            "",
            "Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. "
            "These counts overlap other diagnostics and must not be summed as people.",
            "",
            "| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |",
            "| --- | --- | --- | --- | --- |",
        ]
        for q in r["questions"]:
            if q["field"] != field:
                continue
            options = (
                "; ".join(f"{o['source_code']} = {o['label_as_printed']}" for o in q["options"]).replace("\n", " ")
                or "Numeric entry / derived total"
            )
            lines.append(
                f"| {q['survey_wave']} | {q['source_sheet']} | {q['question_code_cell']} ({q['printed_number']}) | {q['candidate_code_cell']} | {options} |"
            )
        exceptions = [p for p in ps if p["labelled_special_codes"] or p["stored_outside_documented_options"]]
        if exceptions:
            lines += ["", "Dictionary qualifications:", ""]
            for p in exceptions:
                labels = "; ".join(
                    f"raw {code} = {v['label']} ({v['raw_count']:,} source records; {v['stored_count']} stored with that code)"
                    for code, v in p["labelled_special_codes"].items()
                )
                lines.append(
                    f"- {p['survey_wave']}: "
                    + labels
                    + (". " if labels else "")
                    + "Stored codes outside verified choices: "
                    + compact_counts(p["stored_outside_documented_options"])
                    + "."
                )
        lines += [""]
    lines += [
        "## Evidence archive",
        "",
        "The [aggregate review](../data/processing/cses/employment_remaining_review_v1/review.json) contains exact literal cell texts, "
        "source-file and archive-member hashes, candidate IDs, source-variable IDs, fresh Stata dictionaries and complete aggregate frequencies. "
        "It does not contain individual identifiers or new database values.",
        "",
    ]
    return "\n".join(lines)


def document(r):
    c = r["scope_counts"]
    lines = [
        "# Employment review: final 19 fields",
        "",
        "**All 39 of 39 EC business fields have now received a detailed review. No fields remain unreviewed in this scope.** "
        "This finishes the review queue, not all corrections or unrestricted cross-year harmonization. "
        "The physical employment table and current classification view retain their existing values.",
        "",
        f"This batch covers 19 fields across 10 waves ({c['field_wave_profiles']} field-wave profiles), "
        f"{c['source_field_wave_mappings']} direct/derived source mappings and {c['question_field_wave_correspondences']} complete question-to-field-wave correspondences. "
        "Shared method slots and derived total-count correspondences are not separate printed questions. "
        "Seven original English household workbooks were freshly verified sheet by sheet.",
        "",
        "## Variables and available records",
        "",
        "The EC table has 332,903 member-wave records. Below, non-null values measure field availability, not interview respondents. "
        "Do not add these counts across fields. See the [field-wave brief](cses-employment-remaining-field-waves.md) for every year, "
        "option set, route count and source locator.",
        "",
        "| Field | Non-null values | Complete-question waves | Historical cleaner exclusions | Count-suppressed |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for s in r["summaries"]:
        lines.append(
            f"| {s['field']} | {s['nonnull']:,} | {len(s['question_waves'])} | {s['cleaner_exclusions']:,} | {s['secondary_count_suppressed']} |"
        )
    lines += [
        "",
        "## Findings requiring follow-up",
        "",
        "1. **Secondary seasonality is misnamed.** `secondary_job_was_usual_past_7_days` asks whether the secondary work is seasonal in the five inspected 2011+ forms. "
        "Raw 1/2 → stored 1/0 is correct. A future additive alias should preserve the old field and explicitly qualify 2017/2019 evidence, just as for main-job seasonality.",
        "",
        "2. **Explicit special codes remain in old numeric columns.** In 2004, 244 total-occupation values of 9 and four first-search-method values of 9 are labelled missing. "
        "Second/third search slots also retain 293/105 zeros labelled no more ways recorded. These 398 zeros are empty slots, not extra search categories. "
        "The count-9 issue matters to downstream secondary-job eligibility; do not simply recode it and rebuild historical tables without a separate impact review.",
        "",
        "3. **Earlier related source columns are omitted, with important qualifications.** The selected 2004 archive contains job-specific wages and a differently coded hours preference; "
        "the 2007 selected source contains related preference, non-seeking reason and duration columns but lacks a verified household form. "
        "The 2009 source contains a combined hours-change column and separate month/year fields. Their presence does not authorize treating them as equivalent to later canonical columns.",
        "",
        "4. **2009 duration evidence conflicts with observed year values.** The form prints MONTHS and YEARS for 25a/b and 30a/b, but the data year components contain calendar-like years such as 2008 and 2009. "
        "Neither multiplying the year by 12 nor subtracting it from interview year is justified yet. Keep the components separate until their intended meaning is confirmed.",
        "",
        "5. **Known cleaning and route exceptions are now explicit.** The inherited secondary-count rule removes 11 whole-year and three seasonal responses in 2021. "
        "Later month-duration 98 codes have embedded unknown labels; 2021 questions 25/30 print that instruction too. "
        "One excluded 2019 out-of-work value of 99 lacks an explicit label. Two stored 2019 non-seeking reason zeros are outside the verified 1–9 dictionary. "
        "These findings do not justify silently imputing or deleting answers.",
        "",
        "## Earlier source candidates (not imported)",
        "",
        "| Wave | Source variable | Non-null source records | Current disposition |",
        "| --- | --- | ---: | --- |",
    ]
    for s in r["supplemental_raw_columns"]:
        lines.append(
            f"| {s['survey_wave']} | {s['source_variable']} | {s['nonnull']:,} | Retained in original archive; no canonical fill |"
        )
    lines += [
        "",
        "The 2004 preference mapping is 1=Same, 2=Less, 3=More (9=missing), whereas later preference is 1=Less, 2=More, 3=Unchanged. "
        "The later question explicitly conditions on corresponding income changes. The 2004 wages concern each recorded occupation, whereas later wages cover all economic activities. "
        "The 2004 duration question combines unemployment and working fewer hours, so it cannot populate the three later duration concepts without qualification. "
        "2007 source-column names and distributions alone are not questionnaire evidence.",
        "",
        "## Cross-field checks",
        "",
        "| Wave | Duplicate substantive method codes | Later method without first | Whole-year Yes + secondary-seasonal answer | Both hours-more/less filled | Fewer-hours amount > total worked |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for w in r["wave_checks"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    w["survey_wave"],
                    *[
                        f"{w[k]:,}"
                        for k in [
                            "duplicate_substantive_search_method_records",
                            "later_search_slot_without_first_substantive",
                            "secondary_whole_year_yes_with_seasonal_response",
                            "both_less_and_more_hours_reported",
                            "hours_less_exceeds_total_worked",
                        ]
                    ],
                ]
            )
            + " |"
        )
    lines += [
        "",
        "These are record-level diagnostics, not mutually exclusive groups. In 2017/2019 they are response-pair checks, not verified printed-route violations. "
        "No complete common employment/unemployment population is certified: 2004 has age 10+ and a seven-day search period, later forms generally age 5+ and four-week search; "
        "2021 changes the second screen to unpaid work while some downstream gates still mention temporary absence. 2014 remains a draft.",
        "",
        "## Routing overview",
        "",
        "```mermaid",
        "flowchart TD",
        '    W["Work-screen route"] --> J["Additional jobs; derived total"]',
        '    J -->|At least one additional job| S["Secondary whole-year / seasonal items"]',
        '    W --> E["Employee in either job: all-job wages"]',
        '    W --> P["Hours preference"]',
        '    P -->|Less| L["Reduction amount"]',
        '    P -->|More| M["Extra hours; availability; reason"]',
        '    M -->|Available| D["Months working fewer hours"]',
        '    N["Nonworking route"] --> Q["Actively seeking?"]',
        '    Q -->|Yes| A["Up to 3 methods; availability; desired hours; search duration"]',
        '    Q -->|No| R["Reason not seeking"]',
        '    R -->|Reason not 6-8| O["Months out of work"]',
        '    O -->|Less than 13 months| T["Latest work seasonal"]',
        "```",
        "",
        "This schematic describes the inspected 2011+ routes with the stated qualifications; it is not a new database graph. "
        "The field-wave appendix treats 2004 and 2009 differences explicitly. Month 0 means less than one month where printed, not unknown. "
        "Optional second/third method slots need not be filled.",
        "",
        "## Verification and publication boundaries",
        "",
        "All 190 field-wave results were independently reproduced from the 11 selected raw Stata members, including binary recoding, numeric/money domains, "
        "derived total counts and the separate secondary-count suppression stage. Source dictionaries were freshly read and checked against the frozen registry. "
        "The spreadsheets skill guided explicit wording, choices, units, skips and earlier-wave mismatch checks. No original workbook was edited.",
        "",
        (
            f"A forced read-only database comparison matched all {len(r['database_check']['columns'])} selected columns for all 332,903 rows in each of "
            "`cses_data.final_EC_CSES` and `cses_analysis.cses_ec_classification_v1`. This checks the 19 variables and their context/dependencies, not the complete 86-column view."
            if r["database_check"].get("all_selected_cells_equal")
            else "Live database verification was not performed."
        ),
        "",
        "The [aggregate review](../data/processing/cses/employment_remaining_review_v1/review.json) and "
        "[field-wave brief](cses-employment-remaining-field-waves.md) preserve reproducible counts and source locators. "
        "No database values, source dictionaries, historical releases or graph v14 nodes were changed. No correction overlay, Git commit or DVC push was performed.",
        "",
        "## Complete 39-field review ledger",
        "",
        "| Earlier group | Fields already reviewed | Evidence |",
        "| --- | --- | --- |",
        "| Screening (4) | "
        + ", ".join(SCREEN_FIELDS)
        + " | [Screening brief](cses-employment-screening-alignment.md) |",
        "| Hours, days, status (7) | "
        + ", ".join(HOURS_FIELDS)
        + " | [Preserved review](cses-employment-hours-status-alignment.md) and [published corrections](cses-employment-corrected-interface.md) |",
        "| Classification (6) | "
        + ", ".join(CLASS_FIELDS)
        + " | [Review](cses-employment-classification-alignment.md) and [published corrections](cses-classification-corrected-interface.md) |",
        "| Main-job whole-year (1) | main_job_works_whole_year | [Brief](cses-main-job-whole-year.md) |",
        "| Main-job seasonal (1) | main_job_was_usual_past_7_days | [Local correction; not published](cses-main-job-seasonal.md) |",
        "| Main-job abroad (1) | main_job_was_abroad | [Brief](cses-main-job-abroad.md) |",
        "| Remaining batch (19) | All fields listed in this brief | [Detailed appendix](cses-employment-remaining-field-waves.md) |",
        "",
        "The exact union is checked against the 39 module fields in the frozen EC builder, with no duplicates or omissions. "
        "The older 280-field inventory remains a preserved baseline snapshot; its pending labels do not supersede this ledger.",
        "",
        "Reproduce with bundled Python: `rsc/cses_db/review_cses_employment_remaining.py --verify-workbooks --soffice /path/to/bundled/soffice`, "
        "then `.venv/bin/python rsc/cses_db/review_cses_employment_remaining.py --check-database`. Changed snapshots require fresh output/docs paths.",
        "",
        "Next: prepare a separately versioned correction proposal for explicit missing/control codes and both seasonal aliases, with downstream-count impact checks. "
        "Keep ambiguous earlier-source recoveries and unverified questionnaire transfers separate from those evidence-backed changes.",
        "",
    ]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument("--output", type=Path, default=Path(OUTPUT))
    p.add_argument("--docs-dir", type=Path, default=Path("docs"))
    p.add_argument("--verify-workbooks", action="store_true")
    p.add_argument("--soffice")
    p.add_argument("--check-database", action="store_true")
    args = p.parse_args()
    out = args.root / args.output
    if args.verify_workbooks:
        require(args.soffice, "Explicit bundled converter required")
        write_once(out / "source_verification.json", verify_workbooks(args.root, args.soffice))
    else:
        r = make_review(args.root, out / "source_verification.json", args.check_database)
        write_once(out / "review.json", r)
        write_once(args.root / args.docs_dir / "cses-employment-remaining-review.md", document(r))
        write_once(args.root / args.docs_dir / "cses-employment-remaining-field-waves.md", field_document(r))
        print(json.dumps(r["scope_counts"]))


if __name__ == "__main__":
    main()
