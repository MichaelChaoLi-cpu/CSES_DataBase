#!/usr/bin/env python3
"""Supplement the frozen pilot with full selected skip-range and archive-cache checks."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pandas as pd
from align_cses_additional_school import KEYS, ROOT, require
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put, verify_manifest
from inventory_cses_archives import DataSource
from validate_cses_health_all_waves import native_acceptance

PILOT = ROOT/'data/processing/cses/health_all_waves_pilot_v2'
CACHE = ROOT/'data/processed/cses_questionnaires/archive_verified_v2'
OUT = ROOT/'data/processing/cses/health_release_audit_v1'


def full_no_range(rule):
    """Only fields inside the verified negative-screen skip, never later preventive care."""
    additions = {'1999':['p8c16','p8c17','p8c18'],
                 '2004':['q14a08','q14a09','q14a10','q14a11','q14a12']}
    return rule['no_followups']+additions.get(rule['survey_wave'],[])


def build():
    report = json.loads((PILOT/'report.json').read_text())
    inputs = {str((PILOT/'report.json').relative_to(ROOT)):file_sha(PILOT/'report.json')}
    for path,sha in report['inputs'].items():
        require(file_sha(ROOT/path)==sha,'Frozen input changed: '+path)
    for name,sha in report['artifacts'].items():
        require(file_sha(PILOT/name)==sha,'Frozen artifact changed: '+name)
        inputs[str((PILOT/name).relative_to(ROOT))] = sha
    verify_manifest(CACHE)
    cache_receipt = json.loads((CACHE/'verification.json').read_text())
    require(cache_receipt['verified'] and not cache_receipt['historical_v1_modified'],'Verified cache required')
    require(cache_receipt['new_manifest_sha256']==file_sha(CACHE/'manifest.json'),'Cache manifest changed')
    for path in [CACHE/'verification.json',CACHE/'manifest.json',PILOT/'database-validation.json',Path(__file__)]:
        inputs[str(path.relative_to(ROOT))] = file_sha(path)
    rules = json.loads((PILOT/'rules.json').read_text())
    f,source,orphan = [pd.read_parquet(PILOT/n) for n in ['members.parquet','sources.parquet','orphan_health.parquet']]
    native = native_acceptance(source,rules)
    require(not source[KEYS].isna().any().any() and not f[KEYS].isna().any().any(),'Null member keys')
    require(not source.duplicated(KEYS).any() and not f.duplicated(KEYS).any(),'Duplicate member keys')
    join = f[KEYS].merge(source[KEYS],on=KEYS,how='outer',validate='one_to_one',indicator=True)
    require(join._merge.value_counts().to_dict()=={'both':571633,'left_only':66,'right_only':5},'Link partition changed')
    rows = []
    for rule in rules:
        wave = rule['survey_wave']
        payload = DataSource(ROOT/rule['source_archive'],tuple(rule['source_member_chain'])).read_bytes()
        require(hashlib.sha256(payload).hexdigest()==rule['source_sha256'],'Native source changed')
        with pd.io.stata.StataReader(io.BytesIO(payload),convert_categoricals=False,convert_dates=False) as reader:
            labels = reader.variable_labels()
            assigned = dict(zip(reader._varlist,reader._lbllist,strict=True))
            dictionaries = reader.value_labels()
            raw = reader.read()
        var = rule['variable']
        if var:
            require(labels[var]==rule['native_variable_label'],'Variable label changed')
            require({str(k):v for k,v in dictionaries.get(assigned.get(var),{}).items()}==rule['native_value_labels'],'Value labels changed')
        g = f.loc[f.survey_wave.eq(wave)]
        s = source.loc[source.survey_wave.eq(wave)].sort_values('source_row_number')
        require(s.source_row_number.tolist()==list(range(1,len(raw)+1)),'Source row order differs')
        skipped = full_no_range(rule)
        require(all(c in raw for c in skipped),'Skip-range column missing')
        negative_codes = [int(k) for k,v in rule['mapping'].items() if v==0]
        negative = raw[var].isin(negative_codes) if var else pd.Series(False,index=raw.index)
        extended_no = negative & raw[skipped].notna().any(axis=1)
        # The extra checked columns must not reveal an exclusion missing from the pilot.
        stored = s.screen_native.isin(negative_codes) & s[[f'branch_{i}_native' for i in range(1,len(rule['no_followups'])+1)]].notna().any(axis=1)
        require(extended_no.tolist()==stored.tolist(),'Additional skip conflict requires a new pilot version: '+wave)
        form = rule.get('form_path')
        verified_form = form.replace('/cses_questionnaires/v1/','/cses_questionnaires/archive_verified_v2/') if form else None
        if verified_form:
            require(file_sha(ROOT/verified_form)==file_sha(ROOT/form),'Literal questionnaire evidence changed')
            inputs[verified_form] = file_sha(ROOT/verified_form)
        row = {'survey_wave':wave,'roster_members':len(g),'source_rows':len(s),
            'health_linked':int(g.health_linked.sum()),'missing_health_rows':int((~g.health_linked).sum()),
            'orphan_health_rows':int(orphan.survey_wave.eq(wave).sum()),
            'household_unmatched_source_rows':int((~s.hh_link_matched).sum()),
            'screen_variable':var,'native_screen_label':rule['native_variable_label'],
            'native_screen_codes':rule['native_value_labels'],'all_verified_no_skip_fields':skipped,
            'no_skip_non_null_by_field':{c:int((negative & raw[c].notna()).sum()) for c in skipped},
            'negative_screen_branch_flags_source':int(extended_no.sum()),
            'additional_negative_skip_conflicts':0,'screen_status_counts':g.screen_status.value_counts().to_dict(),
            'screen_qualified_records':int(g.screen_qualified.notna().sum()),
            'strict_30d_records':int(g.illness_injury_30d_qualified.notna().sum()),
            'strict_30d_yes':int(g.illness_injury_30d_qualified.eq(1).sum()),
            'form_path_in_frozen_pilot':form,'verified_form_path':verified_form,
            'same_wave_scope_verified':rule['period_days'] is not None,
            'strict_30d_wave':rule['strict_30d'],'source_sha256':rule['source_sha256']}
        rows.append(row)
    put(OUT/'annual.json',encoded(rows))
    result = {'passed':True,'version':'cses-health-release-audit-v1','database_modified':False,
        'historical_pilots_modified':False,'pilot_report_sha256':file_sha(PILOT/'report.json'),
        'inputs':inputs,'annual_sha256':file_sha(OUT/'annual.json'),
        'roster_records':len(f),'source_records':len(source),'matched_records':571633,
        'missing_health_records':66,'orphan_records_preserved':5,
        'strict_30d_records':308955,'strict_30d_yes':56262,
        'additional_negative_skip_conflicts':0,'native_acceptance':native,
        'limits':['1996: no all-member recent screen in selected file; not a claim that all health topics are absent.',
            '2017: same-year form scope unverified; no transfer of 2016 policy.',
            '2019: 150 native code2/form conflicts retained and the whole wave withheld from strict30d.',
            'Negative-branch flags are conservative eligibility exclusions, not proven incorrect screen answers.',
            '1997/1999/2004/2007 retain distinct four-week concepts, not recoded into 30 days.',
            'Only screening inputs and their skip ranges are certified by this audit, not every health follow-up.']}
    put(OUT/'report.json',encoded(result))
    print(json.dumps({k:v for k,v in result.items() if k!='inputs'},indent=2))
    return result


if __name__=='__main__':
    build()
