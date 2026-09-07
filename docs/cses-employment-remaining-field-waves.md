# Final 19 employment fields: wave-by-wave evidence

[Summary and findings](cses-employment-remaining-review.md)

All counts are unweighted member-wave observations. They are not actual interview respondents or unique longitudinal people. Numeric fields do not have a fixed number of choices. Distinct observed values are not questionnaire options. Route checks only cover located complete questions. Blank optional search slots are allowed. 2014 is a draft; 2021 inherits the screening wording conflict. No routes are transferred to 2007/2017/2019.

## additional_jobs_count

Additional jobs/economic activities beyond the main job in the past seven days. Zero means no additional job.

The 0–10 retention bound is an inherited implementation rule, not a printed maximum. Do not confuse additional jobs with total jobs. No counts are imputed for 2004/2007.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 0 / 74,719 | 0 | Numeric | No selected alias | No |
| 2007 | 0 / 15,766 | 0 | Numeric | No selected alias | No |
| 2009 | 35,179 / 51,460 | 5 | Numeric | q15_c11 | Yes |
| 2011-12 | 10,105 / 14,829 | 5 | Numeric | q15_c11 | Yes |
| 2013 | 9,946 / 15,774 | 5 | Numeric | Q15_C11 | Yes |
| 2014 | 31,277 / 49,252 | 5 | Numeric | q15_c11 | Draft |
| 2016 | 10,150 / 15,498 | 5 | Numeric | q15_c11 | Yes |
| 2017 | 10,087 / 15,482 | 5 | Numeric | Q15_C11 | No |
| 2019 | 26,748 / 40,379 | 6 | Numeric | q15_c11 | No |
| 2021 | 25,819 / 39,744 | 5 | Numeric | q15_c11 | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | 0 | 0 | 23 |
| 2011-12 | None | 0 | 0 | 0 | 0 |
| 2013 | None | 0 | 0 | 0 | 4 |
| 2014 | None | 0 | 2 | 1 | 5 |
| 2016 | None | 0 | 1 | 0 | 1 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | None | 0 | 3 | 0 | 4 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2009 | 15 Econo_Status_1 | CJ16 (11) | CJ16 | Numeric entry / derived total |
| 2011-12 | 15 Econo_Status_1 | CW19 (11) | CW19 | Numeric entry / derived total |
| 2014 | 15 Econo_Status_1 | CX19 (11) | CX19 | Numeric entry / derived total |
| 2013 | 15 Econo_Status_1 | CX19 (11) | CX19 | Numeric entry / derived total |
| 2016 | 15 Econo_Status_1 | CX19 (11) | CX19 | Numeric entry / derived total |
| 2021 | 15 Current Econo-2 | AE24 (11) | AE24 | Numeric entry / derived total |

## total_occupations_past_7_days

Total occupation count: directly reported in 2004/2007; later derived as additional jobs plus one only when a main occupation code is present.

2004 code 9 is explicitly labelled missing but remains 9 in 244 stored records. Later totals depend on a present main occupation code and are not a direct answer to a total-count question. Unknown counts must not be filled with zero.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 58,673 / 74,719 | 6 | Numeric | q13a12 | Yes |
| 2007 | 15,643 / 15,766 | 5 | Numeric | q13ac14 | No |
| 2009 | 35,179 / 51,460 | 5 | Numeric | q15_c11 | Yes |
| 2011-12 | 10,104 / 14,829 | 5 | Numeric | q15_c11 | Yes |
| 2013 | 9,946 / 15,774 | 5 | Numeric | Q15_C11 | Yes |
| 2014 | 31,276 / 49,252 | 5 | Numeric | q15_c11 | Draft |
| 2016 | 10,150 / 15,498 | 5 | Numeric | q15_c11 | Yes |
| 2017 | 10,087 / 15,482 | 5 | Numeric | Q15_C11 | No |
| 2019 | 26,747 / 40,379 | 6 | Numeric | q15_c11 | No |
| 2021 | 25,816 / 39,744 | 5 | Numeric | q15_c11 | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | 0 | 0 | 0 |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | 0 | 0 | 23 |
| 2011-12 | None | 0 | 0 | 0 | 1 |
| 2013 | None | 0 | 0 | 0 | 4 |
| 2014 | None | 0 | 1 | 1 | 5 |
| 2016 | None | 0 | 1 | 0 | 1 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | None | 0 | 2 | 0 | 6 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2004 | 13 Econ. Status | AS15 (12) | AS15 | Numeric entry / derived total |
| 2009 | 15 Econo_Status_1 | CJ16 (11) | CJ16 | Numeric entry / derived total |
| 2011-12 | 15 Econo_Status_1 | CW19 (11) | CW19 | Numeric entry / derived total |
| 2014 | 15 Econo_Status_1 | CX19 (11) | CX19 | Numeric entry / derived total |
| 2013 | 15 Econo_Status_1 | CX19 (11) | CX19 | Numeric entry / derived total |
| 2016 | 15 Econo_Status_1 | CX19 (11) | CX19 | Numeric entry / derived total |
| 2021 | 15 Current Econo-2 | AE24 (11) | AE24 | Numeric entry / derived total |

Dictionary qualifications:

- 2004: raw 9 = missing (244 source records; 244 stored with that code). Stored codes outside verified choices: None.

## secondary_job_works_whole_year

Whether the secondary occupation is worked throughout the whole year.

