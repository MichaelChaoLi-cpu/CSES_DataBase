# CSES Storage Provenance Import v1

- Date: 2026-09-05
- Database: `mda`
- Release: `cses-storage-provenance-v1`
- Approval: exact phrase `ACCEPT-CSES-STORAGE-PROVENANCE-V1` received

## Outcome

The reviewed storage-provenance plan was applied in one transaction. The importer inserted exactly one
approved alignment release, 134 dataset-output edges, and one load-run record. Its in-transaction
reconciliation observed all 136 reviewed records as no-ops after insertion, with zero pending inserts
and zero conflicts.

The independent post-import validator used a forced read-only transaction and passed every check. It
again observed 136 no-ops, zero inserts, and zero conflicts. No physical analytical relation, schema,
or variable-level alignment record was changed.

## Versioned evidence

| Evidence | SHA-256 |
|---|---|
| Reviewed plan | `5c5e594a30a2b5a9279500a56f23037828d86eba58497919a5cc29a975dd48da` |
| Import evidence | `f45a93483e3d08831d8593c14eeb5d4546a4e853beaca61886ac1b71dd4d8e03` |
| Validation evidence | `ffb136894b27938e2f6b7efe00dfaf162553cbfa72641b455d9a34e7f314188c` |
| Post-import graph v2 | `8139b385a6465af7a2e75ee180928f1dd3fc45cb2d413d852317419223dad41d` |
| Post-import overview v2 | `a5b0c8c051637e8b42c6764fcbd44eb80f3898ad3779274a3974e357f0d89c9d` |

The final DVC data pointer is `md5:3f0d35f3aca7700c3132a1294162c180.dir` with 68 files and
451,980,258 bytes. The reviewed implementation revision is
`b330f5dbda300fefe1f3ca77dcde2ff36429623c`; the preflight pointer and review record were committed at
`1322c38`.

Graph v1 remains the immutable pre-import evidence referenced by the reviewed specification. Graph v2
is the post-import projection and was reproduced byte-for-byte in two consecutive exports.

## Resulting topology

- alignment releases: 2;
- registered dataset-output edges: 196;
- load runs: 2;
- registered storage relations with dataset edges: 22 of 22;
- storage relations without dataset edges: 0;
- variable mappings: 0.

The release registers CSES-side provenance for `dim_geo_CSES` but does not misclassify
`public.dim_admin2_cambodia` or `public.dim_admin3_cambodia` as CSES datasets. Those remain documented
external dependencies for a later cross-domain dependency model.

## Recovery evidence

Immediately before import, the recovery archive was reverified:

- path: `/Volumes/MikesDataBackup/PG_DB/mda_pre_CSES_schema_v1_20260904-210748_e12vbrzs.dump`;
- SHA-256: `6f192c8e479fbd5a0ee6b2504030d2ba37c3456cb0703b27124ff96840eea641`;
- size: 1,376,932,121 bytes;
- mode: `0600`;
- PostgreSQL TOC entries: 22,176.
