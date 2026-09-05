#!/usr/bin/env python3
"""Recover immutable 2007 lookup and nested 2013 questionnaire evidence."""

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
from pathlib import Path

import pandas as pd
from correct_cses_housing_lighting import write_json
from cses_baseline_metadata import sha256_file
from extract_cses_response_option_cells import NS, read_xlsx_cells
from inventory_cses_archives import DataSource
from record_cses_value_mapping_decisions import require

RELEASE = "cses-housing-recovered-evidence-v1"
DIRECTORY = f"data/releases/{RELEASE}"
SPEC = "rsc/specs/cses_housing_recovered_evidence_v1.json"
SELF = "rsc/cses_db/extract_cses_housing_recovered_evidence.py"
EVIDENCE = f"{DIRECTORY}/source_evidence.json"


def normalize(text):
    # Preserve original bytes/text separately. Only normalize whitespace/apostrophes for comparison.
    return " ".join(text.replace("\u0092", "'").replace("’", "'").split())


def parse_options(cells, coordinates):
    options = []
    for cell in coordinates:
        for line in cells[cell].splitlines():
            if not line.strip():
                continue
            match = re.fullmatch(r"\s*(\d+)\s*=\s*(.+?)\s*", line)
            require(match is not None, f"Unparsed option in {cell}: {line!r}")
            text = match[2]
            skip = re.findall(r"\(>>\s*[^)]+\)", text)
            label = re.sub(r"\(>>\s*[^)]+\)", "", text)
            label = re.sub(r"\(specify\)", "", label, flags=re.IGNORECASE)
            options.append({"code": match[1], "label": normalize(label), "raw_text": line,
                            "source_cell": cell, "skip_instructions": skip})
    require(len({r["code"] for r in options}) == len(options), "Duplicate option code")
    return options


def check_options(options, expected):
    require({r["code"]: r["label"] for r in options} == expected, "Recovered option meanings differ")


def source_payload(root, item):
    require(sha256_file(root / item["archive"]) == item["archive_sha256"], "Archive fingerprint changed")
    payload = DataSource(root / item["archive"], tuple(item["member_chain"])).read_bytes()
    require(hashlib.sha256(payload).hexdigest() == item["source_sha256"], "Evidence member fingerprint changed")
    return payload


def extract(root, soffice):
    spec = json.loads((root / SPEC).read_text())
    sources = []
    converter = subprocess.check_output([soffice, "--version"], text=True, timeout=55).strip()
    for item in spec["instruments"]:
        payload = source_payload(root, item)
        entry = dict(item)
        entry["source_file"] = "::".join([item["archive"], *item["member_chain"]])
        if item["instrument_type"] == "code_lookup":
            frame = pd.read_stata(io.BytesIO(payload), convert_categoricals=False)
            require(set(frame.columns) == {item["code_column"], "descr_eng", "descr_khmer"}, "Lookup columns changed")
            options = [{"code": str(int(row[item["code_column"]])), "label": normalize(row["descr_eng"]),
                        "raw_text": row["descr_eng"], "source_row": i + 1,
                        "source_column": "descr_eng", "skip_instructions": []}
                       for i, row in frame.iterrows()]
            require(len({r["code"] for r in options}) == len(options), "Duplicate lookup code")
            check_options(options, spec["definitions"]["2007"][item["field"]]["expected_labels"])
            entry.update(options=options, extraction_method="Stata lookup rows, not embedded housing value labels")
        else:
            with tempfile.TemporaryDirectory(prefix="cses-2013-recovery-") as temporary:
                directory = Path(temporary)
                original = directory / "questionnaire.xls"
                original.write_bytes(payload)
                subprocess.run([soffice, f"-env:UserInstallation={(directory / 'profile').as_uri()}",
                    "--headless", "--convert-to", "xlsx", "--outdir", str(directory), str(original)],
                    check=True, capture_output=True, text=True, timeout=55)
                converted = (directory / "questionnaire.xlsx").read_bytes()
                with zipfile.ZipFile(io.BytesIO(converted)) as book:
                    names = [s.attrib["name"] for s in ET.fromstring(book.read("xl/workbook.xml"))
                             .findall("s:sheets/s:sheet", NS)]
                require(len(names) == 24 and "04 Housing" in names, "Questionnaire sheet inventory changed")
                cells = read_xlsx_cells(converted, "04 Housing")
            questions = []
            for field, definition in spec["definitions"]["2013"].items():
                loc = definition["cells"]
                require(normalize(cells[loc["code"]]) == definition["printed_code"], "Question code changed")
                if "part" in loc:
                    require(normalize(cells[loc["part"]]) == "(a)", "Question part changed")
                require(normalize(cells[loc["text"]]) == definition["question_text"], "Question text changed")
                options = parse_options(cells, loc["options"])
                check_options(options, definition["expected_labels"])
                coordinates = [loc["code"], loc["text"], *loc["options"]] + ([loc["part"]] if "part" in loc else [])
                questions.append({"field": field, "question_code": definition["question_code"],
                    "question_text": definition["question_text"], "options": options,
                    "source_cells": {c: cells[c] for c in coordinates}, "locators": loc})
            entry.update(sheet_names=names, source_sheet="04 Housing", questions=questions,
                         extraction_method="LibreOffice XLS-to-XLSX, then original-cell XML transcription")
        sources.append(entry)
    return {"release_id": RELEASE, "spec_sha256": sha256_file(root / SPEC),
            "extractor_sha256": sha256_file(root / SELF), "converter_version": converter,
            "sources": sources, "source_archives_modified": False,
            "scope": "Full 2013 workbook registered; only three housing questions cataloged; 2007 lookup evidence, no household questionnaire claim"}


def checked_evidence(root):
    evidence = json.loads((root / EVIDENCE).read_text())
    require(evidence["release_id"] == RELEASE and evidence["spec_sha256"] == sha256_file(root / SPEC)
            and evidence["extractor_sha256"] == sha256_file(root / SELF), "Evidence binding changed")
    for item in evidence["sources"]:
        source_payload(root, item)
    return evidence


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--soffice", default="/Applications/LibreOffice.app/Contents/MacOS/soffice")
    args = p.parse_args()
    result = extract(args.root.resolve(), args.soffice)
    write_json(args.root.resolve() / EVIDENCE, result)
    print(f"sources={len(result['sources'])} housing_questions=3 source_archives_modified=False")


if __name__ == "__main__":
    main()
