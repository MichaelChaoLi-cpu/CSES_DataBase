#!/usr/bin/env python3
"""Independent SQL projection of the accepted fifteen-wave education policy."""
from __future__ import annotations

TARGETS = ['combined','read','write','ever','attendance','highest','current','years']
SOURCE = 'cses_data.cses_education_native_bridge_v1'
ORPHAN = 'cses_data.cses_education_orphan_audit_v1'
RULE = 'cses_alignment.cses_education_source_rule_v1'
BOOK = 'cses_alignment.cses_education_level_codebook_v1'
VIEW = 'cses_analysis.cses_education_unified_v1'
COVERAGE = 'cses_analysis.cses_education_coverage_v1'
MATRIX = 'cses_analysis.cses_education_matrix_v1'
RELATIONS = [SOURCE,ORPHAN,RULE,BOOK,VIEW,COVERAGE,MATRIX]
SOURCE_TYPES = {'survey_wave':'text','household_key':'text','record_key':'text','age_source_value':'double precision',
    'education_linked':'boolean',**{t+'_native':'double precision' for t in TARGETS if t!='combined'}}
ORPHAN_TYPES = {'survey_wave':'text','household_key':'text','record_key':'text','source_row_id':'text',
    **{t+'_native':'double precision' for t in TARGETS}}
RULE_TYPES = {'survey_wave':'text','target':'text','source_variable':'text','source_available':'boolean','mode':'text',
    'minimum_age':'integer','form_evidence_status':'text','form_locator':'text','whole_variable_equivalence_certified':'boolean'}
BOOK_TYPES = {'survey_wave':'text','target':'text','source_code':'integer','family':'text','kind':'text','grade':'integer',
    'form_evidence_status':'text','source_variable':'text','form_locator':'text'}
PHYSICAL_TYPES = {SOURCE:SOURCE_TYPES,ORPHAN:ORPHAN_TYPES,RULE:RULE_TYPES,BOOK:BOOK_TYPES}
NATURAL_KEYS = {SOURCE:['survey_wave','household_key','record_key'],ORPHAN:['survey_wave','household_key','record_key'],
    RULE:['survey_wave','target'],BOOK:['survey_wave','target','source_code'],VIEW:['survey_wave','household_key','record_key'],
    COVERAGE:['survey_wave','age_band','target'],MATRIX:['survey_wave','target']}


