# CSES Housing Value Mapping Execution Preflight v1

Date: 2026-09-05. Release: `cses-housing-value-mapping-v1`.

The user authorized the complete archive, backup, publication, validation and lineage workflow.
The approved 140-entry semantic scope is unchanged. This record freezes execution preparation;
it does not claim that the database transaction has already run.

## Version and evidence bindings

| Item | Immutable reference |
|---|---|
| Approved review archive commit | `1249bc3c1f4ae997db52f88cb1827934f1fafec2` |
| Committed publication implementation | `ad4d6dc4a605af20eeeda76e47329775d062eff6` |
| Reviewed plan SHA-256 | `2f6fdca4705af007cdc982c71044adeada9fc54b97a40620d2871d3cc9577209` |
| Source evidence DVC revision | `md5:ee7cba014b37f11bda832825b842d747.dir` |
| Pre-apply evidence DVC revision | `md5:db49db9b1f3c64d4e94ec45c5e46b91a.dir` (109 files) |
| Execution manifest SHA-256 | `7b39154df6cfd748a67c07551c8c527203e711e7283fac7323e59e0669da39eb` |
| Backup evidence SHA-256 | `27db2e9c6a90418aba65454b330e6f47c16902a4abed862bdfe32009f8dd9979` |
| Reviewed baseline snapshot SHA-256 | `35799d1996e5d75351da2f53feff9565296fc8c09feadb88a370bd6f4731f8b5` |

The DVC-owned execution and backup records are under
`data/releases/cses-housing-value-mapping-v1/`. The source DVC revision deliberately identifies the
reviewed input bundle, not the later output bundle containing its own execution manifest.

## Backup and checks

The external custom-format dump is
`/Volumes/MikesDataBackup/PG_DB/mda_cses-housing-value-mapping-v1_k5m__9vx.dump` (71,049 bytes),
SHA-256 `20a355d73821d48e361ae20df10abeed94f5062d49ee9e4bf8252018c109ef84`.
Its scope is exactly four affected metadata tables: `cses_meta.cses_alignment_release`,
`cses_alignment.cses_variable_mapping`, `cses_alignment.cses_value_mapping`, and
`cses_meta.cses_load_run`. Table-of-contents and full decompression checks passed. This is not a full
`mda` backup and must not be restored over later state as a generic rollback.

All 65 tests passed; the new implementation and tests passed Ruff. Fresh source replay and the
100-questionnaire-option verification passed, and the live read-only database plan exactly matched
the frozen review. A second read-only snapshot matched its approved baseline fingerprint.

The execution manifest binds the committed implementation hashes, backup, plan, input DVC revision,
and all 35 protected CSES tables. Only records belonging to this new release are excluded from the
four append-only metadata fingerprints; earlier releases, including the lighting correction, remain
protected. The housing table and compatibility projection receive full-content checks.

## Authorized transaction

Append one approved release, 21 versioned source rules, 140 value mappings, and one completed load
run: 163 records total. No existing record update, deletion, physical data rewrite, or schema change
is authorized. The 2004 lighting rule retains predecessor mapping 1715 and its missing-code correction.
The 52 unresolved and 16 missing-only rows remain excluded.

Use the literal execution hash above with the
[publication runbook](../cses-value-mapping-publication-runbook.md). Follow the transaction with an
independent read-only validation, graph v6 export/replay, and final Git/DVC synchronization. Keep all
earlier plans, reports, and graphs immutable.
