# CSES complete variable inventory

Scope: the historical seven-core-table inventory. The later HEALTH source and qualified review
interfaces are described separately in the [HEALTH database variable brief](cses-health-database-release.md);
its 248 native field occurrences and 41 review columns are not additions to this 280-field canonical count.

Companion to the [variable brief](cses-variable-brief.md). All counts are unweighted records at the table's grain. Catalog approval of an inherited mapping does not equal a new unrestricted semantic certification. Detailed wave-specific denominators and NULL counts are in [brief.json](../data/processing/cses/variable_brief_v1/brief.json).

Review codes: `housing-qualified` = all-ten-wave source code coverage with retained limits; `member-reviewed` = seven-form foundation review; `age-2004` = published bounded top-code qualification; `baseline/pending` = inherited standardization, variable-specific re-audit pending.

## final_HH_CSES

Unit: household-wave. 77,904 records; 35 fields.

| Field | Non-null / total | Observed distinct | Non-null waves | Review | Existing definition |
| --- | ---: | ---: | --- | --- | --- |
| child_member_count_0_14 | 77,904 / 77,904 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Number of roster members with valid completed age from 0 through 14. |
| commune_code | 62,920 / 77,904 | 25 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source commune code normalized as a six-character string. |
| dataset_name | 77,904 / 77,904 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | CSES plus the normalized survey wave. |
| district_code | 62,920 / 77,904 | 17 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source district code normalized as a four-character string. |
| female_member_count | 77,904 / 77,904 | 12 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Number of roster members with harmonized Sex=2. |
| household_head_age | 77,902 / 77,904 | 84 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | age-2004 | Cleaned completed age inherited from the unique coded household head. |
| household_head_can_read | 77,897 / 77,904 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized literacy indicator inherited from the matched education record: 1=Yes and 0=No. |
| household_head_can_write | 77,892 / 77,904 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized writing indicator inherited from the matched education record: 1=Yes and 0=No. |
| household_head_education_level | 61,703 / 77,904 | 8 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Broad harmonized completed education level inherited from the matched education record for the coded household head. |
| household_head_ethnicity | 77,886 / 77,904 | 8 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Eight-category harmonized ethnicity inherited from the unique coded household head. |
| household_head_marital_status | 77,890 / 77,904 | 4 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Four-category harmonized marital status inherited from the unique coded household head. |
| household_head_person_id | 77,903 / 77,904 | 27,075 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Person identifier for the unique member coded as relationship-to-head=1; null when the household has no unique coded head. |
| household_head_sex | 77,903 / 77,904 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized sex code inherited from the unique coded household head: 1=Male and 2=Female. |
| household_head_years_attended_school | 51,020 / 77,904 | 26 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Cleaned completed years attended inherited from the matched education record for the coded household head; unavailable in 2004. |
| household_id | 77,904 / 77,904 | 27,036 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Wave-normalized household identifier. |
| household_member_count | 77,904 / 77,904 | 16 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Number of released household-roster members in the survey-wave household. |
| household_weight | 62,920 / 77,904 | 5,537 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific household sampling weight; no imputation. |
| male_member_count | 77,904 / 77,904 | 11 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Number of roster members with harmonized Sex=1. |
| older_member_count_65_plus | 77,904 / 77,904 | 5 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Number of roster members with valid completed age of 65 or older. |
| province_code | 77,904 / 77,904 | 25 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source province code normalized as a two-character string. |
| psu | 77,904 / 77,904 | 1,676 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Wave-normalized primary sampling unit identifier. |
| source_archive | 77,904 / 77,904 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Raw archive path relative to the project root. |
| source_row_id | 77,904 / 77,904 | 77,904 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Deterministic identifier for the row in the member-roster source. |
| source_submodule | 77,904 / 77,904 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Stata member path inside the raw archive. |
| stratum | 74,311 / 77,904 | 59 | 2004, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released sampling stratum code retained as a string. |
| survey_actual_day | 35,105 / 77,904 | 31 | 2004, 2019, 2021 | baseline/pending | Calendar day of the selected explicit household survey date: interview date in 2004 and last-visit date in 2019/2021; null in waves without a defensible household-level exact date. |
| survey_actual_month | 35,105 / 77,904 | 12 | 2004, 2019, 2021 | baseline/pending | Calendar month of the selected explicit household survey date: interview date in 2004 and last-visit date in 2019/2021; null in waves without a defensible household-level exact date. |
| survey_actual_year | 35,105 / 77,904 | 7 | 2004, 2019, 2021 | baseline/pending | Calendar year of the selected explicit household survey date: interview date in 2004 and last-visit date in 2019/2021; null in waves without a defensible household-level exact date. |
| survey_month | 62,896 / 77,904 | 12 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released survey month coerced to integer when parseable. |
| survey_wave | 77,904 / 77,904 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Normalized CSES release wave. |
| survey_year | 77,904 / 77,904 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | First calendar year represented by the normalized wave. |
| unknown_age_member_count | 77,904 / 77,904 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Number of roster members whose completed age is null after sentinel and range cleaning. |
| urban_rural | 77,904 / 77,904 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released urban/rural classification code; labels are not recoded across waves. |
| village_code | 62,920 / 77,904 | 31 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source village code normalized as an eight-character string. |
| working_age_member_count_15_64 | 77,904 / 77,904 | 14 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Number of roster members with valid completed age from 15 through 64. |

