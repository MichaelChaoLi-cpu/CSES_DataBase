#!/usr/bin/env python3
"""Independent native-source, scalar and read-only database acceptance."""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from align_cses_additional_school import KEYS, ROOT, require
from build_cses_additional_waves import encoded, source_keys
from cache_cses_questionnaires import file_sha, put
from cses_education_all_waves_sql import VIEW
from cses_hh_hl_common import DEMOGRAPHIC_ALIASES, AlignmentContext, find_column, snake_case, standardize_source
from inventory_cses_archives import DataSource
from pilot_cses_education_all_waves import EXTRA, TARGETS
from publish_cses_education_unified import OUT, PILOT, checked, compare_person
from publish_cses_geography_interface import connect
from validate_cses_education_all_waves import database_acceptance, equal, number
from validate_cses_education_all_waves_v2 import decide


def native_acceptance(f,rules):
    """Read Stata bytes anew, join by person keys, and compare native facts only."""
    spec = json.loads((ROOT/'rsc/specs/cses_additional_waves_v1.json').read_text())
    alignment = json.loads((ROOT/'data/processing/cses/questionnaire_alignment_v1/alignment.json').read_text())
    historical = pd.read_parquet(ROOT/'data/processing/cses/final_HL_CSES.parquet').rename(columns=snake_case)
    orphans = pd.read_parquet(PILOT/'orphan_education.parquet').sort_values(KEYS).reset_index(drop=True)
    missing,counts = [],[]
    for wave,g in f.groupby('survey_wave',sort=True):
        variables = {r['target']:r['source_variable'] for r in rules if r['survey_wave']==wave}
        if wave in EXTRA:
            cfg = spec['waves'][wave]
            with zipfile.ZipFile(ROOT/cfg['archive']) as z:
                h,e = [pd.read_stata(io.BytesIO(z.read(cfg['modules'][kind]['member'])),convert_categoricals=False) for kind in ['HL','ED']]
            for raw in [h,e]:
                raw['household_key'] = source_keys(raw,cfg['household_key'],wave)
                raw['record_key'] = source_keys(raw,cfg['household_key']+[cfg['person_key']],wave)
            from build_cses_additional_waves import fields_for
            agevar = fields_for(spec,cfg['modules']['HL'])['Age Source Value'][0]
            selected = h['age'] if wave=='2025' else h[agevar]
        else:
            old = historical.loc[historical.survey_wave.eq(wave)]
            hl = DataSource(ROOT/old.source_archive.iloc[0],tuple(old.source_submodule.iloc[0].split('::')))
            link = next(r for r in alignment['source_links'] if r['survey_wave']==wave and r['module_code']=='education'
                and ['final_ED_CSES','can_read'] in r['canonical_keys'])
            ed = DataSource(ROOT/link['archive_relative_path'],tuple(p for p in [link['member_path'],link['nested_member_path']] if p))
            h,e = [pd.read_stata(io.BytesIO(s.read_bytes()),convert_categoricals=False) for s in [hl,ed]]
            for raw,source,kind in [(h,hl,'HL'),(e,ed,'ED')]:
                context = AlignmentContext(root=ROOT)
                context.frames[source.display_name(ROOT)] = raw
                keys = standardize_source(context,source,wave,kind).rename(columns=snake_case)
                raw['household_key'],raw['record_key'],raw['source_row_id'] = keys.household_id,keys.person_id,keys.source_row_id
            agevar = find_column(h,DEMOGRAPHIC_ALIASES['Age'])
            selected = h[agevar].where(h[agevar].between(0,120)&h[agevar].mod(1).eq(0))
            if wave=='2004':
                selected = selected.where(~selected.isin([98,99]))
        require(h.record_key.is_unique and e.record_key.is_unique,'Duplicate native keys')
        raw = pd.DataFrame({'survey_wave':wave,'household_key':h.household_key,'record_key':h.record_key,
            'age_source_value':h[agevar],'age_for_analysis':selected,'education_linked':h.record_key.isin(e.record_key)})
        indexed = e.set_index('record_key')
        for t,var in variables.items():
            raw[t+'_native'] = h.record_key.map(indexed[var]) if var else float('nan')
        cols = list(raw)
        actual = g[cols].sort_values(KEYS).reset_index(drop=True)
        raw = raw.sort_values(KEYS).reset_index(drop=True).astype(actual.dtypes.to_dict())
        pd.testing.assert_frame_equal(raw,actual,check_exact=True)
        unmatched = e.loc[~e.record_key.isin(h.record_key)]
        if len(unmatched):
            o = unmatched[['household_key','record_key','source_row_id']].copy()
            o['survey_wave'] = wave
            for t,var in variables.items():
                o[t+'_native'] = unmatched[var] if var else float('nan')
            missing.append(o)
        counts.append({'survey_wave':wave,'roster_records':len(h),'education_records':len(e),
            'linked_education':int(raw.education_linked.sum()),'orphan_records':len(unmatched),'native_mismatches':0})
    actual_orphans = pd.concat(missing)[list(orphans)].sort_values(KEYS).reset_index(drop=True).astype(orphans.dtypes.to_dict())
    pd.testing.assert_frame_equal(actual_orphans,orphans,check_exact=True)
    return counts


