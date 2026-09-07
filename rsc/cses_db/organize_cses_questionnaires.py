#!/usr/bin/env python3
"""Inventory distributed forms and extract locatable question candidates without publication.

Run snapshot with the project's PostgreSQL runtime. Run extract with the bundled
artifact Python runtime and its bundled LibreOffice. No source workbook is edited.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

from extract_cses_response_option_cells import NS, read_xlsx_cells

WAVES = ["2004", "2007", "2009", "2011-12", "2013", "2014", "2016", "2017", "2019", "2021"]
DOCUMENT_EXTENSIONS = {".xls", ".xlsx", ".xlsm", ".doc", ".docx", ".pdf", ".rtf"}
FORM_ROLES = {"household_questionnaire", "village_questionnaire", "household_diary", "household_listing"}


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n").encode()


def write_once(path, value):
    payload = value.encode() if isinstance(value, str) else encoded(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"Refusing to overwrite differing output: {path}")
    else:
        path.write_bytes(payload)


def compact_code(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


def is_question_code(value):
    return bool(re.fullmatch(r"q\d[a-z\d_.\s-]{0,14}", value.strip(), re.I))


def coordinate(cell):
    match = re.fullmatch(r"([A-Z]+)(\d+)", cell)
    col = 0
    for letter in match[1]:
        col = col * 26 + ord(letter) - 64
    return int(match[2]), col


def prompt_priority(value):
    text = " ".join(value.split())
    if re.match(r"^\d{1,2}\s*=|^\d{2}\.\s", text) or re.fullmatch(r"[A-H]\.\s.*", text):
        return -1
    if text.lower() in {"riels", "code", "codes", "years", "months", "percentage", "percent"}:
        return -1
    if "?" in text:
        return 100
    if re.match(r"^(what|which|how|does|did|has|have|can|is|are)\b", text, re.I):
        return 90
    if re.match(r"^(sex|age|relationship|marital status|id number)\b", text, re.I):
        return 80
    if re.match(r"^(please provide|only for|note:|the following|a\. list)\b", text, re.I):
        return 10
    return 50


def classify(name):
    low = name.lower()
    leaf = PurePosixPath(low).name
    if "village" in leaf or leaf.startswith("villageq"):
        return "village_questionnaire"
    if "diar" in leaf:
        return "household_diary"
    if "listing" in leaf:
        return "household_listing"
    if any(s in leaf for s in ("quest", "hses", "forms of cses")):
        return "household_questionnaire" if "forms of" not in leaf else "questionnaire_bundle"
    if "/code" in low or "codes" in low or " code" in leaf:
        return "code_reference"
    if "manual" in leaf:
        return "field_manual"
    return "supporting_document"


def wave_from_path(path):
    matches = [w for w in WAVES if w in path]
    if len(matches) != 1:
        raise ValueError(f"Ambiguous archive wave: {path}")
    return matches[0]


def walk_archive(path, chain=(), payload=None, depth=0):
    if depth > 4:
        raise ValueError("Archive nesting exceeds explicitly inspected limit")
    with zipfile.ZipFile(path if payload is None else io.BytesIO(payload)) as archive:
        for info in sorted(archive.infolist(), key=lambda x: x.filename):
            if info.is_dir() or any(p == "__MACOSX" or p.startswith("._") for p in PurePosixPath(info.filename).parts):
                continue
            extension = PurePosixPath(info.filename).suffix.lower()
            members = (*chain, info.filename)
            if extension == ".zip":
                yield from walk_archive(path, members, archive.read(info), depth + 1)
            elif extension in DOCUMENT_EXTENSIONS:
                yield members, archive.read(info)


def snapshot(output):
    from cses_baseline_metadata import connect_database

    queries = {
        "instruments": "SELECT i.instrument_id,s.survey_wave,i.instrument_type,i.source_file,i.source_sha256::text,"
        "i.document_title,i.language_code,i.documentation_status FROM cses_alignment.cses_instrument i "
        "JOIN cses_meta.cses_survey s USING(survey_id) ORDER BY i.instrument_id",
        "questions": "SELECT q.* FROM cses_alignment.cses_question q ORDER BY q.question_id",
        "source_variables": "SELECT sv.*,s.survey_wave,d.module_code,a.relative_path AS archive_relative_path,"
        "d.member_path,d.nested_member_path FROM cses_alignment.cses_source_variable sv "
        "JOIN cses_meta.cses_dataset d USING(dataset_id) JOIN cses_meta.cses_survey s ON s.survey_id=d.survey_id "
        "JOIN cses_meta.cses_source_archive a USING(source_archive_id) ORDER BY sv.source_variable_id",
        "canonical_variables": "SELECT * FROM cses_alignment.cses_canonical_variable ORDER BY canonical_variable_id",
        "mappings": "SELECT vm.variable_mapping_id,vm.dataset_id,vm.canonical_variable_id,vm.source_variable_names,"
        "vm.source_kind,vm.transformation_rule,vm.alignment_status,r.mapping_version "
        "FROM cses_alignment.cses_variable_mapping vm JOIN cses_meta.cses_alignment_release r "
        "USING(alignment_release_id) ORDER BY vm.variable_mapping_id",
        "housing_dictionary": "SELECT * FROM cses_analysis.cses_housing_value_dictionary_v4 "
        "ORDER BY survey_wave,canonical_name,source_value",
    }
    with connect_database({"dbname": "mda"}) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL statement_timeout='30s'")
        result = {key: connection.execute(query).fetchall() for key, query in queries.items()}
        if connection.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] != "on":
            raise ValueError("Read-only transaction required")
    expected = {"instruments": 20, "questions": 171, "source_variables": 4092,
                "canonical_variables": 280, "mappings": 1746, "housing_dictionary": 201}
    counts = {k: len(v) for k, v in result.items()}
    if counts != expected:
        raise ValueError(f"Current published baseline differs: {counts}")
    result.update(database_mutated=False, transaction_read_only=True, scope_counts=counts)
    write_once(output, result)
    print(json.dumps(counts), flush=True)


def workbook_cells(payload, extension, soffice):
    if extension == ".xls":
        with tempfile.TemporaryDirectory(prefix="cses-questionnaire-extract-") as temp:
            directory = Path(temp)
            original = directory / "source.xls"
            original.write_bytes(payload)
            # Isolated profile; disable all macros before opening any legacy source.
            profile = directory / "profile" / "user"
            profile.mkdir(parents=True)
            (profile / "registrymodifications.xcu").write_text(
                '<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
                '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
                '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
                '</item></oor:items>')
            subprocess.run([soffice, f"-env:UserInstallation={(directory / 'profile').as_uri()}",
                            "--headless", "--convert-to", "xlsx", "--outdir", str(directory), str(original)],
                           check=True, capture_output=True, text=True, timeout=55)
            converted = directory / "source.xlsx"
            if not converted.is_file():
                raise ValueError("Legacy spreadsheet conversion produced no workbook")
            payload = converted.read_bytes()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        book = ET.fromstring(archive.read("xl/workbook.xml"))
        names = [s.attrib["name"] for s in book.findall("s:sheets/s:sheet", NS)]
    return {name: read_xlsx_cells(payload, name) for name in names}


def question_candidates(source, sheets):
    result = []
    for sheet, cells in sheets.items():
        positioned = sorted(((coordinate(c), c, value) for c, value in cells.items()))
        prefix = re.match(r"^\s*(\d{2})(?:[\s_.-]+([A-H])(?:[\s_.-]|$))?", sheet, re.I)
        village = source["instrument_type"] == "village_questionnaire"
        if not prefix and not village:
            continue
        default_section, default_part = (prefix[1], (prefix[2] or "").lower()) if prefix else (None, "")
        codes = []
        for position, cell, value in positioned:
            raw = value.strip()
            if is_question_code(raw):
                method = "printed_q_number"
            elif re.fullmatch(r"\(\d{1,2}[a-z]?\)", raw, re.I):
                method = "printed_column_number"
            elif position[1] <= 4 and re.fullmatch(r"\d{1,2}[a-z]?[.)]?", raw, re.I):
                method = "numbered_row_prompt"
            else:
                continue
            codes.append((position, cell, value, method))
        for (row, col), cell, code, method in codes:
            section = default_section
            if village:
                headers = [(pos, re.match(r"^\s*(\d{1,2})\.\s+[A-Z]", value))
                           for pos, _, value in positioned if pos[0] < row and pos[1] <= 2]
                headers = [(pos, match) for pos, match in headers if match]
                if headers:
                    section = headers[-1][1][1]
            if section is None:
                continue
            right = [(pos, c, value) for pos, c, value in positioned
                     if pos[0] == row and pos[1] > col and len(value.strip()) > 5 and not is_question_code(value)]
            below = [(pos, c, value) for pos, c, value in positioned
                     if row < pos[0] <= row + 4 and col <= pos[1] <= col + 2
                     and len(value.strip()) > 8 and not is_question_code(value)]
            if method == "printed_column_number":
                previous = [pos[0] for pos, _, _, kind in codes
                            if pos[1] == col and pos[0] < row and kind == method]
                start = max(previous, default=max(0, row - 25))
                candidates = [(pos, c, value) for pos, c, value in positioned
                              if start < pos[0] < row and pos[1] == col and len(value.strip()) > 1
                              and not is_question_code(value) and prompt_priority(value) >= 0]
                candidates.sort(key=lambda item: (-prompt_priority(item[2]), item[0]))
                # Preserve every locator; the preferred prompt remains a heuristic candidate.
            else:
                candidates = right[:3] if right else below[:3]
            if method == "numbered_row_prompt":
                candidates = [(pos, c, value) for pos, c, value in candidates
                              if "?" in value or re.match(r"^(what|which|how|did|does|do |is |are |has |have |can |please )", value.strip(), re.I)]
            if not candidates:
                continue
            question_text = candidates[0][2] if candidates else None
            next_rows = [pos[0] for pos, _, _, _ in codes if pos[1] == col and pos[0] > row]
            end = min(next_rows) if next_rows else row + 8
            # Context is deliberately not parsed as the option set: grids can share rows/options.
            if method == "printed_column_number":
                context = {c: value for pos, c, value in positioned if start < pos[0] <= row and col <= pos[1] <= col + 2}
            else:
                context = {c: value for pos, c, value in positioned if row <= pos[0] < min(end, row + 12)}
            part = default_part
            if not default_part:
                markers = [(pos, value) for pos, _, value in positioned if pos[0] < row and pos[1] <= 2
                           and re.fullmatch(r"[A-H][.]?", value.strip())]
                if markers:
                    part = markers[-1][1].strip(". ").lower()
            local = re.fullmatch(r"[qQ(]?(\d{1,2})([a-z]?)[.)]?", code.strip(), re.I)
            normalized = (f"q{section}{part}{int(local[1]):02d}{local[2].lower()}"
                          if local else compact_code(code))
            if village and local:
                normalized = f"s{int(section)}q{int(local[1])}{local[2].lower()}"
            aliases = [normalized]
            if method == "printed_column_number" and not village:
                aliases.append(f"q{section}{part}c{int(local[1]):02d}{local[2].lower()}")
            identity = "::".join([source["source_file"], sheet, cell])
            result.append({"candidate_id": "q:" + digest(identity.encode())[:24],
                "source_file": source["source_file"], "survey_wave": source["survey_wave"],
                "instrument_type": source["instrument_type"], "language_code": source["language_code"],
                "documentation_status": source["documentation_status"], "source_sheet": sheet,
                "question_code_cell": cell, "printed_code": code, "normalized_code": normalized,
                "source_code_candidates": aliases,
                "code_derivation": method + "; sheet section and optional subsection prefix",
                "question_text_candidate": question_text,
                "text_cell_candidates": [c for _, c, _ in candidates], "context_cells": context,
                "context_completeness": "bounded; consult full source_cells.json for shared instructions and options",
                "response_options": None, "option_count": None,
                "extraction_status": "candidate_requires_layout_review", "is_exact_question_text": False})
    return result


def extract(root, snapshot_path, output, soffice):
    registry = json.loads(snapshot_path.read_text())
    known = {i["source_file"]: i for i in registry["instruments"]}
    sources, extracted, candidates, archives = [], [], [], {}
    converter_version = subprocess.check_output([soffice, "--version"], text=True, timeout=55).strip()
    for path in sorted((root / "data/raw").rglob("*.zip")):
        label = str(path.relative_to(root))
        wave = wave_from_path(label)
        archives[label] = digest(path.read_bytes())
        print(f"Scanning {wave}: {path.name}", flush=True)
        for chain, payload in walk_archive(path):
            source_file = "::".join([label, *chain])
            registered = known.get(source_file)
            sha = digest(payload)
            if registered and sha != registered["source_sha256"]:
                raise ValueError(f"Registered instrument fingerprint differs: {source_file}")
            extension = PurePosixPath(chain[-1]).suffix.lower()
            entry = {"survey_wave": wave, "source_file": source_file, "source_sha256": sha,
                     "archive_relative_path": label, "member_chain": list(chain), "extension": extension,
                     "instrument_type": registered["instrument_type"] if registered else classify(chain[-1]),
                     "language_code": registered["language_code"] if registered else "unknown",
                     "documentation_status": registered["documentation_status"] if registered else "unreviewed_variant",
                     "registered_instrument_id": registered["instrument_id"] if registered else None}
            sources.append(entry)
            if entry["instrument_type"] in FORM_ROLES and extension in {".xls", ".xlsx", ".xlsm"}:
                try:
                    sheets = workbook_cells(payload, extension, soffice)
                except (ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
                    entry.update(extraction_status="failed_requires_inspection", extraction_error=type(error).__name__)
                    continue
                extracted.append({"source_file": source_file, "source_sha256": sha, "sheets": sheets})
                entry.update(extraction_status="cells_extracted", sheet_names=list(sheets),
                             nonempty_literal_cells=sum(map(len, sheets.values())))
                questions = question_candidates(entry, sheets)
                entry["question_candidate_count"] = len(questions)
                candidates.extend(questions)
            elif extension == ".docx" and entry["instrument_type"] in {"questionnaire_bundle", "forms_bundle"}:
                # Structural inventory only. Do not OCR or reinterpret image-only questions.
                with zipfile.ZipFile(io.BytesIO(payload)) as document:
                    xml = ET.fromstring(document.read("word/document.xml"))
                    text = "".join(n.text or "" for n in xml.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
                    entry.update(extraction_status="image_bundle_requires_page_transcription",
                                 xml_text_character_count=len(text),
                                 embedded_media_count=sum(n.startswith("word/media/") for n in document.namelist()))
            else:
                entry["extraction_status"] = "inventory_only_not_question_transcription"
        if digest(path.read_bytes()) != archives[label]:
            raise ValueError("Source archive changed during extraction")
    # Include registered Stata code lookups as evidence, not as questionnaire text.
    recovered_path = root / "data/releases/cses-housing-recovered-evidence-v1/source_evidence.json"
    recovered = json.loads(recovered_path.read_text())
    for item in recovered["sources"]:
        if item["instrument_type"] == "code_lookup":
            registered = known[item["source_file"]]
            if registered["source_sha256"] != item["source_sha256"]:
                raise ValueError("Lookup registry/evidence mismatch")
            payload = root.joinpath(item["archive"]).read_bytes()
            for member in item["member_chain"]:
                with zipfile.ZipFile(io.BytesIO(payload)) as z:
                    payload = z.read(member)
            if digest(payload) != item["source_sha256"]:
                raise ValueError("Lookup original fingerprint mismatch")
            sources.append({**registered, "registered_instrument_id": registered["instrument_id"],
                            "extension": ".dta", "extraction_status": "code_lookup_not_questionnaire",
                            "options": item["options"]})
    missing = set(known) - {s["source_file"] for s in sources}
    if missing:
        raise ValueError(f"Registered instruments not inventoried: {sorted(missing)}")
    groups = defaultdict(list)
    for source in sources:
        groups[source["source_sha256"]].append(source["source_file"])
    for source in sources:
        source["identical_content_aliases"] = sorted(p for p in groups[source["source_sha256"]] if p != source["source_file"])
    result = {"inventory_id": "cses-questionnaire-organization-v1", "source_archives_modified": False,
              "macros_executed": False, "database_mutated": False,
              "archive_sha256": archives, "snapshot_sha256": digest(snapshot_path.read_bytes()),
              "implementation_sha256": digest(Path(__file__).read_bytes()),
              "cell_reader_sha256": digest(Path(__file__).with_name("extract_cses_response_option_cells.py").read_bytes()),
              "legacy_converter_version": converter_version,
              "sources": sources, "questions": candidates, "source_cells_sha256": digest(encoded(extracted)),
              "scope_counts": {"archives": len(archives), "document_sources": len(sources),
                               "extracted_workbooks": len(extracted), "question_candidates": len(candidates)},
              "limits": ["Candidate counts are printed code occurrences, not validated distinct questions.",
                         "No unsupported option counts or cross-wave equivalence are inferred.",
                         "All original sources and alternate versions are preserved."]}
    write_once(output / "source_inventory.json", result)
    write_once(output / "source_cells.json", extracted)
    print(json.dumps(result["scope_counts"]), flush=True)
    print(json.dumps(dict(Counter(s["extraction_status"] for s in sources))), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("snapshot", "extract"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--soffice")
    args = parser.parse_args()
    if args.mode == "snapshot":
        snapshot(args.output)
    else:
        if not args.snapshot or not args.soffice:
            parser.error("extract requires --snapshot and --soffice")
        extract(args.root.resolve(), args.snapshot, args.output, args.soffice)


if __name__ == "__main__":
    main()