## final_HL_CSES

Unit: member-wave. 358,920 records; 37 fields.

| Field | Non-null / total | Observed distinct | Non-null waves | Review | Existing definition |
| --- | ---: | ---: | --- | --- | --- |
| absent_from_household | 358,791 / 358,920 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | member-reviewed | Harmonized indicator: 1=absent and 0=present; reference period is current status in 2004 and the past 7 days in later waves. |
| age | 358,919 / 358,920 | 103 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | member-reviewed | Completed age in years, retained from 0 through 120 without imputation. |
| birth_day | 343,279 / 358,920 | 31 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released day of birth retained from 1 through 31; don't-know and missing sentinels are null. |
| birth_month | 347,666 / 358,920 | 12 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released month of birth retained from 1 through 12; don't-know and missing sentinels are null. |
| birth_year | 358,656 / 358,920 | 118 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released year of birth retained from 1800 through the survey start year plus one; don't-know and missing sentinels are null. |
| commune_code | 284,201 / 358,920 | 25 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source commune code normalized as a six-character string. |
| dataset_name | 358,920 / 358,920 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | CSES plus the normalized survey wave. |
| district_code | 284,201 / 358,920 | 17 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source district code normalized as a four-character string. |
| ethnicity_harmonized | 358,771 / 358,920 | 8 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Cross-wave ethnicity: 1=Khmer, 2=Cham, 3=Other local/indigenous group, 4=Chinese, 5=Vietnamese, 6=Thai, 7=Lao, 8=Other. |
| ethnicity_source_code | 358,771 / 358,920 | 8 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released detailed ethnicity code retained for provenance; the 2004 missing sentinel is null. |
| father_line_number | 160,146 / 358,920 | 18 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released within-household line number for the member's father; no-parent-in-household and missing codes are null. |
| father_person_id | 159,962 / 358,920 | 33,648 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Person identifier derived only when Father Line Number matches another member of the same survey-wave household and is not a self-reference. |
| household_id | 358,920 / 358,920 | 27,036 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Wave-normalized household identifier. |
| household_weight | 284,201 / 358,920 | 5,537 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific household sampling weight; no imputation. |
| marital_status_harmonized | 259,265 / 358,920 | 4 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Cross-wave status: 1=Never married/never cohabited, 2=Married/cohabiting, 3=Widowed, 4=Divorced/separated. |
| marital_status_source_code | 259,265 / 358,920 | 6 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific marital-status code retained for provenance. |
| member_line_number | 358,920 / 358,920 | 17 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released within-household member line number, retained as an integer from 1 through 98. |
| mother_line_number | 187,235 / 358,920 | 16 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released within-household line number for the member's mother; no-parent-in-household and missing codes are null. |
| mother_person_id | 186,451 / 358,920 | 43,697 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Person identifier derived only when Mother Line Number matches another member of the same survey-wave household and is not a self-reference. |
| person_id | 358,920 / 358,920 | 153,316 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Wave-normalized person identifier. |
| person_weight | 284,201 / 358,920 | 90,971 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific person sampling weight; no imputation. |
| presence_reference_period | 358,920 / 358,920 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Reference period for the harmonized household-absence indicator. |
| province_code | 358,920 / 358,920 | 25 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source province code normalized as a two-character string. |
| psu | 358,920 / 358,920 | 1,676 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Wave-normalized primary sampling unit identifier. |
| relationship_to_household_head | 358,909 / 358,920 | 15 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | member-reviewed | Released relationship code from 1 through 15; the code list is stable across labeled waves. |
| sex | 358,920 / 358,920 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | member-reviewed | Released code: 1=Male and 2=Female. |
| source_archive | 358,920 / 358,920 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Raw archive path relative to the project root. |
| source_row_id | 358,920 / 358,920 | 358,920 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Deterministic identifier for the row in the member-roster source. |
| source_submodule | 358,920 / 358,920 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Stata member path inside the raw archive. |
| spouse_line_number | 144,917 / 358,920 | 17 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released within-household line number for the member's spouse; spouse-not-in-household and missing codes are null. |
| spouse_person_id | 142,736 / 358,920 | 65,188 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Person identifier derived only when Spouse Line Number matches another member of the same survey-wave household and is not a self-reference. |
| stratum | 341,481 / 358,920 | 59 | 2004, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released sampling stratum code retained as a string. |
| survey_month | 284,102 / 358,920 | 12 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released survey month coerced to integer when parseable. |
| survey_wave | 358,920 / 358,920 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Normalized CSES release wave. |
| survey_year | 358,920 / 358,920 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | First calendar year represented by the normalized wave. |
| urban_rural | 358,920 / 358,920 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released urban/rural classification code; labels are not recoded across waves. |
| village_code | 284,201 / 358,920 | 31 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source village code normalized as an eight-character string. |

