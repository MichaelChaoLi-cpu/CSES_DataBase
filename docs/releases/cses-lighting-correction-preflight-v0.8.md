# CSES Lighting Missing-Code Correction Preflight v0.8

- Date: 2026-09-05
- Release: `cses-housing-lighting-missing-v1`
- Execution approval: user accepted the archive, correction, verification, and database synchronization workflow
- Status: successful read-only plan, before database application

The rebuilt housing table differs from the retained original in exactly one cell: wave 2004,
household `1501320`, `main_lighting_source_code`, 9 → NULL. All 77,922 rows, 50 columns, natural keys,
dtypes, and other cell values are unchanged. The source row is
`2004:2004hh_s03_housing.dta:11580`; the original `q03_08` value is 9 with the explicit Stata label
`missing`. Other years' lighting code 9 is preserved.

The housing dictionary, alignment summary, and coverage audit are byte-identical. The issues file adds
one entry for this one-cell correction. All other retained processing artifacts are unchanged.
The planned metadata additions are one approved release, one revised variable mapping, and one load
run. Original mapping 57 remains immutable; the new load record will identify it as superseded for
the exact 2004 lighting source/canonical pair. Canonical value mappings remain empty.

The database preparation records protected content fingerprints for all 35 CSES physical tables.
The target fingerprint masks only the one cell, while structure, owner/ACL, original row content,
and public compatibility evidence remain protected. The original local table matches every database
cell after the previously accepted comparison-only `source_archive` normalization:
`data/raw/CSE/` → `data/raw/`. Database provenance paths themselves are not changed.

| Evidence | SHA-256 |
|---|---|
| Exact execution plan | `68470cbeba231c0b09bb2bf06e2cb46e6a0163f9663d934246cfcf3c944c57c9` |
| Before evidence | `1d0d8481d4dc2dceaa701d65317c244c219e5b3a48caf76a5330bb651a5957ea` |
| Original housing Parquet | `0c9922a6366737348d09721b985c8f3f402a38ab80ef8101558135b770cc35c8` |
| Corrected housing Parquet | `e0dae1a43267250b22fd8e18070b4a9243cd8f451fd40511ac4f7666e4b4826d` |
| External scoped backup | `497f25056c6da8ae084f3816727a4f9eb4f6a22b61af6b32c8cdde567d2db8db` |

The plan binds implementation revision `fbcea0ac9a7120e861a149d36e01fcc152afc406` and individual code
hashes. The scoped backup is a 1,895,885-byte custom-format dump covering housing and the three
affected metadata tables; table-of-contents and complete decompression checks passed. It is stored
in the existing external PostgreSQL backup directory, not in Git or DVC. The backup path and hash
are recorded in the DVC-owned backup evidence.

See the [correction runbook](../cses-lighting-correction-runbook.md). The exact plan and retained
before/after artifacts are under `data/releases/cses-housing-lighting-missing-v1/`.

All 39 tests passed, including six correction-specific regressions. Ruff and Git whitespace checks
passed. The reviewed pre-application DVC pointer is `md5:6bbbf72511e946daf3d2d1be1511cbdf.dir`
(96 files, 476,109,417 bytes). Original archives and prior release evidence were not modified.
