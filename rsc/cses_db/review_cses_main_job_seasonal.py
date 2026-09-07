#!/usr/bin/env python3
"""Audit seasonal 10c and prepare a source-preserving local semantic projection."""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

from organize_cses_questionnaires import digest, write_once
from review_cses_education import BASE, load_inputs, normalize_legacy_source_paths, selected_sources, verify_workbooks
from review_cses_employment_hours_status import registry, stata_metadata, variable_entry
from review_cses_main_job_whole_year import CONTEXT, PINS, counts, recode
from review_cses_main_job_whole_year import evidence as whole_year_evidence
from review_cses_main_job_whole_year import route as whole_year_route
from review_cses_questionnaires import parse_options, require

SELF='rsc/cses_db/review_cses_main_job_seasonal.py'
OUTPUT='data/processing/cses/main_job_seasonal_review_v1'
PRIOR='data/processing/cses/main_job_whole_year_review_v1/review.json'
PRIOR_SHA='99e11264ce0e2e3bad0ab058642c8aec6cffbf48ecc2bf8f60f4ef42718556b8'
LEGACY='main_job_was_usual_past_7_days'
YEAR='main_job_works_whole_year'
TARGET='main_job_is_seasonal_reported'
STATUS='main_job_seasonal_evidence_status'
ROUTE='main_job_seasonal_literal_route'
EXTRAS=[TARGET,STATUS,ROUTE]
CURRENT='data/processing/cses/employment_classification_corrected_v1/final_EC_CSES.parquet'
CURRENT_SHA='43a032554a7265384297e5c11a968920932582cc4b56546d28d820641ff00e1e'
LAYOUTS={
    '2011-12':('15 Econo_Status_1','CM7','CM19','CM15','CM6','CM11'),
    '2013':('15 Econo_Status_1','CI7','CI19','CI17','CI6','CI12'),
    '2014':('15 Econo_Status_1','CI7','CI19','CI17','CI6','CI12'),
    '2016':('15 Econo_Status_1','CI7','CI19','CI17','CI6','CI12'),
    '2021':('15 Current Econo-2','P12','P24','P22','P11','P17'),
}


def evidence(root):
    spec,alignment,inventory,extracts=load_inputs(root)
    sheets={s['source_file']:s['sheets'] for s in extracts}
    year_questions,earlier=whole_year_evidence(root)
    questions=[]
    for source in selected_sources(spec,inventory):
        wave=source['survey_wave']
        if wave not in LAYOUTS:
            continue
        sn,text,code,option,gate,definition=LAYOUTS[wave]
        cells=sheets[source['source_file']][sn]
        link=[r for r in alignment['source_links'] if r['survey_wave']==wave and ['final_EC_CSES',LEGACY] in r['canonical_keys']]
        require(len(link)==1 and link[0]['variable_name'].lower()=='q15_c10c','Unique q15_c10c mapping required')
        qs=[q for q in inventory['questions'] if q['source_file']==source['source_file'] and q['source_sheet']==sn and q['question_code_cell']==code]
        require(len(qs)==1 and text in qs[0]['text_cell_candidates'] and qs[0]['candidate_id'] in link[0]['candidate_ids'],'Exact candidate identity required')
        options=parse_options({option:cells[option]})
        require(cells[code]=='(10c)' and {o['source_code'] for o in options}=={1,2},'Exact seasonal question/options required')
        require('seasonal?' in cells[text] and 'past 7 days' in cells[text],'Seasonal wording changed')
        require('only part of the year' in cells[definition] and 'reoccurring every year' in cells[definition],'Seasonal definition changed')
        require(cells[gate].strip()=='If Col. 10b = 2','Seasonal item only follows whole-year No')
        year=next(q for q in year_questions if q['survey_wave']==wave)
        questions.append({'survey_wave':wave,'legacy_field':LEGACY,'aligned_field':TARGET,
            'source_variable':link[0]['variable_name'],'source_variable_id':link[0]['source_variable_id'],
            'candidate_id':qs[0]['candidate_id'],'source_file':source['source_file'],'source_sha256':source['source_sha256'],
            'source_sheet':sn,'question_text_cell':text,'question_code_cell':code,'options_cell':option,
            'gate_cell':gate,'definition_cell':definition,'question_text':cells[text],'definition':cells[definition],
            'gate_text':cells[gate],'options':options,'option_count':2,'prior_whole_year_question':year,
            'documentation_status':source['documentation_status'],'whole_variable_certified':False})
    require(len(questions)==5,'Exactly five directly supported question waves required')
    return questions,earlier


