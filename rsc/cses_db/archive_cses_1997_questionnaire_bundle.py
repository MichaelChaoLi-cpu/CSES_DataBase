#!/usr/bin/env python3
"""Archive the NIS-authored IHSN 1997 bundle and its 12-page village form."""
from __future__ import annotations

import io
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from retrieve_cses_questionnaire_materials import BASE, ROOT, encoded, put, sha

URL = 'https://catalog.ihsn.org/catalog/27/download/28301'
INPUT = ROOT/'data/processing/cses/materials_search_20261016/candidates/CSES1997_Questionnaires_IHSN.pdf'


def main():
    source = INPUT.read_bytes()
    if len(source) != 7441596:
        raise ValueError('Bundle changed; inspect boundaries again')
    reader = PdfReader(io.BytesIO(source))
    if len(reader.pages) != 46:
        raise ValueError('Unexpected bundle length')
    writer = PdfWriter()
    for p in reader.pages[4:16]:
        writer.add_page(p)
    writer.add_metadata({'/Title': 'Cambodia Socio-Economic Survey 1997 - Village Questionnaire - 12-page scan',
                         '/Author': 'National Institute of Statistics, Cambodia',
                         '/Subject': 'IHSN NIS-authored questionnaire bundle physical pages 5-16; original printed pages 1-12.'})
    output = io.BytesIO()
    writer.write(output)
    payload = output.getvalue()
    raw = ROOT/'data/raw/questionnaire_supplements/20261016/1997/CSES1997_Questionnaire_Bundle_IHSN_ENG.pdf'
    bundle = BASE/'1997/forms/CSES1997_Questionnaire_Bundle_IHSN_ENG.pdf'
    village = BASE/'1997/forms/CSES1997_Village_Questionnaire_ENG_12page_scan.pdf'
    put(raw, source)
    put(bundle, source)
    put(village, payload)
    record = {'batch': 'bundle_1997_v1', 'retrieval_date_local': '2026-10-16',
              'source_url': URL, 'catalog_url': 'https://catalog.ihsn.org/catalog/27/related-materials',
              'source_author': 'National Institute of Statistics, Cambodia',
              'source_sha256': sha(source), 'source_bytes': len(source), 'source_pages': 46,
              'raw_path': str(raw.relative_to(ROOT)), 'bundle_path': str(bundle.relative_to(ROOT)),
              'questionnaire_path': str(village.relative_to(ROOT)),
              'questionnaire_sha256': sha(payload), 'questionnaire_pages': 12,
              'bundle_pdf_pages_inclusive': [5, 16], 'printed_village_pages': '1-12',
              'verification': 'Visual cover dated 1997; final printed page 12 contains Q86 wages, Q87-Q88 natural disasters and Q89 years affected.',
              'older_11page_variant': 'Retained separately. It also reaches Q89; pagination differs, so 11 pages alone is not proof of omitted questions. Use the 12-page scan when original printed pagination is needed.',
              'image_based': True, 'database_accessed': False,
              'script_sha256': sha(Path(__file__).read_bytes())}
    put(BASE/'manifest_bundle_1997_v1.json', encoded(record))
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
