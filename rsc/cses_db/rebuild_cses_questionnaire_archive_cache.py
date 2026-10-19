#!/usr/bin/env python3
"""Build an archive-exact cache beside v1; never overwrite historical copies or manifests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from align_cses_additional_school import ROOT, require
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, member_bytes, put, safe_path, verify_manifest

OLD = ROOT/'data/processed/cses_questionnaires/v1'
OUT = ROOT/'data/processed/cses_questionnaires/archive_verified_v2'


def build():
    original_manifest = json.loads((OLD/'manifest.json').read_text())
    source_by_path = {r['local_path']:r for r in original_manifest['sources']}
    before = {name:file_sha(safe_path(OLD,name)) for name in original_manifest['artifacts']}
    changes,inputs = [],{str((OLD/'manifest.json').relative_to(ROOT)):file_sha(OLD/'manifest.json')}
    for relative,expected in original_manifest['archive_sha256'].items():
        require(file_sha(ROOT/relative)==expected,'Source archive changed: '+relative)
        inputs[relative] = expected
    for name,expected in original_manifest['artifacts'].items():
        if name in source_by_path:
            src = source_by_path[name]
            payload = member_bytes(ROOT,src['source_file'])
        else:
            require(before[name]==expected,'Historical derivative changed: '+name)
            payload = safe_path(OLD,name).read_bytes()
        require(hashlib.sha256(payload).hexdigest()==expected,'Archive/derivative fingerprint differs: '+name)
        put(safe_path(OUT,name),payload)
        if before[name]!=expected:
            changes.append({'path':name,'historical_copy_sha256':before[name],'new_archive_exact_sha256':expected})
    manifest = {**original_manifest,'library_version':'cses-questionnaires-archive-verified-v2',
        'previous_manifest_sha256':file_sha(OLD/'manifest.json'),
        'construction':'All original document payloads re-read from immutable archive members; all derived literal cells copied only after historical hash verification.',
        'historical_copy_changes':changes,'original_v1_modified':False,'database_mutated':False}
    put(OUT/'manifest.json',encoded(manifest))
    verify_manifest(OUT)
    require(before=={name:file_sha(safe_path(OLD,name)) for name in original_manifest['artifacts']},'Historical cache changed during rebuild')
    inputs[str(Path(__file__).relative_to(ROOT))] = file_sha(Path(__file__))
    receipt = {'verified':True,'database_modified':False,'historical_v1_modified':False,
        'original_source_files':len(source_by_path),'verified_artifacts':len(original_manifest['artifacts']),
        'byte_different_historical_copies_preserved':len(changes),'inputs':inputs,
        'historical_manifest_sha256':file_sha(OLD/'manifest.json'),'new_manifest_sha256':file_sha(OUT/'manifest.json'),
        'original_copy_fingerprints':before,'archive_exact_copy_fingerprints':manifest['artifacts']}
    put(OUT/'verification.json',encoded(receipt))
    print(json.dumps({k:v for k,v in receipt.items() if k not in ['inputs','original_copy_fingerprints','archive_exact_copy_fingerprints']},indent=2))
    return receipt


if __name__=='__main__':
    build()
