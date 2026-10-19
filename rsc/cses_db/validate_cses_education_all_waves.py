#!/usr/bin/env python3
"""Independent scalar and optional read-only database acceptance of the local pilot."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import psycopg
from align_cses_additional_school import KEYS, ROOT, require
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put
from cses_hh_hl_common import snake_case
from pilot_cses_education_all_waves import NEW_DIRS, OLD_FIELDS, OUT, TARGETS
from psycopg import sql
from psycopg.rows import dict_row


def number(x):
    return None if pd.isna(x) else float(x)


def equal(a,b):
    return (pd.isna(a) and b is None) or (pd.notna(a) and a==b)


def decide(r,h,c):
    """Scalar implementation independent of the vector classifier."""
    values = {t:number(getattr(r,t+'_native')) for t in TARGETS}
    ever,current = values['ever'],values['attendance']
    invalid_e = ever is not None and ever not in [1,2]
    invalid_c = current is not None and current not in [1,2]
    hh = values['highest'] is not None and (h is None or h['kind'] not in ['none','unknown'])
    ch = values['current'] is not None and (c is None or c['kind'] not in ['none','unknown'])
    never_conflict = ever==2 and (current==1 or hh or ch)
    not_current_conflict = current==2 and ch
    age,minimum = number(r.age_for_analysis),number(r.minimum_age)
    eligible = None if age is None or minimum is None else age>=minimum
    age_conflict = values['years'] is not None and age is not None and values['years']>age
    out = {'age_eligible':eligible,'never_attended_route_conflict':never_conflict,
        'not_attending_with_current_level_warning':not_current_conflict,'years_exceed_source_age':age_conflict,
        'years_imputed':False,'cross_wave_equivalence_certified':False}
    for t,x in values.items():
        q,grade = None,None
        status = 'observed' if x is not None else 'missing_response'
        entry = h if t=='highest' else c
        if t in ['highest','current']:
            if x is not None and entry is None:
                status = 'unrecognized_level_code'
            elif entry and entry['kind']=='unknown':
                status = 'explicit_unknown_response'
            if t=='highest':
                if x is None and ever==2:
                    status = 'derived_never_attended'
                if never_conflict:
                    status = 'never_attended_route_conflict'
                if invalid_e:
                    status = 'unrecognized_ever_code'
            else:
                if entry and entry['kind']=='none':
                    status = 'none_not_a_current_level'
                if current==2:
                    status = 'current_level_outside_route' if x is not None else 'not_currently_attending'
                if current is None:
                    status = 'current_attendance_unresolved'
                if ever==2 and current==1:
                    status = 'never_attended_route_conflict'
                if invalid_e or invalid_c:
                    status = 'unrecognized_attendance_code'
            if status=='observed':
                q,grade = entry['family'],entry['grade']
            elif status=='derived_never_attended':
                q = 'never_attended'
        elif t=='years':
            if x is not None and age_conflict:
                status = 'years_exceed_source_age'
            if x is not None and not (0<=x<=30 and x==int(x)):
                status = 'outside_integer_0_30_guard'
            if ever==2:
                status = 'documented_skip_no_years_value' if x is None else 'years_value_outside_route'
            if ever is None:
                status = 'ever_attendance_unresolved'
            if invalid_e:
                status = 'unrecognized_ever_code'
            if status=='observed':
                q = int(x)
        else:
            q = {1:1,2:0}.get(x)
            if x is not None and x not in [1,2]:
                status = 'unrecognized_binary_code'
            if t=='combined' and r.combined_mode=='derived_components':
                read,write = values['read'],values['write']
                if any(v is not None and v not in [1,2] for v in [read,write]):
                    status = 'unrecognized_component_code'
                elif read is None or write is None:
                    status = 'missing_component_response'
                else:
                    status,q = 'derived_components',int(read==1 and write==1)
            if t=='attendance':
                if r.skip_supported and ever==2 and current is None:
                    status,q = 'derived_documented_skip_no',0
                if never_conflict or not_current_conflict:
                    status = 'attendance_route_conflict'
                if invalid_e or invalid_c:
                    status = 'unrecognized_attendance_code'
        if not getattr(r,t+'_available'):
            status = 'not_collected_in_selected_source'
        elif not r.form_scope_reviewed:
            status = 'unverified_same_wave_form_scope'
        elif eligible is None:
            status = 'unknown_age_eligibility'
        elif not eligible:
            status = 'outside_questionnaire_age_range'
        elif not r.education_linked:
            status = 'missing_education_record'
        if status not in ['observed','derived_components','derived_documented_skip_no','derived_never_attended']:
            q,grade = None,None
        applicable = bool(getattr(r,t+'_available') and eligible and r.education_linked)
        out.update({t+'_status':status,t+'_qualified':q,t+'_applicable':applicable,
            t+'_expected_by_route':applicable and (ever==1 if t=='years' else current==1 if t=='current' else True)})
        if t in ['highest','current']:
            out[t+'_general_grade'] = grade
    out['combined_derived'] = out['combined_status']=='derived_components'
    return out


def scalar_acceptance(frame,report,book):
    lookup = {(r['survey_wave'],r['target'],r['source_code']):r for r in book}
    counters = defaultdict(Counter)
    for r in frame.itertuples(index=False):
        expected = decide(r,lookup.get((r.survey_wave,'highest',number(r.highest_native))),
                          lookup.get((r.survey_wave,'current',number(r.current_native))))
        for k,v in expected.items():
            require(equal(getattr(r,k),v),'Scalar mismatch: '+r.survey_wave+'/'+k)
        age = number(r.age_for_analysis)
        for band,inband in [('questionnaire_universe',expected['age_eligible']),
            ('ages_6_17',age is not None and 6<=age<=17),('ages_15_plus',age is not None and age>=15)]:
            if not inband:
                continue
            for t in TARGETS:
                count = counters[r.survey_wave,band,t]
                value = expected[t+'_qualified']
                gate = expected[t+'_expected_by_route']
                count['age_band_members'] += 1
                count['expected_by_route'] += gate
                count['raw_non_null'] += number(getattr(r,t+'_native')) is not None
                count['qualified_records'] += value is not None
                count['unresolved_expected'] += gate and value is None
                if t not in ['highest','current','years']:
                    count['qualified_yes'] += value==1
                    count['qualified_no'] += value==0
    require(len(report['coverage'])==360,'Coverage row count changed')
    for row in report['coverage']:
        key = row['survey_wave'],row['age_band'],row['target']
        counter = counters[key]
        require(all(row[k]==v for k,v in counter.items()),'Independent denominator mismatch: '+str(key))
        if not row['form_scope_reviewed'] and row['age_band']=='questionnaire_universe':
            require(row['age_band_members'] is None,'Unverified universe cannot become zero people')
    return {'classified_field_records':len(frame)*len(TARGETS),'scalar_mismatches':0,'denominator_rows':360}


def database_acceptance(frame):
    """SELECT/SET only; never create, replace, register or publish a relation."""
    checks = {}
    with psycopg.connect(dbname='mda',connect_timeout=5,row_factory=dict_row,
         options='-c default_transaction_read_only=on -c statement_timeout=55000') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute('SET LOCAL ROLE mda_readonly')
        require(conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on','Read-only required')
        old_hl = pd.read_parquet(ROOT/'data/processing/cses/final_HL_CSES.parquet').rename(columns=snake_case)
        old_ed = pd.read_parquet(ROOT/'data/processing/cses/education_corrected_v1/final_ED_CSES.parquet')
        for relation,expected,columns,key in [('cses_analysis.cses_hl_age_v1',old_hl,
            ['survey_wave','person_id','household_id','age','source_row_id'],['survey_wave','person_id']),
            ('cses_analysis.cses_ed_aligned_v1',old_ed,['survey_wave','person_id','household_id','source_row_id',
             *OLD_FIELDS.values(),'education_level_harmonized','current_education_level_harmonized',
             'current_level_before_correction','current_level_correction_version','current_level_evidence_status'],['survey_wave','person_id'])]:
            query = sql.SQL('SELECT {} FROM {}').format(sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier(*relation.split('.')))
            actual = pd.DataFrame(conn.execute(query).fetchall()).astype(expected[columns].dtypes.to_dict())
            pd.testing.assert_frame_equal(actual.sort_values(key).reset_index(drop=True),expected[columns].sort_values(key).reset_index(drop=True),check_exact=True)
            checks[relation] = {'rows':len(actual),'columns_verified':len(columns),'mismatches':0}
        relations = {'attendance':('cses_analysis.cses_additional_school_attendance_v1',['school_attendance_qualified','school_current_native_code','school_ever_native_code','age_for_school_analysis']),
            'levels':('cses_analysis.cses_additional_education_levels_v1',['highest_qualified_family','current_qualified_family','highest_qualified_general_grade','current_qualified_general_grade']),
            'literacy':('cses_analysis.cses_additional_literacy_years_v1',['combined_qualified','read_qualified','write_qualified','years_qualified'])}
        for kind,(relation,cols) in relations.items():
            expected = pd.read_parquet(ROOT/NEW_DIRS[kind]/'expected.parquet')[KEYS+cols]
            actual = pd.DataFrame(conn.execute(sql.SQL('SELECT {} FROM {}').format(sql.SQL(',').join(map(sql.Identifier,KEYS+cols)),sql.Identifier(*relation.split('.')))).fetchall()).astype(expected.dtypes.to_dict())
            pd.testing.assert_frame_equal(actual.sort_values(KEYS).reset_index(drop=True),expected.sort_values(KEYS).reset_index(drop=True),check_exact=True)
            checks[relation] = {'rows':len(actual),'columns_verified':len(expected.columns),'mismatches':0}
        geo = pd.DataFrame(conn.execute('SELECT survey_wave,household_key,record_key FROM cses_analysis.cses_person_geography_v2').fetchall())
        require(len(geo)==571699 and not geo.duplicated(KEYS).any(),'Geography grain differs')
        joined = frame[KEYS].merge(geo,on=KEYS,how='outer',validate='one_to_one',indicator=True)
        require(joined['_merge'].eq('both').all(),'Geography linkage lost or multiplied')
        counts = conn.execute('SELECT survey_wave,count(*) n FROM cses_analysis.cses_person_geography_v2 GROUP BY survey_wave').fetchall()
        require({r['survey_wave']:r['n'] for r in counts}==frame.groupby('survey_wave').size().to_dict(),'Wave denominators differ')
    return {'role':'mda_readonly','transaction_read_only':True,'database_modified':False,
        'source_interface_checks':checks,'geography_linked':len(geo),'geography_mismatches':0}


def main(database=False):
    report = json.loads((OUT/'report.json').read_text())
    for p,sha in report['inputs'].items():
        require(file_sha(ROOT/p)==sha,'Pinned input changed: '+p)
    for p,sha in report['artifacts'].items():
        require(file_sha(OUT/p)==sha,'Pilot artifact changed: '+p)
    f = pd.read_parquet(OUT/'members.parquet')
    book = json.loads((OUT/'level_codebook.json').read_text())
    matrix = json.loads((OUT/'matrix.json').read_text())
    require(len(f)==571699 and f[KEYS].notna().all().all() and not f.duplicated(KEYS).any(),'Roster grain differs')
    require(len(matrix)==120 and len({(r['survey_wave'],r['target']) for r in matrix})==120,'Matrix grain differs')
    for r in matrix:
        g = f.loc[f.survey_wave.eq(r['survey_wave'])]
        t = r['target']
        require(r['source_available']==bool(g[t+'_available'].iloc[0]) and
            r['qualified_records']==int(g[t+'_qualified'].notna().sum()),'Matrix counts differ')
    result = {'passed':True,'database_modified':False,'database_accessed':database,'roster_records':len(f),
        'matrix_rows':len(matrix),'orphan_records_preserved':len(pd.read_parquet(OUT/'orphan_education.parquet')),
        **scalar_acceptance(f,report,book),'validator_sha256':file_sha(Path(__file__)),
        'report_sha256':file_sha(OUT/'report.json')}
    if database:
        result['database'] = database_acceptance(f)
    put(OUT/('database-validation.json' if database else 'local-validation.json'),encoded(result))
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',action='store_true')
    main(p.parse_args().database)
