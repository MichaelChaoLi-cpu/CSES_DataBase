# CSES Storage Provenance Release Runbook

[Documentation index](README.md) · [Architecture](cses-database-architecture.md) ·
[Processing workflow](cses-processing-workflow.md) · [Topology](cses-topology.md)

## Purpose and boundary

Close the 15 storage-level lineage gaps left visible by the baseline metadata release, using reviewed
repository evidence and the existing `cses_meta` registry. This release adds no schema and does not
modify any analytical table. It proposes one approved alignment release, 134 dataset-output edges, and
one load-run record.

The 134 edges are derived as follows:

- the 62 reviewed raw-dataset edges for the seven `final_*_CSES` relations are inherited by the matching
  `ind_que_*_CSES` source dictionaries with contribution role `source`;
- the same 62 edges are inherited by the matching `align_summary_*_CSES` relations with contribution
  role `validation`;
- the ten reviewed `final_HH_CSES` dataset edges are inherited by `dim_geo_CSES` with contribution role
  `source`, matching the fingerprinted legacy geography publisher.

The geography publisher also reads `public.dim_admin2_cambodia` and `public.dim_admin3_cambodia`. They
are external reference relations, not CSES archive members, so this release documents them without
inventing `cses_dataset` records for them. Variable-level instrument, question, source-variable,
canonical-variable, and mapping records remain a later release.

## Owned artifacts

| Artifact | Owner | Purpose |
|---|---|---|
| `rsc/specs/cses_storage_provenance_v1.json` | Git | Evidence fingerprints, propagation rules, release identity, and approval phrase |
| `rsc/cses_db/cses_storage_provenance.py` | Git | Deterministic desired state, conflict detection, and transactional reconciliation |
| `rsc/cses_db/plan_cses_storage_provenance.py` | Git | Forced read-only preflight |
| `rsc/cses_db/import_cses_storage_provenance.py` | Git | Exact-plan, exact-phrase, all-or-nothing importer |
| `rsc/cses_db/validate_cses_storage_provenance.py` | Git | Independent forced read-only post-import validation |
| `data/processing/cses/storage_provenance_plan_v1.json` | DVC | Proposed rows, evidence hashes, checks, and database observations |
| `data/processing/cses/storage_provenance_import_v1.json` | DVC | Committed import evidence, created only after approval |
| `data/processing/cses/storage_provenance_validation_v1.json` | DVC | Post-import reconciliation evidence |

## Generate and review the plan

```bash
uv run python rsc/cses_db/plan_cses_storage_provenance.py --root . --dbname mda
```

The planner sets its PostgreSQL transaction to read-only before inspection. It verifies the exact
baseline plan, local release manifest, lineage snapshot, module builders, 21 generated artifacts, and
legacy geography publisher. It then verifies all referenced datasets and target relations in `mda`,
checks physical row counts, confirms the 62 source final-table edges, and rejects unreviewed existing
edges or same-key differences.

A reviewable initial plan must report:

- `database_mutated: false` and `preflight_ready: true`;
- 136 proposed records: one release, 134 dataset-output edges, and one load run;
- 15 target relations and exactly two documented external geography dependencies;
- zero conflicts and no false check values;
- an identical SHA-256 across two runs against unchanged Git, DVC, and database state.

## Database-write gate

Planning does not authorize a database write. Before importing:

1. commit and push the Git-owned specification, implementation, tests, and this runbook;
2. generate the read-only plan from that committed implementation;
3. DVC-version and push the plan, then commit and push the resulting `data.dvc` pointer;
4. verify the current `mda` recovery backup and record its checksum;
5. obtain the exact human confirmation `ACCEPT-CSES-STORAGE-PROVENANCE-V1`.

Only then run:

```bash
uv run python rsc/cses_db/import_cses_storage_provenance.py \
  --root . \
  --dbname mda \
  --apply \
  --confirm ACCEPT-CSES-STORAGE-PROVENANCE-V1
```

The importer refuses to connect without both write flags. It consumes the exact DVC-owned plan,
revalidates all local evidence, verifies that the implementation paths have not changed since the
plan's Git revision, acquires a transaction-scoped advisory lock, rejects conflicts, inserts only the
reviewed rows, reconciles all 136 records to no-ops, and commits once. Any failure rolls back the entire
transaction.

## Post-import validation and topology refresh

```bash
uv run python rsc/cses_db/validate_cses_storage_provenance.py --root . --dbname mda
uv run python rsc/cses_db/export_cses_lineage_graph.py --root . --dbname mda
```

The validator must observe 136 no-ops, zero inserts, zero conflicts, and all database checks true. The
lineage graph is then regenerated as a read-only database projection. The expected storage coverage is
22 of 22 relations, while the documented external geography dependencies remain outside the CSES
dataset registry.
