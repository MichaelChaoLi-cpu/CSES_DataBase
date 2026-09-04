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
and baseline metadata import remain separate reviewed operations.

Climate acquisition, general Cambodia boundary publication, heat-labor analytical tables, figures, and
research results remain outside this reusable core.

## Reproduce the local release

From the project root:

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

## Build order

```text
HL -> ED -> HH -> HO
 |          |
 +-> EC     +-> VL
            +-> SURVEY_DATE
```

HH follows ED because household-head education is linked from the education release. VL requires both
HH and HL. Every output preserves its documented native grain and retained-link exceptions.
