#!/usr/bin/env python3
"""Read the five cataloged housing questionnaires without modifying their archives.

Legacy XLS files are converted in an isolated temporary directory by LibreOffice.
Cell coordinates remain those of the original workbook; converted files are never
used as source identities. Native XLSX files are read directly with the stdlib.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import posixpath
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def read_xlsx_cells(payload: bytes, sheet_name: str) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(node.itertext()) for node in root.findall("s:si", NS)]
        relationships = {
            node.attrib["Id"]: node.attrib["Target"]
            for node in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        }
        book = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet = next(node for node in book.findall("s:sheets/s:sheet", NS) if node.attrib["name"] == sheet_name)
        target = relationships[sheet.attrib[REL]]
        member = target.lstrip("/") if target.startswith("/") else posixpath.normpath(f"xl/{target}")
        cells = {}
        for cell in ET.fromstring(archive.read(member)).findall(".//s:sheetData/s:row/s:c", NS):
            if cell.find("s:f", NS) is not None:
                # Formula cells are not accepted as questionnaire transcription evidence.
                continue
            value = cell.findtext("s:v", default="", namespaces=NS)
            if cell.get("t") == "s":
                value = strings[int(value)]
            elif cell.get("t") == "inlineStr":
                value = "".join(n.text or "" for n in cell.findall("s:is//s:t", NS))
            if value.strip():
                cells[cell.attrib["r"]] = value
        return cells


def extract(root: Path, soffice: str) -> dict:
    spec_bytes = (root / "rsc/specs/cses_questionnaire_provenance_v1.json").read_bytes()
    spec = json.loads(spec_bytes)
    instruments = []
    converter_version = subprocess.run(
        [soffice, "--version"], check=True, capture_output=True, text=True, timeout=55
    ).stdout.strip()
    for instrument in spec["instruments"]:
        if instrument["instrument_type"] != "household_questionnaire" or not instrument["question_catalog_included"]:
            continue
        with zipfile.ZipFile(root / instrument["archive_relative_path"]) as archive:
            payload = archive.read(instrument["member_path"])
        digest = hashlib.sha256(payload).hexdigest()
        if digest != instrument["source_sha256"]:
            raise ValueError(f"Questionnaire fingerprint changed: {instrument['survey_wave']}")
        legacy = Path(instrument["member_path"]).suffix.lower() == ".xls"
        if legacy:
            with tempfile.TemporaryDirectory(prefix="cses-response-cells-") as temporary:
                directory = Path(temporary)
                original = directory / "questionnaire.xls"
                original.write_bytes(payload)
                subprocess.run(
                    [soffice, f"-env:UserInstallation={(directory / 'profile').as_uri()}",
                     "--headless", "--convert-to", "xlsx", "--outdir", str(directory), str(original)],
                    check=True, capture_output=True, text=True, timeout=55,
                )
                cells = read_xlsx_cells((directory / "questionnaire.xlsx").read_bytes(),
                                        "03 Housing" if instrument["survey_wave"] == "2004" else "04 Housing")
        else:
            cells = read_xlsx_cells(payload, "04 Housing")
        instruments.append({
            "survey_wave": instrument["survey_wave"],
            "source_file": f"{instrument['archive_relative_path']}::{instrument['member_path']}",
            "source_sha256": digest,
            "documentation_status": instrument["documentation_status"],
            "source_sheet": "03 Housing" if instrument["survey_wave"] == "2004" else "04 Housing",
            "extraction_method": "LibreOffice XLS-to-XLSX cell extraction" if legacy else "native XLSX XML",
            "cells": cells,
        })
    return {
        "schema_version": 1,
        "questionnaire_spec_sha256": hashlib.sha256(spec_bytes).hexdigest(),
        "extractor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "legacy_converter_version": converter_version,
        "instruments": instruments,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--soffice", default=shutil.which("soffice"))
    args = parser.parse_args()
    if not args.soffice:
        parser.error("LibreOffice is required to read the three legacy XLS questionnaires")
    result = extract(args.root.resolve(), args.soffice)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(f"questionnaires={len(result['instruments'])} source_archives_modified=False")


if __name__ == "__main__":
    main()
