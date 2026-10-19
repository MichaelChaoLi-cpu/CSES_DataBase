#!/usr/bin/env python3
"""Audit supplied source/cached-form integrity and selected missingness; no DB writes."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
from build_cses_additional_waves import encoded, verify
from cache_cses_questionnaires import file_sha, put

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'data/processing/cses/additional_waves_v1'
FORMS = ROOT/'data/processed/cses_questionnaires/additional_waves_v1'
OUT = ROOT/'data/processing/cses/source_gap_audit_v1'


def read_member(archive,member,columns):
    return pd.read_stata(io.BytesIO(archive.read(member)),columns=columns,convert_categoricals=False)


def main():
    verified = verify(ROOT)
    spec = json.loads((ROOT/'rsc/specs/cses_additional_waves_v1.json').read_text())
    datasets = json.loads((BASE/'datasets.json').read_text())
    form_sources = json.loads((FORMS/'sources.json').read_text())
    result = {'scope':'Five supplied waves; source integrity, all 171 selected field profiles, focused routing checks',
              'database_modified':False,'script_sha256':file_sha(Path(__file__)),
              'candidate_manifest_sha256':file_sha(BASE/'manifest.json'),'candidate_cache_verification':verified,
              'waves':{},'low_coverage_fields':[],'nonbinary_recode_exceptions':[]}
    for wave,cfg in spec['waves'].items():
        path = ROOT/cfg['archive']
        if file_sha(path)!=cfg['sha256']:
            raise ValueError('Archive fingerprint changed')
        with zipfile.ZipFile(path) as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise ValueError('Corrupt ZIP member: '+corrupt)
            names = [n for n in archive.namelist() if not any(p.startswith('._') or p=='__MACOSX' for p in Path(n).parts)]
            observed = {n for n in names if n.lower().endswith('.dta')}
            registered = {d['member'] for d in datasets if d['wave']==wave}
            if observed != registered:
                raise ValueError('Native dataset inventory mismatch')
            documents = {n for n in names if Path(n).suffix.lower() in {'.doc','.docx','.pdf','.xls','.xlsx','.xlsm'}}
            cached = [r for r in form_sources if r['wave']==wave]
            if documents != {r['source_member'] for r in cached}:
                raise ValueError('Uncached document in supplied archive')
            for r in cached:
                if file_sha(FORMS/r['local_path']) != r['sha256']:
                    raise ValueError('Cached questionnaire changed')
            result['waves'][wave] = {'source_datasets':len(observed),'archive_sha256':cfg['sha256'],
                                     'zip_crc_passed':True,'document_members':sorted(documents),
                                     'cached_documents_complete_relative_to_supplied_archive':True}
            if wave=='1996':
                d = read_member(archive,'qrt02s96_PersonFile.dta',['c10','c11'])
                result['disability_1996'] = {'screen_yes':int(d.c10.eq(1).sum()),
                    'type_answered_screen_yes':int((d.c10.eq(1)&d.c11.notna()).sum()),
                    'screen_no':int(d.c10.eq(2).sum()),
                    'type_missing_screen_no':int((d.c10.eq(2)&d.c11.isna()).sum())}
            if wave=='2025':
                a = read_member(archive,'S01A_HHmember.dta',['q01ac05a','age','q01ac04c','q01ac09'])
                both = a.q01ac05a.notna()&a.age.notna()
                result['age_2025'] = {'rows':len(a),'selected_age_non_null':int(a.q01ac05a.notna().sum()),
                    'native_calculated_age_non_null':int(a.age.notna().sum()),
                    'overlap':int(both.sum()),'overlap_disagreements':int(a.loc[both,'q01ac05a'].ne(a.loc[both,'age']).sum()),
                    'selected_age_present_birth_year_unknown':int((a.q01ac05a.notna()&a.q01ac04c.eq(-98)).sum()),
                    'selected_age_present_birth_year_known':int((a.q01ac05a.notna()&a.q01ac04c.ne(-98)).sum())}
                result['marital_2025'] = {'under_13':int(a.age.lt(13).sum()),
                    'under_13_missing':int((a.age.lt(13)&a.q01ac09.isna()).sum()),
                    'age_13_plus':int(a.age.ge(13).sum()),
                    'age_13_plus_answered':int((a.age.ge(13)&a.q01ac09.notna()).sum())}
                h = read_member(archive,'S13B_PersonIllness.dta',['q13bc2a','q13bc2b','q13bc06','q13bc07a','q13bc08a','q13bc09a'])
                result['health_2025'] = []
                for code,g in h.groupby('q13bc2a'):
                    result['health_2025'].append({'screen_code':int(code),'rows':len(g),
                        'illness_type_answered':int(g.q13bc2b.notna().sum()),
                        'treatment_sought_answered':int(g.q13bc06.notna().sum()),
                        'first_provider_answered':int(g.q13bc09a.notna().sum()),
                        'healthcare_frequency_answered':int(g.q13bc08a.notna().sum())})
                e = read_member(archive,'S15_PersonEcoCurrent.dta',['s15q14','s15q20'])
                result['availability_2025'] = [{'job_search_code':None if pd.isna(k) else int(k),
                    'records':len(g),'availability_answered':int(g.s15q20.notna().sum())}
                    for k,g in e.groupby('s15q14',dropna=False)]
    rows = {(d['wave'],d['member']):d['rows'] for d in datasets}
    profiles = []
    for p in json.loads((BASE/'field_alignment.json').read_text()):
        n = rows[p['wave'],p['source_member']]
        r = {k:p[k] for k in ['wave','module','target','source_member','source_variable','source_label','source_non_null','mapped_non_null','unmapped_non_null']}
        r.update({'source_rows':n,'source_null':n-p['source_non_null'],
                  'source_non_null_pct':round(100*p['source_non_null']/n,4) if n else None,
                  'interpretation':'Null does not establish missing response; eligibility and routing must be reviewed.'})
        profiles.append(r)
        if n and p['source_non_null']/n<.05:
            result['low_coverage_fields'].append(r)
        if p['unmapped_non_null']:
            result['nonbinary_recode_exceptions'].append(r)
    result['selected_field_wave_profiles']=len(profiles)
    result['profile_sha256']=put(OUT/'field_profiles.json',encoded(profiles))
    result['questionnaire_text_hashes']={str(p.relative_to(FORMS)):file_sha(p) for p in [
        FORMS/'2025/text/CSES2025_Household_Questionnaire_ENG.md',
        FORMS/'1997/text/QuestENG_Form3.md',
        FORMS/'legacy_word_text_v1/1999/QuestENG_Form3Page.txt']}
    result['limitations']=['Completeness is relative to supplied archives, not the full official survey distribution.',
        'Not an exhaustive item-by-item response audit of all 5,427 native variable occurrences.',
        'Source nulls, structural skips, code exceptions, unavailable modules and projection omissions remain distinct.',
        'The 2025 illness/treatment routing mismatch is unresolved; no automatic No imputation is authorized.',
        'Date and village modules not built do not establish absence of native source data or forms.']
    put(OUT/'summary.json',encoded(result))
    print(json.dumps({k:v for k,v in result.items() if k not in {'low_coverage_fields','nonbinary_recode_exceptions','candidate_cache_verification'}},indent=2))


if __name__=='__main__':
    main()
