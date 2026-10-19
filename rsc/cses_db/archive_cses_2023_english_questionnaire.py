#!/usr/bin/env python3
"""Archive the NIS 2023 English household appendix without replacing old evidence.

Download the official report to INPUT with curl first; run using bundled PDF Python.
The full source PDF is retained and the question appendix is copied page-for-page.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parents[2]
SOURCE_URL = 'https://www.nis.gov.kh/nis/CSES/Final%20Report%20of%20Cambodia%20Socio-Economic%20Survey%202023_EN.pdf'
RAW = ROOT/'data/raw/CSES2023/Questionnaire/NIS_CSES2023_Final_Report_ENG.pdf'
INPUT = RAW.with_suffix('.pdf.part')
BASE = ROOT/'data/processed/cses_questionnaires/additional_waves_v1/2023'
OUTPUT = BASE/'forms/CSES2023_Household_Questionnaire_ENG_full.pdf'
MANIFEST = BASE/'official_english_supplement_v1.json'


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def put(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f'Refusing to replace existing different file: {path}')
    else:
        with path.open('xb') as stream:
            stream.write(payload)


def encoded(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode()


def main():
    source = (INPUT if INPUT.exists() else RAW).read_bytes()
    if not source.startswith(b'%PDF-'):
        raise ValueError('Download is not a PDF')
    reader = PdfReader(io.BytesIO(source), strict=True)
    if len(reader.pages) != 271 or reader.is_encrypted:
        raise ValueError('Report shape changed: review the appendix boundaries')
    cover = reader.pages[204].extract_text() or ''
    if not all(s in cover for s in ['HOUSEHOLD QUESTIONNAIRE', 'SURVEY 2023']):
        raise ValueError('Expected 2023 English cover missing')
    if 'LIST OF HOUSEHOLD MEMBERS' not in (reader.pages[206].extract_text() or ''):
        raise ValueError('Expected first substantive questionnaire page missing')
    if 'Q8' not in (reader.pages[269].extract_text() or ''):
        raise ValueError('Expected final victimization continuation missing')
    writer = PdfWriter()
    for page in reader.pages[204:270]:
        writer.add_page(page)
    writer.add_metadata({'/Title': 'Cambodia Socio-Economic Survey 2023 - Household Questionnaire (English)',
                         '/Author': 'National Institute of Statistics, Ministry of Planning, Cambodia',
                         '/Subject': 'Verbatim appendix from the official report, physical PDF pages 205-270.'})
    buffer = io.BytesIO()
    writer.write(buffer)
    output = buffer.getvalue()
    extracted = PdfReader(io.BytesIO(output), strict=True)
    if len(extracted.pages) != 66:
        raise ValueError('Wrong extracted page count')
    pages = []
    for i, (old, new) in enumerate(zip(reader.pages[204:270], extracted.pages, strict=True), 1):
        old_text, new_text = old.extract_text() or '', new.extract_text() or ''
        if old_text != new_text or tuple(old.mediabox) != tuple(new.mediabox) or old.rotation != new.rotation:
            raise ValueError(f'Page content/geometry changed: {i}')
        pages.append({'questionnaire_page': i, 'report_pdf_page': i+204,
                      'text_sha256': sha(new_text.encode()), 'characters': len(new_text),
                      'heading_preview': re.sub(r'\s+', ' ', new_text).strip()[:160]})
    # A blank verso after the cover is present in the official source and retained.
    if [p['questionnaire_page'] for p in pages if not p['characters']] != [2]:
        raise ValueError('Unexpected blank-page pattern')
    put(RAW, source)
    put(OUTPUT, output)
    manifest = {'supplement': 'official_english_supplement_v1', 'retrieval_date_local': '2026-10-16',
                'source_url': SOURCE_URL, 'publisher': 'National Institute of Statistics, Cambodia',
                'source_path': str(RAW.relative_to(ROOT)), 'source_sha256': sha(source),
                'source_bytes': len(source), 'source_pages': len(reader.pages),
                'questionnaire_path': str(OUTPUT.relative_to(ROOT)), 'questionnaire_sha256': sha(output),
                'questionnaire_bytes': len(output), 'questionnaire_pages': 66,
                'report_pdf_pages_inclusive': [205, 270], 'retained_blank_questionnaire_pages': [2],
                'excluded_report_pages': '1-204 (report and appendix dividers), 271 (publisher information)',
                'page_text_and_geometry_match': True, 'pages': pages,
                'script_sha256': sha(Path(__file__).read_bytes()),
                'prior_one_page_english_cover_preserved': True,
                'scope': 'Official English household form only; not the village or household listing form.',
                'database_accessed': False}
    put(MANIFEST, encoded(manifest))
    put(BASE/'text/CSES2023_Household_Questionnaire_ENG_full.json', encoded({
        'source_questionnaire_sha256': sha(output),
        'pages': [{'page': i+1, 'report_pdf_page': i+205, 'text': p.extract_text() or ''}
                  for i, p in enumerate(extracted.pages)]}))
    if INPUT.exists() and INPUT.read_bytes() == source:
        INPUT.unlink()  # Completed temporary download; byte-identical original retained at RAW.
    print(json.dumps({k: v for k, v in manifest.items() if k != 'pages'}, indent=2))


if __name__ == '__main__':
    main()
