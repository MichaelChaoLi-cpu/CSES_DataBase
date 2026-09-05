# CSES Lineage Export Runbook

[Documentation index](README.md) · [Architecture](cses-database-architecture.md) · [Topology](cses-topology.md)

## Purpose and ownership

The exporter creates a deterministic read-only projection of the authoritative CSES registry,
alignment, storage, and compatibility state in PostgreSQL. It never writes to PostgreSQL.

- Git owns the exporter, tests, this runbook, and release notes.
- DVC owns versioned pairs under `data/lineage/`, including the pre-storage-provenance v1 snapshot,
  post-storage-provenance v2 snapshot, post-variable-catalog v3 snapshot,
  post-questionnaire-provenance v4 snapshot, post-lighting-correction v5 snapshot,
  and post-value-dictionary v6 snapshot.
- PostgreSQL remains the source of truth. The graph is a disposable read model and never writes back.

## Export

Run from the project root with local PostgreSQL authentication:

```bash
uv run python rsc/cses_db/export_cses_lineage_graph.py \
  --root . \
  --dbname mda \
  --output data/lineage/cses_lineage_graph_v6.json \
  --overview data/lineage/cses_lineage_overview_v6.mmd
```

This reproduces the v6 state only while the database projection is unchanged. Choose new output names
after any later accepted release; always provide both paths because the legacy CLI default names v1.

The exporter opens one forced read-only transaction and rejects the export unless:

- the database is `mda` and `transaction_read_only=on`;
- all four functional schemas and the `public` compatibility schema exist;
- every registered storage relation has a same-name `public` compatibility view; and
- PostgreSQL dependency metadata confirms that each view reads its registered physical relation.

## Determinism contract

Node identifiers use encoded natural keys rather than PostgreSQL surrogate IDs. Nodes are sorted by
identifier; edges are sorted by type, source, target, and canonical JSON properties. The graph excludes
export timestamps, connection users, and other runtime-only state. Both output files are replaced
atomically.

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

## Versioning

After a successful repeated export, update only `data/` with DVC, review the `data.dvc` pointer, push to
the configured `storage` remote, and commit the pointer with Git. Record the exporter Git revision,
graph and overview SHA-256 values, DVC pointer, and Git pointer in the English release note.
