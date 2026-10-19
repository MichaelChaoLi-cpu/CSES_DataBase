#!/usr/bin/env python3
"""Read-only five-wave sex/age/school pilot; local aggregate evidence only."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import psycopg
from build_cses_additional_waves import encoded, source_keys
from cache_cses_questionnaires import file_sha, put
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/processing/cses/alignment_pilot_v1'
QUERY = '''SELECT p.survey_wave,p.household_key,p.record_key,p.sex,p.age_source_value,
    p.age_topcoded_qualified,p.source_values AS roster_native,
    e.record_key IS NOT NULL AS education_linked,e.currently_attending_school,
    e.ever_attended_school,e.source_values AS education_native
    FROM cses_data.cses_additional_hl_v1 p
    LEFT JOIN cses_data.cses_additional_ed_v1 e USING(survey_wave,record_key,household_key)
    ORDER BY p.survey_wave COLLATE "C",p.record_key COLLATE "C"'''


def number(value):
    return None if pd.isna(value) else float(value)


def school_summary(frame):
    """No recoding of unknowns; inferred-never scenario is explicitly sensitivity-only."""
    current = frame.currently_attending_school
    yes = int(current.eq(1).sum())
    no = int(current.eq(0).sum())
    missing = int(current.isna().sum())
    skipped_never = int((current.isna() & frame.ever_attended_school.eq(0)).sum())
    n = len(frame)
    if yes + no + missing != n:
        raise ValueError('Unexpected standardized school code')
    def pct(numerator,denominator):
        return round(100*numerator/denominator,4) if denominator else None
    return {'records':n,'education_linked':int(frame.education_linked.sum()),
            'yes':yes,'no':no,'missing':missing,'missing_with_never_attended':skipped_never,
            'other_missing':missing-skipped_never,
            'ever_no_current_yes_conflicts':int((current.eq(1)&frame.ever_attended_school.eq(0)).sum()),
            'observed_response_yes_pct':pct(yes,yes+no),
            'all_person_lower_bound_pct':pct(yes,n),'all_person_upper_bound_pct':pct(yes+missing,n),
            'sensitivity_never_skip_as_no_pct':pct(yes,yes+no+skipped_never)}


def age_summary(age):
    valid = age.notna()
    return {'non_null':int(valid.sum()),'missing':int((~valid).sum()),
            'min':number(age.min()),'max':number(age.max()),
            'noninteger_or_outside_0_120':int((valid&(~age.between(0,120)|age.mod(1).ne(0))).sum()),
            'value_98':int(age.eq(98).sum()),'value_99':int(age.eq(99).sum()),
            'median':number(age.median())}


def equality_errors(raw,target):
    same = raw.eq(target) | (raw.isna() & target.isna())
    return int((~same).sum())


def main():
    spec_path = ROOT/'rsc/specs/cses_additional_waves_v1.json'
    spec = json.loads(spec_path.read_text())
    ledger_path = ROOT/'data/processing/cses/additional_waves_v1/field_alignment.json'
    ledger = json.loads(ledger_path.read_text())
    with psycopg.connect(dbname='mda',row_factory=dict_row,connect_timeout=5,
                         options='-c default_transaction_read_only=on -c statement_timeout=55000') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute('SET LOCAL ROLE mda_readonly')
        if conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only'] != 'on':
            raise ValueError('Read-only transaction required')
        frame = pd.DataFrame(conn.execute(QUERY).fetchall())
    if len(frame) != 212779 or frame.duplicated(['survey_wave','record_key']).any():
        raise ValueError('Join multiplied or lost roster records')
    snapshot_sha = hashlib.sha256(frame.to_json(orient='records').encode()).hexdigest()
    # Inspect, but never publish or overwrite, the native Survey Solutions calculated age.
    cfg = spec['waves']['2025']
    archive = ROOT/cfg['archive']
    if file_sha(archive) != cfg['sha256']:
        raise ValueError('2025 source archive changed')
    member = cfg['modules']['HL']['member']
    with zipfile.ZipFile(archive) as z:
        raw = pd.read_stata(io.BytesIO(z.read(member)),convert_categoricals=False,
                            columns=cfg['household_key']+[cfg['person_key'],'q01ac05a','age'])
    raw['record_key'] = source_keys(raw,cfg['household_key']+[cfg['person_key']],'2025')
    db25 = frame.loc[frame.survey_wave.eq('2025')]
    if raw.record_key.duplicated().any() or set(raw.record_key) != set(db25.record_key):
        raise ValueError('2025 calculated-age join is not one-to-one')
    overlap = raw.q01ac05a.notna()&raw.age.notna()
    age_candidate = {'member':member,'source_field':'age','source_label':'Calculated age',
                     **age_summary(raw.age),'manual_overlap':int(overlap.sum()),
                     'manual_disagreements':int(raw.loc[overlap,'q01ac05a'].ne(raw.loc[overlap,'age']).sum()),
                     'state':'local_sensitivity_only_not_published_not_algorithm_certified'}
    frame['pilot_age'] = frame.age_source_value.copy()
    frame.loc[frame.survey_wave.eq('2025'),'pilot_age'] = db25.record_key.map(raw.set_index('record_key').age)
    result = {'version':'cses-alignment-pilot-v1','database_modified':False,'read_role':'mda_readonly',
              'sql':QUERY,'input_snapshot_sha256':snapshot_sha,'script_sha256':file_sha(Path(__file__)),
              'spec_sha256':file_sha(spec_path),'mapping_sha256':file_sha(ledger_path),
              'source_2025_sha256':cfg['sha256'],'age_2025_candidate':age_candidate,'waves':{},
              'limitations':['All frequencies are unweighted sample descriptions, not population estimates.',
                'Distribution similarity does not certify comparability; differences do not establish an error.',
                'The 6–17 restriction is an experimental common-age band, not a verified common question universe.',
                'Never-attended skip as No is a sensitivity scenario, not a database correction.',
                '2025 pilot ages come from native calculated age; formula and full interview-date validity are not certified.',
                'Upper-age codes outside the reviewed 1996/1999 cases remain qualified.']}
    for wave,g in frame.groupby('survey_wave',sort=True):
        raw_errors = {}
        for module,target,column,container in [('HL','Sex','sex','roster_native'),
                                               ('HL','Age Source Value','age_source_value','roster_native'),
                                               ('ED','Currently Attending School','currently_attending_school','education_native')]:
            mapping = next(r for r in ledger if r['wave']==wave and r['module']==module and r['target']==target)
            native = pd.to_numeric(g[container].map(lambda d:d.get(mapping['source_variable']) if isinstance(d,dict) else None),errors='raise')
            expected = native.map({1:1,2:0}) if module=='ED' else native
            raw_errors[target] = equality_errors(expected,g[column])
        if any(raw_errors.values()):
            raise ValueError('Published recode mismatch: '+wave)
        bands = {}
        for lower,upper in [(6,17),(10,14)]:
            bands[f'{lower}_{upper}_as_published'] = school_summary(g[g.age_source_value.between(lower,upper)])
            bands[f'{lower}_{upper}_pilot_age'] = school_summary(g[g.pilot_age.between(lower,upper)])
        result['waves'][wave] = {'records':len(g),'sex_counts':{str(k):int(v) for k,v in g.sex.value_counts(dropna=False).items()},
            'female_pct':round(100*g.sex.eq(2).mean(),4),'sex_missing':int(g.sex.isna().sum()),
            'sex_invalid':int((g.sex.notna()&~g.sex.isin([1,2])).sum()),'age_as_published':age_summary(g.age_source_value),
            'school_all_roster':school_summary(g),'school_age_bands':bands,'native_recode_mismatches':raw_errors,
            'school_by_single_pilot_age':{str(age):school_summary(g[g.pilot_age.eq(age)]) for age in range(6,18)}}
    put(OUT/'summary.json',encoded(result))
    print(json.dumps({'age_2025_candidate':age_candidate,'waves':{w:{k:v[k] for k in ['records','female_pct','age_as_published','school_age_bands']} for w,v in result['waves'].items()}},indent=2))


if __name__ == '__main__':
    main()
