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
The current release adds one reviewed 2004 housing lighting missing-code correction to that baseline.

The v1 functional-schema migration is complete in `mda`: 22 physical CSES relations now reside in
`cses_data`, `cses_alignment`, or `cses_analysis`; seven normalized management tables reside in
`cses_meta`; and exact-name `public` compatibility views preserve the existing query interface. The
migration used a verified external backup and passed preflight, postflight, physical-identity, reader,
and local-baseline validation.

The baseline, storage-provenance, variable-catalog, and questionnaire-provenance releases are imported
and independently validated. All 22 registered storage relations have source provenance. The catalog
covers 10 survey waves, 11 archives, 171 physical datasets, 4,092 source variables, 280 canonical
variables, and 1,715 source-to-canonical mapping records (1,714 baseline rules plus one correction).
It also records 14 instruments, 164 questions, and 291 question links, including 51 provisional links
to the 2014 draft.

The current deterministic database lineage projection is graph v5: 4,802 nodes and 7,495 edges.
Canonical value mappings remain empty. Seven questionnaire gaps and all question-text confidence
boundaries remain explicit.

The preserved pre-correction housing value audit compares lighting, cooking fuel, and tenure across
all ten waves: 30 source profiles, 100 located questionnaire options, and 208 code rows. It identifies 10
field/code groups with different meanings across waves and a documented 2004 lighting missing code
retained in the baseline source-code field. The approved `cses-housing-lighting-missing-v1` release
has now changed that one cell from 9 to NULL in both the local housing artifact and `mda`, preserving
all other values, keys, and types across 77,922 rows and 50 columns. One release, one revised variable
mapping, and one load run retain its provenance without replacing the original mapping. Independent
read-only validation passed. Cross-wave categories and unresolved codes still require semantic review;
the historical audit is not an approval of canonical value mappings.

A correction-aware local value-mapping review now partitions all 208 code rows into 70 candidate label
interpretations, 70 manual-review rows, 52 unresolved rows, and 16 missing-evidence rows. Raw-source and
current database checks passed; every row remains proposed and non-publishable. The review does not
change `mda` or graph v5 and currently awaits Git/DVC version synchronization.

All 140 substantive entries (70 manually qualified rows and 70 candidates) have since received semantic
approval, with their original evidence limitations retained. Detailed source verification and a
read-only publication preflight passed for 21 versioned source rules and 140 value mappings. The
52 blocked and 16 missing-only rows remain excluded. No value mapping has yet been imported.

## Start here

- [Database architecture and schema decision](docs/cses-database-architecture.md)
- [Processing and publication workflow](docs/cses-processing-workflow.md)
- [Database and lineage topology](docs/cses-topology.md)
- [Functional-schema migration runbook](docs/cses-schema-migration-runbook.md)
- [Baseline metadata import runbook](docs/cses-baseline-metadata-runbook.md)
- [Lineage export runbook](docs/cses-lineage-export-runbook.md)
- [Housing value audit runbook](docs/cses-value-audit-runbook.md)
- [Housing value mapping review runbook](docs/cses-value-mapping-review-runbook.md)
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