## final_ED_CSES

Unit: education-record-wave. 343,204 records; 30 fields.

| Field | Non-null / total | Observed distinct | Non-null waves | Review | Existing definition |
| --- | ---: | ---: | --- | --- | --- |
| age | 343,199 / 343,204 | 103 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | age-2004 | Completed age in years, retained from 0 through 120 without imputation. |
| can_read | 335,868 / 343,204 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized indicator: 1=Yes and 0=No. |
| can_write | 335,857 / 343,204 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized indicator: 1=Yes and 0=No. |
| commune_code | 268,481 / 343,204 | 25 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source commune code normalized as a six-character string. |
| current_education_level_harmonized | 87,907 / 343,204 | 7 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Cross-wave level: 1=Preschool, 2=Primary, 3=Lower secondary, 4=Upper secondary, 5=Technical/vocational, 6=Higher education, 7=Other. |
| current_education_level_source_code | 87,960 / 343,204 | 24 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific current grade or level code, retained for provenance. |
| currently_attending_school | 269,884 / 343,204 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized indicator: 1=Yes and 0=No. |
| dataset_name | 343,204 / 343,204 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | CSES plus the normalized survey wave. |
| district_code | 268,481 / 343,204 | 17 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source district code normalized as a four-character string. |
| education_level_harmonized | 269,569 / 343,204 | 8 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Cross-wave level: 0=None, 1=Preschool, 2=Primary, 3=Lower secondary, 4=Upper secondary, 5=Technical/vocational, 6=Higher education, 7=Other. |
| ever_attended_school | 335,840 / 343,204 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized indicator: 1=Yes and 0=No. |
| highest_education_level_source_code | 269,915 / 343,204 | 26 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific detailed code, retained for provenance. |
| hl_link_matched | 343,204 / 343,204 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | 1 when the education record matches final_HL_CSES on survey wave and person identifier; otherwise 0. |
| household_id | 343,204 / 343,204 | 27,036 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Wave-normalized household identifier. |
| household_weight | 268,481 / 343,204 | 5,537 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific household sampling weight; no imputation. |
| person_id | 343,204 / 343,204 | 148,987 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Wave-normalized person identifier. |
| person_weight | 268,481 / 343,204 | 88,994 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific person sampling weight; no imputation. |
| province_code | 343,200 / 343,204 | 25 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source province code normalized as a two-character string. |
| psu | 343,204 / 343,204 | 1,676 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Wave-normalized primary sampling unit identifier. |
| sex | 343,200 / 343,204 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released code: 1=Male and 2=Female. |
| source_archive | 343,204 / 343,204 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Raw archive path relative to the project root. |
| source_row_id | 343,204 / 343,204 | 343,204 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Deterministic identifier for the row in the member-roster source. |
| source_submodule | 343,204 / 343,204 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Stata member path inside the raw archive. |
| stratum | 327,411 / 343,204 | 59 | 2004, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released sampling stratum code retained as a string. |
| survey_month | 268,385 / 343,204 | 12 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released survey month coerced to integer when parseable. |
| survey_wave | 343,204 / 343,204 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Normalized CSES release wave. |
| survey_year | 343,204 / 343,204 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | First calendar year represented by the normalized wave. |
| urban_rural | 343,200 / 343,204 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released urban/rural classification code; labels are not recoded across waves. |
| village_code | 268,481 / 343,204 | 31 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source village code normalized as an eight-character string. |
| years_attended_school | 218,532 / 343,204 | 26 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released completed years attended, retained from 0 through 30 without imputation; unavailable in 2004. |

## final_HO_CSES

Unit: housing-record-wave. 77,922 records; 50 fields.

