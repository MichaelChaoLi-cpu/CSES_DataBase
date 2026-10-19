# CSES variable brief

## Published health screening across fifteen waves

The [published health screening interface](cses-health-screen-interface.md), release 28,
provides `cses_analysis.cses_health_screen_unified_v1` with 571,699 member-wave rows,
43 columns and five separate unmatched health records. Its strict 30-day
illness/injury subset has 308,955 qualified records across eight waves: 2009, 2011-12, 2013,
2014, 2016, 2021, 2023 and 2025, including 56,262 Yes and 252,693 No answers. These are
overlapping cross-section inventory counts, not a pooled population prevalence or direct
respondent count. Seven additive objects and 197 source-output edges publish the accepted
local v2 pilot contract without changing older health interfaces.

The 15-wave matrix and 45 coverage rows separate native availability, instrument-qualified
answers and the strict 30-day outcome. Four-week questions in 1997/1999/2004/2007 stay separate;
1996's selected topics do not supply a general recent-illness screen. The 2017 raw screen stays
unverified. The 2019 English form and official-report appendix both conflict with native
code-2 Injury labels, so 150 code-2 records remain unresolved and the wave stays outside the
strict default. Separately reviewed 2012 evidence closes the first pilot's combined-wave
form qualification without inventing separate 2012 records.

All 66 roster members without health-source rows remain in the published member view. The 109
skipped-branch flags are conservative exclusions, not proven erroneous screen answers.
The native inputs and existing database answers remain unchanged; treatment-seeking is
outside this alignment. See the published brief for SQL entry points, exception categories
and topology, and the retained pilot for its original per-wave evidence.

The earlier local and read-only source/geography acceptance had zero mismatches and 633
tests passed at that stage; the publication suite now passes 654 tests. A supplemental
audit found seven legacy XLS copies with file-hash drift, but
their original archive members and all non-formula questionnaire cells matched the historical
evidence. The historical v1 cache still fails its binary guard, but the new
[archive-exact cache and health preflight](cses-health-screen-preflight.md) now provide a
fully verified separate cache without overwriting old copies or manifests. The annual audit
found no additional negative-skip conflicts. Database preflight did find missing branch inputs
in the newer-wave stored JSON; the separate native-input bridge is now published after a
complete registration rollback rehearsal. Native answers and accepted pilot counts remain
unchanged; 45 coverage rows and 15 matrix rows expose the published denominators and limits.

## Published education interface across all fifteen waves

The [unified education interface](cses-education-unified-interface.md), release 26 on 2026-10-18,
provides `cses_analysis.cses_education_unified_v1`: 571,699 member-wave records, 77 columns and
eight qualified targets. The target counts below now also describe the published view;
the retained local prototype remains historical evidence. Coverage has 360 rows, the
field-wave matrix 120, and the level codebook 564 source meanings. Seven additive objects
have 141 source-output edges. Old tables and views are preserved and do not automatically
inherit the new qualification contract.

Use `*_qualified`, the corresponding status and route denominator together. The 2017 strict
values remain withheld pending questionnaire evidence; raw data are retained. Four unmatched
ED records stay in a separate audit, not the respondent denominator. Two people's four
conflicting attendance/highest inferences are withheld rather than correcting source answers.
Counts are overlapping, unweighted members, not unique direct respondents or a panel.

Post-publication acceptance matched every member-view cell, all 120 matrix rows and all 360
coverage rows. Fresh native reads and 4,573,592 independent field decisions had zero mismatches;
all 571,699 geography keys linked one-to-one. The old database objects remained unchanged,
and the repository suite passed 615 tests. The full backup and rollback rehearsal also passed.

## Preserved local education prototype across all fifteen waves

The [current local-only education pilot](cses-education-all-waves-pilot.md), revision 2, preserves
571,699 member-wave records and four separate historical unmatched ED records. Its 120-cell
matrix covers eight targets with explicit source availability and comparability qualifications.
No new database view or data correction was published by this pilot.

| Local target | Qualified member records |
| --- | ---: |
| Combined literacy | 515,265 |
| Separate reading | 418,682 |
| Separate writing | 418,642 |
| Ever attended | 474,145 |
| Current attendance | 514,881 |
| Highest educational family | 514,461 |
| Current study family | 124,097 |
| Observed completed years attended | 289,796 |

These counts overlap within people, are unweighted and are not counts of direct respondents
or universally equivalent qualifications. Combined literacy includes observed legacy items
and marked modern conjunctions; years are not imputed from skips or grades. Coverage has 360
field-wave-age-band rows and keeps questionnaire universes distinct from common age bands.

The 2007 English education page confirms a 5+ universe; the 2014 final-report appendix supports
the historical draft-based content; the 2019/20 image page has now been visually reviewed.
The older historical reviews remain unchanged. The 2017 form scope is still unresolved:
all 16,909 members and 16,110 ED records remain present as data, but strict prototype values
are withheld rather than borrowing another year's form.

