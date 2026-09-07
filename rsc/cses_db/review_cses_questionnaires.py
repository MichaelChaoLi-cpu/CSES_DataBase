#!/usr/bin/env python3
"""Replay a bounded questionnaire review without rewriting its accepted inputs or any DB.

The review spec selects original cells, not heuristic prompts. Ordinary stdlib
code handles the frozen cell extracts; pandas/pyarrow are used only for the
separate raw-data/Parquet age-impact check. No workbook or database is written.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

from organize_cses_questionnaires import WAVES, digest, write_once

SPEC = "rsc/specs/cses_questionnaire_review_v1.json"
SELF = "rsc/cses_db/review_cses_questionnaires.py"
BUILDER = "rsc/cses_db/cses_hh_hl_common.py"
OUTPUT = "data/processing/cses/questionnaire_review_v1"
MEMBER_WAVES = ["2004", "2009", "2011-12", "2013", "2014", "2016", "2021"]
TARGETS = {100, 101, 199, 206, 207, 313, 316, 412, 415, 854, 1186, 1611, 1857, 1908, 2259, 3896}

# Explicit source-specific locators inspected in the complete member-roster header.
# The age restriction spans ONLY marital status and spouse ID, not the entire roster.
MEMBER_LAYOUT = {
    "2004": dict(sheet="01 Initial", respondent="A3", universe="A4", listing="C5", member="C7",
                 relationship=["AD7", "AH7"], relation_note=None, age_note="AA9", birth_note="V8",
                 marital_age="AR5", marital_merge="AR5:AX6", marital_code="AR17", spouse_code="AV17",
                 marital_options="AR9", father="AL10", mother="AO10", spouse="AV12",
                 birth_registration=[], absence=["T35", "T40", "T47", "X35", "X40", "X44", "X46", "X47"]),
    "2009": dict(sheet="01 A_ Initial", respondent="A5", universe="A6", listing="C7", member="C9",
                 relationship=["AA9", "AF9"], relation_note=None, age_note="X11", birth_note="S10",
                 marital_age="AT7", marital_merge="AT7:BB8", marital_code="AT19", spouse_code="AZ19",
                 marital_options="AT11", father="AK12", mother="AQ12", spouse="AZ14",
                 birth_registration=[], absence=["BT7", "BT12", "BT19", "BX7", "BX13", "BX16", "BX18", "BX19"]),
    "2011-12": dict(sheet="01 A_ Initial", respondent="A5", universe="A6", listing="C7", member="C9",
                    relationship=["AA9", "AF9"], relation_note="AA17", age_note="X11", birth_note="S10",
                    marital_age="AT7", marital_merge="AT7:BB8", marital_code="AT19", spouse_code="AZ19",
                    marital_options="AT11", father="AK12", mother="AQ12", spouse="AZ14",
                    birth_registration=[], absence=["BT7", "BT12", "BT19", "BX7", "BX13", "BX16", "BX18", "BX19"]),
    "2013": dict(sheet="01 A_ Initial", respondent="A5", universe="A6", listing="C7", member="C9",
                 relationship=["AA9", "AF9"], relation_note="AA17", age_note="X11", birth_note="S10",
                 marital_age="AT7", marital_merge="AT7:BB8", marital_code="AT19", spouse_code="AZ19",
                 marital_options="AT11", father="AK12", mother="AQ12", spouse="AZ14",
                 birth_registration=[], absence=["BT7", "BT12", "BT19", "BX7", "BX13", "BX16", "BX18", "BX19"]),
    "2014": dict(sheet="01 A_ Initial", respondent="A5", universe="A6", listing="C7", member="C9",
                 relationship=["AG9", "AL9"], relation_note="AG17", age_note="X11", birth_note="S10",
                 marital_age="AW7", marital_merge="AW7:BE8", marital_code="AW19", spouse_code="BC19",
                 marital_options="AW11", father="AQ12", mother="AT12", spouse="BC14",
                 birth_registration=["AA7", "AA9", "AA10", "AA16", "AA18", "AA19"],
                 absence=["BY7", "BY12", "BY19", "CC7", "CC13", "CC16", "CC18", "CC19"]),
    "2016": dict(sheet="01 A_ Initial", respondent="A5", universe="A6", listing="C7", member="C9",
                 relationship=["AG9", "AL9"], relation_note="AG17", age_note="X11", birth_note="S10",
                 marital_age="AW7", marital_merge="AW7:BE8", marital_code="AW19", spouse_code="BC19",
                 marital_options="AW11", father="AQ12", mother="AT12", spouse="BC14",
                 birth_registration=["AA7", "AA9", "AA10", "AA16", "AA18", "AA19"],
                 absence=["BY7", "BY12", "BY19", "CC7", "CC13", "CC16", "CC18", "CC19"]),
    "2021": dict(sheet="01 A_ Initial", respondent="B3", universe="B4", listing="C5", member="C10",
                 relationship=["AC7", "AH7"], relation_note=None, age_note="V9", birth_note="Q8",
                 marital_age="AU5", marital_merge="AU5:BC7", marital_code="AU17", spouse_code="BA17",
                 marital_options="AU10", father="AO10", mother="AR10", spouse="BA12",
                 birth_registration=["Y5", "Y7", "Y12", "Y15", "Y17"],
                 absence=["BR5", "BR12", "BR17", "BV5", "BV11", "BV16", "BV17", "BY5", "BY8", "BY17"]),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def norm(text):
    return " ".join(text.split())


def evidence(sheets, sheet, locators):
    require(sheet in sheets, f"Missing source sheet: {sheet}")
    require(all(c in sheets[sheet] for c in locators), f"Missing required cell in {sheet}: {locators}")
    return {c: sheets[sheet][c] for c in locators}


def parse_options(cells):
    """Read complete multiline lists without truncating continuation cells."""
    result = []
    for cell, text in cells.items():
        for match in re.finditer(r"(?ms)^\s*(\d{1,2})\s*=\s*(.*?)(?=^\s*\d{1,2}\s*=|\Z)", text):
            result.append({"source_code": int(match[1]), "label_as_printed": match[2].strip(),
                           "display_label": norm(match[2]), "source_cell": cell})
    codes = [o["source_code"] for o in result]
    require(len(codes) == len(set(codes)), "Duplicate option code across continuation cells")
    return result


def checked_inputs(root, spec):
    require(not spec["publication_authorized"] and not spec["whole_variable_harmonization_certified"],
            "This review is local only")
    values = {}
    for name, expected in spec["input_sha256"].items():
        payload = (root / spec["baseline"] / name).read_bytes()
        require(digest(payload) == expected, f"Accepted baseline changed: {name}")
        values[name] = json.loads(payload)
    inventory = values["source_inventory.json"]
    for path, expected in inventory["archive_sha256"].items():
        require(digest((root / path).read_bytes()) == expected, f"Raw archive changed: {path}")
    alignment = values["alignment.json"]
    require(digest((root / BUILDER).read_bytes()) == alignment["existing_member_builder_sha256"],
            "Published member builder changed")
    for file, key in [("align_cses_questionnaires.py", "implementation_sha256"),
                      ("organize_cses_questionnaires.py", "organizer_sha256")]:
        require(digest((root / "rsc/cses_db" / file).read_bytes()) == alignment[key],
                f"Accepted implementation changed: {file}")
    return values


def resolve_queue(spec, alignment, inventory, cell_sources):
    queue = {r["source_variable_id"]: r for r in alignment["source_links"]
             if r["status"] == "ambiguous_candidates_require_review"}
    selected = spec["question_resolutions"] + spec["identifier_resolutions"]
    ids = [r["source_variable_id"] for r in selected]
    require(len(ids) == len(set(ids)) and set(ids) == set(queue) == TARGETS,
            "Review must cover exactly the 16 frozen ambiguous links once")
    questions = {r["candidate_id"]: r for r in inventory["questions"]}
    sources = {r["source_file"]: r for r in inventory["sources"]}
    cells = {r["source_file"]: r["sheets"] for r in cell_sources}
    results = []
    for choice in selected:
        link = queue[choice["source_variable_id"]]
        candidates = [questions[q] for q in link["candidate_ids"]]
        paths = {c["source_file"] for c in candidates}
        require(len(paths) == 1, "Ambiguous candidates cross instrument versions")
        source_file = paths.pop()
        source = sources[source_file]
        require(source["survey_wave"] == link["survey_wave"], "Cross-wave resolution rejected")
        book = cells[source_file]
        row = {"source_variable_id": link["source_variable_id"], "survey_wave": link["survey_wave"],
               "variable_name": link["variable_name"], "variable_label": link["variable_label"],
               "data_source": {k: link[k] for k in ("dataset_id", "archive_relative_path", "member_path", "nested_member_path")},
               "source_file": source_file, "source_sha256": source["source_sha256"],
               "documentation_status": source["documentation_status"], "original_candidate_ids": link["candidate_ids"],
               "database_publication_approved": False, "whole_variable_harmonization_certified": False}
        decisions = []
        if "code_cell" in choice:
            found = [c for c in candidates if c["source_sheet"] == choice["sheet"]
                     and c["question_code_cell"] == choice["code_cell"]]
            require(len(found) == 1, "Inspected question occurrence not unique")
            selected_id = found[0]["candidate_id"]
            ev = evidence(book, choice["sheet"], [choice["code_cell"], choice["text_cell"], *choice["context_cells"]])
            row.update(role="interview_question", publication_class="ready_for_question_link_plan",
                       reviewed_text=ev[choice["text_cell"]], source_sheet=choice["sheet"],
                       code_cell=choice["code_cell"], text_cell=choice["text_cell"], evidence_cells=ev,
                       selected_candidate_id=selected_id, reason=choice["reason"])
            for candidate in candidates:
                decisions.append({"candidate_id": candidate["candidate_id"], "source_sheet": candidate["source_sheet"],
                                  "code_cell": candidate["question_code_cell"],
                                  "decision": "selected_question" if candidate["candidate_id"] == selected_id else "rejected_false_match",
                                  "reason": choice["reason"]})
        else:
            by_location = {(c["source_sheet"], c["question_code_cell"]): c for c in candidates}
            expected = {(s, c) for s, c, _ in choice["occurrences"]}
            require(len(expected) == len(candidates) and expected == set(by_location),
                    "Identifier review must account for every repeated candidate")
            for sheet, code, header in choice["occurrences"]:
                ev = evidence(book, sheet, [code, header])
                require(norm(ev[header]) == choice["label"], "Inspected identifier header changed")
                require(ev[code] == ("(3)" if row["source_variable_id"] == 199 else "(1)"), "Identifier column changed")
                decisions.append({"candidate_id": by_location[sheet, code]["candidate_id"],
                                  "source_sheet": sheet, "code_cell": code, "text_cell": header,
                                  "evidence_cells": ev, "decision": "reclassified_repeated_identifier_header",
                                  "reason": "One plot/parcel identifier repeated across table panels; nearby data-row numbers and section titles are not its label."})
            row.update(role="repeat_identifier", reviewed_text=choice["label"],
                       publication_class="qualified_metadata_only", selected_candidate_id=None,
                       reason="Preserve all header occurrences as identifier provenance, not interview-question records. Plot/parcel wording is not a cross-wave unit-equivalence certification.")
        row["candidate_decisions"] = decisions
        row["qualifications"] = (["The 2014 English instrument is a draft; no verified status is granted."]
                                 if source["documentation_status"] == "provisional" else [])
        results.append(row)
    return sorted(results, key=lambda r: r["source_variable_id"])


def review_members(alignment, inventory, cell_sources):
    sources = {s["source_file"]: s for s in inventory["sources"]}
    cells = {s["source_file"]: s["sheets"] for s in cell_sources}
    checked = alignment["reviewed_member_correspondences"]
    require(len(checked) == 28, "Expected the 28 accepted member correspondences")
    results, foundations = [], []
    for wave in MEMBER_WAVES:
        previous = [r for r in checked if r["survey_wave"] == wave]
        require(len(previous) == 4 and len({r["source_file"] for r in previous}) == 1, "Member source is not unique")
        source_file = previous[0]["source_file"]
        source = sources[source_file]
        layout = MEMBER_LAYOUT[wave]
        sheet = layout["sheet"]
        book = cells[source_file]
        locators = [layout[k] for k in ("respondent", "universe", "listing", "member", "age_note", "birth_note",
                                        "marital_age", "marital_code", "spouse_code", "marital_options", "father", "mother", "spouse")]
        locators += layout["relationship"] + layout["birth_registration"] + layout["absence"]
        if layout["relation_note"]:
            locators.append(layout["relation_note"])
        ev = evidence(book, sheet, locators)
        relationship = parse_options({c: ev[c] for c in layout["relationship"]})
        require([o["source_code"] for o in relationship] == list(range(1, 16)), "Incomplete 15-code relationship list")
        minimum = 15 if wave == "2004" else 13
        require(f"aged {minimum} and above" in ev[layout["marital_age"]], "Marital eligibility changed")
        require("absent for less than 12 months" in ev[layout["member"]], "Membership definition changed")
        marital = parse_options({layout["marital_options"]: ev[layout["marital_options"]]})
        require(len(marital) == (6 if wave == "2004" else 4), "Marital option list changed")
        absence_rule = (
            "Question 13 asks current absence. No answer-specific jump is printed in its option cell. "
            "The following question asks months absent in the past 12 months; 0 means less than one month, "
            "90 means always present. After question 14, move to next person. Do not invent a yes/no jump."
            if wave == "2004" else
            "Question 13 asks whether the member was present all days last week. Yes (1) explicitly skips to next person; "
            "No (2) continues to weeks absent during the past 12 months, with 0 for less than one week. "
            + ("The 2021 form then adds question 15, reason for absence (5 options)."
               if wave == "2021" else "After question 14, the form explicitly moves to next person.")
        )
        foundation = {"survey_wave": wave, "source_file": source_file, "source_sha256": source["source_sha256"],
                      "source_sheet": sheet, "documentation_status": source["documentation_status"],
                      "evidence_cells": ev, "relationship_options": relationship,
                      "relationship_note": ev.get(layout["relation_note"]),
                      "roster_universe": "All usually residing household members; lives here or absent for less than 12 months.",
                      "respondent": "Head, spouse, or another adult member if both are absent.",
                      "four_core_fields_age_eligibility": "All roster members; no separate age minimum printed for sex, age, relationship or presence/absence.",
                      "marital_and_spouse_minimum_age": minimum, "marital_options": marital,
                      "marital_age_header_merge": layout["marital_merge"],
                      "marital_skip_rule": "Non-partnered categories skip spouse ID to printed column 11/11a; partnered categories continue to spouse ID.",
                      "birth_registration_rule": "Ages 0-4 only; age 5+ skips to column 6. Four options; probe registration if no certificate."
                      if layout["birth_registration"] else "No column 5b birth-registration question in the inspected roster header.",
                      "absence_routing_rule": absence_rule,
                      "hh_aggregation_basis": "The existing builder counts all released HL roster rows, not only those present. A unique relationship code 1 identifies the head. An orphan housing row does not create a roster household.",
                      "qualifications": ["Questionnaire membership guidance does not prove released data obey every eligibility/skip rule.",
                                         "No wholesale screening, recoding, denominator change or database publication is authorized."],
                      "publication_class": "qualified_metadata_only", "database_publication_approved": False}
        if wave == "2014":
            foundation["qualifications"].append("English draft only; retain provisional evidence status.")
        foundations.append(foundation)
        for old in previous:
            field = old["canonical_name"]
            row = {**old, "review_id": "foundation-" + old["review_id"],
                   "review_status": "local_wording_options_universe_routing_reviewed",
                   "universe_reference": wave, "publication_class": "qualified_metadata_only",
                   "evidence_cells": evidence(book, sheet, [old["text_cell"], old["question_code_cell"]])}
            if field == "relationship_to_household_head":
                row.update(response_kind="categorical", option_count=15, options=relationship,
                           qualification="All 15 codes are located. Keep the literal 'Great/grand child' note in 2011-12, 2013, 2014 and 2016; it is absent from the other inspected headers. Do not silently recode grandchildren.")
            elif field == "age":
                row.update(response_kind="numeric_completed_years", option_count=None,
                           age_instruction=ev[layout["age_note"]], age_instruction_cell=layout["age_note"],
                           top_code={"value": 96, "meaning": "96 years or older"} if wave == "2004" else None,
                           unknown_age_marker="98" if wave == "2004" else None if wave == "2021" else "-",
                           qualification="2004 code 96 is top-coded, not exact age. 2004 questionnaire 98 and released-data 99 remain distinct evidence. Later dash missing markers require data encoding checks; the 2021 birth-date 98 instruction is not an age-98 instruction.")
            elif field == "absent_from_household":
                row.update(response_kind="categorical", option_count=2, options=old["simple_options_checked"],
                           canonical_absent_mapping={"1": 1, "2": 0} if wave == "2004" else {"1": 0, "2": 1},
                           reference_period="Current status" if wave == "2004" else "Past 7 days",
                           qualification=absence_rule + " These two reference periods are not analytically interchangeable.")
            else:
                row.update(response_kind="categorical", option_count=2, options=old["simple_options_checked"],
                           publication_class="qualified_metadata_only" if wave == "2014" else "ready_for_question_link_plan",
                           qualification="Codes 1=Male and 2=Female; use each wave's roster universe. 2014 remains draft.")
            row["previous_wording_review_interpretation"] = old["interpretation"]
            row["interpretation"] = row["qualification"]
            results.append(row)
    gaps = [{"survey_wave": wave, "publication_class": "insufficient_evidence", "database_publication_approved": False,
             "reason": "Household questionnaire not located; no transfer from another wave."
             if wave in {"2007", "2017"} else "Image-based 2019 DOCX needs page transcription; other-wave text is not substituted."}
            for wave in WAVES if wave not in MEMBER_WAVES]
    return results, foundations, gaps


def age_impact(root):
    """Aggregate-only diagnostic: raw Stata and existing Parquet, without person disclosure."""
    import pandas as pd

    archive_path = "data/raw/CSES 2004.zip"
    member = "CSES 2004/Stata 2004/2004hh_s01a_hhmembers.dta"
    with zipfile.ZipFile(root / archive_path) as archive:
        payload = archive.read(member)
    raw = pd.read_stata(io.BytesIO(payload), convert_categoricals=False, columns=["q01a05", "q01a06"])
    counts = {str(code): int(raw.q01a05.eq(code).sum()) for code in (96, 98, 99)}
    tables = []
    for name in ("HL", "ED", "EC", "HH"):
        path = f"data/processing/cses/final_{name}_CSES.parquet"
        age = "Household Head Age" if name == "HH" else "Age"
        df = pd.read_parquet(root / path, columns=["Survey Wave", age])
        wave = df.loc[df["Survey Wave"].astype(str).eq("2004")]
        tables.append({"table": f"final_{name}_CSES", "path": path, "sha256": digest((root / path).read_bytes()),
                       "age_column": age, "wave_rows": len(wave), "age_96_rows": int(wave[age].eq(96).sum())})
    return {"source_file": archive_path + "::" + member, "source_sha256": digest(payload),
            "source_rows": len(raw), "source_code_counts": counts,
            "raw_topcoded_heads": int((raw.q01a05.eq(96) & raw.q01a06.eq(1)).sum()), "tables": tables,
            "finding": "2004 questionnaire AA9 defines 96 as 96+. The existing builder retains 96 and its common metadata describes completed age without a top-code qualification.",
            "proposed_follow_up": "Plan an explicit age-top-code flag/qualified analysis interface and metadata update. Preserve raw/source age. Do not replace 96 with a guessed exact age or silently delete the records.",
            "not_affected_by_topcoding": "All 96+ members remain in age 65+; thresholds 0-14/15-64/65+ do not change. Exact-age statistics require qualification.",
            "data_modified": False, "database_mutated": False}


def md(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def reports(review):
    lines = ["# Resolved questionnaire ambiguity queue", "",
             "Sixteen source-variable ambiguities are resolved locally: nine interview questions and seven repeated land identifiers.",
             "This is a review overlay, not a rewrite of the accepted extraction or a database publication.", "",
             "| Source ID | Wave | Variable | Role | Correct label | Publication class |",
             "| --- | --- | --- | --- | --- | --- |"]
    for row in review["ambiguity_resolutions"]:
        lines.append("| " + " | ".join(md(row[k]) for k in ("source_variable_id", "survey_wave", "variable_name", "role", "reviewed_text", "publication_class")) + " |")
    for row in review["ambiguity_resolutions"]:
        lines.extend(["", f"## {row['source_variable_id']}: {row['survey_wave']} {row['variable_name']}", "",
                      f"Source: `{row['source_file']}`", f"SHA-256: `{row['source_sha256']}`", "",
                      f"Data member: `{row['data_source']['archive_relative_path']}::{row['data_source']['member_path']}"
                      + ("::" + row["data_source"]["nested_member_path"] if row["data_source"]["nested_member_path"] else "") + "`", "",
                      row["reason"], *row["qualifications"], ""])
        if row["role"] == "interview_question":
            lines.append(f"Selected: `{row['source_sheet']}!{row['code_cell']}` → `{row['text_cell']}`: {md(row['reviewed_text'])}")
        lines.append("")
        for decision in row["candidate_decisions"]:
            lines.append(f"- `{decision['candidate_id']}`: `{decision['source_sheet']}!{decision['code_cell']}` "
                         f"{decision['decision']}" + (f" → `{decision['text_cell']}`" if "text_cell" in decision else ""))
    queue = "\n".join(lines) + "\n"
    lines = ["# HH and HL questionnaire foundations", "",
             "Seven original English forms, four core member topics, 28 field-wave records. These extend the accepted wording-only checks.",
             "No household questionnaire is borrowed for 2007 or 2017; 2019 remains a separate image-transcription queue. 2014 remains draft.", "",
             "| Wave | Relationship choices | Marital choices | Marital/spouse minimum age | Birth-registration question |",
             "| --- | --- | --- | --- | --- |"]
    for f in review["member_foundations"]:
        lines.append(f"| {f['survey_wave']} | 15 | {len(f['marital_options'])} | {f['marital_and_spouse_minimum_age']} | "
                     + ("Ages 0-4; 4 choices" if f["survey_wave"] in {"2014", "2016", "2021"} else "Not in inspected roster header") + " |")
    lines.extend(["", "Sex and absence/presence each have two choices. Age is numeric, not a finite-choice field.", "",
                  "## Population and aggregation", "",
                  "The seven forms ask for all usually residing members. A person counts if living here or absent for less than 12 months. "
                  "The head is listed first; the respondent is the head, spouse or another adult when both are absent. "
                  "The four core topics have no separate age minimum. The age-13/15 restriction applies only to marital status and spouse ID.", "",
                  "Current HH composition counts released HL roster rows, including absent members; it is not a count of people present that week. "
                  "A unique relationship code 1 supplies head attributes. The source instruction to list the head first is not grounds to invent a head. "
                  "A questionnaire rule is not proof of row-level compliance; this review does not filter members or alter denominators.", "",
                  "## Relationship codes", "",
                  "The complete lists occupy two neighboring cells in every inspected form. Spelling/wrapping differ; source labels remain in JSON.", "",
                  "| Code | Label (2009 wording) |", "| --- | --- |"])
    for o in next(f for f in review["member_foundations"] if f["survey_wave"] == "2009")["relationship_options"]:
        lines.append(f"| {o['source_code']} | {md(o['display_label'])} |")
    lines.extend(["", "2011-12, 2013, 2014 and 2016 additionally print: 'Great/grand child should be reported in other relatives'. "
                  "The literal note is retained; it does not authorize silently moving code-8 grandchildren to code 13. "
                  "No such note was found in the inspected 2004, 2009 or 2021 member headers.", "",
                  "## Age and missing values", "",
                  "2004: 00 = younger than one; 96 = 96 years or older; 98 = don't know. The released data contain a separate 99 sentinel. "
                  "2009–2016 inspected forms: 0 = younger than one; dash = unknown. 2021 age instructions only specify 0 for infants; "
                  "the neighboring birth-date instruction uses 98 but is not an age instruction.", "",
                  "## Presence and routing", "",
                  "2004 asks current absence (1=yes, 2=no). Later forms ask presence all days last week (1=yes, 2=no). "
                  "The existing builder already reverses the later coding and retains the reference period. Current status and last-week status remain different measures.", ""])
    for f in review["member_foundations"]:
        lines.extend([f"## {f['survey_wave']} source instructions", "", f"Source: `{f['source_file']}`", "",
                      f"SHA-256: `{f['source_sha256']}`", "", f"Sheet: `{f['source_sheet']}`", "",
                      f["absence_routing_rule"], "", f["birth_registration_rule"], "",
                      "Exact cells (including continuation options, special codes and routing):", ""])
        for cell, text in f["evidence_cells"].items():
            lines.append(f"- `{cell}`: {md(text)}")
    members = "\n".join(lines) + "\n"
    impact = review["age_impact"]
    lines = ["# Questionnaire review v1", "",
             "This local, append-only review resolves the accepted 16-item ambiguity queue and completes source-level HH/HL roster foundations for seven English forms. "
             "It does not approve all 1,156 new candidates, change published data, or archive Git/DVC versions.", "",
             "- [Resolved queue](resolved-queue.md)", "- [HH/HL options, population and routing](member-foundations.md)",
             "- [Complete evidence, decisions, hashes and age-impact counts](review.json)", "",
             "## Publication classification", "",
             "| Scope | Ready for question-link planning | Qualified metadata only | Insufficient questionnaire evidence |",
             "| --- | --- | --- | --- |", "| 16 ambiguous source links | 9 questions | 7 identifiers (one draft) | 0 |",
             "| 28 member field-wave records | 6 sex correspondences | 22 (draft, age, relationship notes or period/routing limits) | 0 within inspected seven waves |",
             "| Missing household questionnaire waves | 0 | 0 | 3 waves: 2007, 2017, 2019 |", "",
             "These counts have different units and must not be added. 'Ready' is limited to the stated question-link evidence; it is not whole-variable certification or authorization to publish.", "",
             "## New age qualification", "", impact["finding"], "",
             f"Raw 2004 counts: 96 → {impact['source_code_counts']['96']}; 98 → {impact['source_code_counts']['98']}; "
             f"99 → {impact['source_code_counts']['99']}. Top-coded heads: {impact['raw_topcoded_heads']}.", "",
             "| Existing local table | 2004 rows | Age=96 rows |", "| --- | --- | --- |"]
    for t in impact["tables"]:
        lines.append(f"| {t['table']} | {t['wave_rows']} | {t['age_96_rows']} |")
    lines.extend(["", "These are table rows, not additive counts of distinct people. The check reads local canonical Parquet files, not a fresh live-database snapshot.", "",
                  impact["not_affected_by_topcoding"], "", impact["proposed_follow_up"], "",
                  "## Next gate", "",
                  "Prepare the bounded age-top-code/metadata correction and a separate publication plan for the reviewed questionnaire evidence. "
                  "Identifiers require provenance representation, not fabricated interview questions. "
                  "Retain provisional 2014 status, literal relationship notes and missing-wave gaps. "
                  "Education and employment questionnaire review can follow the member-foundation gate; 2019 page transcription remains independent.", ""])
    return {"README.md": "\n".join(lines), "resolved-queue.md": queue, "member-foundations.md": members}


def build(root, spec):
    inputs = checked_inputs(root, spec)
    alignment, inventory, cells = (inputs[k] for k in ("alignment.json", "source_inventory.json", "source_cells.json"))
    resolved = resolve_queue(spec, alignment, inventory, cells)
    members, foundations, gaps = review_members(alignment, inventory, cells)
    return {"review_id": spec["review_id"], "input_sha256": spec["input_sha256"],
            "spec_sha256": digest((root / SPEC).read_bytes()), "implementation_sha256": digest((root / SELF).read_bytes()),
            "member_builder_sha256": digest((root / BUILDER).read_bytes()),
            "ambiguity_resolutions": resolved, "reviewed_member_fields": members, "member_foundations": foundations,
            "missing_wave_evidence": gaps, "age_impact": age_impact(root),
            "summary": {"queue_resolved": len(resolved), "queue_unresolved": 0,
                        "roles": dict(Counter(r["role"] for r in resolved)),
                        "member_fields": len(members), "member_waves": len(foundations),
                        "member_publication_classes": dict(Counter(r["publication_class"] for r in members)),
                        "nonambiguous_candidates_outside_this_review": sum(
                            r["status"] == "candidate_requires_review"
                            and r["source_variable_id"] not in {m["source_variable_id"] for m in members}
                            for r in alignment["source_links"])},
            "database_mutated": False, "new_mappings_published": 0, "source_archives_modified": False,
            "historical_alignment_modified": False, "publication_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, default=Path(OUTPUT))
    args = parser.parse_args()
    spec = json.loads((args.root / SPEC).read_text())
    review = build(args.root, spec)
    products = {"review.json": review, **reports(review)}
    # Check every target before writing any: a changed historical output cannot
    # leave a partially updated package. write_once enforces the same rule again.
    from organize_cses_questionnaires import encoded

    output = args.root / args.output
    for name, content in products.items():
        path = output / name
        payload = content.encode() if isinstance(content, str) else encoded(content)
        require(not path.exists() or path.read_bytes() == payload, f"Refusing differing historical output: {path}")
    for name, content in products.items():
        write_once(output / name, content)
    print(json.dumps(review["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