def person_query(columns,source=SOURCE,rule=RULE,book=BOOK):
    pivot = ['min(minimum_age) AS minimum_age','max(form_evidence_status) AS form_evidence_status',
             "max(mode) FILTER(WHERE target='combined') AS combined_mode"]
    for t in TARGETS:
        pivot.extend([f"bool_or(source_available) FILTER(WHERE target='{t}') AS {t}_available",
                      f"max(source_variable) FILTER(WHERE target='{t}') AS {t}_variable"])
    natives = ','.join(f'(e.source_values->>p.{t}_variable)::double precision AS {t}_native' for t in TARGETS)
    oldnatives = ','.join('NULL::double precision AS combined_native' if t=='combined' else f'b.{t}_native' for t in TARGETS)
    available = ','.join('p.'+t+'_available' for t in TARGETS)
    statuses,qualifications = [],[]
    for t in TARGETS:
        x = t+'_native'
        if t=='highest':
            body = """WHEN invalid_ever THEN 'unrecognized_ever_code'
              WHEN first_never_conflict THEN 'never_attended_route_conflict'
              WHEN highest_native IS NULL AND ever_native=2 THEN 'derived_never_attended'
              WHEN highest_source_kind='unknown' THEN 'explicit_unknown_response'
              WHEN highest_native IS NOT NULL AND highest_source_kind IS NULL THEN 'unrecognized_level_code'
              WHEN highest_native IS NULL THEN 'missing_response' ELSE 'observed'"""
        elif t=='current':
            body = """WHEN invalid_ever OR invalid_current THEN 'unrecognized_attendance_code'
              WHEN ever_native=2 AND attendance_native=1 THEN 'never_attended_route_conflict'
              WHEN attendance_native IS NULL THEN 'current_attendance_unresolved'
              WHEN attendance_native=2 AND current_native IS NOT NULL THEN 'current_level_outside_route'
              WHEN attendance_native=2 THEN 'not_currently_attending'
              WHEN current_source_kind='none' THEN 'none_not_a_current_level'
              WHEN current_source_kind='unknown' THEN 'explicit_unknown_response'
              WHEN current_native IS NOT NULL AND current_source_kind IS NULL THEN 'unrecognized_level_code'
              WHEN current_native IS NULL THEN 'missing_response' ELSE 'observed'"""
        elif t=='years':
            body = """WHEN invalid_ever THEN 'unrecognized_ever_code'
              WHEN ever_native IS NULL THEN 'ever_attendance_unresolved'
              WHEN ever_native=2 AND years_native IS NULL THEN 'documented_skip_no_years_value'
              WHEN ever_native=2 THEN 'years_value_outside_route'
              WHEN years_native IS NOT NULL AND NOT(years_native BETWEEN 0 AND 30 AND years_native=floor(years_native))
                THEN 'outside_integer_0_30_guard'
              WHEN years_exceed_source_age THEN 'years_exceed_source_age'
              WHEN years_native IS NULL THEN 'missing_response' ELSE 'observed'"""
        elif t=='combined':
            body = """WHEN combined_mode='derived_components' THEN CASE
              WHEN (read_native IS NOT NULL AND read_native NOT IN (1,2)) OR
                   (write_native IS NOT NULL AND write_native NOT IN (1,2)) THEN 'unrecognized_component_code'
              WHEN read_native IS NULL OR write_native IS NULL THEN 'missing_component_response'
              ELSE 'derived_components' END
              WHEN combined_native IS NOT NULL AND combined_native NOT IN (1,2) THEN 'unrecognized_binary_code'
              WHEN combined_native IS NULL THEN 'missing_response' ELSE 'observed'"""
        else:
            body = f"WHEN {x} IS NOT NULL AND {x} NOT IN (1,2) THEN 'unrecognized_binary_code' WHEN {x} IS NULL THEN 'missing_response' ELSE 'observed'"
            if t=='attendance':
                body = """WHEN invalid_ever OR invalid_current THEN 'unrecognized_attendance_code'
                  WHEN first_never_conflict OR not_attending_with_current_level_warning THEN 'attendance_route_conflict'
                  WHEN skip_supported AND ever_native=2 AND attendance_native IS NULL THEN 'derived_documented_skip_no' """+body
        statuses.append(f"CASE WHEN NOT {t}_available THEN 'not_collected_in_selected_source' "
            f"WHEN NOT form_scope_reviewed THEN 'unverified_same_wave_form_scope' "
            f"WHEN age_eligible IS NULL THEN 'unknown_age_eligibility' WHEN NOT age_eligible THEN 'outside_questionnaire_age_range' "
            f"WHEN NOT education_linked THEN 'missing_education_record' {body} END::text AS {t}_first_status")
        applicable = f'coalesce({t}_available AND age_eligible AND education_linked,false)'
        gate = 'ever_native=1' if t=='years' else 'attendance_native=1' if t=='current' else 'true'
        qualifications.extend([f'{applicable} AS {t}_applicable',f'({applicable} AND coalesce({gate},false)) AS {t}_expected_by_route'])
    final_statuses = []
    for t in TARGETS:
        value = f'{t}_first_status'
        if t in ['attendance','highest']:
            value = "CASE WHEN never_attended_positive_years_warning AND form_scope_reviewed AND age_eligible AND education_linked "
            value += f"AND {t}_first_status IN ('observed','derived_never_attended','derived_documented_skip_no') "
            value += f"THEN 'never_attended_positive_years_conflict' ELSE {t}_first_status END"
        final_statuses.append(f'{value} AS {t}_status')
    for t in TARGETS:
        if t=='highest':
            value = "CASE WHEN highest_status='derived_never_attended' THEN 'never_attended' ELSE highest_source_family END"
        elif t=='current':
            value = 'current_source_family'
        elif t=='years':
            value = 'years_native::bigint'
        elif t=='combined':
            value = "CASE WHEN combined_status='derived_components' THEN (read_native=1 AND write_native=1)::integer ELSE (combined_native=1)::integer END"
        elif t=='attendance':
            value = "CASE WHEN attendance_status='derived_documented_skip_no' THEN 0 ELSE (attendance_native=1)::integer END"
        else:
            value = f'({t}_native=1)::integer'
        qualifications.append(f"CASE WHEN {t}_status IN ('observed','derived_components','derived_documented_skip_no','derived_never_attended') THEN {value} END AS {t}_qualified")
        if t in ['highest','current']:
            qualifications.append(f"CASE WHEN {t}_status IN ('observed','derived_never_attended') THEN {t}_source_grade END AS {t}_general_grade")
    return f"""WITH policy AS MATERIALIZED (SELECT survey_wave,{','.join(pivot)} FROM {rule} GROUP BY survey_wave),
      native AS (
        SELECT h.survey_wave,h.person_id AS record_key,h.household_id AS household_key,b.age_source_value,
          h.age::double precision AS age_for_analysis,b.education_linked,{oldnatives}
        FROM cses_data."final_HL_CSES" h JOIN {source} b
          ON h.survey_wave=b.survey_wave AND h.person_id=b.record_key AND h.household_id=b.household_key
        UNION ALL SELECT h.survey_wave,h.record_key,h.household_key,h.age_source_value,
          s.age_for_school_analysis AS age_for_analysis,e.record_key IS NOT NULL AS education_linked,{natives}
        FROM cses_data.cses_additional_hl_v1 h
        JOIN cses_analysis.cses_additional_school_attendance_v1 s USING(survey_wave,household_key,record_key)
        JOIN policy p ON p.survey_wave=h.survey_wave
        LEFT JOIN cses_data.cses_additional_ed_v1 e ON e.survey_wave=h.survey_wave
          AND e.household_key=h.household_key AND e.record_key=h.record_key),
      inputs AS (SELECT n.*,{available},p.minimum_age,p.minimum_age IS NOT NULL AS form_scope_reviewed,
        p.form_evidence_status,p.combined_mode,n.survey_wave<>'1996' AND p.minimum_age IS NOT NULL AS skip_supported,
        CASE WHEN n.survey_wave='2025' THEN 'published_native_calculated_age_formula_unverified'
          ELSE 'reported_source_age_no_new_exact_age_certification' END::text AS age_selection_status,
        CASE WHEN n.survey_wave='2004' AND n.age_for_analysis IS NOT NULL THEN n.age_for_analysis=96
          WHEN n.survey_wave IN ('1996','1999') AND n.age_for_analysis IS NOT NULL THEN n.age_for_analysis=98
          ELSE NULL END::boolean AS age_documented_topcode,
        CASE WHEN p.minimum_age IS NOT NULL AND n.age_for_analysis IS NOT NULL
          THEN n.age_for_analysis>=p.minimum_age ELSE NULL END::boolean AS age_eligible,
        h.family AS highest_source_family,h.kind AS highest_source_kind,h.grade AS highest_source_grade,
        c.family AS current_source_family,c.kind AS current_source_kind,c.grade AS current_source_grade,
        n.ever_native IS NOT NULL AND n.ever_native NOT IN (1,2) AS invalid_ever,
        n.attendance_native IS NOT NULL AND n.attendance_native NOT IN (1,2) AS invalid_current,
        n.highest_native IS NOT NULL AND coalesce(h.kind NOT IN ('none','unknown'),true) AS hint_h,
        n.current_native IS NOT NULL AND coalesce(c.kind NOT IN ('none','unknown'),true) AS hint_c
        FROM native n JOIN policy p USING(survey_wave)
        LEFT JOIN {book} h ON n.survey_wave=h.survey_wave AND h.target='highest' AND n.highest_native=h.source_code
        LEFT JOIN {book} c ON n.survey_wave=c.survey_wave AND c.target='current' AND n.current_native=c.source_code),
      flags AS (SELECT *,coalesce(ever_native=2 AND (attendance_native=1 OR hint_h OR hint_c),false) AS first_never_conflict,
        coalesce(attendance_native=2 AND hint_c,false) AS not_attending_with_current_level_warning,
        coalesce(years_native>age_for_analysis,false) AS years_exceed_source_age,
        coalesce(ever_native=2 AND years_native>0,false) AS never_attended_positive_years_warning FROM inputs),
      first_statuses AS (SELECT *,{','.join(statuses)} FROM flags),
      statuses AS (SELECT *,{','.join(final_statuses)},
        first_never_conflict OR never_attended_positive_years_warning AS never_attended_route_conflict FROM first_statuses),
      qualified AS (SELECT *,{','.join(qualifications)} FROM statuses),
      final AS (SELECT *,combined_status='derived_components' AS combined_derived,false AS years_imputed,
        false AS cross_wave_equivalence_certified FROM qualified)
      SELECT {','.join(columns)} FROM final"""


