# CSES Lineage Export Runbook

[Documentation index](README.md) · [Architecture](cses-database-architecture.md) · [Topology](cses-topology.md)

## Purpose and ownership

The exporter creates a deterministic read-only projection of the authoritative CSES registry,
alignment, storage, and compatibility state in PostgreSQL. It never writes to PostgreSQL.

- Git owns the exporter, tests, this runbook, and release notes.
- DVC owns versioned pairs under `data/lineage/`, including the pre-storage-provenance v1 snapshot,
  post-storage-provenance v2 snapshot, post-variable-catalog v3 snapshot,
  post-questionnaire-provenance v4 snapshot, post-lighting-correction v5 snapshot,
  post-value-dictionary v6, housing-interface v7, 2017-transfer v8, recovered-evidence v9, and 2021-resolution v10 extensions.
- PostgreSQL remains the source of truth. The graph is a disposable read model and never writes back.

## Export

Run from the project root with local PostgreSQL authentication:

```bash
uv run python rsc/cses_db/publish_cses_housing_2021.py export --root .
```

This reproduces v10 after independent v4 validation. It retains prior view topology and evidence
edges, adds actual v4 dependencies, and records both 2021 language sources and their coding conflict.
It preserves all earlier graph files. The legacy
`export_cses_lineage_graph.py` projects the earlier catalog model only; its default names v1 and
must not overwrite accepted history. See the [current interface runbook](cses-housing-2021-resolution.md).

The exporter opens one forced read-only transaction and rejects the export unless:

- the database is `mda` and `transaction_read_only=on`;
- all four functional schemas and the `public` compatibility schema exist;
- every registered storage relation has a same-name `public` compatibility view; and
- PostgreSQL dependency metadata confirms that each view reads its registered physical relation.

## Determinism contract

Node identifiers use encoded natural keys rather than PostgreSQL surrogate IDs. Nodes are sorted by
identifier; edges are sorted by type, source, target, and canonical JSON properties. The graph excludes
export timestamps, connection users, and other runtime-only state. The legacy exporter replaces its
two output files atomically; the v7 extension instead preserves existing identical files and rejects
differing contents. Its execution binding and code hash remain part of the deterministic projection.

Use a new output version whenever an accepted release changes the database projection; never overwrite
a snapshot fingerprinted by a reviewed plan or specification. Run the exporter twice without changing
PostgreSQL and compare SHA-256 values. Both graph and overview
must be byte-identical. A changed graph checksum therefore represents a changed database projection or
a reviewed exporter-contract change.

## Graph interpretation

The v1 projection includes:

- survey, source-archive, and physical-dataset provenance;
- alignment releases and load runs;
- registered physical storage relations and verified `public` compatibility views;
- dataset-to-storage materialization edges;
- instruments, questions, source variables, canonical variables, and mappings when those normalized
  records exist.

The summary explicitly lists storage relations without registered dataset-output edges. These are
visible lineage gaps, not invented mappings and not automatic database errors. Fill them only through a
reviewed metadata release.

The v6 snapshot contains 4,804 nodes, 7,522 edges, six releases, six load runs, and a summary count of
140 value mappings. Source-rule edges include their value-mapping counts, not individual category
nodes or value labels. Query the exact dictionary release in PostgreSQL or inspect its approved scope
for the full 140-entry detail. The aggregate Mermaid overview is intentionally a higher-level view.

The v7 extension has 4,813 nodes and 7,540 edges: two analysis-view nodes, seven newly represented
metadata-relation nodes, and 18 additional schema/dependency edges. The seven metadata relations
already existed; graph nodes are not new database tables. Its dependency detail is
`data/lineage/cses_housing_interface_topology_v1.json`; the full graph is `cses_lineage_graph_v7.json`.

## Versioning

The preserved v9 graph contains 4,828 nodes, 7,600 edges, eight releases/runs and 200 value mappings.
There are 18 instruments, 167 question nodes and 294 question-link edges. Four explicit recovered
instrument-to-release edges make the new evidence basis visible. Its dependency detail is
`data/lineage/cses_housing_interface_topology_v3.json`; the full graph is `cses_lineage_graph_v9.json`.

Current graph v10 has 4,838 nodes, 7,627 edges, nine releases/runs, 201 values, 20 instruments,
171 questions and 296 question links. Its outputs are `cses_lineage_graph_v10.json` and
`cses_housing_interface_topology_v4.json` under `data/lineage/`.

After a successful repeated export, update only `data/` with DVC, review the `data.dvc` pointer, push to
the configured `storage` remote, and commit the pointer with Git. Record the exporter Git revision,
graph and overview SHA-256 values, DVC pointer, and Git pointer in the English release note.