def route(frame,wave):
    parent=whole_year_route(frame,wave)
    return None if parent is None else parent & frame[YEAR].eq(0)


def project(frame):
    import pandas as pd

    require(not set(EXTRAS)&set(frame),'Projection already contains semantic fields')
    after=frame.copy()
    after[TARGET]=frame[LEGACY].where(frame.survey_wave.isin(LAYOUTS))
    after[STATUS]=pd.Series('no_selected_source_column',index=frame.index,dtype='string')
    after.loc[frame.survey_wave.isin(LAYOUTS),STATUS]='questionnaire_verified'
    after.loc[frame.survey_wave.eq('2014'),STATUS]='questionnaire_draft'
    after.loc[frame.survey_wave.eq('2017'),STATUS]='questionnaire_semantics_unverified'
    after.loc[frame.survey_wave.eq('2019'),STATUS]='binary_labels_only_question_text_truncated'
    after[ROUTE]=pd.Series(pd.NA,index=frame.index,dtype='boolean')
    for wave in LAYOUTS:
        selected=frame.survey_wave.eq(wave)
        after.loc[selected,ROUTE]=route(frame.loc[selected],wave)
    pd.testing.assert_frame_equal(after[list(frame)],frame,check_exact=True)
    return after


def projection_sql():
    waves="'2011-12','2013','2014','2016','2021'"
    return f"""SELECT b.*,
 CASE WHEN survey_wave IN ({waves}) THEN {LEGACY} ELSE NULL END::smallint AS {TARGET},
 CASE WHEN survey_wave='2014' THEN 'questionnaire_draft'
      WHEN survey_wave IN ({waves}) THEN 'questionnaire_verified'
      WHEN survey_wave='2017' THEN 'questionnaire_semantics_unverified'
      WHEN survey_wave='2019' THEN 'binary_labels_only_question_text_truncated'
      ELSE 'no_selected_source_column' END::text AS {STATUS},
 CASE WHEN survey_wave IN ({waves}) THEN
      age>=5 AND (worked_at_least_one_hour_past_7_days=1 OR second_work_screening_source_code=1)
      AND {YEAR}=0 ELSE NULL END::boolean AS {ROUTE}
 FROM cses_analysis.cses_ec_classification_v1 b"""


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
        for c in ['household_id','source_archive','source_submodule','source_row_id']:
            pd.testing.assert_series_equal(keys[c].astype(current[c].dtype),current[c],check_names=False)
        metadata={k:v for s in sources for k,v in stata_metadata(s).items()}
        fields=[]
        for field,alias in [(LEGACY,'q15_c10c'),(YEAR,'q15_c10b')]:
            raw,column=source_value(aligned,[alias])
            expected=pd.Series(pd.NA,index=current.index,dtype='Int8')
            entry,meta=None,None
            if column:
                entry=variable_entry(registry(root),wave,column)
                meta=metadata[column]
                require(meta=={k:entry[k] for k in ['variable_label','value_labels']},'Fresh metadata mismatch')
                expected=recode(raw)
            pd.testing.assert_series_equal(expected,current[field],check_names=False)
            fields.append({'field':field,'source_variable':column,'source_variable_id':entry['source_variable_id'] if entry else None,
                'fresh_stata_metadata':meta,'raw_nonnull':int(raw.notna().sum()) if raw is not None else 0,
                'raw_values':counts(raw) if raw is not None else {},
                'discarded_values':counts(raw.loc[raw.notna() & expected.isna()]) if raw is not None else {},'raw_to_canonical_equal':True})
        values=current[LEGACY]
        observed=values.notna()
        mask=route(current,wave)
        profiles.append({'survey_wave':wave,'rows':len(current),'fields':fields,
            'source_files':[{'source_file':s.display_name(root),'sha256':digest(s.read_bytes())} for s in sources],
            'nonnull':int(observed.sum()),'yes':int(values.eq(1).sum()),'no':int(values.eq(0).sum()),'null':int(values.isna().sum()),
            'whole_year_yes_with_response':int((current[YEAR].eq(1)&observed).sum()),
            'whole_year_yes_and_seasonal_yes':int((current[YEAR].eq(1)&values.eq(1)).sum()),
            'whole_year_no_without_response':int((current[YEAR].eq(0)&~observed).sum()),
            'whole_year_unknown_with_response':int((current[YEAR].isna()&observed).sum()),
            'literal_route_records':int(mask.fillna(False).sum()) if mask is not None else None,
            'nonnull_inside_route':int((observed&mask.fillna(False)).sum()) if mask is not None else None,
            'nonnull_outside_known_route':int((observed&mask.eq(False).fillna(False)).sum()) if mask is not None else None,
            'route_unknown_records':int(mask.isna().sum()) if mask is not None else None,
            'nonnull_route_unknown':int((observed&mask.isna()).sum()) if mask is not None else None,
            'within_route_null':int((~observed&mask.fillna(False)).sum()) if mask is not None else None,
            'aligned_semantic_value_available':wave in LAYOUTS,'hl_unmatched':int(current.hl_link_matched.eq(0).sum())})
    return frame,profiles


