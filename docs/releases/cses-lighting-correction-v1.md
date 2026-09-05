# CSES Lighting Missing-Code Correction v1

- Date: 2026-09-05
- Release: `cses-housing-lighting-missing-v1`
- Database: `mda`
- Status: applied, independently validated, and exported as lineage graph v5
- Approval: user accepted the archive, correction, verification, and database synchronization workflow

## Published change

Exactly one cell in `cses_data.final_HO_CSES.main_lighting_source_code` changed from 9 to SQL NULL:
survey wave 2004, household `1501320`, source row `2004:2004hh_s03_housing.dta:11580`.
The immutable archive member `CSES 2004/Stata 2004/2004hh_s03_housing.dta` records `q03_08=9`
with the explicit Stata value label `missing`. The source builder now excludes code 9 only for this
wave and field. Other waves retain code 9 wherever the earlier rule allowed it.

The rebuilt local housing artifact has 77,922 rows and 50 columns. Its exact before/after comparison
proves one changed cell and preserves all other values, keys, and dtypes. The issues file adds one
entry; the housing dictionary, alignment summary, and coverage audit remain byte-identical.
Other processing artifacts and all raw archives are unchanged.

The database transaction appended exactly three metadata records: one approved alignment release,
one revised variable mapping, and one load run. Mapping 57 remains intact; the correction load's
validation summary identifies it as superseded for the 2004 lighting source/canonical pair.
Consumers should use the correction release's explicit rule as an override, not interpret the two
historical records as two different canonical variables. There are now 1,715 variable mappings,
five alignment releases, and five load runs. Canonical value mappings remain empty.

## Validation and compatibility

Application was bound to the exact preflight plan SHA-256 and committed implementation. It used one
transaction, an advisory lock, protected-table locks, an exact old-value/natural-key/source-row match,
and before/after content checks. Its result is `updated_rows=1`, `updated_cells=1`.

Independent validation in a new forced `REPEATABLE READ, READ ONLY` transaction passed:

- All 35 CSES physical tables retain their protected content fingerprints. Only the approved cell
  and three appended metadata records are excluded from the protected comparison.
- Table identities, ordered columns, owner/ACL evidence, and compatibility definitions are unchanged.
- Every corrected local housing cell matches the database after the previously accepted,
  comparison-only `source_archive` prefix normalization, `data/raw/CSE/` to `data/raw/`.
  No database provenance path was rewritten; the before/after database fingerprints use original
  stored paths without normalization.
- The physical housing table and its `public` compatibility view have the same full content hash
  and row count. All 22 registered compatibility projections also passed lineage-export checks.
- Original source variables, canonical variables, questions, questionnaire links, dataset-output
  provenance, and prior release records remain intact. No schema or value-mapping publication occurred.

The housing validator passed, including unique keys, domains, and household-context consistency.
It retains the existing 19 unmatched household links rather than deleting source records. All 39 tests
passed, including six correction-specific regressions; Ruff and Git whitespace checks passed.
Historical catalog tests reproduce their original pinned builder and retained baseline artifacts in
an isolated fixture; they do not silently repin older releases to the corrected state.

## Backup and recovery evidence

Before application, a new custom-format dump was created and verified by table-of-contents inspection,
full decompression, size, and SHA-256:

`/Volumes/MikesDataBackup/PG_DB/mda_cses-housing-lighting-missing-v1_oa0xe8le.dump`

It is 1,895,885 bytes and covers exactly four tables: `cses_data.final_HO_CSES`,
`cses_meta.cses_alignment_release`, `cses_alignment.cses_variable_mapping`, and
`cses_meta.cses_load_run`. It is a scoped recovery artifact, not a full database backup, and is not
stored in Git or DVC. Recovery would need a separately scoped operation; do not blindly replace
append-only release history or newer data. The retained before image provides the original cell.

## Lineage graph v5

The post-correction graph contains 4,802 natural-key nodes and 7,495 edges: two nodes and six edges
more than graph v4. The correction rule carries its release and transformation on the source-to-
canonical edge. The graph includes five releases and five load runs, 1,771 source-field mapping
edges, and unchanged storage coverage for all 22 registered relations. It does not contain a
respondent-level node or a fabricated canonical value mapping.

