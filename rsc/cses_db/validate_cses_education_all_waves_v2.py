#!/usr/bin/env python3
"""Independent scalar verification of the corrected local-only education prototype."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from align_cses_additional_school import KEYS, ROOT, require
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put
from pilot_cses_education_all_waves import TARGETS
from pilot_cses_education_all_waves_v2 import OUT
from validate_cses_education_all_waves import database_acceptance, equal, number
from validate_cses_education_all_waves import decide as first_decide


def decide(r,h,c):
    out = first_decide(r,h,c)
    years = number(r.years_native)
    conflict = number(r.ever_native)==2 and years is not None and years>0
    out['never_attended_positive_years_warning'] = conflict
    out['never_attended_route_conflict'] = out['never_attended_route_conflict'] or conflict
    if conflict and r.form_scope_reviewed and out['age_eligible'] and r.education_linked:
        for t in ['attendance','highest']:
            if out[t+'_qualified'] is not None:
                out[t+'_qualified'] = None
                out[t+'_status'] = 'never_attended_positive_years_conflict'
                if t=='highest':
                    out['highest_general_grade'] = None
    return out


def main(database=False):
    report = json.loads((OUT/'report.json').read_text())
    require(report['prototype_not_published'] and not report['database_modified'],'Local-only prototype required')
    for p,sha in report['inputs'].items():
        require(file_sha(ROOT/p)==sha,'Pinned input changed: '+p)
    for p,sha in report['artifacts'].items():
        require(file_sha(OUT/p)==sha,'Prototype artifact changed: '+p)
    f = pd.read_parquet(OUT/'members.parquet')
    book = json.loads((OUT/'level_codebook.json').read_text())
    lookup = {(r['survey_wave'],r['target'],r['source_code']):r for r in book}
    matrix = json.loads((OUT/'matrix.json').read_text())
    require(len(f)==571699 and not f.duplicated(KEYS).any() and f[KEYS].notna().all().all(),'Roster grain differs')
    require(len(matrix)==120 and len({(r['survey_wave'],r['target']) for r in matrix})==120,'Matrix grain differs')
    for row in matrix:
        g = f.loc[f.survey_wave.eq(row['survey_wave'])]
        require(row['qualified_records']==int(g[row['target']+'_qualified'].notna().sum()),'Matrix count differs')
    counters = defaultdict(Counter)
    for r in f.itertuples(index=False):
        expected = decide(r,lookup.get((r.survey_wave,'highest',number(r.highest_native))),
                          lookup.get((r.survey_wave,'current',number(r.current_native))))
        require(all(equal(getattr(r,k),v) for k,v in expected.items()),'Independent scalar mismatch: '+r.survey_wave)
        age = number(r.age_for_analysis)
        for band,inband in [('questionnaire_universe',expected['age_eligible']),
            ('ages_6_17',age is not None and 6<=age<=17),('ages_15_plus',age is not None and age>=15)]:
            if not inband:
                continue
            for t in TARGETS:
                c = counters[r.survey_wave,band,t]
                q = expected[t+'_qualified']
                gate = expected[t+'_expected_by_route']
                c['age_band_members'] += 1
                c['expected_by_route'] += gate
                c['raw_non_null'] += number(getattr(r,t+'_native')) is not None
                c['qualified_records'] += q is not None
                c['unresolved_expected'] += gate and q is None
                if t not in ['highest','current','years']:
                    c['qualified_yes'] += q==1
                    c['qualified_no'] += q==0
    require(len(report['coverage'])==360,'Coverage row count differs')
    for row in report['coverage']:
        c = counters[row['survey_wave'],row['age_band'],row['target']]
        require(all(row[k]==v for k,v in c.items()),'Independent denominator mismatch')
        if not row['form_scope_reviewed'] and row['age_band']=='questionnaire_universe':
            require(row['age_band_members'] is None,'Unverified universe cannot become zero people')
    result = {'passed':True,'prototype_not_published':True,'database_modified':False,'database_accessed':database,
        'roster_records':len(f),'classified_field_records':len(f)*8,'scalar_mismatches':0,
        'matrix_rows':120,'denominator_rows':360,'orphan_records_preserved':len(pd.read_parquet(OUT/'orphan_education.parquet')),
        'report_sha256':file_sha(OUT/'report.json'),'validator_sha256':file_sha(Path(__file__))}
    if database:
        result['database'] = database_acceptance(f)
    put(OUT/('database-validation.json' if database else 'local-validation.json'),encoded(result))
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',action='store_true')
    main(p.parse_args().database)
