# CSES Housing Value Mapping Publication v1 and Lineage Graph v6

Date: 2026-09-05. Database: `mda`. Release: `cses-housing-value-mapping-v1`.

## Outcome

The approved dictionary was published in one transaction and independently validated in a new forced
read-only transaction. Exactly 163 metadata records were appended:

| Record family | Added | Current total |
|---|---:|---:|
| Alignment releases | 1 | 6 |
| Versioned source-to-canonical rules | 21 | 1,736 |
| Value mappings | 140 | 140 |
| Completed load runs | 1 | 6 |

No existing record was updated or deleted. No new schema, physical column, analytical view, or data
rewrite was introduced. The dictionary uses `cses_alignment.cses_value_mapping`, linked to new
release-specific `cses_variable_mapping` records. The 21 effective predecessor rules remain intact;
the new 2004 lighting rule copies correction mapping 1715, not superseded baseline mapping 57.
The load history retains all predecessor IDs and versions.

The accepted scope contains 28 tenure, 58 cooking-fuel, and 54 lighting entries across 2004, 2009,
2011-12, 2014, 2016, 2019, and 2021. These represent 24 field-specific categories and include nine
zero-frequency labeled/options-only codes. They are code dictionary entries, not 140 household rows.

The 52 unresolved and 16 missing-only review rows remain excluded. Twenty provisional 2014 entries,
46 skip annotations, and 25 compound/residual qualifications remain in the approved evidence.
`Other` remains wave-specific; compound options remain distinct; electrical labels do not establish
grid access or technology. Identical numeric codes do not establish cross-wave equivalence. This
release does not settle analytical denominators or reinterpret undocumented missingness.

## Validation and recovery evidence

- All 65 tests passed; Ruff passed on the publication implementation and regression tests.
- Fresh source replay matched all 30 reviewed profiles. All 100 available questionnaire options
  matched their retained cells and five original source members; the other 40 approved entries retain
  Stata-label evidence.
- The transaction compared every intended metadata record before commit and protected all 35 CSES
  tables. Only the newly appended release records are excluded from the four affected metadata-table
  fingerprints; every earlier record remains protected.
- Independent validation found the exact same 163 records and before/after protected fingerprint.
  Housing remains 77,922 rows and 50 columns, with full content and compatibility projection unchanged.
  All 22 registered storage relations retain their coverage and compatibility interfaces.
- Full database/local housing equality uses only the previously accepted comparison-time normalization
  of anchored `data/raw/CSE/` to `data/raw/`. Database paths were not rewritten. The local housing
  Parquet SHA-256 remains `e0dae1a43267250b22fd8e18070b4a9243cd8f451fd40511ac4f7666e4b4826d`.

The verified custom-format backup is
`/Volumes/MikesDataBackup/PG_DB/mda_cses-housing-value-mapping-v1_k5m__9vx.dump` (71,049 bytes),
SHA-256 `20a355d73821d48e361ae20df10abeed94f5062d49ee9e4bf8252018c109ef84`.
It covers exactly the four affected metadata tables, not all of `mda`. Its table-of-contents and full
decompression checks passed. Recovery requires explicit scope and preservation of any newer records;
do not restore it wholesale over later state.

## Immutable evidence and version chain

The original review, manual decisions, combined preflight and graphs v1–v5 remain unchanged.
New publication evidence lives under `data/releases/cses-housing-value-mapping-v1/`.

| Artifact | SHA-256 |
|---|---|
| Reviewed `plan.json` | `2f6fdca4705af007cdc982c71044adeada9fc54b97a40620d2871d3cc9577209` |
| `execution.json` | `7b39154df6cfd748a67c07551c8c527203e711e7283fac7323e59e0669da39eb` |
| `import.json` | `666b3b234bbc2dd6c6fdf20c19b670429c672f34562df5a04f2c28db76ace2c0` |
| `validation.json` | `0795b52319a9ed2268e878e48a89f1e2c9f95c4254f1887e4be87fbb4c39defa` |
| Protected state, excluding only new release records | `fdf3f948703e438f317564737eb2f957403e26fd7888b7737ded27a114cdeacf` |
| Canonical published record content | `2870089cc4abc0d999f16abf3265192b4fd1cc58a8eedb9d549451464ca38922` |

The protected-state fingerprint differs from the older correction snapshot fingerprint by design:
the current check includes all earlier correction metadata and excludes only this dictionary release.
Both definitions are preserved in the execution manifest and historical preflight evidence.

| Milestone | Git / DVC reference |
|---|---|
| Approved input archive | Git `1249bc3c1f4ae997db52f88cb1827934f1fafec2`; DVC `ee7cba014b37f11bda832825b842d747.dir` |
| Executed implementation | Git `ad4d6dc4a605af20eeeda76e47329775d062eff6` |
| Pre-apply execution evidence | Git `089d2b7`; DVC `db49db9b1f3c64d4e94ec45c5e46b91a.dir` |
| Final publication evidence | DVC `5ad55e960b423151f845bd240b0b2cd4.dir` (113 files; 488,854,364 bytes) |

The final Git commit containing this record and `data.dvc` identifies the output version without a
self-referential commit hash. The load run's DVC revision deliberately identifies the reviewed input
bundle, not the later output bundle. Only four files were added after the execution checkpoint:
import and validation records, graph v6, and its overview. No earlier data artifact changed.

## Graph v6

The new deterministic projection contains 4,804 nodes and 7,522 edges, adding two nodes and 27 edges
relative to v5. There are 1,792 source-to-canonical edges for 1,736 mapping records because some rules
reference multiple source fields. The summary counts 140 value mappings, with per-rule counts on
source edges. Individual category labels are not graph nodes; the full dictionary remains in
PostgreSQL and the [approved scope](../../data/processing/cses/value_mapping_release_v1/approved_scope.md).

Two forced read-only exports were byte-identical:

| Output | SHA-256 |
|---|---|
| `data/lineage/cses_lineage_graph_v6.json` | `d29e33ae4637ec024db201abae6a3520c781122491102c3c2ced23e6cb6da35d` |
| `data/lineage/cses_lineage_overview_v6.mmd` | `55be8e7de6502d950503c4e829b93639f17bc6f8c744bbdfac2df61cd1d5b08f` |

Exporter implementation revision: `3e815137c9ad886666f6ed160cf77d397df0c661`.
The [topology document](../cses-topology.md) also explains the dictionary-specific relationships and
unchanged physical-data boundary, which the aggregate generated overview does not enumerate.

## Current operations

```bash
uv run python rsc/cses_db/publish_cses_value_mappings.py validate --root .
```

Use the [publication runbook](../cses-value-mapping-publication-runbook.md) for the exact execution
contract. Older correction-only and review preflights are pinned to earlier catalog states and are
historical; do not weaken their gates or regenerate their immutable outputs against the newer state.
Downstream consumers must select `cses-housing-value-mapping-v1` explicitly to avoid joining all
historical rules. An analysis-ready category view remains a separate output-contract decision.
