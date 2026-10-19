#!/usr/bin/env python3
"""Read-only age, school and health gap checks across published CSES waves."""
from __future__ import annotations

import json
from pathlib import Path

import psycopg
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'data/processing/cses/cross_wave_gap_audit_v1'
HEALTH = {
    '2004':('q14a06','q14a08','q14a09'),
    '2009':('q13bc02','q13bc06','q13bc09a'),
    '2011-12':('q13bc2a','q13bc06','q13bc9a'),
    '2013':('Q13BC2A','Q13BC06','Q13BC9A'),
    '2014':('q13bc2a','q13bc06','q13bc9a'),
    '2016':('q13bc2a','q13bc06','q13bc9a'),
    '2017':('Q13BC2A','Q13BC06','Q13BC9A'),
    '2019':('q13bc2a','q13bc06','q13bc09a'),
    '2021':('q13bc2a','q13bc06','q13bc09a'),
}
NEW_HEALTH = {'1997':('p8c3','p8c5','p8c7'),'1999':('p7c3','p7c5','p7c7'),
              '2023':('q13bc2a','q13bc06','q13bc09a'),'2025':('q13bc2a','q13bc06','q13bc09a')}
QUERIES = {
    'age': '''WITH p AS (
      SELECT survey_wave,age::double precision AS age,sex FROM cses_data."final_HL_CSES"
      UNION ALL SELECT survey_wave,age_source_value,sex FROM cses_data.cses_additional_hl_v1)
      SELECT survey_wave,count(*) records,count(*) FILTER(WHERE age IS NULL) age_missing,
      min(age) age_min,max(age) age_max,count(*) FILTER(WHERE age<0 OR age>120 OR age<>trunc(age)) invalid_numeric_age,
      count(*) FILTER(WHERE sex IS NULL) sex_missing FROM p GROUP BY 1 ORDER BY 1''',
    'school': '''WITH p AS (
      SELECT survey_wave,person_id AS person,household_id AS household,age::double precision age FROM cses_data."final_HL_CSES"
      UNION ALL SELECT survey_wave,record_key,household_key,age_source_value FROM cses_data.cses_additional_hl_v1),
      e AS (SELECT survey_wave,person_id AS person,household_id AS household,ever_attended_school AS ever,currently_attending_school AS current FROM cses_data."final_ED_CSES"
      UNION ALL SELECT survey_wave,record_key,household_key,ever_attended_school,currently_attending_school FROM cses_data.cses_additional_ed_v1)
      SELECT p.survey_wave,count(*) roster,count(*) FILTER(WHERE e.person IS NULL) education_row_absent,
      count(*) FILTER(WHERE e.current IS NULL) current_missing_including_absent,
      count(*) FILTER(WHERE e.current IS NULL AND e.ever=0) missing_current_with_never_attended,
      count(*) FILTER(WHERE e.current=1 AND e.ever=0) contradictory_answers,
      count(*) FILTER(WHERE p.age BETWEEN 6 AND 17 AND e.current=1 AND e.ever=0) contradictions_age_6_17_as_published
      FROM p LEFT JOIN e USING(survey_wave,person,household) GROUP BY p.survey_wave ORDER BY 1''',
    'legacy_health_rows_absent': '''SELECT p.survey_wave,count(*) FILTER(WHERE h.person_id IS NULL) roster_without_health
      FROM cses_data."final_HL_CSES" p LEFT JOIN cses_data.cses_health_illness_source_v1 h USING(survey_wave,person_id,household_id)
      GROUP BY p.survey_wave ORDER BY 1''',
    'legacy_health_orphans': '''SELECT survey_wave,hl_link_status,count(*) records
      FROM cses_data.cses_health_illness_source_v1 WHERE hl_link_status<>'matched' GROUP BY 1,2 ORDER BY 1,2''',
    'age_2004_raw_missing': '''SELECT h.raw_record->>'age' native_age_code,count(*) records FROM cses_data."final_HL_CSES" p
      JOIN cses_data.cses_health_illness_source_v1 h USING(survey_wave,person_id,household_id)
      WHERE p.age IS NULL GROUP BY 1''',
    'health_2009_activity_branch': '''SELECT raw_record->>'q13bc04' activity_code,count(*) records,
      count(raw_record->>'q13bc06') treatment_answered,count(raw_record->>'q13bc09a') provider_present
      FROM cses_data.cses_health_illness_source_v1 WHERE survey_wave='2009' AND (raw_record->>'q13bc02')::numeric=1
      GROUP BY 1 ORDER BY 1''',
    'health_2007_unverified_candidates': '''SELECT raw_record->>'q14ac06' candidate_screen_code,count(*) records,
      count(raw_record->>'q14ac08a') candidate08a_present,count(raw_record->>'q14ac08b') candidate08b_present,
      count(raw_record->>'q14ac09') candidate09_present FROM cses_data.cses_health_illness_source_v1
      WHERE survey_wave='2007' GROUP BY 1 ORDER BY 1''',
    'health_2021_unresolved_type': '''SELECT count(*) records FROM cses_analysis.cses_health_illness_v1
      WHERE survey_wave='2021' AND raw_type_code BETWEEN 22 AND 73''',
}


