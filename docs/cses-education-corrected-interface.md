# Corrected CSES education analysis interface

This version corrects the reviewed current-education-level mapping while preserving the original
physical release and all historical evidence. Use `cses_analysis.cses_ed_aligned_v1` for the corrected
ED analysis values. The unchanged `cses_data."final_ED_CSES"`, `public."final_ED_CSES"` and
`cses_analysis.cses_ed_age_v1` remain historical interfaces and still contain the old current-level
group for these 30 records. They are not silently redirected.

Publication and verification evidence are recorded in the
[release note](releases/cses-education-current-postgraduate-v1.md).

## Exact correction

| Wave | Current source code | Old group | Corrected group | Records | Evidence |
| --- | ---: | --- | --- | ---: | --- |
| 2013 | 21 | 7=Other | 6=Higher education | 6 | Original English questionnaire |
| 2014 | 21 | 7=Other | 6=Higher education | 18 | User-approved draft qualification retained |
| 2016 | 21 | 7=Other | 6=Higher education | 6 | Original English questionnaire |

The three forms print `Postgraduate studies` at `02 Education!AF7`. The user requested the correction
after reviewing the 30-row scope, including the 2014 draft. This release does not reinterpret the
eight 2017 code-21 records: their missing household-form evidence remains explicit.
Highest-completed education code 21 still means Other; it is a different question and is unchanged.

## Fields and population

The view has **343,204 member-wave records and 37 columns**, with the same keys and no row filter.
It builds on the 34-column age-qualified ED view, replacing only the current-level grouping for
the 30 approved records, and adds:

| Added field | Meaning |
| --- | --- |
| `current_level_before_correction` | Original inherited current-level group, for every row |
| `current_level_correction_version` | `cses-education-current-postgraduate-v1` on the 30 changed rows; NULL elsewhere |
| `current_level_evidence_status` | Source-questionnaire correction, user-approved 2014 draft, unresolved 2017, or unchanged/not-newly-certified |

The existing four `age_2004_*` fields are preserved. The three age-96 members remain explicitly
top-coded; no exact age is invented. Original current-level source codes, highest-completed levels,
weights and all other data values are unchanged. Correction counts are not extra respondents.

The additive `cses_analysis.cses_ed_current_level_rule_v1` view holds three source-rule rows with
source-variable ID, original source file and hash, sheet/cell, label, review hash, release ID and
approval qualification. This interface release does not insert a physical-table mapping or load run
into the historical metadata catalog; its versioned rules and execution evidence describe the
analysis-view overlay, not an update to the physical canonical release.

## Query examples

```sql
SELECT survey_wave, current_level_evidence_status,
       current_level_before_correction, current_education_level_harmonized,
       count(*) AS records
FROM cses_analysis.cses_ed_aligned_v1
WHERE current_level_correction_version IS NOT NULL
GROUP BY 1, 2, 3, 4
ORDER BY 1;

SELECT survey_wave, source_label, source_file, source_sheet, source_cell,
       documentation_status
FROM cses_analysis.cses_ed_current_level_rule_v1
ORDER BY survey_wave;
```

A matching versioned [Parquet artifact](../data/processing/cses/education_corrected_v1/final_ED_CSES.parquet)
is generated from the preserved baseline, age rule and correction. The original Parquet path is
unchanged. The local version uses the current repository-relative archive paths; database paths
retain the historical prefix, normalized only during comparisons.

## Interpretation limits and following work

This fixes one mapping defect, not every ED variable. The earlier
[ED review](cses-education-alignment.md) and [field-wave denominators](cses-education-field-wave-review.md)
remain unchanged historical evidence; their counts of non-null records are unchanged by this
non-null-to-non-null correction. The 17 contradictory attendance records, four unmatched ED records,
three household-form gaps and other recorded restrictions remain unresolved or qualified.

EC screening review continues separately in the
[employment brief](cses-employment-screening-alignment.md). No common cross-wave labour-force
definition is adopted by either release.

## Reproduction and recovery boundary

The new publisher never uses `CREATE OR REPLACE`, updates a physical table or overwrites a historical
artifact. It binds the accepted ED review, original data and code hashes, creates a private external
schema-only backup, rehearses the full transaction with rollback, then publishes two new views with
reader grants. Independent validation checks every projected value, all 35 physical-table fingerprints,
all pre-existing interface definitions, reader access and retained age qualifications.

After publication, use:

```bash
.venv/bin/python rsc/cses_db/publish_cses_education_correction.py validate
.venv/bin/python rsc/cses_db/publish_cses_education_correction.py export
```

Earlier validators that freeze the entire historical interface catalog may intentionally reject the
two additional view names. Do not weaken or rewrite their accepted evidence; this release's validator
provides the current complete protected-state check. Removing the new views or restoring an old dump
requires a separately scoped recovery decision. Git/DVC archival is separate and is not implied by
database publication.
