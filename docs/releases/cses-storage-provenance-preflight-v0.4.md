# CSES Storage Provenance Preflight v0.4

- Date: 2026-09-05
- Database: `mda`
- Database mutation: none

## Outcome

The `cses-storage-provenance-v1` release is ready for explicit review. Two consecutive forced read-only
preflights produced the same plan SHA-256:

`5c5e594a30a2b5a9279500a56f23037828d86eba58497919a5cc29a975dd48da`

The reviewed implementation revision is
`b330f5dbda300fefe1f3ca77dcde2ff36429623c`. The DVC data snapshot containing the plan is
`md5:7a0c75884e61eb4f45bae779474faf3f.dir` and is synchronized with the `storage` remote.

## Proposed transaction

| Record group | Inserts | No-ops | Conflicts |
|---|---:|---:|---:|
| Alignment releases | 1 | 0 | 0 |
| Dataset-output edges | 134 | 0 | 0 |
| Load runs | 1 | 0 | 0 |
| **Total** | **136** | **0** | **0** |

The 134 edges cover all 15 relations missing dataset-level provenance in lineage graph v1: seven
source dictionaries, seven alignment summaries, and `dim_geo_CSES`. The preflight also confirmed that
the 62 source final-table edges match the accepted baseline exactly, every referenced dataset and target
relation is registered, physical row counts match the registry, and all checks are true.

No variable-level metadata is proposed. `public.dim_admin2_cambodia` and
`public.dim_admin3_cambodia` remain explicit external geography dependencies rather than fabricated
CSES datasets.

## Recovery and approval boundary

The existing pre-change recovery artifact is:

- path: `/Volumes/MikesDataBackup/PG_DB/mda_pre_CSES_schema_v1_20260904-210748_e12vbrzs.dump`;
- SHA-256: `6f192c8e479fbd5a0ee6b2504030d2ba37c3456cb0703b27124ff96840eea641`;
- size: 1,376,932,121 bytes;
- PostgreSQL archive entries: 22,176;
- mode: `0600`.

The backup must be reverified immediately before applying the plan. No database write is authorized by
this preflight. The required exact confirmation is:

`ACCEPT-CSES-STORAGE-PROVENANCE-V1`
