#!/usr/bin/env python3
"""Independently accept the 2012-evidence revision; database transactions stay read-only."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd
from align_cses_additional_school import KEYS, ROOT, require
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put
from pilot_cses_health_all_waves import OUTCOMES
from pilot_cses_health_all_waves_v2 import OUT
from validate_cses_education_all_waves import equal, number
from validate_cses_health_all_waves import database_acceptance, decide, native_acceptance


def main(database=False):
    report = json.loads((OUT/'report.json').read_text())
    require(report['prototype_not_published'] and not report['database_modified'],'Local-only scope required')
    for path,sha in report['inputs'].items():
        require(file_sha(ROOT/path)==sha,'Input changed: '+path)
    for path,sha in report['artifacts'].items():
        require(file_sha(OUT/path)==sha,'Artifact changed: '+path)
    f,source,orphan = [pd.read_parquet(OUT/name) for name in ['members.parquet','sources.parquet','orphan_health.parquet']]
    rules = json.loads((OUT/'rules.json').read_text())
    lookup = {r['survey_wave']:r for r in rules}
    require(len(f)==571699 and not f.duplicated(KEYS).any() and len(source)==571638 and len(orphan)==5,'Unexpected grain')
    native = native_acceptance(source,rules)
    counters = {}
    for row in f.itertuples(index=False):
        expected = decide(row,lookup[row.survey_wave])
        require(all(equal(getattr(row,k),v) for k,v in expected.items()),'Scalar mismatch: '+row.survey_wave)
        age = number(row.age_for_analysis)
        for band,inside in [('all_members',True),('ages_6_17',age is not None and 6<=age<=17),('ages_15_plus',age is not None and age>=15)]:
            if not inside:
                continue
            c = counters.setdefault((row.survey_wave,band),Counter())
            c['members_in_band'] += 1
            c['health_linked'] += row.health_linked
            c['raw_screen_non_null'] += number(row.screen_native) is not None
            c['screen_applicable'] += expected['screen_applicable']
            c['unresolved_expected'] += expected['screen_applicable'] and expected['screen_qualified'] is None
            for target in OUTCOMES:
                q = expected[target]
                c[target+'_records'] += q is not None
                c[target+'_yes'] += q==1
                c[target+'_no'] += q==0
    cov = json.loads((OUT/'coverage.json').read_text())
    require(len(cov)==45 and all(all(r[k]==v for k,v in counters[r['survey_wave'],r['age_band']].items()) for r in cov),'Independent coverage differs')
    matrix = json.loads((OUT/'matrix.json').read_text())
    require(len(matrix)==15 and all(r[t+'_records']==int(f.loc[f.survey_wave.eq(r['survey_wave']),t].notna().sum()) for r in matrix for t in OUTCOMES),'Matrix differs')
    require(int(f.illness_injury_30d_qualified.notna().sum())==308955 and int(f.illness_injury_30d_qualified.eq(1).sum())==56262,'Revised strict count differs')
    result = {'passed':True,'prototype_not_published':True,'database_modified':False,'database_accessed':database,
        'report_sha256':file_sha(OUT/'report.json'),'validator_sha256':file_sha(Path(__file__)),
        'roster_records':len(f),'orphan_records_preserved':len(orphan),'scalar_records_verified':len(f),'scalar_mismatches':0,
        'coverage_rows':45,'matrix_rows':15,'strict_30d_records':308955,'strict_30d_yes':56262,**native}
    if database:
        result['database'] = database_acceptance(f,source,rules)
    put(OUT/('database-validation.json' if database else 'local-validation.json'),encoded(result))
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',action='store_true')
    main(parser.parse_args().database)
