#!/usr/bin/env python3
"""Preserve the official 2019/20 report and its village-questionnaire appendix."""
from __future__ import annotations

import io
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from retrieve_cses_questionnaire_materials import BASE, ROOT, encoded, put, sha

SOURCE_URL = 'https://www.nis.gov.kh/nis/CSES/Final%20Report%20of%20Cambodia%20Socio-Economic%20Survey%202019-20_EN.pdf'
INPUT = ROOT/'data/processing/cses/materials_search_20261016/candidates/NIS_CSES2019_20_Report_EN.pdf'


def main():
    source = INPUT.read_bytes()
    if len(source) != 30161769:
        raise ValueError('Source report size changed; review boundaries')
    reader = PdfReader(io.BytesIO(source))
    if len(reader.pages) != 285:
        raise ValueError('Unexpected report page count')
    if 'Appendix 1. Village questionnaire' not in (reader.pages[199].extract_text() or ''):
        raise ValueError('Missing village appendix divider')
    if 'Appendix 2.' not in (reader.pages[211].extract_text() or ''):
        raise ValueError('Missing next appendix divider')
    writer = PdfWriter()
    for page in reader.pages[201:211]:
        writer.add_page(page)
    writer.add_metadata({'/Title': 'Cambodia Socio-Economic Survey 2019/20 - Village Questionnaire (English)',
                         '/Author': 'National Institute of Statistics, Ministry of Planning, Cambodia',
                         '/Subject': 'Official report physical pages 202-211; nine image-based form pages and one blank verso retained.'})
    buffer = io.BytesIO()
    writer.write(buffer)
    payload = buffer.getvalue()
    check = PdfReader(io.BytesIO(payload))
    if len(check.pages) != 10:
        raise ValueError('Extracted page count changed')
    for old, new in zip(reader.pages[201:211], check.pages, strict=True):
        if old.extract_text() != new.extract_text() or tuple(old.mediabox) != tuple(new.mediabox):
            raise ValueError('Source/extract page mismatch')
    raw = ROOT/'data/raw/questionnaire_supplements/20261016/2019/CSES2019_20_Final_Report_ENG.pdf'
    report_copy = BASE/'2019/references/CSES2019_20_Final_Report_ENG.pdf'
    form = BASE/'2019/forms/CSES2019_20_Village_Questionnaire_ENG.pdf'
    put(raw, source)
    put(report_copy, source)
    put(form, payload)
    result = {'batch': 'village_2019_v2', 'retrieval_date_local': '2026-10-16',
              'source_url': SOURCE_URL, 'source_sha256': sha(source), 'source_bytes': len(source),
              'raw_path': str(raw.relative_to(ROOT)), 'source_copy_path': str(report_copy.relative_to(ROOT)),
              'source_pages': len(reader.pages), 'questionnaire_path': str(form.relative_to(ROOT)),
              'questionnaire_sha256': sha(payload), 'questionnaire_bytes': len(payload), 'questionnaire_pages': 10,
              'source_pdf_pages_inclusive': [202, 211],
              'substantive_form_source_pages': list(range(202, 211)),
              'blank_verso_source_pages': [211],
              'year_and_role_evidence': 'Image cover at report page 202 explicitly says CAMBODIA SOCIO-ECONOMIC SURVEY 2019/20, VILLAGE QUESTIONNAIRE, FORM 1.',
              'last_form_page_evidence': 'Report page 210 contains medicine retail prices, items 01-10.',
              'image_based_form': True, 'all_form_pages_visually_checked': True,
              'correction': 'V2 corrects the initial text-only blank-page inference: source pages 203/205/207/209 have scanned questions, not blank versos. All ten page images remain unchanged.',
              'text_and_geometry_match': True,
              'script_sha256': sha(Path(__file__).read_bytes()), 'database_accessed': False}
    put(BASE/'manifest_village_2019_v2.json', encoded(result))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