def main():
    result = {'database_modified':False,'scope':'15 published rosters; selected age/school/health diagnostics, not all variables',
              'script_sha256':file_sha(Path(__file__)),'queries':QUERIES,'health_field_selections':{**HEALTH,**NEW_HEALTH}}
    with psycopg.connect(dbname='mda',row_factory=dict_row,connect_timeout=5,
                         options='-c default_transaction_read_only=on -c statement_timeout=55000') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute('SET LOCAL ROLE mda_readonly')
        assert conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']=='on'
        for label,query in QUERIES.items():
            result[label]=conn.execute(query).fetchall()
        if sum(r['records'] for r in result['age'])!=571699 or sum(r['roster'] for r in result['school'])!=571699:
            raise ValueError('Roster joins changed counts')
        result['health_by_screen']=[]
        for choices,relation,column in [(HEALTH,'cses_data.cses_health_illness_source_v1','raw_record'),
                                        (NEW_HEALTH,'cses_data.cses_additional_health_v1','source_values')]:
            for wave,fields in choices.items():
                # Identifiers come only from the fixed table/column pairs above; keys are parameters.
                query=f'''WITH x AS(SELECT {column}->>%s screening,{column}->>%s treatment,{column}->>%s provider
                  FROM {relation} WHERE survey_wave=%s)
                  SELECT screening,count(*) records,count(treatment) treatment_non_null,
                  count(*) FILTER(WHERE treatment IN ('1','2','1.0','2.0')) treatment_valid_binary,
                  count(*) FILTER(WHERE treatment IS NULL) treatment_null,
                  count(provider) provider_present,
                  count(*) FILTER(WHERE treatment IS NULL AND provider IS NOT NULL) provider_with_null_treatment
                  FROM x GROUP BY 1 ORDER BY 1'''
                rows=conn.execute(query,(*fields,wave)).fetchall()
                result['health_by_screen'].append({'wave':wave,'groups':rows,'sql':query})
    form=ROOT/'data/processed/cses_questionnaires/v1/2009/text/72e05de6451dd3a8.json'
    cells=json.loads(form.read_text())['sheets']['Health Care Seeking _ Expen ']
    result['questionnaire_2009']={'path':str(form.relative_to(ROOT)),'sha256':file_sha(form),
        'cells':{k:cells[k] for k in ['AR7','AR25','BD7','BD17','BD25','BP7','BP17','BP25','BU7','BU25','CL7','CL25']}}
    if '>> 7' not in cells['BD17'] or cells['BP25']!='(6)':
        raise ValueError('2009 routing evidence changed')
    result['limitations']=['2007 and 2017 household-form evidence remains missing; native candidates are not semantic certification.',
        'The 1996 disability/under-five diarrhoea scope is not a counterpart of modern all-person illness/treatment.',
        'Provider information among screening negatives may describe other care; it is not automatically contradictory.',
        'Non-null provider codes include native unknown/sentinel codes; not all are classified providers.',
        '2025 school age-band counts from the published age remain incomplete; use the separate pilot only as a local scenario.',
        'A source-specific skip explains blanks but does not certify an all-illness denominator for that item.']
    put(OUT/'summary.json',encoded(result))
    print(json.dumps({k:v for k,v in result.items() if k not in {'queries','health_by_screen','questionnaire_2009'}},indent=2))
    print('HEALTH BY SCREEN',json.dumps([{k:v for k,v in r.items() if k!='sql'} for r in result['health_by_screen']],indent=2))


if __name__=='__main__':
    main()