| Field | Non-null / total | Observed distinct | Non-null waves | Review | Existing definition |
| --- | ---: | ---: | --- | --- | --- |
| boils_drinking_water | 60,726 / 77,922 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized released response: 1=Yes and 0=No. |
| commune_code | 62,919 / 77,922 | 25 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source commune code normalized as a six-character string. |
| dataset_name | 77,922 / 77,922 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | CSES plus the normalized survey wave. |
| district_code | 62,919 / 77,922 | 17 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source district code normalized as a four-character string. |
| drinking_water_treatment_frequency_source_code | 77,904 / 77,922 | 3 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released frequency code: 1=always, 2=sometimes, 3=never. |
| dwelling_maintenance_expense_riel | 77,204 / 77,922 | 229 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released dwelling maintenance and minor-repair expense in Cambodian riel; retain source reference-period interpretation. |
| dwelling_tenure_harmonized | 77,834 / 77,922 | 4 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Cross-wave code: 1=owned, 2=occupied rent-free, 3=rented, 4=other. |
| dwelling_tenure_source_code | 77,834 / 77,922 | 4 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | housing-qualified | Released dwelling legal-status or tenure code. |
| filters_drinking_water | 60,724 / 77,922 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized released response: 1=Yes and 0=No. |
| floor_area_square_meters | 77,780 / 77,922 | 328 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released occupied floor area in square meters; positive values are retained without imputation. |
| floor_material_source_code | 77,905 / 77,922 | 9 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific primary floor-material code; consult the variable dictionary before comparing detailed categories across waves. |
| has_toilet_facility | 77,882 / 77,922 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Wave-specific harmonized indicator distinguishing a reported toilet facility from no facility or open-land defecation. |
| hh_link_matched | 77,922 / 77,922 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | 1 when the housing record matches final_HH_CSES on survey wave and household identifier; otherwise 0. |
| household_id | 77,922 / 77,922 | 27,044 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Wave-normalized household identifier. |
| household_weight | 62,919 / 77,922 | 5,537 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific household sampling weight; no imputation. |
| households_in_housing_unit | 77,901 / 77,922 | 13 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released number of households sharing the housing unit, retained as a positive integer. |
| main_cooking_fuel_source_code | 77,897 / 77,922 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | housing-qualified | Released wave-specific main cooking-fuel code. |
| main_drinking_water_source_code | 77,898 / 77,922 | 14 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific main drinking-water source in the wet season. |
| main_lighting_source_code | 77,903 / 77,922 | 9 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | housing-qualified | Released wave-specific main lighting-source code. |
| monthly_battery_expense_riel | 77,903 / 77,922 | 224 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released household battery expense in Cambodian riel; no imputation or price adjustment. |
| monthly_charcoal_expense_riel | 77,904 / 77,922 | 244 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released household charcoal expense in Cambodian riel; no imputation or price adjustment. |
| monthly_electricity_expense_riel | 77,904 / 77,922 | 1,500 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released household electricity expense in Cambodian riel; no imputation or price adjustment. |
| monthly_firewood_expense_riel | 77,905 / 77,922 | 346 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released household firewood expense in Cambodian riel; no imputation or price adjustment. |
| monthly_garbage_collection_expense_riel | 77,903 / 77,922 | 97 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released monthly garbage-collection expense in Cambodian riel; no imputation or price adjustment. |
| monthly_gas_expense_riel | 77,906 / 77,922 | 419 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released household gas or LPG expense in Cambodian riel; no imputation or price adjustment. |
| monthly_imputed_rent_riel | 60,923 / 77,922 | 255 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released estimated monthly rent for a similar dwelling in Cambodian riel; unavailable in 2004. |
| monthly_kerosene_expense_riel | 77,906 / 77,922 | 213 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released household kerosene expense in Cambodian riel; no imputation or price adjustment. |
| monthly_other_energy_expense_riel | 77,896 / 77,922 | 192 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released other household energy expense in Cambodian riel; no imputation or price adjustment. |
| monthly_rent_paid_riel | 2,454 / 77,922 | 149 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released monthly dwelling rent paid in Cambodian riel; structurally null for non-renting households. |
| monthly_sewage_disposal_expense_riel | 77,900 / 77,922 | 195 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released monthly sewage or wastewater-disposal expense in Cambodian riel; no imputation or price adjustment. |
| monthly_water_charges_riel | 77,886 / 77,922 | 599 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released monthly water charges in Cambodian riel; exact missing sentinels and negative values are null, with no imputation or price adjustment. |
| province_code | 77,919 / 77,922 | 25 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source province code normalized as a two-character string. |
| psu | 77,922 / 77,922 | 1,676 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Wave-normalized primary sampling unit identifier. |
| roof_material_source_code | 77,905 / 77,922 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific primary roof-material code; consult the variable dictionary before comparing detailed categories across waves. |
| rooms_used | 77,803 / 77,922 | 16 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released number of rooms used by the household, excluding dedicated kitchen and bathroom spaces where specified. |
| source_archive | 77,922 / 77,922 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Raw archive path relative to the project root. |
| source_row_id | 77,922 / 77,922 | 77,922 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Deterministic identifier for the row in the member-roster source. |
| source_submodule | 77,922 / 77,922 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Stata member path inside the raw archive. |
| stratum | 74,326 / 77,922 | 59 | 2004, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released sampling stratum code retained as a string. |
| survey_month | 62,895 / 77,922 | 12 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released survey month coerced to integer when parseable. |
| survey_wave | 77,922 / 77,922 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Normalized CSES release wave. |
| survey_year | 77,922 / 77,922 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | First calendar year represented by the normalized wave. |
| toilet_facility_source_code | 77,882 / 77,922 | 9 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific toilet-facility code; detailed categories change in 2019. |
| treats_drinking_water | 77,904 / 77,922 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized indicator: 1 when treatment is always or sometimes, 0 when never, and null otherwise. |
| urban_rural | 77,919 / 77,922 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released urban/rural classification code; labels are not recoded across waves. |
| uses_alum_water_treatment | 60,723 / 77,922 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized released response: 1=Yes and 0=No. |
| uses_chemical_water_treatment | 60,724 / 77,922 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized released response: 1=Yes and 0=No. |
| uses_other_water_treatment | 60,718 / 77,922 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized released response: 1=Yes and 0=No. |
| village_code | 62,919 / 77,922 | 31 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source village code normalized as an eight-character string. |
| wall_material_source_code | 77,904 / 77,922 | 9 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific primary wall-material code; consult the variable dictionary before comparing detailed categories across waves. |

