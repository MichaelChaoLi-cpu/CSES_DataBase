#!/usr/bin/env python3
"""Audit six EC classification fields and supplemental evidence without publication."""
from __future__ import annotations

import argparse
import io
import json
import re
import zipfile
from pathlib import Path

from organize_cses_questionnaires import digest, workbook_cells, write_once
from review_cses_education import BASE, load_inputs, normalize_legacy_source_paths, selected_sources, verify_workbooks
from review_cses_employment_hours_status import clean_numeric, gate_cells, registry, stata_metadata, variable_entry
from review_cses_employment_screening import BUILDER, BUILDER_SHA, LAYOUT
from review_cses_questionnaires import parse_options, require

SELF = "rsc/cses_db/review_cses_employment_classification.py"
OUTPUT = "data/processing/cses/employment_classification_review_v1"
FIELDS = [f"{job}_{kind}_source_code" for job in ["main", "secondary"]
          for kind in ["occupation", "industry", "employer_type"]]
EMPLOYER = [FIELDS[2], FIELDS[5]]
CONTEXT = ["survey_wave", "person_id", "age", "hl_link_matched", "worked_at_least_one_hour_past_7_days",
           "second_work_screening_source_code", "additional_jobs_count", "total_occupations_past_7_days"]
PINS = {
    "data/processing/cses/employment_hours_status_review_v1/review.json": "077c6e78e6a64ba5fccd44041f856fa4db7cceca85d46a251bdf94cd31288ae2",
    "data/releases/cses-employment-recovery-qualified-v1/execution.json": "47f1f574a385bdffadeb6716f2a6117cd3efad38111f5cf5e4095ccc094f2d59",
    "data/processing/cses/employment_corrected_v1/final_EC_CSES.parquet": "450e5bd8082337cf6f55c3d69d4c71d0fa8f735fbf8ef6f52eef2146f5adf89e",
    "data/lineage/cses_lineage_graph_v13.json": "c1acebbc1984a00765518e30526749d17138f07d96b6df66f2d3f9af510c5eef",
}
BOOK_ARCHIVE = "data/raw/CSES 2009.zip"
BOOK_MEMBER = "CSES 2009/Other Doc/CSES2009 ISCO and ISIC Codes.xls"
SUP_ARCHIVE = "data/raw/CSES 2007.zip"
SUP_MEMBER = "CSES 2007/HH data/CSES 2007/13B_mainoccupation.dta"
SUP_DICT = "CSES 2007/HH data/CSES 2007/code/dbo_c_isic.dta"


def layouts(wave):
    if wave == "2004":
        return [("13 Econ. Status", *v) for v in [
            ("C29", "J42", "J40"), ("M29", "U42", "U40"), ("AJ29", "AJ42", "AJ31")]] * 2
    if wave == "2009":
        return [("15 Econo_Status_1", *v) for v in [
            ("W4", "AJ16", "AJ14"), ("AO4", "BF16", "BF14"), ("BI4", "BI16", "BI7"),
            ("CP4", "DH16", "DH14"), ("DM4", "EC16", "EC14"), ("EF4", "EF16", "EF7")]]
    if wave == "2021":
        return [(sn, *v) for sn, v in [
            ("15 Current Eco-1", ("V4", "AI17", "AI15")), ("15 Current Eco-1", ("AN4", "BD17", "BD15")),
            ("15 Current Eco-1", ("BG4", "BG17", "BG7")), ("15 Current Econo-3", ("C4", "Q16", "Q14")),
            ("15 Current Econo-3", ("T4", "AG16", "AG14")), ("15 Current Econo-3", ("AL4", "AL16", "AL6"))]]
    require(wave in {"2011-12", "2013", "2014", "2016"}, "No layout borrowing")
    return [("15 Econo_Status_1", *v) for v in [
        ("V6", "AI19", "AI17"), ("AN6", "BD19", "BD17"), ("BG6", "BG19", "BG9"),
        ("DF6", "DT19", "DT17"), ("DW6", "EJ19", "EJ17"), ("EO6", "EO19", "EO9")]]


