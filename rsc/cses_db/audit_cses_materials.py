#!/usr/bin/env python3
"""Inventory current loose and archived CSES documents, without database access.

Run with the bundled document Python. Reuse hash-matched cell extracts; convert
new legacy XLS in isolated macro-disabled temporary profiles. Never edit sources.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from organize_cses_questionnaires import workbook_cells

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/processing/cses/materials_audit_v1'
SOFFICE = '/Users/lichao/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice'
DOC_EXT = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.xlsm', '.rtf', '.txt'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def noise(name):
    return any(p.startswith('._') or p in {'__MACOSX', '.DS_Store'} for p in Path(name).parts)


def main():
    records, documents, archives, errors = [], {}, [], []
    cached_cells = {r['source_sha256']: r['sheets'] for r in json.loads(
        (ROOT/'data/processing/cses/questionnaire_alignment_v1/source_cells.json').read_text())}
    cached_originals = {}
    for p in (ROOT/'data/processed/cses_questionnaires').rglob('*'):
        if p.is_file() and p.suffix.lower() in DOC_EXT and any(t in p.parts for t in ('forms', 'references')):
            cached_originals.setdefault(sha(p.read_bytes()), []).append(str(p.relative_to(ROOT)))

    def record(name, payload):
        h = sha(payload)
        records.append({'source': name, 'bytes': len(payload), 'sha256': h,
                        'cached_originals': cached_originals.get(h, [])})
        documents.setdefault(h, (name, payload))

    def scan_zip(src, chain):
        with zipfile.ZipFile(src) as z:
            entries = [i for i in z.infolist() if not i.is_dir() and not noise(i.filename)]
            archives.append({'source': chain, 'entries': len(entries),
                             'extensions': dict(Counter(Path(i.filename).suffix.lower() for i in entries))})
            for i in entries:
                ext = Path(i.filename).suffix.lower()
                name = chain+'::'+i.filename
                if ext == '.zip':
                    scan_zip(io.BytesIO(z.read(i)), name)
                elif ext == '.rar':
                    scan_rar(z.read(i), name)
                elif ext in DOC_EXT:
                    record(name, z.read(i))

    def scan_rar(payload, chain):
        with tempfile.TemporaryDirectory(prefix='cses-materials-rar-') as td:
            p = Path(td)/'source.rar'
            p.write_bytes(payload)
            listing = subprocess.check_output(['/usr/bin/bsdtar', '-tf', str(p)])
            listing = re.sub(rb'\\([0-7]{3})', lambda m: bytes([int(m[1], 8)]), listing)
            names = listing.decode('utf-8').splitlines()
            archives.append({'source': chain, 'entries': len(names),
                             'extensions': dict(Counter(Path(n).suffix.lower() for n in names if not noise(n)))})
            for n in names:
                if not noise(n) and Path(n).suffix.lower() in DOC_EXT:
                    record(chain+'::'+n, subprocess.check_output(['/usr/bin/bsdtar', '-xOf', str(p), n]))

    for p in sorted((ROOT/'data/raw').rglob('*')):
        if not p.is_file() or noise(str(p)):
            continue
        ext, name = p.suffix.lower(), str(p.relative_to(ROOT))
        if ext == '.zip':
            scan_zip(p, name)
        elif ext == '.rar':
            scan_rar(p.read_bytes(), name)
        elif ext in DOC_EXT:
            record(name, p.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'inventory.json').write_text(json.dumps({'sources': records, 'archives': archives}, indent=2))
    print(f'Inventoried {len(records)} document occurrences, {len(documents)} distinct hashes.', flush=True)
    content = {}
    for h, (name, payload) in documents.items():
        ext = Path(name).suffix.lower()
        try:
            if ext == '.pdf':
                # Poppler provides a reproducible page split and also handles image-only pages.
                text = subprocess.check_output(['/opt/homebrew/bin/pdftotext', '-layout', '-', '-'], input=payload).decode()
                pages = text.split('\f')
                if not pages[-1].strip():
                    pages.pop()
                content[h] = {'source': name, 'pages': pages, 'method': 'poppler_literal_no_ocr'}
            elif ext in {'.xls', '.xlsx', '.xlsm'}:
                sheets = cached_cells.get(h)
                if sheets is None:
                    sheets = workbook_cells(payload, ext, SOFFICE)
                content[h] = {'source': name, 'sheets': sheets, 'method': 'hash_cached_cells' if h in cached_cells else 'workbook_cells_no_macros'}
            elif ext in {'.doc', '.rtf'}:
                with tempfile.TemporaryDirectory(prefix='cses-materials-word-') as td:
                    p = Path(td)/('source'+ext)
                    p.write_bytes(payload)
                    text = subprocess.check_output(['/usr/bin/textutil', '-convert', 'txt', '-encoding', 'UTF-8', '-stdout', str(p)], timeout=55).decode()
                content[h] = {'source': name, 'text': text, 'method': 'textutil_literal_not_layout'}
            elif ext == '.docx':
                with zipfile.ZipFile(io.BytesIO(payload)) as z:
                    tree = ET.fromstring(z.read('word/document.xml'))
                    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    text = '\n'.join(t.text or '' for t in tree.findall('.//w:t', ns))
                    media = [n for n in z.namelist() if n.startswith('word/media/')]
                    for n in media:
                        target = OUT/'docx_media'/h/Path(n).name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(z.read(n))
                content[h] = {'source': name, 'text': text, 'media': media, 'method': 'ooxml_and_embedded_images'}
            else:
                content[h] = {'source': name, 'text': payload.decode(errors='replace'), 'method': 'literal_text'}
            print('Inspected '+name, flush=True)
        except Exception as e:
            errors.append({'source': name, 'error': str(e)})
            print('ERROR '+name+' '+str(e), flush=True)
    (OUT/'content.json').write_text(json.dumps(content, ensure_ascii=False, indent=2))
    result = {'script_sha256': sha(Path(__file__).read_bytes()), 'document_occurrences': len(records),
              'distinct_document_hashes': len(documents), 'archive_inventories': len(archives),
              'unregistered_loose_documents': [r for r in records if '::' not in r['source'] and not r['cached_originals']],
              'errors': errors, 'database_accessed': False, 'sources_modified': False,
              'scope': 'Current data/raw loose files and recursive ZIP/RAR members; not an official completeness certification.'}
    (OUT/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
