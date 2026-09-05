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
The current lineage projection is graph v10: 4,838 nodes and 7,627 edges, exported twice identically.

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
