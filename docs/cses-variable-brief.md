# CSES variable brief

Current HEALTH supplement: [database release and variable brief](cses-health-database-release.md).
It covers 358,859 person-wave records, two partially aligned concepts and a 41-column qualified
interface. The 280-field counts below remain the historical seven-core-table scope, not a total
of all HEALTH native fields or review/provenance columns.

Snapshot: after publication of the 2004 age-96+ interface, before the proposed 15-question-link batch.

## What is aligned?

All 280 physical-table fields have inherited standardized definitions and pass current key/availability checks. That is technical alignment, not proof that choices, units, eligibility, reference periods and denominators are identical across years.

**No variable is claimed here to have unrestricted, fully certified analytical comparability across all ten waves.** The completed scopes below are useful and explicitly bounded; zero blanket certifications does not mean zero usable data.

| Variable / scope | Completed work | Remaining interpretation boundary |
| --- | --- | --- |
| HO dwelling_tenure_source_code, main_cooking_fuel_source_code, main_lighting_source_code | Published definitions in all ten waves: 201 dictionary entries; all non-null source codes matched | Draft/skip/compound categories, 2017 approved transfer, 2021 language conflict, raw tenure-0 anomaly and housing orphans retained; no common denominator certified |
| HL sex | Question and 1=Male / 2=Female correspondence checked in 2004, 2009, 2011-12, 2013, 2016, 2021 | New question links planned, not published. 2014 draft; 2007/2017 household form gaps; 2019 transcription pending |
| HL age; ED/EC age; HH household_head_age | Published 2004 age-96+ qualification in four additive views | 3 distinct people are lower-bounded at 96, not exact age; other years outside that rule |
| HL relationship_to_household_head | Full 15-choice source lists checked in seven English forms | Literal Great/grand-child note differs; 2014 draft and three untranscribed/unavailable waves remain |
| HL absent_from_household | Coding polarity and questionnaire routing checked | 2004 current absence differs from later last-week presence; reference periods must remain separate |
| Other ED, EC, VL, date and derived/context fields | Existing transformations, definitions and availability inventoried | Variable-specific semantic re-audit remains pending; date/identifier fields need contracts rather than response options |

The proposed 9 substantive question links, 6 sex question links and 7 identifier provenance rows are evidence-registration work, not 22 newly fully aligned analytical variables.

## Population and respondent counts

Counts below are unweighted released record counts. A member can be reported by a household proxy. A record is not proof that this person answered a questionnaire or every question. Actual unique interview-respondent counts are not established. Cross-wave person/household identifiers are not validated longitudinal identities.

| Table | Statistical unit | Records / unique within-wave keys | Fields | Waves |
| --- | --- | ---: | ---: | ---: |
| final_HH_CSES | household-wave | 77,904 | 35 | 10 |
| final_HL_CSES | member-wave | 358,920 | 37 | 10 |
| final_ED_CSES | education-record-wave | 343,204 | 30 | 10 |
| final_HO_CSES | housing-record-wave | 77,922 | 50 | 10 |
| final_EC_CSES | employment-record-wave | 332,903 | 60 | 10 |
| final_VL_CSES | village/PSU-wave | 5,718 | 40 | 8 |
| final_SURVEY_DATE_CSES | household-date-record-wave | 77,904 | 28 | 10 |

HL/ED/EC composite-key union: **358,926 person-wave records**. HH/HO/date union: **77,923 household-wave records**. These are deduplicated across the stated tables within a wave, not unique humans/households followed across years. Do not sum the seven table totals or include village rows in a person count.