Two Yes/No choices. Eleven valid 2021 raw answers were suppressed by the inherited known-total-below-two rule; one nonbinary 2019 raw value was excluded. This review preserves both the source archive and existing cleaned results.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 0 / 74,719 | 0 | Unverified | No selected alias | No |
| 2007 | 0 / 15,766 | 0 | Unverified | No selected alias | No |
| 2009 | 0 / 51,460 | 0 | Unverified | No selected alias | No |
| 2011-12 | 3,651 / 14,829 | 2 | 2 (complete_questionnaire) | q15_c17b | Yes |
| 2013 | 2,493 / 15,774 | 2 | 2 (complete_questionnaire) | Q15_C17B | Yes |
| 2014 | 7,413 / 49,252 | 2 | 2 (complete_questionnaire) | q15_c17b | Draft |
| 2016 | 2,529 / 15,498 | 2 | 2 (complete_questionnaire) | q15_c17b | Yes |
| 2017 | 2,432 / 15,482 | 2 | Unverified | Q15_C17B | No |
| 2019 | 8,817 / 40,379 | 2 | 2 (embedded_stata_labels) | q15_c17b | No |
| 2021 | 7,768 / 39,744 | 2 | 2 (complete_questionnaire) | q15_c17b | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2011-12 | None | 0 | 0 | 0 | 12 |
| 2013 | None | 0 | 0 | 4 | 6 |
| 2014 | None | 0 | 0 | 3 | 28 |
| 2016 | None | 0 | 1 | 0 | 12 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | 0.0: 1 | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | None | 11 | 1 | 0 | 2 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2011-12 | 15 Econo_Status_2 | K19 (17b) | K19 | 1 = Yes (>>18a); 2 = No |
| 2014 | 15 Econo_Status_2 | J19 (17b) | J19 | 1 = Yes (>>17d); 2 = No |
| 2013 | 15 Econo_Status_2 | J19 (17b) | J19 | 1 = Yes (>>17d); 2 = No |
| 2016 | 15 Econo_Status_2 | J19 (17b) | J19 | 1 = Yes (>>17d); 2 = No |
| 2021 | 15 Current Econo-4 | J25 (17b) | J25 | 1 = Yes (>>17d); 2 = No |

## secondary_job_was_usual_past_7_days

Whether the secondary occupation during the past seven days is seasonal. The legacy word usual is a naming error, not a polarity error.

The complete questions say seasonal, not usual. Keep the legacy name for compatibility until an additive correction is published. Whole-year Yes skips this item; do not invert whole-year work to construct it. Three valid 2021 raw answers were suppressed by the count rule.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 0 / 74,719 | 0 | Unverified | No selected alias | No |
| 2007 | 0 / 15,766 | 0 | Unverified | No selected alias | No |
| 2009 | 0 / 51,460 | 0 | Unverified | No selected alias | No |
| 2011-12 | 2,013 / 14,829 | 2 | 2 (complete_questionnaire) | q15_c17c | Yes |
| 2013 | 1,139 / 15,774 | 2 | 2 (complete_questionnaire) | Q15_C17C | Yes |
| 2014 | 3,507 / 49,252 | 2 | 2 (complete_questionnaire) | q15_c17c | Draft |
| 2016 | 726 / 15,498 | 2 | 2 (complete_questionnaire) | q15_c17c | Yes |
| 2017 | 686 / 15,482 | 2 | Unverified | Q15_C17C | No |
| 2019 | 3,131 / 40,379 | 2 | 2 (embedded_stata_labels) | q15_c17c | No |
| 2021 | 2,390 / 39,744 | 2 | 2 (complete_questionnaire) | q15_c17c | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2011-12 | None | 0 | 0 | 1 | 31 |
| 2013 | None | 0 | 0 | 2 | 23 |
| 2014 | None | 0 | 87 | 9 | 69 |
| 2016 | None | 0 | 9 | 4 | 16 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | 0.0: 1, 3.0: 1 | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | 0.0: 2 | 3 | 12 | 0 | 2 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2011-12 | 15 Econo_Status_2 | P19 (17c) | P19 | 1 = Yes; 2 = No |
| 2014 | 15 Econo_Status_2 | M19 (17c) | M19 | 1 = Yes; 2 = No |
| 2013 | 15 Econo_Status_2 | M19 (17c) | M19 | 1 = Yes; 2 = No |
| 2016 | 15 Econo_Status_2 | M19 (17c) | M19 | 1 = Yes; 2 = No |
| 2021 | 15 Current Econo-4 | M25 (17c) | M25 | 1 = Yes; 2 = No |

## monthly_salary_wages_riel

Salary/wages last month from all jobs/economic activities, cash or in kind, nominal Cambodian riel. Not household income, not main-job-only income.

The recorded amount covers all jobs, including in-kind wages, in nominal riel. Eligibility is employee status in either main or secondary occupation. The 2004 archive has separate job-level wages; they cannot simply be called the later all-job total.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 0 / 74,719 | 0 | Numeric | No selected alias | No |
| 2007 | 0 / 15,766 | 0 | Numeric | No selected alias | No |
| 2009 | 9,708 / 51,460 | 583 | Numeric | q15_c20 | Yes |
| 2011-12 | 3,611 / 14,829 | 374 | Numeric | q15_c20 | Yes |
| 2013 | 4,206 / 15,774 | 292 | Numeric | Q15_C20 | Yes |
| 2014 | 14,078 / 49,252 | 532 | Numeric | q15_c20 | Draft |
| 2016 | 4,949 / 15,498 | 362 | Numeric | q15_c20 | Yes |
| 2017 | 5,145 / 15,482 | 359 | Numeric | Q15_C20 | No |
| 2019 | 26,539 / 40,379 | 508 | Numeric | q15_c20 | No |
| 2021 | 11,632 / 39,744 | 433 | Numeric | q15_c20 | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | 0 | 144 | 0 |
| 2011-12 | None | 0 | 0 | 16 | 0 |
| 2013 | None | 0 | 0 | 1 | 0 |
| 2014 | None | 0 | 1 | 69 | 0 |
| 2016 | None | 0 | 0 | 5 | 16 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | None | 0 | 12 | 22 | 11 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2009 | 15 Econo_Status_2 | W16 (20) | W16 | Numeric entry / derived total |
| 2011-12 | 15 Econo_Status_2 | AS19 (20) | AS19 | Numeric entry / derived total |
| 2014 | 15 Econo_Status_2 | AS19 (20) | AS19 | Numeric entry / derived total |
| 2013 | 15 Econo_Status_2 | AS19 (20) | AS19 | Numeric entry / derived total |
| 2016 | 15 Econo_Status_2 | AS19 (20) | AS19 | Numeric entry / derived total |
| 2021 | 15 Current Econo-4 | AS25 (20) | AS25 | Numeric entry / derived total |

## preferred_hours_change_source_code

Preference for fewer, more or unchanged hours, conditional on corresponding income changes in 2009 onward.