Among the 14 verified questionnaire universes, 50 age-eligible members lack ED records.
Two raw year/age conflicts and one 2021 value of 50 years outside the analytical 0-30 guard
remain explicit. A positive-years/never-attended conflict guard removes two local attendance
and highest-family inferences, in 2009 and 2014, without changing any database answer. The
newer five-wave accepted qualified values remain exactly preserved. See the full pilot for
per-wave counts, source locators, orphan preservation and the publication boundary.

Final local acceptance verified 4,573,592 field classifications, all 120 matrix cells and
360 denominator rows with zero mismatches. A read-only comparison confirmed all 571,699
geography keys and the relevant existing interface fields. The repository suite passed
608 tests. This is an accepted local prototype, not a new database release.

## Additional wave literacy and observed school years

Published 2026-10-18 as alignment release 24.

The [literacy and observed-years interface](cses-additional-literacy-years.md) preserves
212,779 member-wave records. Its four targets separate combined literacy, reading, writing
and observed completed years attended; legacy combined answers are never split, and modern
combined values are marked as derived from two valid component answers.

| Wave | Qualified combined literacy / age eligible | Qualified reading / age eligible | Qualified writing / age eligible | Qualified observed years / ever-attended Yes |
| --- | ---: | ---: | ---: | ---: |
| 1996 | 40,968 / 40,968 | Not separately collected | Not separately collected | Not collected |
| 1997 | 26,669 / 26,671 | Not separately collected | Not separately collected | Not collected |
| 1999 | 29,002 / 29,002 | Not separately collected | Not separately collected | Not collected |
| 2023 | 49,475 / 49,475 | 49,475 / 49,475 | 49,475 / 49,475 | 42,159 / 42,160 |
| 2025 | 49,425 / 49,455 | 49,454 / 49,455 | 49,425 / 49,455 | 42,780 / 42,780 |

Combined literacy has 195,539 qualified records and 32 unresolved eligible records: two
missing 1997 answers, 29 undefined 2025 writing codes 0, and one missing 2025 component pair.
The qualified total includes 96,639 observed combined answers and 98,900 modern conjunctions,
not one identically asked instrument. Separate reading has 98,929 qualified records, writing
98,900 and observed years 84,939. Field counts overlap and must not be added into a respondent
total. Counts are unweighted member records and can include proxy reports.

In 2023 one years answer has an invalid ever-attended gate and another exceeds source age;
both are excluded without changing their native values. In 2025 one eligible member has an
unresolved gate. The 13,988 documented never-attended years skips remain null, not imputed
zero. The older three selected sources lack the independent completed-years field.
An average of qualified years therefore describes qualified ever-attenders, not all members.
Literacy does not require school attendance. Age universes are 5+ in the older waves and 3+ in the modern
waves; a separate ages-15-plus coverage band provides a common minimum age, not age standardization.

Use `cses_analysis.cses_additional_literacy_years_v1`, its coverage view and the source-rule
table. The source codes, qualified results, statuses and derivation flags remain separate.
Instrument equivalence is not certified, and no school-years imputation is performed.

Both post-publication read-only checks passed: 212,779 native member records, 851,116 field
classifications, 20 source rules and 40 denominator rows matched, with zero lost geography
joins. Existing data and interfaces remain unchanged. The repository suite passed 588 tests.

## Additional wave highest attainment and current level

Published 2026-10-18 as alignment release 21.

The [attainment and current-study interface](cses-additional-education-levels.md) covers the same
212,779 members, with 188 code meanings for nine available field-wave pairs. These are not
188 variables or a certified ISCED crosswalk. Highest attainment and current study remain
separate, as do source codes, ordinary grades, certificates, vocational categories and degrees.

| Wave | Qualified highest family / applicable | Unresolved highest | Qualified current family / reported current students | Unresolved current |
| --- | ---: | ---: | ---: | ---: |
| 1996 | 40,797 / 40,968 | 171 | Source field unavailable | Not defined |
| 1997 | 26,382 / 26,671 | 289 | 6,986 / 7,007 | 21 |
| 1999 | 29,002 / 29,002 | 0 | 8,049 / 8,049 | 0 |
| 2023 | 49,472 / 49,475 | 3 | 12,303 / 12,303 | 0 |
| 2025 | 49,454 / 49,455 | 1 | 12,620 / 12,620 | 0 |

The totals are 195,107 qualified highest categories, including 30,516 explicitly marked
never-attended skip derivations, and 39,958 qualified current categories. None/Other and
unspecified degree types remain distinct; these are not all precisely equivalent qualifications.
There are 464 unresolved highest field records and 21 unresolved current field records, with
possible overlap across people. Counts are unweighted member records, not direct respondents.
The current-level source field is unavailable in the selected 1996 source; no grade is imputed.

Use `cses_analysis.cses_additional_education_levels_v1`, its coverage view and the new source
codebook. The 1999 dictionary correctly distinguishes preschool 0 from None 99; the earlier
school-rule metadata has a documented erratum, with zero existing attendance results affected.