def scalar_acceptance(f,book,coverage):
    lookup = {(r['survey_wave'],r['target'],r['source_code']):r for r in book}
    counters = defaultdict(Counter)
    for r in f.itertuples(index=False):
        expected = decide(r,lookup.get((r.survey_wave,'highest',number(r.highest_native))),
            lookup.get((r.survey_wave,'current',number(r.current_native))))
        require(all(equal(getattr(r,k),v) for k,v in expected.items()),'Independent scalar mismatch: '+r.survey_wave)
        age = number(r.age_for_analysis)
        for band,inband in [('questionnaire_universe',expected['age_eligible']),
            ('ages_6_17',age is not None and 6<=age<=17),('ages_15_plus',age is not None and age>=15)]:
            if not inband:
                continue
            for t in TARGETS:
                c = counters[r.survey_wave,band,t]
                q,gate = expected[t+'_qualified'],expected[t+'_expected_by_route']
                c['age_band_members'] += 1
                c['expected_by_route'] += gate
                c['raw_non_null'] += number(getattr(r,t+'_native')) is not None
                c['qualified_records'] += q is not None
                c['unresolved_expected'] += gate and q is None
                if t not in ['highest','current','years']:
                    c['qualified_yes'] += q==1
                    c['qualified_no'] += q==0
    for row in coverage:
        c = counters[row['survey_wave'],row['age_band'],row['target']]
        require(all(row[k]==v for k,v in c.items()),'Independent denominator mismatch')
        if row['survey_wave']=='2017' and row['age_band']=='questionnaire_universe':
            require(row['age_band_members'] is None,'Unverified universe cannot become zero people')
    return {'classified_field_records':len(f)*8,'scalar_mismatches':0,'denominator_rows':360}


def main(database=False):
    from cses_education_all_waves_sql import BOOK, RULE
    f,tables,e = checked()
    result = {'passed':True,'database_modified':False,'database_accessed':database,
        'evidence_sha256':file_sha(OUT/'evidence.json'),'validator_sha256':file_sha(Path(__file__)),
        'native':native_acceptance(f,tables[RULE]),
        **scalar_acceptance(f,tables[BOOK],e['coverage'])}
    if database:
        with connect() as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            conn.execute('SET LOCAL ROLE mda_readonly')
            require(conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on','Read-only required')
            compare_person(conn,f'SELECT * FROM {VIEW}',None,f)
        result['database'] = database_acceptance(f)
        result['published_sha256'] = file_sha(OUT/'published.json')
    put(OUT/('independent-database.json' if database else 'independent-local.json'),encoded(result))
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',action='store_true')
    main(parser.parse_args().database)