def check_database(original,projected):
    import pandas as pd
    from cses_baseline_metadata import connect_database
    from psycopg import sql
    from publish_cses_age_topcode import read_only

    columns=CONTEXT+[LEGACY,YEAR]
    expected=original[columns].sort_values(['survey_wave','person_id']).reset_index(drop=True)
    with connect_database({'dbname':'mda'}) as conn:
        read_only(conn)
        for schema,table in [('cses_data','final_EC_CSES'),('cses_analysis','cses_ec_classification_v1')]:
            query=sql.SQL('SELECT {} FROM {} ORDER BY survey_wave,person_id').format(sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier(schema,table))
            live=pd.DataFrame(conn.execute(query).fetchall()).astype(expected.dtypes.to_dict())
            live.source_archive=normalize_legacy_source_paths(live.source_archive)
            pd.testing.assert_frame_equal(live,expected,check_exact=True)
        live=pd.DataFrame(conn.execute('SELECT * FROM ('+projection_sql()+') p ORDER BY survey_wave,person_id').fetchall()).astype(projected.dtypes.to_dict())
        live.source_archive=normalize_legacy_source_paths(live.source_archive)
        pd.testing.assert_frame_equal(live,projected.sort_values(['survey_wave','person_id']).reset_index(drop=True),check_exact=True)
    return {'transaction_read_only':True,'original_selected_columns':columns,'original_relations_compared':2,
        'all_selected_values_match':True,'local_projection_columns':len(projected.columns),'local_projection_rows':len(projected),
        'all_projection_values_match':True,'persistent_database_objects_created':False}


