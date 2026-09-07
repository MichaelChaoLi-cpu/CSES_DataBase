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

## Current status

The [HEALTH database release and variable brief](docs/cses-health-database-release.md) is the current
entry point for illness/care publication: ten sources, 358,859 person-wave records, a 41-column
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
