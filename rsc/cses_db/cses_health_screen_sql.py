"""Independent SQL for additive health screening interfaces; no Python classifier reuse."""
from __future__ import annotations

KEYS = ['survey_wave','household_key','record_key']
RULE = 'cses_alignment.cses_health_screen_rule_v1'
ADDITIONAL = 'cses_data.cses_health_screen_additional_source_v1'
SOURCE = 'cses_analysis.cses_health_screen_source_v1'
VIEW = 'cses_analysis.cses_health_screen_unified_v1'
COVERAGE = 'cses_analysis.cses_health_screen_coverage_v1'
MATRIX = 'cses_analysis.cses_health_screen_matrix_v1'
ORPHAN = 'cses_analysis.cses_health_screen_orphan_v1'
RELATIONS = [RULE,ADDITIONAL,SOURCE,VIEW,COVERAGE,MATRIX,ORPHAN]
TARGETS = ['screen_qualified','illness_injury_30d_candidate','illness_injury_30d_qualified']
BRANCHES = [f'branch_{i}_native' for i in range(1,12)]
SOURCE_TYPES = {**dict.fromkeys(KEYS,'text'),'source_row_number':'bigint','source_id':'text',
    'screen_native':'double precision',**dict.fromkeys(BRANCHES,'double precision'),
    'screen_variant_conflict':'boolean','followup_variant_conflict':'boolean','hh_link_matched':'boolean'}


def source_query(rule=RULE,additional=ADDITIONAL):
    branches = ','.join(f"(h.payload->>(r.rule->'no_followups'->>{i}))::double precision AS {c}" for i,c in enumerate(BRANCHES))
    return f"""WITH raw AS (
      SELECT survey_wave,household_id AS household_key,person_id AS record_key,
        source_row_number,source_id,raw_record AS payload,hh_link_matched,
        NULL::double precision AS alternate_treatment_source_response
      FROM cses_data.cses_health_illness_source_v1
    ) SELECT h.survey_wave,h.household_key,h.record_key,h.source_row_number,
      coalesce(h.source_id,r.rule->>'source_id') AS source_id,
      (h.payload->>(r.rule->>'variable'))::double precision AS screen_native,{branches},
      false AS screen_variant_conflict,
      false AS followup_variant_conflict,h.hh_link_matched
    FROM raw h JOIN {rule} r ON r.survey_wave=h.survey_wave
    UNION ALL SELECT {','.join(SOURCE_TYPES)} FROM {additional}"""


def person_query(columns,source=SOURCE,rule=RULE):
    branches = ','.join('s.'+c for c in BRANCHES)
    any_branch = ' OR '.join(c+' IS NOT NULL' for c in BRANCHES)
    return f"""WITH inputs AS (
      SELECT e.survey_wave,e.household_key,e.record_key,e.age_source_value,e.age_for_analysis,e.age_selection_status,
        s.source_row_number::double precision,s.source_id,s.screen_native,{branches},
        coalesce(s.screen_variant_conflict,false) AS screen_variant_conflict,
        coalesce(s.followup_variant_conflict,false) AS followup_variant_conflict,
        coalesce(s.hh_link_matched,false) AS hh_link_matched,s.record_key IS NOT NULL AS health_linked,
        r.rule,(r.rule->>'variable') IS NOT NULL AS screen_available,
        (r.rule->>'period_days') IS NOT NULL AS form_scope_reviewed,
        r.rule->>'family' AS instrument_family,(r.rule->>'period_days')::integer AS reference_period_days,
        r.rule->>'form_status' AS form_evidence_status,r.rule->>'variable' AS source_variable,
        CASE WHEN s.screen_native=trunc(s.screen_native) THEN
          (r.rule->'mapping'->>s.screen_native::bigint::text)::integer END AS screen_binary_native,
        (r.rule->>'strict_30d')::boolean AS strict_30d_wave
      FROM cses_analysis.cses_education_unified_v1 e JOIN {rule} r ON r.survey_wave=e.survey_wave
      LEFT JOIN {source} s ON s.survey_wave=e.survey_wave AND s.household_key=e.household_key AND s.record_key=e.record_key
    ), flags AS (
      SELECT *,coalesce(screen_binary_native=0 AND ({any_branch}),false) AS no_with_followup,
        coalesce(screen_native=2 AND jsonb_array_length(rule->'injury_only')=2
          AND (branch_1_native IS NOT NULL OR branch_2_native IS NOT NULL),false) AS injury_with_illness_only,
        coalesce(rule->'disputed_codes' @> to_jsonb(screen_native),false) AS source_form_code_conflict,
        screen_available AND form_scope_reviewed AND health_linked AND hh_link_matched AS screen_applicable
      FROM inputs
    ), classified AS (
      SELECT *,CASE
        WHEN NOT screen_available THEN 'not_collected_in_selected_source'
        WHEN NOT form_scope_reviewed THEN 'unverified_same_wave_form_scope'
        WHEN NOT health_linked THEN 'missing_health_source_record'
        WHEN NOT hh_link_matched THEN 'household_not_matched'
        WHEN screen_native IS NULL THEN 'source_null'
        WHEN rule->'missing_codes' @> to_jsonb(screen_native) THEN 'explicit_missing_code'
        WHEN screen_binary_native IS NULL THEN 'unrecognized_native_code'
        WHEN source_form_code_conflict THEN 'source_form_code_conflict'
        WHEN screen_variant_conflict THEN 'screen_variant_conflict'
        WHEN no_with_followup OR injury_with_illness_only THEN 'screening_branch_conflict'
        ELSE 'observed_with_instrument_scope' END AS screen_status
      FROM flags
    ), qualified AS (
      SELECT *,CASE WHEN screen_status='observed_with_instrument_scope' THEN screen_binary_native END AS screen_qualified
      FROM classified
    ), result AS (
      SELECT *,CASE WHEN reference_period_days=30 THEN screen_qualified END AS illness_injury_30d_candidate,
        CASE WHEN strict_30d_wave AND reference_period_days=30 THEN screen_qualified END AS illness_injury_30d_qualified,
        CASE WHEN screen_status<>'observed_with_instrument_scope' THEN screen_status
          WHEN strict_30d_wave THEN 'observed_30day_screen'
          WHEN reference_period_days<>30 THEN 'separate_period_or_concept'
          ELSE 'qualified_wave_not_in_strict_default' END AS strict_30d_status,
        false AS screen_imputed,false AS cross_wave_equivalence_certified
      FROM qualified
    ) SELECT {','.join(columns)} FROM result"""


