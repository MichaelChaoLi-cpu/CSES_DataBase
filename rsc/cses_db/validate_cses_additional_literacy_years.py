#!/usr/bin/env python3
"""Independent native-Stata acceptance of literacy and observed schooling years."""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import psycopg
from align_cses_additional_literacy_years import COVERAGE, OUT, ROOT, RULE, TARGETS, VIEW
from align_cses_additional_school import KEYS, require
from build_cses_additional_waves import encoded, fields_for, metadata_only, source_keys
from cache_cses_questionnaires import file_sha, put
from psycopg.rows import dict_row


def number(x):
    return None if pd.isna(x) else float(x)


def equal(actual,expected):
    return (pd.isna(actual) and expected is None) or (pd.notna(actual) and actual==expected)


def decide(wave,age,linked,ever,combined,read,write,years):
    """Scalar policy, no calls to the vector classifier or SQL generator."""
    legacy = wave in ['1996','1997','1999']
    eligible = None if age is None else age >= (5 if legacy else 3)
    bad_years = years is not None and not (0<=years<=30 and years==int(years))
    age_conflict = years is not None and age is not None and years>age
    out = {}
    for target,value in [('combined',combined),('read',read),('write',write),('years',years)]:
        available = target=='combined' or not legacy
        qualified = None
        if not available:
            status = 'not_collected_in_selected_education_source'
        elif eligible is None:
            status = 'unknown_age_eligibility'
        elif not eligible:
            status = 'outside_questionnaire_age_range'
        elif not linked:
            status = 'missing_education_record'
        elif target=='years':
            if ever is not None and ever not in [1,2]:
                status = 'unrecognized_ever_attendance_code'
            elif ever is None:
                status = 'ever_attendance_unresolved'
            elif ever==2:
                status = 'documented_skip_no_years_value' if value is None else 'years_value_outside_ever_attendance_route'
            elif bad_years:
                status = 'outside_integer_0_30_guard'
            elif age_conflict:
                status = 'years_exceed_source_age'
            elif value is None:
                status = 'missing_years_after_ever_yes'
            else:
                status,qualified = 'observed_years',int(value)
        elif target=='combined' and not legacy:
            if any(x is not None and x not in [1,2] for x in [read,write]):
                status = 'unrecognized_component_code'
            elif read is None or write is None:
                status = 'missing_component_response'
            else:
                status,qualified = 'derived_both_valid_read_and_write',int(read==1 and write==1)
        elif value is None:
            status = 'missing_response'
        elif value not in [1,2]:
            status = 'unrecognized_native_binary_code'
        else:
            status,qualified = 'observed_binary',int(value==1)
        out.update({f'{target}_source_available':available,f'{target}_status':status,
            f'{target}_qualified':qualified,f'{target}_target_applicable':bool(available and eligible and linked)})
    out.update({'years_numeric_guard_failed':bad_years,'years_exceed_source_age':age_conflict,
        'years_expected_by_route':out['years_target_applicable'] and ever==1,
        'combined_derived_from_components':out['combined_status']=='derived_both_valid_read_and_write',
        'write_yes_read_no_warning':write==1 and read==2,'literacy_instrument_equivalence_certified':False,
        'years_imputation_performed':False})
    return out