2009 onward: 1=Less, 2=More, 3=Unchanged. The related 2004 question uses 1=Same, 2=Less, 3=More and lacks the explicit income-change condition. It requires a qualified crosswalk, not direct code reuse.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 0 / 74,719 | 0 | Unverified | No selected alias | No |
| 2007 | 0 / 15,766 | 0 | Unverified | No selected alias | No |
| 2009 | 35,199 / 51,460 | 3 | 3 (complete_questionnaire) | q15_c21 | Yes |
| 2011-12 | 10,105 / 14,829 | 3 | 3 (complete_questionnaire) | q15_c21 | Yes |
| 2013 | 9,941 / 15,774 | 3 | 3 (complete_questionnaire) | Q15_C21 | Yes |
| 2014 | 31,267 / 49,252 | 3 | 3 (complete_questionnaire) | q15_c21 | Draft |
| 2016 | 10,149 / 15,498 | 3 | 3 (complete_questionnaire) | q15_c21 | Yes |
| 2017 | 10,087 / 15,482 | 3 | Unverified | Q15_C21 | No |
| 2019 | 26,744 / 40,379 | 3 | 3 (embedded_stata_labels) | q15_c21 | No |
| 2021 | 25,818 / 39,744 | 3 | 3 (complete_questionnaire) | q15_c21 | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | 0 | 0 | 3 |
| 2011-12 | None | 0 | 0 | 0 | 0 |
| 2013 | None | 0 | 0 | 0 | 9 |
| 2014 | None | 0 | 1 | 1 | 14 |
| 2016 | None | 0 | 1 | 0 | 2 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | None | 0 | 4 | 0 | 6 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2009 | 15 Econo_Status_2 | AM16 (21) | AM16 | 1 = Less hours; 2 = More hours; 3 = Unchanged hours  (>> NEXT PERSON) |
| 2011-12 | 15 Econo_Status_2 | BA19 (21) | BA19 | 1 = Less hours; 2 = More hours; 3 = Unchanged hours  (>> NEXT PERSON) |
| 2014 | 15 Econo_Status_2 | BA19 (21) | BA19 | 1 = Less hours; 2 = More hours; 3 = Unchanged hours  (>> NEXT PERSON) |
| 2013 | 15 Econo_Status_2 | BA19 (21) | BA19 | 1 = Less hours; 2 = More hours; 3 = Unchanged hours  (>> NEXT PERSON) |
| 2016 | 15 Econo_Status_2 | BA19 (21) | BA19 | 1 = Less hours; 2 = More hours; 3 = Unchanged hours  (>> NEXT PERSON) |
| 2021 | 15 Current Econo-4 | BA25 (21) | BA25 | 1 = Less hours; 2 = More hours => 22b; 3 = Unchanged hours  (>> NEXT PERSON) |

## hours_less_preferred

Number of hours to subtract from the past-seven-day hours, not the desired total.

Later forms explicitly ask for the reduction, not desired total hours. The 2009 single q15_c22 field is omitted by the split-column aliases and has a shorter more/less question; recovery requires a separate interpretation decision.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 0 / 74,719 | 0 | Numeric | No selected alias | No |
| 2007 | 0 / 15,766 | 0 | Numeric | No selected alias | No |
| 2009 | 0 / 51,460 | 0 | Numeric | No selected alias | No |
| 2011-12 | 170 / 14,829 | 26 | Numeric | q15_c22a | Yes |
| 2013 | 239 / 15,774 | 31 | Numeric | Q15_C22A | Yes |
| 2014 | 339 / 49,252 | 38 | Numeric | q15_c22a | Draft |
| 2016 | 65 / 15,498 | 18 | Numeric | q15_c22a | Yes |
| 2017 | 62 / 15,482 | 15 | Numeric | Q15_C22A | No |
| 2019 | 33 / 40,379 | 13 | Numeric | q15_c22a | No |
| 2021 | 8 / 39,744 | 5 | Numeric | q15_c22a | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2011-12 | None | 0 | 0 | 0 | 0 |
| 2013 | None | 0 | 0 | 0 | 0 |
| 2014 | None | 0 | 11 | 0 | 2 |
| 2016 | None | 0 | 4 | 0 | 0 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | None | 0 | 1 | 0 | 0 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2011-12 | 15 Econo_Status_2 | BG19 (22a) | BG19 | Numeric entry / derived total |
| 2014 | 15 Econo_Status_2 | BG19 (22a) | BG19 | Numeric entry / derived total |
| 2013 | 15 Econo_Status_2 | BG19 (22a) | BG19 | Numeric entry / derived total |
| 2016 | 15 Econo_Status_2 | BG19 (22a) | BG19 | Numeric entry / derived total |
| 2021 | 15 Current Econo-4 | BG25 (22a) | BG25 | Numeric entry / derived total |

## hours_more_preferred

Number of hours to add to the past-seven-day hours, not the desired total.

Later forms explicitly ask for the additional hours, not desired total hours. The 2009 combined field is not automatically split or treated as an increment in this review.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 0 / 74,719 | 0 | Numeric | No selected alias | No |
| 2007 | 0 / 15,766 | 0 | Numeric | No selected alias | No |
| 2009 | 0 / 51,460 | 0 | Numeric | No selected alias | No |
| 2011-12 | 761 / 14,829 | 48 | Numeric | q15_c22b | Yes |
| 2013 | 198 / 15,774 | 37 | Numeric | Q15_C22B | Yes |
| 2014 | 363 / 49,252 | 44 | Numeric | q15_c22b | Draft |
| 2016 | 78 / 15,498 | 27 | Numeric | q15_c22b | Yes |
| 2017 | 58 / 15,482 | 27 | Numeric | Q15_C22B | No |
| 2019 | 173 / 40,379 | 43 | Numeric | q15_c22b | No |
| 2021 | 407 / 39,744 | 41 | Numeric | q15_c22b | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2011-12 | None | 0 | 0 | 0 | 1 |
| 2013 | None | 0 | 0 | 0 | 1 |
| 2014 | None | 0 | 2 | 0 | 2 |
| 2016 | None | 0 | 0 | 0 | 0 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | None | 0 | 3 | 0 | 0 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2011-12 | 15 Econo_Status_2 | BL19 (22b) | BL19 | Numeric entry / derived total |
| 2014 | 15 Econo_Status_2 | BL19 (22b) | BL19 | Numeric entry / derived total |
| 2013 | 15 Econo_Status_2 | BL19 (22b) | BL19 | Numeric entry / derived total |
| 2016 | 15 Econo_Status_2 | BL19 (22b) | BL19 | Numeric entry / derived total |
| 2021 | 15 Current Econo-4 | BL25 (22b) | BL25 | Numeric entry / derived total |

