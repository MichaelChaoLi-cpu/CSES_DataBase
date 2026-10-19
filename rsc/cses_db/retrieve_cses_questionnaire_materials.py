#!/usr/bin/env python3
"""Retrieve a reviewed JSON plan of official materials as immutable supplements.

Run with the bundled PDF Python. Original PDFs are retained byte-for-byte under
data/raw and copied to the questionnaire library. No database access is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'data/processed/cses_questionnaires/official_retrieval_v1'


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def put(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as stream:
            stream.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ValueError(f'Refusing different overwrite: {path}')


def encoded(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode()


def retrieve(item):
    raw = ROOT/'data/raw/questionnaire_supplements/20261016'/item['year']/item['filename']
    if raw.exists():
        payload = raw.read_bytes()
    else:
        request = urllib.request.Request(item['url'], headers={'User-Agent': 'CSES-materials-archive/1.0'})
        with urllib.request.urlopen(request, timeout=35) as response:
            payload = response.read(25_000_001)
    if len(payload) > 25_000_000 or not payload.startswith(b'%PDF-'):
        raise ValueError('Not a bounded PDF body: '+item['url'])
    digest = sha(payload)
    if item.get('sha256') and digest != item['sha256']:
        raise ValueError('Previously verified download changed: '+item['url'])
    reader = PdfReader(io.BytesIO(payload))
    if reader.is_encrypted or (item.get('pages') and len(reader.pages) != item['pages']):
        raise ValueError('PDF shape mismatch: '+item['filename'])
    pages = [{'page': i+1, 'text': p.extract_text() or ''} for i, p in enumerate(reader.pages)]
    cover = re.sub(r'\s+', ' ', pages[0]['text']).casefold()
    for required in item.get('cover_required', []):
        if required.casefold() not in cover:
            raise ValueError('Missing cover evidence '+required+': '+item['filename'])
    category = 'references' if item.get('kind') == 'reference' else 'forms'
    local = BASE/item['year']/category/item['filename']
    text_path = BASE/item['year']/'text'/(Path(item['filename']).stem+'.json')
    put(raw, payload)
    put(local, payload)
    put(text_path, encoded({'source_sha256': digest, 'source_url': item['url'], 'pages': pages,
                            'method': 'pypdf_literal_no_ocr'}))
    result = dict(item, sha256=digest, bytes=len(payload), pages=len(reader.pages),
                  raw_path=str(raw.relative_to(ROOT)), local_path=str(local.relative_to(ROOT)),
                  text_path=str(text_path.relative_to(ROOT)), original_and_library_bytes_match=True,
                  source_inspected_date_local='2026-10-16')
    print(f"Archived {item['year']} {item['role']}: {len(reader.pages)} pages", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    args = parser.parse_args()
    plan_bytes = args.plan.read_bytes()
    plan = json.loads(plan_bytes)
    for item in plan['resources']:
        if not re.fullmatch(r'[0-9]{4}(?:-[0-9]{2})?', item['year']):
            raise ValueError('Unsafe year')
        if Path(item['filename']).name != item['filename'] or not item['filename'].endswith('.pdf'):
            raise ValueError('Unsafe file name')
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(retrieve, plan['resources']))
    result = {'batch': plan['batch'], 'retrieved_date_local': '2026-10-16', 'resources': records,
              'plan_sha256': sha(plan_bytes), 'script_sha256': sha(Path(__file__).read_bytes()),
              'database_accessed': False, 'original_archives_modified': False,
              'semantics': 'Materials availability only; no question-to-variable mapping certification.'}
    put(BASE/('manifest_'+plan['batch']+'.json'), encoded(result))
    print(json.dumps({'batch': plan['batch'], 'archived': len(records)}, indent=2))


if __name__ == '__main__':
    main()
