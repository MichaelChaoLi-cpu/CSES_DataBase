#!/usr/bin/env python3
"""Local fifteen-wave health screening pilot. No database connection or write path."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
from align_cses_additional_school import KEYS, ROOT, require
from build_cses_additional_waves import encoded, parquet_bytes
from build_cses_additional_waves import source_keys as extra_keys
from build_cses_health import load_source
from cache_cses_questionnaires import file_sha, put
from cses_hh_hl_common import snake_case
from inventory_cses_archives import DataSource
from pilot_cses_education_all_waves import EXTRA
from plan_cses_health_illness import source_keys as old_keys

OUT = ROOT/'data/processing/cses/health_all_waves_pilot_v1'
SPEC = ROOT/'rsc/specs/cses_health_all_waves_pilot_v1.json'
HEALTH = ROOT/'data/processed/cses_health/v1'
BRANCHES = [f'branch_{i}_native' for i in range(1,12)]
OUTCOMES = ['screen_qualified','illness_injury_30d_candidate','illness_injury_30d_qualified']
FORMS = {
    '1996':('data/processed/cses_questionnaires/additional_waves_v1/legacy_word_text_v1/1996/QuestENG_Form2.txt','Under-five health, two-week diarrhoea; separate child-work illness/injury over a year; no selected all-member recent-illness item'),
    '1997':('data/processed/cses_questionnaires/additional_waves_v1/1997/forms/QuestENG_Form3.pdf','Physical page 8, IV Health, Q6 column3; all usually resident members; major illness/injury/other problem, four weeks'),
    '1999':('data/processed/cses_questionnaires/additional_waves_v1/legacy_word_text_v1/1999/QuestENG_Form3Page.txt','IV Health Q4 column3; all usually resident members; illness/injury/other healthcare need, four weeks; preventive care remains in source'),
    '2007':('data/raw/CSES 2007/Questionnaire/KHM_2007_CSES_hh_questionnaire.pdf','Physical pages41-43, section14A, screen col6; Week4, all usually resident members; four-week broader health problem'),
    '2014':('data/raw/CSES 2014/CSES_2014_Report.pdf','Physical page250; printed238, questionnaire37/54; section13B screen(2); suffix correspondence to native2a supported by historical source audit'),
    '2019':('data/processing/cses/materials_audit_v1/render_2019/Forms of CSES 2019-20-English\u200b.pdf','Physical/printed page46, section13B col2a: 1=sick/illness, 2=No(>>4), 3=No(>>7); code2 conflicts with native Injury'),
    '2023':('data/processed/cses_questionnaires/additional_waves_v1/2023/forms/CSES2023_Household_Questionnaire_ENG_full.pdf','Physical page47, section13B col2a; 1 illness,2 injury,3 no; all usually resident members,30days'),
    '2025':('data/processed/cses_questionnaires/additional_waves_v1/2025/text/CSES2025_Household_Questionnaire_ENG.json','Matching sheets 13 Health Care Seeking _ 2 and 13 Health Care Seeking_2 (2), B2/B3/C7/C18/C25; paper scope only'),
}


def source_inputs(pin):
    """Re-read native bytes, retain original screen and each skipped-branch input."""
    spec = json.loads(pin(SPEC).read_text())
    require(not spec['database_publication_authorized'] and not spec['historical_outputs_mutable'],'Local-only scope required')
    old = json.loads(pin('rsc/specs/cses_health_recent_illness_v1.json').read_text())['waves']
    intake = json.loads(pin(HEALTH/'manifest.json').read_text())
    addition = json.loads(pin('rsc/specs/cses_additional_waves_v1.json').read_text())['waves']
    old_proof = {r['survey_wave']:r for r in json.loads(pin('data/processing/cses/health_recent_illness_v1/wave_review.json').read_text())}
    native_datasets = json.loads(pin('data/processing/cses/additional_waves_v1/datasets.json').read_text())
    frames,rules,checks = [],[],[]
    for wave,cfg in spec['waves'].items():
        rule = dict(cfg,survey_wave=wave)
        if wave in EXTRA:
            c = addition[wave]
            archive,chain = pin(c['archive'],c['sha256']),(c['modules']['HEALTH']['member'],)
            expected_sha = next(d['sha256'] for d in native_datasets if d['wave']==wave and d['member']==chain[0])
        else:
            s = next(s for s in intake['sources'] if s['source_id']==old[wave]['source_id'])
            archive,chain = pin(s['archive_relative_path'],intake['archive_sha256'][s['archive_relative_path']]),tuple(s['member_chain'])
            expected_sha = s['source_sha256']
        source = DataSource(archive,chain)
        payload = source.read_bytes()
        import hashlib
        require(hashlib.sha256(payload).hexdigest()==expected_sha,'Native member bytes changed')
        with pd.io.stata.StataReader(io.BytesIO(payload),convert_categoricals=False,convert_dates=False) as reader:
            labels = reader.variable_labels()
            assignments = dict(zip(reader._varlist,reader._lbllist,strict=True))
            dictionaries = reader.value_labels()
            native = reader.read()
        if wave in EXTRA:
            keys = pd.DataFrame({'survey_wave':wave,'household_key':extra_keys(native,c['household_key'],wave),
                'record_key':extra_keys(native,c['household_key']+[c['person_key']],wave)})
            missing = json.loads(pin(f'data/processing/cses/additional_waves_v1/source_missing/{wave}/{Path(chain[0]).stem}.json').read_text())
        else:
            keys = old_keys(native,wave).rename(columns={'household_id':'household_key','person_id':'record_key'})
            cached = load_source(HEALTH,old[wave]['source_id'])
            pin(HEALTH/s['parquet_path'])
            for column in native:
                pd.testing.assert_series_equal(native[column],cached[column],check_names=False,check_dtype=False)
        var = cfg['variable']
        if var is None:
            mapping = {}
        elif wave=='2017':
            mapping = {}  # Unlabelled candidate never inherits another questionnaire.
        else:
            mapping = {1:1,2:1,3:0} if wave in ['2019','2021','2023','2025'] else {1:1,2:0}
        no_followups = cfg.get('no_followups')
        if no_followups is None:
            no_followups = [] if wave in ['1996','2017'] else [next(k for k in native if k.lower()==v)
                for v in ['q13bc2b','q13bc03','q13bc04','q13bc05','q13bc06']]
        require(len(no_followups)<=len(BRANCHES) and all(v in native for v in no_followups),'Branch layout differs: '+wave)
        if wave in EXTRA:
            selected = {var,*no_followups}
            require(not any(m['variable_name'] in selected for m in missing),'Selected screening inputs have extended missing; review required')
        injury_vars = no_followups[:2] if wave in ['2019','2021','2023','2025'] else []
        rule.update(mapping={str(k):v for k,v in mapping.items()},missing_codes=[9] if wave=='2004' else [],
            no_followups=no_followups,injury_only=injury_vars,
            source_archive=str(archive.relative_to(ROOT)),source_member_chain=list(chain),source_sha256=expected_sha,
            source_id=old[wave]['source_id'] if wave not in EXTRA else expected_sha[:16],
            native_variable_label=labels[var] if var else None,
            native_value_labels={str(k):v for k,v in dictionaries.get(assignments.get(var),{}).items()} if var else {})
        if wave in FORMS:
            path,locator = FORMS[wave]
            pin(path)
            rule.update(form_path=path,form_locator=locator)
        elif wave!='2017':
            proof = old_proof[wave]['questionnaire']
            path = 'data/processed/cses_questionnaires/v1/'+proof['form']['cells_path']
            cells = json.loads(pin(path).read_text())['sheets'][proof['sheet']]
            require(all(cells[proof['locators'][k]]==proof[k] for k in ['question','options','universe','printed_number']),'Historical form changed')
            pin('data/processed/cses_questionnaires/v1/'+proof['form']['local_path'])
            rule.update(form_path=path,form_locator=proof['sheet']+'; '+str(proof['locators']))
        else:
            rule.update(form_path=None,form_locator=None)
        x = keys.copy()
        x['source_row_number'] = range(1,len(x)+1)
        x['source_id'] = rule['source_id']
        x['screen_native'] = native[var].astype(float) if var else float('nan')
        for i,column in enumerate(BRANCHES):
            x[column] = native[no_followups[i]].astype(float) if i<len(no_followups) else float('nan')
        x['screen_variant_conflict'] = False
        x['followup_variant_conflict'] = False
        if wave=='2023':
            alternate = pd.read_stata(io.BytesIO(DataSource(archive,('S13A_PersonIllness.dta',)).read_bytes()),convert_categoricals=False,convert_dates=False)
            primary = native.set_index(['hhid','persid'])
            alternate = alternate.set_index(['hhid','persid'])
            require(primary.index.is_unique and alternate.index.is_unique and set(primary.index)==set(alternate.index),'Variant key grain differs')
            alternate = alternate.reindex(primary.index)
            for column in [var,*no_followups]:
                delta = ~(primary[column].eq(alternate[column])|(primary[column].isna()&alternate[column].isna()))
                name = 'screen_variant_conflict' if column==var else 'followup_variant_conflict'
                x[name] |= delta.to_numpy()
            require(not x.screen_variant_conflict.any(),'Screen variants unexpectedly disagree')
            require(int(x.followup_variant_conflict.sum())==1,'Follow-up variant count differs')
        require(not x.duplicated(KEYS).any(),'Duplicate health key')
        frames.append(x)
        rules.append(rule)
        checks.append({'survey_wave':wave,'source_rows':len(x),'native_member_sha256':expected_sha,'raw_cache_mismatches':0})
    # These supplemental sources resolve period/scope but do not adjudicate the 2019 code2 conflict.
    pin('data/processed/cses_questionnaires/official_retrieval_v1/2019/references/CSES2019_20_Final_Report_ENG.pdf')
    cells = json.loads(pin(FORMS['2025'][0]).read_text())['sheets']
    require(all(cells['13 Health Care Seeking _ 2'][k]==cells['13 Health Care Seeking_2 (2)'][k]
        for k in ['B2','B3','C7','C18','C25']),'2025 screening sheet versions differ')
    for path in sorted((OUT/'evidence').glob('*.png')):
        pin(path)
    return pd.concat(frames,ignore_index=True),rules,checks


def qualify(f,rules):
    """Vector screening policy; unasked, missing, unverified and contradictory differ."""
    frames = []
    for rule in rules:
        g = f.loc[f.survey_wave.eq(rule['survey_wave'])].copy()
        x = g.screen_native
        mapping = {int(k):v for k,v in rule['mapping'].items()}
        observed = x.map(mapping).astype('Int64')
        no = [k for k,v in mapping.items() if v==0]
        g['no_with_followup'] = x.isin(no)&g[BRANCHES[:len(rule['no_followups'])]].notna().any(axis=1)
        g['injury_with_illness_only'] = x.eq(2)&g[BRANCHES[:len(rule['injury_only'])]].notna().any(axis=1)
        g['source_form_code_conflict'] = x.isin(rule.get('disputed_codes',[]))
        g['screen_available'] = rule['variable'] is not None
        g['form_scope_reviewed'] = rule['period_days'] is not None
        g['instrument_family'] = rule['family']
        g['reference_period_days'] = rule['period_days']
        g['form_evidence_status'] = rule['form_status']
        g['source_variable'] = rule['variable']
        g['screen_binary_native'] = observed
        status = pd.Series('observed_with_instrument_scope',index=g.index,dtype='string')
        status.loc[g.no_with_followup|g.injury_with_illness_only] = 'screening_branch_conflict'
        status.loc[g.screen_variant_conflict] = 'screen_variant_conflict'
        status.loc[g.source_form_code_conflict] = 'source_form_code_conflict'
        status.loc[x.notna()&observed.isna()] = 'unrecognized_native_code'
        status.loc[x.isin(rule['missing_codes'])] = 'explicit_missing_code'
        status.loc[x.isna()] = 'source_null'
        status.loc[~g.hh_link_matched] = 'household_not_matched'
        status.loc[~g.health_linked] = 'missing_health_source_record'
        if rule['period_days'] is None:
            status[:] = 'unverified_same_wave_form_scope'
        if rule['variable'] is None:
            status[:] = 'not_collected_in_selected_source'
        g['screen_status'] = status
        g['screen_applicable'] = bool(rule['variable'] and rule['period_days'])&g.health_linked&g.hh_link_matched
        g['screen_qualified'] = observed.where(status.eq('observed_with_instrument_scope'))
        blank = pd.Series(pd.NA,index=g.index,dtype='Int64')
        g['illness_injury_30d_candidate'] = g.screen_qualified if rule['period_days']==30 else blank
        g['illness_injury_30d_qualified'] = g.illness_injury_30d_candidate if rule['strict_30d'] else blank
        g['strict_30d_wave'] = rule['strict_30d']
        g['strict_30d_status'] = status.copy()
        valid = status.eq('observed_with_instrument_scope')
        g.loc[valid,'strict_30d_status'] = ('observed_30day_screen' if rule['strict_30d'] else
            'separate_period_or_concept' if rule['period_days']!=30 else 'qualified_wave_not_in_strict_default')
        g['screen_imputed'] = False
        g['cross_wave_equivalence_certified'] = False
        frames.append(g)
    result = pd.concat(frames,ignore_index=True).sort_values(KEYS).reset_index(drop=True)
    result['reference_period_days'] = result.reference_period_days.astype('Int64')
    return result


def coverage(f):
    rows = []
    for wave,g in f.groupby('survey_wave',sort=True):
        for band,mask in [('all_members',pd.Series(True,index=g.index)),('ages_6_17',g.age_for_analysis.between(6,17)),('ages_15_plus',g.age_for_analysis.ge(15))]:
            x = g.loc[mask]
            r = {'survey_wave':wave,'age_band':band,'roster_members':len(g),'members_in_band':len(x),
                'health_linked':int(x.health_linked.sum()),'raw_screen_non_null':int(x.screen_native.notna().sum()),
                'screen_applicable':int(x.screen_applicable.sum()),'unresolved_expected':int((x.screen_applicable&x.screen_qualified.isna()).sum())}
            for col in OUTCOMES:
                r[col+'_records'] = int(x[col].notna().sum())
                r[col+'_yes'] = int(x[col].eq(1).sum())
                r[col+'_no'] = int(x[col].eq(0).sum())
            rows.append(r)
    return rows


def build():
    inputs = {}
    def pin(path,expected=None):
        p = Path(path)
        p = p if p.is_absolute() else ROOT/p
        sha = file_sha(p)
        require(expected is None or sha==expected,'Input changed: '+str(p))
        inputs[str(p.relative_to(ROOT))] = sha
        return p
    source,rules,checks = source_inputs(pin)
    # The accepted education roster is an exact-key, source-age bridge, not an education eligibility filter.
    education = ROOT/'data/processing/cses/education_all_waves_pilot_v2'
    report = json.loads(pin(education/'report.json').read_text())
    roster = pd.read_parquet(pin(education/'members.parquet',report['artifacts']['members.parquet']))[KEYS+['age_source_value','age_for_analysis','age_selection_status']]
    require(len(roster)==571699 and not roster.duplicated(KEYS).any(),'Roster spine changed')
    old_hh = pd.read_parquet(pin('data/processing/cses/final_HH_CSES.parquet')).rename(columns=snake_case)
    old_hh = old_hh[['survey_wave','household_id']].rename(columns={'household_id':'household_key'})
    new_hh = pd.read_parquet(pin('data/processing/cses/additional_waves_v1/tables/all_HH.parquet'))[['Survey Wave','Household Key']].rename(columns=snake_case)
    hh = pd.concat([old_hh,new_hh],ignore_index=True)
    require(not hh.duplicated(['survey_wave','household_key']).any(),'Household grain changed')
    source = source.merge(hh.assign(hh_link_matched=True),on=['survey_wave','household_key'],how='left',validate='many_to_one')
    source['hh_link_matched'] = source.hh_link_matched.eq(True)
    linked = source.merge(roster[KEYS].assign(roster_linked=True),on=KEYS,how='left',validate='one_to_one')
    orphan = linked.loc[linked.roster_linked.ne(True)].drop(columns='roster_linked').copy()
    require(len(source)==571638 and len(orphan)==5,'Health source/orphan count differs')
    frame = roster.merge(source.assign(health_linked=True),on=KEYS,how='left',validate='one_to_one')
    for col in ['health_linked','hh_link_matched','screen_variant_conflict','followup_variant_conflict']:
        frame[col] = frame[col].eq(True)
    f = qualify(frame,rules)
    cov = coverage(f)
    matrix = []
    for rule in rules:
        w = rule['survey_wave']
        g = f.loc[f.survey_wave.eq(w)]
        matrix.append({**rule,'roster_members':len(g),'health_source_rows':int(source.survey_wave.eq(w).sum()),
            'linked_source_rows':int(g.health_linked.sum()),'roster_without_health':int((~g.health_linked).sum()),
            'orphan_health_rows':int(orphan.survey_wave.eq(w).sum()),'screen_native_counts':{str(k):int(v) for k,v in g.screen_native.value_counts(dropna=False).items()},
            'screen_status_counts':{str(k):int(v) for k,v in g.screen_status.value_counts().items()},
            'no_with_followup':int(g.no_with_followup.sum()),'injury_with_illness_only':int(g.injury_with_illness_only.sum()),
            'followup_variant_conflicts':int(g.followup_variant_conflict.sum()),
            **{col+'_records':int(g[col].notna().sum()) for col in OUTCOMES}})
    for p in [Path(__file__),ROOT/'rsc/cses_db/validate_cses_health_all_waves.py',
        *[ROOT/'rsc/cses_db'/name for name in ['cses_hh_hl_common.py','build_cses_additional_waves.py','plan_cses_health_illness.py','build_cses_health.py','cache_cses_questionnaires.py','inventory_cses_archives.py','pilot_cses_education_all_waves.py']]]:
        pin(p)
    artifacts = {}
    outputs = {'members.parquet':parquet_bytes(f),'sources.parquet':parquet_bytes(source),
        'orphan_health.parquet':parquet_bytes(orphan),'rules.json':encoded(rules),'matrix.json':encoded(matrix),'coverage.json':encoded(cov),
        'exceptions.parquet':parquet_bytes(f.loc[f.no_with_followup|f.injury_with_illness_only|f.source_form_code_conflict|(~f.health_linked)].reset_index(drop=True))}
    for name,data in outputs.items():
        put(OUT/name,data)
        artifacts[name] = file_sha(OUT/name)
    summary = {'version':'cses-health-all-waves-pilot-v1','database_modified':False,'prototype_not_published':True,
        'roster_members':len(f),'member_columns':len(f.columns),'health_source_records':len(source),'orphan_health_records':len(orphan),
        'roster_without_health':int((~f.health_linked).sum()),'matrix_rows':len(matrix),'coverage_rows':len(cov),
        'qualified_records':{col:int(f[col].notna().sum()) for col in OUTCOMES},'source_checks':checks,
        'inputs':inputs,'artifacts':artifacts,
        'limitations':['2017 same-wave health form remains unverified; 1996 selected topics do not supply a general recent-illness screen.',
            '1997/1999/2004/2007 four-week concepts remain separate; 2011-12 and 2019 are excluded from the strict 30-day default.',
            '2019 code2 conflicts with Injury native labels in both the standalone form and official report appendix; no automatic adjudication.',
            'No treatment-seeking, illness-type, disability, weight or geographic-identity harmonization; no prevalence estimate or imputation.']}
    put(OUT/'report.json',encoded(summary))
    print(json.dumps({k:v for k,v in summary.items() if k not in ['inputs','artifacts','source_checks']},indent=2))
    return summary


if __name__=='__main__':
    build()