def coverage_query(view=VIEW,rule=RULE):
    values = []
    for t in TARGETS:
        q = f'{t}_qualified::text'
        values.append(f"('{t}',{t}_native,{q},{t}_expected_by_route)")
    return f"""WITH members AS MATERIALIZED (SELECT * FROM {view}),
      roster AS (SELECT survey_wave,count(*) n FROM members GROUP BY survey_wave),
      aggregated AS (SELECT s.survey_wave,a.age_band,t.target,count(*) AS age_band_members,
        count(*) FILTER(WHERE t.expected) AS expected_by_route,count(t.native) AS raw_non_null,
        count(t.qualified) AS qualified_records,count(*) FILTER(WHERE t.expected AND t.qualified IS NULL) AS unresolved_expected,
        count(*) FILTER(WHERE t.qualified='1') AS qualified_yes,count(*) FILTER(WHERE t.qualified='0') AS qualified_no
        FROM members s CROSS JOIN LATERAL (VALUES
          ('questionnaire_universe',age_eligible),('ages_6_17',age_for_analysis BETWEEN 6 AND 17),
          ('ages_15_plus',age_for_analysis>=15)) a(age_band,inband)
        CROSS JOIN LATERAL (VALUES {','.join(values)}) t(target,native,qualified,expected)
        WHERE a.inband GROUP BY s.survey_wave,a.age_band,t.target)
      SELECT r.survey_wave,b.age_band,r.target,n.n AS roster_members,r.minimum_age,
        r.minimum_age IS NOT NULL AS form_scope_reviewed,
        CASE WHEN b.age_band='questionnaire_universe' AND r.minimum_age IS NULL THEN NULL
          ELSE coalesce(a.age_band_members,0) END AS age_band_members,
        r.source_available,coalesce(a.expected_by_route,0) AS expected_by_route,coalesce(a.raw_non_null,0) AS raw_non_null,
        coalesce(a.qualified_records,0) AS qualified_records,coalesce(a.unresolved_expected,0) AS unresolved_expected,
        CASE WHEN r.target NOT IN ('highest','current','years') THEN coalesce(a.qualified_yes,0) END AS qualified_yes,
        CASE WHEN r.target NOT IN ('highest','current','years') THEN coalesce(a.qualified_no,0) END AS qualified_no
      FROM {rule} r CROSS JOIN (VALUES ('questionnaire_universe'),('ages_6_17'),('ages_15_plus')) b(age_band)
      JOIN roster n USING(survey_wave) LEFT JOIN aggregated a USING(survey_wave,age_band,target)"""