## final_EC_CSES

Unit: employment-record-wave. 332,903 records; 60 fields.

| Field | Non-null / total | Observed distinct | Non-null waves | Review | Existing definition |
| --- | ---: | ---: | --- | --- | --- |
| actively_seeking_work | 104,226 / 332,903 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized released response: 1=Yes and 0=No; later waves specify the past four weeks. |
| additional_jobs_count | 159,311 / 332,903 | 6 | 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released number of jobs beyond the main job in later-wave current-employment modules. |
| age | 332,900 / 332,903 | 101 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | age-2004 | Completed age in years, retained from 0 through 120 without imputation. |
| available_for_additional_work | 4,507 / 332,903 | 2 | 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized released response: 1=Yes and 0=No. |
| available_for_work | 16,582 / 332,903 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized released response: 1=Yes and 0=No. |
| commune_code | 258,182 / 332,903 | 25 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source commune code normalized as a six-character string. |
| dataset_name | 332,903 / 332,903 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | CSES plus the normalized survey wave. |
| desired_weekly_hours | 29,425 / 332,903 | 82 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released desired weekly hours; 98/99 sentinels are null. |
| district_code | 258,182 / 332,903 | 17 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source district code normalized as a four-character string. |
| hl_link_matched | 332,903 / 332,903 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | 1 when the current-employment record matches final_HL_CSES on survey wave and person identifier; otherwise 0. |
| hours_less_preferred | 916 / 332,903 | 44 | 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released number of fewer weekly hours preferred. |
| hours_more_preferred | 2,038 / 332,903 | 58 | 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released number of additional weekly hours preferred. |
| household_id | 332,903 / 332,903 | 27,035 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Wave-normalized household identifier. |
| household_weight | 258,182 / 332,903 | 5,537 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific household sampling weight; no imputation. |
| job_search_method_1_source_code | 973 / 332,903 | 7 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific first job-search method code. |
| job_search_method_2_source_code | 606 / 332,903 | 6 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific second job-search method code. |
| job_search_method_3_source_code | 203 / 332,903 | 7 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific third job-search method code. |
| latest_work_seasonal | 1,205 / 332,903 | 2 | 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized released response: 1=Yes and 0=No. |
| main_days_worked_last_month | 201,332 / 332,903 | 32 | 2004, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released main-job workdays in the last month, retained from 0 through 31. |
| main_employer_type_source_code | 201,964 / 332,903 | 11 | 2004, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific employer-type code. |
| main_employment_status_source_code | 201,924 / 332,903 | 6 | 2004, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific employment-status code. |
| main_hours_worked_past_7_days | 201,366 / 332,903 | 94 | 2004, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released main-job weekly hours; 98/99 sentinels are null. |
| main_industry_source_code | 201,973 / 332,903 | 291 | 2004, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released industry code retained at its wave-specific two- or four-character width. |
| main_job_was_abroad | 123,829 / 332,903 | 2 | 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized released response: 1=Yes and 0=No. |
| main_job_was_usual_past_7_days | 38,176 / 332,903 | 2 | 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized released response: 1=Yes and 0=No. |
| main_job_works_whole_year | 124,104 / 332,903 | 2 | 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized released response: 1=Yes and 0=No. |
| main_occupation_source_code | 201,978 / 332,903 | 214 | 2004, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released three-character occupation code; classification is not assumed stable across waves. |
| monthly_salary_wages_riel | 79,868 / 332,903 | 1,462 | 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released total salary and wages in nominal Cambodian riel for 2009-2021; no imputation or price adjustment. |
| months_actively_seeking_work | 294 / 332,903 | 12 | 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released active-search duration in months; 98/99 sentinels are null. |
| months_out_of_work | 1,267 / 332,903 | 32 | 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released duration out of work in months; 98/99 sentinels are null. |
| months_working_fewer_hours | 1,651 / 332,903 | 16 | 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released duration in months; 98/99 sentinels are null. |
| person_id | 332,903 / 332,903 | 146,361 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Wave-normalized person identifier. |
| person_weight | 258,182 / 332,903 | 85,519 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific person sampling weight; no imputation. |
| preferred_hours_change_source_code | 159,310 / 332,903 | 3 | 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released preference code for fewer, more, or unchanged hours. |
| province_code | 332,901 / 332,903 | 25 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source province code normalized as a two-character string. |
| psu | 332,903 / 332,903 | 1,676 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Wave-normalized primary sampling unit identifier. |
| reason_not_actively_seeking_source_code | 82,736 / 332,903 | 10 | 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific reason code. |
| reason_working_fewer_hours_source_code | 4,507 / 332,903 | 3 | 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific reason code. |
| second_work_screening_source_code | 109,967 / 332,903 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released 1/2 response retained as a source code because the wording shifts between job absence and unpaid work across waves. |
| secondary_days_worked_last_month | 42,661 / 332,903 | 32 | 2004, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released secondary-job workdays in the last month, retained from 0 through 31. |
| secondary_employer_type_source_code | 56,564 / 332,903 | 11 | 2004, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific secondary employer-type code. |
| secondary_employment_status_source_code | 56,559 / 332,903 | 6 | 2004, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific secondary employment-status code. |
| secondary_hours_worked_past_7_days | 56,504 / 332,903 | 80 | 2004, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released secondary-job weekly hours; 98/99 sentinels are null. |
| secondary_industry_source_code | 56,562 / 332,903 | 213 | 2004, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released wave-specific secondary industry code; null unless at least two occupations are reported. |
| secondary_job_was_usual_past_7_days | 13,592 / 332,903 | 2 | 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized released response: 1=Yes and 0=No. |
| secondary_job_works_whole_year | 35,103 / 332,903 | 2 | 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized released response: 1=Yes and 0=No. |
| secondary_occupation_source_code | 56,564 / 332,903 | 182 | 2004, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released three-character secondary occupation code; null unless at least two occupations are reported. |
| sex | 332,901 / 332,903 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released code: 1=Male and 2=Female. |
| source_archive | 332,903 / 332,903 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Raw archive path relative to the project root. |
| source_row_id | 332,903 / 332,903 | 332,903 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Deterministic identifier for the row in the member-roster source. |
| source_submodule | 332,903 / 332,903 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Stata member path inside the raw archive. |
| stratum | 317,135 / 332,903 | 59 | 2004, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released sampling stratum code retained as a string. |
| survey_month | 258,093 / 332,903 | 12 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released survey month coerced to integer when parseable. |
| survey_wave | 332,903 / 332,903 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Normalized CSES release wave. |
| survey_year | 332,903 / 332,903 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | First calendar year represented by the normalized wave. |
| total_hours_worked_past_7_days | 162,117 / 332,903 | 120 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released total weekly hours, with documented 98/99 sentinels set to null. |
| total_occupations_past_7_days | 233,621 / 332,903 | 8 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released total in 2004/2007 and derived as one plus additional jobs in later waves when a main job is reported. |
| urban_rural | 332,901 / 332,903 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Released urban/rural classification code; labels are not recoded across waves. |
| village_code | 258,182 / 332,903 | 31 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Source village code normalized as an eight-character string. |
| worked_at_least_one_hour_past_7_days | 316,735 / 332,903 | 2 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Harmonized released response: 1=Yes and 0=No; wording emphasizes paid work in later waves. |