Post-publication read-only acceptance verified all 212,779 native member records, 425,558
field classifications and ten denominator rows, with zero mismatches and no lost geography
joins. Existing data and interfaces remain unchanged. The repository suite passed 561 tests;
remaining unknowns and cross-wave qualification differences are retained, not certified away.

## Additional wave current school attendance

Published 2026-10-18 as alignment release 19.

The [school attendance interface](cses-additional-school-attendance.md) keeps all 212,779
member-wave records and separates observed answers, documented skip-derived No values,
unresolved cases and members outside questionnaire age ranges. The 195,571 age-eligible
members include **195,253 qualified records and 318 unresolved or conservatively excluded
records**. There are 30,209 explicitly flagged skip-derived No values; original answers are
unchanged. These counts do not certify the whole education module or a pooled population.

| Wave | Age-eligible members | Qualified denominator | Unresolved or excluded |
| --- | ---: | ---: | ---: |
| 1996 | 40,968 | 40,968 | 0 |
| 1997 | 26,671 | 26,367 | 304 |
| 1999 | 29,002 | 28,990 | 12 |
| 2023 | 49,475 | 49,474 | 1 |
| 2025 | 49,455 | 49,454 | 1 |

Query `cses_analysis.cses_additional_school_attendance_v1` and its coverage/rule views.
1996 explicitly includes training/vocational institutions; the other forms ask about the
school system and separately ask about non-formal classes. Concept scopes remain visible
and cross-wave equivalence is not certified. All counts and diagnostic shares are unweighted;
member records can be proxy-reported and are not counts of direct respondents.

## 2025 age selection update

Published 2026-10-18 as alignment release 17.

The [2025 age interface](cses-2025-age-interface.md) selects native `age` for all **51,775
members in 12,338 households**, instead of relying on the 165 populated manual-age cells.
Use `cses_analysis.cses_2025_person_age_v1.age_for_analysis` explicitly; older tables and
geography views are unchanged. All 165 manual overlaps agree. The observed age range is 0–105,
with 11,753 members aged 6–17; these are unweighted member-wave counts, not direct respondents.

This fixes source-field selection, not every age interpretation issue. Native calculation,
reference date and top-code semantics remain unverified. A first-visit date diagnostic agrees
for 51,096 members, differs by one year for four, and cannot be calculated for 675 incomplete or
invalid birth dates. The interface preserves these flags and both age values without imputation.
The following publication and pilot sections describe the unchanged historical v1 scope.

## Additional-wave publication: 2026-10-03

**Historical v1 pilot warning:** published 2025 age is non-null for only 165 of 51,775 members;
the complete native calculated-age field was not selected. School attendance rates also change
substantially when never-attended skips are handled explicitly. Sex passed the five-wave
coding/completeness checks. See the [read-only pilot](cses-additional-waves.md#read-only-alignment-pilot).
No database correction was made by that experiment. The counts below describe storage, not blanket
analytical readiness.

The subsequent [source-gap audit](cses-additional-waves.md#source-completeness-and-missingness-audit)
also flags 2025 treatment sought: only the 262 injury cases answer `q13bc06`; all 14,695 illness
cases are blank despite 14,324 having provider records. Do not treat these nulls as No or use the
field as a complete treatment-sought indicator. Raw data, questionnaires and database remain unchanged.

The [five-wave release](cses-additional-waves.md#additional-wave-database-release) adds
**45,444 household-wave records and 212,779 member-wave records** for 1996, 1997, 1999, 2023
and 2025. These are not counts of direct respondents or longitudinally unique people. The older
ten-wave tables remain unchanged; together the rosters contain 571,699 member-wave records.

| New-wave module | Published records | Important denominator or interpretation limit |
| --- | ---: | --- |
| HH | 45,444 | Unique household-wave keys; all roster links match |
| HL | 212,779 | Proxy reporting possible; six 1996/1999 ages are 98+, not exact 98 |
| ED | 203,738 | Eligibility differs; combined literacy is not separate reading/writing; 12 unresolved 1999 attendance responses retained |
| EC | 201,851 | 2023 has 51,914 unique records after three reviewed folds; all 51,917 original candidate rows also retained separately |
| HO | 45,444 | Source categories, season and fuel concepts remain wave-specific |
| HEALTH | 212,779 | Different screening/age universes; unresolved 2023 provider disagreements retained |
| SURVEY_DATE | 33,434 | Native date components only for 1996, 2023 and 2025 |

There are **171 field-wave mappings across 74 distinct module/target pairs**, including 51
label-verified binary/sex recodes. These are not 74 fully comparable variables across all 15 waves.
The source catalog contains 5,427 native variable occurrences in 173 datasets, including fields
outside the materialized modules. No blanket cross-wave equivalence is certified by this release.

Use `cses_data.cses_additional_<module>_v1` and the published field-mapping/evidence tables.
Supplement-only qualified columns must not be treated as populated for unreviewed waves.
The geography v2 interface covers all 15 waves; full source village codes are available for every
roster record, but map-code matches are incomplete and historical village identity/geometry
remains unverified. See the release for per-wave counts, restrictions and SQL examples.

## Historical ten-wave brief

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
