# CSES Functional-Schema Migration Runbook

[Documentation index](README.md) · [Architecture](cses-database-architecture.md) ·
[Processing workflow](cses-processing-workflow.md) · [Topology](cses-topology.md)

## Current state

Migration v1 completed on 2026-09-04 after explicit approval, a verified external backup, and a fresh
read-only preflight. All 22 physical relations, 22 `public` compatibility views, four functional schemas,
31 protected objects, and the `mda_readonly` interface passed post-migration validation. The execution
section remains the reproducible procedure for audit and disaster-recovery review; it does not authorize
future data replacement or constraint changes.

## Versioned inputs

| Artifact | Responsibility |
|---|---|
| `rsc/specs/cses_schema_v1.json` | Exact 22-object scope, target schemas, reader roles, and natural keys |
| `rsc/sql/cses_schema_v1.sql` | Four functional schemas and the constrained metadata/alignment model |
| `rsc/sql/cses_public_to_functional_v1.sql` | Generated all-or-nothing object migration and compatibility layer |
| `rsc/cses_db/render_cses_migration_sql.py` | Deterministic SQL renderer and stale-file check |
| `rsc/cses_db/plan_cses_schema_migration.py` | Forced read-only database preflight |
| `data/processing/cses/migration_dry_run_v1.json` | DVC-owned preflight evidence |

The generated migration SQL embeds the complete schema DDL so schema creation, metadata model creation,
relation moves, compatibility views, grants, and postconditions occur in one transaction.

## Exact migration scope

| Target schema | Existing physical relations | Count |
|---|---|---:|
| `cses_data` | Seven `final_*_CSES` tables and `dim_geo_CSES` | 8 |
| `cses_alignment` | Seven `ind_que_*_CSES` tables | 7 |
| `cses_analysis` | Seven `align_summary_*_CSES` tables | 7 |
| `cses_meta` | New registry tables defined by v1 DDL | 7 new tables |

Climate tables, generic Cambodia geography dimensions, MICS/NLSS relations, `_catalog`, `_guide`,
`_data_issues`, PostgreSQL monitoring views, and heat-labor research products are protected and are not
part of this migration.

## Read-only preflight

Regenerate and verify the SQL before every database check:

```bash
uv run python rsc/cses_db/render_cses_migration_sql.py --root .
uv run python rsc/cses_db/render_cses_migration_sql.py --root . --check
```

Run the database preflight:

```bash
uv run python rsc/cses_db/plan_cses_schema_migration.py --root . --dbname mda
```

The command sets `transaction_read_only = on`. It requires all 22 physical source relations to exist,
all target relations to be absent, a consistent owner, exactly the declared non-owner read grants, no
unplanned dependent PostgreSQL views, and unique non-null values for all eight declared natural keys. It
records all other `public` relations as the protected comparison set. `migration_ready` must be `true`.

The preflight cannot detect SQL text embedded in external applications. Existing research repositories
must therefore continue to use the exact-name `public` compatibility views until their queries are
intentionally updated.

## Backup gate

Immediately before migration, create a custom-format database backup on external storage. Use a unique
timestamped filename; never overwrite an earlier verified dump.

```bash
pg_dump -d mda --format=custom --compress=6 \
  --file=/Volumes/MikesDataBackup/PG_DB/mda-YYYYMMDD-HHMMSS.dump
chmod 600 /Volumes/MikesDataBackup/PG_DB/mda-YYYYMMDD-HHMMSS.dump
pg_restore --file=/dev/null /Volumes/MikesDataBackup/PG_DB/mda-YYYYMMDD-HHMMSS.dump
shasum -a 256 /Volumes/MikesDataBackup/PG_DB/mda-YYYYMMDD-HHMMSS.dump
```

Record the dump path, byte size, SHA-256, `pg_restore` result, and preflight SHA-256 outside the database
transaction. A TOC/decompression check is necessary but does not replace a periodic restore test into an
isolated database.

## Migration execution procedure

Migration v1 used the following command only after explicit database-write approval, a verified backup,
passing tests, and a fresh read-only preflight:

```bash
psql -X -v ON_ERROR_STOP=1 -d mda \
  -f rsc/sql/cses_public_to_functional_v1.sql
```

The script:

1. obtains a transaction-scoped advisory lock and a five-second lock timeout;
2. creates the four schemas and constrained v1 metadata/alignment model;
3. refuses missing, conflicting, or mixed public/functional layouts;
4. snapshots all 31 currently protected `public` relations;
5. moves the 22 physical tables with `ALTER TABLE ... SET SCHEMA`, preserving table OIDs and indexes;
6. creates exact-name `public` compatibility views and restores `mda_readonly` access;
7. verifies physical OID preservation, target kinds, compatibility-view kinds, and the protected snapshot;
8. commits only if every postcondition passes.

Any SQL error aborts the transaction. Do not manually repair a mixed layout; inspect the error and either
retry from the unchanged pre-migration state or restore the verified backup.

## Post-migration validation

The completed postflight reported `layout = functional` and `post_migration_valid = true`; all target
relations are base tables, all exact-name `public` objects are views, and row/key evidence is unchanged.
The production reader role successfully queried both interfaces, and the local-to-database baseline
audit passed against `cses_data`.

Do not promote unique indexes to primary keys or add cross-module foreign keys in this first structural
migration. The natural-key audit shows that primary-key promotion is technically possible, but retained
ED, HO, and EC link exceptions require a separate constraint design and approval.

## Baseline metadata import

The v1 migration creates empty management and normalized alignment tables. Importing the current
`ind_que_*` and `align_summary_*` evidence into that model is a later reviewed load. It must identify the
import as a baseline snapshot and must not invent unavailable historical revisions or questionnaire
provenance.