def evidence(root):
    spec, alignment, inventory, extracts = load_inputs(root)
    sheets = {s["source_file"]: s["sheets"] for s in extracts}
    entries = registry(root)
    questions, universes = [], []
    for source in selected_sources(spec, inventory):
        wave = source["survey_wave"]
        cells = sheets[source["source_file"]]
        screen = LAYOUT[wave]
        universes.append({"survey_wave": wave, "minimum_age": screen["minimum_age"],
            "source_file": source["source_file"], "population_sheet": screen["sheets"][0],
            "population_cells": {c: cells[screen['sheets'][0]][c] for c in [screen['universe'], screen['respondent']]},
            "gate_cells": {sn: {c: cells[sn][c] for c in cols} for sn, cols in gate_cells(wave).items()}})
        for field, (sn, text, code, detail) in zip(FIELDS, layouts(wave), strict=True):
            cs = cells[sn]
            links = [v for v in alignment["source_links"] if v["survey_wave"] == wave
                     and ["final_EC_CSES", field] in v["canonical_keys"]]
            require(len(links) == 1, "One existing raw-field mapping required")
            link = links[0]
            entry = variable_entry(entries, wave, link["variable_name"])
            number = re.fullmatch(r"\((\d+[a-z]?)\)", cs[code].strip())[1]
            name = entry["variable_name"].lower()
            if wave == "2004":
                require(name.endswith("2" if field.startswith("secondary") else "1"), "Repeated row suffix changed")
                name = name[:-1].rstrip("_")
                require(cs["C43"] == "1º" and cs["C44"] == "2º", "Job-row identity changed")
            require(re.search(r"(\d+[a-z]?)$", name)[1].lstrip("0") == number.lstrip("0"), "Printed/raw item mismatch")
            candidates = [q for q in inventory["questions"] if q["source_file"] == source["source_file"]
                          and q["source_sheet"] == sn and q["question_code_cell"] == code]
            require(len(candidates) == 1, "One exact printed code locator required")
            candidate = candidates[0]
            require((text if field in EMPLOYER else detail) in candidate["text_cell_candidates"], "Code-header locator mismatch")
            if link["candidate_ids"]:
                require(candidate["candidate_id"] in link["candidate_ids"], "Existing question candidate changed")
            opts = parse_options({detail: cs[detail]}) if field in EMPLOYER else []
            if opts:
                require({o["source_code"] for o in opts} == set(range(1, 11 if wave == "2004" else 9)), "Employer option set changed")
            else:
                require("NIS" in cs[detail] and ("ISIC" if "industry" in field else "OCC") in cs[detail], "Classification header changed")
            questions.append({"survey_wave": wave, "field": field, "source_file": source["source_file"],
                "source_sha256": source["source_sha256"], "source_sheet": sn, "question_text_cell": text,
                "question_code_cell": code, "detail_cell": detail, "question_text": cs[text], "printed_code": cs[code],
                "detail_text": cs[detail], "options": opts, "option_count": len(opts) if opts else None,
                "response_kind": "printed_employer_categories" if opts else "coded_open_description",
                "source_variable": entry["variable_name"], "source_variable_id": entry["source_variable_id"],
                "candidate_id": candidate["candidate_id"], "original_candidate_ids": link["candidate_ids"],
                "correspondence_basis": "explicit_code_column_and_repeated_job_row" if wave == "2004" else
                    "explicit_2009_A_printed_C_released" if wave == "2009" else "explicit_description_and_code_column",
                "documentation_status": source["documentation_status"], "whole_variable_certified": False})
    require(len(questions) == 42 and len({q['candidate_id'] for q in questions}) == 39, "42 correspondences / 39 items required")
    return questions, universes


def counts(series):
    return {str(k): int(n) for k, n in series.dropna().astype("string").value_counts().sort_index().items()}


def classification(values, width):
    """Independent reproduction of inherited minimum-width code formatting, not a crosswalk."""
    result = values.astype("string").str.strip().str.replace(r"\.0+$", "", regex=True)
    result = result.mask(result.str.lower().isin(["", "nan", "none", "<na>"]))
    return result.where(result.str.fullmatch(r"\d+", na=False)).str.zfill(width)


def width_for(field, wave):
    return 3 if "occupation" in field else 2 if wave == "2004" else 4


def literal_route(frame, field, wave):
    if wave not in LAYOUT:
        return None
    age = frame.age.ge(LAYOUT[wave]["minimum_age"])
    if wave == "2004":
        return age & frame.total_occupations_past_7_days.ge(2 if field.startswith("secondary") else 1)
    work = frame.worked_at_least_one_hour_past_7_days.eq(1) | frame.second_work_screening_source_code.eq(1)
    return age & work & (frame.additional_jobs_count.ge(1) if field.startswith("secondary") else True)


def special_labels(labels):
    return {c: t for c, t in labels.items() if re.search(r"\bmissing\b|not stated", t, re.I)}


