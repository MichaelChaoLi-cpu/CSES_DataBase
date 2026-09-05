# CSES Database Build Infrastructure

This directory contains the reusable local build inherited from the validated `MJ02b` CSES work. The
source archives in this repository are byte-identical to the eleven archives used by that project.

## Boundary

- Input: immutable DVC-owned archives under `data/raw/`.
- Output: reproducible DVC-owned artifacts under `data/processing/cses/`.
- Code: Git-owned inventory, harmonization, builders, validators, and release comparison.
- PostgreSQL: schema migration v1 completed; routine audits and research access remain read-only.

The legacy `MJ02b` publishers are intentionally not copied. They write all object families and catalog
records into `public`, which conflicts with the functional-schema architecture. The v1 migration
contract, metadata model, deterministic SQL renderer, forced read-only preflight, external backup
verification, transactional migration, and postflight validation are implemented. New data publication
remains a separate reviewed operation; the approved baseline metadata import and its read-only
validation are complete.

Climate acquisition, general Cambodia boundary publication, heat-labor analytical tables, figures, and
research results remain outside this reusable core.

## Reproduce the local release

The command below reproduces the historical baseline when run with its matching Git/DVC revisions.
The current housing builder includes the approved one-cell lighting correction, so an exact comparison
against the unchanged `MJ02b` baseline is expected to find that difference. Do not overwrite the old
baseline manifest or comparison evidence with the new release. Use the correction workflow below
for current housing validation.

Historical command, from the project root:

```bash
uv run python rsc/cses_db/build_local_release.py \
  --root . \
  --reference-root ../../Research/MJ02b
```

This runs archive inventory, the dependency-ordered builders, all local validators, an optional
content comparison against the earlier release, and a machine-readable local release manifest. It does
not connect to PostgreSQL or update DVC.

After the local build passes, compare its structure with the current database in a forced read-only
transaction:

```bash
uv run python rsc/cses_db/audit_mda_baseline.py --root . --dbname mda --schema public
```

This checks relation presence, exact row counts, ordered columns, comments, and indexes. It does not
compare every cell and does not authorize migration.

## Plan the functional-schema migration

Render and verify the SQL from the Git-owned contract:

```bash
uv run python rsc/cses_db/render_cses_migration_sql.py --root .
uv run python rsc/cses_db/render_cses_migration_sql.py --root . --check
```

Run the forced read-only database preflight:

```bash
uv run python rsc/cses_db/plan_cses_schema_migration.py --root . --dbname mda
```

The preflight writes `data/processing/cses/migration_dry_run_v1.json` and exits unsuccessfully if the
source/target layout, roles, grants, dependencies, ownership, or declared natural keys violate the v1
contract. See the project migration runbook before any write operation.

## Plan the baseline metadata import

Run the forced read-only registry preflight:

```bash
uv run python rsc/cses_db/plan_cses_baseline_metadata.py --root . --dbname mda
```

This writes `data/processing/cses/baseline_metadata_plan_v1.json`. It verifies the Git-owned baseline
specification, DVC evidence, source archives, physical relations, metadata-table layout, and existing
records. The separate importer requires `--apply` and the exact approval phrase documented in the
[baseline metadata runbook](../../docs/cses-baseline-metadata-runbook.md); do not use it without a
reviewed plan and explicit database-write approval.

After an approved import, validate the exact reviewed plan in a separate forced read-only transaction:

```bash
uv run python rsc/cses_db/validate_cses_baseline_metadata.py --root . --dbname mda
```

## Plan the variable catalog

Catalog all registered Stata columns and build the conservative source-to-canonical proposal in a
forced read-only database transaction:

```bash
uv run python rsc/cses_db/plan_cses_variable_catalog.py --root . --dbname mda
```

The imported and independently validated v1 release covers 171 registered source datasets, 4,092
physical source variables, and the 280 columns in the seven accepted final tables. It does not
synthesize questionnaires or canonical value mappings. Any future import still requires `--apply`
plus the exact phrase documented in the
[variable catalog runbook](../../docs/cses-variable-catalog-runbook.md).

## Plan questionnaire provenance

Fingerprint the selected source-archive instruments and build deterministic question links in a
forced read-only transaction:

```bash
uv run python rsc/cses_db/plan_cses_questionnaire_provenance.py --root . --dbname mda
```

The imported and independently validated questionnaire-provenance v1 release uses the existing
alignment schema. It contains 14 instrument files, 164 question transcriptions, and 291 same-wave
source-variable links. The 2014 draft remains provisional, and image-only/OCR material is not promoted
to authoritative question text. Any later database write still requires `--apply` plus the exact
phrase documented in the
[questionnaire provenance runbook](../../docs/cses-questionnaire-provenance-runbook.md).

