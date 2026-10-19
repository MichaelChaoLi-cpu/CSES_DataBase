#!/usr/bin/env python3
"""Read-only diagnosis of gaps between registered health JSON and native pilot inputs."""
import json
from pathlib import Path

import pandas as pd
from align_cses_additional_school import KEYS, ROOT, require
from audit_cses_health_release import PILOT
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put
from cses_health_screen_sql import BRANCHES
from psycopg.types.json import Jsonb
from publish_cses_geography_interface import connect

OUT = ROOT/'data/processing/cses/health_database_input_audit_v1'


def main():
    rules = json.loads((PILOT/'rules.json').read_text())
    branches = ','.join(f"(h.payload->>(r.rule->'no_followups'->>{i}))::double precision AS {c}" for i,c in enumerate(BRANCHES))
    query = f'''WITH r AS (SELECT survey_wave,rule FROM jsonb_to_recordset(%s::jsonb) AS t(survey_wave text,rule jsonb)),
      h AS (SELECT survey_wave,household_id AS household_key,person_id AS record_key,raw_record AS payload
        FROM cses_data.cses_health_illness_source_v1 UNION ALL
        SELECT survey_wave,household_key,record_key,source_values FROM cses_data.cses_additional_health_v1)
      SELECT h.survey_wave,h.household_key,h.record_key,
        (h.payload->>(r.rule->>'variable'))::double precision AS screen_native,{branches}
      FROM h JOIN r USING(survey_wave)'''
    with connect() as conn:
        conn.execute('SET LOCAL ROLE mda_readonly')
        require(conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on','Read-only required')
        actual = pd.DataFrame(conn.execute(query,(Jsonb([{'survey_wave':r['survey_wave'],'rule':r} for r in rules]),)).fetchall())
    actual = actual.sort_values(KEYS).reset_index(drop=True)
    native = pd.read_parquet(PILOT/'sources.parquet').sort_values(KEYS).reset_index(drop=True)
    pd.testing.assert_frame_equal(actual[KEYS].astype(native[KEYS].dtypes.to_dict()),native[KEYS],check_exact=True)
    rows,affected = [],pd.Series(False,index=native.index)
    for col in ['screen_native',*BRANCHES]:
        d = ~(actual[col].eq(native[col])|(actual[col].isna()&native[col].isna()))
        require(actual.loc[d,col].isna().all() and native.loc[d,col].notna().all(),'Not solely missing native inputs')
        affected |= d
        for wave,n in native.loc[d,'survey_wave'].value_counts().items():
            rule = next(r for r in rules if r['survey_wave']==wave)
            variable = rule['variable'] if col=='screen_native' else rule['no_followups'][BRANCHES.index(col)]
            rows.append({'survey_wave':wave,'pilot_column':col,'native_variable':variable,'non_null_native_cells_absent_from_json':int(n)})
    result = {'passed':True,'database_modified':False,'role':'mda_readonly','transaction_read_only':True,
        'pilot_report_sha256':file_sha(PILOT/'report.json'),'script_sha256':file_sha(Path(__file__)),
        'source_records_compared':len(native),'screen_value_mismatches':0,
        'missing_non_null_branch_cells':sum(r['non_null_native_cells_absent_from_json'] for r in rows),
        'affected_records_by_wave':native.loc[affected,'survey_wave'].value_counts().to_dict(),
        'differences':rows,'remedy':'Add a separate native-input bridge for all five additional waves; preserve existing tables and frozen pilot.'}
    put(OUT/'report.json',encoded(result))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