def supplemental_2007(root, frame):
    import pandas as pd
    from cses_hh_hl_common import AlignmentContext, snake_case, standardize_source
    from inventory_cses_archives import discover_sources

    source = [s for s in discover_sources(root) if s.archive_members == (SUP_MEMBER,)]
    require(len(source) == 1, "Unique 2007 supplemental job source required")
    source = source[0]
    ctx = AlignmentContext(root=root)
    raw = ctx.load(source)
    keys = standardize_source(ctx, source, "2007", "EC").rename(columns=snake_case)
    require(not keys.person_id.isna().any() and not raw.duplicated(["persid", "q13b_ocid"]).any(), "Person-job key invalid")
    require(set(raw.q13b_ocid) == {1, 2}, "Supplement job indices changed")
    current = frame.loc[frame.survey_wave.eq("2007")].set_index("person_id")
    require(set(keys.person_id) <= set(current.index), "Supplement has unmatched EC keys")
    linked = current.loc[keys.person_id].reset_index()
    require(keys.household_id.equals(linked.household_id), "Supplement household link mismatch")
    require(current[FIELDS].isna().all().all(), "Expected all-six-null 2007 baseline")
    rows = []
    for job, prefix in [(1, "main"), (2, "secondary")]:
        job_mask = raw.q13b_ocid.eq(job)
        eligible = linked.total_occupations_past_7_days.ge(job)
        for kind, column in [("occupation", "q13bc02b"), ("industry", "q13bc03b"), ("employer_type", "q13bc07")]:
            values = clean_numeric(raw[column], 9999) if kind == "employer_type" else classification(raw[column], 3 if kind == "occupation" else 4)
            rows.append({"field": f"{prefix}_{kind}_source_code", "source_variable": column, "job_index": job,
                "raw_job_rows": int(job_mask.sum()), "candidate_nonnull_before_gate": int((job_mask & values.notna()).sum()),
                "candidate_nonnull_known_count_supports_job": int((job_mask & values.notna() & eligible.fillna(False)).sum()),
                "nonnull_known_count_conflict": int((job_mask & values.notna() & eligible.eq(False).fillna(False)).sum()),
                "nonnull_job_count_unknown": int((job_mask & values.notna() & eligible.isna()).sum()),
                "values": counts(values.loc[job_mask]), "published": False})
    with zipfile.ZipFile(root / SUP_ARCHIVE) as z:
        dictionary_payload = z.read(SUP_DICT)
    dictionary = pd.read_stata(io.BytesIO(dictionary_payload), convert_categoricals=False)
    codes = classification(dictionary.isiccode, 4)
    require(not codes.isna().any() and not codes.duplicated().any(), "2007 ISIC dictionary key invalid")
    industry = classification(raw.q13bc03b, 4)
    main_ids, secondary_ids = (set(keys.loc[raw.q13b_ocid.eq(j), "person_id"]) for j in [1, 2])
    return {"source_archive": SUP_ARCHIVE, "source_member": SUP_MEMBER, "source_sha256": digest(source.read_bytes()),
        "rows": len(raw), "persons": keys.person_id.nunique(), "job_index_counts": counts(raw.q13b_ocid),
        "duplicate_person_job_keys": 0, "unmatched_ec_keys": 0, "household_conflicts": 0,
        "secondary_persons_without_main_job_row": len(secondary_ids - main_ids), "candidate_fields": rows,
        "metadata": stata_metadata(source), "dictionary_member": SUP_DICT, "dictionary_sha256": digest(dictionary_payload),
        "industry_dictionary": dict(zip(codes, dictionary.descr_eng, strict=True)),
        "industry_codes_absent_from_dictionary": counts(industry.loc[~industry.isin(codes)]),
        "job_index_meaning_status": "candidate_primary_secondary_order_not_questionnaire_certified",
        "recovery_requires_separate_grain_and_gate_contract": True, "database_mutated": False}


