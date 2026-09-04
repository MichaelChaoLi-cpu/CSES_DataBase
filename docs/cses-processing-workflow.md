# CSES Processing and Publication Workflow

[Documentation index](README.md) · [Architecture](cses-database-architecture.md) · [Topology](cses-topology.md)

## Objective

Provide one reproducible path from immutable survey archives to reviewed PostgreSQL relations. Every
published field must be traceable to a physical source variable, an explicit transformation, a reviewed
alignment release, and a successful load run.

## Ownership contract

| Layer | Location | Owner | Rule |
|---|---|---|---|
| Raw survey archives | `data/raw/` | DVC | Immutable; read archive members in memory |
| Processing and release evidence | `data/processing/`, `data/releases/` | DVC | Reproducible outputs, not hand-edited truth |
| Mapping specifications | `rsc/specs/` | Git | Reviewable, deterministic, and versioned |
| Loader, validators, SQL, tests | `rsc/` | Git | No research-project-specific analysis |
| Current approved state | PostgreSQL `mda` | Database | Transactional source of truth after publication |
| Lineage graph snapshots | `data/lineage/` | DVC | Deterministic read models; never write back |
| Architecture, operations, releases | `docs/` | Git | English project record |

No credential may be stored in Git or DVC. Database writers must use local authentication or an approved
secret store.

## Alignment lifecycle

Each source-to-canonical mapping advances through explicit states:

```text
discovered -> documented -> mapped -> tested -> approved -> loaded
```

- `discovered`: the archive member and physical source variable are inventoried.
- `documented`: source labels, instrument evidence, grain, and coding are recorded.
- `mapped`: a candidate canonical field and transformation are specified.
- `tested`: deterministic checks pass on every applicable wave.
- `approved`: the mapping is included in a named alignment release.
- `loaded`: one successful database run records the source and release fingerprints.

Questionnaire linkage and analytical mapping are independent review decisions. A source label or question
link does not by itself approve cross-wave comparability.

## Standard pipeline

### 1. Inventory and fingerprint

- Discover top-level and nested archive members without expanding or modifying `data/raw/`.
- Record archive size and SHA-256, member path, member size, module candidate, wave, and source grain.
- Reject ambiguous duplicate candidates until a reviewed selection rule exists.
- Treat file modification time as non-authoritative.

### 2. Catalog physical variables

- Read Stata metadata and source variables at their native grain.
- Preserve original names, labels, storage types, value labels, position, and observation counts.
- Record unreadable files and unsupported formats as visible inventory states.
- Do not create synthetic questionnaire questions from recode labels.

### 3. Review alignment specifications

- Keep survey-wave selection rules and source-to-canonical mappings in Git-owned manifests.
- State identifier normalization, missing/sentinel rules, category mappings, units, and transformations.
- Preserve source codes alongside harmonized values when cross-wave meaning is not fully established.
- Require explicit release approval before a mapping can publish data.

### 4. Build module-grain staging artifacts

The inherited core dependency order is:

```text
HL -> ED -> HH
HL -> EC
HH -> HO
HH + HL -> VL
HH -> SURVEY_DATE
```

Build each module independently where possible. Preserve legitimate unmatched source rows with explicit
link-status fields; never silently drop them to satisfy a join.

### 5. Run pre-publication validation

At minimum, validate:

- archive and member fingerprints;
- row counts and unique natural keys by wave;
- expected columns, types, nullability, and value ranges;
- one-to-one and many-to-one linkage contracts;
- retained orphan counts and conflict counts;
- dictionary coverage and transformation-rule coverage;
- deterministic rebuild equality for unchanged inputs and specifications.

No PostgreSQL write begins if a required check fails.

### 6. Publish transactionally

- Require an explicit write confirmation and an explicit replacement flag for existing targets.
- Open one database transaction for metadata, staging tables, final relations, comments, indexes,
  registry records, load history, and interface refresh.
- Copy into uniquely named staging tables and verify counts before target replacement.
- Replace only the named release scope.
- Roll back the complete transaction on any key, mapping, count, comment, index, or view failure.
- Record identical source and alignment fingerprints as an auditable skip rather than rewriting tables.

Research analysis, figure, and table scripts must use read-only transactions and must never publish or
replace the reusable CSES database.

### 7. Validate the published state

- Compare database rows, columns, types, keys, and comments with the approved staging manifest.
- Verify storage-registry and dataset-output counts.
- Confirm that every published relation belongs to the intended schema.
- Confirm that compatibility views expose the intended columns without creating duplicate storage.
- Check that no staging relation remains after commit.

### 8. Export lineage and release evidence

- Export a deterministic, read-only graph from PostgreSQL.
- Sort natural-key node and edge identifiers so unchanged state yields a byte-identical checksum.
- Store the graph snapshot and machine-readable validation summary under DVC.
- Record the alignment version, load run, database validation, graph checksum, Git revision, and DVC
  pointer in an English release note.

## Initial adoption plan

1. Copy reusable database infrastructure from `../../Research/MJ02b/src/database/` into `rsc/` with
   attribution in Git history; do not copy research analyses.
2. Change its input contract from `data/raw/CSE/` to this repository's `data/raw/`, or introduce one
   centrally configured archive root.
3. Preserve the existing cleaning decisions and exception counts in explicit specifications and tests.
4. Reproduce the current seven core table releases locally from the identical archive set.
5. Separate hard-coded `public._catalog` writes from the CSES authoritative metadata model.
6. Add schema creation and migration code with dry-run, idempotence, and rollback tests.
7. ~~Add a deterministic graph exporter only after the relational model is stable.~~ Completed after
   baseline metadata validation.

## Release checklist

- [x] Raw archive fingerprints match the approved inventory.
- [x] Baseline mapping specification and alignment release are reviewed.
- [x] Local module builds and validators pass.
- [x] Existing database targets and dependencies are inventoried.
- [x] A current external backup exists and has been restore-read verified.
- [x] Database dry-run passes with a protected inventory of unrelated relations.
- [x] Explicit structural-migration database-write approval is recorded.
- [x] Transactional schema migration and post-migration validation pass.
- [x] Baseline metadata import plan is deterministic, conflict-free, and forced read-only.
- [x] Baseline metadata release and transactional import are explicitly approved and validated.
- [x] Lineage graph export is deterministic and forced read-only.
- [x] Git, DVC, database, and release-note identities are cross-recorded.

## Operations boundary

This document defines the workflow but does not authorize a database mutation, DVC transfer, Git
commit, or Git push. Each operation follows its own explicit approval and verification process.