| Wave | HH | HL | ED | HO | EC | VL | Date | Person-wave union |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2004 | 14,984 | 74,719 | 74,719 | 15,000 | 74,719 | 900 | 14,984 | 74,719 |
| 2007 | 3,593 | 17,439 | 15,789 | 3,593 | 15,766 | 357 | 3,593 | 17,439 |
| 2009 | 11,971 | 57,105 | 53,647 | 11,971 | 51,460 | 720 | 11,971 | 57,105 |
| 2011-12 | 3,592 | 16,327 | 15,469 | 3,592 | 14,829 | 355 | 3,592 | 16,327 |
| 2013 | 3,840 | 17,225 | 16,389 | 3,840 | 15,774 | 0 | 3,840 | 17,226 |
| 2014 | 12,090 | 53,968 | 51,221 | 12,092 | 49,252 | 1,006 | 12,090 | 53,972 |
| 2016 | 3,839 | 16,985 | 16,093 | 3,839 | 15,498 | 364 | 3,839 | 16,986 |
| 2017 | 3,840 | 16,909 | 16,110 | 3,840 | 15,482 | 0 | 3,840 | 16,909 |
| 2019 | 10,075 | 44,548 | 42,308 | 10,075 | 40,379 | 1,008 | 10,075 | 44,548 |
| 2021 | 10,080 | 43,695 | 41,459 | 10,080 | 39,744 | 1,008 | 10,080 | 43,695 |

## Key variables: available records

Non-null counts describe stored observations, not substantive choices or eligible respondents. Distinct values are local observed values, not questionnaire option counts (IDs and numeric ages have no finite-choice interpretation).

| Table | Field | Non-null / records | Null | Known questionnaire choices / rule |
| --- | --- | ---: | ---: | --- |
| final_HL_CSES | absent_from_household | 358,791 / 358,920 | 129 | 2; polarity and period differ |
| final_HL_CSES | age | 358,919 / 358,920 | 1 | Numeric; 2004 top-code 96+ |
| final_HL_CSES | relationship_to_household_head | 358,909 / 358,920 | 11 | 15 in inspected forms |
| final_HL_CSES | sex | 358,920 / 358,920 | 0 | 2 in inspected forms |
| final_HO_CSES | dwelling_tenure_source_code | 77,834 / 77,922 | 88 | Wave-specific dictionary; no pooled option count |
| final_HO_CSES | main_cooking_fuel_source_code | 77,897 / 77,922 | 25 | Wave-specific dictionary; no pooled option count |
| final_HO_CSES | main_lighting_source_code | 77,903 / 77,922 | 19 | Wave-specific dictionary; no pooled option count |

The six ready-for-link sex waves contain 226,056 member records and 226,056 non-null sex values; this is a bounded evidence scope, not all-wave certification.

## Important analytical constraints

- 2004 general household/person weights are absent in the selected core sources. Do not substitute 1 or borrow weights.
- Household membership includes usually residing members and absences under 12 months; it is not the number present last week.
- ED/EC table sizes are not automatically the eligible analysis denominators. Review wave-specific age gates, skips and reference periods before calculating rates.
- Housing preserves unmatched households; do not silently inner-join them away. Village joins to households require deduplicated PSU keys.
- Exact household dates are available only for 2004, 2019 and 2021 in the accepted date contract. Do not turn survey year into an exact interview day.
- Missing cells, absent modules, structural skips and unanswered questions are distinct. The report does not infer a missingness reason from NULL.

| Retained unmatched relationship | Wave | Unmatched records |
| --- | --- | ---: |
| final_HO_CSES → final_HH_CSES | 2004 | 16 |
| final_HO_CSES → final_HH_CSES | 2009 | 1 |
| final_HO_CSES → final_HH_CSES | 2014 | 2 |
| final_ED_CSES → final_HL_CSES | 2013 | 1 |
| final_ED_CSES → final_HL_CSES | 2014 | 3 |
| final_EC_CSES → final_HL_CSES | 2014 | 1 |
| final_EC_CSES → final_HL_CSES | 2016 | 1 |

## Full variable inventory and reproducibility

- [All 280 fields with definitions, counts and review status](cses-variable-inventory.md)
- [Machine-readable 2,800 field-wave cells, unit counts and live checks](../data/processing/cses/variable_brief_v1/brief.json)
- [Questionnaire batch publication plan](cses-questionnaire-batch-plan.md)
- [Housing interface](cses-housing-2021-resolution.md) and [age interface](cses-age-topcode.md)

The report uses a forced repeatable-read/read-only database transaction. Every field-wave row/non-null count and table key is compared with local artifacts; person/household union counts and linkage exceptions are checked independently in PostgreSQL. It does not claim a new full raw-data rebuild or row-level validation of every skip. Original questionnaire/age review hashes and inputs are pinned. No individual respondent rows are saved in the report. Physical-field count excludes additive view columns.
