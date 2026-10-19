#!/usr/bin/env python3
"""Retain the first pilot and add a positive-years/never-attended inference guard."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from align_cses_additional_school import KEYS, ROOT, require
from build_cses_additional_waves import encoded, parquet_bytes
from cache_cses_questionnaires import file_sha, put
from pilot_cses_education_all_waves import EXTRA, NEW_DIRS, TARGETS, coverage
from pilot_cses_education_all_waves import OUT as FIRST
from pilot_cses_education_all_waves import qualify as first_qualify

OUT = ROOT/'data/processing/cses/education_all_waves_pilot_v2'
VERSION = 'cses-education-all-waves-pilot-v2'


def qualify(frame):
    f = first_qualify(frame)
    conflict = f.ever_native.eq(2) & f.years_native.gt(0)
    f['never_attended_positive_years_warning'] = conflict
    # 2017 diagnostics remain provisional; its strict values already stay null.
    guard = conflict & f.form_scope_reviewed & f.age_eligible.fillna(False) & f.education_linked
    f['never_attended_route_conflict'] = f.never_attended_route_conflict | conflict
    for t in ['attendance','highest']:
        exclude = guard & f[t+'_qualified'].notna()
        f.loc[exclude,t+'_status'] = 'never_attended_positive_years_conflict'
        f.loc[exclude,t+'_qualified'] = pd.NA
        if t=='highest':
            f.loc[exclude,'highest_general_grade'] = pd.NA
    return f


def build():
    original = json.loads((FIRST/'report.json').read_text())
    for p,sha in original['inputs'].items():
        require(file_sha(ROOT/p)==sha,'First-pilot input changed: '+p)
    for p,sha in original['artifacts'].items():
        require(file_sha(FIRST/p)==sha,'First-pilot artifact changed: '+p)
    prior = json.loads((FIRST/'database-validation.json').read_text())
    require(prior['passed'] and not prior['database_modified'],'First-pilot read-only acceptance required')
    require(prior['report_sha256']==file_sha(FIRST/'report.json'),'First report differs from acceptance')
    inputs = dict(original['inputs'])
    for path in [FIRST/'report.json',FIRST/'database-validation.json',*[FIRST/n for n in original['artifacts']],
                 Path(__file__),ROOT/'rsc/cses_db/validate_cses_education_all_waves.py',
                 ROOT/'rsc/cses_db/validate_cses_education_all_waves_v2.py']:
        inputs[str(path.relative_to(ROOT))] = file_sha(path)
    require(prior['validator_sha256']==inputs['rsc/cses_db/validate_cses_education_all_waves.py'],'First validator changed')
    before = pd.read_parquet(FIRST/'members.parquet')
    f = qualify(before)
    changes = {}
    for t in TARGETS:
        equal = f[t+'_qualified'].eq(before[t+'_qualified']).fillna(False) | (f[t+'_qualified'].isna() & before[t+'_qualified'].isna())
        changed = ~equal
        changes[t] = {'changed_records':int(changed.sum()),
            'by_wave':{str(w):int(n) for w,n in f.loc[changed].groupby('survey_wave').size().items()}}
        if changed.any():
            require(t in ['attendance','highest'] and f.loc[changed,t+'_qualified'].isna().all() and
                f.loc[changed,'never_attended_positive_years_warning'].all(),'Unintended prototype change')
    require(len(f)==571699 and not f.duplicated(KEYS).any(),'Roster grain changed')
    # Previously published five-wave results must remain exactly preserved.
    preserved = []
    for t,kind,column in [('attendance','attendance','school_attendance_qualified'),
        ('highest','levels','highest_qualified_family'),('current','levels','current_qualified_family'),
        *[(t,'literacy',t+'_qualified') for t in ['combined','read','write','years']]]:
        expected = pd.read_parquet(ROOT/NEW_DIRS[kind]/'expected.parquet').set_index(KEYS)[column]
        actual = f.loc[f.survey_wave.isin(EXTRA)].set_index(KEYS)[t+'_qualified'].reindex(expected.index)
        same = actual.eq(expected).fillna(False) | (actual.isna() & expected.isna())
        require(same.all(),'Published five-wave value differs: '+t)
        preserved.append({'target':t,'records':len(actual),'mismatches':0})
    matrix = json.loads((FIRST/'matrix.json').read_text())
    for row in matrix:
        g = f.loc[f.survey_wave.eq(row['survey_wave'])]
        t = row['target']
        row['qualified_records'] = int(g[t+'_qualified'].notna().sum())
        row['unresolved_expected'] = int((g[t+'_expected_by_route'] & g[t+'_qualified'].isna()).sum())
    for name,payload in [('members.parquet',parquet_bytes(f)),('matrix.json',encoded(matrix)),
        ('level_codebook.json',(FIRST/'level_codebook.json').read_bytes()),
        ('orphan_education.parquet',(FIRST/'orphan_education.parquet').read_bytes())]:
        put(OUT/name,payload)
    report = {**original,'version':VERSION,'inputs':inputs,'database_modified':False,'prototype_not_published':True,
        'supersedes_report_sha256':file_sha(FIRST/'report.json'),'correction':{
            'policy':'No derived/usable attendance or highest attainment when recorded positive years conflict with ever-attended No. Source values and first pilot retained.',
            'changed_qualified_fields':changes,
            'warning_records_all_waves_including_unverified_2017':int(f.never_attended_positive_years_warning.sum()),
            'warning_records_reviewed_form_scope':int((f.never_attended_positive_years_warning & f.form_scope_reviewed).sum())},
        'accepted_extra_wave_preservation':preserved,'coverage':coverage(f),
        'status_counts':{t:{w:{str(k):int(v) for k,v in g[t+'_status'].value_counts().items()} for w,g in f.groupby('survey_wave')} for t in TARGETS},
        'artifacts':{n:file_sha(OUT/n) for n in ['members.parquet','orphan_education.parquet','matrix.json','level_codebook.json']}}
    put(OUT/'report.json',encoded(report))
    print(json.dumps({k:report[k] for k in ['roster_members','matrix_rows','orphan_rows','correction','accepted_extra_wave_preservation']},indent=2))
    return report


if __name__=='__main__':
    build()