## available_for_additional_work

Availability to work more hours during the past seven days or start within two weeks, if more hours are preferred.

The past-seven-days/next-two-weeks availability window and more-hours preference gate are explicit in six inspected forms. One 2019 code 0 was previously converted to NULL. NULL is not No.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 0 / 74,719 | 0 | Unverified | No selected alias | No |
| 2007 | 0 / 15,766 | 0 | Unverified | No selected alias | No |
| 2009 | 2,473 / 51,460 | 2 | 2 (complete_questionnaire) | q15_c23 | Yes |
| 2011-12 | 762 / 14,829 | 2 | 2 (complete_questionnaire) | q15_c23 | Yes |
| 2013 | 199 / 15,774 | 2 | 2 (complete_questionnaire) | Q15_C23 | Yes |
| 2014 | 363 / 49,252 | 2 | 2 (complete_questionnaire) | q15_c23 | Draft |
| 2016 | 78 / 15,498 | 2 | 2 (complete_questionnaire) | q15_c23 | Yes |
| 2017 | 57 / 15,482 | 2 | Unverified | Q15_C23 | No |
| 2019 | 169 / 40,379 | 2 | 2 (embedded_stata_labels) | q15_c23 | No |
| 2021 | 406 / 39,744 | 2 | 2 (complete_questionnaire) | q15_c23 | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | 0 | 1 | 0 |
| 2011-12 | None | 0 | 0 | 0 | 0 |
| 2013 | None | 0 | 0 | 0 | 0 |
| 2014 | None | 0 | 0 | 0 | 0 |
| 2016 | None | 0 | 0 | 0 | 0 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | 0.0: 1 | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | None | 0 | 2 | 0 | 0 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2009 | 15 Econo_Status_2 | AX16 (23) | AX16 | 1 = Yes; 2 = No |
| 2011-12 | 15 Econo_Status_2 | BQ19 (23) | BQ19 | 1 = Yes; 2 = No |
| 2014 | 15 Econo_Status_2 | BQ19 (23) | BQ19 | 1 = Yes; 2 = No |
| 2013 | 15 Econo_Status_2 | BQ19 (23) | BQ19 | 1 = Yes; 2 = No |
| 2016 | 15 Econo_Status_2 | BQ19 (23) | BQ19 | 1 = Yes; 2 = No |
| 2021 | 15 Current Econo-4 | BQ25 (23) | BQ25 | 1 = Yes; 2 = No |

## reason_working_fewer_hours_source_code

Reason for working fewer hours than preferred, if more hours are preferred; not restricted to those available for extra work.

Three options: temporary illness, not enough work available, other reasons. Ask when more hours are preferred, regardless of whether more work is currently possible. Do not impose availability Yes from the following duration question.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 0 / 74,719 | 0 | Unverified | No selected alias | No |
| 2007 | 0 / 15,766 | 0 | Unverified | No selected alias | No |
| 2009 | 2,473 / 51,460 | 3 | 3 (complete_questionnaire) | q15_c24 | Yes |
| 2011-12 | 762 / 14,829 | 3 | 3 (complete_questionnaire) | q15_c24 | Yes |
| 2013 | 199 / 15,774 | 3 | 3 (complete_questionnaire) | Q15_C24 | Yes |
| 2014 | 363 / 49,252 | 3 | 3 (complete_questionnaire) | q15_c24 | Draft |
| 2016 | 78 / 15,498 | 3 | 3 (complete_questionnaire) | q15_c24 | Yes |
| 2017 | 57 / 15,482 | 3 | Unverified | Q15_C24 | No |
| 2019 | 168 / 40,379 | 3 | 3 (embedded_stata_labels) | q15_c24 | No |
| 2021 | 407 / 39,744 | 3 | 3 (complete_questionnaire) | q15_c24 | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | 0 | 1 | 0 |
| 2011-12 | None | 0 | 0 | 0 | 0 |
| 2013 | None | 0 | 0 | 0 | 0 |
| 2014 | None | 0 | 0 | 0 | 0 |
| 2016 | None | 0 | 0 | 0 | 0 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | None | 0 | 2 | 1 | 0 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2009 | 15 Econo_Status_2 | BD16 (24) | BD16 | 1 = Temporary illness; 2 = Not enough work  available; 3 = Other reasons |
| 2011-12 | 15 Econo_Status_2 | BY19 (24) | BY19 | 1 = Temporary illness; 2 = Not enough work  available; 3 = Other reasons |
| 2014 | 15 Econo_Status_2 | BY19 (24) | BY19 | 1 = Temporary illness; 2 = Not enough work  available; 3 = Other reasons |
| 2013 | 15 Econo_Status_2 | BY19 (24) | BY19 | 1 = Temporary illness; 2 = Not enough work  available; 3 = Other reasons |
| 2016 | 15 Econo_Status_2 | BY19 (24) | BY19 | 1 = Temporary illness; 2 = Not enough work  available; 3 = Other reasons |
| 2021 | 15 Current Econo-4 | BY25 (24) | BY25 | 1 = Temporary illness; 2 = Not enough work  available; 3 = Other reasons |

## months_working_fewer_hours

Months of working fewer hours than desired while available for more work; zero is less than one month in later inspected forms.

