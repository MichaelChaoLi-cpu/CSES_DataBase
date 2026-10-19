#!/usr/bin/env python3
"""Local fifteen-wave roster-spine education pilot; no database write capability."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
from align_cses_additional_levels import definitions_for
from align_cses_additional_school import KEYS, ROOT, require
from build_cses_additional_waves import encoded, fields_for, parquet_bytes, source_keys
from cache_cses_questionnaires import file_sha, put
from cses_education import ED_ALIASES
from cses_hh_hl_common import DEMOGRAPHIC_ALIASES, AlignmentContext, find_column, snake_case, standardize_source
from inventory_cses_archives import DataSource

VERSION = 'cses-education-all-waves-pilot-v1'
OUT = ROOT/'data/processing/cses/education_all_waves_pilot_v1'
SPEC = ROOT/'rsc/specs/cses_education_all_waves_pilot_v1.json'
EXTRA = {'1996','1997','1999','2023','2025'}
TARGETS = ['combined','read','write','ever','attendance','highest','current','years']
DIRECT = {'combined':'Can Read And Write Combined','read':'Can Read','write':'Can Write',
    'ever':'Ever Attended School','attendance':'Currently Attending School',
    'highest':'Highest Education Level Source Code','current':'Current Education Level Source Code',
    'years':'Years Attended School Source Value'}
OLD_FIELDS = {'read':'can_read','write':'can_write','ever':'ever_attended_school',
    'attendance':'currently_attending_school','highest':'highest_education_level_source_code',
    'current':'current_education_level_source_code','years':'years_attended_school'}
NEW_DIRS = {'attendance':'data/releases/cses-additional-school-attendance-v1',
    'levels':'data/releases/cses-additional-education-levels-v1',
    'literacy':'data/releases/cses-additional-literacy-years-v1'}


def level_definitions(wave,target):
    require(target in ['highest','current'],'Unreviewed level target')
    if wave in EXTRA:
        return {k:{'family':v['semantic_family'],'kind':v['response_kind'],'grade':v['general_grade']}
                for k,v in definitions_for(wave,target).items()}
    require(wave in ['2004','2007','2009','2011-12','2013','2014','2016','2017','2019','2021'],'Unreviewed wave')
    if wave=='2017':
        return {}
    out = {i:{'family':'general_school_grade','kind':'value','grade':i} for i in range(1,13)}
    def add(code,family,kind='value'):
        out[code] = {'family':family,'kind':kind,'grade':None}
    add(0,'preschool_kindergarten')
    if wave=='2004':
        for c,f in {13:'secondary_certificate_unspecified',14:'technical_vocational_pre_secondary',
            15:'technical_vocational_post_secondary',16:'university_undergraduate',
            17:'university_degree_unspecified',18:'postgraduate_unspecified',19:'other_unspecified'}.items():
            add(c,f,'other' if c==19 else 'value')
        add(98,None,'unknown')
        if target=='highest':
            add(90,'none_unspecified','none')
    elif target=='highest':
        for c,f in {13:'lower_secondary_certificate',14:'upper_secondary_certificate',
            15:'technical_vocational_pre_secondary',16:'technical_vocational_post_secondary',
            17:'university_undergraduate',18:'bachelor',19:'masters',20:'doctorate',21:'other_unspecified'}.items():
            add(c,f,'other' if c==21 else 'value')
        add(88,'no_grade_completed','none')
        add(98,None,'unknown')
    elif wave in ['2007','2009','2011-12']:
        for c,f in {13:'technical_vocational_pre_secondary',14:'technical_vocational_post_secondary',
            15:'university_undergraduate',16:'postgraduate_unspecified'}.items():
            add(c,f)
    else:
        for c,f in {15:'technical_vocational_pre_secondary',16:'technical_vocational_post_secondary',
                    17:'university_undergraduate'}.items():
            add(c,f)
        if wave in ['2013','2014','2016']:
            add(21,'postgraduate_unspecified')
            if wave=='2016':
                add(18,'continuing_undergraduate_studies')
        else:
            add(18,'masters')
            add(19,'doctorate')
            add(20,'other_unspecified','other')
    return out


def qualify(frame):
    """Field-specific vector qualification. Unknown form scope never becomes a Yes/No."""
    f = frame.copy(deep=True)
    require(set(f.survey_wave).issubset(EXTRA|set(['2004','2007','2009','2011-12','2013','2014','2016','2017','2019','2021'])),'Unreviewed wave')
    f['age_eligible'] = f.age_for_analysis.ge(f.minimum_age).where(f.minimum_age.notna() & f.age_for_analysis.notna()).astype('boolean')
    for t in ['highest','current']:
        for k in ['family','kind','grade']:
            mapping = {(w,c):v[k] for w in f.survey_wave.unique() for c,v in level_definitions(w,t).items()}
            f[f'{t}_source_{k}'] = [mapping.get((w,c)) for w,c in zip(f.survey_wave,f[f'{t}_native'],strict=True)]
    ever,current = f.ever_native,f.attendance_native
    invalid_ever = ever.notna() & ~ever.isin([1,2])
    invalid_current = current.notna() & ~current.isin([1,2])
    hints_h = f.highest_native.notna() & ~f.highest_source_kind.isin(['none','unknown'])
    hints_c = f.current_native.notna() & ~f.current_source_kind.isin(['none','unknown'])
    f['never_attended_route_conflict'] = ever.eq(2) & (current.eq(1) | hints_h | hints_c)
    f['not_attending_with_current_level_warning'] = current.eq(2) & hints_c
    f['years_exceed_source_age'] = f.years_native.gt(f.age_for_analysis)
    for t in TARGETS:
        x = f[f'{t}_native']
        s = pd.Series('observed',index=f.index,dtype='string')
        s.loc[x.isna()] = 'missing_response'
        if t in ['highest','current']:
            s.loc[x.notna() & f[f'{t}_source_kind'].isna()] = 'unrecognized_level_code'
            s.loc[f[f'{t}_source_kind'].eq('unknown')] = 'explicit_unknown_response'
            value = f[f'{t}_source_family'].astype('string')
            if t=='highest':
                s.loc[x.isna() & ever.eq(2)] = 'derived_never_attended'
                s.loc[f.never_attended_route_conflict] = 'never_attended_route_conflict'
                s.loc[invalid_ever] = 'unrecognized_ever_code'
                value.loc[s.eq('derived_never_attended')] = 'never_attended'
            else:
                s.loc[f[f'{t}_source_kind'].eq('none')] = 'none_not_a_current_level'
                s.loc[current.eq(2)] = 'not_currently_attending'
                s.loc[current.eq(2) & x.notna()] = 'current_level_outside_route'
                s.loc[current.isna()] = 'current_attendance_unresolved'
                s.loc[ever.eq(2) & current.eq(1)] = 'never_attended_route_conflict'
                s.loc[invalid_ever | invalid_current] = 'unrecognized_attendance_code'
        elif t=='years':
            valid = x.between(0,30) & x.mod(1).eq(0)
            value = x.where(valid).astype('Int64')
            s.loc[f.years_exceed_source_age] = 'years_exceed_source_age'
            s.loc[x.notna() & ~valid] = 'outside_integer_0_30_guard'
            s.loc[ever.eq(2) & x.isna()] = 'documented_skip_no_years_value'
            s.loc[ever.eq(2) & x.notna()] = 'years_value_outside_route'
            s.loc[ever.isna()] = 'ever_attendance_unresolved'
            s.loc[invalid_ever] = 'unrecognized_ever_code'
        else:
            value = x.map({1:1,2:0}).astype('Int64')
            s.loc[x.notna() & ~x.isin([1,2])] = 'unrecognized_binary_code'
            if t=='combined':
                derived = f.combined_mode.eq('derived_components')
                valid = f.read_native.isin([1,2]) & f.write_native.isin([1,2])
                bad = ((f.read_native.notna() & ~f.read_native.isin([1,2])) |
                       (f.write_native.notna() & ~f.write_native.isin([1,2])))
                s.loc[derived] = 'missing_component_response'
                s.loc[derived & bad] = 'unrecognized_component_code'
                s.loc[derived & valid] = 'derived_components'
                value.loc[derived] = pd.NA
                value.loc[derived & valid] = (f.read_native.eq(1) & f.write_native.eq(1)).astype(int)
            if t=='attendance':
                derive_no = f.skip_supported & ever.eq(2) & current.isna()
                s.loc[derive_no] = 'derived_documented_skip_no'
                value.loc[derive_no] = 0
                s.loc[f.never_attended_route_conflict | f.not_attending_with_current_level_warning] = 'attendance_route_conflict'
                s.loc[invalid_ever | invalid_current] = 'unrecognized_attendance_code'
        s.loc[~f.education_linked] = 'missing_education_record'
        s.loc[~f.age_eligible.fillna(True)] = 'outside_questionnaire_age_range'
        s.loc[f.age_eligible.isna()] = 'unknown_age_eligibility'
        s.loc[~f.form_scope_reviewed] = 'unverified_same_wave_form_scope'
        s.loc[~f[f'{t}_available']] = 'not_collected_in_selected_source'
        usable = s.isin(['observed','derived_components','derived_documented_skip_no','derived_never_attended'])
        f[f'{t}_status'] = s
        f[f'{t}_qualified'] = value.where(usable)
        if t in ['highest','current']:
            f[f'{t}_general_grade'] = pd.to_numeric(f[f'{t}_source_grade']).where(usable).astype('Int64')
        applicable = (f[f'{t}_available'] & f.age_eligible & f.education_linked).fillna(False)
        f[f'{t}_applicable'] = applicable
        f[f'{t}_expected_by_route'] = applicable & (ever.eq(1) if t=='years' else current.eq(1) if t=='current' else True)
    f['combined_derived'] = f.combined_status.eq('derived_components')
    f['years_imputed'] = False
    f['cross_wave_equivalence_certified'] = False
    return f


def coverage(frame):
    rows = []
    for w,g in frame.groupby('survey_wave',sort=True):
        for band,mask in [('questionnaire_universe',g.age_eligible.fillna(False)),
                          ('ages_6_17',g.age_for_analysis.between(6,17)),('ages_15_plus',g.age_for_analysis.ge(15))]:
            f = g.loc[mask]
            for t in TARGETS:
                q = f[f'{t}_qualified']
                expected = f[f'{t}_expected_by_route']
                rows.append({'survey_wave':w,'age_band':band,'target':t,'roster_members':len(g),
                    'minimum_age':None if pd.isna(g.minimum_age.iloc[0]) else int(g.minimum_age.iloc[0]),
                    'form_scope_reviewed':bool(g.form_scope_reviewed.iloc[0]),
                    'age_band_members':len(f) if band!='questionnaire_universe' or g.form_scope_reviewed.all() else None,
                    'source_available':bool(g[f'{t}_available'].iloc[0]),'expected_by_route':int(expected.sum()),
                    'raw_non_null':int(f[f'{t}_native'].notna().sum()),'qualified_records':int(q.notna().sum()),
                    'unresolved_expected':int((expected & q.isna()).sum()),
                    'qualified_yes':int(q.eq(1).sum()) if t not in ['highest','current','years'] else None,
                    'qualified_no':int(q.eq(0).sum()) if t not in ['highest','current','years'] else None})
    return rows


def build():
    cfg = json.loads(SPEC.read_text())
    require(not cfg['database_publication_authorized'] and not cfg['historical_outputs_mutable'],'Local-only boundary required')
    inputs = {}
    def pin(path,expected=None):
        path = Path(path)
        path = path if path.is_absolute() else ROOT/path
        sha = file_sha(path)
        require(expected is None or sha==expected,'Pinned input changed: '+str(path))
        inputs[str(path.relative_to(ROOT))] = sha
        return path
    pin(SPEC)
    for p in [Path(__file__),ROOT/'rsc/cses_db/cses_hh_hl_common.py',ROOT/'rsc/cses_db/cses_education.py',
              ROOT/'rsc/cses_db/align_cses_additional_levels.py',ROOT/'rsc/cses_db/build_cses_additional_waves.py',
              ROOT/'rsc/cses_db/cache_cses_questionnaires.py',ROOT/'rsc/cses_db/inventory_cses_archives.py']:
        pin(p)
    review = json.loads(pin('data/processing/cses/education_review_v1/review.json').read_text())
    pin('rsc/cses_db/cses_education.py',review['education_builder_sha256'])
    for p,sha in review['input_sha256'].items():
        pin('data/processing/cses/questionnaire_alignment_v1/'+p,sha)
    pin('data/processing/cses/education_review_v1/source_verification.json')
    alignment = json.loads((ROOT/'data/processing/cses/questionnaire_alignment_v1/alignment.json').read_text())
    inventory = json.loads((ROOT/'data/processing/cses/questionnaire_alignment_v1/source_inventory.json').read_text())
    for p,sha in inventory['archive_sha256'].items():
        pin(p,sha)
    for item in cfg['supplemental_form_review'].values():
        pin(item['path'],item['sha256'])
        if 'original_path' in item:
            pin(item['original_path'],item['original_sha256'])
    old_hl = pd.read_parquet(pin('data/processing/cses/final_HL_CSES.parquet')).rename(columns=snake_case)
    old_ed = pd.read_parquet(pin('data/processing/cses/education_corrected_v1/final_ED_CSES.parquet'))
    pin('data/processing/cses/final_ED_CSES.parquet',review['canonical_parquet_sha256'])
    pin('data/processing/cses/education_corrected_v1/plan.json')
    for d in NEW_DIRS.values():
        e = json.loads(pin(d+'/evidence.json').read_text())
        for p,sha in e['inputs'].items():
            pin(p,sha)
        pin(d+'/expected.parquet',e['expected_sha256'])
        for name,key in [('validated.json','validated'),('independent-checks.json','passed')]:
            require(json.loads(pin(d+'/'+name).read_text())[key],'Accepted extra-wave release required')
        pin(d+'/published.json')
    spec = json.loads(pin('rsc/specs/cses_additional_waves_v1.json').read_text())
    schools = pd.read_parquet(ROOT/NEW_DIRS['attendance']/'expected.parquet')
    old_questions = {(r['survey_wave'],r['canonical_field']):r for r in review['questions']}
    source_checks,orphans,matrix,frames,book = [],[],[],[],[]
    for wave in sorted(set(old_hl.survey_wave)|EXTRA):
        isnew = wave in EXTRA
        if isnew:
            c = spec['waves'][wave]
            with zipfile.ZipFile(ROOT/c['archive']) as z:
                raw_hl = pd.read_stata(io.BytesIO(z.read(c['modules']['HL']['member'])),convert_categoricals=False)
                raw_ed = pd.read_stata(io.BytesIO(z.read(c['modules']['ED']['member'])),convert_categoricals=False)
            for f in [raw_hl,raw_ed]:
                f['record_key'] = source_keys(f,c['household_key']+[c['person_key']],wave)
                f['household_key'] = source_keys(f,c['household_key'],wave)
            aliases = fields_for(spec,c['modules']['ED'])
            variables = {t:aliases[DIRECT[t]][0] if DIRECT[t] in aliases else None for t in TARGETS}
            agevar = fields_for(spec,c['modules']['HL'])['Age Source Value'][0]
            selected_age = raw_hl['age'] if wave=='2025' else raw_hl[agevar]
            x = pd.DataFrame({'survey_wave':wave,'record_key':raw_hl.record_key,'household_key':raw_hl.household_key,
                'age_source_value':raw_hl[agevar],'age_for_analysis':selected_age})
            p = schools.loc[schools.survey_wave.eq(wave)].set_index('record_key').reindex(x.record_key)
            pd.testing.assert_series_equal(selected_age.reset_index(drop=True),p.age_for_school_analysis.reset_index(drop=True),check_names=False,check_dtype=False)
            minimum = 5 if wave in ['1996','1997','1999'] else 3
            form = next(r for r in json.loads((ROOT/NEW_DIRS['attendance']/'evidence.json').read_text())['rules'] if r['survey_wave']==wave)
            form_status = 'accepted_extra_wave_form_scope'
            form_locator = form['questionnaire_path']+'; '+form['locator']
        else:
            h = old_hl.loc[old_hl.survey_wave.eq(wave)].copy()
            hs = DataSource(pin(h.source_archive.iloc[0]),tuple(h.source_submodule.iloc[0].split('::')))
            edlink = next(r for r in alignment['source_links'] if r['survey_wave']==wave and r['module_code']=='education'
                          and ['final_ED_CSES','can_read'] in r['canonical_keys'])
            es = DataSource(pin(edlink['archive_relative_path']),tuple(p for p in [edlink['member_path'],edlink['nested_member_path']] if p))
            raw_hl,raw_ed = [pd.read_stata(io.BytesIO(s.read_bytes()),convert_categoricals=False) for s in [hs,es]]
            for raw,source in [(raw_hl,hs),(raw_ed,es)]:
                context = AlignmentContext(root=ROOT)
                context.frames[source.display_name(ROOT)] = raw
                keys = standardize_source(context,source,wave,'HL' if source==hs else 'ED').rename(columns=snake_case)
                raw['record_key'],raw['household_key'],raw['source_row_id'] = keys.person_id,keys.household_id,keys.source_row_id
            require(set(h.person_id)==set(raw_hl.record_key),'Old raw roster keys differ')
            variables = {t:find_column(raw_ed,ED_ALIASES[old_label]) if t!='combined' else None
                         for t,old_label in {**{t:next(k for k in ED_ALIASES if snake_case(k)==field) for t,field in OLD_FIELDS.items()},'combined':None}.items()}
            agevar = find_column(raw_hl,DEMOGRAPHIC_ALIASES['Age'])
            selected_age = raw_hl[agevar].where(raw_hl[agevar].between(0,120) & raw_hl[agevar].mod(1).eq(0))
            if wave=='2004':
                selected_age = selected_age.where(~selected_age.isin([98,99]))
            pd.testing.assert_series_equal(selected_age.reset_index(drop=True),h.set_index('person_id').reindex(raw_hl.record_key).age.reset_index(drop=True),check_names=False,check_dtype=False)
            x = pd.DataFrame({'survey_wave':wave,'record_key':raw_hl.record_key,'household_key':raw_hl.household_key,
                'age_source_value':raw_hl[agevar],'age_for_analysis':selected_age})
            canonical = old_ed.loc[old_ed.survey_wave.eq(wave)].set_index('source_row_id').reindex(raw_ed.source_row_id)
            require(set(canonical.index)==set(raw_ed.source_row_id) and canonical.person_id.eq(raw_ed.record_key.to_numpy()).all(), 'Old ED raw identities differ')
            for t,var in variables.items():
                if var:
                    v = raw_ed[var]
                    expected = v.map({1:1,2:0}) if t in ['read','write','ever','attendance'] else v.where(v.between(0,30)&v.mod(1).eq(0)) if t=='years' else v
                    pd.testing.assert_series_equal(expected.reset_index(drop=True),canonical[OLD_FIELDS[t]].reset_index(drop=True),check_names=False,check_dtype=False)
            evidence = old_questions.get((wave,'can_read'))
            minimum = cfg['supplemental_form_review'][wave]['minimum_age'] if wave in cfg['supplemental_form_review'] else evidence['minimum_age'] if evidence else None
            form_status = cfg['supplemental_form_review'][wave]['status'] if wave in cfg['supplemental_form_review'] else 'historical_literal_form_review' if evidence else 'same_wave_form_not_located'
            form_locator = cfg['supplemental_form_review'][wave]['path']+'; '+cfg['supplemental_form_review'][wave]['locator'] if wave in cfg['supplemental_form_review'] else evidence['source_file']+'; '+evidence['source_sheet'] if evidence else None
        require(raw_hl.record_key.is_unique and raw_ed.record_key.is_unique,'Duplicate native record keys')
        e = raw_ed.set_index('record_key')
        x['education_linked'] = x.record_key.isin(e.index)
        linked = x.education_linked
        require(x.loc[linked,'household_key'].eq(x.loc[linked,'record_key'].map(e.household_key)).all(),'ED/HL household mismatch')
        for t in TARGETS:
            var = variables.get(t)
            x[f'{t}_native'] = x.record_key.map(e[var]) if var else float('nan')
            x[f'{t}_available'] = var is not None or (t=='combined' and wave not in ['1996','1997','1999'])
        x['minimum_age'] = minimum
        x['form_scope_reviewed'] = minimum is not None
        x['form_evidence_status'] = form_status
        x['combined_mode'] = 'observed_combined' if wave in ['1996','1997','1999'] else 'derived_components'
        x['skip_supported'] = wave!='1996' and minimum is not None
        x['age_selection_status'] = 'published_native_calculated_age_formula_unverified' if wave=='2025' else 'reported_source_age_no_new_exact_age_certification'
        x['age_documented_topcode'] = pd.Series(pd.NA,index=x.index,dtype='boolean')
        if wave in ['2004','1996','1999']:
            x['age_documented_topcode'] = x.age_for_analysis.eq(96 if wave=='2004' else 98).astype('boolean').where(x.age_for_analysis.notna())
        for t in ['highest','current']:
            for code,meaning in level_definitions(wave,t).items():
                book.append({'survey_wave':wave,'target':t,'source_code':code,**meaning,'form_evidence_status':form_status,
                    'source_variable':variables[t],'form_locator':form_locator})
        missing = e.loc[~e.index.isin(x.record_key)].copy()
        if len(missing):
            o = missing[['household_key']].copy()
            o['survey_wave'] = wave
            o['record_key'] = o.index
            o['source_row_id'] = missing.source_row_id
            for t in TARGETS:
                o[f'{t}_native'] = missing[variables[t]] if variables.get(t) else float('nan')
            orphans.append(o.reset_index(drop=True))
        for t in TARGETS:
            matrix.append({'survey_wave':wave,'target':t,'source_variable':variables.get(t),
                'source_available':bool(x[f'{t}_available'].iloc[0]),'mode':x.combined_mode.iloc[0] if t=='combined' else 'direct_native' if variables.get(t) else 'unavailable',
                'roster_members':len(x),'native_education_rows':len(e),'native_source_non_null':int(e[variables[t]].notna().sum()) if variables.get(t) else 0,
                'orphan_education_rows':len(missing),'minimum_age':minimum,'form_evidence_status':form_status,
                'form_locator':form_locator,'whole_variable_equivalence_certified':False})
        frames.append(x)
        source_checks.append({'survey_wave':wave,'raw_roster_records':len(raw_hl),'raw_education_records':len(raw_ed),
            'linked_education_records':int(linked.sum()),'orphan_education_records':len(missing),'native_mismatches':0})
    frame = pd.concat(frames,ignore_index=True)
    for c in ['age_source_value','age_for_analysis','minimum_age']+[f'{t}_native' for t in TARGETS]:
        frame[c] = pd.to_numeric(frame[c]).astype(float)
    frame = qualify(frame).sort_values(KEYS).reset_index(drop=True)
    require(len(frame)==571699 and not frame.duplicated(KEYS).any(),'Fifteen-wave roster grain differs')
    orphan_frame = pd.concat(orphans,ignore_index=True).sort_values(KEYS).reset_index(drop=True)
    require(len(orphan_frame)==4,'Prior unmatched ED scope changed')
    preserve = []
    expected_sources = {k:pd.read_parquet(ROOT/p/'expected.parquet').set_index(KEYS) for k,p in NEW_DIRS.items()}
    sample = frame.loc[frame.survey_wave.isin(EXTRA)].set_index(KEYS)
    mapping = {'combined':('literacy','combined_qualified'),'read':('literacy','read_qualified'),
        'write':('literacy','write_qualified'),'years':('literacy','years_qualified'),
        'attendance':('attendance','school_attendance_qualified'),'highest':('levels','highest_qualified_family'),
        'current':('levels','current_qualified_family')}
    for t,(kind,col) in mapping.items():
        expected = expected_sources[kind].reindex(sample.index)[col]
        actual = sample[f'{t}_qualified']
        delta = ~(actual.eq(expected).fillna(False) | (actual.isna() & expected.isna()))
        require(not delta.any(),'Extra-wave accepted values changed: '+t)
        preserve.append({'target':t,'records':len(actual),'mismatches':int(delta.sum())})
    for row in matrix:
        g = frame.loc[frame.survey_wave.eq(row['survey_wave'])]
        t = row['target']
        row['qualified_records'] = int(g[f'{t}_qualified'].notna().sum())
        row['unresolved_expected'] = int((g[f'{t}_expected_by_route'] & g[f'{t}_qualified'].isna()).sum())
    for name,payload in [('members.parquet',parquet_bytes(frame)),('orphan_education.parquet',parquet_bytes(orphan_frame)),
                         ('matrix.json',encoded(matrix)),('level_codebook.json',encoded(book))]:
        put(OUT/name,payload)
    report = {'version':VERSION,'database_modified':False,'strict_2017_form_unresolved':True,'inputs':inputs,
        'roster_members':len(frame),'matrix_rows':len(matrix),'level_codebook_rows':len(book),'orphan_rows':len(orphan_frame),
        'source_checks':source_checks,'accepted_extra_wave_preservation':preserve,'coverage':coverage(frame),
        'status_counts':{t:{w:{str(k):int(v) for k,v in g[f'{t}_status'].value_counts().items()} for w,g in frame.groupby('survey_wave')} for t in TARGETS},
        'artifacts':{n:file_sha(OUT/n) for n in ['members.parquet','orphan_education.parquet','matrix.json','level_codebook.json']},
        'limitations':['Local pilot, not a published database interface or blanket equivalence.',
            '2017 raw answers retained but strict fields withheld pending same-wave form evidence.',
            'School years are observed only among gate-qualified ever-attenders; skips remain null.',
            'All counts are unweighted member-wave records, not direct respondents or longitudinal identities.',
            'Older and current degree dictionaries are separate; ordinary grades are not completed school years.']}
    put(OUT/'report.json',encoded(report))
    print(json.dumps({k:report[k] for k in ['roster_members','matrix_rows','level_codebook_rows','orphan_rows','source_checks','accepted_extra_wave_preservation']},indent=2))
    return report


if __name__=='__main__':
    build()
