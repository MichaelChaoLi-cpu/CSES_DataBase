#!/usr/bin/env python3
"""Audit changed questionnaire copies without repairing or rewriting source files."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from align_cses_additional_school import ROOT, require
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put, verify_manifest
from inventory_cses_archives import DataSource
from organize_cses_questionnaires import workbook_cells


def differences(a,b):
    result = []
    for sheet in sorted(set(a)|set(b)):
        for cell in sorted(set(a.get(sheet,{}))|set(b.get(sheet,{}))):
            if a.get(sheet,{}).get(cell)!=b.get(sheet,{}).get(cell):
                result.append({'sheet':sheet,'cell':cell})
    return result


def main():
    folder = ROOT/'data/processed/cses_questionnaires/v1'
    manifest = json.loads((folder/'manifest.json').read_text())
    bad = []
    inputs = {}
    for name,sha in manifest['artifacts'].items():
        path = folder/name
        require(path.is_file(),'Missing questionnaire artifact: '+name)
        if file_sha(path)!=sha:
            bad.append(name)
    rows = []
    for name in bad:
        source = next(s for s in manifest['sources'] if s['local_path']==name)
        path = folder/name
        archive = ROOT/source['archive_relative_path']
        original = DataSource(archive,tuple(source['member_chain'])).read_bytes()
        original_sha = hashlib.sha256(original).hexdigest()
        require(original_sha==manifest['artifacts'][name],'Archive questionnaire member changed')
        require(path.suffix.lower()=='.xls','Unexpected mismatch type')
        # The existing extractor works on temporary copies, with macros disabled and an isolated profile.
        a = workbook_cells(original,'.xls','/opt/homebrew/bin/soffice')
        b = workbook_cells(path.read_bytes(),'.xls','/opt/homebrew/bin/soffice')
        cached = json.loads((folder/source['cells_path']).read_text())['sheets']
        delta,dictionary_delta = differences(a,b),differences(a,cached)
        require(not delta and not dictionary_delta,'Literal questionnaire cells changed; alignment must be reconsidered')
        row = {'cached_path':str(path.relative_to(ROOT)),'archive_member_chain':source['member_chain'],
            'expected_original_sha256':original_sha,'cached_file_sha256':file_sha(path),
            'archive_member_matches_manifest':True,'literal_cell_differences_from_archive':len(delta),
            'historical_literal_cache_differences_from_archive':len(dictionary_delta),
            'literal_cells_checked':sum(map(len,a.values()))}
        rows.append(row)
        print(path.name+': archive fingerprint verified; literal cells unchanged',flush=True)
        for p in [path,archive,folder/source['cells_path']]:
            inputs[str(p.relative_to(ROOT))] = file_sha(p)
    verify_manifest(ROOT/'data/processed/cses_health/v1')
    out = ROOT/'data/processing/cses/health_all_waves_pilot_v2'
    for p in [folder/'manifest.json',out/'report.json',out/'database-validation.json',Path(__file__),
        ROOT/'rsc/cses_db/organize_cses_questionnaires.py',ROOT/'rsc/cses_db/extract_cses_response_option_cells.py']:
        inputs[str(p.relative_to(ROOT))] = file_sha(p)
    result = {'database_modified':False,'cached_files_modified':False,'whole_questionnaire_cache_matches_manifest':not bad,
        'mismatching_copy_count':len(bad),'all_changed_copies_original_members_verified':True,
        'all_changed_copies_literal_cells_match_original_and_historical_extract':True,
        'health_native_cache_matches_manifest':True,'files':rows,'inputs':inputs,
        'scope':'Non-formula literal cell comparison, not format, macro or full-workbook binary equivalence. No cause or author of the byte changes is attributed.'}
    put(out/'form-copy-integrity.json',encoded(result))
    print(json.dumps({k:v for k,v in result.items() if k not in ['inputs','files']},indent=2))


if __name__=='__main__':
    main()
