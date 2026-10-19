# CSES Database

This repository owns the reproducible ingestion, alignment, validation, publication, and lineage
workflow for the Cambodia Socio-Economic Survey (CSES) in the `mda` PostgreSQL database.

The project separates four kinds of state:

- Git owns code, tests, mapping specifications, and documentation under `rsc/` and `docs/`.
- DVC owns source archives and reproducible data artifacts under `data/`, plus runtime settings under
  `etc/`.
- PostgreSQL owns the current transactional catalog, approved mappings, load history, and published
  analytical relations.
- Database backups remain external recovery artifacts and are not substitutes for Git or DVC.

## Using the CSES database

The database is **`mda` (PostgreSQL)**. For research, start with the explicitly named
`cses_analysis` views below, not a publication script. The ingestion and technical validation
of the approved releases are complete; study-specific adjustments remain a separate research
decision. This guide reflects the releases validated on **2026-10-18**.

### Connect and inspect safely

For the existing local PostgreSQL instance, connect with your configured database login:

```bash
psql -X -v ON_ERROR_STOP=1 -d mda
```

If connecting from another machine, obtain the actual host, port and authorized login from
the database administrator; they are not supplied by this repository. Do not put credentials
in Git or DVC. `mda_readonly` is the reader role, not necessarily a directly usable login.
With a login authorized to assume it, run:

```sql
BEGIN READ ONLY;
SET LOCAL ROLE mda_readonly;
SELECT current_database(), current_user, current_setting('transaction_read_only');

-- Discover the published analysis interfaces and their columns.
SELECT table_name
FROM information_schema.views
WHERE table_schema = 'cses_analysis'
ORDER BY table_name;

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'cses_analysis'
  AND table_name = 'cses_health_screen_unified_v1'
ORDER BY ordinal_position;
ROLLBACK;
```

Run the query examples below inside the same `BEGIN READ ONLY` / `SET LOCAL ROLE` /
`ROLLBACK` pattern. A login lacking permission to assume the reader role needs administrator
configuration, not a rerun of ingestion or publication.

### Which relation should I query?

