# CSES Variable Catalog Release Runbook

[Documentation index](README.md) · [Architecture](cses-database-architecture.md) · [Topology](cses-topology.md)

## Purpose and scope

`cses-variable-catalog-v1` fills the variable-level layer already defined in `cses_alignment`; it does
not create another schema. The release catalogs every physical column in the 171 registered Stata
datasets, registers the 280 accepted final-table columns as canonical variables, and records only
source-to-canonical mappings supported by the pinned CSES builders and dictionaries.

The release deliberately creates no instruments, questions, or canonical value mappings. No
authoritative questionnaire files are registered in the current repository evidence, and released
Stata value labels describe source codes rather than reviewed cross-wave recodes. Source value labels
are retained on `cses_source_variable` without being promoted to `cses_value_mapping`.

## Ownership

| Artifact | Owner |
|---|---|
| Release specification and planner/importer/validator | Git (`rsc/`) |
| Architecture, topology, and release record | Git (`docs/`) |
| Reviewed variable-catalog plan and later import/validation evidence | DVC (`data/processing/cses/`) |
| Applied registry rows | PostgreSQL (`mda.cses_meta` and `mda.cses_alignment`) |

## Mapping interpretation

- Every registered Stata member is read directly from its top-level or nested ZIP; raw archives are
  not unpacked or changed.
- Variable position, native Stata storage type, variable label, and Stata value-label set are recorded
  as source metadata.
- Standard mappings are resolved only within the source-module families actually read by each pinned
  builder. If two physical inputs in the same builder legitimately expose the same reviewed field,
  each dataset receives its own mapping row.
- Blank dictionary source fields remain canonical-only derivations. They are not converted into
  invented raw mappings.
- The three household exact-date sources use an explicit, reviewed field list pinned in the release
  specification.
- Canonical fields come from the exact 280 ordered columns in the validated physical seven-table
  contract. Their database types and grains follow the accepted database state.

## Read-only preflight

From the repository root:

```bash
DVC_SITE_CACHE_DIR=/private/tmp/dvc-site-cache \
UV_CACHE_DIR=/private/tmp/uv-cache \
uv run python rsc/cses_db/plan_cses_variable_catalog.py --root . --dbname mda
```

The planner forces a read-only PostgreSQL transaction. It verifies all pinned fingerprints, scans all
171 Stata headers, checks the seven physical target contracts, rejects unresolved source fields,
rejects existing conflicts or unreviewed variable-level state, and writes
`data/processing/cses/variable_catalog_plan_v1.json`.

Run the planner twice and compare SHA-256 values before review. A valid plan reports
`database_mutated=false`, `preflight_ready=true`, and zero conflicts.

## Write gate

Database mutation is forbidden until the reviewed plan is Git/DVC versioned and the operator supplies
the exact phrase:

```text
ACCEPT-CSES-VARIABLE-CATALOG-V1
```

Only then run:

```bash
DVC_SITE_CACHE_DIR=/private/tmp/dvc-site-cache \
UV_CACHE_DIR=/private/tmp/uv-cache \
uv run python rsc/cses_db/import_cses_variable_catalog.py \
  --root . --dbname mda --apply \
  --confirm ACCEPT-CSES-VARIABLE-CATALOG-V1
```

The importer binds the approved phrase to the exact DVC-reviewed desired state and the Git revision
that generated it. It takes a transaction-scoped advisory lock, inserts the release as one transaction,
and rolls back on any conflict or post-write mismatch. It never updates or deletes existing rows.

## Independent validation

After an approved import:

```bash
DVC_SITE_CACHE_DIR=/private/tmp/dvc-site-cache \
UV_CACHE_DIR=/private/tmp/uv-cache \
uv run python rsc/cses_db/validate_cses_variable_catalog.py --root . --dbname mda
```

The validator runs in a new forced read-only transaction. Every planned record must reconcile as a
no-op, no questionnaire or canonical value mapping may have appeared, and the import evidence must
reference the exact reviewed plan. Export the next lineage graph only after this validation succeeds.

## Next independent release

Questionnaire discovery and question-to-source-variable links are a separate release. It must retain
source files, hashes, exact/provisional text status, pages or sequence evidence, and explicit link
review. Canonical category harmonization is also separate and must not treat coincident source code
numbers as semantic equivalence.
