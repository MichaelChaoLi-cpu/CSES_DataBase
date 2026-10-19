#!/usr/bin/env python3
"""Read-only, bounded availability probes for known NIS questionnaire downloads.

PDF bodies are inspected in memory. Only aggregate retrieval evidence is saved.
"""
from __future__ import annotations

import hashlib
import io
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
RESOURCES = [
    ('1997', 'household_listing', '11/download/75'),
    ('1997', 'village_questionnaire', '11/download/76'),
    ('1999', 'household_listing', '12/download/79'),
    ('1999', 'village_questionnaire', '12/download/80'),
    ('2011', 'village_questionnaire', '17/download/117'),
    ('2011', 'diary_version_candidate', '17/download/118'),
]


def probe(item):
    wave, role, endpoint = item
    url = 'https://microdata.nis.gov.kh/index.php/catalog/'+endpoint
    result = {'wave': wave, 'role': role, 'url': url}
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'CSES-materials-audit/1.0'})
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = response.read(2_000_001)
            result.update(status=response.status, final_url=response.url,
                          content_type=response.headers.get('Content-Type'), bytes_read=len(payload))
        if len(payload) > 2_000_000 or not payload.startswith(b'%PDF-'):
            raise ValueError('Response is not a bounded PDF body')
        reader = PdfReader(io.BytesIO(payload))
        result.update(pdf_valid=True, pages=len(reader.pages), sha256=hashlib.sha256(payload).hexdigest(),
                      first_page_text=(reader.pages[0].extract_text() or '')[:2500],
                      archived_locally=False)
    except Exception as error:
        result.update(pdf_valid=False, error=str(error))
    return result


def main():
    with ThreadPoolExecutor(max_workers=3) as pool:
        resources = list(pool.map(probe, RESOURCES))
    result = {'checked_date_local': '2026-10-16', 'resources': resources,
              'interpretation': 'A catalog link alone is not a retrieved or year-certified form; inspect each probe outcome.',
              'database_accessed': False}
    out = ROOT/'data/processing/cses/materials_retrieval_20261016/official_download_probes.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