For 2011 onward this is a month duration, with less than one month entered as 0. In 2019/2021 code 98 is explicitly labelled unknown. The omitted 2009 month/year pair contains calendar-like years and cannot be multiplied into a duration.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 0 / 74,719 | 0 | Numeric | No selected alias | No |
| 2007 | 0 / 15,766 | 0 | Numeric | No selected alias | No |
| 2009 | 0 / 51,460 | 0 | Numeric | No selected alias | No |
| 2011-12 | 612 / 14,829 | 12 | Numeric | q15_c25 | Yes |
| 2013 | 163 / 15,774 | 11 | Numeric | Q15_C25 | Yes |
| 2014 | 309 / 49,252 | 12 | Numeric | q15_c25 | Draft |
| 2016 | 67 / 15,498 | 12 | Numeric | q15_c25 | Yes |
| 2017 | 45 / 15,482 | 8 | Numeric | Q15_C25 | No |
| 2019 | 139 / 40,379 | 11 | Numeric | q15_c25 | No |
| 2021 | 316 / 39,744 | 15 | Numeric | q15_c25 | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2011-12 | None | 0 | 0 | 0 | 39 |
| 2013 | None | 0 | 0 | 0 | 16 |
| 2014 | None | 0 | 1 | 0 | 19 |
| 2016 | None | 0 | 0 | 0 | 0 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | 98.0: 7 | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | 98.0: 24 | 0 | 2 | 0 | 24 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2011-12 | 15 Econo_Status_2 | CE19 (25) | CE19 | Numeric entry / derived total |
| 2014 | 15 Econo_Status_2 | CE19 (25) | CE19 | Numeric entry / derived total |
| 2013 | 15 Econo_Status_2 | CE19 (25) | CE19 | Numeric entry / derived total |
| 2016 | 15 Econo_Status_2 | CE19 (25) | CE19 | Numeric entry / derived total |
| 2021 | 15 Current Econo-4 | CE25 (25) | CE25 | Numeric entry / derived total |

Dictionary qualifications:

- 2019: raw 98 = Don't know (7 source records; 0 stored with that code). Stored codes outside verified choices: None.
- 2021: raw 98 = Don't know (24 source records; 0 stored with that code). Stored codes outside verified choices: None.

## job_search_method_1_source_code

First recorded job-search method slot, not a ranking or a separate question.

Six substantive search methods. Four 2004 code-9 values are explicitly missing but remain stored. The slots form one multiple-response question; blank optional slots do not imply a missing interview.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 408 / 74,719 | 7 | 6 (complete_questionnaire) | q13a09a | Yes |
| 2007 | 94 / 15,766 | 6 | Unverified | q13ac11a | No |
| 2009 | 135 / 51,460 | 6 | 6 (complete_questionnaire) | q15_c27a | Yes |
| 2011-12 | 29 / 14,829 | 4 | 6 (complete_questionnaire) | q15_c27a | Yes |
| 2013 | 30 / 15,774 | 4 | 6 (complete_questionnaire) | Q15_C27A | Yes |
| 2014 | 71 / 49,252 | 5 | 6 (complete_questionnaire) | q15_c27a | Draft |
| 2016 | 17 / 15,498 | 4 | 6 (complete_questionnaire) | q15_c27a | Yes |
| 2017 | 16 / 15,482 | 4 | Unverified | Q15_C27A | No |
| 2019 | 63 / 40,379 | 5 | 6 (embedded_stata_labels) | q15_c27a | No |
| 2021 | 110 / 39,744 | 6 | 6 (complete_questionnaire) | q15_c27a | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | 0 | 0 | 0 |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | 4 | 0 | 0 |
| 2011-12 | None | 0 | 0 | 0 | 0 |
| 2013 | None | 0 | 0 | 0 | 0 |
| 2014 | None | 0 | 11 | 0 | 0 |
| 2016 | None | 0 | 0 | 0 | 0 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | None | 0 | 4 | 0 | 0 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2004 | 13 Econ. Status | AD15 (9a) | AD15 | 1 = Applied to    advertisement; 2 = Contacted potential    employers; 3 = Enquired with friends    relatives etc.; 4 = Employment agency; 5 = Tried to start own    business but failed; 6 = Other (specify) |
| 2009 | 15 Econo_Status_2 | CB16 (27a) | CB16 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |
| 2011-12 | 15 Econo_Status_2 | CR19 (27a) | CR19 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |
| 2014 | 15 Econo_Status_2 | CR19 (27a) | CR19 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |
| 2013 | 15 Econo_Status_2 | CR19 (27a) | CR19 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |
| 2016 | 15 Econo_Status_2 | CR19 (27a) | CR19 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |
| 2021 | 15 Current Econo-4 | CR25 (27a) | CR25 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |

Dictionary qualifications:

- 2004: raw 9 = missing (4 source records; 4 stored with that code). Stored codes outside verified choices: 9: 4.

## job_search_method_2_source_code

Second optional recorded job-search method slot, not a ranking or a separate question.

Six substantive methods, with 2004 code 0 explicitly meaning no more ways recorded (293 records). Treat 0 as an empty slot in a future interpreted interface, not a seventh method.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 408 / 74,719 | 6 | 6 (complete_questionnaire) | q13a09b | Yes |
| 2007 | 23 / 15,766 | 4 | Unverified | q13ac11b | No |
| 2009 | 53 / 51,460 | 5 | 6 (complete_questionnaire) | q15_c27b | Yes |
| 2011-12 | 18 / 14,829 | 3 | 6 (complete_questionnaire) | q15_c27b | Yes |
| 2013 | 5 / 15,774 | 2 | 6 (complete_questionnaire) | Q15_C27B | Yes |
| 2014 | 21 / 49,252 | 5 | 6 (complete_questionnaire) | q15_c27b | Draft |
| 2016 | 4 / 15,498 | 3 | 6 (complete_questionnaire) | q15_c27b | Yes |
| 2017 | 5 / 15,482 | 2 | Unverified | Q15_C27B | No |
| 2019 | 30 / 40,379 | 5 | 6 (embedded_stata_labels) | q15_c27b | No |
| 2021 | 39 / 39,744 | 5 | 6 (complete_questionnaire) | q15_c27b | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | 0 | 0 | 0 |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | 2 | 0 | 80 |
| 2011-12 | None | 0 | 0 | 0 | 11 |
| 2013 | None | 0 | 0 | 0 | 25 |
| 2014 | None | 0 | 3 | 0 | 42 |
| 2016 | None | 0 | 0 | 0 | 13 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | None | 0 | 1 | 0 | 68 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2004 | 13 Econ. Status | AF15 (9b) | AD15 | 1 = Applied to    advertisement; 2 = Contacted potential    employers; 3 = Enquired with friends    relatives etc.; 4 = Employment agency; 5 = Tried to start own    business but failed; 6 = Other (specify) |
| 2009 | 15 Econo_Status_2 | CD16 (27b) | CB16 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |
| 2011-12 | 15 Econo_Status_2 | CT19 (27b) | CR19 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |
| 2014 | 15 Econo_Status_2 | CT19 (27b) | CR19 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |
| 2013 | 15 Econo_Status_2 | CT19 (27b) | CR19 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |
| 2016 | 15 Econo_Status_2 | CT19 (27b) | CR19 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |
| 2021 | 15 Current Econo-4 | CT25 (27b) | CR25 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |

