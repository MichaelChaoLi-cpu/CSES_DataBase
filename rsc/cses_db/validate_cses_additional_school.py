#!/usr/bin/env python3
"""Independent read-only acceptance against original Stata and scalar route logic."""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import psycopg
from align_cses_additional_school import COVERAGE, KEYS, OUT, ROOT, RULE, VIEW, require
from build_cses_additional_waves import encoded, fields_for, source_keys
from cache_cses_questionnaires import file_sha, put
from psycopg.rows import dict_row


def native(value):
    return None if pd.isna(value) else float(value)


def decide(age, minimum, linked, cur, ever, highest, grade, rule):
    """Scalar implementation independent of pandas and the view's SQL CASE."""
    current = {1:1,2:0}.get(cur)
    prior = {1:1,2:0}.get(ever)
    invalid = (cur is not None and cur not in [1,2]) or (ever is not None and ever not in [1,2])
    grade_hint = grade is not None and grade not in rule['neutral_current_codes']
    history_hint = highest is not None and highest not in rule['neutral_highest_codes']
    never_current = prior == 0 and current == 1
    never_history = prior == 0 and (history_hint or grade_hint)
    no_grade = current == 0 and grade_hint
    conflict = never_current or never_history or no_grade
    eligible = age is not None and age >= minimum
    gate_missing = rule['skip_supported'] and prior is None and current is not None
    if age is None:
        status = 'unknown_age_eligibility'
    elif not eligible:
        status = 'outside_questionnaire_age_range'
    elif not linked:
        status = 'missing_education_record'
    elif invalid:
        status = 'unrecognized_native_response_code'
    elif conflict:
        status = 'unresolved_route_conflict'
    elif gate_missing:
        status = 'observed_current_gate_missing'
    elif current is not None:
        status = 'observed_current'
    elif rule['skip_supported'] and prior == 0:
        status = 'documented_skip_inferred_no'
    elif rule['skip_supported'] and prior is None:
        status = 'unanswered_gate_and_current'
    elif rule['skip_supported'] and prior == 1:
        status = 'unanswered_current_after_ever_yes'
    else:
        status = 'unanswered_current_attendance'
    derived = status == 'documented_skip_inferred_no'
    value = 0 if derived else current if status in ['observed_current','observed_current_gate_missing'] else None
    return {'school_current_observed':current,'school_ever_observed':prior,
            'school_age_eligible':None if age is None else eligible,
            'school_invalid_response_code':invalid,'school_ever_no_current_yes':never_current,
            'school_never_with_history_response':never_history,'school_not_current_with_current_grade':no_grade,
            'school_route_conflict':conflict,'school_gate_missing_with_current_observed':gate_missing,
            'school_current_grade_missing':rule['skip_supported'] and current==1 and grade is None,
            'education_record_outside_age_universe':linked and age is not None and not eligible,
            'school_route_status':status,'school_attendance_qualified':value,
            'school_attendance_derived_from_skip':derived,'qualified_denominator_eligible':value is not None}


def equal(a, b):
    return (pd.isna(a) and b is None) or (pd.notna(a) and a == b)


