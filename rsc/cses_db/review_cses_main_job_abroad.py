#!/usr/bin/env python3
"""Review the already stored main-job abroad item without changing published data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from organize_cses_questionnaires import digest, write_once
from review_cses_education import BASE, load_inputs, normalize_legacy_source_paths, selected_sources, verify_workbooks
from review_cses_employment_hours_status import registry, stata_metadata, variable_entry
from review_cses_main_job_seasonal import CURRENT, CURRENT_SHA, LEGACY, YEAR
from review_cses_main_job_whole_year import CONTEXT, EXECUTION, PINS, counts, recode
from review_cses_main_job_whole_year import evidence as whole_year_evidence
from review_cses_main_job_whole_year import route as screen_route
from review_cses_questionnaires import parse_options, require

SELF='rsc/cses_db/review_cses_main_job_abroad.py'
OUTPUT='data/processing/cses/main_job_abroad_review_v1'
FIELD='main_job_was_abroad'
PRIOR='data/processing/cses/main_job_seasonal_review_v1/review.json'
PRIOR_SHA='9536f439336108de787634a653eb882493d89b4a8e33673a996830d2300bcff7'
LAYOUTS={
    '2011-12':('15 Econo_Status_1','CR10','CR19','CR15','CR6'),
    '2013':('15 Econo_Status_1','CM12','CM19','CM17','CM6'),
    '2014':('15 Econo_Status_1','CM12','CM19','CM17','CM6'),
    '2016':('15 Econo_Status_1','CM12','CM19','CM17','CM6'),
    '2021':('15 Current Econo-2','T17','T24','T22','T11'),
}


def evidence(root):
    spec,alignment,inventory,extracts=load_inputs(root)
    sheets={s['source_file']:s['sheets'] for s in extracts}
    years,_=whole_year_evidence(root)
    questions,earlier=[],[]
    for source in selected_sources(spec,inventory):
        wave=source['survey_wave']
        if wave not in LAYOUTS:
            selected={sn:cs for sn,cs in sheets[source['source_file']].items() if sn.startswith('13 ' if wave=='2004' else '15 ')}
            hits=[{'sheet':sn,'cell':c,'text':t} for sn,cs in selected.items() for c,t in cs.items()
                  if 'foreign country' in t.lower() or 'abroad' in t.lower() or t.strip()=='(10d)']
            require(not hits,'Unexpected abroad question in earlier selected form')
            earlier.append({'survey_wave':wave,'source_file':source['source_file'],'source_sha256':source['source_sha256'],
                'sheets_checked':sorted(selected),'search_terms':['foreign country','abroad','exact (10d)'],
                'matches':hits,'scope':'Selected English current-employment sheets only; not proof of noncollection in every source'})
            continue
        sn,text,code,option,gate=LAYOUTS[wave]
        cs=sheets[source['source_file']][sn]
        links=[r for r in alignment['source_links'] if r['survey_wave']==wave and ['final_EC_CSES',FIELD] in r['canonical_keys']]
        require(len(links)==1 and links[0]['variable_name'].lower()=='q15_c10d','Unique raw-variable identity required')
        link=links[0]
        candidates=[q for q in inventory['questions'] if q['source_file']==source['source_file'] and q['source_sheet']==sn and q['question_code_cell']==code]
        require(len(candidates)==1 and text in candidates[0]['text_cell_candidates'] and candidates[0]['candidate_id'] in link['candidate_ids'],'Exact historical candidate required')
        opts=parse_options({option:cs[option]})
        require(cs[code]=='(10d)' and [(o['source_code'],o['label_as_printed'].strip()) for o in opts]==[(1,'Yes'),(2,'No')],'Exact question and binary meanings required')
        require('main occupation/ economic activity done in a foreign country?' in cs[text],'Full question meaning changed')
        require('Col 3 = 1' in cs[gate] and 'Col 4 = 1' in cs[gate] and ' or ' in cs[gate].replace('\n',' '),'Literal OR gate changed')
        year=next(q for q in years if q['survey_wave']==wave)
        require('>>10d' in year['options'][0]['label_as_printed'].replace(' ',''),'Whole-year Yes must bypass 10c to 10d')
        questions.append({'survey_wave':wave,'field':FIELD,'source_variable':link['variable_name'],'source_variable_id':link['source_variable_id'],
            'candidate_id':candidates[0]['candidate_id'],'source_file':source['source_file'],'source_sha256':source['source_sha256'],
            'source_sheet':sn,'question_text_cell':text,'question_code_cell':code,'options_cell':option,'gate_cell':gate,
            'question_text':cs[text],'options':opts,'option_count':2,'gate_text':cs[gate],
            'prior_whole_year_question':year,'documentation_status':source['documentation_status'],
            'minimum_age':5,'whole_year_or_seasonal_answer_required':False,'whole_variable_certified':False})
    require(len(questions)==5 and len(earlier)==2,'Five complete questions and two earlier checks required')
    return questions,earlier


def route(frame,wave):
    # Item 10d has its own OR-screen gate; do not import item 10c's 10b=No condition.
    return None if wave not in LAYOUTS else screen_route(frame,wave)


def data_review(root):
    import pandas as pd
    from cses_employment import employment_sources, prepare_wave_sources, source_value
    from cses_hh_hl_common import AlignmentContext, snake_case

    frame=pd.read_parquet(root/'data/processing/cses/final_EC_CSES.parquet').rename(columns=snake_case)
    require(frame.shape==(332903,60) and not frame.duplicated(['survey_wave','person_id']).any(),'Frozen EC grain changed')
    profiles=[]
    for wave,sources in employment_sources(root):
        keys,aligned=prepare_wave_sources(AlignmentContext(root=root),wave,sources)
        keys=keys.rename(columns=snake_case)
        current=frame.loc[frame.survey_wave.eq(wave)].set_index('person_id')
        require(len(current)==len(keys) and set(current.index)==set(keys.person_id),'Raw key mismatch')
        current=current.loc[keys.person_id].reset_index()
        for col in ['household_id','source_archive','source_submodule','source_row_id']:
            pd.testing.assert_series_equal(keys[col].astype(current[col].dtype),current[col],check_names=False)
        raw,column=source_value(aligned,['q15_c10d'])
        expected=pd.Series(pd.NA,index=current.index,dtype='Int8')
        meta,entry=None,None
        if column:
            entry=variable_entry(registry(root),wave,column)
            meta={k:v for s in sources for k,v in stata_metadata(s).items()}[column]
            require(meta=={k:entry[k] for k in ['variable_label','value_labels']},'Fresh Stata metadata differs')
            expected=recode(raw)
        pd.testing.assert_series_equal(expected,current[FIELD],check_names=False)
        observed=expected.notna()
        mask=route(current,wave)
        profiles.append({'survey_wave':wave,'rows':len(current),'source_variable':column,
            'source_variable_id':entry['source_variable_id'] if entry else None,'fresh_stata_metadata':meta,
            'source_files':[{'source_file':s.display_name(root),'sha256':digest(s.read_bytes())} for s in sources],
            'raw_nonnull':int(raw.notna().sum()) if raw is not None else 0,'raw_values':counts(raw) if raw is not None else {},
            'discarded_raw_values':counts(raw.loc[raw.notna()&expected.isna()]) if raw is not None else {},
            'yes':int(expected.eq(1).sum()),'no':int(expected.eq(0).sum()),'nonnull':int(observed.sum()),'null':int((~observed).sum()),
            'literal_route_records':int(mask.fillna(False).sum()) if mask is not None else None,
            'nonnull_within_route':int((observed&mask.fillna(False)).sum()) if mask is not None else None,
            'nonnull_outside_known_route':int((observed&mask.eq(False).fillna(False)).sum()) if mask is not None else None,
            'nonnull_route_unknown':int((observed&mask.isna()).sum()) if mask is not None else None,
            'route_unknown_records':int(mask.isna().sum()) if mask is not None else None,
            'within_route_null':int((~observed&mask.fillna(False)).sum()) if mask is not None else None,
            'nonnull_with_whole_year_yes':int((observed&current[YEAR].eq(1)).sum()),
            'nonnull_without_seasonal_response':int((observed&current[LEGACY].isna()).sum()),
            'hl_unmatched':int(current.hl_link_matched.eq(0).sum()),'raw_to_canonical_equal':True})
    return frame,profiles


def check_database(frame):
    import pandas as pd
    from cses_baseline_metadata import connect_database
    from psycopg import sql
    from publish_cses_age_topcode import read_only

    columns=CONTEXT+[FIELD,YEAR,LEGACY]
    expected=frame[columns].sort_values(['survey_wave','person_id']).reset_index(drop=True)
    relations=[('cses_data','final_EC_CSES'),('cses_analysis','cses_ec_classification_v1')]
    with connect_database({'dbname':'mda'}) as conn:
        read_only(conn)
        for schema,name in relations:
            query=sql.SQL('SELECT {} FROM {} ORDER BY survey_wave,person_id').format(sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier(schema,name))
            live=pd.DataFrame(conn.execute(query).fetchall()).astype(expected.dtypes.to_dict())
            live.source_archive=normalize_legacy_source_paths(live.source_archive)
            pd.testing.assert_frame_equal(live,expected,check_exact=True)
    return {'transaction_read_only':True,'all_selected_cells_equal':True,'columns':columns,
        'relations':['.'.join(r) for r in relations],'rows_per_relation':len(frame),'full_relation_validation':False}


def make_review(root,verification,live):
    from plan_cses_age_topcode import checked_review

    checked_review(root)
    pins={**PINS,PRIOR:PRIOR_SHA,CURRENT:CURRENT_SHA}
    for path,sha in pins.items():
        require(digest((root/path).read_bytes())==sha,f'Frozen dependency changed: {path}')
    for path,sha in json.loads((root/EXECUTION).read_text())['file_sha256'].items():
        require(digest((root/path).read_bytes())==sha,f'Published dependency changed: {path}')
    prior=json.loads((root/PRIOR).read_text())
    for path,sha in prior['frozen_inputs'].items():
        require(digest((root/path).read_bytes())==sha,f'Prior review dependency changed: {path}')
    require(digest((root/'rsc/cses_db/review_cses_main_job_seasonal.py').read_bytes())==prior['implementation_sha256'],'Prior seasonal review changed')
    year=json.loads((root/'data/processing/cses/main_job_whole_year_review_v1/review.json').read_text())
    require(digest((root/'rsc/cses_db/review_cses_main_job_whole_year.py').read_bytes())==year['implementation_sha256'],'Prior whole-year helper changed')
    verified=json.loads(verification.read_text())
    require(verified['source_cells_sha256']==digest((root/BASE/'source_cells.json').read_bytes()),'Source extraction changed')
    require(verified['implementation_sha256']==digest((root/'rsc/cses_db/review_cses_education.py').read_bytes()),'Workbook verifier changed')
    require(len(verified['sources'])==7 and all(s['all_sheets_equal'] for s in verified['sources']),'Seven fresh workbook checks required')
    questions,earlier=evidence(root)
    frame,profiles=data_review(root)
    return {'review_id':'cses-main-job-abroad-review-v1','field':FIELD,'implementation_sha256':digest((root/SELF).read_bytes()),
        'frozen_inputs':pins,'source_verification':verified,'questions':questions,'earlier_inspected_forms':earlier,'profiles':profiles,
        'scope_counts':{'batch_fields':1,'cumulative_reviewed_ec_fields':20,'remaining_ec_fields':19,'rows':len(frame),
            'field_wave_profiles':len(profiles),'raw_field_wave_mappings':sum(p['source_variable'] is not None for p in profiles),
            'question_wave_correspondences':len(questions),'nonnull':sum(p['nonnull'] for p in profiles),
            'yes':sum(p['yes'] for p in profiles),'no':sum(p['no'] for p in profiles),
            'raw_nonnull':sum(p['raw_nonnull'] for p in profiles),
            'inherited_nonbinary_exclusions':sum(sum(p['discarded_raw_values'].values()) for p in profiles),
            'fully_certified_all_ten_wave_fields':0},
        'database_check':check_database(frame) if live else {'performed':False},
        'database_mutated':False,'canonical_data_mutated':False,'individual_records_saved':False,'new_question_links_published':False}


def document(r):
    c=r['scope_counts']
    lines=['# Main job performed in a foreign country','',
        f"`{FIELD}` (`q15_c10d`, case varies) is already stored in the physical EC table and the current `cses_analysis.cses_ec_classification_v1` view. "
        '**20 of 39 EC fields have now been reviewed; 19 remain.** Reviewed means detailed evidence and value checks, not that every year is fully comparable.','',
        '## Meaning and choices','',
        'Five complete inspected questions ask whether the person’s main occupation/economic activity is done in a foreign country. '
        'The existing name is consistent with that meaning. There are **two choices: raw 1 = Yes, raw 2 = No; stored 1 = Yes, stored 0 = No**. '
        'NULL is not No. The item concerns the location of the main job, not nationality, migration status or employment by a foreign-owned company inside Cambodia. '
        'It belongs to the current/past-seven-days employment block, including its temporary-absence route; the question does not independently measure days spent abroad.','',
        '## Availability','',
        f"Across {c['rows']:,} EC member-wave records there are **{c['nonnull']:,} non-null values: {c['yes']:,} Yes and {c['no']:,} No**. "
        'These are unweighted member-wave observations, not actual interview respondents or unique people followed across years.','',
        '| Wave | EC records | Yes | No | Non-null | NULL | Question evidence |',
        '| --- | ---: | ---: | ---: | ---: | ---: | --- |']
    for p in r['profiles']:
        w=p['survey_wave']
        status='Draft complete question' if w=='2014' else 'Complete selected question' if w in LAYOUTS else 'Truncated foreign-country wording + Yes/No labels; route unverified' if w=='2019' else 'Source column present; household question unverified' if w=='2017' else 'No exact column in selected source'
        lines.append('| '+' | '.join([w,*[f"{p[k]:,}" for k in ['rows','yes','no','nonnull','null']],status])+' |')
    lines += ['',
        'The exact raw alias is absent from the selected 2004, 2007 and 2009 current-employment data. No abroad item was found by the recorded '
        'phrase/item search in the selected 2004/2009 English current-employment sheets. These are scoped findings, not proof that no related information exists anywhere. '
        '2017 lacks verified household question evidence. Unlike seasonal 10c, the 2019 Stata label retains the meaningful phrase “done in a foreign co”, '
        'supporting the foreign-country interpretation, but it is still truncated and does not establish the complete question or route. '
        'No route is borrowed for either year and no full cross-wave certification is asserted. The 2014 form remains a draft.','',
        '## Routing and exceptions','',
        'Question 10d has its own literal gate: age 5+ and first work-screen Yes **OR** second work-screen Yes. '
        'It does **not** require whole-year No, a seasonal Yes/No, or even a non-null seasonal response. Whole-year Yes explicitly skips 10c and goes to 10d. '
        'Do not filter this variable using the preceding seasonal item’s route.','',
        'The 2021 printed gate still mentions temporary absence although the revised second screen asks about unpaid work. '
        'The numeric OR condition is retained as a literal diagnostic, with the wording conflict unresolved. '
        'Responses outside the route are kept, not overwritten or treated as proof that the gate is wrong.','',
        '| Wave | Literal route | Non-null inside | Non-null outside | Non-null, route unknown | NULL inside route |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    assessed=[p for p in r['profiles'] if p['survey_wave'] in LAYOUTS]
    for p in assessed:
        lines.append('| '+' | '.join([p['survey_wave'],*[f"{p[k]:,}" for k in ['literal_route_records','nonnull_within_route','nonnull_outside_known_route','nonnull_route_unknown','within_route_null']]])+' |')
    lines += ['',
        f"In the five inspected-question waves, {sum(p['nonnull_outside_known_route'] for p in assessed):,} non-null values are outside the literal route, "
        f"{sum(p['nonnull_route_unknown'] for p in assessed):,} have an unknown route, and {sum(p['within_route_null'] for p in assessed):,} eligible records have no stored answer. "
        'These are diagnostics rather than a certified analytical denominator.','',
        f"Those five waves include {sum(p['nonnull_with_whole_year_yes'] for p in assessed):,} non-null abroad responses with whole-year Yes, "
        f"and {sum(p['nonnull_without_seasonal_response'] for p in assessed):,} with a missing seasonal response. These groups overlap and must not be added. "
        'Neither pattern is itself a skip violation for 10d. The two pre-existing unmatched EC→HL records remain; missing age can make route eligibility unknown.','',
        f"The inherited binary conversion excluded {c['inherited_nonbinary_exclusions']:,} non-null raw codes from {c['raw_nonnull']:,} original non-null codes. "
        'The review records the exact raw frequencies and any exclusions. No new recoding or imputation is applied.','']
    excluded=[p for p in r['profiles'] if p['discarded_raw_values']]
    if excluded:
        lines += ['| Wave | Excluded raw codes |','| --- | --- |']
        lines += ['| '+p['survey_wave']+' | '+', '.join(f'{code}: {n}' for code,n in p['discarded_raw_values'].items())+' |' for p in excluded]
        lines += ['']
    lines += ['## Source locators and verification','',
        '| Wave | Raw variable | Sheet | Text / code / options | Gate |','| --- | --- | --- | --- | --- |']
    for q in r['questions']:
        lines.append(f"| {q['survey_wave']} | {q['source_variable']} | {q['source_sheet']} | {q['question_text_cell']} / {q['question_code_cell']} / {q['options_cell']} | {q['gate_cell']} |")
    lines += ['',
        'The [aggregate review](../data/processing/cses/main_job_abroad_review_v1/review.json) includes exact question/option/gate text, '
        'source-variable and candidate identities, seven raw-field reproductions, fresh Stata labels, hashes and ten field-wave profiles. '
        'The spreadsheets skill guided separate wording, choice and skip checks. All seven selected original workbooks were freshly re-extracted, '
        'with every sheet matching the frozen evidence and no original workbook edits.','',
        ('A forced read-only transaction matched all 13 selected columns across 332,903 rows in both the physical EC table and current classification view. '
         'This includes the reviewed value, whole-year/seasonal context and identity/provenance. It is not a full 86-column view validation.'
         if r['database_check'].get('all_selected_cells_equal') else 'Live database verification was not performed.'),'',
        '```mermaid','flowchart LR','    A["Age 5+ and first OR second work screen Yes"] --> Y["10b: whole-year work"]',
        '    Y -->|Yes: skip 10c| D["10d: main job in a foreign country"]',
        '    Y -->|No| S["10c: seasonal work"]','    S --> D','    D --> B["Raw 1/2 to stored 1/0; no route filtering"]','```','',
        'The diagram describes the five inspected forms, with the 2014 draft and 2021 gate qualification above. It is not a new database topology. '
        'Published graph v14 and all prior database objects/releases remain unchanged. No interpretation overlay, question-link publication, Git commit or DVC push is performed.','',
        'Reproduce with bundled Python: `rsc/cses_db/review_cses_main_job_abroad.py --verify-workbooks --soffice /path/to/bundled/soffice`, '
        'then `.venv/bin/python rsc/cses_db/review_cses_main_job_abroad.py --check-database`. Use fresh `--output` and `--docs-dir` paths for changed snapshots.','',
        'The next useful review is additional job count (`additional_jobs_count`), separating it from total occupation count before using it to gate secondary-job fields.','']
    return '\n'.join(lines)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    p.add_argument('--output',type=Path,default=Path(OUTPUT))
    p.add_argument('--docs-dir',type=Path,default=Path('docs'))
    p.add_argument('--verify-workbooks',action='store_true')
    p.add_argument('--soffice')
    p.add_argument('--check-database',action='store_true')
    args=p.parse_args()
    output=args.root/args.output
    if args.verify_workbooks:
        require(args.soffice,'Explicit bundled converter required')
        write_once(output/'source_verification.json',verify_workbooks(args.root,args.soffice))
    else:
        r=make_review(args.root,output/'source_verification.json',args.check_database)
        write_once(output/'review.json',r)
        write_once(args.root/args.docs_dir/'cses-main-job-abroad.md',document(r))
        print(json.dumps(r['scope_counts']))


if __name__=='__main__':
    main()