def make_review(root,verification,live):
    import pandas as pd
    from plan_cses_age_topcode import checked_review
    from review_cses_main_job_whole_year import EXECUTION

    checked_review(root)
    for path,sha in {**PINS,PRIOR:PRIOR_SHA,CURRENT:CURRENT_SHA}.items():
        require(digest((root/path).read_bytes())==sha,f'Frozen dependency changed: {path}')
    prior=json.loads((root/PRIOR).read_text())
    require(digest((root/'rsc/cses_db/review_cses_main_job_whole_year.py').read_bytes())==prior['implementation_sha256'],'Prior helper changed')
    for path,sha in json.loads((root/EXECUTION).read_text())['file_sha256'].items():
        require(digest((root/path).read_bytes())==sha,f'Published input changed: {path}')
    verified=json.loads(verification.read_text())
    require(verified['source_cells_sha256']==digest((root/BASE/'source_cells.json').read_bytes()),'Source-cell baseline changed')
    require(verified['implementation_sha256']==digest((root/'rsc/cses_db/review_cses_education.py').read_bytes()),'Workbook verifier changed')
    require(len(verified['sources'])==7 and all(s['all_sheets_equal'] for s in verified['sources']),'Seven fresh workbook checks required')
    questions,earlier=evidence(root)
    original,profiles=data_review(root)
    projected=project(pd.read_parquet(root/CURRENT))
    require(projected.shape==(332903,89),'Expected local 89-column projection')
    review={'review_id':'cses-main-job-seasonal-review-v1','implementation_sha256':digest((root/SELF).read_bytes()),
        'frozen_inputs':{**PINS,PRIOR:PRIOR_SHA,CURRENT:CURRENT_SHA},'legacy_field':LEGACY,'aligned_field':TARGET,
        'source_verification':verified,'questions':questions,'earlier_whole_year_form_checks':earlier,'profiles':profiles,
        'projection_sql':projection_sql(),'scope_counts':{'batch_fields':1,'cumulative_reviewed_ec_fields':19,'remaining_ec_fields':20,
            'rows':len(original),'field_wave_profiles':10,'raw_source_waves':sum(p['fields'][0]['source_variable'] is not None for p in profiles),
            'question_wave_correspondences':len(questions),'stored_nonnull':sum(p['nonnull'] for p in profiles),
            'stored_yes':sum(p['yes'] for p in profiles),'stored_no':sum(p['no'] for p in profiles),
            'raw_nonnull':sum(p['fields'][0]['raw_nonnull'] for p in profiles),
            'inherited_nonbinary_exclusions':sum(sum(p['fields'][0]['discarded_values'].values()) for p in profiles),
            'supported_alias_nonnull':int(projected[TARGET].notna().sum()),'whole_year_yes_with_response':sum(p['whole_year_yes_with_response'] for p in profiles),
            'whole_year_yes_and_seasonal_yes':sum(p['whole_year_yes_and_seasonal_yes'] for p in profiles),
            'fully_certified_all_ten_wave_fields':0},
        'database_check':check_database(original,projected) if live else {'performed':False},
        'database_mutated':False,'canonical_data_mutated':False,'old_field_renamed':False,
        'local_projection_created':True,'persistent_alias_published':False,'individual_records_saved_in_review':False}
    return review,projected