Dictionary qualifications:

- 2004: raw 0 = *no more ways recorded (293 source records; 293 stored with that code). Stored codes outside verified choices: 0: 293.

## job_search_method_3_source_code

Third optional recorded job-search method slot, not a ranking or a separate question.

Six substantive methods, with 2004 code 0 explicitly meaning no more ways recorded (105 records). Preserve slot order without claiming it is an importance ranking.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 115 / 74,719 | 5 | 6 (complete_questionnaire) | q13a09c | Yes |
| 2007 | 6 / 15,766 | 3 | Unverified | q13ac11c | No |
| 2009 | 17 / 51,460 | 5 | 6 (complete_questionnaire) | q15_c27c | Yes |
| 2011-12 | 8 / 14,829 | 3 | 6 (complete_questionnaire) | q15_c27c | Yes |
| 2013 | 1 / 15,774 | 1 | 6 (complete_questionnaire) | Q15_C27C | Yes |
| 2014 | 8 / 49,252 | 5 | 6 (complete_questionnaire) | q15_c27c | Draft |
| 2016 | 1 / 15,498 | 1 | 6 (complete_questionnaire) | q15_c27c | Yes |
| 2017 | 2 / 15,482 | 1 | Unverified | Q15_C27C | No |
| 2019 | 13 / 40,379 | 4 | 6 (embedded_stata_labels) | q15_c27c | No |
| 2021 | 32 / 39,744 | 6 | 6 (complete_questionnaire) | q15_c27c | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | 0 | 0 | 293 |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | 0 | 0 | 114 |
| 2011-12 | None | 0 | 0 | 0 | 21 |
| 2013 | None | 0 | 0 | 0 | 29 |
| 2014 | None | 0 | 1 | 0 | 53 |
| 2016 | None | 0 | 0 | 0 | 16 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | None | 0 | 0 | 0 | 74 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2004 | 13 Econ. Status | AH15 (9c) | AD15 | 1 = Applied to    advertisement; 2 = Contacted potential    employers; 3 = Enquired with friends    relatives etc.; 4 = Employment agency; 5 = Tried to start own    business but failed; 6 = Other (specify) |
| 2009 | 15 Econo_Status_2 | CF16 (27c) | CB16 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |
| 2011-12 | 15 Econo_Status_2 | CV19 (27c) | CR19 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |
| 2014 | 15 Econo_Status_2 | CV19 (27c) | CR19 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |
| 2013 | 15 Econo_Status_2 | CV19 (27c) | CR19 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |
| 2016 | 15 Econo_Status_2 | CV19 (27c) | CR19 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |
| 2021 | 15 Current Econo-4 | CV25 (27c) | CR25 | 1 = Applied to advertisement; 2 = Contacted (potential) employers; 3 = Enquired with friends relatives etc; 4 = Employment agency; 5 = Tried to start own business but failed; 6 = Other (specify) |

Dictionary qualifications:

- 2004: raw 0 = *no more ways recorded (105 source records; 105 stored with that code). Stored codes outside verified choices: 0: 105.

## desired_weekly_hours

Desired total weekly hours. In 2004 both workers wanting different hours and nonworkers can reach the item; later forms route jobseekers here.

Desired total weekly hours have a broader 2004 route than later jobseeker-only wording. The 263 excluded 2004 code-99 values are labelled missing. The 168-hour bound and exclusion of 98 elsewhere remain inherited rules, not universally documented questionnaire limits.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 22,430 / 74,719 | 82 | Numeric | q13a10 | Yes |
| 2007 | 6,522 / 15,766 | 51 | Numeric | q13ac12 | No |
| 2009 | 135 / 51,460 | 18 | Numeric | q15_c29 | Yes |
| 2011-12 | 29 / 14,829 | 8 | Numeric | q15_c29 | Yes |
| 2013 | 30 / 15,774 | 9 | Numeric | Q15_C29 | Yes |
| 2014 | 71 / 49,252 | 15 | Numeric | q15_c29 | Draft |
| 2016 | 17 / 15,498 | 7 | Numeric | q15_c29 | Yes |
| 2017 | 16 / 15,482 | 6 | Numeric | Q15_C29 | No |
| 2019 | 64 / 40,379 | 13 | Numeric | q15_c29 | No |
| 2021 | 111 / 39,744 | 12 | Numeric | q15_c29 | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | 99.0: 263 | 0 | 11 | 10 | 111 |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | 4 | 0 | 0 |
| 2011-12 | None | 0 | 0 | 0 | 0 |
| 2013 | None | 0 | 0 | 0 | 0 |
| 2014 | None | 0 | 11 | 0 | 0 |
| 2016 | None | 0 | 0 | 0 | 0 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | None | 0 | 5 | 0 | 0 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2004 | 13 Econ. Status | AJ15 (10) | AJ15 | Numeric entry / derived total |
| 2009 | 15 Econo_Status_2 | CM16 (29) | CM16 | Numeric entry / derived total |
| 2011-12 | 15 Econo_Status_2 | DC19 (29) | DC19 | Numeric entry / derived total |
| 2014 | 15 Econo_Status_2 | DC19 (29) | DC19 | Numeric entry / derived total |
| 2013 | 15 Econo_Status_2 | DC19 (29) | DC19 | Numeric entry / derived total |
| 2016 | 15 Econo_Status_2 | DC19 (29) | DC19 | Numeric entry / derived total |
| 2021 | 15 Current Econo-4 | DC25 (29) | DC25 | Numeric entry / derived total |

Dictionary qualifications:

- 2004: raw 99 = missing (263 source records; 0 stored with that code). Stored codes outside verified choices: None.