## Audit housing codes and missingness

The following is the historical pre-correction pilot command. Its pinned builder/table/catalog
fingerprints intentionally reject the newer correction release. Reproduce it only with the matching
Git/DVC revisions and database snapshot, keeping the accepted v1 reports immutable:

```bash
uv run python rsc/cses_db/plan_cses_value_audit.py --root . --dbname mda
```

The pilot checks archive and evidence hashes, profiles complete raw columns with Stata missing codes
preserved, reads 100 explicitly located questionnaire options, and verifies the current database's
code frequencies against the pinned local release. It writes a JSON preflight, code comparison,
conflict report, and Mermaid review overview under `data/processing/cses/value_audit_v1/`.
See the [value audit runbook](../../docs/cses-value-audit-runbook.md) for the separate questionnaire
cell-extraction command, confidence boundaries, and deterministic reproduction procedure. Candidate
categories remain proposed; this command has no database-write mode.

## Build the correction-aware value mapping review

```bash
uv run python rsc/cses_db/plan_cses_value_mapping_review.py --root .
```

This separate read-only planner uses the preserved audit and accepted lighting correction rather than
repinning historical evidence. It replays the ten raw housing datasets, checks the full corrected
local/database housing table, and verifies 35 protected CSES tables. The new local review partitions
208 code rows into candidate, manual-review, unresolved, and missing-only evidence buckets. Every row
remains proposed; there is no apply or SQL-generation mode. See the
[review runbook](../../docs/cses-value-mapping-review-runbook.md) for output files, exact bucket meanings,
immutable output/replay rules, and publication boundaries.

After an exact user decision on a review bucket, materialize it separately rather than rewriting the
source review:

```bash
uv run python rsc/cses_db/record_cses_value_mapping_decisions.py --root .
```

The current decision specification selects the 70 user-approved `manual_review` identities from the
pinned review hash. It retains provisional/skip/comparability qualifications and has no database
connection or publication path. See the
[decision record](../../docs/releases/cses-value-mapping-manual-decisions-v1.md).

Both substantive buckets are now approved (140 entries). To recheck their source evidence and build
the combined publication preflight without database writes:

```bash
uv run python rsc/cses_db/plan_cses_value_mapping_release.py --root .
```

This retains the original review and manual-decision bundles. It writes the combined approved scope
and proposed 21 versioned source rules plus 140 value mappings under
`data/processing/cses/value_mapping_release_v1/`. See the
[v0.10 preflight](../../docs/releases/cses-value-mapping-preflight-v0.10.md) for detailed checks,
interpretation boundaries, and remaining version/backup/execution preparation.

## Validate the current lighting correction

The approved `cses-housing-lighting-missing-v1` release excludes source code 9 only from the 2004
lighting field. Exactly one housing cell changed in the local artifact and `mda`; all other cells,
keys, and dtypes are preserved. One revised variable mapping, one release, and one load run were
appended without replacing the historical mapping or adding canonical value mappings.

```bash
uv run python rsc/cses_db/validate_cses_ho.py
uv run python rsc/cses_db/correct_cses_housing_lighting.py validate --root .
```

The second command uses a forced read-only database transaction and the immutable correction evidence.
See the [correction runbook](../../docs/cses-lighting-correction-runbook.md) and
[release record](../../docs/releases/cses-lighting-correction-v1.md) for source checks, scoped backup,
before/after comparisons, and version pins. Older catalog and release plans remain historical; their
fingerprint gates must not be weakened to accept the corrected state.

## Export the lineage graph

Export the authoritative database state through one forced read-only transaction:

```bash
uv run python rsc/cses_db/export_cses_lineage_graph.py --root . --dbname mda \
  --output data/lineage/cses_lineage_graph_v5.json \
  --overview data/lineage/cses_lineage_overview_v5.mmd
```

The deterministic JSON graph and aggregate Mermaid overview are DVC-owned under `data/lineage/`. See the
[lineage export runbook](../../docs/cses-lineage-export-runbook.md) for its validation, interpretation,
and versioning contract. Always specify a new version for a changed database state; the CLI's legacy
default points to v1 and must not overwrite accepted historical evidence.

## Build order

```text
HL -> ED -> HH -> HO
 |          |
 +-> EC     +-> VL
            +-> SURVEY_DATE
```

HH follows ED because household-head education is linked from the education release. VL requires both
HH and HL. Every output preserves its documented native grain and retained-link exceptions.
