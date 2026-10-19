#!/usr/bin/env python3
"""Evidence-bounded school attendance projection for five additional CSES waves."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
from build_cses_additional_waves import encoded, fields_for, parquet_bytes, source_keys
from cache_cses_questionnaires import file_sha, put

ROOT = Path(__file__).resolve().parents[2]
VERSION = 'cses-additional-school-attendance-v1'
OUT = ROOT / 'data/releases' / VERSION
BASE = ROOT / 'data/processing/cses/additional_waves_v1'
SPEC = ROOT / 'rsc/specs/cses_additional_waves_v1.json'
FORMS = 'data/processed/cses_questionnaires/additional_waves_v1/'
KEYS = ['survey_wave', 'household_key', 'record_key']
VIEW = 'cses_analysis.cses_additional_school_attendance_v1'
RULE = 'cses_alignment.cses_additional_school_rule_v1'
COVERAGE = 'cses_analysis.cses_additional_school_coverage_v1'
EXPECTED = {'1996': 46811, '1997': 29931, '1999': 32348, '2023': 51914, '2025': 51775}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def rules():
    locations = {
        '1996': ('legacy_word_text_v1/1996/QuestENG_Form2.txt', 'Printed page 6; columns 26-28; 5 years old and over',
                 'education_including_training_and_vocational_institutions'),
        '1997': ('1997/forms/QuestENG_Form3.pdf', 'PDF page 4; schooling Q4; columns 5 and 7 skip to 10',
                 'school_system_with_separate_nonformal_item'),
        '1999': ('legacy_word_text_v1/1999/QuestENG_Form3Page.txt', 'II SCHOOLING Q2; columns 4 and 6 skip to 9',
                 'school_system_with_separate_nonformal_item'),
        '2023': ('2023/forms/CSES2023_Household_Questionnaire_ENG_full.pdf',
                 'PDF pages 12-13; columns 4 and 7 skip to 11; holidays count as in school',
                 'school_system_with_separate_nonformal_item'),
        '2025': ('2025/text/CSES2025_Household_Questionnaire_ENG.json',
                 '02 Education (2): B3, R10/R16, AH10/AH15/AH17, BJ10/BJ12; cached cells, not electronic routing logic',
                 'school_system_with_separate_nonformal_item'),
    }
    spec = json.loads(SPEC.read_text())
    result = []
    for wave, (relative, locator, concept) in locations.items():
        cfg = spec['waves'][wave]
        fields = fields_for(spec, cfg['modules']['ED'])
        form = FORMS + relative
        result.append({'survey_wave': wave, 'questionnaire_minimum_age': 5 if wave in {'1996','1997','1999'} else 3,
            'skip_supported': wave != '1996', 'concept_scope': concept,
            'current_variable': fields['Currently Attending School'][0],
            'ever_variable': fields.get('Ever Attended School', [None])[0],
            'education_member': cfg['modules']['ED']['member'],
            'neutral_highest_codes': [0] if wave in {'1997','1999'} else [88,98,-98],
            'neutral_current_codes': [0] if wave in {'1997','1999'} else [98,-98],
            'questionnaire_path': form, 'questionnaire_sha256': file_sha(ROOT / form), 'locator': locator,
            'holiday_instruction_explicit': True if wave in {'2023','2025'} else None,
            'cross_wave_equivalence_certified': False, 'mapping_version': VERSION})
    return result


def qualify(frame):
    """Preserve observed answers. Only non-conflicting documented skips yield derived No."""
    f = frame.copy(deep=True)
    require(f.survey_wave.isin(EXPECTED).all(), 'Unreviewed wave')
    age = f.age_for_school_analysis
    curr, ever = f.school_current_observed, f.school_ever_observed
    f['school_age_eligible'] = age.ge(f.questionnaire_minimum_age).where(age.notna()).astype('boolean')
    f['school_invalid_response_code'] = ((f.school_current_native_code.notna() & ~f.school_current_native_code.isin([1,2])) |
        (f.school_ever_native_code.notna() & ~f.school_ever_native_code.isin([1,2])))
    f['school_ever_no_current_yes'] = (ever.eq(0) & curr.eq(1)).fillna(False)
    history = pd.Series(False, index=f.index)
    current_grade = pd.Series(False, index=f.index)
    for rule in rules_for_frame(f):
        m = f.survey_wave.eq(rule['survey_wave'])
        history.loc[m] = (f.loc[m, 'school_highest_level_source_code'].notna() &
                         ~f.loc[m, 'school_highest_level_source_code'].isin(rule['neutral_highest_codes']))
        current_grade.loc[m] = (f.loc[m, 'school_current_level_source_code'].notna() &
                               ~f.loc[m, 'school_current_level_source_code'].isin(rule['neutral_current_codes']))
    f['school_never_with_history_response'] = (ever.eq(0) & (history | current_grade)).fillna(False)
    f['school_not_current_with_current_grade'] = (curr.eq(0) & current_grade).fillna(False)
    f['school_route_conflict'] = f[['school_ever_no_current_yes','school_never_with_history_response',
                                  'school_not_current_with_current_grade']].any(axis=1)
    f['school_current_grade_missing'] = (f.skip_supported & curr.eq(1) & f.school_current_level_source_code.isna()).fillna(False)
    f['school_gate_missing_with_current_observed'] = f.skip_supported & ever.isna() & curr.notna()
    f['education_record_outside_age_universe'] = (f.education_record_linked & ~f.school_age_eligible).fillna(False)
    status = pd.Series('unanswered_current_attendance', index=f.index, dtype='string')
    status.loc[f.skip_supported & ever.eq(1).fillna(False)] = 'unanswered_current_after_ever_yes'
    status.loc[f.skip_supported & ever.isna()] = 'unanswered_gate_and_current'
    status.loc[f.skip_supported & ever.eq(0).fillna(False) & curr.isna()] = 'documented_skip_inferred_no'
    status.loc[curr.notna()] = 'observed_current'
    status.loc[f.school_gate_missing_with_current_observed] = 'observed_current_gate_missing'
    status.loc[f.school_route_conflict] = 'unresolved_route_conflict'
    status.loc[f.school_invalid_response_code] = 'unrecognized_native_response_code'
    status.loc[~f.education_record_linked] = 'missing_education_record'
    status.loc[~f.school_age_eligible.fillna(True)] = 'outside_questionnaire_age_range'
    status.loc[age.isna()] = 'unknown_age_eligibility'
    f['school_route_status'] = status
    f['school_attendance_qualified'] = curr.astype('Int64').where(status.isin(['observed_current','observed_current_gate_missing']))
    f.loc[status.eq('documented_skip_inferred_no'), 'school_attendance_qualified'] = 0
    f['school_attendance_derived_from_skip'] = status.eq('documented_skip_inferred_no')
    f['qualified_denominator_eligible'] = f.school_attendance_qualified.notna()
    f['school_cross_wave_equivalence_certified'] = False
    f['school_release'] = VERSION
    return f.drop(columns=['skip_supported'])


def rules_for_frame(frame):
    # Pure policy: no file reads in classifier/tests.
    return [{'survey_wave': w, 'neutral_highest_codes': [0] if w in {'1997','1999'} else [88,98,-98],
             'neutral_current_codes': [0] if w in {'1997','1999'} else [98,-98]}
            for w in frame.survey_wave.unique()]


def summary(frame):
    result = []
    for wave, f in frame.groupby('survey_wave', sort=True):
        for band, mask in [('questionnaire_age_eligible', f.school_age_eligible.fillna(False)),
                           ('ages_6_17', f.age_for_school_analysis.between(6,17)),
                           ('ages_10_14', f.age_for_school_analysis.between(10,14))]:
            g = f.loc[mask]
            yes, no = int(g.school_attendance_qualified.eq(1).sum()), int(g.school_attendance_qualified.eq(0).sum())
            n, unknown = len(g), int(g.school_attendance_qualified.isna().sum())
            observed_yes = int(g.school_current_observed.eq(1).sum())
            observed_n = int(g.school_current_observed.notna().sum())
            def pct(a, b):
                return round(100*a/b, 6) if b else None
            result.append({'survey_wave': wave, 'age_band': band, 'concept_scope': g.school_concept_scope.iloc[0] if len(g) else f.school_concept_scope.iloc[0],
                'members': n, 'qualified_yes': yes, 'qualified_no': no, 'qualified_denominator': yes+no,
                'unknown_or_excluded': unknown, 'inferred_no': int(g.school_attendance_derived_from_skip.sum()),
                'route_conflicts': int(g.school_route_conflict.sum()), 'invalid_code_records': int(g.school_invalid_response_code.sum()),
                'observed_yes': observed_yes, 'observed_nonnull': observed_n,
                'qualified_unweighted_yes_pct': pct(yes,yes+no), 'observed_only_yes_pct': pct(observed_yes,observed_n),
                'missingness_lower_bound_pct': pct(yes,n), 'missingness_upper_bound_pct': pct(yes+unknown,n)})
    return result


def build():
    spec = json.loads(SPEC.read_text())
    manifest = json.loads((BASE / 'manifest.json').read_text())
    inputs = {str(SPEC.relative_to(ROOT)): file_sha(SPEC), str(Path(__file__).relative_to(ROOT)): file_sha(Path(__file__)),
              'rsc/cses_db/build_cses_additional_waves.py': file_sha(ROOT/'rsc/cses_db/build_cses_additional_waves.py'),
              'rsc/cses_db/publish_cses_2025_age.py': file_sha(ROOT/'rsc/cses_db/publish_cses_2025_age.py')}
    agebase = ROOT / 'data/releases/cses-2025-age-source-v2'
    receipt = json.loads((agebase/'validated.json').read_text())
    require(receipt['validated'], 'Published 2025 age acceptance required')
    age = pd.read_parquet(agebase/'source.parquet').set_index('record_key')
    for name in ['validated.json','source.parquet','evidence.json','published.json']:
        inputs[str((agebase/name).relative_to(ROOT))] = file_sha(agebase/name)
    rs = rules()
    frames, native_checks = [], []
    for rule in rs:
        w = rule['survey_wave']; cfg = spec['waves'][w]
        require(file_sha(ROOT/cfg['archive']) == cfg['sha256'], 'Archive changed: '+w)
        inputs[cfg['archive']] = cfg['sha256']
        inputs[rule['questionnaire_path']] = rule['questionnaire_sha256']
        tables = {}
        for module in ['HL','ED']:
            relative = f'tables/{w}/{module}.parquet'; path = BASE/relative
            require(file_sha(path) == manifest['artifacts'][relative], 'Candidate changed: '+relative)
            inputs[str(path.relative_to(ROOT))] = file_sha(path)
            tables[module] = pd.read_parquet(path)
        p, e = tables['HL'], tables['ED']
        require(len(p) == EXPECTED[w], 'Unexpected roster count')
        fields = fields_for(spec, cfg['modules']['ED'])
        with zipfile.ZipFile(ROOT/cfg['archive']) as z:
            columns = list(dict.fromkeys(cfg['household_key']+[cfg['person_key']]+[v[0] for v in fields.values()]))
            raw = pd.read_stata(io.BytesIO(z.read(rule['education_member'])), convert_categoricals=False, columns=columns)
        raw['Record Key'] = source_keys(raw, cfg['household_key']+[cfg['person_key']], w)
        require(not raw['Record Key'].duplicated().any(), 'Duplicate raw education key')
        require(set(raw['Record Key']) == set(e['Record Key']), 'Raw/candidate ED key mismatch')
        r = raw.set_index('Record Key').reindex(e['Record Key'])
        for source, _ in fields.values():
            pd.testing.assert_series_equal(r[source].reset_index(drop=True), e['source__'+source].reset_index(drop=True),
                                           check_dtype=False, check_names=False)
        native_checks.append({'survey_wave': w, 'education_rows': len(raw), 'source_fields_verified': len(fields), 'mismatches': 0})
        x = pd.DataFrame({'survey_wave': w, 'household_key': p['Household Key'], 'record_key': p['Record Key'],
                          'age_source_value': p['Age Source Value']})
        if w == '2025':
            require(set(p['Record Key']) == set(age.index), '2025 age key mismatch')
            x['age_for_school_analysis'] = p['Record Key'].map(age.native_calculated_age)
            x['age_selection_status'] = 'native_calculated_age_formula_unverified'
            x['age_first_visit_check_status'] = p['Record Key'].map(age.first_visit_check_status)
        else:
            x['age_for_school_analysis'] = p['Age Source Value']
            x['age_selection_status'] = 'published_source_age_no_new_exact_age_certification'
            x['age_first_visit_check_status'] = pd.Series(pd.NA, index=x.index, dtype='string')
        mapping = {'school_current_observed': 'Currently Attending School','school_ever_observed': 'Ever Attended School',
                   'school_highest_level_source_code':'Highest Education Level Source Code',
                   'school_current_level_source_code':'Current Education Level Source Code'}
        values = pd.DataFrame({'record_key': e['Record Key'], 'ed_household_key': e['Household Key']})
        for target, source in mapping.items():
            values[target] = e[source] if source in e else pd.NA
        for target, source in [('school_current_native_code','Currently Attending School'),('school_ever_native_code','Ever Attended School')]:
            values[target] = e['source__'+fields[source][0]] if source in fields else pd.NA
            if source in fields:
                expected = pd.to_numeric(values[target]).map({1:1,2:0})
                pd.testing.assert_series_equal(expected, pd.to_numeric(values[mapping_inv(mapping,source)]), check_dtype=False, check_names=False)
        require(values.record_key.is_unique and set(values.record_key).issubset(set(x.record_key)), 'ED orphan or duplicate')
        x = x.merge(values, on='record_key', how='left', validate='one_to_one', indicator=True)
        x['education_record_linked'] = x['_merge'].eq('both')
        require(x.loc[x.education_record_linked, 'household_key'].eq(x.loc[x.education_record_linked, 'ed_household_key']).all(), 'ED household mismatch')
        x = x.drop(columns=['_merge','ed_household_key'])
        for c in ['school_current_observed','school_ever_observed']:
            x[c] = pd.to_numeric(x[c]).astype('Int64')
        for c in ['age_source_value','age_for_school_analysis','school_current_native_code','school_ever_native_code',
                  'school_highest_level_source_code','school_current_level_source_code']:
            x[c] = pd.to_numeric(x[c]).astype('float64')
        x['questionnaire_minimum_age'] = rule['questionnaire_minimum_age']
        x['school_concept_scope'] = rule['concept_scope']; x['skip_supported'] = rule['skip_supported']
        frames.append(qualify(x))
    frame = pd.concat(frames, ignore_index=True).sort_values(KEYS).reset_index(drop=True)
    require(len(frame) == 212779 and not frame.duplicated(KEYS).any(), 'Roster grain changed')
    put(OUT/'expected.parquet', parquet_bytes(frame))
    report = {'version': VERSION, 'inputs': inputs, 'rules': rs, 'native_checks': native_checks,
              'summary': summary(frame), 'records': len(frame),
              'route_status_counts': {w: {str(k): int(v) for k,v in g.school_route_status.value_counts().items()}
                                      for w,g in frame.groupby('survey_wave')},
              'expected_sha256': file_sha(OUT/'expected.parquet'),
              'policy': 'Conservative qualified indicator; observed values untouched; age eligibility and route/code conflicts explicit; no pooled cross-wave equivalence.'}
    put(OUT/'evidence.json', encoded(report))
    return report


def mapping_inv(mapping, source):
    return next(k for k,v in mapping.items() if v == source)


if __name__ == '__main__':
    result = build()
    print(json.dumps({k:result[k] for k in ['records','route_status_counts','summary']}, indent=2))