## months_actively_seeking_work

Months out of work and actively looking for work, distinct from total months out of work.

The active-search duration is not the same as total months out of work. The 2009 q15_c30a/b pair is omitted by the single-column alias and its year component contains calendar-like years. Do not calculate months without resolving that inconsistency.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 0 / 74,719 | 0 | Numeric | No selected alias | No |
| 2007 | 0 / 15,766 | 0 | Numeric | No selected alias | No |
| 2009 | 0 / 51,460 | 0 | Numeric | No selected alias | No |
| 2011-12 | 23 / 14,829 | 7 | Numeric | q15_c30 | Yes |
| 2013 | 25 / 15,774 | 8 | Numeric | Q15_C30 | Yes |
| 2014 | 59 / 49,252 | 9 | Numeric | q15_c30 | Draft |
| 2016 | 16 / 15,498 | 7 | Numeric | q15_c30 | Yes |
| 2017 | 13 / 15,482 | 4 | Numeric | Q15_C30 | No |
| 2019 | 56 / 40,379 | 10 | Numeric | q15_c30 | No |
| 2021 | 102 / 39,744 | 12 | Numeric | q15_c30 | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2011-12 | None | 0 | 0 | 0 | 6 |
| 2013 | None | 0 | 0 | 0 | 5 |
| 2014 | None | 0 | 8 | 0 | 9 |
| 2016 | None | 0 | 1 | 0 | 2 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | 98.0: 4 | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | 98.0: 7 | 0 | 4 | 0 | 8 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2011-12 | 15 Econo_Status_2 | DQ19 (30) | DQ19 | Numeric entry / derived total |
| 2014 | 15 Econo_Status_2 | DQ19 (30) | DQ19 | Numeric entry / derived total |
| 2013 | 15 Econo_Status_2 | DQ19 (30) | DQ19 | Numeric entry / derived total |
| 2016 | 15 Econo_Status_2 | DQ19 (30) | DQ19 | Numeric entry / derived total |
| 2021 | 15 Current Econo-4 | DL25 (30) | DL25 | Numeric entry / derived total |

Dictionary qualifications:

- 2019: raw 98 = Don't know months (4 source records; 0 stored with that code). Stored codes outside verified choices: None.
- 2021: raw 98 = Don't know months (7 source records; 0 stored with that code). Stored codes outside verified choices: None.

## reason_not_actively_seeking_source_code

Reason for not actively seeking work in the past four weeks; codes 6–8 bypass the later out-of-work items in 2011 onward.

Nine printed reasons in the six inspected 2009+ forms. Two stored 2019 zeros have no meaning in the printed/embedded 1–9 dictionary. The 2007 archive has a related q13ac10 column, but its household question and routing remain unverified.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 0 / 74,719 | 0 | Unverified | No selected alias | No |
| 2007 | 0 / 15,766 | 0 | Unverified | No selected alias | No |
| 2009 | 16,153 / 51,460 | 9 | 9 (complete_questionnaire) | q15_c31 | Yes |
| 2011-12 | 4,696 / 14,829 | 9 | 9 (complete_questionnaire) | q15_c31 | Yes |
| 2013 | 5,796 / 15,774 | 9 | 9 (complete_questionnaire) | Q15_C31 | Yes |
| 2014 | 17,950 / 49,252 | 9 | 9 (complete_questionnaire) | q15_c31 | Draft |
| 2016 | 5,336 / 15,498 | 9 | 9 (complete_questionnaire) | q15_c31 | Yes |
| 2017 | 5,384 / 15,482 | 9 | Unverified | Q15_C31 | No |
| 2019 | 13,593 / 40,379 | 10 | 9 (embedded_stata_labels) | q15_c31 | No |
| 2021 | 13,828 / 39,744 | 9 | 9 (complete_questionnaire) | q15_c31 | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | 26 | 0 | 0 |
| 2011-12 | None | 0 | 1 | 0 | 0 |
| 2013 | None | 0 | 2 | 0 | 0 |
| 2014 | None | 0 | 42 | 0 | 0 |
| 2016 | None | 0 | 8 | 1 | 0 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | None | 0 | 20 | 1 | 2 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2009 | 15 Econo_Status_2 | CV16 (31) | CV16 | 1 = Believes no work is available; 2 = Awaiting result of application; 3 = Waiting to start new job; 4 = Permanent disabled; 5 = Illness/desease/injured; 6 = Too young, too old, retired; 7 = Student; 8 = Housekeeping, caring for children, elderly or disabled; 9 = Other reasons (specify) |
| 2011-12 | 15 Econo_Status_2 | DW19 (31) | DW19 | 1 = Believes no work is available; 2 = Awaiting result of application; 3 = Waiting to start new job; 4 = Permanent disabled; 5 = Illness/desease/injured; 6 = Too young, too old, retired; 7 = Student; 8 = Housekeeping, caring for children, elderly or disabled; 9 = Other reason, specify.... |
| 2014 | 15 Econo_Status_2 | DW19 (31) | DW19 | 1 = Believes no work is available; 2 = Awaiting result of application; 3 = Waiting to start new job; 4 = Permanent disabled; 5 = Illness/disease/injured; 6 = Too young, too old, retired; 7 = Student; 8 = Housekeeping, caring for children, elderly or disabled; 9 = Other reason, specify.... |
| 2013 | 15 Econo_Status_2 | DW19 (31) | DW19 | 1 = Believes no work is available; 2 = Awaiting result of application; 3 = Waiting to start new job; 4 = Permanent disabled; 5 = Illness/disease/injured; 6 = Too young, too old, retired; 7 = Student; 8 = Housekeeping, caring for children, elderly or disabled; 9 = Other reason, specify.... |
| 2016 | 15 Econo_Status_2 | DW19 (31) | DW19 | 1 = Believes no work is available; 2 = Awaiting result of application; 3 = Waiting to start new job; 4 = Permanent disabled; 5 = Illness/disease/injured; 6 = Too young, too old, retired; 7 = Student; 8 = Housekeeping, caring for children, elderly or disabled; 9 = Other reason, specify.... |
| 2021 | 15 Current Econo-4 | DR25 (31) | DR25 | 1 = Believes no work is available; 2 = Awaiting result of application; 3 = Waiting to start new job; 4 = Permanent disabled; 5 = Illness/disease/injured; 6 = Too young, too old, retired; 7 = Student; 8 = Housekeeping, caring for children, elderly or disabled; 9 = Other reason, specify.... |

