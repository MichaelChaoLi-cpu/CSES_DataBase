#!/usr/bin/env python3
"""Independent post-publication native-byte and scalar health acceptance; SELECT only."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd
from align_cses_additional_school import require
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put
from cses_health_screen_sql import RULE, SOURCE, TARGETS, VIEW
from publish_cses_geography_interface import connect
from publish_cses_health_screen_v2 import EXECUTION, OUT, checked_plan
from validate_cses_education_all_waves import equal, number
from validate_cses_health_all_waves import decide, native_acceptance


def main():
    f,source,orphan,rules,parent,e,plan = checked_plan()
    pub = json.loads((OUT/'published.json').read_text())
    require(pub['committed'] and pub['execution_sha256']==file_sha(EXECUTION),'Committed matching release required')
    lookup = {r['survey_wave']:r['rule'] for r in rules}
    counters = {}
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute("SET LOCAL statement_timeout='180s'")
        conn.execute('SET LOCAL ROLE mda_readonly')
        require(conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on','Read-only required')
        require(conn.execute(f'SELECT * FROM {RULE} ORDER BY survey_wave').fetchall()==rules,'Published rule mismatch')
        actual_source = pd.DataFrame(conn.execute(f'SELECT * FROM {SOURCE} ORDER BY survey_wave COLLATE "C",household_key COLLATE "C",record_key COLLATE "C"').fetchall()).astype(source.dtypes.to_dict())
        pd.testing.assert_frame_equal(actual_source,source,check_exact=True)
        native = native_acceptance(actual_source,[r['rule'] for r in rules])
        offset = 0
        with conn.cursor(name='native_scalar_health_acceptance') as cursor:
            cursor.execute(f'SELECT * FROM {VIEW} ORDER BY survey_wave COLLATE "C",household_key COLLATE "C",record_key COLLATE "C"')
            while rows := cursor.fetchmany(5000):
                actual = pd.DataFrame(rows).astype(f.dtypes.to_dict())
                pd.testing.assert_frame_equal(actual,f.iloc[offset:offset+len(rows)].reset_index(drop=True),check_exact=True)
                for row in actual.itertuples(index=False):
                    expected = decide(row,lookup[row.survey_wave])
                    require(all(equal(getattr(row,k),v) for k,v in expected.items()),'Independent scalar health mismatch')
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
                        for target in TARGETS:
                            value = expected[target]
                            c[target+'_records'] += value is not None
                            c[target+'_yes'] += value==1
                            c[target+'_no'] += value==0
                offset += len(rows)
        require(offset==571699,'Published member grain mismatch')
    from prepare_cses_health_screen_interface import PILOT
    coverage = json.loads((PILOT/'coverage.json').read_text())
    require(len(counters)==45 and all(all(r[k]==v for k,v in counters[r['survey_wave'],r['age_band']].items()) for r in coverage),'Independent denominator mismatch')
    result = {'passed':True,'database_modified':False,'transaction_read_only':True,'role':'mda_readonly',
        'validator_sha256':file_sha(Path(__file__)),'published_sha256':file_sha(OUT/'published.json'),
        'member_rows_exact':offset,'member_columns_exact':len(f.columns),'source_rows_exact':len(actual_source),
        'native_mismatches':0,'scalar_mismatches':0,'independent_age_band_rows':45,
        'strict_30d_records':int(sum(c['illness_injury_30d_qualified_records'] for (w,b),c in counters.items() if b=='all_members')),
        'strict_30d_yes':int(sum(c['illness_injury_30d_qualified_yes'] for (w,b),c in counters.items() if b=='all_members')),
        'native_acceptance':native,'orphan_rows_preserved':len(orphan)}
    require(result['strict_30d_records']==308955 and result['strict_30d_yes']==56262,'Strict denominator mismatch')
    put(OUT/'independent-native.json',encoded(result))
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    main()
