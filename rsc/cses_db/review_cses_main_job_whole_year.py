#!/usr/bin/env python3
"""Review one already stored EC variable without changing data or publication artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from organize_cses_questionnaires import digest, write_once
from review_cses_education import BASE, load_inputs, normalize_legacy_source_paths, selected_sources, verify_workbooks
from review_cses_employment_hours_status import registry, stata_metadata, variable_entry
from review_cses_employment_screening import LAYOUT as SCREEN
from review_cses_questionnaires import parse_options, require

SELF = 'rsc/cses_db/review_cses_main_job_whole_year.py'
OUTPUT = 'data/processing/cses/main_job_whole_year_review_v1'
FIELD = 'main_job_works_whole_year'
LAYOUTS = {
    '2011-12': ('15 Econo_Status_1','CH10','CH19','CH15','CH6','BV6','CM6'),
    '2013': ('15 Econo_Status_1','CD12','CD19','CD16','CD6','BV6','CI6'),
    '2014': ('15 Econo_Status_1','CD12','CD19','CD16','CD6','BV6','CI6'),
    '2016': ('15 Econo_Status_1','CD12','CD19','CD16','CD6','BV6','CI6'),
    '2021': ('15 Current Econo-2','K17','K24','K21','K11','C11','P11'),
}
EXECUTION = 'data/releases/cses-employment-classification-qualified-v1/execution.json'
PINS = {
    EXECUTION: '6c00852e26b63457517b572cc455caf70c52942c5108aff29c9a239da05c0e4c',
    'data/lineage/cses_lineage_graph_v14.json': '0ad1cbb8b5651fbabf13c479ee6cbe24e85d794b6e45f519f258940a80b053da',
    'data/processing/cses/employment_classification_review_v1/review.json': 'e26b6d86ba717cab287a2bddb4f2d9f2869281d04fd38ddf230902973b3bd4cd',
}
CONTEXT = ['survey_wave','person_id','household_id','age','hl_link_matched',
    'worked_at_least_one_hour_past_7_days','second_work_screening_source_code',
    'source_archive','source_submodule','source_row_id']


def evidence(root):
    spec, alignment, inventory, extracts = load_inputs(root)
    sheets = {s['source_file']:s['sheets'] for s in extracts}
    questions, absent = [], []
    for source in selected_sources(spec,inventory):
        wave=source['survey_wave']
        if wave not in LAYOUTS:
            current = {sn:cs for sn,cs in sheets[source['source_file']].items() if sn.startswith('13 ' if wave=='2004' else '15 ')}
            found=[{'sheet':sn,'cell':c,'text':t} for sn,cs in current.items() for c,t in cs.items() if 'whole year' in t.lower()]
            require(not found,'Unexpected whole-year item in earlier selected form')
            absent.append({'survey_wave':wave,'source_file':source['source_file'],'source_sha256':source['source_sha256'],
                'selected_current_employment_sheets':sorted(current),'whole_year_phrase_found':False,
                'scope':'selected English current-employment sheets only; not proof of noncollection in every source'})
            continue
        sn,text,code,options,gate,bypass,next_gate=LAYOUTS[wave]
        cs=sheets[source['source_file']][sn]
        link=[r for r in alignment['source_links'] if r['survey_wave']==wave and ['final_EC_CSES',FIELD] in r['canonical_keys']]
        require(len(link)==1 and link[0]['variable_name'].lower()=='q15_c10b','Unique q15_c10b identity required')
        candidate=[q for q in inventory['questions'] if q['source_file']==source['source_file'] and q['source_sheet']==sn and q['question_code_cell']==code]
        require(len(candidate)==1 and text in candidate[0]['text_cell_candidates'],'Exact question locator required')
        require(candidate[0]['candidate_id'] in link[0]['candidate_ids'],'Historical candidate identity changed')
        opts=parse_options({options:cs[options]})
        require({o['source_code'] for o in opts}=={1,2} and cs[code]=='(10b)','Two options / exact item required')
        require('whole year' in cs[text] and 'main occupation' in cs[text],'Meaning changed')
        require('>>10d' in cs[options].replace(' ','') and '10b = 2' in cs[next_gate],'Yes bypasses separate seasonal item')
        require('Col 3 = 1' in cs[gate] and 'Col 4 = 1' in cs[gate],'OR-screen gate changed')
        screen=SCREEN[wave]
        ss=sheets[source['source_file']][screen['sheets'][0]]
        questions.append({'survey_wave':wave,'field':FIELD,'source_variable':link[0]['variable_name'],
            'source_variable_id':link[0]['source_variable_id'],'candidate_id':candidate[0]['candidate_id'],
            'source_file':source['source_file'],'source_sha256':source['source_sha256'],'source_sheet':sn,
            'question_text_cell':text,'question_code_cell':code,'options_cell':options,
            'question_text':cs[text],'options':opts,'option_count':2,
            'route_cells':{c:cs[c] for c in [gate,bypass,next_gate]},
            'population_sheet':screen['sheets'][0],
            'population_cells':{c:ss[c] for c in [screen['universe'],screen['respondent']]},
            'second_screen_text':'\n'.join(ss[c] for c in screen['texts'][1]),
            'minimum_age':5,'documentation_status':source['documentation_status'],
            '2021_gate_text_mentions_temporary_absence_despite_unpaid_second_screen':wave=='2021',
            'whole_variable_certified':False})
    require(len(questions)==5 and len(absent)==2,'Five supported questions and two earlier inspected forms expected')
    return questions,absent


def recode(values):
    import pandas as pd
    return pd.to_numeric(values,errors='coerce').map({1:1,2:0}).astype('Int8')


def route(frame,wave):
    if wave not in LAYOUTS:
        return None
    return frame.age.ge(5) & (frame.worked_at_least_one_hour_past_7_days.eq(1) | frame.second_work_screening_source_code.eq(1))


def counts(values):
    return {str(k):int(n) for k,n in values.dropna().astype('string').value_counts().sort_index().items()}


def data_review(root):
    import pandas as pd
    from cses_employment import employment_sources, prepare_wave_sources, source_value
    from cses_hh_hl_common import AlignmentContext, snake_case

    frame=pd.read_parquet(root/'data/processing/cses/final_EC_CSES.parquet').rename(columns=snake_case)
    require(frame.shape==(332903,60) and not frame.duplicated(['survey_wave','person_id']).any(),'EC grain changed')
    profiles=[]
    for wave,sources in employment_sources(root):
        keys,aligned=prepare_wave_sources(AlignmentContext(root=root),wave,sources)
        keys=keys.rename(columns=snake_case)
        current=frame.loc[frame.survey_wave.eq(wave)].set_index('person_id')
        require(len(current)==len(keys) and set(current.index)==set(keys.person_id),'Source keys differ')
        current=current.loc[keys.person_id].reset_index()
        for c in ['household_id','source_archive','source_submodule','source_row_id']:
            pd.testing.assert_series_equal(keys[c].astype(current[c].dtype),current[c],check_names=False)
        raw,column=source_value(aligned,['q15_c10b'])
        meta,entry=None,None
        expected=pd.Series(pd.NA,index=current.index,dtype='Int8')
        if column:
            entry=variable_entry(registry(root),wave,column)
            fresh={k:v for source in sources for k,v in stata_metadata(source).items()}
            meta=fresh[column]
            require(meta=={k:entry[k] for k in ['variable_label','value_labels']},'Fresh Stata labels differ')
            expected=recode(raw)
        pd.testing.assert_series_equal(expected,current[FIELD],check_names=False)
        mask=route(current,wave)
        observed=expected.notna()
        profiles.append({'survey_wave':wave,'rows':len(current),'source_variable':column,
            'source_variable_id':entry['source_variable_id'] if entry else None,'fresh_stata_metadata':meta,
            'source_files':[{'source_file':s.display_name(root),'sha256':digest(s.read_bytes())} for s in sources],
            'raw_values':counts(raw) if raw is not None else {},'raw_nonnull':int(raw.notna().sum()) if raw is not None else 0,
            'yes':int(expected.eq(1).sum()),'no':int(expected.eq(0).sum()),'nonnull':int(observed.sum()),'null':int((~observed).sum()),
            'discarded_raw_values':counts(raw.loc[raw.notna() & expected.isna()]) if raw is not None else {},
            'literal_route_records':int(mask.fillna(False).sum()) if mask is not None else None,
            'nonnull_within_route':int((observed & mask.fillna(False)).sum()) if mask is not None else None,
            'nonnull_outside_known_route':int((observed & mask.eq(False).fillna(False)).sum()) if mask is not None else None,
            'route_unknown_records':int(mask.isna().sum()) if mask is not None else None,
            'nonnull_route_unknown':int((observed & mask.isna()).sum()) if mask is not None else None,
            'within_route_null':int((~observed & mask.fillna(False)).sum()) if mask is not None else None,
            'hl_unmatched':int(current.hl_link_matched.eq(0).sum()),'raw_to_canonical_equal':True})
    return frame,profiles


def check_database(frame):
    import pandas as pd
    from cses_baseline_metadata import connect_database
    from psycopg import sql
    from publish_cses_age_topcode import read_only

    columns=CONTEXT+[FIELD]
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
    for p,sha in PINS.items():
        require(digest((root/p).read_bytes())==sha,f'Frozen dependency changed: {p}')
    manifest=json.loads((root/EXECUTION).read_text())
    for p,sha in manifest['file_sha256'].items():
        require(digest((root/p).read_bytes())==sha,f'Published implementation changed: {p}')
    verified=json.loads(verification.read_text())
    require(verified['source_cells_sha256']==digest((root/BASE/'source_cells.json').read_bytes()),'Source extraction baseline changed')
    require(verified['implementation_sha256']==digest((root/'rsc/cses_db/review_cses_education.py').read_bytes()),'Workbook verifier changed')
    require(len(verified['sources'])==7 and all(v['all_sheets_equal'] for v in verified['sources']),'Seven fresh workbook checks required')
    questions,absent=evidence(root)
    frame,profiles=data_review(root)
    return {'review_id':'cses-main-job-whole-year-review-v1','field':FIELD,'implementation_sha256':digest((root/SELF).read_bytes()),
        'frozen_inputs':PINS,'source_verification':verified,'questions':questions,'earlier_inspected_forms':absent,'profiles':profiles,
        'scope_counts':{'batch_fields':1,'cumulative_reviewed_ec_fields':18,'remaining_ec_fields':21,'field_wave_profiles':10,
            'raw_field_wave_mappings':sum(p['source_variable'] is not None for p in profiles),'question_wave_correspondences':5,
            'rows':len(frame),'nonnull':sum(p['nonnull'] for p in profiles),'yes':sum(p['yes'] for p in profiles),
            'no':sum(p['no'] for p in profiles),'fully_certified_all_ten_wave_fields':0},
        'database_check':check_database(frame) if live else {'performed':False},
        'database_mutated':False,'canonical_data_mutated':False,'individual_records_saved':False,'new_question_links_published':False}


def document(r):
    c=r['scope_counts']
    lines=['# Main job: works the whole year','',
        f"`{FIELD}` is already stored in the original EC table and inherited by the current `cses_analysis.cses_ec_classification_v1` view. "
        f"This review adds one examined EC field: **18 of 39 reviewed, 21 remaining**. It does not certify unrestricted comparability across all ten waves.",'',
        '## Meaning and coding','',
        'The item asks whether the person works the whole year in their main occupation/economic activity. The five inspected forms containing it have two choices: '
        '**raw 1 = Yes, 2 = No; canonical 1 = Yes, 0 = No**. NULL remains unknown/unavailable, not No. '
        'The original Stata variable is `q15_c10b` (case varies). The transformation is reproduced for all seven source-bearing waves; absent columns yield NULL in three earlier waves.','',
        'This is not a measured count of months worked, proof of 12 months of employment in a specific calendar year, or a direct inverse of seasonal work. '
        'Yes skips the separate seasonal item 10c and goes to 10d; No enters 10c. Neither a seasonal classification nor values for the next field are derived here.','',
        '## Availability and population','',
        f"Across {c['rows']:,} EC member-wave records there are **{c['nonnull']:,} non-null responses: {c['yes']:,} Yes and {c['no']:,} No**. "
        'These are unweighted records, not actual interview respondents or longitudinally unique people. Non-null availability is not a certified eligible denominator.','',
        '| Wave | EC records | Yes (1) | No (0) | Non-null | NULL | Raw variable | Question evidence |',
        '| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |']
    for p in r['profiles']:
        wave=p['survey_wave']
        status='Draft' if wave=='2014' else 'Verified selected form' if wave in LAYOUTS else 'Embedded Yes/No labels; form transcription pending' if wave=='2019' else 'Household form unverified' if wave in ['2007','2017'] else 'Item not found in inspected current-employment form'
        lines.append('| '+' | '.join([wave,*[f"{p[k]:,}" for k in ['rows','yes','no','nonnull','null']],p['source_variable'] or 'Not in selected source',status])+' |')
    lines += ['',
        'The 2004/2007/2009 selected current-employment sources have no `q15_c10b` column. No whole-year item was found in the '
        'inspected 2004/2009 English current-employment sheets; this is not a claim about every possible archive or module. '
        'The recovered 2007 job-index table does not supply this field. 2017 values reproduce the released mapping but lack independently verified questionnaire semantics. '
        '2019 embedded Stata labels establish its 1/2 Yes/No coding, not its untranscribed questionnaire route.','',
        '## Routing and limitations','',
        'In the five inspected forms, age eligibility is 5+ and the literal item gate is first work screen Yes OR second screen Yes. '
        'It is not restricted to first-screen Yes: the hours block explicitly sends its bypass to 10b. No route is borrowed for 2007/2017/2019. '
        'The 2014 draft remains provisional.','',
        '**2021 wording conflict is retained:** the 10b gate still mentions temporary absence, while the revised second screening question asks about unpaid work. '
        'The literal numeric OR condition is recorded for diagnostics, but this does not establish unchanged cross-wave population meaning. '
        'No original answers outside a printed route are deleted or overwritten.','',
        '| Wave | Literal route records | Non-null inside | Non-null outside known route | Route unknown | Non-null with unknown route | NULL inside route |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for p in r['profiles']:
        if p['survey_wave'] in LAYOUTS:
            lines.append('| '+' | '.join([p['survey_wave'],*[f"{p[k]:,}" for k in ['literal_route_records','nonnull_within_route','nonnull_outside_known_route','route_unknown_records','nonnull_route_unknown','within_route_null']]])+' |')
    removals=sum(sum(p['discarded_raw_values'].values()) for p in r['profiles'])
    lines += ['',f"The inherited 1/2-only conversion discarded {removals:,} non-null raw values in this field. "
        'The machine-readable profiles retain the exact discarded values, if any. Route violations are source-data diagnostics, not instructions to change coding. '
        '2004 general sampling weights remain unavailable. The two existing unmatched EC→HL records are retained; missing age can make route eligibility unknown.','',
        '## Exact source locators','',
        '| Wave | Sheet | Question text | Code | Options | Item gate |', '| --- | --- | --- | --- | --- | --- |']
    for q in r['questions']:
        lines.append(f"| {q['survey_wave']} | {q['source_sheet']} | {q['question_text_cell']} | {q['question_code_cell']} | {q['options_cell']} | {LAYOUTS[q['survey_wave']][4]} |")
    lines += ['',
        'The [aggregate review](../data/processing/cses/main_job_whole_year_review_v1/review.json) includes question texts, exact options, gate cells, '
        'source-variable identities, fresh Stata labels, source hashes and ten field-wave profiles. All seven selected household workbooks were '
        'freshly re-extracted and every sheet compared with the frozen cells. Spreadsheet guidance informed the explicit choice/skip checks; no workbook was modified.','',
        ('A forced read-only comparison matched all 11 selected columns across 332,903 rows in both the physical EC table and current classification view. '
         'This is not a full-table or full-view validation.' if r['database_check'].get('all_selected_cells_equal') else 'Live database verification was not performed.'),'',
        '```mermaid','flowchart LR','    Q["Five located 10b questions + two earlier forms checked"] --> E["Yes/No coding and OR-screen gate"]',
        '    S["Seven raw q15_c10b columns"] --> M["1 to 1; 2 to 0; NULL preserved"]',
        '    M --> DB["Existing physical EC and current classification view"]','    E --> D["Local review; no database mutation"]','    DB --> D','```','',
        'This is a local review diagram. Published graph v14, all database objects and prior execution-pinned files remain unchanged. '
        'No new question links, interpretation overlay, Git commit or DVC push are published.','',
        'Reproduce with the bundled Python runtime: `rsc/cses_db/review_cses_main_job_whole_year.py --verify-workbooks --soffice /path/to/bundled/soffice`, '
        'then `.venv/bin/python rsc/cses_db/review_cses_main_job_whole_year.py --check-database`. Changed snapshots require a fresh `--output` and `--docs-dir`.','',
        'Next review the adjacent main-job seasonal question (`q15_c10c`). Its existing canonical name `main_job_was_usual_past_7_days` '
        'does not match the located seasonal wording; that naming/meaning issue is flagged for the next field, not silently fixed in this one-field review.','']
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
        write_once(args.root/args.docs_dir/'cses-main-job-whole-year.md',document(r))
        print(json.dumps(r['scope_counts']))


if __name__=='__main__':
    main()