def data_review(root, questions, codebook):
    import pandas as pd
    from cses_employment import ALIASES, employment_sources, prepare_wave_sources, source_value
    from cses_hh_hl_common import AlignmentContext, snake_case

    frame = pd.read_parquet(root / "data/processing/cses/final_EC_CSES.parquet").rename(columns=snake_case)
    require(frame.shape == (332903, 60) and not frame.duplicated(["survey_wave", "person_id"]).any(), "EC grain changed")
    require(not frame[["survey_wave", "person_id"]].isna().any().any(), "Null EC key")
    aliases = {snake_case(k): v for k, v in ALIASES.items()}
    entries = registry(root)
    profiles, sources, waves = [], [], []
    for wave, raw_sources in employment_sources(root):
        keys, aligned = prepare_wave_sources(AlignmentContext(root=root), wave, raw_sources)
        keys = keys.rename(columns=snake_case)
        current = frame.loc[frame.survey_wave.eq(wave)].set_index("person_id")
        require(len(current) == len(keys) and set(current.index) == set(keys.person_id), "Raw key mismatch")
        current = current.loc[keys.person_id].reset_index()
        for key in ["household_id", "source_archive", "source_submodule", "source_row_id"]:
            pd.testing.assert_series_equal(keys[key].astype(current[key].dtype), current[key], check_names=False)
        metadata = {}
        for source in raw_sources:
            metadata.update(stata_metadata(source))
        raw_count, _ = source_value(aligned, aliases["total_occupations_past_7_days" if wave in {"2004", "2007"} else "additional_jobs_count"])
        count = clean_numeric(raw_count, 10)
        if wave not in {"2004", "2007"}:
            raw_main, _ = source_value(aligned, aliases[FIELDS[0]])
            main = classification(raw_main, 3)
            pd.testing.assert_series_equal(count, current.additional_jobs_count, check_names=False)
            count = (count + 1).where(main.notna()).astype("Int16")
        pd.testing.assert_series_equal(count, current.total_occupations_past_7_days, check_names=False)
        no_secondary = count.notna() & count.lt(2)
        source_fields = []
        for field in FIELDS:
            raw, column = source_value(aligned, aliases[field])
            before = pd.Series(pd.NA, index=current.index, dtype="Int16" if field in EMPLOYER else "string")
            meta, entry = None, None
            if column:
                entry = variable_entry(entries, wave, column)
                meta = metadata[column]
                require(meta == {k: entry[k] for k in ["variable_label", "value_labels"]}, "Fresh Stata metadata mismatch")
                before = clean_numeric(raw, 9999) if field in EMPLOYER else classification(raw, width_for(field, wave))
            expected = before.mask(no_secondary) if field.startswith("secondary") else before
            pd.testing.assert_series_equal(expected.astype(current[field].dtype), current[field], check_names=False)
            labels = (meta or {}).get("value_labels") or {}
            special = special_labels(labels)
            formatted_special = {c if field in EMPLOYER else c.zfill(width_for(field, wave)): t for c, t in special.items()}
            values = current[field].astype("string")
            known_missing = values.isin(formatted_special)
            observed = values.notna()
            q = next((q for q in questions if q["survey_wave"] == wave and q["field"] == field), None)
            dictionary = codebook["dictionaries"]["ISCO" if "occupation" in field else "ISIC"] if wave == "2009" and field not in EMPLOYER else None
            route = literal_route(current, field, wave)
            raw_nonnull = int(raw.notna().sum()) if raw is not None else 0
            source_fields.append({"field": field, "source_variable": column,
                "source_variable_id": entry["source_variable_id"] if entry else None, "fresh_stata_metadata": meta,
                "raw_to_canonical_equal": True, "raw_values": counts(raw) if raw is not None else {},
                "cleaner_removed_values": counts(raw.loc[raw.notna() & before.isna()]) if raw is not None else {}})
            profiles.append({"survey_wave": wave, "field": field, "rows": len(current), "source_variable": column,
                "raw_nonnull": raw_nonnull, "nonnull": int(observed.sum()), "null": int((~observed).sum()),
                "cleaner_removed": raw_nonnull - int(before.notna().sum()), "secondary_suppressed": int(before.notna().sum() - observed.sum()),
                "values": counts(current[field]), "observed_distinct_codes": int(values.nunique()),
                "labelled_missing_or_not_stated": counts(values.loc[known_missing]),
                "labelled_missing_count": int(known_missing.sum()), "nonnull_excluding_explicit_labelled_missing": int((observed & ~known_missing).sum()),
                "option_count": q["option_count"] if q else len(labels) if field in EMPLOYER and labels else None,
                "option_basis": "questionnaire" if q and field in EMPLOYER else "embedded_stata_labels" if field in EMPLOYER and labels else None,
                "employer_outside_printed_choices": counts(values.loc[~values.isin([str(o['source_code']) for o in q['options']]) & observed]) if q and field in EMPLOYER else None,
                "code_lengths": counts(values.dropna().str.len()),
                "longer_than_minimum_width": int(values.str.len().gt(width_for(field, wave)).sum()) if field not in EMPLOYER else None,
                "zero_code_cells": int(values.str.fullmatch("0+", na=False).sum()),
                "observed_codes_not_in_2009_workbook_dictionary": counts(values.loc[observed & ~values.isin(dictionary)]) if dictionary is not None else None,
                "nonnull_with_no_embedded_label": counts(values.loc[observed & ~values.isin([c if field in EMPLOYER else c.zfill(width_for(field, wave)) for c in labels])]) if labels else None,
                "literal_route_records": int(route.fillna(False).sum()) if route is not None else None,
                "nonnull_outside_known_route": int((observed & route.eq(False).fillna(False)).sum()) if route is not None else None,
                "route_unknown": int(route.isna().sum()) if route is not None else None, "whole_variable_certified": False})
        sources.append({"survey_wave": wave, "files": [{"source_file": s.display_name(root), "source_sha256": digest(s.read_bytes())} for s in raw_sources], "fields": source_fields})
        waves.append({"survey_wave": wave, "rows": len(current), "any_batch_nonnull": int(current[FIELDS].notna().any(axis=1).sum()),
            "all_six_nonnull": int(current[FIELDS].notna().all(axis=1).sum()), "hl_unmatched": int(current.hl_link_matched.eq(0).sum())})
        print(f"{wave}: six raw transformations reproduced", flush=True)
    return frame, profiles, sources, waves


