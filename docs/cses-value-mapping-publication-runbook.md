# CSES Value Mapping Publication

This describes the completed dictionary-only release. For current checks after the 2021 resolution,
use `publish_cses_housing_2021.py validate --root .`. Earlier validators remain
immutable historical release logic and reject the expanded catalog.
See the [current housing v4 runbook](cses-housing-2021-resolution.md).

The user authorized the complete archive, backup, publication, validation and lineage workflow for
`cses-housing-value-mapping-v1`. Its semantic decisions cover exactly 140 values under 21 versioned
source rules. The frozen [v0.10 preflight](releases/cses-value-mapping-preflight-v0.10.md) remains
immutable; publication adds its own execution and result evidence under
`data/releases/cses-housing-value-mapping-v1/`.

## Publication sequence

Archive the approved review/decision/preflight bundle and commit the publication implementation first.
Then run:

```bash
uv run python rsc/cses_db/publish_cses_value_mappings.py backup --root . \
  --backup-dir /Volumes/MikesDataBackup/PG_DB
uv run python rsc/cses_db/publish_cses_value_mappings.py prepare --root .
```

The newly named custom-format backup covers `cses_alignment_release`, `cses_variable_mapping`,
`cses_value_mapping`, and `cses_load_run`. It is an external scoped recovery artifact, not a full
database backup. Table-of-contents, full decompression and SHA-256 checks precede execution.

Preparation replays the accepted source evidence, checks the fresh database plan, and records all
35 protected CSES tables. Four affected metadata-table fingerprints exclude only the new release's
records; all prior records, including the lighting correction, remain protected. Physical housing
content, row count, columns, identities, owner/ACL and compatibility evidence are also retained.
The execution manifest binds the reviewed plan, external backup, exact committed implementation,
source DVC revision, and pre-publication snapshot. The program prints its SHA-256.

Preserve the execution evidence with DVC/Git before applying it. Supply its literal hash:

```text
uv run python rsc/cses_db/publish_cses_value_mappings.py apply --root . \
  --apply --execution-sha256 <execution manifest SHA-256>
uv run python rsc/cses_db/publish_cses_value_mappings.py validate --root .
```

The hash selects the already authorized, concrete execution manifest. No new semantic approval is
required. The transaction acquires an advisory lock and locks the protected CSES tables, checks the
before fingerprints and target triggers, then inserts one release, 21 source rules, 140 values and
one load run. It compares every planned record and all protected state before committing. Any
difference rolls back the complete transaction. A retry validates the exact existing release and
does not add duplicate records. Sequence gaps after a rolled-back attempt are harmless PostgreSQL
identity allocation, not extra metadata records.

Independent validation uses a new forced read-only transaction and verifies all 163 records,
protected tables and full housing/local equality with the accepted comparison-only archive-path
normalization. Its output binds the import evidence and execution manifest. This command validates
the dictionary-only state; older baseline/correction-only preflights describe earlier catalog states.

The load history stores the exact predecessor source-rule IDs and interpretation notes. Value
metadata remains linked to the approved dictionary release; consumers should select this release
explicitly rather than joining every historical source mapping. Original numeric source-code columns
are unchanged. Draft evidence, compound/residual categories, and skip qualifications remain visible.

After validation, export new graph v6 files explicitly; keep v1–v5 immutable. The existing graph model
records value-mapping counts on source-rule edges, not one node per category. Preserve the full 140-row
dictionary in the database and release evidence, then synchronize the resulting data unit and release
documentation through DVC and Git.

Recovery needs an exact scope and should preserve newer records and append-only history. Do not
restore the scoped dump over a newer database as a generic rollback.