def main(local=False):
    evidence = json.loads((OUT/'evidence.json').read_text())
    spec = json.loads((ROOT/'rsc/specs/cses_additional_waves_v1.json').read_text())
    if local:
        actual = pd.read_parquet(OUT/'expected.parquet')
        summaries = evidence['summary']
        geography = None
        require(len(actual)==212779 and not actual.duplicated(KEYS).any(),'Local roster grain differs')
    else:
        with psycopg.connect(dbname='mda',connect_timeout=5,row_factory=dict_row,
                         options='-c default_transaction_read_only=on -c statement_timeout=55000') as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            conn.execute('SET LOCAL ROLE mda_readonly')
            require(conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on','Read-only required')
            actual = pd.DataFrame(conn.execute(f'SELECT * FROM {VIEW}').fetchall())
            geography = conn.execute(f'''SELECT count(*) n FROM {VIEW} s
              JOIN cses_analysis.cses_person_geography_v2 g USING(survey_wave,household_key,record_key)''').fetchone()['n']
            require(geography==212779 and len(actual)==212779 and not actual.duplicated(KEYS).any(),'Roster/geography grain differs')
            summaries = conn.execute(f'SELECT * FROM {COVERAGE} ORDER BY survey_wave,age_band').fetchall()
            rule_hashes = conn.execute(f'SELECT survey_wave,evidence_sha256,questionnaire_sha256 FROM {RULE} ORDER BY survey_wave').fetchall()
        expected_rules = [{'survey_wave':r['survey_wave'],'evidence_sha256':file_sha(OUT/'evidence.json'),
                           'questionnaire_sha256':r['questionnaire_sha256']} for r in evidence['rules']]
        require(rule_hashes==expected_rules,'Evidence-rule binding differs')
    require(not actual.school_cross_wave_equivalence_certified.any(),'Unreviewed equivalence asserted')
    profiles, bands = {}, defaultdict(Counter)
    for rule in evidence['rules']:
        w = rule['survey_wave']
        cfg = spec['waves'][w]
        require(file_sha(ROOT/cfg['archive'])==cfg['sha256'],'Source archive changed')
        ef = fields_for(spec,cfg['modules']['ED'])
        age_variable = fields_for(spec,cfg['modules']['HL'])['Age Source Value'][0]
        hcols = cfg['household_key']+[cfg['person_key'],age_variable]+(['age'] if w=='2025' else [])
        ecols = cfg['household_key']+[cfg['person_key']]+[v[0] for v in ef.values()]
        with zipfile.ZipFile(ROOT/cfg['archive']) as z:
            h = pd.read_stata(io.BytesIO(z.read(cfg['modules']['HL']['member'])),convert_categoricals=False,columns=list(dict.fromkeys(hcols)))
            e = pd.read_stata(io.BytesIO(z.read(cfg['modules']['ED']['member'])),convert_categoricals=False,columns=list(dict.fromkeys(ecols)))
        for f in [h,e]:
            f['record_key'] = source_keys(f,cfg['household_key']+[cfg['person_key']],w)
            f['household_key'] = source_keys(f,cfg['household_key'],w)
            require(f.record_key.is_unique,'Duplicate native person key')
        h = h.set_index('record_key')
        e = e.set_index('record_key')
        g = actual.loc[actual.survey_wave.eq(w)]
        require(set(h.index)==set(g.record_key) and set(e.index).issubset(set(h.index)),'Native keys differ')
        statuses = Counter()
        for r in g.itertuples(index=False):
            src = h.loc[r.record_key]
            linked = r.record_key in e.index
            require(src.household_key==r.household_key,'Native household key differs')
            vals = e.loc[r.record_key] if linked else None
            if linked:
                require(vals.household_key==r.household_key,'Native ED household key differs')
            def get(target):
                return native(vals[ef[target][0]]) if linked and target in ef else None
            cur, ever = get('Currently Attending School'), get('Ever Attended School')
            highest, grade = get('Highest Education Level Source Code'), get('Current Education Level Source Code')
            age = native(src['age' if w=='2025' else age_variable])
            for field,value in {'education_record_linked':linked,'age_source_value':native(src[age_variable]),
                'age_for_school_analysis':age,'school_current_native_code':cur,'school_ever_native_code':ever,
                'school_highest_level_source_code':highest,'school_current_level_source_code':grade,
                'questionnaire_minimum_age':rule['questionnaire_minimum_age'], 'school_concept_scope':rule['concept_scope']}.items():
                require(equal(getattr(r,field),value),'Native field mismatch: '+w+'/'+field)
            expected = decide(age,rule['questionnaire_minimum_age'],linked,cur,ever,highest,grade,rule)
            for field,value in expected.items():
                require(equal(getattr(r,field),value),'Independent route mismatch: '+w+'/'+field)
            statuses[expected['school_route_status']] += 1
            for band,included in [('questionnaire_age_eligible',expected['school_age_eligible']),
                                  ('ages_6_17',age is not None and 6<=age<=17),
                                  ('ages_10_14',age is not None and 10<=age<=14)]:
                if included:
                    counter = bands[w,band]
                    counter['members'] += 1
                    counter['qualified_yes'] += expected['school_attendance_qualified']==1
                    counter['qualified_no'] += expected['school_attendance_qualified']==0
                    counter['unknown_or_excluded'] += expected['school_attendance_qualified'] is None
                    counter['inferred_no'] += expected['school_attendance_derived_from_skip']
        profiles[w] = dict(statuses)
    for s in summaries:
        require(all(s[k]==v for k,v in bands[s['survey_wave'],s['age_band']].items()), 'Independent denominator mismatch')
    result = {'passed':True,'role':None if local else 'mda_readonly','database_accessed':not local,
              'read_only':True,'native_rows_verified':len(actual),
              'native_and_qualified_mismatches':0,'geography_linked':geography,'independent_denominator_rows':len(summaries),
              'route_status_counts':profiles,'validator_sha256':file_sha(Path(__file__)),
              'expected_sha256':file_sha(OUT/'expected.parquet')}
    if not local:
        result['published_sha256'] = file_sha(OUT/'published.json')
    put(OUT/('independent-local-checks.json' if local else 'independent-checks.json'),encoded(result))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local',action='store_true',help='Check local candidate without connecting to PostgreSQL')
    main(parser.parse_args().local)
