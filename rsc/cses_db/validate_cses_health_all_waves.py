#!/usr/bin/env python3
"""Independent scalar acceptance and optional SELECT-only database verification."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

import pandas as pd
from align_cses_additional_school import KEYS, ROOT, require
from build_cses_additional_waves import encoded
from build_cses_additional_waves import source_keys as extra_keys
from cache_cses_questionnaires import file_sha, put
from inventory_cses_archives import DataSource
from pilot_cses_health_all_waves import BRANCHES, OUT, OUTCOMES
from plan_cses_health_illness import source_keys as old_keys
from validate_cses_education_all_waves import equal, number


def decide(row,rule):
    x = number(row.screen_native)
    mapping = {int(k):v for k,v in rule['mapping'].items()}
    value = mapping.get(x)
    no = value==0 and any(number(getattr(row,c)) is not None for c in BRANCHES[:len(rule['no_followups'])])
    injury = x==2 and any(number(getattr(row,c)) is not None for c in BRANCHES[:len(rule['injury_only'])])
    conflict = x in rule.get('disputed_codes',[])
    if rule['variable'] is None:
        status = 'not_collected_in_selected_source'
    elif rule['period_days'] is None:
        status = 'unverified_same_wave_form_scope'
    elif not row.health_linked:
        status = 'missing_health_source_record'
    elif not row.hh_link_matched:
        status = 'household_not_matched'
    elif x is None:
        status = 'source_null'
    elif x in rule['missing_codes']:
        status = 'explicit_missing_code'
    elif value is None:
        status = 'unrecognized_native_code'
    elif conflict:
        status = 'source_form_code_conflict'
    elif row.screen_variant_conflict:
        status = 'screen_variant_conflict'
    elif no or injury:
        status = 'screening_branch_conflict'
    else:
        status = 'observed_with_instrument_scope'
    q = value if status=='observed_with_instrument_scope' else None
    candidate = q if rule['period_days']==30 else None
    strict = candidate if rule['strict_30d'] else None
    strict_status = status
    if status=='observed_with_instrument_scope':
        strict_status = 'observed_30day_screen' if rule['strict_30d'] else 'separate_period_or_concept' if rule['period_days']!=30 else 'qualified_wave_not_in_strict_default'
    return {'screen_binary_native':value,'screen_qualified':q,'illness_injury_30d_candidate':candidate,
        'illness_injury_30d_qualified':strict,'no_with_followup':no,'injury_with_illness_only':injury,
        'source_form_code_conflict':conflict,'screen_status':status,'strict_30d_status':strict_status,
        'screen_applicable':bool(rule['variable'] and rule['period_days'] and row.health_linked and row.hh_link_matched),
        'screen_imputed':False,'cross_wave_equivalence_certified':False}


def native_acceptance(source,rules):
    extra = json.loads((ROOT/'rsc/specs/cses_additional_waves_v1.json').read_text())['waves']
    for rule in rules:
        wave = rule['survey_wave']
        raw_bytes = DataSource(ROOT/rule['source_archive'],tuple(rule['source_member_chain'])).read_bytes()
        require(hashlib.sha256(raw_bytes).hexdigest()==rule['source_sha256'],'Member hash changed')
        raw = pd.read_stata(io.BytesIO(raw_bytes),convert_categoricals=False,convert_dates=False)
        if wave in extra:
            c = extra[wave]
            keys = pd.DataFrame({'survey_wave':wave,'household_key':extra_keys(raw,c['household_key'],wave),
                'record_key':extra_keys(raw,c['household_key']+[c['person_key']],wave)})
        else:
            keys = old_keys(raw,wave).rename(columns={'household_id':'household_key','person_id':'record_key'})
        expected = source.loc[source.survey_wave.eq(wave)].sort_values('source_row_number').reset_index(drop=True)
        pd.testing.assert_frame_equal(keys[KEYS].reset_index(drop=True).astype(expected[KEYS].dtypes.to_dict()),expected[KEYS],check_exact=True)
        variable = rule['variable']
        for output,column in [('screen_native',variable),*[(c,rule['no_followups'][i] if i<len(rule['no_followups']) else None) for i,c in enumerate(BRANCHES)]]:
            values = raw[column].astype(float) if column else pd.Series(float('nan'),index=raw.index)
            pd.testing.assert_series_equal(values.reset_index(drop=True),expected[output],check_names=False,check_exact=True)
    return {'native_mismatches':0,'source_rows':len(source),'waves':len(rules)}


def database_acceptance(f,source,rules):
    from publish_cses_geography_interface import connect
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute('SET LOCAL ROLE mda_readonly')
        require(conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on','Read-only required')
        spine = pd.DataFrame(conn.execute('SELECT survey_wave,household_key,record_key,age_for_analysis FROM cses_analysis.cses_education_unified_v1').fetchall())
        columns = KEYS+['age_for_analysis']
        spine = spine[columns].sort_values(KEYS).reset_index(drop=True).astype(f[columns].dtypes.to_dict())
        pd.testing.assert_frame_equal(spine,f[columns],check_exact=True)
        for rule in rules:
            wave,var = rule['survey_wave'],rule['variable']
            if var is None:
                continue
            old = wave not in ['1996','1997','1999','2023','2025']
            relation = 'cses_data.cses_health_illness_source_v1' if old else 'cses_data.cses_additional_health_v1'
            keys = 'survey_wave,household_id AS household_key,person_id AS record_key' if old else ','.join(KEYS)
            record = 'raw_record' if old else 'source_values'
            actual = pd.DataFrame(conn.execute(f'SELECT {keys},({record}->>%s)::double precision AS screen_native FROM {relation} WHERE survey_wave=%s',(var,wave)).fetchall())
            expected = source.loc[source.survey_wave.eq(wave),KEYS+['screen_native']].sort_values(KEYS).reset_index(drop=True)
            actual = actual[list(expected)].sort_values(KEYS).reset_index(drop=True).astype(expected.dtypes.to_dict())
            pd.testing.assert_frame_equal(actual,expected,check_exact=True)
        geo = pd.DataFrame(conn.execute('SELECT survey_wave,household_key,record_key FROM cses_analysis.cses_person_geography_v2').fetchall())
        require(len(geo)==len(f) and not geo.duplicated(KEYS).any(),'Geography key grain differs')
        matched = f[KEYS].merge(geo,on=KEYS,how='outer',validate='one_to_one',indicator=True)
        require(matched['_merge'].eq('both').all(),'Geography keys differ')
    return {'role':'mda_readonly','transaction_read_only':True,'database_modified':False,
        'roster_age_records_verified':len(f),'source_screen_mismatches':0,'geography_linked':len(geo),'geography_mismatches':0}


def main(database=False):
    report = json.loads((OUT/'report.json').read_text())
    require(report['prototype_not_published'] and not report['database_modified'],'Local-only scope required')
    for p,sha in report['inputs'].items():
        require(file_sha(ROOT/p)==sha,'Input changed: '+p)
    for name,sha in report['artifacts'].items():
        require(file_sha(OUT/name)==sha,'Artifact changed: '+name)
    f,source,orphan = [pd.read_parquet(OUT/name) for name in ['members.parquet','sources.parquet','orphan_health.parquet']]
    rules = json.loads((OUT/'rules.json').read_text())
    lookup = {r['survey_wave']:r for r in rules}
    require(len(f)==571699 and not f.duplicated(KEYS).any(),'Roster grain differs')
    require(len(source)==571638 and len(orphan)==5 and int((~f.health_linked).sum())==66,'Health linkage counts differ')
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
    coverage = json.loads((OUT/'coverage.json').read_text())
    require(len(coverage)==45 and all(all(r[k]==v for k,v in counters[r['survey_wave'],r['age_band']].items()) for r in coverage),'Independent coverage differs')
    matrix = json.loads((OUT/'matrix.json').read_text())
    require(len(matrix)==15,'Matrix grain differs')
    for r in matrix:
        g = f.loc[f.survey_wave.eq(r['survey_wave'])]
        require(all(r[t+'_records']==int(g[t].notna().sum()) for t in OUTCOMES),'Matrix count differs')
    result = {'passed':True,'database_modified':False,'database_accessed':database,'report_sha256':file_sha(OUT/'report.json'),
        'validator_sha256':file_sha(Path(__file__)),'roster_records':len(f),'orphan_records_preserved':len(orphan),
        'scalar_records_verified':len(f),'scalar_mismatches':0,'coverage_rows':45,'matrix_rows':15,**native}
    if database:
        result['database'] = database_acceptance(f,source,rules)
    put(OUT/('database-validation.json' if database else 'local-validation.json'),encoded(result))
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',action='store_true')
    main(parser.parse_args().database)
