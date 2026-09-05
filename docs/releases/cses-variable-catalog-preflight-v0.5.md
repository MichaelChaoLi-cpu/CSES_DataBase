# CSES Variable Catalog Preflight v0.5

Date: 2026-09-05

## Outcome

The deterministic, forced read-only preflight for `cses-variable-catalog-v1` passed. The database was
not mutated. The existing `cses_alignment` schema is sufficient; no schema addition or alteration is
part of this release.

## Reviewed scope

| Record family | Planned count |
|---|---:|
| Alignment releases | 1 |
| Physical source variables | 4,092 |
| Canonical variables | 280 |
| Tested variable mappings | 1,714 |
| Load runs | 1 |
| Instruments | 0 |
| Questions | 0 |
| Canonical value mappings | 0 |

The 4,092 source variables cover all 171 registered Stata datasets. The 280 canonical variables match
the exact columns and PostgreSQL types of the seven accepted `cses_data.final_*_CSES` tables. All
nonblank standard dictionary fields resolved inside their builder-specific source-module scope. The
three exact-date sources use the explicit field lists in the reviewed release specification.

## Database preflight

- Database: `mda`
- Transaction: forced read-only
- Registered datasets: 171
- Physical canonical columns: 280
- Existing instruments/questions/value mappings: 0/0/0
- Existing source variables/canonicals/variable mappings for this scope: 0/0/0
- Planned actions: 6,088 inserts, 0 no-ops, 0 conflicts
- Database mutation: false
- Preflight ready: true

The plan was generated twice from Git commit
`1229f1b3d3a8f377245cfa22fa7f40e158f3c128`; both files were byte-identical.

## Evidence

| Evidence | Fingerprint |
|---|---|
| `data/processing/cses/variable_catalog_plan_v1.json` | SHA-256 `0d9563ff820073baa420b98e1c722b32cfdad77d2c27ce6df7fbdb307a4fa8c1`; 6,192,085 bytes |
| Source data state used by the plan | DVC `md5:3f0d35f3aca7700c3132a1294162c180.dir` |
| Data state after adding the reviewed plan | DVC `md5:bab42cc0671b7b0ea1673febd3f3c921.dir`; 69 files; 458,172,343 bytes |
| Unit and contract tests | 23 passed |
| Ruff | passed |
| DVC remote | `storage`; cache and remote in sync |

The DVC object stores the entire proposed desired state, including source metadata, canonical
definitions, exact source-field arrays, transformation descriptions, record keys, and the read-only
database reconciliation result.

## Deliberate exclusions

- No questionnaire or question records are inferred from Stata labels or recode dictionaries.
- No question links are created without authoritative instrument evidence.
- No Stata value label is promoted to a cross-wave canonical value mapping.
- No blank/derived dictionary field is converted into a fictional physical source variable.
- No source dataset, final table, compatibility view, or existing metadata row is updated or deleted.

## Write gate

Import remains blocked until the operator supplies this exact phrase after reviewing the versioned
plan:

```text
ACCEPT-CSES-VARIABLE-CATALOG-V1
```

The importer also requires `--apply`, verifies the plan SHA and generating Git revision, takes a
transaction-scoped advisory lock, and rolls back the complete transaction on any conflict or post-write
mismatch. See the [variable catalog runbook](../cses-variable-catalog-runbook.md).
