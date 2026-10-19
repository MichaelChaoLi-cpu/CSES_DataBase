#!/usr/bin/env python3
"""Independent read-only acceptance checks for the five-wave publication."""
from __future__ import annotations

import json
from pathlib import Path

import psycopg
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put
from psycopg import sql
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/releases/cses-additional-waves-qualified-v1'
EXPECTED = {
    '1996': [9000,46811,46811,46811,9000,46811,9000],
    '1997': [6010,29931,26675,22349,6010,29931,0],
    '1999': [6000,32348,29002,29002,6000,32348,0],
    '2023': [12096,51914,49475,51914,12096,51914,12096],
    '2025': [12338,51775,51775,51775,12338,51775,12338],
}
MODULES = ['hh','hl','ed','ec','ho','health','survey_date']
CHECKS = {
    'household_person_links': (
        'SELECT count(*) n FROM cses_data.cses_additional_hl_v1 p JOIN cses_data.cses_additional_hh_v1 h USING(survey_wave,household_key)',
        212779),
    'geography_unique_person_keys': (
        'SELECT count(DISTINCT (survey_wave,record_key)) n FROM cses_analysis.cses_person_geography_v2',
        571699),
    'exact_age_not_invented_for_98plus': (
        "SELECT count(*) n FROM cses_data.cses_additional_hl_v1 WHERE survey_wave IN ('1996','1999') AND age_topcoded_qualified AND age_lower_bound_years_qualified=98 AND age_exact_years_qualified IS NULL",
        6),
    'unreviewed_age_waves_not_assigned_exact_age': (
        "SELECT count(*) n FROM cses_data.cses_additional_hl_v1 WHERE survey_wave NOT IN ('1996','1999') AND age_exact_years_qualified IS NOT NULL",
        0),
    'unresolved_1999_school_answers': (
        "SELECT count(*) n FROM cses_data.cses_additional_ed_v1 WHERE survey_wave='1999' AND route_review_status IN ('current_attendance_missing_after_ever_yes','current_attendance_missing_but_grade_present') AND currently_attending_school IS NULL",
        12),
    '2023_employment_original_rows': (
        'SELECT count(*) n FROM cses_data.cses_additional_ec_2023_source_v1',51917),
    '2023_employment_folded_rows_qualified': (
        "SELECT count(*) n FROM cses_data.cses_additional_ec_v1 WHERE survey_wave='2023' AND duplicate_key AND qualified_unique_record_eligible",
        3),
    '2023_provider_disagreements_not_imputed': (
        "SELECT count(*) n FROM cses_data.cses_additional_health_v1 WHERE survey_wave='2023' AND first_provider_source_code=98 AND alternate_first_provider_source_code=18 AND first_provider_qualified_source_code IS NULL",
        3),
    '2025_writing_zero_not_inferred_no': (
        "SELECT count(*) n FROM cses_data.cses_additional_ed_v1 WHERE survey_wave='2025' AND (source_values->>'q02c03')::numeric=0 AND can_write IS NULL",
        29),
    'no_combined_literacy_split': (
        "SELECT count(*) n FROM cses_data.cses_additional_ed_v1 WHERE survey_wave IN ('1996','1997','1999') AND (can_read IS NOT NULL OR can_write IS NOT NULL)",
        0),
    'no_2025_daily_hours_relabelled_weekly': (
        "SELECT count(*) n FROM cses_data.cses_additional_ec_v1 WHERE survey_wave='2025' AND (main_hours_past_week_source_value IS NOT NULL OR total_hours_past_week_source_value IS NOT NULL)",
        0),
}


def main():
    result = {'publication_sha256':file_sha(OUT/'published.json'),
              'validator_sha256':file_sha(Path(__file__)),'module_counts':{},'checks':{}}
    with psycopg.connect(dbname='mda',connect_timeout=5,row_factory=dict_row,
                         options='-c default_transaction_read_only=on -c statement_timeout=55000') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute('SET LOCAL ROLE mda_readonly')
        for index,module in enumerate(MODULES):
            rows = conn.execute(sql.SQL('SELECT survey_wave,count(*) n FROM {} GROUP BY survey_wave ORDER BY survey_wave')
                                .format(sql.Identifier('cses_data','cses_additional_'+module+'_v1'))).fetchall()
            counts = {r['survey_wave']:r['n'] for r in rows}
            if counts != {wave:values[index] for wave,values in EXPECTED.items() if values[index]}:
                raise ValueError('Wave/module counts differ: '+module)
            result['module_counts'][module] = counts
        for label,(query,expected) in CHECKS.items():
            actual = conn.execute(query).fetchone()['n']
            if actual != expected:
                raise ValueError(f'{label}: {actual} != {expected}')
            result['checks'][label] = {'sql':query,'expected':expected,'actual':actual}
        # Exercise both new metadata interfaces using the actual analytical reader role.
        for relation,expected in [('cses_meta.cses_additional_evidence_v1',45),
                                  ('cses_alignment.cses_additional_field_mapping_v1',171)]:
            actual = conn.execute(sql.SQL('SELECT count(*) n FROM {}').format(sql.Identifier(*relation.split('.')))).fetchone()['n']
            if actual != expected:
                raise ValueError('Evidence count mismatch')
        result['role'] = 'mda_readonly'
        result['read_only'] = conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only']
        if result['read_only'] != 'on':
            raise ValueError('Not read only')
    put(OUT/'analysis-checks.json',encoded(result))
    print(json.dumps({'passed':True,'role':result['role'],'module_counts':result['module_counts'],
                      'semantic_checks':{k:v['actual'] for k,v in result['checks'].items()}},indent=2))


if __name__ == '__main__':
    main()