Dictionary qualifications:

- 2019: Stored codes outside verified choices: 0: 2.

## months_out_of_work

Total months out of work, looking or not looking, reached through the non-seeking route in the inspected later forms.

2011+ printed item includes looking and not looking for work, but is reached via not-seeking and reason codes other than 6–8. It is not a universal duration for everyone without work. Most excluded 98 values are labelled unknown; one 2019 code 99 lacks that label.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 0 / 74,719 | 0 | Numeric | No selected alias | No |
| 2007 | 0 / 15,766 | 0 | Numeric | No selected alias | No |
| 2009 | 0 / 51,460 | 0 | Numeric | No selected alias | No |
| 2011-12 | 71 / 14,829 | 17 | Numeric | q15_c32 | Yes |
| 2013 | 43 / 15,774 | 19 | Numeric | Q15_C32 | Yes |
| 2014 | 298 / 49,252 | 16 | Numeric | q15_c32 | Draft |
| 2016 | 75 / 15,498 | 11 | Numeric | q15_c32 | Yes |
| 2017 | 70 / 15,482 | 12 | Numeric | Q15_C32 | No |
| 2019 | 360 / 40,379 | 22 | Numeric | q15_c32 | No |
| 2021 | 350 / 39,744 | 23 | Numeric | q15_c32 | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2011-12 | None | 0 | 3 | 0 | 85 |
| 2013 | None | 0 | 1 | 0 | 149 |
| 2014 | None | 0 | 17 | 0 | 397 |
| 2016 | None | 0 | 3 | 0 | 157 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | 98.0: 107, 99.0: 1 | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | 98.0: 238 | 0 | 7 | 2 | 240 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2011-12 | 15 Econo_Status_2 | EF19 (32) | EF19 | Numeric entry / derived total |
| 2014 | 15 Econo_Status_2 | EF19 (32) | EF19 | Numeric entry / derived total |
| 2013 | 15 Econo_Status_2 | EF19 (32) | EF19 | Numeric entry / derived total |
| 2016 | 15 Econo_Status_2 | EF19 (32) | EF19 | Numeric entry / derived total |
| 2021 | 15 Current Econo-4 | EA25 (32) | EA25 | Numeric entry / derived total |

Dictionary qualifications:

- 2019: raw 98 = Don't know (107 source records; 0 stored with that code). Stored codes outside verified choices: None.
- 2021: raw 98 = Don't know (238 source records; 0 stored with that code). Stored codes outside verified choices: None.

## latest_work_seasonal

Whether the latest job was seasonal, asked after less than 13 months out of work in the inspected later forms. Not current main/secondary seasonality.

Two Yes/No choices, under the non-seeking/reason route and less than 13 months out of work. The latest job is not necessarily the main or secondary current job. Four nonbinary raw codes were previously excluded.

| Wave | Non-null / EC rows | Distinct | Options | Raw field | Full question |
| --- | ---: | ---: | --- | --- | --- |
| 2004 | 0 / 74,719 | 0 | Unverified | No selected alias | No |
| 2007 | 0 / 15,766 | 0 | Unverified | No selected alias | No |
| 2009 | 0 / 51,460 | 0 | Unverified | No selected alias | No |
| 2011-12 | 77 / 14,829 | 2 | 2 (complete_questionnaire) | q15_c33 | Yes |
| 2013 | 33 / 15,774 | 2 | 2 (complete_questionnaire) | Q15_C33 | Yes |
| 2014 | 308 / 49,252 | 2 | 2 (complete_questionnaire) | q15_c33 | Draft |
| 2016 | 73 / 15,498 | 2 | 2 (complete_questionnaire) | q15_c33 | Yes |
| 2017 | 61 / 15,482 | 2 | Unverified | Q15_C33 | No |
| 2019 | 333 / 40,379 | 2 | 2 (embedded_stata_labels) | q15_c33 | No |
| 2021 | 320 / 39,744 | 2 | 2 (complete_questionnaire) | q15_c33 | Yes |

| Wave | Cleaner exclusions (code: count) | Count-suppressed | Outside known route | Unknown route, answered | NULL inside route |
| --- | --- | ---: | ---: | ---: | ---: |
| 2004 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2007 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2009 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2011-12 | None | 0 | 10 | 7 | 0 |
| 2013 | None | 0 | 4 | 4 | 0 |
| 2014 | None | 0 | 30 | 16 | 1 |
| 2016 | None | 0 | 7 | 0 | 1 |
| 2017 | None | 0 | Not assessed | Not assessed | Not assessed |
| 2019 | 0.0: 1, 8.0: 1 | 0 | Not assessed | Not assessed | Not assessed |
| 2021 | 0.0: 1, 3.0: 1 | 0 | 6 | 0 | 0 |

Cleaner exclusions and secondary-count suppression are separate historical stages. Derivation-related NULLs are recorded separately in the aggregate review. These counts overlap other diagnostics and must not be summed as people.

| Wave | Question sheet | Printed slot | Shared candidate anchor | Options as printed |
| --- | --- | --- | --- | --- |
| 2011-12 | 15 Econo_Status_2 | EL19 (33) | EL19 | 1 = Yes; 2 = No |
| 2014 | 15 Econo_Status_2 | EL19 (33) | EL19 | 1 = Yes; 2 = No |
| 2013 | 15 Econo_Status_2 | EL19 (33) | EL19 | 1 = Yes; 2 = No |
| 2016 | 15 Econo_Status_2 | EL19 (33) | EL19 | 1 = Yes; 2 = No |
| 2021 | 15 Current Econo-4 | EG25 (33) | EG25 | 1 = Yes; 2 = No |

## Evidence archive

The [aggregate review](../data/processing/cses/employment_remaining_review_v1/review.json) contains exact literal cell texts, source-file and archive-member hashes, candidate IDs, source-variable IDs, fresh Stata dictionaries and complete aggregate frequencies. It does not contain individual identifiers or new database values.