Two consecutive forced read-only exports of both JSON and Mermaid files were byte-identical.
The exporter implementation revision is `3e815137c9ad886666f6ed160cf77d397df0c661`.
Graphs v1–v4 remain unchanged. See the [topology](../cses-topology.md) for the correction path and
the [export runbook](../cses-lineage-export-runbook.md) for safe versioned output commands.

## Fingerprints and version chain

All correction evidence is DVC-owned under `data/releases/cses-housing-lighting-missing-v1/`:
`before/`, `after/`, `before.json`, `backup.json`, `plan.json`, `import.json`, and `validation.json`.
Graph v5 is under `data/lineage/`.

| Evidence | SHA-256 |
|---|---|
| Exact execution plan | `68470cbeba231c0b09bb2bf06e2cb46e6a0163f9663d934246cfcf3c944c57c9` |
| Import record | `6aa48a67bebc822aee0a313695c0ee1cca233ad26333e9eac2609ff8bd0ad362` |
| Independent validation | `f4b51d586294c9f7d9dce9c02481c30a718d9c6b74949c3dcac62d0773ac3d15` |
| Original housing Parquet | `0c9922a6366737348d09721b985c8f3f402a38ab80ef8101558135b770cc35c8` |
| Corrected housing Parquet | `e0dae1a43267250b22fd8e18070b4a9243cd8f451fd40511ac4f7666e4b4826d` |
| Scoped external backup | `497f25056c6da8ae084f3816727a4f9eb4f6a22b61af6b32c8cdde567d2db8db` |
| Graph v5 JSON | `27bb249bb8496558bd0e8b580828b21fc4e644c079f62053dc1d5f9fdf5a14fc` |
| Graph v5 Mermaid | `c3d09cfe6949ef00cac81eff3db0ecc2ec7d030fbee64f423c88d138c806fd03` |

The full housing database content fingerprint changed from
`9fa2db8c5ecc185a8d19606e8d1e7d6d2f242bccf3582971f4a559307b461c34` to
`03f0fc45be58e1a559b95bcc7348896ed652b423fb0249c5b4236d2e0f9bf990`.
These are sorted SQL row-content fingerprints, not Parquet file hashes.

| Milestone | Git reference | DVC data pointer |
|---|---|---|
| Archived pre-correction value audit | `e8ced0a` | `md5:a24546010057cb38153543cfdf0d7490.dir` |
| Correction implementation bound by plan | `fbcea0ac9a7120e861a149d36e01fcc152afc406` | Source baseline above |
| Reviewed pre-application evidence | `870134c` | `md5:6bbbf72511e946daf3d2d1be1511cbdf.dir` |
| Completed correction and graph v5 | Commit containing this record and `data.dvc` | `md5:3c393945cb2a4af8c12d24833590d0e6.dir` |

The final data unit contains 100 files and 481,893,879 bytes. Relative to the pre-application pointer,
only four files were added: import evidence, independent validation, and the two graph v5 files.
The load run's `dvc_revision` deliberately identifies the immutable source baseline, not the later
post-application evidence pointer; the plan, implementation revision, and this chain identify the
remaining stages. `etc/` is unchanged. Git owns the code/docs and pointers; payloads are synchronized
to the configured DVC `storage` remote at `/Volumes/MikesDataBackup/dvc_remote`.

## Remaining review boundary

The original value audit remains a historical pre-correction report. Its proposed categories and
unresolved codes are not approved canonical mappings, and its pinned checks intentionally reject a
different builder/table/catalog state. Do not overwrite old plans, manifests, graphs, or reports to
make their checks pass on the newer release. The undocumented 2021 tenure code 0, untranslated labels,
compound/residual categories, and questionnaire evidence gaps remain separate review work.

See the [correction runbook](../cses-lighting-correction-runbook.md),
[preflight record](cses-lighting-correction-preflight-v0.8.md), and
[historical value audit](cses-value-audit-preflight-v0.7.md).
