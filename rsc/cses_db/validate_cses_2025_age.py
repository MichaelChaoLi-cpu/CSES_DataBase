#!/usr/bin/env python3
"""Independent read-only acceptance: compare every selected age to immutable Stata."""
import hashlib
import io
import json
import zipfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import psycopg
from build_cses_additional_waves import encoded, source_keys
from cache_cses_questionnaires import file_sha, put
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/releases/cses-2025-age-source-v2'


def main():
    spec = json.loads((ROOT / 'rsc/specs/cses_additional_waves_v1.json').read_text())['waves']['2025']
    archive = ROOT / spec['archive']
    if file_sha(archive) != spec['sha256']:
        raise ValueError('Immutable source archive changed')
    with zipfile.ZipFile(archive) as z:
        payload = z.read('S01A_HHmember.dta')
        cover = pd.read_stata(io.BytesIO(z.read('S00_HHcover.dta')), convert_categoricals=False,
                              columns=['interview__id', 's01q12_visit1'])
    raw = pd.read_stata(io.BytesIO(payload), convert_categoricals=False,
                        columns=spec['household_key'] + [spec['person_key'], 'age', 'q01ac05a',
                                                        'q01ac04a', 'q01ac04b', 'q01ac04c'])
    if cover.interview__id.duplicated().any():
        raise ValueError('Duplicate cover key')
    raw['first_visit'] = raw.interview__id.map(cover.set_index('interview__id').s01q12_visit1)
    raw['record_key'] = source_keys(raw, spec['household_key'] + [spec['person_key']], '2025')
    raw['household_key'] = source_keys(raw, spec['household_key'], '2025')
    with psycopg.connect(dbname='mda', connect_timeout=5, row_factory=dict_row,
                         options='-c default_transaction_read_only=on -c statement_timeout=55000') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute('SET LOCAL ROLE mda_readonly')
        if conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only'] != 'on':
            raise ValueError('Read-only required')
        actual = pd.DataFrame(conn.execute('''SELECT survey_wave,household_key,record_key,age_for_analysis,
          age_source_value,age_formula_verified,age_reference_date_verified,age_topcode_semantics_verified,
          first_visit_check_status,first_visit_calendar_age_check,native_minus_first_visit_check,age_source_member_sha256
          FROM cses_analysis.cses_2025_person_age_v1''').fetchall())
        geography = conn.execute('''SELECT count(*) n FROM cses_analysis.cses_2025_person_age_v1 a
          JOIN cses_analysis.cses_person_geography_v2 g USING(survey_wave,household_key,record_key)''').fetchone()['n']
        rule = conn.execute('SELECT * FROM cses_alignment.cses_2025_age_rule_v1').fetchall()
        old_counts = conn.execute('''SELECT survey_wave,count(*) AS records,count(age_source_value) AS age_non_null
          FROM cses_data.cses_additional_hl_v1 GROUP BY survey_wave ORDER BY survey_wave''').fetchall()
        metadata = conn.execute('''SELECT count(*) AS edges,count(DISTINCT o.storage_table_id) AS outputs
          FROM cses_meta.cses_dataset_output o JOIN cses_meta.cses_alignment_release r USING(alignment_release_id)
          WHERE r.mapping_version='cses-2025-age-source-v2' ''').fetchone()
    joined = raw.merge(actual, on=['household_key', 'record_key'], how='outer', indicator=True, validate='one_to_one')
    if len(joined) != 51775 or not joined['_merge'].eq('both').all():
        raise ValueError('Source/interface key mismatch')
    if not joined.age.eq(joined.age_for_analysis).all():
        raise ValueError('Selected age differs from native source')
    same = joined.q01ac05a.eq(joined.age_source_value) | (joined.q01ac05a.isna() & joined.age_source_value.isna())
    if not same.all():
        raise ValueError('Manual source changed')
    # Independently recompute the diagnostic with Python dates, not the builder's pandas code.
    for r in joined.itertuples(index=False):
        expected_age = None
        try:
            birth = date(int(r.q01ac04c), int(r.q01ac04b), int(r.q01ac04a))
        except (ValueError, TypeError, OverflowError):
            expected_status = 'incomplete_or_invalid_birth_date'
        else:
            try:
                visit = datetime.fromisoformat(r.first_visit).date()
            except (ValueError, TypeError):
                expected_status = 'missing_or_invalid_first_visit_date'
            else:
                expected_age = visit.year - birth.year - ((visit.month, visit.day) < (birth.month, birth.day))
                expected_status = ('matches_first_visit_calendar_age' if r.age == expected_age
                                   else 'differs_from_first_visit_calendar_age')
        if r.first_visit_check_status != expected_status:
            raise ValueError('Row-level calendar diagnostic status mismatch')
        if expected_age is None:
            if pd.notna(r.first_visit_calendar_age_check) or pd.notna(r.native_minus_first_visit_check):
                raise ValueError('Calendar age invented for invalid date')
        elif r.first_visit_calendar_age_check != expected_age or r.native_minus_first_visit_check != r.age - expected_age:
            raise ValueError('Row-level calendar diagnostic value mismatch')
    if (actual[['age_formula_verified', 'age_reference_date_verified', 'age_topcode_semantics_verified']].any().any()
            or geography != 51775 or not actual.survey_wave.eq('2025').all()
            or not actual.age_source_member_sha256.eq(hashlib.sha256(payload).hexdigest()).all()):
        raise ValueError('Qualification/provenance/geography failed')
    evidence = json.loads((OUT / 'evidence.json').read_text())
    status = {str(k): int(v) for k, v in actual.first_visit_check_status.value_counts().items()}
    if status != evidence['summary']['first_visit_check_counts']:
        raise ValueError('Date-check profile differs')
    if len(rule) != 1 or rule[0]['evidence_sha256'] != file_sha(OUT / 'evidence.json'):
        raise ValueError('Missing evidence rule')
    if metadata != {'edges': 6, 'outputs': 3}:
        raise ValueError('Missing source/output registration')
    expected_counts = [('1996', 46811, 46811), ('1997', 29931, 29931), ('1999', 32348, 32348),
                       ('2023', 51914, 51914), ('2025', 51775, 165)]
    if [tuple(r.values()) for r in old_counts] != expected_counts:
        raise ValueError('Historical roster changed')
    result = {'passed': True, 'role': 'mda_readonly', 'read_only': True,
              'records_compared_to_native_source': len(joined), 'native_age_disagreements': 0,
              'manual_value_disagreements': 0, 'geography_linked': geography,
              'calendar_diagnostic_rows_independently_verified': len(joined), 'registered_source_output_edges': metadata['edges'],
              'first_visit_check_counts': status, 'historical_roster_counts': old_counts,
              'source_archive_sha256': spec['sha256'], 'validator_sha256': file_sha(Path(__file__)),
              'published_sha256': file_sha(OUT / 'published.json')}
    put(OUT / 'independent-checks.json', encoded(result))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
