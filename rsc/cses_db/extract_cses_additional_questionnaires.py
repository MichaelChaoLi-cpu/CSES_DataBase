#!/usr/bin/env python3
"""Searchable PDF pages and XLSM cells from the additional-wave cache only.

Run with the bundled document Python runtime. No macros, OCR, raw archive reads,
or automatic question-to-variable approval. Legacy Word originals stay available.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cache_cses_questionnaires import cells_markdown, file_sha, put, safe_path
from organize_cses_questionnaires import encoded, workbook_cells

BASE = "data/processed/cses_questionnaires/additional_waves_v1"


def extract(root):
    from pypdf import PdfReader

    base = root / BASE
    manifest_path = base / "manifest.json"
    original = json.loads(manifest_path.read_text())
    records, artifacts = [], {}
    for source in original["sources"]:
        path = safe_path(base, source["local_path"])
        if file_sha(path) != source["sha256"]:
            raise ValueError(f"Cached questionnaire changed: {path}")
        record = dict(source)
        stem = f"{source['wave']}/text/{path.stem}"
        if path.suffix.lower() == ".pdf":
            pages = [{"page": i + 1, "text": page.extract_text() or ""}
                     for i, page in enumerate(PdfReader(path).pages)]
            record.update(method="pypdf_text_no_ocr", pages=len(pages),
                          text_characters=sum(len(p["text"]) for p in pages))
            content = {"source_sha256": source["sha256"], "pages": pages}
            text = "\n\n".join(f"## Page {p['page']}\n\n{p['text']}" for p in pages)
            if source["wave"] == "2023" and "ENG" in path.name:
                record["limitation"] = "One-page cover only; no substantive question evidence."
            else:
                record["limitation"] = "Literal text extraction; layout and language not semantically verified."
        elif path.suffix.lower() in {".xlsx", ".xlsm"}:
            sheets = workbook_cells(path.read_bytes(), path.suffix.lower(), None)
            record.update(method="native_xml_cells_no_macros", sheets=len(sheets),
                          literal_cells=sum(len(cells) for cells in sheets.values()))
            record["limitation"] = "Literal cells only, not approved question links; images and formula results excluded."
            content = {"source_sha256": source["sha256"], "sheets": sheets}
            text = cells_markdown({"source_file": path.name, "survey_wave": source["wave"],
                                   "language_code": "en"}, sheets)
        else:
            record.update(method="original_only", limitation="Legacy Word text/layout extraction pending.")
            records.append(record)
            continue
        for ext, payload in ((".json", encoded(content)), (".md", text.encode())):
            relative = stem + ext
            artifacts[relative] = put(safe_path(base, relative), payload)
        record["text_path"] = stem + ".md"
        records.append(record)
    manifest = {"source_manifest_sha256": file_sha(manifest_path), "extractor_sha256": file_sha(Path(__file__)),
                "sources": records, "artifacts": artifacts, "question_links_approved": False}
    put(base / "text_manifest.json", encoded(manifest))
    return [{k: v for k, v in r.items() if k not in {"sha256", "source_member", "status"}} for r in records]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    print(json.dumps(extract(parser.parse_args().root), indent=2, ensure_ascii=False))
