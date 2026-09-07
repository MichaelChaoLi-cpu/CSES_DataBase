#!/usr/bin/env python3
"""Build a local question/source/canonical crosswalk; never approve or publish guesses."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from organize_cses_questionnaires import WAVES, compact_code, digest, write_once


def matches(variable, code):
    variable, code = compact_code(variable), compact_code(code)
    if not code or not variable.startswith(code):
        return False
    remainder = variable[len(code):]
    return not remainder or not (code[-1].isdigit() and remainder[0].isdigit())


def longest_candidates(variable, pool):
    found = [(q, max((len(code) for code in q.get("source_code_candidates", [q["normalized_code"]])
                     if matches(variable, code)), default=0)) for q in pool]
    found = [(q, length) for q, length in found if length]
    if not found:
        return []
    length = max(size for _, size in found)
    return sorted((q for q, size in found if size == length), key=lambda q: q["candidate_id"])


def norm_text(text):
    return " ".join((text or "").replace("’", "'").replace("\u0092", "'").lower().split())


def md(text):
    return str(text if text is not None else "—").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def audit_registered_questions(registry, cell_sources):
    instruments = {i["instrument_id"]: i for i in registry["instruments"]}
    cells_by_source = {s["source_file"]: s["sheets"] for s in cell_sources}
    rows = []
    for q in registry["questions"]:
        instrument = instruments[q["instrument_id"]]
        context = q["repeat_context"]
        cell = context.get("question_text_cell") or context.get("locators", {}).get("text")
        sheet = context.get("source_sheet")
        source_cells = cells_by_source.get(instrument["source_file"], {}).get(sheet, {})
        locators = cell.split("+") if cell else []
        text = " ".join(source_cells[c] for c in locators) if locators and all(c in source_cells for c in locators) else None
        rows.append({"question_id": q["question_id"], "question_code": q["question_code"],
                     "source_file": instrument["source_file"], "source_sheet": sheet, "source_cell": cell, "source_cells": locators,
                     "registered_text": q["question_text"], "original_cell_text": text,
                     "status": "normalized_cell_matches" if text is not None and norm_text(text) == norm_text(q["question_text"])
                     else "source_locator_not_available" if text is None else "transcription_difference_requires_review"})
    return rows


def review_member_correspondences(alignment, inventory):
    """Replay the four explicitly inspected member-question families in seven source waves.

    This checks question correspondence and the two simple option sets only;
    it is not publication, universe harmonization, or transfer to missing waves.
    """
    candidates = {q["candidate_id"]: q for q in inventory["questions"]}
    sources = {s["source_file"]: s for s in inventory["sources"]}
    waves = ["2004", "2009", "2011-12", "2013", "2014", "2016", "2021"]
    texts = {
        "sex": "Sex",
        "age": "What is.. [NAME] ...’s age in completed years?",
        "relationship_to_household_head": "Relationship to the head",
        "absent_from_household": "Has ..[NAME].. been present all days last week?",
    }
    rows = []
    for field, expected in texts.items():
        for wave in waves:
            links = [r for r in alignment["source_links"] if r["survey_wave"] == wave and ["final_HL_CSES", field] in r["canonical_keys"]]
            if len(links) != 1 or len(links[0]["candidate_ids"]) != 1:
                raise ValueError(f"Reviewed member correspondence is no longer unique: {field}/{wave}")
            link = links[0]
            question = candidates[link["candidate_ids"][0]]
            wording = "Is ..[NAME].. absent from home at present?" if field == "absent_from_household" and wave == "2004" else expected
            if norm_text(question["question_text_candidate"]) != norm_text(wording):
                raise ValueError(f"Inspected question wording changed: {field}/{wave}")
            options = None
            if field in {"sex", "absent_from_household"}:
                expected_options = {"1": "male", "2": "female"} if field == "sex" else {"1": "yes", "2": "no"}
                found = {}
                for cell, text in question["context_cells"].items():
                    for code, label in re.findall(r"(?m)^\s*([12])\s*=\s*([A-Za-z]+)\s*$", text):
                        found[code] = {"label": label.lower(), "source_cell": cell}
                if {k: v["label"] for k, v in found.items()} != expected_options:
                    raise ValueError(f"Inspected simple options changed: {field}/{wave}")
                options = found
            note = {
                "sex": "Question label and 1=Male/2=Female agree; sample universe still follows each questionnaire.",
                "age": "Age in completed years agrees; this is numeric, not a finite-choice question. Boundary/missing codes require separate data review.",
                "relationship_to_household_head": "Question topic agrees. Complete relationship option lists and instructions are not certified by this wording check.",
                "absent_from_household": "2004 asks current absence; later inspected questionnaires ask presence throughout last week. Answer polarity and reference period differ. The existing builder reverses the later yes/no coding and retains the reference period.",
            }[field]
            identity = f"member-{field}-{wave}"
            link["local_wording_review_id"] = identity
            rows.append({"review_id": identity, "canonical_name": field, "survey_wave": wave,
                         "source_variable_id": link["source_variable_id"], "source_variable": link["variable_name"],
                         "candidate_id": question["candidate_id"], "source_file": question["source_file"],
                         "source_sha256": sources[question["source_file"]]["source_sha256"],
                         "source_sheet": question["source_sheet"], "text_cell": question["text_cell_candidates"][0],
                         "question_code_cell": question["question_code_cell"], "question_text": question["question_text_candidate"],
                         "simple_options_checked": options, "review_status": "local_question_correspondence_checked",
                         "documentation_status": question["documentation_status"], "interpretation": note,
                         "database_publication_approved": False, "whole_variable_harmonization_certified": False})
    return rows


def build(registry, inventory):
    instruments = {i["instrument_id"]: i for i in registry["instruments"]}
    sources = {s["source_file"]: s for s in inventory["sources"]}
    questions = {q["question_id"]: q for q in registry["questions"]}
    pools = defaultdict(list)
    for question in inventory["questions"]:
        source = sources[question["source_file"]]
        # Alternate versions are available for review, not silently made preferred.
        if source["registered_instrument_id"] is None or source["language_code"] != "en":
            continue
        pools[source["survey_wave"], source["instrument_type"]].append(question)
    memberships = defaultdict(list)
    for mapping in registry["mappings"]:
        for name in mapping["source_variable_names"] or []:
            memberships[mapping["dataset_id"], name.lower()].append(mapping)
    dictionary = defaultdict(list)
    for item in registry["housing_dictionary"]:
        dictionary[item["survey_wave"], item["canonical_name"]].append(item)
    canonicals = {c["canonical_variable_id"]: c for c in registry["canonical_variables"]}
    links = []
    for variable in registry["source_variables"]:
        role = "village_questionnaire" if variable["module_code"] == "village" else "household_questionnaire"
        pool = pools[variable["survey_wave"], role]
        candidates = longest_candidates(variable["variable_name"], pool)
        association = memberships[variable["dataset_id"], variable["variable_name"].lower()]
        canonical_keys = sorted({(canonicals[m["canonical_variable_id"]]["target_table"],
                                 canonicals[m["canonical_variable_id"]]["canonical_name"]) for m in association})
        registered = questions.get(variable["question_id"])
        existing = None
        if registered:
            instrument = instruments[registered["instrument_id"]]
            if instrument["survey_wave"] != variable["survey_wave"]:
                raise ValueError("Existing question link crosses waves")
            existing = {**registered, "source_file": instrument["source_file"],
                        "language_code": instrument["language_code"],
                        "link_status": variable["question_link_status"]}
            status = "existing_provisional_link" if variable["question_link_status"] == "proposed" else "existing_registered_link"
        elif candidates:
            texts = {norm_text(q["question_text_candidate"]) for q in candidates}
            status = "candidate_requires_review" if len(texts) == 1 else "ambiguous_candidates_require_review"
        elif not pool:
            status = "no_extractable_selected_questionnaire"
        else:
            status = "no_numbered_question_match"
        approved_housing = []
        for table, name in canonical_keys:
            if table == "final_HO_CSES" and name in {"dwelling_tenure_source_code", "main_cooking_fuel_source_code", "main_lighting_source_code"}:
                values = dictionary[variable["survey_wave"], name]
                approved_housing.append({"canonical_name": name, "dictionary_entries": len(values),
                    "dictionary_versions": sorted({v["dictionary_version"] for v in values}),
                    "basis": "user_approved_2016_transfer" if variable["survey_wave"] == "2017"
                             else "source_code_lookup" if variable["survey_wave"] == "2007"
                             else "published_source_evidence",
                    "not_a_new_question_link": True})
        links.append({"source_variable_id": variable["source_variable_id"], "dataset_id": variable["dataset_id"],
            "survey_wave": variable["survey_wave"], "module_code": variable["module_code"],
            "variable_name": variable["variable_name"], "variable_label": variable["variable_label"],
            "archive_relative_path": variable["archive_relative_path"], "member_path": variable["member_path"],
            "nested_member_path": variable["nested_member_path"], "status": status,
            "existing_question": existing, "candidate_ids": [q["candidate_id"] for q in candidates],
            "candidate_question_codes": sorted({q["normalized_code"] for q in candidates}),
            "canonical_keys": [list(key) for key in canonical_keys],
            "mapping_versions": sorted({m["mapping_version"] for m in association}),
            "approved_housing_dictionary": approved_housing,
            "requires_new_review_before_publication": registered is None,
            "semantic_equivalence_confirmed": False})
    # This preserves every mapping version, rather than choosing max(id) as an effective rule.
    by_canonical = defaultdict(list)
    for link in links:
        for key in link["canonical_keys"]:
            by_canonical[tuple(key), link["survey_wave"]].append(link)
    crosswalk = []
    for canonical in registry["canonical_variables"]:
        key = canonical["target_table"], canonical["canonical_name"]
        for wave in WAVES:
            rows = by_canonical[key, wave]
            wave_mappings = [m for m in registry["mappings"] if m["canonical_variable_id"] == canonical["canonical_variable_id"]
                             and any(v["dataset_id"] == m["dataset_id"] and v["survey_wave"] == wave
                                     for v in registry["source_variables"])]
            crosswalk.append({"target_table": key[0], "canonical_name": key[1], "survey_wave": wave,
                "canonical_definition": canonical["canonical_definition"], "analytical_grain": canonical["analytical_grain"],
                "source_variable_ids": [r["source_variable_id"] for r in rows],
                "source_variables": sorted({r["variable_name"] for r in rows}),
                "existing_question_ids": sorted({r["existing_question"]["question_id"] for r in rows if r["existing_question"]}),
                "candidate_ids": sorted({c for r in rows for c in r["candidate_ids"]}),
                "mapping_versions": sorted({m["mapping_version"] for m in wave_mappings}),
                "source_kinds": sorted({m["source_kind"] for m in wave_mappings}),
                "source_link_status_counts": dict(sorted(Counter(r["status"] for r in rows).items())),
                "alignment_basis": "existing_canonical_mapping_association_not_new_semantic_approval",
                "unlinked_reason": None if rows else "no_direct_source_variable_association; derived/context/absent scope requires review"})
    # Exact wording groups help reviewers find renumbering. Eligibility/options still require review.
    text_groups = defaultdict(list)
    for q in inventory["questions"]:
        s = sources[q["source_file"]]
        if s["registered_instrument_id"] and s["language_code"] == "en" and len(norm_text(q["question_text_candidate"])) > 20:
            text_groups[s["instrument_type"], norm_text(q["question_text_candidate"])].append(q)
    families = [{"wording": key[1], "instrument_type": key[0],
                 "survey_waves": sorted({q["survey_wave"] for q in rows}),
                 "candidate_ids": sorted(q["candidate_id"] for q in rows),
                 "equivalence_status": "same_normalized_wording_only; check universe, units, period, options and routing"}
                for key, rows in sorted(text_groups.items()) if len({q["survey_wave"] for q in rows}) >= 2]
    return {"alignment_id": "cses-questionnaire-alignment-v1", "database_mutated": False,
            "new_mappings_published": 0, "source_links": links, "canonical_crosswalk": crosswalk,
            "wording_families": families, "summary": {
                "source_variables": len(links), "existing_question_links": sum(bool(r["existing_question"]) for r in links),
                "new_candidate_links": sum(r["existing_question"] is None and bool(r["candidate_ids"]) for r in links),
                "canonical_fields": len(canonicals), "canonical_field_wave_rows": len(crosswalk),
                "cross_wave_wording_families": len(families),
                "link_status_counts": dict(sorted(Counter(r["status"] for r in links).items()))}}


def reports(output, registry, inventory, alignment):
    by_wave = defaultdict(list)
    for source in inventory["sources"]:
        by_wave[source["survey_wave"]].append(source)
    pool = {q["candidate_id"]: q for q in inventory["questions"]}
    source_index = {s["source_file"]: s for s in inventory["sources"]}
    lines = ["# CSES questionnaire organization and question alignment", "",
             "This is a local review workbench, not a new database publication. Original archives are unchanged.",
             "Question counts below are located candidate occurrences, including repeat headers and alternate versions.",
             "Unknown option counts are unknown, not zero. Same wording or code does not certify cross-wave equivalence.", "",
             "## Survey waves", "", "| Wave | Registered instruments | Extracted workbooks | Printed-code candidates | Existing source links | New candidate source links |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for wave in WAVES:
        sources = by_wave[wave]
        qs = [q for q in inventory["questions"] if q["survey_wave"] == wave]
        links = [r for r in alignment["source_links"] if r["survey_wave"] == wave]
        lines.append(f"| [{wave}](waves/{wave}.md) | {sum(s['registered_instrument_id'] is not None for s in sources)} | "
                     f"{sum(s['extraction_status'] == 'cells_extracted' for s in sources)} | {len(qs)} | "
                     f"{sum(bool(r['existing_question']) for r in links)} | {sum(not r['existing_question'] and bool(r['candidate_ids']) for r in links)} |")
        detail = [f"# CSES {wave} questionnaires", "", "## Sources and versions", "",
                  "Original files are referenced inside their archives; no rename, deletion or overwrite was performed.", "",
                  "| Source | Role | Registration | Extraction | Identical aliases |", "| --- | --- | --- | --- | ---: |"]
        for s in sources:
            detail.append(f"| {md(s['source_file'])} | {s['instrument_type']} | {s['documentation_status']} | {s['extraction_status']} | {len(s['identical_content_aliases'])} |")
        detail += ["", "## Question candidates in registered sources", "",
                   "These are locatable candidates, not newly approved transcriptions. Column headers, eligibility and shared options need layout review.", ""]
        for q in qs:
            if source_index[q["source_file"]]["registered_instrument_id"] is None:
                continue
            detail += [f"### {q['candidate_id']}", "", f"`{q['normalized_code']}` — {md(q['question_text_candidate'])}", "",
                       f"Source: `{q['source_file']}`; sheet `{q['source_sheet']}`; code cell `{q['question_code_cell']}`; "
                       f"text candidates `{', '.join(q['text_cell_candidates'])}`. {q['documentation_status']}.", ""]
        if not qs:
            detail += ["No numbered question candidates extracted. This is not evidence that the questions were not asked.", ""]
        write_once(output / "waves" / f"{wave}.md", "\n".join(detail))
    lines += ["", "## Crosswalks through the existing canonical definitions", "",
              "All historical mapping versions remain explicit. These associations do not newly approve question or value equivalence.", ""]
    for table in sorted({r["target_table"] for r in alignment["canonical_crosswalk"]}):
        lines.append(f"- [{table}](crosswalks/{table}.md)")
        detail = [f"# {table} question crosswalk", "",
                  "Source associations follow existing catalog rules; candidate links are local proposals only.",
                  "Empty direct-source lists can reflect derived/context fields or absent data and need interpretation.", "",
                  "| Canonical field | Wave | Source variables | Registered questions | Candidate codes | Source-link states |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for row in alignment["canonical_crosswalk"]:
            if row["target_table"] != table:
                continue
            codes = sorted({pool[q]["normalized_code"] for q in row["candidate_ids"]})
            detail.append("| " + " | ".join(map(md, [row["canonical_name"], row["survey_wave"], ", ".join(row["source_variables"]),
                          ", ".join(map(str, row["existing_question_ids"])), ", ".join(codes), row["source_link_status_counts"]])) + " |")
        write_once(output / "crosswalks" / f"{table}.md", "\n".join(detail) + "\n")
    lines += ["", "## Inspected member questions", "",
              "[Four member-question families across seven source waves](member-question-review.md) have a local wording check.",
              "Sex and absence yes/no options were also checked. This does not approve new database mappings.", "",
              "[Number/column locator review queue](review-queue.md) lists the 16 ambiguous source links individually.", ""]
    reviewed = ["# Member question correspondence checks", "",
                "Twenty-eight source-specific checks cover sex, age, relationship to head and absence in seven available English questionnaires.",
                "2014 remains draft. No question wording is borrowed for 2007, 2017 or the image-only 2019 source.", "",
                "| Field | Wave | Source variable | Question wording | Locator | Interpretation |",
                "| --- | --- | --- | --- | --- | --- |"]
    for row in alignment["reviewed_member_correspondences"]:
        reviewed.append("| " + " | ".join(map(md, [row["canonical_name"], row["survey_wave"], row["source_variable"],
                         row["question_text"], row["source_sheet"] + "!" + row["text_cell"], row["interpretation"]])) + " |")
    write_once(output / "member-question-review.md", "\n".join(reviewed) + "\n")
    queue = ["# Number and column locator review queue", "",
             "These are extraction/numbering ambiguities, not established contradictions in the original survey.",
             "Repeated headings, identifier columns, merged cells and combined sections can produce competing candidates.",
             "Keep the existing database unchanged until each proposed source link has a source-layout review.", ""]
    for row in alignment["source_links"]:
        if row["status"] != "ambiguous_candidates_require_review":
            continue
        queue += [f"## {row['survey_wave']} {row['variable_name']} (source variable {row['source_variable_id']})", "",
                  f"Data source: `{row['archive_relative_path']}::{row['member_path']}`. Source label: {md(row['variable_label'])}.", "",
                  "| Candidate | Sheet | Code cell | Text cells | Extracted text candidate |", "| --- | --- | --- | --- | --- |"]
        for identity in row["candidate_ids"]:
            q = pool[identity]
            queue.append("| " + " | ".join(map(md, [identity, q["source_sheet"], q["question_code_cell"],
                                                    ", ".join(q["text_cell_candidates"]), q["question_text_candidate"]])) + " |")
        queue.append("")
    write_once(output / "review-queue.md", "\n".join(queue))
    lines += ["", "## Evidence boundaries", "",
              "- 2007 household evidence remains code lookups, not a recovered household questionnaire.",
              "- 2013 has the nested original questionnaire; previously published housing questions remain registered.",
              "- 2014 retains draft status. New candidates are not approved links.",
              "- 2017 has no located original questionnaire. Only the three already approved housing definitions inherit 2016 meanings.",
              "- 2019 image-bundle questions require page-based transcription; no OCR is treated as reviewed text.",
              "- 2021 language versions are separate. The published lighting conflict decision remains unchanged.",
              "- Raw cell contexts retain potential options, units and routing. Unparsed options are not reported as an empty option set.", "",
              "The JSON files retain full locators, source hashes, published question records, candidate links and cross-wave wording families.", ""]
    write_once(output / "README.md", "\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--cells", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    registry, inventory = json.loads(args.snapshot.read_text()), json.loads(args.inventory.read_text())
    if digest(args.snapshot.read_bytes()) != inventory["snapshot_sha256"]:
        raise ValueError("Registry snapshot does not match extracted evidence")
    if digest(args.cells.read_bytes()) != inventory["source_cells_sha256"]:
        raise ValueError("Literal cell extraction differs from its inventory binding")
    alignment = build(registry, inventory)
    alignment["reviewed_member_correspondences"] = review_member_correspondences(alignment, inventory)
    alignment["summary"]["locally_checked_member_correspondences"] = len(alignment["reviewed_member_correspondences"])
    alignment["registered_question_audit"] = audit_registered_questions(registry, json.loads(args.cells.read_text()))
    alignment["summary"]["registered_transcription_checks"] = dict(sorted(Counter(
        q["status"] for q in alignment["registered_question_audit"]).items()))
    alignment.update(snapshot_sha256=digest(args.snapshot.read_bytes()), inventory_sha256=digest(args.inventory.read_bytes()),
                     implementation_sha256=digest(Path(__file__).read_bytes()),
                     organizer_sha256=digest(Path(__file__).with_name("organize_cses_questionnaires.py").read_bytes()),
                     existing_member_builder_sha256=digest(Path(__file__).with_name("cses_hh_hl_common.py").read_bytes()))
    write_once(args.output / "alignment.json", alignment)
    reports(args.output, registry, inventory, alignment)
    print(json.dumps(alignment["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
