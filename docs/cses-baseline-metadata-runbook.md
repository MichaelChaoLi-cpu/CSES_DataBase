# CSES Baseline Metadata Import Runbook

[Documentation index](README.md) · [Architecture](cses-database-architecture.md) ·
[Processing workflow](cses-processing-workflow.md) · [Topology](cses-topology.md)

## Purpose

Adopt the already validated CSES functional-schema state into the seven `cses_meta` registry tables
without claiming to reconstruct load history that predates this repository. The Git-owned specification
defines the reviewed scope; DVC-owned evidence supplies archive fingerprints, physical table observations,
and the generated import plan.

The plan and import deliberately leave two visible lineage gaps:

- `dim_geo_CSES` is registered as a physical storage object without an invented archive edge.
- The seven inherited source dictionaries and seven alignment summaries are registered as storage
  objects, but their dataset edges wait for reviewed variable-level metadata.

## Owned artifacts

| Artifact | Owner | Purpose |
|---|---|---|
| `rsc/specs/cses_baseline_metadata_v1.json` | Git | Ten waves, eleven archives, storage scope, direct sources, dependencies, and approval gate |
| `rsc/cses_db/cses_baseline_metadata.py` | Git | Validation, desired-state construction, conflict detection, and transactional reconciliation |
| `rsc/cses_db/plan_cses_baseline_metadata.py` | Git | Forced read-only database preflight |
| `rsc/cses_db/import_cses_baseline_metadata.py` | Git | Explicitly gated all-or-nothing importer |
| `data/processing/cses/baseline_metadata_plan_v1.json` | DVC | Deterministic desired rows, database observations, checks, and proposed operations |

## Generate the read-only plan

```bash
uv run python rsc/cses_db/plan_cses_baseline_metadata.py --root . --dbname mda
```

The planner opens a transaction and immediately applies `SET TRANSACTION READ ONLY`. It verifies the
eleven archive files against their declared size and SHA-256, checks the 22 physical relations against
post-migration evidence, inspects all seven metadata tables, and classifies every proposed row as
`insert`, `noop`, or `conflict`.

A reviewable plan must have all of the following:

- `database_mutated: false`;
- `preflight_ready: true`;
- no false values in `checks`;
- zero `conflict` operations;
- the expected record counts for the reviewed specification;
- an unchanged SHA-256 across two runs against unchanged Git, DVC, and database state.

The initial preflight on 2026-09-04 proposed 278 inserts: 10 surveys, 11 source archives, 171 physical
datasets, one alignment release, 22 storage relations, 62 direct source-to-output edges, and one
baseline-adoption load record. Every `cses_meta` table was empty.

## Database-write gate

Generating or reviewing the plan does not authorize an import. Before an approved execution:

1. commit the Git-owned importer, specification, tests, and operational documentation;
2. regenerate the plan so its Git revision identifies that committed implementation and its fixed
   source-DVC revision identifies the input snapshot without creating a self-referential output hash;
3. update and push the DVC-owned plan;
4. commit `data.dvc` together with the final plan checksum in the release record, then push Git;
5. obtain explicit human acceptance of the baseline alignment release and database write;
6. verify that a current restore-tested database backup remains available.

Only after those conditions are met may the guarded importer be run:

```bash
uv run python rsc/cses_db/import_cses_baseline_metadata.py \
  --root . \
  --dbname mda \
  --apply \
  --confirm ACCEPT-CSES-BASELINE-V1
```

The importer refuses to connect without both write flags. It takes a transaction-scoped advisory lock,
inserts only missing rows, treats byte-for-byte-equivalent desired records as no-ops, rejects same-key
differences as conflicts, verifies the reconciled state, and commits once. Any failure rolls back the
complete transaction.

## Post-import verification

Regenerate the read-only plan. All 278 reviewed records must be `noop`, with zero `insert` and zero
`conflict` operations. Then export the deterministic lineage graph from PostgreSQL; the graph remains a
read-only DVC projection rather than a second source of truth.