## final_VL_CSES

Unit: village/PSU-wave. 5,718 records; 40 fields.

| Field | Non-null / total | Observed distinct | Non-null waves | Review | Existing definition |
| --- | ---: | ---: | --- | --- | --- |
| boys_below_18_count | 4,709 / 5,718 | 1,023 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2021 | baseline/pending | Released count of boys below age 18. |
| commune_code | 4,818 / 5,718 | 25 | 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Source commune code normalized as a six-character string. |
| commune_name | 2,016 / 5,718 | 1,108 | 2019, 2021 | baseline/pending | Released commune name where available; no name lookup is imposed on earlier waves. |
| dataset_name | 5,718 / 5,718 | 8 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | CSES plus the normalized survey wave. |
| district_code | 4,818 / 5,718 | 17 | 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Source district code normalized as a four-character string. |
| district_name | 2,016 / 5,718 | 198 | 2019, 2021 | baseline/pending | Released district name where available; no name lookup is imposed on earlier waves. |
| enumeration_area_count | 2,378 / 5,718 | 36 | 2014, 2016, 2021 | baseline/pending | Released number of enumeration areas; available only in later detailed village modules. |
| five_year_population_movement_source_code | 4,710 / 5,718 | 4 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2021 | baseline/pending | Released code 1-4 describing whether more people moved in, moved out, both equally, or neither over five years. |
| girls_below_18_count | 4,709 / 5,718 | 1,051 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2021 | baseline/pending | Released count of girls below age 18. |
| hh_psu_link_matched | 5,718 / 5,718 | 1 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | 1 when the village record's survey-wave PSU occurs in final_HH_CSES; otherwise 0. |
| households_in_surveyed_enumeration_area | 2,378 / 5,718 | 148 | 2014, 2016, 2021 | baseline/pending | Released household count for the surveyed enumeration area where a village has multiple enumeration areas. |
| men_18_plus_count | 4,709 / 5,718 | 1,306 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2021 | baseline/pending | Released count of men age 18 or older. |
| population_18_plus_count | 4,709 / 5,718 | 1,955 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2021 | baseline/pending | Released count of village residents age 18 or older. |
| population_below_18_count | 4,709 / 5,718 | 1,565 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2021 | baseline/pending | Released count of village residents below age 18. |
| province_code | 5,718 / 5,718 | 25 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Source province code normalized as a two-character string. |
| province_name | 2,016 / 5,718 | 25 | 2019, 2021 | baseline/pending | Released province name where available; no name lookup is imposed on earlier waves. |
| psu | 5,718 / 5,718 | 1,674 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Wave-normalized primary sampling unit identifier. |
| sample_household_count | 5,718 / 5,718 | 10 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Number of final_HH_CSES records linked to the survey-wave PSU. |
| sample_person_count | 5,718 / 5,718 | 114 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Number of final_HL_CSES records linked to the survey-wave PSU. |
| source_archive | 5,718 / 5,718 | 8 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Raw archive path relative to the project root. |
| source_row_id | 5,718 / 5,718 | 5,718 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Deterministic identifier for the row in the member-roster source. |
| source_submodule | 5,718 / 5,718 | 8 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Stata member path inside the raw archive. |
| stratum | 5,361 / 5,718 | 59 | 2004, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Released sampling stratum code retained as a string. |
| survey_month | 4,761 / 5,718 | 12 | 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Released survey month coerced to integer when parseable. |
| survey_wave | 5,718 / 5,718 | 8 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Normalized CSES release wave. |
| survey_year | 5,718 / 5,718 | 8 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | First calendar year represented by the normalized wave. |
| urban_rural | 5,718 / 5,718 | 2 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Released urban/rural classification code; labels are not recoded across waves. |
| village_code | 4,818 / 5,718 | 31 | 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Source village code normalized as an eight-character string. |
| village_female_count | 5,714 / 5,718 | 1,950 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Released directly in 2019 and otherwise derived as girls below 18 plus women age 18 or older. |
| village_household_count | 5,718 / 5,718 | 1,111 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Released number of households living in the village. |
| village_household_count_five_years_ago | 4,709 / 5,718 | 944 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2021 | baseline/pending | Released retrospective number of village households five years earlier. |
| village_land_area_square_kilometers | 4,706 / 5,718 | 2,064 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2021 | baseline/pending | Released village land area in square kilometers; positive values are retained without imputation. |
| village_male_count | 5,717 / 5,718 | 1,908 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Released directly in 2019 and otherwise derived as boys below 18 plus men age 18 or older. |
| village_name | 2,016 / 5,718 | 1,599 | 2019, 2021 | baseline/pending | Released village name where available; no name lookup is imposed on earlier waves. |
| village_person_count | 5,717 / 5,718 | 2,796 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2019, 2021 | baseline/pending | Released total village population. |
| village_person_count_five_years_ago | 4,706 / 5,718 | 2,313 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2021 | baseline/pending | Released retrospective village population five years earlier; the exact 99999 missing sentinel is null. |
| village_reference_day | 4,656 / 5,718 | 31 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2021 | baseline/pending | Released day for the village population reference date. |
| village_reference_month | 4,685 / 5,718 | 12 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2021 | baseline/pending | Released month for the village population reference date. |
| village_reference_year | 4,704 / 5,718 | 19 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2021 | baseline/pending | Released year for the village population reference date. |
| women_18_plus_count | 4,706 / 5,718 | 1,375 | 2004, 2007, 2009, 2011-12, 2014, 2016, 2021 | baseline/pending | Released count of women age 18 or older. |

