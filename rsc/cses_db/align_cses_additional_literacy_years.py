#!/usr/bin/env python3
"""Source-preserving literacy and observed school-years qualification for five waves."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
from align_cses_additional_school import KEYS, ROOT, require
from build_cses_additional_waves import encoded, fields_for, metadata_only, parquet_bytes, source_keys
from cache_cses_questionnaires import file_sha, put

VERSION = 'cses-additional-literacy-years-v1'
OUT = ROOT/'data/releases'/VERSION
BASE = ROOT/'data/releases/cses-additional-education-levels-v1'
SCHOOL = ROOT/'data/releases/cses-additional-school-attendance-v1'
RULE = 'cses_alignment.cses_additional_literacy_years_rule_v1'
VIEW = 'cses_analysis.cses_additional_literacy_years_v1'
COVERAGE = 'cses_analysis.cses_additional_literacy_years_coverage_v1'
TARGETS = ['combined','read','write','years']
LABELS = {'combined':'Can Read And Write Combined','read':'Can Read','write':'Can Write',
          'years':'Years Attended School Source Value'}
LEGACY = {'1996','1997','1999'}


def rules(spec, school_rules):
    rows = []
    for old in school_rules:
        wave = old['survey_wave']
        fields = fields_for(spec,spec['waves'][wave]['modules']['ED'])
        for target in TARGETS:
            names = [fields[LABELS[target]][0]] if LABELS[target] in fields else []
            mode = 'observed_years' if target=='years' else 'observed_binary'
            if target=='combined' and wave not in LEGACY:
                names = [fields[LABELS[t]][0] for t in ['read','write']]
                mode = 'derived_both_valid_read_and_write'
            available = bool(names)
            rows.append({'survey_wave':wave,'target':target,'source_variables':names,
                'source_variable_labels':{},'native_value_labels':{},'source_available':available,
                'mode':mode if available else 'not_collected_in_selected_education_source',
                'minimum_age':old['questionnaire_minimum_age'],'maximum_years':30 if target=='years' else None,
                'questionnaire_path':old['questionnaire_path'],'questionnaire_sha256':old['questionnaire_sha256'],
                'questionnaire_locator':{'1996':'Printed page 6, column 28; age 5+',
                    '1997':'PDF page 4, II SCHOOLING Q4 column 4; age 5+',
                    '1999':'II SCHOOLING Q2 column 3; age 5+',
                    '2023':'PDF page 12, columns 2-5; age 3+; enter completed number of years',
                    '2025':'02 Education (2): B3, L10/L16, O10/O16, R10/R16, U10/U17/U26; literal cell cache'}[wave],
                'qualification':('Observed completed years attended only; ever-attended Yes required. Integer 0-30 is an analytical guard, not a printed maximum. Years above source age excluded. Skips stay null, not imputed zero.'
                    if target=='years' else 'Simple message in any language; 1996 also says dialect. Combined legacy answers are never split. Modern combined requires both valid observed binaries, not an independent combined answer. Literacy is not gated by school attendance.'),
                'mapping_version':VERSION})
    return rows


def qualify(frame):
    """Vector logic, separate from SQL and independent scalar acceptance."""
    f = frame.copy(deep=True)
    require(f.survey_wave.isin(LEGACY|{'2023','2025'}).all(),'Unreviewed wave')
    legacy = f.survey_wave.isin(LEGACY)
    for target in TARGETS:
        f[f'{target}_source_available'] = True if target=='combined' else ~legacy
        x = f[f'{target}_source_value']
        status = pd.Series('observed_binary' if target!='years' else 'observed_years',index=f.index,dtype='string')
        if target!='years':
            status.loc[x.isna()] = 'missing_response'
            status.loc[x.notna() & ~x.isin([1,2])] = 'unrecognized_native_binary_code'
            result = x.map({1:1,2:0}).astype('Int64')
            if target=='combined':
                valid = f.read_source_value.isin([1,2]) & f.write_source_value.isin([1,2])
                invalid = ((f.read_source_value.notna() & ~f.read_source_value.isin([1,2])) |
                           (f.write_source_value.notna() & ~f.write_source_value.isin([1,2])))
                status.loc[~legacy] = 'missing_component_response'
                status.loc[~legacy & invalid] = 'unrecognized_component_code'
                status.loc[~legacy & valid] = 'derived_both_valid_read_and_write'
                result.loc[~legacy] = pd.NA
                result.loc[~legacy & valid] = (f.read_source_value.eq(1) & f.write_source_value.eq(1)).astype(int)
        else:
            ever = f.school_ever_native_code
            valid = x.between(0,30) & x.mod(1).eq(0)
            f['years_numeric_guard_failed'] = x.notna() & ~valid
            f['years_exceed_source_age'] = (x.notna() & f.age_for_education_analysis.notna() & x.gt(f.age_for_education_analysis))
            status.loc[x.isna()] = 'missing_years_after_ever_yes'
            status.loc[f.years_exceed_source_age] = 'years_exceed_source_age'
            status.loc[f.years_numeric_guard_failed] = 'outside_integer_0_30_guard'
            status.loc[ever.eq(2) & x.isna()] = 'documented_skip_no_years_value'
            status.loc[ever.eq(2) & x.notna()] = 'years_value_outside_ever_attendance_route'
            status.loc[ever.isna()] = 'ever_attendance_unresolved'
            status.loc[ever.notna() & ~ever.isin([1,2])] = 'unrecognized_ever_attendance_code'
            result = x.where(valid).astype('Int64')
        status.loc[~f.education_record_linked] = 'missing_education_record'
        status.loc[~f.education_age_eligible.fillna(True)] = 'outside_questionnaire_age_range'
        status.loc[f.education_age_eligible.isna()] = 'unknown_age_eligibility'
        status.loc[~f[f'{target}_source_available']] = 'not_collected_in_selected_education_source'
        f[f'{target}_status'] = status
        f[f'{target}_qualified'] = result.where(status.isin(['observed_binary','observed_years','derived_both_valid_read_and_write']))
        f[f'{target}_target_applicable'] = (f[f'{target}_source_available'] & f.education_age_eligible & f.education_record_linked).fillna(False)
    f['years_expected_by_route'] = f.years_target_applicable & f.school_ever_native_code.eq(1).fillna(False)
    f['combined_derived_from_components'] = f.combined_status.eq('derived_both_valid_read_and_write')
    f['write_yes_read_no_warning'] = f.write_source_value.eq(1) & f.read_source_value.eq(2)
    f['literacy_instrument_equivalence_certified'] = False
    f['years_imputation_performed'] = False
    f['literacy_years_release'] = VERSION
    return f


def summary(frame):
    rows = []
    for wave,g in frame.groupby('survey_wave',sort=True):
        for band,mask in [('questionnaire_age_eligible',g.education_age_eligible.fillna(False)),
                          ('ages_15_plus',g.age_for_education_analysis.ge(15))]:
            f = g.loc[mask]
            for target in TARGETS:
                x = f[f'{target}_qualified']
                applicable = f[f'{target}_target_applicable']
                expected = f.years_expected_by_route if target=='years' else applicable
                rows.append({'survey_wave':wave,'age_band':band,'target':target,
                    'source_available':bool(g[f'{target}_source_available'].iloc[0]),'members_in_age_band':len(f),
                    'target_applicable_members':int(applicable.sum()),'expected_response_by_route':int(expected.sum()),
                    'source_non_null':int(f[f'{target}_source_value'].notna().sum()),'qualified_records':int(x.notna().sum()),
                    'qualified_yes':int(x.eq(1).sum()) if target!='years' else None,
                    'qualified_no':int(x.eq(0).sum()) if target!='years' else None,
                    'unresolved_expected_response':int((expected & x.isna()).sum()),
                    'unrecognized_response_records':int(f[f'{target}_status'].str.startswith('unrecognized_').sum()),
                    'derived_combined':int(f.combined_derived_from_components.sum()) if target=='combined' else 0,
                    'documented_years_skips':int(f.years_status.eq('documented_skip_no_years_value').sum()) if target=='years' else 0,
                    'years_age_conflicts':int(f.years_exceed_source_age.sum()) if target=='years' else 0})
    return rows


def build():
    previous = json.loads((BASE/'evidence.json').read_text())
    inputs = {**previous['inputs'],str(Path(__file__).relative_to(ROOT)):file_sha(Path(__file__))}
    for directory in [BASE,SCHOOL]:
        for name in ['evidence.json','expected.parquet','published.json','validated.json','independent-checks.json']:
            inputs[str((directory/name).relative_to(ROOT))] = file_sha(directory/name)
        for name,key in [('validated.json','validated'),('independent-checks.json','passed')]:
            require(json.loads((directory/name).read_text())[key],'Previous release acceptance required')
    for path,sha in inputs.items():
        require(file_sha(ROOT/path)==sha,'Input changed: '+path)
    spec = json.loads((ROOT/'rsc/specs/cses_additional_waves_v1.json').read_text())
    old = json.loads((SCHOOL/'evidence.json').read_text())
    rs = rules(spec,old['rules'])
    parent = pd.read_parquet(SCHOOL/'expected.parquet')
    f = parent[KEYS+['age_for_school_analysis','age_selection_status','questionnaire_minimum_age',
        'school_age_eligible','education_record_linked','school_ever_native_code']].rename(columns={
            'age_for_school_analysis':'age_for_education_analysis','school_age_eligible':'education_age_eligible'})
    manifest_path = ROOT/'data/processing/cses/additional_waves_v1/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    inputs[str(manifest_path.relative_to(ROOT))] = file_sha(manifest_path)
    frames,native = [],[]
    for wave,cfg in spec['waves'].items():
        path = manifest_path.parent/f'tables/{wave}/ED.parquet'
        require(file_sha(path)==manifest['artifacts'][f'tables/{wave}/ED.parquet'],'ED candidate changed')
        inputs[str(path.relative_to(ROOT))] = file_sha(path)
        candidate = pd.read_parquet(path).set_index('Record Key')
        with zipfile.ZipFile(ROOT/cfg['archive']) as z:
            payload = z.read(cfg['modules']['ED']['member'])
        _,metadata = metadata_only(payload)
        raw = pd.read_stata(io.BytesIO(payload),convert_categoricals=False)
        raw['record_key'] = source_keys(raw,cfg['household_key']+[cfg['person_key']],wave)
        raw['household_key'] = source_keys(raw,cfg['household_key'],wave)
        require(raw.record_key.is_unique and set(raw.record_key)==set(candidate.index),'ED native/candidate keys differ')
        x = f.loc[f.survey_wave.eq(wave)].copy()
        require(set(raw.record_key)==set(x.loc[x.education_record_linked,'record_key']),'Native education link differs')
        raw = raw.set_index('record_key')
        require(x.loc[x.education_record_linked,'household_key'].eq(x.loc[x.education_record_linked,'record_key'].map(raw.household_key)).all(),'Native education household mismatch')
        fields = fields_for(spec,cfg['modules']['ED'])
        for target in TARGETS:
            var = fields.get(LABELS[target],[None])[0]
            x[f'{target}_source_value'] = x.record_key.map(raw[var]) if var else float('nan')
            if var:
                pd.testing.assert_series_equal(raw[var].reindex(candidate.index),candidate['source__'+var],check_names=False,check_dtype=False)
        for rule in [r for r in rs if r['survey_wave']==wave]:
            for var in rule['source_variables']:
                info = next(m for m in metadata if m['name']==var)
                rule['source_variable_labels'][var] = info['label']
                rule['native_value_labels'][var] = info['value_labels']
                if rule['target']!='years':
                    require(info['value_labels']==[{'source_value':1,'label':'Yes'},{'source_value':2,'label':'No'}],'Binary dictionary changed')
        frames.append(x)
        native.append({'survey_wave':wave,'native_education_rows':len(raw),'selected_fields_verified':sum(LABELS[t] in fields for t in TARGETS),'mismatches':0})
    result = qualify(pd.concat(frames,ignore_index=True)).sort_values(KEYS).reset_index(drop=True)
    require(len(result)==212779 and not result.duplicated(KEYS).any(),'Roster grain changed')
    put(OUT/'rules.json',encoded(rs))
    put(OUT/'expected.parquet',parquet_bytes(result))
    evidence = {'version':VERSION,'inputs':inputs,'records':len(result),'rules':rs,'native_checks':native,
        'rules_sha256':file_sha(OUT/'rules.json'),'expected_sha256':file_sha(OUT/'expected.parquet'),
        'summary':summary(result),'status_counts':{t:{w:{str(k):int(v) for k,v in g[f'{t}_status'].value_counts().items()}
            for w,g in result.groupby('survey_wave')} for t in TARGETS},
        'policy':'Combined legacy versus derived modern literacy remains distinct; observed years only, no skip/grade/degree imputation. Age and route diagnostics are explicit.'}
    put(OUT/'evidence.json',encoded(evidence))
    return evidence


if __name__=='__main__':
    e = build()
    print(json.dumps({k:e[k] for k in ['records','summary','status_counts']},indent=2))
