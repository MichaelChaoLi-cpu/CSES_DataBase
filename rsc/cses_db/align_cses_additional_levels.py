#!/usr/bin/env python3
"""Keep highest attainment and current study separate, with literal code provenance."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
from align_cses_additional_school import KEYS, ROOT, require
from build_cses_additional_waves import encoded, fields_for, metadata_only, parquet_bytes, source_keys
from cache_cses_questionnaires import file_sha, put

VERSION = 'cses-additional-education-levels-v1'
OUT = ROOT/'data/releases'/VERSION
BASE = ROOT/'data/releases/cses-additional-school-attendance-v1'
BOOK = 'cses_alignment.cses_additional_education_level_codebook_v1'
VIEW = 'cses_analysis.cses_additional_education_levels_v1'
COVERAGE = 'cses_analysis.cses_additional_education_level_coverage_v1'
TARGETS = {'highest':'Highest Education Level Source Code','current':'Current Education Level Source Code'}


def definitions_for(wave, target):
    """Explicit meanings, not a numeric ladder or a purported ISCED crosswalk."""
    require(wave in {'1996','1997','1999','2023','2025'} and target in TARGETS,'Unreviewed wave or target')
    rows = {}
    def add(code, family, kind='value', grade=None, form_code=None, meaning=None, note=''):
        rows[code] = {'semantic_family':family,'response_kind':kind,'general_grade':grade,
            'questionnaire_code':code if form_code is None else form_code,
            'questionnaire_meaning':meaning or family.replace('_',' '), 'qualification':note}
    maximum = 11 if wave=='1996' else 12
    if wave=='1996' and target=='current':
        return rows
    for grade in range(1,maximum+1):
        add(grade,'general_school_grade',grade=grade,meaning=f'Class {grade}',
            note='Named ordinary grade only; not completed years attended, an ISCED level or a credential equivalence.')
    if wave=='1996':
        add(0,'never_attended','none')
        add(12,'secondary_certificate_unspecified',note='Not literal Class 12; secondary school certificate/diploma, subtype unresolved.')
        add(13,'vocational_bst_os_undergraduate',note='BST/OS level and equivalence not established.')
        add(14,'vocational_bst_os_graduate',note='BST/OS level and equivalence not established.')
        add(15,'university_undergraduate',note='Undergraduate is not a certified awarded university degree.')
        add(16,'university_degree_unspecified',note='Graduate/degree holder does not identify Bachelor versus another degree.')
        add(17,'postgraduate_unspecified',note='Do not split into Masters and Doctorate.')
        add(88,'no_grade_completed','none')
        add(99,None,'unknown',meaning='Not reported or unknown')
    elif wave in {'1997','1999'}:
        if wave=='1997':
            add(0,'none_unspecified','none',note='None does not independently distinguish never attended from no class completed.')
        else:
            add(0,'preschool_kindergarten')
            add(99,'none_unspecified','none',note='Printed and native None, NOT an unknown-response code.')
        add(13,'secondary_certificate_unspecified',note='Do not force into lower versus upper secondary certificate.')
        add(14,'technical_vocational_pre_secondary')
        add(15,'technical_vocational_post_secondary')
        add(16,'university_undergraduate',note='No awarded-degree inference.')
        add(17,'university_degree_unspecified',note='Exact degree not stated; current study is not a degree already held.')
        add(18,'postgraduate_unspecified',note='Do not split into Masters and Doctorate.')
        add(19,'other_unspecified','other')
    else:
        require(wave in {'2023','2025'},'Unreviewed wave')
        add(0,'preschool_kindergarten')
        add(15,'technical_vocational_pre_secondary')
        add(16,'technical_vocational_post_secondary')
        add(17,'university_undergraduate',note='Highest question explicitly says no degree; current question describes study, not an award.')
        if target=='highest':
            add(13,'lower_secondary_certificate')
            add(14,'upper_secondary_certificate')
            add(18,'bachelor')
            add(19,'masters')
            add(20,'doctorate')
            add(88,'no_grade_completed','none')
            add(98 if wave=='2023' else -98,None,'unknown',form_code=98,meaning='Do not know',
                note='2025 native -98 corresponds in meaning to printed 98; retain native code.')
            add(21 if wave=='2023' else 96,'other_unspecified','other',form_code=21,
                note='2025 native 96 is labeled Other; printed 21 is Other. Label-supported meaning, not a certified electronic code crosswalk.')
        else:
            add(18,'masters',note='Current Masters programme, NOT Bachelor or evidence of a degree held.')
            add(19,'doctorate',note='Current Doctorate programme, not a degree already held.')
            add(20 if wave=='2023' else 96,'other_unspecified','other',form_code=20,
                note='2025 native 96 is labeled Other; printed 20 is Other. Preserve both codes.')
    return rows


def qualify(frame, book):
    f = frame.copy(deep=True)
    for target in TARGETS:
        for name in ['semantic_family','response_kind','general_grade','native_value_label','source_form_code_differs']:
            mapping = {(r['survey_wave'],r['source_code']):r[name] for r in book if r['target']==target}
            f[f'{target}_source_{name}'] = [mapping.get((w,c)) for w,c in zip(f.survey_wave,f[f'{target}_source_code'],strict=True)]
    high, current = f.highest_source_code, f.current_source_code
    ever, attend = f.school_ever_observed, f.school_current_observed
    invalid_ever = f.school_ever_native_code.notna() & ~f.school_ever_native_code.isin([1,2])
    invalid_current = f.school_current_native_code.notna() & ~f.school_current_native_code.isin([1,2])
    high_hint = high.notna() & ~f.highest_source_response_kind.isin(['none','unknown'])
    current_hint = current.notna() & ~f.current_source_response_kind.isin(['none','unknown'])
    gate_conflict = (ever.eq(0) & (attend.eq(1) | high_hint | current_hint)).fillna(False)
    f['highest_other_item_warning'] = f.school_route_conflict | f.school_invalid_response_code
    hs = pd.Series('observed_highest',index=f.index,dtype='string')
    hs.loc[f.highest_other_item_warning] = 'observed_highest_other_item_warning'
    hs.loc[ever.isna() & f.survey_wave.ne('1996')] = 'observed_highest_gate_missing'
    hs.loc[high.isna()] = 'missing_highest_gate_unresolved'
    hs.loc[high.isna() & ever.eq(1).fillna(False)] = 'missing_highest_after_ever_yes'
    hs.loc[high.isna() & ever.eq(0).fillna(False) & ~gate_conflict] = 'derived_never_attended_from_documented_skip'
    hs.loc[high.notna() & f.highest_source_response_kind.isna()] = 'unrecognized_highest_code'
    hs.loc[f.highest_source_response_kind.eq('unknown')] = 'explicit_unknown_highest'
    hs.loc[gate_conflict] = 'never_attended_route_conflict'
    hs.loc[invalid_ever] = 'unrecognized_ever_attendance_code'
    hs.loc[~f.education_record_linked] = 'missing_education_record'
    hs.loc[~f.school_age_eligible.fillna(True)] = 'outside_questionnaire_age_range'
    hs.loc[f.school_age_eligible.isna()] = 'unknown_age_eligibility'
    f['highest_level_status'] = hs
    usable_h = hs.str.startswith('observed_highest')
    f['highest_qualified_family'] = f.highest_source_semantic_family.where(usable_h)
    derived = hs.eq('derived_never_attended_from_documented_skip')
    f.loc[derived,'highest_qualified_family'] = 'never_attended'
    f['highest_qualified_general_grade'] = pd.to_numeric(f.highest_source_general_grade).where(usable_h).astype('Int64')
    f['highest_derived_from_skip'] = derived
    cs = pd.Series('observed_current_level',index=f.index,dtype='string')
    cs.loc[current.isna()] = 'missing_current_level_after_yes'
    cs.loc[f.current_source_response_kind.eq('none')] = 'none_not_a_current_level'
    cs.loc[f.current_source_response_kind.eq('unknown')] = 'explicit_unknown_current_level'
    cs.loc[current.notna() & f.current_source_response_kind.isna()] = 'unrecognized_current_level_code'
    cs.loc[attend.eq(0).fillna(False)] = 'not_currently_attending'
    cs.loc[attend.eq(0).fillna(False) & current.notna()] = 'current_code_outside_attendance_route'
    cs.loc[attend.isna()] = 'current_attendance_unresolved'
    cs.loc[(ever.eq(0) & attend.eq(1)).fillna(False)] = 'never_attended_route_conflict'
    cs.loc[invalid_ever | invalid_current] = 'unrecognized_attendance_gate_code'
    cs.loc[~f.education_record_linked] = 'missing_education_record'
    cs.loc[~f.school_age_eligible.fillna(True)] = 'outside_questionnaire_age_range'
    cs.loc[f.school_age_eligible.isna()] = 'unknown_age_eligibility'
    cs.loc[f.survey_wave.eq('1996')] = 'not_collected_in_selected_education_source'
    f['current_level_status'] = cs
    usable_c = cs.eq('observed_current_level')
    f['current_qualified_family'] = f.current_source_semantic_family.where(usable_c)
    f['current_qualified_general_grade'] = pd.to_numeric(f.current_source_general_grade).where(usable_c).astype('Int64')
    f['highest_target_applicable'] = (f.school_age_eligible & f.education_record_linked).fillna(False)
    f['current_target_available'] = f.survey_wave.ne('1996')
    f['current_target_applicable'] = (f.current_target_available & f.highest_target_applicable & attend.eq(1)).fillna(False)
    for target in TARGETS:
        f[f'{target}_family_usable'] = f[f'{target}_qualified_family'].notna()
        for c in ['semantic_family','response_kind','native_value_label']:
            f[f'{target}_source_{c}'] = f[f'{target}_source_{c}'].astype('string')
        f[f'{target}_source_general_grade'] = pd.to_numeric(f[f'{target}_source_general_grade']).astype('Int64')
        f[f'{target}_source_form_code_differs'] = f.pop(f'{target}_source_source_form_code_differs').fillna(False).astype(bool)
        f[f'{target}_qualified_family'] = f[f'{target}_qualified_family'].astype('string')
    f['education_isced_equivalence_certified'] = False
    f['education_levels_release'] = VERSION
    return f


def summary(f):
    rows = []
    for wave,g in f.groupby('survey_wave',sort=True):
        for target in TARGETS:
            applicable = g[f'{target}_target_applicable']
            family = g[f'{target}_qualified_family']
            rows.append({'survey_wave':wave,'target':target,'target_available':not(target=='current' and wave=='1996'),
                'roster_members':len(g),'age_eligible_members':int(g.school_age_eligible.sum()),
                'target_applicable_members':int(applicable.sum()),'source_non_null':int(g[f'{target}_source_code'].notna().sum()),
                'qualified_family_records':int(family.notna().sum()),
                'qualified_general_grade_records':int(g[f'{target}_qualified_general_grade'].notna().sum()),
                'unresolved_applicable_records':int((applicable & family.isna()).sum()),
                'derived_never_attended':int(g.highest_derived_from_skip.sum()) if target=='highest' else 0,
                'source_form_renumbered_records':int(g[f'{target}_source_form_code_differs'].sum()),
                'explicit_unknown_responses':int(g[f'{target}_source_response_kind'].eq('unknown').sum())})
    return rows


def build():
    previous = json.loads((BASE/'evidence.json').read_text())
    for name in ['validated.json','independent-checks.json']:
        receipt = json.loads((BASE/name).read_text())
        require(receipt.get('validated',receipt.get('passed')), 'Previous school acceptance required')
    require(file_sha(BASE/'expected.parquet')==previous['expected_sha256'],'School snapshot changed')
    inputs = {**previous['inputs'], str((BASE/'expected.parquet').relative_to(ROOT)):file_sha(BASE/'expected.parquet'),
              str((BASE/'evidence.json').relative_to(ROOT)):file_sha(BASE/'evidence.json'),
              str(Path(__file__).relative_to(ROOT)):file_sha(Path(__file__))}
    for name in ['validated.json','independent-checks.json','published.json']:
        inputs[str((BASE/name).relative_to(ROOT))] = file_sha(BASE/name)
    for relative,sha in inputs.items():
        require(file_sha(ROOT/relative)==sha,'Input changed: '+relative)
    parent = pd.read_parquet(BASE/'expected.parquet')
    sourcecols = KEYS+['age_for_school_analysis','school_age_eligible','education_record_linked','school_concept_scope',
        'school_current_observed','school_ever_observed','school_current_native_code','school_ever_native_code',
        'school_route_conflict','school_invalid_response_code','school_highest_level_source_code','school_current_level_source_code']
    f = parent[sourcecols].rename(columns={'school_highest_level_source_code':'highest_source_code',
                                         'school_current_level_source_code':'current_source_code'})
    spec = json.loads((ROOT/'rsc/specs/cses_additional_waves_v1.json').read_text())
    book, checks = [], []
    for rule in previous['rules']:
        wave = rule['survey_wave']
        cfg = spec['waves'][wave]
        fields = fields_for(spec,cfg['modules']['ED'])
        with zipfile.ZipFile(ROOT/cfg['archive']) as z:
            payload = z.read(cfg['modules']['ED']['member'])
        _, metadata = metadata_only(payload)
        raw = pd.read_stata(io.BytesIO(payload),convert_categoricals=False)
        raw['record_key'] = source_keys(raw,cfg['household_key']+[cfg['person_key']],wave)
        require(raw.record_key.is_unique,'Duplicate native ED key')
        released = f.loc[f.survey_wave.eq(wave)].set_index('record_key').reindex(raw.record_key)
        for target,label in TARGETS.items():
            if label not in fields:
                require(target=='current' and wave=='1996','Unexpected missing target')
                continue
            variable = fields[label][0]
            pd.testing.assert_series_equal(raw[variable].reset_index(drop=True),released[f'{target}_source_code'].reset_index(drop=True),check_names=False,check_dtype=False)
            info = next(r for r in metadata if r['name']==variable)
            native_labels = {int(r['source_value']):r['label'] for r in info['value_labels']}
            definitions = definitions_for(wave,target)
            require(set(native_labels).issubset(definitions),'Unreviewed native dictionary code')
            observed = set(raw[variable].dropna().tolist())
            require(all(float(c).is_integer() and int(c) in definitions for c in observed),'Unreviewed observed level code')
            for code,meaning in sorted(definitions.items()):
                book.append({'survey_wave':wave,'target':target,'source_code':code,'source_variable':variable,
                    'native_value_label':native_labels.get(code), **meaning,
                    'source_form_code_differs':code!=meaning['questionnaire_code'],
                    'source_label_provenance':'native_value_label' if code in native_labels else 'questionnaire_grade_sequence_expansion_native_label_absent',
                    'questionnaire_path':rule['questionnaire_path'],'questionnaire_sha256':rule['questionnaire_sha256'],
                    'questionnaire_locator':rule['locator'],'mapping_version':VERSION})
            checks.append({'survey_wave':wave,'target':target,'source_variable':variable,'native_rows':len(raw),'mismatches':0})
    require(len(book)==188,'Unexpected codebook size')
    result = qualify(f,book).sort_values(KEYS).reset_index(drop=True)
    old99 = parent.loc[parent.survey_wave.eq('1999')]
    revised99 = ((old99.school_ever_observed.eq(0) & (old99.school_current_observed.eq(1) |
        (old99.school_highest_level_source_code.notna() & old99.school_highest_level_source_code.ne(99)) |
        (old99.school_current_level_source_code.notna() & old99.school_current_level_source_code.ne(99)))) |
        (old99.school_current_observed.eq(0) & old99.school_current_level_source_code.notna() & old99.school_current_level_source_code.ne(99))).fillna(False)
    delta99 = int(revised99.ne(old99.school_route_conflict).sum())
    require(delta99==0,'Prior attendance output affected; separate correction required')
    put(OUT/'codebook.json',encoded(book))
    put(OUT/'expected.parquet',parquet_bytes(result))
    report = {'version':VERSION,'inputs':inputs,'native_checks':checks,'codebook_entries':len(book),
        'records':len(result),'summary':summary(result),'codebook_sha256':file_sha(OUT/'codebook.json'),
        'expected_sha256':file_sha(OUT/'expected.parquet'),'prior_1999_attendance_changed_records':delta99,
        'prior_1999_rule_note':'Historical school v1 incorrectly listed 0 as neutral for 1999. Correct meanings are 0=Preschool,99=None. Current source records produce identical attendance outputs. New level dictionary uses correct meanings; old release remains immutable.',
        'status_counts':{target:{w:{str(k):int(v) for k,v in g[f'{target}_level_status'].value_counts().items()}
                               for w,g in result.groupby('survey_wave')} for target in TARGETS},
        'policy':'Field-specific semantic families and ordinary grades, not years attended, degree equivalence or ISCED. Original codes retained.'}
    put(OUT/'evidence.json',encoded(report))
    return report


if __name__=='__main__':
    r = build()
    print(json.dumps({k:r[k] for k in ['records','codebook_entries','summary','status_counts']},indent=2))