## final_SURVEY_DATE_CSES

Unit: household-date-record-wave. 77,904 records; 28 fields.

| Field | Non-null / total | Observed distinct | Non-null waves | Review | Existing definition |
| --- | ---: | ---: | --- | --- | --- |
| candidate_actual_month | 35,105 / 77,904 | 12 | 2004, 2019, 2021 | baseline/pending | Calendar month of Candidate Reference Date. |
| candidate_actual_year | 35,105 / 77,904 | 7 | 2004, 2019, 2021 | baseline/pending | Calendar year of Candidate Reference Date. |
| candidate_date_within_documented_period | 14,984 / 77,904 | 2 | 2004 | baseline/pending | For 2004, 1 when Candidate Reference Date is within November 2003 through January 2005 and 0 otherwise; null where no exact documented period check is encoded. |
| candidate_reference_date | 35,105 / 77,904 | 758 | 2004, 2019, 2021 | baseline/pending | Transparent candidate for future exposure alignment: interview date in 2004 and last visit in 2019/2021. It has not been adopted as the final analytical anchor. |
| candidate_reference_definition | 35,139 / 77,904 | 2 | 2004, 2019, 2021 | baseline/pending | Source role used to construct Candidate Reference Date. |
| confirmed_survey_month | 35,139 / 77,904 | 12 | 2004, 2019, 2021 | baseline/pending | Raw Month of Survey in 2019/2021, or month of the explicitly labeled interview date in 2004; null when unavailable. |
| confirmed_survey_time_source | 35,139 / 77,904 | 2 | 2004, 2019, 2021 | baseline/pending | Field definition supplying the confirmed household survey year/month. |
| confirmed_survey_year | 35,139 / 77,904 | 7 | 2004, 2019, 2021 | baseline/pending | Raw Year of Survey in 2019/2021, or year of the explicitly labeled interview date in 2004; null when no household-level year is confirmed. |
| confirmed_year_differs | 35,139 / 77,904 | 2 | 2004, 2019, 2021 | baseline/pending | 1 when Confirmed Survey Year differs from Nominal Survey Year, 0 when equal, null without a confirmed year. |
| dataset_name | 77,904 / 77,904 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | CSES survey-date staging dataset plus normalized release wave. |
| date_precision | 77,904 / 77,904 | 3 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Exact day where a confirmed date is available, month where only Survey Month is available, otherwise unavailable. |
| exact_date_source_archive | 35,139 / 77,904 | 3 | 2004, 2019, 2021 | baseline/pending | Original raw archive containing the exact date fields. |
| exact_date_source_submodule | 35,139 / 77,904 | 3 | 2004, 2019, 2021 | baseline/pending | Stata member containing the exact date fields. |
| first_visit_date | 10,080 / 77,904 | 329 | 2021 | baseline/pending | Date constructed only from fields explicitly labeled as the first household visit. |
| household_id | 77,904 / 77,904 | 27,036 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Wave-normalized household identifier. |
| interview_date | 14,984 / 77,904 | 98 | 2004 | baseline/pending | Date constructed only from day/month/year fields explicitly labeled as the interview date. |
| last_visit_date | 35,053 / 77,904 | 825 | 2004, 2019, 2021 | baseline/pending | Date constructed only from fields explicitly labeled as the last household visit. |
| nominal_survey_year | 77,904 / 77,904 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | First year encoded by the release-wave name; not necessarily the actual interview year. |
| nominal_year_differs | 35,105 / 77,904 | 2 | 2004, 2019, 2021 | baseline/pending | 1 when Candidate Actual Year differs from Nominal Survey Year, 0 when equal, null without an exact candidate date. |
| reinterview_date | 18 / 77,904 | 9 | 2004 | baseline/pending | Quality-control re-interview date where released; it is not the main survey date. |
| released_survey_month | 20,155 / 77,904 | 12 | 2019, 2021 | baseline/pending | Household-level month from the same raw other-information source as Year of Survey; retained for linkage validation. |
| released_survey_year | 20,155 / 77,904 | 4 | 2019, 2021 | baseline/pending | Household-level year from a raw field explicitly labeled Year of Survey; released in 2019 and 2021. |
| survey_actual_day | 35,105 / 77,904 | 31 | 2004, 2019, 2021 | baseline/pending | Calendar day of the selected explicit household survey date: interview date in 2004 and last-visit date in 2019/2021; null otherwise. |
| survey_actual_month | 35,105 / 77,904 | 12 | 2004, 2019, 2021 | baseline/pending | Calendar month of the selected explicit household survey date: interview date in 2004 and last-visit date in 2019/2021; null otherwise. |
| survey_actual_year | 35,105 / 77,904 | 7 | 2004, 2019, 2021 | baseline/pending | Calendar year of the selected explicit household survey date: interview date in 2004 and last-visit date in 2019/2021; null otherwise. |
| survey_month | 62,896 / 77,904 | 12 | 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Month retained from the household linkage spine; may be the only available timing field. |
| survey_month_matches_candidate | 20,121 / 77,904 | 2 | 2019, 2021 | baseline/pending | 1 when released Survey Month equals Candidate Actual Month, 0 when they differ, null when either is unavailable. |
| survey_wave | 77,904 / 77,904 | 10 | 2004, 2007, 2009, 2011-12, 2013, 2014, 2016, 2017, 2019, 2021 | baseline/pending | Normalized CSES release wave. |
