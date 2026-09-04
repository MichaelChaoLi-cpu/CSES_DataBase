# CSES Baseline Metadata Import v1

Date: 2026-09-05

## Outcome

The reviewed `cses-baseline-metadata-v1` state was imported into `mda.cses_meta` in one PostgreSQL
transaction after explicit approval. The import changed only the seven normalized CSES management
tables; none of the 22 physical CSES data, alignment, or analysis relations was replaced or modified.

| Registry group | Inserted records | Read-only validation |
|---|---:|---:|
| Surveys | 10 | 10 existing |
| Source archives | 11 | 11 existing |
| Physical datasets | 171 | 171 existing |
| Alignment releases | 1 | 1 existing |
| Storage relations | 22 | 22 existing |
| Dataset-output edges | 62 | 62 existing |
| Load runs | 1 | 1 existing |
| **Total** | **278** | **278 no-ops** |

The importer reconciled the committed transaction to 278 no-ops with zero inserts and zero conflicts.
Two subsequent executions of the independent forced read-only validator produced the same byte-identical
report and again found 278 no-ops, zero inserts, and zero conflicts.

## Recovery gate

Immediately before the write, the external PostgreSQL recovery checkpoint was re-read and verified:

- Backup: `/Volumes/MikesDataBackup/PG_DB/mda_pre_CSES_schema_v1_20260904-210748_e12vbrzs.dump`
- Size: 1,376,932,121 bytes
- Mode: `0600`
- SHA-256: `6f192c8e479fbd5a0ee6b2504030d2ba37c3456cb0703b27124ff96840eea641`
- PostgreSQL custom-format TOC entries: 22,176
- Verification: full SHA-256 read and `pg_restore --list` both passed

## Cross-recorded identities

| Identity | Value |
|---|---|
| Reviewed plan SHA-256 | `5d3bad6f959c051eaff4c1b7ecfb73cbb59f387a1b296723ac1d8d8b93e5def2` |
| Reviewed importer code Git revision | `e0fec7e629c467229178fab35aa7f70e46b32cd4` |
| Baseline specification SHA-256 | `0ba5aebbef0ef7ef77ef51a374cc8255e651ee7d547bd7a58284e7ab413d1ea6` |
| Source DVC input revision | `md5:5527d5015fff181a75a2dd6184f4e3db.dir` |
| Reviewed-plan DVC pointer | `md5:5a9cf2b23f361cb1cab1e66b1209f2cf.dir` |
| Reviewed-plan Git pointer | `198e124c69b8393a8ac99b7d2729d9ef54e970fd` |
| Import evidence SHA-256 | `d4b5e439ebc3d7cf2e9183d207650183013851a3662f06b4651c35028f23adb5` |
| Validator code Git revision | `c66a2ed445e0d0ebb1afcab250bba62a5f0aca3d` |
| Validation evidence SHA-256 | `77a4632976a9b3c12fbbf8daa4fa0a8d826624ffaa118c3f2bff622992a8662b` |
| Final evidence DVC pointer | `md5:7d21f25ca3d608da46a3802255fa5e9d.dir` |
| Final evidence Git pointer | `2fe6e331fa38674eaf53e7b2bd10216af75830f4` |

The DVC remote `storage` was synchronized before the final evidence pointer was committed.

## Interpretation and remaining scope

This release adopts the validated current state; it does not invent historical runs or variable-level
mapping evidence that was not captured previously. The direct source edge for `dim_geo_CSES` and the
inherited dictionary and alignment-summary dataset edges remain explicit follow-up gaps.

The next milestone is a deterministic, read-only lineage-graph exporter over the authoritative
PostgreSQL metadata. Primary-key or foreign-key promotion and any replacement publication remain behind
separate review and approval gates.
