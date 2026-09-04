# CSES Functional-Schema Migration v1

## Status

Completed on 2026-09-04 in `mda` after an external verified backup and a fresh read-only preflight.
The migration committed as one PostgreSQL transaction and all post-migration checks passed.

## Recovery checkpoint

- Backup: `/Volumes/MikesDataBackup/PG_DB/mda_pre_CSES_schema_v1_20260904-210748_e12vbrzs.dump`
- Format: PostgreSQL custom format
- Size: 1,376,932,121 bytes
- Mode: `0600`
- SHA-256: `6f192c8e479fbd5a0ee6b2504030d2ba37c3456cb0703b27124ff96840eea641`
- TOC entries: 22,176
- Verification: `pg_restore --list` and complete decompression to `/dev/null` passed
- Database size at backup start: 17,867,364,031 bytes

The dump was created with PostgreSQL 18.3 tools. It is a complete recovery checkpoint, not a substitute
for a periodic isolated restore test.

## Executed migration

The executed SQL SHA-256 was
`727a2e6739f9ecdda6b02245989902f3f00c27ce9de415ee62b8c3c8a4c64c8f`, matching the fresh preflight
record. In one transaction it:

1. created `cses_meta`, `cses_alignment`, `cses_data`, and `cses_analysis`;
2. created seven normalized management tables, six normalized alignment tables, and two audit views;
3. moved eight CSES data/geography tables, seven source dictionaries, and seven alignment summaries out
   of `public` while preserving their physical PostgreSQL OIDs;
4. created 22 exact-name `public` compatibility views;
5. granted functional-schema and compatibility-view read access to `mda_readonly`;
6. verified the unchanged identity of all 31 protected non-migrated `public` relations before commit.

## Post-migration state

| Schema | Base tables | Views | Responsibility |
|---|---:|---:|---|
| `cses_meta` | 7 | 0 | Survey, archive, dataset, release, storage, output, and load-run registry |
| `cses_alignment` | 13 | 0 | Six normalized evidence tables plus seven retained source dictionaries |
| `cses_data` | 8 | 0 | Seven final CSES tables and the geography bridge |
| `cses_analysis` | 7 | 2 | Seven retained alignment summaries and normalized audit views |
| `public` compatibility surface | 0 CSES physical tables | 22 | Exact-name read interfaces |

The normalized management and alignment tables are intentionally empty at this migration boundary. A
reviewed baseline import is required before they become authoritative evidence; the retained dictionaries
and summaries remain available in their functional schemas and through `public` compatibility views.

## Validation

- `post_migration_valid = true` for all 22 scoped objects.
- Physical OID, persistence, owner, size, row count, ordered columns, constraints, indexes, grants, and
  natural-key evidence were preserved across the move.
- All compatibility-view columns match their authoritative physical relations.
- All eight declared natural keys still have zero null-key rows and zero duplicate groups.
- All seven core CSES tables match the local Parquet baseline on relation presence, exact rows, and
  ordered columns.
- `mda_readonly` successfully queried both `public."final_HH_CSES"` and
  `cses_data."final_HH_CSES"`, receiving 77,904 rows from each.
- All 31 protected non-CSES `public` relations retained the same names, OIDs, and relation kinds.

Machine-readable evidence is under `data/processing/cses/` and is DVC-owned:

- `mda_backup_verification_v1.json`
- `migration_dry_run_v1.json`
- `migration_postflight_v1.json`
- `mda_post_migration_audit_v1.json`
- `migration_validation_v1.json`

## Remaining gates

- Import a reviewed baseline registry and alignment release without inventing unavailable history.
- Add append-only revision evidence before the first replacement publication.
- Export and validate the deterministic lineage graph.
- Update Git and DVC versions so code, data evidence, and this database event are cross-recorded.