def document(r):
    c=r['scope_counts']
    lines=['# Main-job seasonality: corrected meaning and local alignment','',
        f"The legacy field `{LEGACY}` is misnamed: the directly verified source question `q15_c10c` asks whether the main job is **seasonal**, not usual. "
        '**The stored binary polarity is correct: raw 1 = Yes maps to 1, raw 2 = No maps to 0. Do not invert it.** '
        'The local semantic projection introduces `main_job_is_seasonal_reported` while preserving all 86 columns of the current database interface. '
        'The database old column and metadata have not been renamed, and no persistent database view is created by this review.','',
        'EC review coverage is now **19 of 39 fields**, with 20 remaining. This is one newly reviewed source field; the three local projection columns are not three additional reviewed variables.','',
        '## Meaning and skips','',
        'Five inspected forms define seasonal work as work performed during only part of the year, with the same job recurring every year. '
        'Question 10c refers to the main occupation/economic activity during the past seven days and has two Yes/No choices. '
        'It follows whole-year item 10b only when the raw answer to 10b is 2 (canonical 0). A whole-year Yes skips 10c and goes to 10d. '
        'Seasonal is therefore not the inverse of whole-year work; do not fill a skipped 10c with 0 or 1.','',
        'The literal route is age 5+, first OR second work screen Yes, and whole-year No. The 2014 form is a draft. '
        'The 2021 inherited gate still mentions temporary absence even though the second screen asks about unpaid work; this wording conflict remains unresolved. '
        'Neither equal binary codes nor this literal route certify an identical cross-wave statistical population.','',
        '## Availability and evidence scope','',
        f"The old stored field has **{c['stored_nonnull']:,} non-null member-wave values** across seven waves: {c['stored_yes']:,} Yes and {c['stored_no']:,} No. "
        f"The explicitly evidence-qualified local alias has **{c['supported_alias_nonnull']:,} non-null values** in five questionnaire-supported waves, including the labelled 2014 draft scope. "
        'These are unweighted records, not actual interview respondents or unique humans followed across years.','',
        '| Wave | EC records | Stored Yes (1) | Stored No (0) | Stored non-null | NULL | Seasonal meaning evidence |',
        '| --- | ---: | ---: | ---: | ---: | ---: | --- |']
    for p in r['profiles']:
        w=p['survey_wave']
        evidence_status='Draft question/definition' if w=='2014' else 'Verified question/definition' if w in LAYOUTS else 'No selected source column' if not p['fields'][0]['source_variable'] else 'Yes/No labels; question text truncated' if w=='2019' else 'Household question unverified'
        lines.append('| '+' | '.join([w,*[f"{p[k]:,}" for k in ['rows','yes','no','nonnull','null']],evidence_status])+' |')
    lines += ['',
        '**2019 limitation:** fresh Stata metadata establishes Yes/No option labels, but its variable question label is truncated before the word seasonal. '
        'It does not independently establish the full question meaning; the household image-form transcription is still pending. '
        '2017 also lacks a verified household question. Their original 7,083 and 2,032 stored values remain available under the legacy field, '
        'but the evidence-qualified alias is NULL for those waves. This is withholding an unsupported semantic assertion, not deleting data or claiming that the source did not ask the question. '
        '2004/2007/2009 selected current-employment sources lack the exact alias; nothing is borrowed from other modules or years.','',
        '## Whole-year and route exceptions','',
        f"Across the seven source-bearing waves, {c['whole_year_yes_with_response']:,} records have both whole-year Yes and a non-null 10c answer; "
        f"{c['whole_year_yes_and_seasonal_yes']:,} have Yes in both fields. These are response-pair diagnostics. In the five verified forms they violate the printed 10b bypass. "
        'For 2017/2019 the route is unverified, so a contradiction in their questionnaire is not asserted. Source answers are preserved in all cases.','',
        '| Wave | Whole-year Yes + any 10c | Yes in both | Whole-year No + missing 10c | Whole-year unknown + 10c | Literal route records | Non-null outside route | Non-null, route unknown |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for p in r['profiles']:
        if not p['fields'][0]['source_variable']:
            continue
        lines.append('| '+' | '.join([p['survey_wave'],*[f"{p[k]:,}" if p[k] is not None else 'Not assessed' for k in [
            'whole_year_yes_with_response','whole_year_yes_and_seasonal_yes','whole_year_no_without_response','whole_year_unknown_with_response',
            'literal_route_records','nonnull_outside_known_route','nonnull_route_unknown']]])+' |')
    lines += ['',
        'The local reported alias is **not route-filtered**: reported values outside the route remain visible alongside a separate nullable route flag. '
        'A downstream analysis must state its denominator/exception policy rather than silently deleting or imputing these cases. '
        'NULL can indicate no selected source, a skipped/unanswered question, or insufficient semantic evidence in the new alias; consult both the legacy value and evidence status.','',
        '## Local alignment outputs','',
        '| New local column | Contract |','| --- | --- |',
        f'| `{TARGET}` | Legacy 1/0 copied without inversion in 2011-12, 2013, 2014, 2016 and 2021 only; NULL elsewhere |',
        f'| `{STATUS}` | Verified questionnaire, draft questionnaire, unverified 2017 semantics, truncated 2019 label, or no selected source |',
        f'| `{ROUTE}` | Nullable literal-route diagnostic for the five inspected forms; NULL where the route is unverified |','',
        'The [versioned local Parquet](../data/processing/cses/main_job_seasonal_review_v1/local_semantic_projection.parquet) '
        'contains 332,903 rows and 89 columns. It is **not** a new database table or a replacement for the canonical release. '
        'The [read-only SQL projection](../rsc/sql/cses_main_job_seasonal_projection.sql) returns the same corrected names directly from the existing mda view, '
        'without CREATE/ALTER/UPDATE statements. New alias columns exist in the query result, not persistently in mda.','',
        '## Source locators and verification','',
        '| Wave | Source variable | Sheet | Text / code / options | Gate / definition |',
        '| --- | --- | --- | --- | --- |']
    for q in r['questions']:
        lines.append(f"| {q['survey_wave']} | {q['source_variable']} | {q['source_sheet']} | {q['question_text_cell']} / {q['question_code_cell']} / {q['options_cell']} | {q['gate_cell']} / {q['definition_cell']} |")
    lines += ['',
        'The [aggregate review](../data/processing/cses/main_job_seasonal_review_v1/review.json) preserves raw-variable identities and hashes, '
        'the exact seasonal definitions, adjacent whole-year gates, fresh Stata labels and ten field-wave profiles. Seven original English workbooks '
        'were freshly extracted and every sheet matched the frozen cells. The spreadsheets skill guided separate checks of wording, option polarity and skips, with original workbooks unchanged.','',
        'All seven seasonal raw-field transformations and all seven whole-year dependencies were independently reproduced. '
        f"The source has {c['raw_nonnull']:,} non-null seasonal codes; the inherited 1/2 conversion excludes {c['inherited_nonbinary_exclusions']} nonbinary codes, "
        'leaving 38,176 stored non-null values. These exclusions predate this review: original archive values are preserved, '
        'but neither the legacy binary column nor the new reported alias carries the invalid raw codes. No unsupported Yes/No interpretation is assigned.','',
        '| Wave | Raw seasonal codes excluded by inherited conversion |','| --- | --- |',
        *[f"| {p['survey_wave']} | "+', '.join(f"{code}: {n} records" for code,n in p['fields'][0]['discarded_values'].items())+' |'
          for p in r['profiles'] if p['fields'][0]['discarded_values']],
        '',
        ('Forced read-only database comparisons matched all 12 selected columns in the physical EC table and current classification view. '
         'The complete proposed 89-column SQL projection also matched the local projection for all 332,903 records. This validates a SELECT result, not publication of a new view.'
         if r['database_check'].get('all_projection_values_match') else 'Live database checks were not performed.'),'',
        '```mermaid','flowchart LR','    Q["Question 10c + seasonal definition"] --> S["Correct name: seasonal, not usual"]',
        '    W["Whole-year 10b + screening gates"] --> R["Nullable route flag; no forced recoding"]',
        '    B["Existing 86-column EC interface"] --> P["Local / SELECT-only 89-column projection"]',
        '    S --> P','    R --> P','    P -.-> N["Persistent alias publication is a separate step"]','```','',
        'This local process diagram does not alter published graph v14. Previous reviews, publishers, the 37 physical CSES relations, '
        'catalog mappings and historical views remain unchanged. No Git commit or DVC push is performed.','',
        'Reproduce with the bundled runtime using `rsc/cses_db/review_cses_main_job_seasonal.py --verify-workbooks --soffice /path/to/bundled/soffice`, '
        'then `.venv/bin/python rsc/cses_db/review_cses_main_job_seasonal.py --check-database`. Use fresh `--output`, `--docs-dir` and `--sql-output` paths for a changed snapshot.','',
        'The next implementation step is a separately versioned additive database alias with the same explicit evidence/route qualifiers; do not rename the historical column in place. '
        '2017/2019 semantic promotion still requires the missing source-question evidence or a separately approved, explicitly qualified transfer.','']
    return '\n'.join(lines)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    p.add_argument('--output',type=Path,default=Path(OUTPUT))
    p.add_argument('--docs-dir',type=Path,default=Path('docs'))
    p.add_argument('--sql-output',type=Path,default=Path('rsc/sql/cses_main_job_seasonal_projection.sql'))
    p.add_argument('--verify-workbooks',action='store_true')
    p.add_argument('--soffice')
    p.add_argument('--check-database',action='store_true')
    args=p.parse_args()
    output=args.root/args.output
    if args.verify_workbooks:
        require(args.soffice,'Explicit bundled converter required')
        write_once(output/'source_verification.json',verify_workbooks(args.root,args.soffice))
    else:
        r,projected=make_review(args.root,output/'source_verification.json',args.check_database)
        payload=io.BytesIO()
        projected.to_parquet(payload,index=False)
        path=output/'local_semantic_projection.parquet'
        output.mkdir(parents=True,exist_ok=True)
        if path.exists():
            require(path.read_bytes()==payload.getvalue(),'Versioned projection changed')
        else:
            path.write_bytes(payload.getvalue())
        r['local_projection_sha256']=digest(payload.getvalue())
        write_once(output/'review.json',r)
        write_once(args.root/args.docs_dir/'cses-main-job-seasonal.md',document(r))
        write_once(args.root/args.sql_output,'-- Read-only semantic projection; does not create a database object.\nBEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;\n'+projection_sql()+';\nCOMMIT;\n')
        print(json.dumps(r['scope_counts']))


if __name__=='__main__':
    main()