def coverage_query(view=VIEW):
    targets = ','.join(f"count({t}) FILTER(WHERE inside) AS {t}_records,count(*) FILTER(WHERE inside AND {t}=1) AS {t}_yes,count(*) FILTER(WHERE inside AND {t}=0) AS {t}_no" for t in TARGETS)
    return f"""WITH expanded AS (
      SELECT m.*,b.age_band,b.inside FROM {view} m CROSS JOIN LATERAL (
        VALUES ('all_members',true),('ages_6_17',coalesce(age_for_analysis BETWEEN 6 AND 17,false)),
          ('ages_15_plus',coalesce(age_for_analysis>=15,false))) b(age_band,inside)
    ) SELECT survey_wave,age_band,count(*) AS roster_members,count(*) FILTER(WHERE inside) AS members_in_band,
      count(*) FILTER(WHERE inside AND health_linked) AS health_linked,
      count(*) FILTER(WHERE inside AND screen_native IS NOT NULL) AS raw_screen_non_null,
      count(*) FILTER(WHERE inside AND screen_applicable) AS screen_applicable,
      count(*) FILTER(WHERE inside AND screen_applicable AND screen_qualified IS NULL) AS unresolved_expected,
      {targets}
    FROM (SELECT * FROM expanded) e
    GROUP BY survey_wave,age_band"""


def orphan_query(source=SOURCE):
    return f"""SELECT s.* FROM {source} s WHERE NOT EXISTS (
      SELECT 1 FROM cses_analysis.cses_education_unified_v1 e WHERE e.survey_wave=s.survey_wave
        AND e.household_key=s.household_key AND e.record_key=s.record_key)"""


def matrix_query(view=VIEW,source=SOURCE,rule=RULE):
    targets = ','.join(f'count({t}) AS {t}_records' for t in TARGETS)
    return f"""WITH counts AS (
      SELECT survey_wave,count(*) AS roster_members,count(*) FILTER(WHERE health_linked) AS linked_source_rows,
        count(*) FILTER(WHERE NOT health_linked) AS roster_without_health,
        count(*) FILTER(WHERE no_with_followup) AS no_with_followup,
        count(*) FILTER(WHERE injury_with_illness_only) AS injury_with_illness_only,
        count(*) FILTER(WHERE followup_variant_conflict) AS followup_variant_conflicts,{targets}
      FROM {view} GROUP BY survey_wave
    ), native AS (
      SELECT survey_wave,jsonb_object_agg(code,n) AS screen_native_counts FROM (
        SELECT survey_wave,CASE WHEN screen_native IS NULL THEN 'nan' ELSE screen_native::numeric::text||'.0' END AS code,count(*) AS n
        FROM {view} GROUP BY survey_wave,screen_native) q GROUP BY survey_wave
    ), statuses AS (
      SELECT survey_wave,jsonb_object_agg(screen_status,n) AS screen_status_counts FROM (
        SELECT survey_wave,screen_status,count(*) n FROM {view} GROUP BY survey_wave,screen_status) q GROUP BY survey_wave
    ), sources AS (SELECT survey_wave,count(*) AS health_source_rows FROM {source} GROUP BY survey_wave)
    SELECT c.*,s.health_source_rows,s.health_source_rows-c.linked_source_rows AS orphan_health_rows,
      n.screen_native_counts,t.screen_status_counts,r.rule,r.verified_form_path
    FROM counts c JOIN sources s USING(survey_wave) JOIN native n USING(survey_wave)
      JOIN statuses t USING(survey_wave) JOIN {rule} r USING(survey_wave)"""
