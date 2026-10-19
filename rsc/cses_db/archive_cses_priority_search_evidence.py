#!/usr/bin/env python3
"""Archive inspected priority-search references without marking questionnaire gaps closed.

The large Khmer report is retained once under raw; the library index links to it.
No PDF authoring, database access, Git commit or DVC operation is performed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pypdf import PdfReader
from retrieve_cses_questionnaire_materials import BASE, ROOT, encoded, put, sha

SEARCH = ROOT/'data/processing/cses/materials_priority_search_20261016'
SOURCES = [
    {
        'year': '2021', 'role': 'official_report_reference_not_missing_companion_form',
        'url': 'https://www.nis.gov.kh/nis/CSES/Final%20Report%20of%20Cambodia%20Socio-Economic%20Survey%202021_KH.pdf',
        'candidate': 'NIS_CSES2021_Final_Report_KHM.pdf',
        'filename': 'CSES2021_Final_Report_KHM.pdf',
        'sha256': '25c80cdf8007d600a272c06ad58bf0f9efedbc83d8fcee08a57096547a3c2acc',
        'bytes': 489257776, 'pages': 312,
        'finding': 'Contents and physical pages 200-312 visually screened. Appendix divider at 244; Form 3 household cover at 246; household pages 246-311; 247 is blank; 312 is publisher information. No village/listing/diary appendix or embedded file found.',
        'rendered_and_visually_screened_ranges': [[1, 18], [200, 312]],
        'retained_once_due_to_size': True,
    },
    {
        'year': '2017', 'role': 'third_party_reference_citing_2017_questionnaire_not_original_form',
        'url': 'https://www.simplepovertyscorecard.com/KHM-2017-ENG.pdf',
        'candidate': 'KHM-2017-ENG_scorecard.pdf',
        'filename': 'Scorocs_KHM2017_Poverty_Scorecard_ENG.pdf',
        'sha256': 'e7fc270fec7b698717dd31146ba294d127eea7ea288abba767eaa399f2139bca',
        'bytes': 871776, 'pages': 174,
        'finding': 'Physical page 47 (printed 37) explicitly cites NIS 2017 Household Questionnaire. Its annotation links to the 2012 manual, not a downloadable 2017 original; there are no embedded attachments. This is a source lead only, not a replacement questionnaire.',
        'visually_checked_citation_page': 47,
    },
]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    records = []
    for spec in SOURCES:
        raw = ROOT/'data/raw/questionnaire_supplements/20261016'/spec['year']/spec['filename']
        candidate = SEARCH/'candidates'/spec['candidate']
        source = raw if raw.exists() else candidate
        if source.stat().st_size != spec['bytes'] or digest(source) != spec['sha256']:
            raise ValueError('Reviewed source bytes changed: '+str(source))
        reader = PdfReader(source)
        if len(reader.pages) != spec['pages'] or list(reader.attachments.keys()):
            raise ValueError('Reviewed PDF structure changed')
        record = dict(spec, raw_path=str(raw.relative_to(ROOT)), embedded_files_found=0)
        if spec['year'] == '2017':
            text = reader.pages[46].extract_text() or ''
            if 'National Institute of Statistics (2017)' not in text or 'Household Questionnaire' not in text:
                raise ValueError('Missing cited 2017 source')
            local = BASE/'2017/references'/spec['filename']
            payload = source.read_bytes()
            put(raw, payload)
            put(local, payload)
            record['library_path'] = str(local.relative_to(ROOT))
        elif not raw.exists():
            raw.parent.mkdir(parents=True, exist_ok=True)
            candidate.rename(raw)  # Same filesystem: retain the large download once, unchanged.
        records.append(record)
    result = {
        'batch': 'priority_search_20261016_v1', 'date_local': '2026-10-16',
        'resources': records, 'new_missing_questionnaires_recovered': 0,
        'priority_gaps_still_open': {
            '2017': ['household', 'village', 'household_listing'],
            '2021': ['village', 'diary', 'household_listing'],
            '2023': ['village', 'household_listing'],
        },
        'script_sha256': sha(Path(__file__).read_bytes()), 'database_accessed': False,
        'original_archives_modified': False,
    }
    put(BASE/'manifest_priority_search_20261016_v1.json', encoded(result))
    print(json.dumps({'references_archived': len(records), 'new_missing_questionnaires_recovered': 0}))


if __name__ == '__main__':
    main()
