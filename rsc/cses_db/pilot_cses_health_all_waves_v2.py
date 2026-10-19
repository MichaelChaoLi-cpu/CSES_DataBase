#!/usr/bin/env python3
"""Add reviewed 2012 evidence without changing the frozen first health pilot."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd
from align_cses_additional_school import ROOT, require
from build_cses_additional_waves import encoded, parquet_bytes
from cache_cses_questionnaires import file_sha, put
from pilot_cses_health_all_waves import OUT as FIRST
from pilot_cses_health_all_waves import OUTCOMES, coverage, qualify

OUT = ROOT/'data/processing/cses/health_all_waves_pilot_v2'
SPEC = ROOT/'rsc/specs/cses_health_all_waves_pilot_v2.json'


def promote_rules(rules,spec):
    result = [dict(r) for r in rules]
    r = next(r for r in result if r['survey_wave']=='2011-12')
    require(r['period_days']==30 and not r['strict_30d'],'Unexpected first-wave policy')
    r.update(strict_30d=True,form_status='2011_and_2012_matching_health_screen_forms_supported',
        supplemental_form_path=spec['form_path'],supplemental_form_locator='Physical and printed page39; section13B columns2/2a, No skip7; cover2012',
        supplemental_form_review=spec['review'])
    return result


def build():
    spec = json.loads(SPEC.read_text())
    require(not spec['database_publication_authorized'] and not spec['historical_outputs_mutable'],'Local-only scope required')
    prior = json.loads((FIRST/'report.json').read_text())
    for p,sha in prior['inputs'].items():
        require(file_sha(ROOT/p)==sha,'Frozen input changed: '+p)
    for name,sha in prior['artifacts'].items():
        require(file_sha(FIRST/name)==sha,'Frozen artifact changed: '+name)
    receipt = json.loads((FIRST/'database-validation.json').read_text())
    require(receipt['passed'] and receipt['report_sha256']==file_sha(FIRST/'report.json') and not receipt['database_modified'],'First-pilot independent acceptance required')
    pages = subprocess.check_output(['pdftotext','-layout',str(ROOT/spec['form_path']),'-']).decode().split('\f')
    require('SURVEY 2012' in pages[0] and all(s in pages[38] for s in ['LAST 30DAYS','2 = No (>> 7)','all members who usually reside']),'2012 source/page text changed')
    rules = promote_rules(json.loads((FIRST/'rules.json').read_text()),spec)
    before = pd.read_parquet(FIRST/'members.parquet')
    f = qualify(before,rules).astype(before.dtypes.to_dict())
    mutable = ['form_evidence_status','strict_30d_wave','strict_30d_status','illness_injury_30d_qualified']
    pd.testing.assert_frame_equal(before.drop(columns=mutable),f.drop(columns=mutable),check_exact=True)
    mask = f.survey_wave.eq('2011-12')
    pd.testing.assert_frame_equal(before.loc[~mask],f.loc[~mask],check_exact=True)
    require(int(f.loc[mask,'illness_injury_30d_qualified'].notna().sum())==16327,'Unexpected combined-wave denominator')
    require(int(f.illness_injury_30d_qualified.notna().sum())==308955,'Strict denominator differs')
    matrix = json.loads((FIRST/'matrix.json').read_text())
    updated = next(r for r in rules if r['survey_wave']=='2011-12')
    for row in matrix:
        if row['survey_wave']=='2011-12':
            row.update(updated,illness_injury_30d_qualified_records=16327)
    artifacts = {}
    payloads = {'members.parquet':parquet_bytes(f),'rules.json':encoded(rules),'matrix.json':encoded(matrix),'coverage.json':encoded(coverage(f))}
    for name in ['sources.parquet','orphan_health.parquet','exceptions.parquet']:
        payloads[name] = (FIRST/name).read_bytes()
    for name,data in payloads.items():
        put(OUT/name,data)
        artifacts[name] = file_sha(OUT/name)
    inputs = dict(prior['inputs'])
    for path in [FIRST/'report.json',FIRST/'database-validation.json',*[FIRST/name for name in prior['artifacts']],
        SPEC,ROOT/spec['form_path'],ROOT/spec['visual_path'],Path(__file__),ROOT/'rsc/cses_db/validate_cses_health_all_waves_v2.py']:
        inputs[str(path.relative_to(ROOT))] = file_sha(path)
    report = {**prior,'version':spec['version'],'inputs':inputs,'artifacts':artifacts,
        'supersedes_report_sha256':file_sha(FIRST/'report.json'),
        'change':'2011 and separately reviewed 2012 health forms support the combined-wave 30-day screen; only strict eligibility and its evidence/status change.',
        'qualified_records':{col:int(f[col].notna().sum()) for col in OUTCOMES},
        'strict_30d_yes':int(f.illness_injury_30d_qualified.eq(1).sum()),
        'strict_30d_waves':[r['survey_wave'] for r in rules if r['strict_30d']],
        'limitations':[s.replace('2011-12 and 2019 are excluded','2019 is excluded') for s in prior['limitations']]}
    put(OUT/'report.json',encoded(report))
    print(json.dumps({k:v for k,v in report.items() if k not in ['inputs','artifacts','source_checks']},indent=2))
    return report


if __name__=='__main__':
    build()
