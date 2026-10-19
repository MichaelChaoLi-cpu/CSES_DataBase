#!/usr/bin/env python3
"""Independent raw-Stata and scalar acceptance, locally or in a read-only DB."""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import psycopg
from align_cses_additional_levels import BOOK, COVERAGE, OUT, ROOT, VIEW
from align_cses_additional_school import KEYS, require
from build_cses_additional_waves import encoded, fields_for, source_keys
from cache_cses_questionnaires import file_sha, put
from psycopg.rows import dict_row


def number(value):
    return None if pd.isna(value) else float(value)


def equal(a,b):
    return (pd.isna(a) and b is None) or (pd.notna(a) and a==b)


def parent_flags(wave,high,level,ever,current):
    """Reproduce the immutable release-19 warning, not its future-data code policy."""
    ev,cu = {1:1,2:0}.get(ever),{1:1,2:0}.get(current)
    invalid = (ever is not None and ever not in [1,2]) or (current is not None and current not in [1,2])
    h = high is not None and high not in ([0] if wave in ['1997','1999'] else [88,98,-98])
    c = level is not None and level not in ([0] if wave in ['1997','1999'] else [98,-98])
    route = (ev==0 and (cu==1 or h or c)) or (cu==0 and c)
    return route,invalid


def decide(wave,eligible,linked,ever,current,high,level,h,c):
    ev,cu = {1:1,2:0}.get(ever),{1:1,2:0}.get(current)
    ih = ever is not None and ever not in [1,2]
    ic = current is not None and current not in [1,2]
    hk,ck = h['response_kind'] if h else None,c['response_kind'] if c else None
    hint_h = high is not None and hk not in ['none','unknown']
    hint_c = level is not None and ck not in ['none','unknown']
    conflict = ev==0 and (cu==1 or hint_h or hint_c)
    route,invalid = parent_flags(wave,high,level,ever,current)
    warning = route or invalid
    if eligible is None:
        hs = 'unknown_age_eligibility'
    elif not eligible:
        hs = 'outside_questionnaire_age_range'
    elif not linked:
        hs = 'missing_education_record'
    elif ih:
        hs = 'unrecognized_ever_attendance_code'
    elif conflict:
        hs = 'never_attended_route_conflict'
    elif hk=='unknown':
        hs = 'explicit_unknown_highest'
    elif high is not None and h is None:
        hs = 'unrecognized_highest_code'
    elif high is None:
        hs = ('derived_never_attended_from_documented_skip' if ev==0 else
              'missing_highest_after_ever_yes' if ev==1 else 'missing_highest_gate_unresolved')
    elif ev is None and wave!='1996':
        hs = 'observed_highest_gate_missing'
    elif warning:
        hs = 'observed_highest_other_item_warning'
    else:
        hs = 'observed_highest'
    if wave=='1996':
        cs = 'not_collected_in_selected_education_source'
    elif eligible is None:
        cs = 'unknown_age_eligibility'
    elif not eligible:
        cs = 'outside_questionnaire_age_range'
    elif not linked:
        cs = 'missing_education_record'
    elif ih or ic:
        cs = 'unrecognized_attendance_gate_code'
    elif ev==0 and cu==1:
        cs = 'never_attended_route_conflict'
    elif cu is None:
        cs = 'current_attendance_unresolved'
    elif cu==0:
        cs = 'current_code_outside_attendance_route' if level is not None else 'not_currently_attending'
    elif level is not None and c is None:
        cs = 'unrecognized_current_level_code'
    elif ck=='unknown':
        cs = 'explicit_unknown_current_level'
    elif ck=='none':
        cs = 'none_not_a_current_level'
    elif level is None:
        cs = 'missing_current_level_after_yes'
    else:
        cs = 'observed_current_level'
    derived = hs=='derived_never_attended_from_documented_skip'
    hf = 'never_attended' if derived else h['semantic_family'] if hs.startswith('observed_highest') else None
    hg = h['general_grade'] if hs.startswith('observed_highest') else None
    cf = c['semantic_family'] if cs=='observed_current_level' else None
    cg = c['general_grade'] if cs=='observed_current_level' else None
    applicable = bool(eligible and linked)
    return {'highest_level_status':hs,'current_level_status':cs,'highest_qualified_family':hf,
        'current_qualified_family':cf,'highest_qualified_general_grade':hg,'current_qualified_general_grade':cg,
        'highest_derived_from_skip':derived,'highest_other_item_warning':warning,
        'highest_target_applicable':applicable,'current_target_available':wave!='1996',
        'current_target_applicable':wave!='1996' and applicable and cu==1,
        'highest_family_usable':hf is not None,'current_family_usable':cf is not None}