def verify_sources(root, soffice):
    verified = verify_workbooks(root, soffice)
    with zipfile.ZipFile(root / BOOK_ARCHIVE) as z:
        payload = z.read(BOOK_MEMBER)
    cells = workbook_cells(payload, ".xls", soffice)
    dictionaries = {}
    locators = {}
    for sheet, width in [("ISCO", 3), ("ISIC", 4)]:
        require(cells[sheet]["A1"] == f"{sheet} codes in CSES 2009", "Codebook title mismatch")
        entries, refs = {}, {}
        for cell, code in cells[sheet].items():
            if re.fullmatch(r"A\d+", cell) and int(cell[1:]) >= 4 and code.isdigit():
                key = code.zfill(width)
                require(key not in entries, "Duplicate codebook key")
                entries[key] = cells[sheet]["B" + cell[1:]]
                refs[key] = [cell, "B" + cell[1:]]
        dictionaries[sheet], locators[sheet] = entries, refs
    verified["classification_codebook"] = {"archive": BOOK_ARCHIVE, "member": BOOK_MEMBER,
        "sha256": digest(payload), "cells": cells, "dictionaries": dictionaries, "locators": locators,
        "revision_status": "titles_name_CSES_2009_no_explicit_ISCO_ISIC_revision",
        "sheet3_status": "unheaded_supplement_retained_not_automatically_merged"}
    return verified