def matrix_query(view=VIEW,rule=RULE,orphan=ORPHAN):
    values = ','.join(f"('{t}',{t}_native,{t}_qualified::text,{t}_expected_by_route)" for t in TARGETS)
    orphan_values = ','.join(f"('{t}',{t}_native)" for t in TARGETS)
    return f"""WITH members AS MATERIALIZED (SELECT * FROM {view}),
      roster AS (SELECT survey_wave,count(*) AS roster_members,count(*) FILTER(WHERE education_linked) AS linked FROM members GROUP BY survey_wave),
      stats AS (SELECT survey_wave,t.target,count(t.native) AS native_nonnull,count(t.qualified) AS qualified_records,
        count(*) FILTER(WHERE t.expected AND t.qualified IS NULL) AS unresolved_expected
        FROM members CROSS JOIN LATERAL (VALUES {values}) t(target,native,qualified,expected) GROUP BY survey_wave,t.target),
      orphans AS (SELECT survey_wave,t.target,count(*) AS rows,count(t.native) AS native_nonnull
        FROM {orphan} CROSS JOIN LATERAL (VALUES {orphan_values}) t(target,native) GROUP BY survey_wave,t.target)
      SELECT r.form_evidence_status,r.form_locator,r.minimum_age,r.mode,
        n.linked+coalesce(o.rows,0) AS native_education_rows,s.native_nonnull+coalesce(o.native_nonnull,0) AS native_source_non_null,
        coalesce(o.rows,0) AS orphan_education_rows,s.qualified_records,n.roster_members,r.source_available,r.source_variable,
        r.survey_wave,r.target,s.unresolved_expected,r.whole_variable_equivalence_certified
      FROM {rule} r JOIN roster n USING(survey_wave) JOIN stats s USING(survey_wave,target)
      LEFT JOIN orphans o USING(survey_wave,target)"""