def main(local=False):
    evidence = json.loads((OUT/'evidence.json').read_text())
    require(file_sha(OUT/'codebook.json')==evidence['codebook_sha256'],'Dictionary changed')
    book = json.loads((OUT/'codebook.json').read_text())
    if local:
        require(file_sha(OUT/'expected.parquet')==evidence['expected_sha256'],'Candidate changed')
        actual = pd.read_parquet(OUT/'expected.parquet')
        coverage = evidence['summary']
        geography = None
    else:
        with psycopg.connect(dbname='mda',connect_timeout=5,row_factory=dict_row,
             options='-c default_transaction_read_only=on -c statement_timeout=55000') as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            conn.execute('SET LOCAL ROLE mda_readonly')
            require(conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on','Read-only required')
            actual = pd.DataFrame(conn.execute(f'SELECT * FROM {VIEW}').fetchall())
            coverage = conn.execute(f'SELECT * FROM {COVERAGE} ORDER BY survey_wave,target').fetchall()
            livebook = conn.execute(f'SELECT * FROM {BOOK} ORDER BY survey_wave,target,source_code').fetchall()
            require(livebook==sorted(book,key=lambda r:(r['survey_wave'],r['target'],r['source_code'])),'Database dictionary differs')
            geography = conn.execute(f'SELECT count(*) n FROM {VIEW} v JOIN cses_analysis.cses_person_geography_v2 g USING(survey_wave,household_key,record_key)').fetchone()['n']
            require(geography==212779,'Geography linkage differs')
    require(len(actual)==212779 and not actual.duplicated(KEYS).any(),'Roster grain differs')
    require(not actual.education_isced_equivalence_certified.any(),'Unsupported ISCED certification')
    mapping = {(r['survey_wave'],r['target'],r['source_code']):r for r in book}
    spec = json.loads((ROOT/'rsc/specs/cses_additional_waves_v1.json').read_text())
    counters = defaultdict(Counter)
    statuses = defaultdict(Counter)
    for wave,cfg in spec['waves'].items():
        require(file_sha(ROOT/cfg['archive'])==cfg['sha256'],'Source ZIP changed')
        ef = fields_for(spec,cfg['modules']['ED'])
        agevar = fields_for(spec,cfg['modules']['HL'])['Age Source Value'][0]
        hcols = cfg['household_key']+[cfg['person_key'],agevar]+(['age'] if wave=='2025' else [])
        with zipfile.ZipFile(ROOT/cfg['archive']) as z:
            h = pd.read_stata(io.BytesIO(z.read(cfg['modules']['HL']['member'])),convert_categoricals=False,columns=list(dict.fromkeys(hcols)))
            e = pd.read_stata(io.BytesIO(z.read(cfg['modules']['ED']['member'])),convert_categoricals=False)
        for f in [h,e]:
            f['record_key'] = source_keys(f,cfg['household_key']+[cfg['person_key']],wave)
            f['household_key'] = source_keys(f,cfg['household_key'],wave)
            require(f.record_key.is_unique,'Duplicate raw person key')
        h,e = h.set_index('record_key'),e.set_index('record_key')
        group = actual.loc[actual.survey_wave.eq(wave)]
        require(set(h.index)==set(group.record_key) and set(e.index).issubset(set(h.index)),'Native key mismatch')
        for r in group.itertuples(index=False):
            roster = h.loc[r.record_key]
            linked = r.record_key in e.index
            ed = e.loc[r.record_key] if linked else None
            require(roster.household_key==r.household_key,'Household key mismatch')
            if linked:
                require(ed.household_key==r.household_key,'Education household mismatch')
            def get(target):
                return number(ed[ef[target][0]]) if linked and target in ef else None
            high,level = get('Highest Education Level Source Code'),get('Current Education Level Source Code')
            ever,current = get('Ever Attended School'),get('Currently Attending School')
            age = number(roster['age' if wave=='2025' else agevar])
            minimum = 5 if wave in ['1996','1997','1999'] else 3
            eligible = age>=minimum if age is not None else None
            route,invalid = parent_flags(wave,high,level,ever,current)
            for field,value in {'age_for_school_analysis':age,'school_age_eligible':eligible,'education_record_linked':linked,
                'school_current_native_code':current,'school_ever_native_code':ever,
                'school_current_observed':{1:1,2:0}.get(current),'school_ever_observed':{1:1,2:0}.get(ever),
                'highest_source_code':high,'current_source_code':level,'school_route_conflict':route,'school_invalid_response_code':invalid}.items():
                require(equal(getattr(r,field),value),'Native/context mismatch: '+wave+'/'+field)
            hs,cs = mapping.get((wave,'highest',high)),mapping.get((wave,'current',level))
            expected = decide(wave,eligible,linked,ever,current,high,level,hs,cs)
            for field,value in expected.items():
                require(equal(getattr(r,field),value),'Scalar classification mismatch: '+wave+'/'+field)
            for target,entry,code in [('highest',hs,high),('current',cs,level)]:
                statuses[wave,target][expected[f'{target}_level_status']] += 1
                count = counters[wave,target]
                count['roster_members'] += 1
                count['age_eligible_members'] += bool(eligible)
                applicable = expected[f'{target}_target_applicable']
                family = expected[f'{target}_qualified_family']
                count['target_applicable_members'] += applicable
                count['source_non_null'] += code is not None
                count['qualified_family_records'] += family is not None
                count['qualified_general_grade_records'] += expected[f'{target}_qualified_general_grade'] is not None
                count['unresolved_applicable_records'] += applicable and family is None
                count['derived_never_attended'] += target=='highest' and expected['highest_derived_from_skip']
                count['source_form_renumbered_records'] += entry['source_form_code_differs'] if entry else False
                count['explicit_unknown_responses'] += entry['response_kind']=='unknown' if entry else False
    for row in coverage:
        require(all(row[k]==v for k,v in counters[row['survey_wave'],row['target']].items()),'Independent denominator mismatch')
    result = {'passed':True,'role':None if local else 'mda_readonly','read_only':True,'database_accessed':not local,
        'native_rows_verified':len(actual),'classified_field_records':2*len(actual),'codebook_entries':len(book),
        'native_and_qualified_mismatches':0,'geography_linked':geography,'independent_denominator_rows':len(coverage),
        'validator_sha256':file_sha(Path(__file__)),'expected_sha256':file_sha(OUT/'expected.parquet'),
        'codebook_sha256':file_sha(OUT/'codebook.json')}
    if not local:
        result['published_sha256'] = file_sha(OUT/'published.json')
    put(OUT/('independent-local-checks.json' if local else 'independent-checks.json'),encoded(result))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--local',action='store_true')
    main(p.parse_args().local)