def main(local=False):
    evidence = json.loads((OUT/'evidence.json').read_text())
    for p,sha in evidence['inputs'].items():
        require(file_sha(ROOT/p)==sha,'Pinned source changed: '+p)
    require(file_sha(OUT/'rules.json')==evidence['rules_sha256'],'Rules changed')
    rules = json.loads((OUT/'rules.json').read_text())
    geography = None
    if local:
        require(file_sha(OUT/'expected.parquet')==evidence['expected_sha256'],'Candidate changed')
        actual = pd.read_parquet(OUT/'expected.parquet')
        coverage = evidence['summary']
    else:
        with psycopg.connect(dbname='mda',connect_timeout=5,row_factory=dict_row,
             options='-c default_transaction_read_only=on -c statement_timeout=55000') as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            conn.execute('SET LOCAL ROLE mda_readonly')
            require(conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on','Read-only required')
            actual = pd.DataFrame(conn.execute(f'SELECT * FROM {VIEW}').fetchall())
            coverage = conn.execute(f'SELECT * FROM {COVERAGE} ORDER BY survey_wave,age_band,target').fetchall()
            require(conn.execute(f'SELECT * FROM {RULE} ORDER BY survey_wave,target').fetchall()==sorted(rules,key=lambda r:(r['survey_wave'],r['target'])),'Published rules differ')
            geography = conn.execute(f'SELECT count(*) n FROM {VIEW} v JOIN cses_analysis.cses_person_geography_v2 g USING(survey_wave,household_key,record_key)').fetchone()['n']
            require(geography==212779,'Geography link differs')
    require(len(actual)==212779 and not actual.duplicated(KEYS).any(),'Roster grain changed')
    spec = json.loads((ROOT/'rsc/specs/cses_additional_waves_v1.json').read_text())
    lookup = {(r['survey_wave'],r['target']):r for r in rules}
    counters = defaultdict(Counter)
    labels = {'combined':'Can Read And Write Combined','read':'Can Read','write':'Can Write','years':'Years Attended School Source Value'}
    for wave,cfg in spec['waves'].items():
        with zipfile.ZipFile(ROOT/cfg['archive']) as z:
            hb = z.read(cfg['modules']['HL']['member'])
            eb = z.read(cfg['modules']['ED']['member'])
        h = pd.read_stata(io.BytesIO(hb),convert_categoricals=False)
        e = pd.read_stata(io.BytesIO(eb),convert_categoricals=False)
        for f in [h,e]:
            f['record_key'] = source_keys(f,cfg['household_key']+[cfg['person_key']],wave)
            f['household_key'] = source_keys(f,cfg['household_key'],wave)
            require(f.record_key.is_unique,'Duplicate native member key')
        h,e = h.set_index('record_key'),e.set_index('record_key')
        fields = fields_for(spec,cfg['modules']['ED'])
        _,metadata = metadata_only(eb)
        for target in TARGETS:
            rule = lookup[wave,target]
            names = [fields[labels[target]][0]] if labels[target] in fields else []
            if target=='combined' and wave in ['2023','2025']:
                names = ['q02c02','q02c03']
            require(rule['source_variables']==names and rule['source_available']==bool(names),'Rule field availability differs')
            for variable in names:
                info = next(m for m in metadata if m['name']==variable)
                require(rule['source_variable_labels'][variable]==info['label'] and rule['native_value_labels'][variable]==info['value_labels'],'Native labels differ')
        group = actual.loc[actual.survey_wave.eq(wave)]
        require(set(group.record_key)==set(h.index) and set(e.index).issubset(set(h.index)),'Native key set differs')
        agevar = 'age' if wave=='2025' else fields_for(spec,cfg['modules']['HL'])['Age Source Value'][0]
        for r in group.itertuples(index=False):
            linked = r.record_key in e.index
            ed = e.loc[r.record_key] if linked else None
            age = number(h.loc[r.record_key,agevar])
            require(r.household_key==h.loc[r.record_key,'household_key'],'Native household key differs')
            if linked:
                require(r.household_key==ed.household_key,'Native ED household differs')
            def get(label):
                return number(ed[fields[label][0]]) if linked and label in fields else None
            values = [get(labels[t]) for t in TARGETS]
            ever = get('Ever Attended School')
            minimum = 5 if wave in ['1996','1997','1999'] else 3
            native = {'age_for_education_analysis':age,'education_age_eligible':None if age is None else age>=minimum,
                'education_record_linked':linked,'school_ever_native_code':ever,'questionnaire_minimum_age':minimum,
                **{f'{t}_source_value':v for t,v in zip(TARGETS,values,strict=True)}}
            for field,value in native.items():
                require(equal(getattr(r,field),value),'Native value mismatch: '+wave+'/'+field)
            expected = decide(wave,age,linked,ever,*values)
            for field,value in expected.items():
                require(equal(getattr(r,field),value),'Scalar classification mismatch: '+wave+'/'+field)
            require(r.literacy_years_release==evidence['version'],'Release stamp differs')
            for band,inband in [('questionnaire_age_eligible',native['education_age_eligible']),('ages_15_plus',age is not None and age>=15)]:
                if not inband:
                    continue
                for target,value in zip(TARGETS,values,strict=True):
                    c = counters[wave,band,target]
                    q = expected[f'{target}_qualified']
                    app = expected[f'{target}_target_applicable']
                    byroute = expected['years_expected_by_route'] if target=='years' else app
                    c['members_in_age_band'] += 1
                    c['target_applicable_members'] += app
                    c['expected_response_by_route'] += byroute
                    c['source_non_null'] += value is not None
                    c['qualified_records'] += q is not None
                    c['qualified_yes'] += q==1
                    c['qualified_no'] += q==0
                    c['unresolved_expected_response'] += byroute and q is None
                    c['unrecognized_response_records'] += expected[f'{target}_status'].startswith('unrecognized_')
                    c['derived_combined'] += target=='combined' and expected['combined_derived_from_components']
                    c['documented_years_skips'] += target=='years' and expected['years_status']=='documented_skip_no_years_value'
                    c['years_age_conflicts'] += target=='years' and expected['years_exceed_source_age']
    require(len(coverage)==40,'Coverage row count differs')
    for row in coverage:
        key = row['survey_wave'],row['age_band'],row['target']
        count = counters[key]
        require(row['source_available']==lookup[key[0],key[2]]['source_available'],'Coverage availability differs')
        for field in ['qualified_yes','qualified_no']:
            if key[2]=='years':
                require(row[field] is None,'Years are not a binary indicator')
                count.pop(field,None)
        require(all(row[k]==v for k,v in count.items()),'Independent denominator mismatch: '+str(key))
    result = {'passed':True,'role':None if local else 'mda_readonly','read_only':True,'database_accessed':not local,
        'native_rows_verified':len(actual),'classified_field_records':4*len(actual),'native_and_qualified_mismatches':0,
        'geography_linked':geography,'independent_denominator_rows':len(coverage),'rule_rows_verified':len(rules),
        'validator_sha256':file_sha(Path(__file__)),'expected_sha256':file_sha(OUT/'expected.parquet'),
        'rules_sha256':file_sha(OUT/'rules.json')}
    if not local:
        result['published_sha256'] = file_sha(OUT/'published.json')
    put(OUT/('independent-local-checks.json' if local else 'independent-checks.json'),encoded(result))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--local',action='store_true')
    main(p.parse_args().local)
