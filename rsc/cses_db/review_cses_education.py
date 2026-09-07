#!/usr/bin/env python3
"""Review ED source questions, options, routing and aggregate impacts; never publish."""
from __future__ import annotations

import argparse
import io
import json
import re
import zipfile
from pathlib import Path

from organize_cses_questionnaires import WAVES, digest, write_once

SELF = "rsc/cses_db/review_cses_education.py"
SPEC = "rsc/specs/cses_education_review_v1.json"
BASE = "data/processing/cses/questionnaire_alignment_v1"
OUTPUT = "data/processing/cses/education_review_v1"
DERIVED = ["education_level_harmonized", "current_education_level_harmonized"]
GROUPS = {0: "None", 1: "Preschool", 2: "Primary", 3: "Lower secondary", 4: "Upper secondary",
          5: "Technical/vocational", 6: "Higher education", 7: "Other"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_inputs(root):
    spec = json.loads((root / SPEC).read_text())
    require(not spec["database_publication_authorized"] and not spec["canonical_data_changes_authorized"], "Review cannot authorize writes")
    require(digest((root / "rsc/cses_db/cses_education.py").read_bytes()) == spec["education_builder_sha256"], "Frozen education builder changed")
    return spec, *[json.loads((root / BASE / name).read_text()) for name in
                   ("alignment.json", "source_inventory.json", "source_cells.json")]


def selected_sources(spec, inventory):
    sources = [s for s in inventory["sources"] if s["survey_wave"] in spec["layouts"]
               and s["instrument_type"] == "household_questionnaire" and s["language_code"] == "en"
               and s["registered_instrument_id"] is not None]
    require(len(sources) == len(spec["layouts"]) == 7 and len({s["survey_wave"] for s in sources}) == 7, "Seven unique selected forms required")
    return sources


def verify_workbooks(root, soffice):
    """Bundled-runtime mode: fresh macro-disabled extraction, no workbook authorship."""
    from organize_cses_questionnaires import workbook_cells

    spec, _, inventory, cells = load_inputs(root)
    frozen = {s["source_file"]: s["sheets"] for s in cells}
    rows = []
    for source in selected_sources(spec, inventory):
        payload = (root / source["archive_relative_path"]).read_bytes()
        require(digest(payload) == inventory["archive_sha256"][source["archive_relative_path"]], "Raw archive changed")
        for member in source["member_chain"]:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                payload = archive.read(member)
        require(digest(payload) == source["source_sha256"], "Original questionnaire hash mismatch")
        fresh = workbook_cells(payload, source["extension"], soffice)
        require(fresh == frozen[source["source_file"]], "Fresh extraction differs from frozen literal cells")
        rows.append({"survey_wave": source["survey_wave"], "source_file": source["source_file"],
                     "source_sha256": source["source_sha256"], "all_sheets_equal": True,
                     "education_cells_checked": len(fresh[spec["sheet"]])})
        print(f"{source['survey_wave']}: original workbook cells verified", flush=True)
    return {"sources": rows, "source_cells_sha256": digest((root / BASE / "source_cells.json").read_bytes()),
            "implementation_sha256": digest((root / SELF).read_bytes()), "workbooks_modified": False}


def options(text, cell, field):
    """Keep printed entries and explicitly distinguish grades omitted with ellipses."""
    entries = {}
    for match in re.finditer(r"(?ms)^\s*(\d{1,2})\s*=\s*(.*?)(?=^\s*\d{1,2}\s*=|\Z)", text):
        code = int(match[1])
        require(code not in entries, "Duplicate printed response code")
        label = match[2].strip()
        entries[code] = {"source_code": code, "label_as_printed": label, "source_cell": cell,
                         "label_basis": "literal_printed_entry", "is_unknown_code": code == 98}
    if field in {"highest_education_level_source_code", "current_education_level_source_code"}:
        require(all(c in entries for c in (0, 1, 2, 11, 12)), "Grade-range anchors missing")
        require("..." in text, "Cannot expand grades without printed ellipsis")
        for code in range(3, 11):
            if code not in entries:
                entries[code] = {"source_code": code, "label_as_printed": None, "source_cell": cell,
                                 "label_basis": "grade_sequence_expanded_from_printed_ellipsis",
                                 "display_label": f"Class {code}" + (" completed" if field.startswith("highest") else ""),
                                 "is_unknown_code": False}
    return [entries[c] for c in sorted(entries)]


def expected_codes(wave, field):
    if field in {"can_read", "can_write", "ever_attended_school", "currently_attending_school"}:
        return {1, 2}
    if field == "years_attended_school":
        return set()
    if field == "highest_education_level_source_code":
        return set(range(20)) | {90, 98} if wave == "2004" else set(range(22)) | {88, 98}
    if wave == "2004":
        return set(range(20)) | {98}
    if wave in {"2009", "2011-12"}:
        return set(range(17))
    return set(range(13)) | ({15, 16, 17, 21} if wave in {"2013", "2014"}
                            else {15, 16, 17, 18, 21} if wave == "2016" else {15, 16, 17, 18, 19, 20})


def evidence_review(spec, alignment, inventory, cell_sources):
    cells = {s["source_file"]: s["sheets"] for s in cell_sources}
    candidates = {q["candidate_id"]: q for q in inventory["questions"]}
    records, universes = [], []
    for source in selected_sources(spec, inventory):
        wave = source["survey_wave"]
        layout = spec["layouts"][wave]
        sheet = cells[source["source_file"]][spec["sheet"]]
        require(f"aged {layout['minimum_age']} years and older" in sheet[layout["universe"]], "Questionnaire age gate changed")
        context = {c: sheet[c] for c in [layout["universe"], layout["respondent"], layout["holiday"], *layout["extra_notes"]]}
        universes.append({"survey_wave": wave, "minimum_age": layout["minimum_age"],
                          "source_file": source["source_file"], "source_sheet": spec["sheet"],
                          "documentation_status": source["documentation_status"], "literal_instructions": context,
                          "actual_interview_respondent_count": None})
        for index, field in enumerate(spec["fields"]):
            column, option_cell = layout["columns"][index], layout["options"][index]
            if column is None:
                require(wave == "2004" and field == "years_attended_school", "Unexpected missing source item")
                continue
            text_cell, code_cell = f"{column}{layout['question_row']}", f"{column}{layout['code_row']}"
            links = [r for r in alignment["source_links"] if r["survey_wave"] == wave and r["module_code"] == "education"
                     and ["final_ED_CSES", field] in r["canonical_keys"]]
            require(len(links) == 1, "Question must have exactly one source-variable identity")
            link = links[0]
            matched = [candidates[c] for c in link["candidate_ids"] if candidates[c]["source_file"] == source["source_file"]
                       and candidates[c]["source_sheet"] == spec["sheet"] and candidates[c]["question_code_cell"] == code_cell]
            require(len(matched) == 1 and text_cell in matched[0]["text_cell_candidates"], "Reviewed cell is not the expected question candidate")
            opts = options(sheet[option_cell], option_cell, field)
            require({o["source_code"] for o in opts} == expected_codes(wave, field), f"Option set changed: {wave}/{field}")
            if field in {"ever_attended_school", "currently_attending_school"}:
                target = layout["never_skip_question" if field == "ever_attended_school" else "current_no_skip_question"]
                require(str(target) in sheet[option_cell] and ">>" in sheet[option_cell], "No-answer skip lost")
            if field == "years_attended_school":
                require("completed number of years" in sheet[option_cell], "Years unit instruction changed")
            records.append({"survey_wave": wave, "canonical_field": field, "source_variable_id": link["source_variable_id"],
                "source_variable": link["variable_name"], "data_source": {k: link[k] for k in
                    ("dataset_id", "archive_relative_path", "member_path", "nested_member_path")},
                "candidate_id": matched[0]["candidate_id"], "source_file": source["source_file"],
                "source_sha256": source["source_sha256"], "source_sheet": spec["sheet"],
                "question_text_cell": text_cell, "question_code_cell": code_cell, "options_cell": option_cell,
                "question_text": sheet[text_cell], "printed_question_number": sheet[code_cell],
                "options_and_routing_as_printed": sheet[option_cell], "options": opts,
                "substantive_option_count": sum(not o["is_unknown_code"] for o in opts) if opts else None,
                "unknown_option_count": sum(o["is_unknown_code"] for o in opts),
                "numeric_unit": "completed years attended; builder range 0–30 is a processing rule, not a printed maximum" if field == "years_attended_school" else None,
                "minimum_age": layout["minimum_age"], "requires_ever_attended_yes": field in
                    {"years_attended_school", "highest_education_level_source_code", "currently_attending_school", "current_education_level_source_code"},
                "requires_current_attendance_yes": field == "current_education_level_source_code",
                "documentation_status": source["documentation_status"],
                "review_status": "source_correspondence_options_and_routing_reviewed_with_qualifications",
                "whole_variable_certified": False, "database_publication_approved": False})
    require(len(records) == 48 and len(universes) == 7, "Expected 48 source question-wave reviews")
    return records, universes


def value_counts(series):
    return {str(int(k)) if float(k).is_integer() else str(float(k)): int(v)
            for k, v in series.dropna().value_counts().sort_index().items()}


def field_profile(frame, field, minimum_age, item_available=True):
    """Literal route diagnostics: no silently adopted estimator or missingness reason."""
    import pandas as pd

    observed = frame[field].notna()
    gated_ever = field in {"years_attended_school", "highest_education_level_source_code", "education_level_harmonized",
                           "currently_attending_school", "current_education_level_source_code", "current_education_level_harmonized"}
    gated_current = field in {"current_education_level_source_code", "current_education_level_harmonized"}
    route = pd.Series(True, index=frame.index, dtype="boolean")
    if gated_ever:
        route &= frame.ever_attended_school.eq(1)
    if gated_current:
        route &= frame.currently_attending_school.eq(1)
    assess_route = minimum_age is not None and item_available
    age_gate = frame.age.ge(minimum_age) if assess_route else pd.Series(pd.NA, index=frame.index, dtype="boolean")
    eligible = age_gate & route
    return {"field": field, "rows": len(frame), "nonnull": int(observed.sum()), "null": int((~observed).sum()),
            "observed_values": value_counts(frame[field]), "minimum_age_from_questionnaire": minimum_age,
            "source_item_available": item_available,
            "literal_route_eligible_records": int(eligible.fillna(False).sum()) if assess_route else None,
            "nonnull_within_literal_route": int((observed & eligible.fillna(False)).sum()) if assess_route else None,
            "literal_route_unknown_records": int(eligible.isna().sum()) if assess_route else None,
            "nonnull_below_minimum_age": int((observed & frame.age.lt(minimum_age).fillna(False)).sum()) if assess_route else None,
            "nonnull_despite_ever_no": int((observed & frame.ever_attended_school.eq(0).fillna(False)).sum()) if gated_ever and item_available else None,
            "nonnull_despite_current_no": int((observed & frame.currently_attending_school.eq(0).fillna(False)).sum()) if gated_current and item_available else None,
            "eligible_population_certified": False}


def raw_and_local(root, spec, alignment, reviews):
    import pandas as pd
    from cses_education import ED_ALIASES, harmonize_current_level, harmonize_highest_level
    from cses_hh_hl_common import AlignmentContext, find_column, snake_case, standardize_source
    from inventory_cses_archives import DataSource

    frame = pd.read_parquet(root / "data/processing/cses/final_ED_CSES.parquet").rename(columns=snake_case)
    require(len(frame) == 343204 and len(frame.columns) == 30 and not frame.duplicated(["survey_wave", "person_id"]).any(), "ED grain changed")
    require(not frame[["survey_wave", "person_id", "source_row_id"]].isna().any().any(), "Missing ED identity")
    reviewed = {(r["survey_wave"], r["canonical_field"]): r for r in reviews}
    alias_by_field = {snake_case(k): v for k, v in ED_ALIASES.items()}
    profiles, sources, waves = [], [], []
    for wave in WAVES:
        links = [r for r in alignment["source_links"] if r["survey_wave"] == wave and r["module_code"] == "education"
                 and ["final_ED_CSES", "can_read"] in r["canonical_keys"]]
        require(len(links) == 1, "One released education source required per wave")
        identity = links[0]
        chain = tuple(p for p in [identity["member_path"], identity["nested_member_path"]] if p)
        source = DataSource(root / identity["archive_relative_path"], chain)
        payload = source.read_bytes()
        with pd.io.stata.StataReader(io.BytesIO(payload), convert_categoricals=False) as reader:
            labels = reader.variable_labels()
            embedded_label_sets = len(reader.value_labels())
            raw = reader.read()
        context = AlignmentContext(root=root)
        context.frames[source.display_name(root)] = raw
        keys = standardize_source(context, source, wave, "ED").rename(columns=snake_case)
        current = frame.loc[frame.survey_wave.eq(wave)].set_index("source_row_id")
        require(len(current) == len(raw) and set(current.index) == set(keys.source_row_id), "Raw/current source-row identity mismatch")
        current = current.loc[keys.source_row_id].reset_index()
        for key in ["survey_wave", "person_id", "household_id", "source_archive", "source_submodule"]:
            require(current[key].equals(keys[key].astype(current[key].dtype)), f"Raw/current {key} identity mismatch")
        raw_fields = []
        for field, aliases in alias_by_field.items():
            column = find_column(raw, aliases)
            if column is None:
                require(wave == "2004" and field == "years_attended_school" and current[field].isna().all(), "Unexpected missing raw item")
                continue
            matches = [r for r in alignment["source_links"] if r["dataset_id"] == identity["dataset_id"] and r["variable_name"] == column
                       and ["final_ED_CSES", field] in r["canonical_keys"]]
            require(len(matches) == 1, "Raw source variable does not match frozen mapping")
            values = pd.to_numeric(raw[column], errors="coerce")
            if field in {"can_read", "can_write", "ever_attended_school", "currently_attending_school"}:
                expected = values.map({1: 1, 2: 0})
            elif field == "years_attended_school":
                expected = values.where(values.between(0, 30) & values.mod(1).eq(0))
            else:
                expected = values
            pd.testing.assert_series_equal(expected.astype(current[field].dtype), current[field], check_names=False)
            evidence = reviewed.get((wave, field))
            option_codes = {o["source_code"] for o in evidence["options"]} if evidence and evidence["options"] else None
            frequencies = value_counts(values)
            raw_fields.append({"field": field, "raw_variable": column, "variable_label": labels.get(column),
                "source_variable_id": matches[0]["source_variable_id"], "raw_nonnull": int(values.notna().sum()),
                "raw_null": int(values.isna().sum()), "raw_values": frequencies,
                "outside_reviewed_code_list": {k: n for k, n in frequencies.items() if float(k) not in option_codes} if option_codes is not None else None,
                "raw_to_existing_field_equal": True})
        highest = current.highest_education_level_source_code.map(lambda v: harmonize_highest_level(wave, v))
        cur = current.current_education_level_source_code.map(lambda v: harmonize_current_level(wave, v))
        cur = cur.where(current.currently_attending_school.eq(1).fillna(False))
        for field, values in zip(DERIVED, [highest, cur]):
            pd.testing.assert_series_equal(values.astype(current[field].dtype), current[field], check_names=False)
        sources.append({"survey_wave": wave, "dataset_id": identity["dataset_id"], "data_source": source.display_name(root),
                        "source_sha256": digest(payload), "rows": len(raw), "raw_fields": raw_fields,
                        "embedded_value_label_set_count": embedded_label_sets,
                        "existing_derived_mapping_reproduced": True})
        minimum_age = spec["layouts"].get(wave, {}).get("minimum_age")
        for field in [*spec["fields"], *DERIVED]:
            available = not (wave == "2004" and field == "years_attended_school")
            profiles.append({"survey_wave": wave, **field_profile(current, field, minimum_age, available)})
        code21 = current.current_education_level_source_code.eq(21).fillna(False)
        waves.append({"survey_wave": wave, "rows": len(current), "hl_unmatched": int(current.hl_link_matched.eq(0).sum()),
            "age_missing": int(current.age.isna().sum()), "minimum_age_from_questionnaire": minimum_age,
            "at_or_above_printed_minimum_age": int(current.age.ge(minimum_age).sum()) if minimum_age is not None else None,
            "below_printed_minimum_age": int(current.age.lt(minimum_age).sum()) if minimum_age is not None else None,
            "raw_code21_rows": int(code21.sum()),
            "raw_code21_current_yes": int((code21 & current.currently_attending_school.eq(1)).sum()),
            "raw_code21_existing_groups": value_counts(current.loc[code21, "current_education_level_harmonized"]),
            "current_yes_despite_ever_no": int((current.currently_attending_school.eq(1) & current.ever_attended_school.eq(0)).sum())})
    return frame, profiles, sources, waves


def normalize_legacy_source_paths(series):
    """Only the pre-existing, documented repository relocation; never alter DB paths."""
    return series.str.replace(r"^data/raw/CSE/", "data/raw/", regex=True)


def check_database(frame):
    """Independent live full-row comparison, retaining no individual data in outputs."""
    import pandas as pd
    from cses_baseline_metadata import connect_database
    from psycopg import sql

    with connect_database({"dbname": "mda"}) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        conn.execute("SET LOCAL statement_timeout='55s'")
        require(conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on", "Read-only required")
        columns = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='cses_data' AND table_name='final_ED_CSES' ORDER BY ordinal_position").fetchall()
        require([r["column_name"] for r in columns] == list(frame.columns), "Live ED column layout changed")
        live = pd.DataFrame(conn.execute(sql.SQL("SELECT {} FROM cses_data.\"final_ED_CSES\" ORDER BY survey_wave,person_id").format(
            sql.SQL(",").join(map(sql.Identifier, frame.columns)))).fetchall()).astype(frame.dtypes.to_dict())
        expected = frame.sort_values(["survey_wave", "person_id"]).reset_index(drop=True)
        normalized_paths = normalize_legacy_source_paths(live.source_archive)
        path_rows = int(live.source_archive.ne(normalized_paths).sum())
        live["source_archive"] = normalized_paths
        pd.testing.assert_frame_equal(live, expected, check_exact=True)
    return {"database": "mda", "transaction_read_only": True, "database_mutated": False,
            "full_local_live_rows_equal": True, "rows": len(frame), "fields": len(frame.columns),
            "comparison_only_path_normalization": "source_archive prefix data/raw/CSE/ -> data/raw/; established baseline relocation",
            "path_normalized_rows": path_rows, "database_paths_rewritten": False}


def make_review(root, verification, check_live):
    from plan_cses_age_topcode import checked_review

    checked_review(root)
    spec, alignment, inventory, cells = load_inputs(root)
    verified = json.loads(verification.read_text())
    require(verified["implementation_sha256"] == digest((root / SELF).read_bytes()), "Fresh extraction implementation changed")
    require(verified["source_cells_sha256"] == digest((root / BASE / "source_cells.json").read_bytes()), "Fresh extraction baseline changed")
    require(len(verified["sources"]) == 7 and all(r["all_sheets_equal"] for r in verified["sources"]), "Fresh original workbook verification required")
    questions, universes = evidence_review(spec, alignment, inventory, cells)
    frame, profiles, sources, waves = raw_and_local(root, spec, alignment, questions)
    return {"review_id": spec["review_id"], "implementation_sha256": digest((root / SELF).read_bytes()),
        "spec_sha256": digest((root / SPEC).read_bytes()), "education_builder_sha256": spec["education_builder_sha256"],
        "input_sha256": {name: digest((root / BASE / name).read_bytes()) for name in
            ("alignment.json", "source_inventory.json", "source_cells.json", "registry.json")},
        "canonical_parquet_sha256": digest((root / "data/processing/cses/final_ED_CSES.parquet").read_bytes()),
        "source_verification": verified, "questions": questions, "universes": universes,
        "profiles": profiles, "raw_sources": sources, "wave_counts": waves,
        "unreviewed_form_waves": spec["unreviewed_household_form_waves"], "correction_candidate": spec["correction_candidate"],
        "scope_counts": {"physical_fields": 30, "education_fields": 9, "direct_source_field_waves": 69,
                         "reviewed_question_waves": 48, "reviewed_forms": 7, "profile_field_waves": 90},
        "database_check": check_database(frame) if check_live else {"performed": False},
        "database_mutated": False, "canonical_data_mutated": False, "individual_records_saved": False,
        "all_wave_semantic_certification": False}


def md(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def documents(report):
    lines = ["# CSES education alignment brief", "", "Local evidence review; no new database publication or data correction.", "",
        "The education table has **343,204 member-wave records and 30 physical fields**. Nine fields concern education "
        "(seven source question families and two derived levels); the other 21 are identities, demographic/context or provenance fields. "
        "This review covers 69 available direct source-field/wave pairs, 48 question correspondences in seven English forms, "
        "and all 90 education-field/wave profiles. The 2014 form is a draft. Actual directly interviewed respondent counts remain unknown.", "",
        "## New mapping conflict: current postgraduate studies", "",
        "The 2013, 2014 and 2016 English forms label **current-level source code 21 as Postgraduate studies**, "
        "but the inherited builder maps it to **7=Other**. The proposed interpretation is **6=Higher education**. "
        "This is a proposed correction, not a change applied by this review. Highest-completed code 21 is Other and must not be changed with it.", "",
        "| Wave | Current-level code 21 records | Confirmed current attendance | Existing group | Evidence boundary |", "| --- | ---: | ---: | --- | --- |"]
    for w in report["wave_counts"]:
        if w["raw_code21_rows"]:
            boundary = "English form checked" if w["survey_wave"] in {"2013", "2016"} else "2014 draft only" if w["survey_wave"] == "2014" else "No household form: do not transfer the meaning"
            groups = "; ".join(f"{k}={GROUPS[int(k)]}: {n}" for k, n in w["raw_code21_existing_groups"].items())
            lines.append(f"| {w['survey_wave']} | {w['raw_code21_rows']} | {w['raw_code21_current_yes']} | {groups} | {boundary} |")
    lines += ["", "The 30 questionnaire-supported candidate rows comprise 12 from 2013/2016 and 18 from the 2014 draft. "
        "The additional eight 2017 rows are a separate unresolved scope. Neither group is silently corrected. "
        "The released 2017 education file has no embedded value-label sets to independently establish code 21. "
        "In 2021, current-level code 20 means Other, whereas highest-completed code 20 means Doctorate; "
        "current and completed-level dictionaries must remain separate.", "",
        "## What is aligned, and what still needs a decision?", "",
        "| Field family | Verified scope | Remaining boundary |", "| --- | --- | --- |",
        "| can_read / can_write | Same simple-message-in-any-language questions; 1=Yes / 2=No in all seven forms; existing 1/0 transformations reproduced | Five-plus universe in 2004, three-plus later; respondent/proxy protocols vary; three form gaps remain |",
        "| ever_attended_school / currently_attending_school | Fourteen question-wave records; two choices each; explicit No skips and holiday inclusion checked | Current attendance is downstream of ever-attendance; no automatic zero imputation or universal denominator |",
        "| years_attended_school | Six printed questions ask completed years attended; absent in 2004 | Numeric, not a fixed option list; 0–30 is an inherited cleaning rule, not a printed maximum; not equivalent to highest completed grade |",
        "| highest_education_level_source_code / education_level_harmonized | Seven full grade/code lists, unknown code 98 and none/no-class codes 90 versus 88 checked | Broad grouping collapses grades, certificates and incomplete undergraduate study; exact educational attainment is not established by the broad label |",
        "| current_education_level_source_code / current_education_level_harmonized | Seven current-level lists compared separately from completed attainment | Confirmed code-21 mapping conflict; further values absent from printed lists require separate evidence; 2014 remains provisional |", "",
        "No education field receives unrestricted all-ten-wave analytical certification from this batch. "
        "The questionnaire correspondence, literal options and routing are now documented for the inspected forms; "
        "no question link has been inserted into PostgreSQL.", "",
        "## Denominators and eligibility", "",
        "| Wave | ED records | Printed minimum age | At/above minimum | Below minimum | Missing age | Unmatched HL |", "| --- | ---: | --- | ---: | ---: | ---: | ---: |"]
    for w in report["wave_counts"]:
        lines.append("| " + " | ".join([w["survey_wave"], f"{w['rows']:,}", str(w["minimum_age_from_questionnaire"] or "Not verified"),
            *[f"{w[k]:,}" if w[k] is not None else "Not inferred" for k in ["at_or_above_printed_minimum_age", "below_printed_minimum_age"]],
            str(w["age_missing"]), str(w["hl_unmatched"])]) + " |")
    lines += ["", "Age-eligible records are not automatically actual respondents or final analysis denominators. "
        "The four unmatched education rows remain present, with unavailable inherited ages. "
        "2004 includes roster rows below the printed five-year threshold; the release is preserved. "
        "All nine education fields are NULL for its 7,266 known under-five records. "
        "2016 contains one age-two record despite a three-plus instruction; do not delete or alter it by inference.", "",
        "Respondent instructions differ: 2004 requests members age five-plus; 2009 names the head, spouse or another adult; "
        "2011-12 onward requests members age three-plus, asks parents for ages three to six and permits proxy interviews for absent people. "
        "The respondent-ID item appearing in later forms is outside the nine canonical education fields and is not counted as a new aligned variable.", "",
        "Literal routing: No to ever-attended skips to question 10 in 2004 or 11 later, bypassing years, completed level and current attendance. "
        "No to current attendance skips current level. School holidays still count as being in the school system. "
        "Recorded values outside these routes are diagnostic counts, not automatic proof of erroneous answers. "
        "Structural skips, released blanks, unknown code 98 and invalid codes are not interchangeable.", "",
        "There are 17 records reporting current attendance Yes while ever-attended is No (2014: 9; 2016: 7; 2021: 1). "
        "Retain and flag them; the literal-route denominators exclude them without rewriting stored answers. "
        "The 2004 release also uses 9 in the four Yes/No fields (216 field cells) and 99 in completed/current level "
        "(67 and 15 records). These codes are absent from the inspected printed option lists; the existing processing "
        "keeps detailed level source codes but sets the corresponding harmonized values to NULL. "
        "These are overlapping field counts, not 298 unique respondents, and their raw missingness reasons are not inferred.", "",
        "## Available values and literal-route counts", "",
        "The [90-cell profile](cses-education-field-wave-review.md) gives each field's non-null count, "
        "age/route-restricted non-null count and observed routing exceptions by wave. These are unweighted counts. "
        "2004 lacks general person/household weights. No rates or pooled estimates are certified here.", "",
        "## Evidence, topology and reproducibility", "",
        "```mermaid", "flowchart LR", '    Q["7 original English forms"] --> E["48 located questions, options and route contexts"]',
        '    R["10 raw education datasets"] --> V["69 source transformations / 9 canonical fields"]',
        '    E --> A["90 field-wave profiles and semantic comparison"]', '    V --> A',
        '    P["Existing ED Parquet and read-only mda"] --> A', '    A --> D["Documented scope, gaps and proposed code-21 correction"]', "```", "",
        "This local dependency diagram does not replace the published database lineage graph v11.", "",
        "Original workbook bytes and all extracted sheets were independently rechecked with macro-disabled legacy conversion. "
        "All seven raw source fields were compared row-by-row with existing ED outputs wherever present, and the two existing derived mappings "
        "were replayed. The latter proves reproduction, not semantic correctness. "
        + ("A separate read-only database transaction compared all 343,204 rows and 30 fields against the local artifact: "
           "29 fields match exactly; source_archive matches after the established comparison-only prefix relocation "
           "from data/raw/CSE/ to data/raw/. Database paths are not rewritten. " if report["database_check"].get("full_local_live_rows_equal") else "No live database comparison is claimed. ")
        + "Reports retain aggregates and source hashes only, not individual records.", "",
        "- [Complete literal options, locators, raw code frequencies and review results](../data/processing/cses/education_review_v1/review.json)",
        "- [Original population brief snapshot](cses-variable-brief.md)",
        "- [Previously prepared question-link batch](cses-questionnaire-batch-plan.md)", "",
        "To reproduce, first run `review_cses_education.py --verify-workbooks --soffice /path/to/bundled/soffice` "
        "with the bundled Python runtime, then run `.venv/bin/python rsc/cses_db/review_cses_education.py --check-database`. "
        "Use a fresh `--output` directory for a changed snapshot. Original review packages, builders, source data and published interfaces are not rewritten.", "",
        "## Next bounded decisions", "",
        "1. Review the code-21 correction scope separately: 12 records supported by non-draft forms, 18 by the 2014 draft, and eight unresolved 2017 records.",
        "2. Register the 2004 released 9/99 code qualifications separately from the printed unknown code 98, and retain the 17 contradictory attendance records as diagnostics.",
        "3. Recover/transcribe the three remaining household-form gaps before certifying all-wave comparability; continue EC review independently.",
        "", "Spreadsheet review guidance informed literal-source preservation, complete option lists and the separation of eligibility from observed records. "
        "Project Python handles Parquet/Stata/database verification; no source workbook is edited or authored.", ""]
    detail = ["# CSES education field-wave profiles", "", "Companion to the [education brief](cses-education-alignment.md). "
        "All counts are member-wave records, not directly interviewed people. The literal-route counts combine the printed age threshold "
        "with observed Yes gates; they are diagnostic denominators, not an adopted estimator. Missing forms receive no borrowed age/route denominator. "
        "The absent 2004 years-attended item receives no invented route denominator. Detailed source-code non-null counts can include unknown codes; "
        "consult the harmonized field and literal option evidence before treating them as substantive answers.", ""]
    for field in [r["field"] for r in report["profiles"] if r["survey_wave"] == "2004"]:
        detail += [f"## {field}", "", "| Wave | All records | Non-null | Null | Literal-route records | Non-null in route | Non-null below age | Non-null despite ever-No | Non-null despite current-No |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for r in report["profiles"]:
            if r["field"] == field:
                detail.append("| " + " | ".join([r["survey_wave"], *[f"{r[k]:,}" if r[k] is not None else "Not assessed" for k in
                    ["rows", "nonnull", "null", "literal_route_eligible_records", "nonnull_within_literal_route", "nonnull_below_minimum_age", "nonnull_despite_ever_no", "nonnull_despite_current_no"]]]) + " |")
        detail.append("")
    detail += ["## Substantive questionnaire choices", "", "Grade codes omitted with printed ellipses are explicitly expanded and flagged in the JSON. "
               "Counts below include these grade-sequence expansions but exclude unknown code 98. Numeric years have no finite choice count.", "",
               "| Wave | Field | Substantive choices | Unknown choices | Source cell | Status |", "| --- | --- | ---: | ---: | --- | --- |"]
    for r in report["questions"]:
        detail.append(f"| {r['survey_wave']} | {r['canonical_field']} | {r['substantive_option_count'] if r['substantive_option_count'] is not None else 'Numeric'} | {r['unknown_option_count']} | {r['source_sheet']}!{r['options_cell']} | {r['documentation_status']} |")
    detail += ["", "## Released codes absent from inspected printed lists", "", "These are evidence mismatches, not automatic recodes. "
               "Listed counts are raw released records, without filtering by attendance or age.", "",
               "| Wave | Field | Code | Records |", "| --- | --- | ---: | ---: |"]
    for s in report["raw_sources"]:
        for f in s["raw_fields"]:
            for code, n in (f["outside_reviewed_code_list"] or {}).items():
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
        require(args.soffice, "Explicit bundled converter required")
        write_once(output / "source_verification.json", verify_workbooks(args.root, args.soffice))
    else:
        report = make_review(args.root, output / "source_verification.json", args.check_database)
        brief, detail = documents(report)
        write_once(output / "review.json", report)
        write_once(args.root / args.docs_dir / "cses-education-alignment.md", brief)
        write_once(args.root / args.docs_dir / "cses-education-field-wave-review.md", detail)
        print(json.dumps(report["scope_counts"]))


if __name__ == "__main__":
    main()