def check_database(frame):
    import pandas as pd
    from cses_baseline_metadata import connect_database
    from psycopg import sql

    columns = CONTEXT + FIELDS + ["source_archive", "source_submodule", "source_row_id"]
    expected = frame[columns].sort_values(["survey_wave", "person_id"]).reset_index(drop=True)
    with connect_database({"dbname": "mda"}) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        conn.execute("SET LOCAL statement_timeout='55s'")
        require(conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on", "Read-only required")
        for schema, table in [("cses_data", "final_EC_CSES"), ("cses_analysis", "cses_ec_aligned_v1")]:
            query = sql.SQL("SELECT {} FROM {}.{} ORDER BY survey_wave,person_id").format(
                sql.SQL(",").join(map(sql.Identifier, columns)), sql.Identifier(schema), sql.Identifier(table))
            live = pd.DataFrame(conn.execute(query).fetchall()).astype(expected.dtypes.to_dict())
            live["source_archive"] = normalize_legacy_source_paths(live.source_archive)
            pd.testing.assert_frame_equal(live, expected, check_exact=True)
    return {"all_selected_values_equal": True, "rows_per_relation": len(frame), "selected_columns": columns,
        "relations": ["cses_data.final_EC_CSES", "cses_analysis.cses_ec_aligned_v1"],
        "full_relation_validation": False, "transaction_read_only": True, "database_mutated": False}


def make_review(root, verification, live):
    from plan_cses_age_topcode import checked_review

    checked_review(root)
    for path, sha in {**PINS, BUILDER: BUILDER_SHA}.items():
        require(digest((root / path).read_bytes()) == sha, f"Frozen input changed: {path}")
    prior = json.loads((root / "data/processing/cses/employment_hours_status_review_v1/review.json").read_text())
    require(digest((root / "rsc/cses_db/review_cses_employment_hours_status.py").read_bytes()) == prior['implementation_sha256'], "Frozen helper changed")
    verified = json.loads(verification.read_text())
    require(verified["source_cells_sha256"] == digest((root / BASE / "source_cells.json").read_bytes()), "Frozen source cells changed")
    require(verified["implementation_sha256"] == digest((root / "rsc/cses_db/review_cses_education.py").read_bytes()), "Workbook verifier changed")
    require(len(verified["sources"]) == 7 and all(v["all_sheets_equal"] for v in verified["sources"]), "Seven fresh verified forms required")
    with zipfile.ZipFile(root / BOOK_ARCHIVE) as z:
        require(digest(z.read(BOOK_MEMBER)) == verified["classification_codebook"]["sha256"], "Codebook source changed")
    questions, universes = evidence(root)
    frame, profiles, sources, waves = data_review(root, questions, verified["classification_codebook"])
    supplement = supplemental_2007(root, frame)
    comparisons = []
    for source in sources:
        if source['survey_wave'] not in {'2019', '2021'}:
            continue
        for field in source['fields']:
            if field['field'] in EMPLOYER:
                continue
            kind = 'ISCO' if 'occupation' in field['field'] else 'ISIC'
            book = verified['classification_codebook']['dictionaries'][kind]
            labels = {c.zfill(width_for(field['field'], source['survey_wave'])): t
                      for c, t in field['fresh_stata_metadata']['value_labels'].items()}
            comparisons.append({'survey_wave': source['survey_wave'], 'field': field['field'], 'codebook_sheet': kind,
                'code_sets_equal': set(book) == set(labels), 'all_literal_labels_equal': book == labels,
                'all_labels_equal_after_whitespace_normalization':
                    {c: ' '.join(t.split()) for c, t in book.items()} == {c: ' '.join(t.split()) for c, t in labels.items()},
                'label_differences': {c: {'codebook_2009': book[c], 'embedded_label': labels[c]}
                    for c in sorted(set(book) & set(labels)) if book[c] != labels[c]},
                'scope': 'dictionary_comparison_only_not_observed_code_or_population_certification'})
    return {"review_id": "cses-employment-classification-review-v1", "implementation_sha256": digest((root / SELF).read_bytes()),
        "frozen_inputs_sha256": {**PINS, BUILDER: BUILDER_SHA}, "source_verification": verified,
        "questions": questions, "universes": universes, "profiles": profiles, "raw_sources": sources,
        "wave_counts": waves, "supplemental_2007": supplement, "codebook_label_comparisons": comparisons,
        "database_check": check_database(frame) if live else {"performed": False},
        "scope_counts": {"rows": len(frame), "batch_fields": 6, "employment_fields": 39, "cumulative_reviewed_fields": 17,
            "remaining_employment_fields": 22, "question_wave_correspondences": len(questions), "distinct_printed_items": 39,
            "field_wave_profiles": len(profiles), "existing_raw_field_wave_mappings": sum(p['source_variable'] is not None for p in profiles),
            "fully_certified_all_ten_wave_fields": 0},
        "database_mutated": False, "canonical_data_mutated": False, "individual_records_saved": False,
        "classification_crosswalk_published": False, "supplemental_recovery_published": False}


def documents(r):
    missing = sum(p["labelled_missing_count"] for p in r["profiles"])
    lines = ["# CSES occupation, industry and employer type", "",
        "This third EC batch reviews six fields across 332,903 member-wave records. Cumulative review coverage is "
        "17 of 39 employment fields, with 22 remaining. None of the six is certified as unrestrictedly comparable across all ten waves. "
        "Source correspondence is not a common classification crosswalk. The original table, current corrected interface and published graph v13 are unchanged.", "",
        "## Variables and available records", "", "Counts are unweighted records, not actual interview respondents or longitudinal people. "
        "Non-null codes can still mean missing/not stated. Removing only explicit labelled missing codes does not certify the remaining codes as valid.", "",
        "| Field | Non-null | Explicit labelled missing/not stated | Remaining non-null | Response type |", "| --- | ---: | ---: | ---: | --- |"]
    for field in FIELDS:
        ps = [p for p in r['profiles'] if p['field'] == field]
        n, m = sum(p['nonnull'] for p in ps), sum(p['labelled_missing_count'] for p in ps)
        lines.append(f"| `{field}` | {n:,} | {m:,} | {n-m:,} | " + ("10 employer choices in 2004; 8 in six later forms" if field in EMPLOYER else "Coded description; not a fixed questionnaire choice list") + " |")
    lines += ["", "## Main findings", "",
        "1. **Employer categories change.** 2004 has 10 printed categories; inspected 2009–2021 forms have eight. "
        "Code 7 changes from self-employed farm to embassies/international institutions/foreign aid, and code 8 from non-farm self-employed to Other. "
        "Do not pool identical numbers. In 2004 the Stata label for code 7 says farm worker, whereas the questionnaire says self-employed farm. "
        "Both wordings are retained, not silently reconciled. Employer type is distinct from employment status.",
        "2. **Classification codes need wave-specific dictionaries.** Occupations are padded to a minimum of three digits; industry to two in 2004 "
        "and four later. Padding preserves leading zeros and does not truncate longer codes. It is not a classification conversion. "
        "The newly inspected original `CSES2009 ISCO and ISIC Codes.xls` provides named 2009 code lists, but its sheet titles do not state revision numbers. "
        "An unheaded Sheet3 is retained separately, not silently merged. We do not infer a universal ISCO/ISIC revision from code patterns.",
        f"3. **{missing:,} retained field-cells explicitly mean missing/not stated.** The original 2004 labels identify occupation 999, industry 99 "
        "and employer 99 as missing. 2019/2021 labels identify occupation 999 and industry 9990 as not stated. These remain raw codes in the current interface. "
        "A separate qualified overlay is the next bounded correction, not automatic deletion. Field-cell counts may overlap in people.",
        "4. **2007 has an omitted long-format job source.** `13B_mainoccupation.dta` contains "
        f"{r['supplemental_2007']['rows']:,} job rows for {r['supplemental_2007']['persons']:,} people. All link to EC with matching household keys, "
        "and person/job-index keys are unique. It is outside the original builder selection, which explains the six all-NULL canonical fields. "
        "Job indices 1/2 suggest primary/secondary rows but are not independently questionnaire-certified. "
        f"There are {r['supplemental_2007']['secondary_persons_without_main_job_row']:,} people with index 2 but no index 1. "
        "A pivot, source-row lineage and explicit treatment of job-count conflicts are needed before recovery; no values are filled here.", "",
        "**Do not treat every zero or unusual code as missing.** In 2004, industry `00` is explicitly labelled growing of cereals and other crops n.e.c.: "
        "14,515 main-job and 920 secondary-job cells. These are substantive source codes, not NULL candidates. "
        "A further 12 retained cells in 2019/2021 have no corresponding embedded label (listed in the detail report); their meanings remain unresolved. "
        "In particular, unlabelled industry 9999 is not automatically the labelled 9990 not-stated code.", "",
        "## Evidence and denominators", "",
        "Seven English household forms were freshly re-extracted with macros disabled, all sheets compared with frozen cells. "
        "42 field/question correspondences map to 39 distinct printed items because 2004 repeats primary/secondary job rows. "
        "The 2009 printed subsection A / released variable subsection C difference is explicitly located. "
        "54 existing raw field-wave transformations and their job-count dependencies were reproduced from 11 Stata sources, including fresh labels.", "",
        "Printed eligibility is age 10+ in 2004 and 5+ in inspected later forms. For 2004, the literal Part B route requires job count at least one/two. "
        "For later inspected forms, main details accept first OR second work screen Yes; secondary details additionally require at least one additional job. "
        "These routes are diagnostics, not a newly certified labour-force denominator. The inherited cleaner suppresses secondary details for known job counts below two, "
        "but not for unknown counts. The 2014 form remains a draft; 2007/2017 household forms are unverified, and 2019 image-form transcription is pending. "
        "2019 embedded code labels do not establish its missing questionnaire routes. Two unmatched HL records remain; 2004 general sampling weights are unavailable.", "",
        "| Wave | EC records | Any of six non-null | All six non-null | Unmatched HL |", "| --- | ---: | ---: | ---: | ---: |"]
    for w in r['wave_counts']:
        lines.append("| " + " | ".join([w['survey_wave'], *[f"{w[k]:,}" for k in ['rows','any_batch_nonnull','all_six_nonnull','hl_unmatched']]]) + " |")
    lines += ["", "All-six completeness is not a recommended sample: many people do not have a secondary job.", "",
        "[Detailed field-wave counts, option lists, source cells and recovery diagnostics](cses-employment-classification-field-waves.md) "
        "and the [aggregate evidence snapshot](../data/processing/cses/employment_classification_review_v1/review.json) retain the audit trail.", "",
        ("A forced read-only database transaction matched all selected values in both the original EC table and current corrected EC view: "
         f"332,903 records and {len(r['database_check']['selected_columns'])} columns per relation. This is a selected-column comparison, not a full relation validation."
         if r['database_check'].get('all_selected_values_equal') else "Live database checks were not performed."), "",
        "```mermaid", "flowchart LR", '    Q["7 household forms"] --> L["42 field/question links"]',
        '    R["11 selected Stata files"] --> T["54 reproduced field-wave mappings"]',
        '    C["2009 codebook + embedded labels"] --> D["Wave-specific code meanings and exceptions"]',
        '    S["2007 omitted job rows + industry dictionary"] --> P["Recovery proposal: pivot, keys, count conflicts"]',
        '    L --> D', '    T --> D', '    D --> N["Qualified interpretation proposal; no publication"]',
        '    P --> N', "```", "",
        "This is a local review topology, not a new database graph. Published graph v13 and all earlier release/review snapshots remain frozen. "
        "Spreadsheet guidance informed code-column/description pairing, literal option checks and preservation of original observations.", "",
        "Reproduce using the bundled runtime: `rsc/cses_db/review_cses_employment_classification.py --verify-workbooks --soffice /path/to/bundled/soffice`, "
        "then `.venv/bin/python rsc/cses_db/review_cses_employment_classification.py --check-database`. Changed snapshots require fresh `--output` / `--docs-dir`. "
        "No Git/DVC push or database publication is implied.", "",
        "Next resolve the scoped labelled-missing overlay and the 2007 source-grain/gate recovery contract. "
        "Do not publish an all-wave classification crosswalk without authoritative wave-specific classification evidence.", ""]
    details = ["# CSES classification field-wave evidence", "", "Companion to the [batch brief](cses-employment-classification-alignment.md). "
        "Observed distinct codes are not questionnaire option counts. All counts describe retained baseline values, including labelled missing codes.", ""]
    for field in FIELDS:
        details += [f"## {field}", "", "| Wave | Rows | Raw non-null | Canonical non-null | Distinct codes | Labelled missing | Cleaner removed | Secondary suppressed | Outside known route | Route unknown |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for p in r['profiles']:
            if p['field'] != field:
                continue
            details.append("| " + " | ".join([p['survey_wave'], *[f"{p[k]:,}" if p[k] is not None else "Not assessed" for k in
                ['rows','raw_nonnull','nonnull','observed_distinct_codes','labelled_missing_count','cleaner_removed','secondary_suppressed','nonnull_outside_known_route','route_unknown']]]) + " |")
        details.append("")
    details += ["## Explicit missing / not-stated codes retained", "", "| Wave | Field | Code | Cells |", "| --- | --- | --- | ---: |"]
    for p in r['profiles']:
        for code, n in p['labelled_missing_or_not_stated'].items():
            details.append(f"| {p['survey_wave']} | {p['field']} | `{code}` | {n:,} |")
    details += ["", "## Printed employer options", "", "The two job blocks share each wave's code set, but no all-wave pooled dictionary is adopted. "
        "2004 source-label wording for code 7 conflicts with its printed wording. Later code 7 has a different meaning entirely.", "",
        "| Wave | Code | Label as printed (main job) |", "| --- | --- | --- |"]
    for q in r['questions']:
        if q['field'] == FIELDS[2]:
            for o in q['options']:
                details.append(f"| {q['survey_wave']} | {o['source_code']} | {' '.join(o['label_as_printed'].split())} |")
    details += ["", "## Exact source locators", "", "Classification descriptions are paired with their adjacent code columns; "
        "the code header alone is not the substantive question text. 2004 job rows C43/C44 identify first/second jobs.", "",
        "| Wave | Field | Source variable | Sheet | Description / code / header or options | Evidence |", "| --- | --- | --- | --- | --- | --- |"]
    for q in r['questions']:
        details.append(f"| {q['survey_wave']} | {q['field']} | {q['source_variable']} | {q['source_sheet']} | {q['question_text_cell']} / {q['question_code_cell']} / {q['detail_cell']} | {q['documentation_status']} |")
    details += ["", "## 2009 codebook coverage", "", "The following stored codes are absent from the named ISCO/ISIC sheets. "
        "Absence from this list is not proof of invalidity; the unheaded Sheet3 is preserved for review, not merged into a dictionary.", "",
        "| Field | Code | Cells |", "| --- | --- | ---: |"]
    for p in r['profiles']:
        for code, n in (p['observed_codes_not_in_2009_workbook_dictionary'] or {}).items():
            details.append(f"| {p['field']} | `{code}` | {n:,} |")
    if not any(p['observed_codes_not_in_2009_workbook_dictionary'] for p in r['profiles']):
        details.append("| None: all non-null 2009 codes are covered | — | 0 |")
    details += ["", "The 2009 workbook has 162 occupation and 249 industry dictionary entries, including not-stated categories. "
        "2019/2021 embedded industry dictionaries match its ISIC sheet literally; occupation dictionaries also match after trimming "
        "trailing spaces on codes 262 and 548. The two literal differences per occupation field are whitespace only, not different meanings. "
        "These bounded dictionary correspondences support reuse with explicit provenance, not unrestricted all-wave comparability or a revision assignment.", "",
        "| Wave | Field | Code | 2009 workbook label | Embedded label |", "| --- | --- | --- | --- | --- |"]
    for c in r['codebook_label_comparisons']:
        for code, labels in c['label_differences'].items():
            details.append(f"| {c['survey_wave']} | {c['field']} | `{code}` | {labels['codebook_2009']} | {labels['embedded_label']} |")
    details += ["", "## Observed codes without an embedded label", "", "Only fields with an embedded dictionary are assessed here. "
        "Unlabelled does not prove invalid or missing. The table contains 12 field-cells; no values are recoded.", "",
        "| Wave | Field | Code | Cells |", "| --- | --- | --- | ---: |"]
    for p in r['profiles']:
        for code, n in (p['nonnull_with_no_embedded_label'] or {}).items():
            details.append(f"| {p['survey_wave']} | {p['field']} | `{code}` | {n:,} |")
    details += ["", "## 2007 long-format recovery candidates", "", "These are candidate row-index interpretations, not certified main/secondary questionnaire mappings. "
        "No data has been filled. Known-count conflicts must be addressed explicitly rather than silently overwriting source records.", "",
        "| Candidate field | Job rows | Non-null before gate | Known count supports job | Known count conflicts | Count unknown |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for p in r['supplemental_2007']['candidate_fields']:
        details.append("| " + " | ".join([p['field'], *[f"{p[k]:,}" for k in ['raw_job_rows','candidate_nonnull_before_gate','candidate_nonnull_known_count_supports_job','nonnull_known_count_conflict','nonnull_job_count_unknown']]]) + " |")
    details += ["", "The companion 2007 `dbo_c_isic.dta` has " + str(len(r['supplemental_2007']['industry_dictionary'])) + " unique padded industry codes. "
        "Unmatched observed industry codes: `" + json.dumps(r['supplemental_2007']['industry_codes_absent_from_dictionary'], sort_keys=True) + "`. "
        "This supports a wave-specific lookup, not a cross-wave conversion. Full source hashes and metadata are in the aggregate evidence snapshot.", ""]
    return "\n".join(lines), "\n".join(details)


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
        write_once(output / "source_verification.json", verify_sources(args.root, args.soffice))
    else:
        result = make_review(args.root, output / "source_verification.json", args.check_database)
        brief, details = documents(result)
        write_once(output / "review.json", result)
        write_once(args.root / args.docs_dir / "cses-employment-classification-alignment.md", brief)
        write_once(args.root / args.docs_dir / "cses-employment-classification-field-waves.md", details)
        print(json.dumps(result['scope_counts']))


if __name__ == "__main__":
    main()