| Research need | Recommended relation | Scope and documentation |
| --- | --- | --- |
| Member spine, selected age and education | `cses_analysis.cses_education_unified_v1` | All 15 waves, 571,699 member-wave rows; eight qualified education targets, native inputs and statuses. [Education contract](docs/cses-education-unified-interface.md) |
| Education availability and denominators | `cses_analysis.cses_education_coverage_v1`, `cses_analysis.cses_education_matrix_v1` | Target/wave coverage, routing and questionnaire evidence; inspect before choosing a denominator. [Coverage definitions](docs/cses-education-unified-interface.md#qualified-coverage-and-use) |
| Recent illness/injury screening | `cses_analysis.cses_health_screen_unified_v1` | All 15 wave rosters; use `illness_injury_30d_qualified` for the strict eight-wave subset. [Health screening contract](docs/cses-health-screen-interface.md) |
| Health screening availability and denominators | `cses_analysis.cses_health_screen_coverage_v1`, `cses_analysis.cses_health_screen_matrix_v1` | Age-band denominators, annual statuses and source/form evidence. [Coverage limits](docs/cses-health-screen-interface.md#coverage-and-qualifications) |
| Province, district, commune and village source codes | `cses_analysis.cses_person_geography_v2`, `cses_analysis.cses_geography_coverage_v2` | All 15 waves; code linkage does not certify historical village entities or village geometry. [Geography contract](docs/cses-additional-waves.md#geography-and-provenance-access) |
| Employment and occupation/industry interpretations | `cses_analysis.cses_ec_classification_v1` | Historical ten-wave EC scope, 332,903 records; not a unified 15-wave employment interface. [EC contract](docs/cses-classification-corrected-interface.md) |
| Housing categories | `cses_analysis.cses_housing_categories_v4` | Historical ten-wave housing scope, 77,922 records, including 19 unmatched HH records. [Housing contract](docs/cses-housing-2021-resolution.md) |
| Historical illness-type/care review | `cses_analysis.cses_health_illness_v1` | Historical ten-wave health-source scope, 358,859 records; not the newer 15-wave screening contract. [Illness/care contract](docs/cses-health-database-release.md) |
| Household, roster, education, employment, housing or timing source projections | `cses_data` relations described below | Published source projections preserve native codes and qualifications; not every archived variable is materialized. [Variable brief](docs/cses-variable-brief.md) and [additional-wave release](docs/cses-additional-waves.md#additional-wave-database-release) |

The 15 wave labels are `1996`, `1997`, `1999`, `2004`, `2007`, `2009`, `2011-12`,
`2013`, `2014`, `2016`, `2017`, `2019`, `2021`, `2023` and `2025`. Use `survey_wave`
as text; `2011-12` is one combined release, not two independent annual samples.

The source projections are deliberately **not one appended set of tables**:

- Historical ten waves (2004 through 2021): `cses_data."final_HH_CSES"`,
  `"final_HL_CSES"`, `"final_ED_CSES"`, `"final_EC_CSES"`, `"final_HO_CSES"`,
  `"final_VL_CSES"` and `"final_SURVEY_DATE_CSES"` (each in `cses_data`).
  HH = household, HL = member roster, ED = education, EC = employment, HO = housing,
  VL = village-questionnaire/PSU record, SURVEY_DATE = household timing.
  Module records and non-null fields do not necessarily cover every household or wave.
- Additional five waves (1996, 1997, 1999, 2023, 2025):
  `cses_data.cses_additional_hh_v1`, `cses_additional_hl_v1`, `cses_additional_ed_v1`,
  `cses_additional_ec_v1`, `cses_additional_ho_v1`, `cses_additional_health_v1` and
  `cses_additional_survey_date_v1` (each in `cses_data`). No new VL records are fabricated;
  timing records cover only 1996, 2023 and 2025.
- Exact-name `public` compatibility views preserve the historical interfaces. They do not
  automatically include the five additional waves or inherit later qualification rules.
  Do not use `SELECT * ... UNION ALL SELECT * ...` across the two table families: their
  keys, columns and source meanings differ.

### First queries and joins

```sql
-- Count the full member spine; then inspect usable answers separately.
SELECT survey_wave, count(*) AS member_wave_records,
       count(attendance_qualified) AS usable_attendance_records
FROM cses_analysis.cses_education_unified_v1
GROUP BY survey_wave ORDER BY survey_wave;

-- Strict 30-day screening: NULL means unavailable/unqualified, never healthy No.
SELECT survey_wave, count(*) AS member_wave_records,
       count(illness_injury_30d_qualified) AS usable_30day_records,
       count(*) FILTER (WHERE illness_injury_30d_qualified = 1) AS yes_records,
       count(*) FILTER (WHERE illness_injury_30d_qualified = 0) AS no_records
FROM cses_analysis.cses_health_screen_unified_v1
GROUP BY survey_wave ORDER BY survey_wave;

-- Connect modules and geography using the entire member-wave key.
SELECT e.survey_wave, e.household_key, e.record_key, e.age_for_analysis,
       e.attendance_qualified, e.attendance_status,
       h.illness_injury_30d_qualified, h.strict_30d_status,
       g.admin1_code, g.admin2_code, g.admin3_code, g.admin4_code
FROM cses_analysis.cses_education_unified_v1 e
LEFT JOIN cses_analysis.cses_health_screen_unified_v1 h
  USING (survey_wave, household_key, record_key)
LEFT JOIN cses_analysis.cses_person_geography_v2 g
  USING (survey_wave, household_key, record_key)
WHERE e.survey_wave = '2023'
ORDER BY e.household_key, e.record_key
LIMIT 20;
```

The unified member key is **`(survey_wave, household_key, record_key)`**. Household joins
use **`(survey_wave, household_key)`** only where the household-side relation is unique at
that grain. Historical tables instead use `household_id` / `person_id`; consult the
[key contracts](docs/cses-database-architecture.md#grain-and-key-contracts) before joining
them. Do not join on ID alone, cast native-component keys or UUIDs to numbers, or assume
that a matching ID identifies the same person across years. Job-level rows can multiply
member records and need their own keys.

Read qualified values together with their statuses, route flags and coverage. For example,
2017 education/health qualification remains withheld, and strict health screening excludes
2019's unresolved code conflict. Missing answers, inapplicable questions and unresolved
codes are not interchangeable. Row counts describe member-wave or module records, not
unique directly interviewed people or a longitudinal panel. These examples are unweighted
sample diagnostics, not national estimates. Weighting and other study-specific adjustments
are deferred until a concrete research request; they are not an unfinished ingestion step.

For source and rule tracing, use `cses_meta` (catalog, sources and release/load history)
and `cses_alignment` (versioned mappings, rules and dictionaries). See the
[database topology](docs/cses-topology.md) and [questionnaire collection](data/processed/cses_questionnaires/README.md).
Do not rerun `publish`, `apply`, migration or restore commands to read data.

## Current status

The [published health screening interface](docs/cses-health-screen-interface.md), release 28
on 2026-10-18, retains all 571,699 member-wave records in a 43-column view, with 308,955 strict
30-day screening records across eight waves. Seven additive objects have 197 source-output
edges. The native-input bridge restores selected branch values absent from earlier stored
JSON without changing original answers or old interfaces. Different four-week concepts,
2017's unverified form, 2019's code conflict, 66 missing-health records and five source orphans
remain explicit. This does not harmonize treatment or illness types. The accepted
[pilot](docs/cses-health-all-waves-pilot.md) and [preflight](docs/cses-health-screen-preflight.md)
remain historical evidence, including the verified separate archive cache.

The [unified fifteen-wave education interface](docs/cses-education-unified-interface.md),
release 26 on 2026-10-18, preserves 571,699 member-wave records with eight qualified targets,
explicit statuses, a 120-row field-wave matrix and 360 coverage rows. It is additive:
historical interfaces remain unchanged. Strict 2017 values are withheld pending questionnaire
evidence, and four unmatched education records stay in a separate audit. Use this new
interface explicitly for its qualification contract; a shared schema is not blanket equivalence.

Five additional waves (1996, 1997, 1999, 2023 and 2025) are now
[published additively](docs/cses-additional-waves.md#additional-wave-database-release): seven
qualified module tables, 45,444 households and 212,779 roster records, with 173 source datasets,
5,427 native variables and 171 field-wave mappings cataloged. This is not blanket cross-wave
harmonization. The historical ten-wave tables and their counts below are unchanged. The geography
v2 interface covers all 15 waves and 571,699 member-wave records, without claiming verified village geometry.

A subsequent [read-only analysis pilot](docs/cses-additional-waves.md#read-only-alignment-pilot)
found that the original five-wave 2025 age projection selected a sparse field while the native
calculated age is complete. The additive [2025 age interface](docs/cses-2025-age-interface.md)
now selects that native age, and the unified education view consumes the published age/route
context. Do not use the original sparse projection for 2025 age-specific denominators.
The original pilot itself did not modify the database.

The preserved [ten-wave HEALTH release and variable brief](docs/cses-health-database-release.md)
remains the entry point for its historical illness-type/care contract: ten sources,
358,859 person-wave records, a 41-column
qualified analysis interface and graph v15. It adds three physical tables and two views without
changing the seven core tables. Two HEALTH concepts are reviewed, neither equivalent across all ten waves.

The [2021 illness dictionary v2](docs/cses-health-2021-dictionary-recovery.md) recovers three codes
from the Khmer form, with 3,097 additional version-qualified usable records and 1,053 still unresolved.

The [second HEALTH variable review](docs/cses-health-illness-type.md) adds a partial illness-type
crosswalk, preserving changing classification families and unresolved 2021 codes. The new named
release publishes these qualified results, not an all-ten-wave harmonization claim.

The [first HEALTH variable review](docs/cses-health-recent-illness.md) adds a local recent-illness/injury
crosswalk: four form-supported waves and 134,977 conservative usable person-wave records. Qualified
or unverified waves remain separate. This historical local review is now consumed by the named HEALTH release.

The new [HEALTH source-intake module](docs/cses-health-module.md) provides 68 native source datasets
under `data/processed/cses_health/v1/`, without changing the seven published core tables. The
[extracted questionnaire library](data/processed/cses_questionnaires/v1/README.md) provides per-wave
originals and searchable cells for routine review without reopening archives. Only the ten illness/care
sources are included in the new database release; the other HEALTH topics remain local.

The first [illness/care table design and preflight](docs/cses-health-illness-preflight.md) now retains
358,859 source records in a local table draft. Five people absent from HL and 66 roster records
without health rows are explicitly recorded. This historical read-only plan is preserved and is
now implemented by the separate authorized HEALTH publisher.

Start with the [variable brief](docs/cses-variable-brief.md) for current alignment scope and
record denominators, and the [280-field inventory](docs/cses-variable-inventory.md) for individual
definitions and non-null counts. The seven core tables contain 358,920 HL member-wave records and
77,904 HH household-wave records; these are not counts of actual people interviewed. The
[15-question-link publication plan](docs/cses-questionnaire-batch-plan.md) has passed read-only
preflight but has not changed the published catalog.

The [education alignment review](docs/cses-education-alignment.md) examines nine ED fields across ten
waves, including 48 question correspondences in seven English forms. Its reviewed 30-record
current-level code-21 correction is now available in the additive
[corrected ED interface](docs/cses-education-corrected-interface.md),
`cses_analysis.cses_ed_aligned_v1` (343,204 rows, 37 columns), and a matching versioned Parquet.
The 2014 draft qualification is retained; eight 2017 records remain unresolved. Original physical
tables, public compatibility views and the earlier age-only ED view still retain the old values.
No question links or historical metadata records were changed by this interface release.

The first [employment screening brief](docs/cses-employment-screening-alignment.md) reviews four of
39 employment fields, 28 question-wave correspondences and 40 field-wave profiles across 332,903 EC
records. The 2021 paid/unpaid-work distinction, changing search periods and routing restrictions
prevent treating equal option codes as fully comparable meanings.

The second [hours, workdays and status brief](docs/cses-employment-hours-status-alignment.md) adds seven
fields, 49 field/question correspondences (46 distinct printed items) and 70 field-wave profiles.
Together the two batches examine 11 of 39 employment fields, leaving 28 for subsequent batches;
reviewed fields are not certified as comparable across all ten waves. The new review identifies an
omitted 2009 secondary-days alias with 13,830 recoverable values, 256 retained 2004 status cells
labelled missing, and six 2004 total-hours records labelled 96+.

Those three issues are now handled in the [corrected EC interface](docs/cses-employment-corrected-interface.md),
`cses_analysis.cses_ec_aligned_v1` (332,903 rows, 74 columns). A versioned auxiliary table supplies
13,830 same-wave secondary-day values; separate interpreted status fields qualify the 185 main-job
and 71 secondary-job missing codes, and six total-hours records receive 96+ lower-bound/exact-value
qualifications. Original status codes and hours, all 35 pre-existing physical relations and historical
interfaces remain unchanged. The auxiliary table is a 36th physical relation, not an eighth core
table or an addition to the historical 22-entry storage registry. Four versioned rule rows and the
execution/graph evidence retain its provenance. See the
[EC publication record](docs/releases/cses-employment-recovery-qualified-v1.md).

The 2,412 retained hours-reconciliation inconsistencies and unverified hourly 98/99 exclusions are
not changed. Earlier general, ED, screening and hours/status briefs remain preserved snapshots;
use the corrected interface supplement for current values and denominators.

The third [occupation, industry and employer-type brief](docs/cses-employment-classification-alignment.md)
adds six fields, bringing review coverage to 17 of 39 employment fields (22 remaining). It records
42 question correspondences, 60 field-wave profiles, 774 retained labelled-missing/not-stated cells,
12 unlabelled observed code cells and an omitted 2007 long-format source with 11,949 job rows for
10,174 people. All selected values match the original EC table and current corrected view in read-only
checks. That review remains a preserved pre-publication snapshot.

The subsequent [classification correction](docs/cses-classification-corrected-interface.md) publishes
`cses_analysis.cses_ec_classification_v1` (332,903 rows, 86 columns), with 774 explicit missing-code
interpretations in new fields and all 74 prior columns preserved. The omitted 2007 source is recovered
in `cses_ec_jobs_2007_source_v1` and its diagnostic view `cses_ec_jobs_2007_v1`: all 11,949 job-index
rows remain, including 65 index/count conflicts and 21 index-2-only rows. The 2007 main/secondary
wide fields are deliberately not filled without verified job-index meanings. No all-wave classification
crosswalk is published. The additional source table is the 37th physical CSES relation, preserving
the prior 36 and historical metadata. See the
[release evidence](docs/releases/cses-employment-classification-qualified-v1.md) and graph v14.

The next [one-variable review: main job works the whole year](docs/cses-main-job-whole-year.md)
raises EC review coverage to 18 of 39 fields (21 remaining). The already stored binary field has
124,104 non-null member-wave responses across seven waves: 85,793 Yes and 38,311 No. Five forms
support the question/options, with the 2014 draft and 2021 screening/gate wording qualifications
retained. No new database values, question links or graph version are published by this review.

The [seasonality review and local alignment](docs/cses-main-job-seasonal.md) raises coverage to
19 of 39 EC fields (20 remaining). `main_job_was_usual_past_7_days` is a misleading legacy name
for question 10c about seasonal work; its stored Yes/No polarity is correct. A local 89-column
projection and equivalent read-only SQL preserve all 86 current interface columns and add an
evidence-qualified seasonal alias plus evidence/route flags. The alias covers 29,061 reported values
in five question-supported waves, while all 38,176 original values remain available in the legacy
field. The 2017 question is unverified and the 2019 Stata label is truncated before “seasonal”.
Route exceptions remain visible. The review also records 13 nonbinary raw codes previously
converted to NULL (12 in 2019 and one in 2021); these are not reinterpreted as Yes/No.
No persistent database alias or graph v15 is published.

The [main-job abroad review](docs/cses-main-job-abroad.md) raised detailed EC review coverage to
20 of 39 fields (19 remaining). The existing field describes the location of the main job, not the
ownership of its employer. It has 123,829 non-null values: 3,086 Yes and 120,743 No. Its independent
OR-screen gate does not require a seasonal response or whole-year No. The brief records six
outside-route responses in the five inspected-question waves and three nonbinary source codes
previously converted to NULL in 2019. No database values or published graph nodes are changed.

The [final 19-field review](docs/cses-employment-remaining-review.md) completes the **39/39 EC
business-variable review queue**, with [190 field-wave profiles](docs/cses-employment-remaining-field-waves.md).
This is review completion, not a claim that every field is fully harmonized or all corrections are
published. Findings include the secondary-seasonal naming error, 244 total-count and four search-method
values explicitly labelled missing, 398 empty search-method slots stored as zero, 14 count-suppressed
secondary answers, and qualified earlier-source recovery candidates. All 19 fields and their context
match the original table and current view in read-only checks. Original data, releases and graph v14
remain unchanged; the report separates evidence-backed correction proposals from unresolved recoveries.

The raw archive set matches the eleven CSES archives used by the earlier `MJ02b` database work. This
repository reproduces and validates the seven core local table artifacts. The original baseline
matched the earlier Parquet release value for value after normalizing the intentional raw-path change.
The current physical data adds one reviewed 2004 housing lighting missing-code correction to that
baseline. A subsequent metadata-only release publishes the approved housing value dictionary.

The v1 functional-schema migration is complete in `mda`: 22 physical CSES relations now reside in
`cses_data`, `cses_alignment`, or `cses_analysis`; seven normalized management tables reside in
`cses_meta`; and exact-name `public` compatibility views preserve the existing query interface. The
migration used a verified external backup and passed preflight, postflight, physical-identity, reader,
and local-baseline validation.

The baseline, storage-provenance, variable-catalog, and questionnaire-provenance releases are imported
and independently validated. All 22 registered storage relations have source provenance. The catalog
covers 10 survey waves, 11 archives, 171 physical datasets, 4,092 source variables, 280 canonical
variables, and 1,746 source-to-canonical mapping records (1,714 baseline rules, one correction,
21 original dictionary-release rules, three 2017 transfer rules, six recovered-evidence rules,
and one 2021 lighting resolution rule).
It also records 20 instruments, 171 questions, and 296 question links, including 51 provisional links
to the 2014 draft.

The catalog records 201 approved value mappings across 31 dictionary source rules, nine alignment
releases and nine load runs. Three recovered 2007 code tables, the nested 2013 questionnaire and both
2021 language questionnaires are registered. Historical gap reports remain preserved.
The age-qualification projection is preserved as graph v11: 4,843 nodes and 7,640 edges. Its five
views retain explicit 96+ interpretation for three 2004 members. The preserved graph v12 has 4,845
nodes and 7,644 edges, exported twice identically. It adds the corrected ED interface and its
evidence-rule view; see the
[ED publication record](docs/releases/cses-education-current-postgraduate-v1.md) for independently
verified counts and topology. The EC correction extends this projection to graph v13, with 4,848
nodes and 7,654 edges, exported twice identically; the
[EC publication record](docs/releases/cses-employment-recovery-qualified-v1.md) records the current
export and validation results. Existing physical data and earlier interfaces, including housing v4,
remain unchanged by these additive interface releases.

The preserved pre-correction housing value audit compares lighting, cooking fuel, and tenure across
all ten waves: 30 source profiles, 100 located questionnaire options, and 208 code rows. It identifies 10
field/code groups with different meanings across waves and a documented 2004 lighting missing code
retained in the baseline source-code field. The approved `cses-housing-lighting-missing-v1` release
has now changed that one cell from 9 to NULL in both the local housing artifact and `mda`, preserving
all other values, keys, and types across 77,922 rows and 50 columns. One release, one revised variable
mapping, and one load run retain its provenance without replacing the original mapping. Independent
read-only validation passed. The historical audit alone is not approval of canonical value mappings;
the later approval and metadata publication are recorded separately below.

A preserved correction-aware local value-mapping review partitions all 208 code rows into 70 candidate label
interpretations, 70 manual-review rows, 52 unresolved rows, and 16 missing-evidence rows. Raw-source and
then-current database checks passed; every row in that historical file remains proposed and
non-publishable. The review itself made no database changes and is archived with Git/DVC.

All 140 substantive entries (70 manually qualified rows and 70 candidates) have since received semantic
approval, with their original evidence limitations retained. The approved
`cses-housing-value-mapping-v1` release is now published: 140 value mappings representing 24 field-specific
categories across seven waves, 21 versioned source rules, one release and one load run. Publication
changes metadata only; source codes and all existing records remain unchanged. The 52 blocked and
16 missing-only rows remain excluded. Draft, compound/residual, and skip qualifications are retained;
this dictionary is not a claim that all categories or analytical denominators are comparable.

The preserved v1 housing interface exposes `cses_analysis.cses_housing_value_dictionary_v1` (140 entries) and
`cses_analysis.cses_housing_categories_v1` (77,922 rows, 66 columns). These additive views preserve all
50 original housing columns and expose release-selected categories, match states and evidence for
tenure, cooking fuel and lighting. All ten waves and 19 unmatched HH records remain visible. No
physical table or existing metadata record was rewritten by that interface-only release.

The preserved v2 interface adds the explicitly user-approved 2016-to-2017 dictionary transfer:
`cses_analysis.cses_housing_value_dictionary_v2` has 161 entries and
`cses_analysis.cses_housing_categories_v2` retains 77,922 rows and 66 columns. All 11,519 non-null
2017 tenure/cooking/lighting values match; the one tenure NULL remains NULL. The decision basis is
retained as `user_approved_cross_wave_transfer`, not verified 2017 questionnaire evidence. Publication,
independent validation and reproducible graph v8 export were completed at that stage. Archival for
the subsequent housing work is tracked in the current v4 release note.

The preserved v3 interface adds the recovered 2007/2013 primary evidence: 39 definitions, four
instruments, three 2013 housing questions and three reviewed source-question links.
`cses_analysis.cses_housing_value_dictionary_v3` has 200 entries;
`cses_analysis.cses_housing_categories_v3` retains 77,922 rows and 66 columns. All 22,289 non-null
values in the two recovered waves match, with ten original NULLs preserved. The physical data and
v1/v2 interfaces are unchanged. The 2013 workbook is registered in full, but its other sections are
not newly cataloged here. At the v3 stage, six 2021 lighting observations and the separate raw
tenure-code-0 question remained unresolved; no whole-database semantic completion was claimed.
Publication and independent read-only validation passed, as did all 113 tests at that stage.

The current v4 interface adds 2021 lighting code 8 as biogas for six observations, preserving the
English/Khmer questionnaire conflict and the raw tenure-code-0 anomaly. The dictionary has 201 entries;
all non-null values of the three reviewed housing fields now match. Physical data, all earlier views
and evidence qualifications remain unchanged. Independent validation and 125 tests passed.
The read-only orphan audit traces all 19 unmatched housing keys to missing original roster coverage:
16 have entirely empty housing questions; three have substantive answers. No records were deleted
or imputed. Whole-database semantic completion is not claimed.

## Start here

- [Corrected EC interface, population counts and query examples](docs/cses-employment-corrected-interface.md)
- [EC recovery/qualification publication and graph v13](docs/releases/cses-employment-recovery-qualified-v1.md)
- [Corrected education interface and query examples](docs/cses-education-corrected-interface.md)
- [Education correction publication and graph v12](docs/releases/cses-education-current-postgraduate-v1.md)
- [Employment screening brief: first four fields and comparability limits](docs/cses-employment-screening-alignment.md)
- [Employment field-wave counts, option counts and source locators](docs/cses-employment-screening-field-waves.md)
- [Employment hours, workdays and status: second batch and correction candidates](docs/cses-employment-hours-status-alignment.md)
- [Hours/status field-wave counts and source locators](docs/cses-employment-hours-status-field-waves.md)
- [Occupation, industry and employer type: third batch variable brief](docs/cses-employment-classification-alignment.md)
- [Classification field-wave counts, dictionaries and 2007 recovery candidates](docs/cses-employment-classification-field-waves.md)
- [Current classification interpretations and recovered 2007 job-index source](docs/cses-classification-corrected-interface.md)
- [Classification/source-job publication evidence and graph v14](docs/releases/cses-employment-classification-qualified-v1.md)
- [Questionnaires by wave and current question-alignment workbench](docs/cses-questionnaire-organization.md)
- [Resolved question ambiguities, HH/HL foundations and age-top-code qualification](docs/cses-questionnaire-review.md)
- [Published 2004 age-96+ analysis interface](docs/cses-age-topcode.md)
- [Age interface publication and graph v11](docs/releases/cses-age-2004-topcode-v1.md)
- [Core table readiness inventory and prioritized work queue](docs/cses-readiness-inventory.md)
- [Current housing v4 interface and 2021 resolution](docs/cses-housing-2021-resolution.md)
- [2021 publication and graph v10](docs/releases/cses-housing-2021-resolution-v1.md)
- [Housing orphan diagnosis](docs/cses-housing-orphan-diagnosis.md)
- [Preserved housing v3 and recovered 2007/2013 evidence](docs/cses-housing-recovered-evidence.md)
- [Recovered-evidence publication and graph v9](docs/releases/cses-housing-recovered-evidence-v1.md)
- [Preserved housing v2 interface and 2017 alignment](docs/cses-housing-2017-alignment.md)
- [2017 transfer publication and graph v8](docs/releases/cses-housing-2017-from-2016-v1.md)
- [Preserved housing v1 interface](docs/cses-housing-interface-runbook.md)
- [Housing interface publication and graph v7](docs/releases/cses-housing-interface-v1.md)
- [Database architecture and schema decision](docs/cses-database-architecture.md)
- [Processing and publication workflow](docs/cses-processing-workflow.md)
- [Database and lineage topology](docs/cses-topology.md)
- [Functional-schema migration runbook](docs/cses-schema-migration-runbook.md)
- [Baseline metadata import runbook](docs/cses-baseline-metadata-runbook.md)
- [Lineage export runbook](docs/cses-lineage-export-runbook.md)
- [Housing value audit runbook](docs/cses-value-audit-runbook.md)
- [Housing value mapping review runbook](docs/cses-value-mapping-review-runbook.md)
- [Value mapping publication history](docs/cses-value-mapping-publication-runbook.md)
- [Published value dictionary and graph v6](docs/releases/cses-value-mapping-import-v1.md)
- [Current housing value review](data/processing/cses/value_mapping_review_v1/review.md) (local DVC-owned artifact)
- [Value mapping review preflight v0.9](docs/releases/cses-value-mapping-review-preflight-v0.9.md)
- [Approved housing manual-review decisions v1](docs/releases/cses-value-mapping-manual-decisions-v1.md)
- [Approved 140-entry scope and publication preflight](docs/releases/cses-value-mapping-preflight-v0.10.md)
- [Lighting correction runbook](docs/cses-lighting-correction-runbook.md)
- [Lighting correction release v1](docs/releases/cses-lighting-correction-v1.md)
- [Housing code comparison](data/processing/cses/value_audit_v1/code_review.md) (DVC artifact)
- [Housing code conflicts](data/processing/cses/value_audit_v1/conflicts.md) (DVC artifact)
- [Questionnaire provenance import v1](docs/releases/cses-questionnaire-provenance-import-v1.md)
- [Housing value audit preflight v0.7](docs/releases/cses-value-audit-preflight-v0.7.md)
- [Baseline reproduction record](docs/releases/cses-baseline-reproduction-v0.1.md)
- [Functional-schema preflight record](docs/releases/cses-schema-preflight-v0.2.md)
- [Functional-schema migration v1](docs/releases/cses-functional-schema-migration-v1.md)
- [Baseline metadata preflight v0.3](docs/releases/cses-baseline-metadata-preflight-v0.3.md)
- [Baseline metadata import v1](docs/releases/cses-baseline-metadata-import-v1.md)
- [Lineage graph v1](docs/releases/cses-lineage-graph-v1.md)

## Repository ownership

- `docs/`: architecture, decisions, runbooks, and release notes; tracked by Git.
- `rsc/`: reusable source code, SQL, mapping specifications, and tests; tracked by Git.
- `data/`: raw archives, processing artifacts, release evidence, and graph snapshots; tracked by DVC.
- `etc/`: project settings and non-secret runtime configuration; tracked by DVC.

Do not store credentials, passwords, tokens, or private keys in this repository or in DVC.
