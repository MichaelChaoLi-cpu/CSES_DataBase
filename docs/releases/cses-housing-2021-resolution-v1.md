# CSES housing 2021 resolution v1

Published and independently validated on 2026-09-06. Release identifier:
`cses-housing-2021-resolution-v1`. See the [current interface contract](../cses-housing-2021-resolution.md).

## Published result

- Added the 2021 lighting value `8 -> biogas`, supported by the original Khmer questionnaire
  and released Stata labels. All six observations now match the dictionary; code 9 remains Other.
- Registered both original English and Khmer questionnaires and four question records, retaining
  their conflicting lighting options, original-language text, cell locators, skip text and hashes.
  Updated only the two previously empty lighting/tenure question links to the Khmer evidence.
- Inserted ten metadata records in total and updated those two links. Added v4 dictionary and
  category views; v1/v2/v3 and all physical respondent values remain unchanged.
- The v4 dictionary has 201 entries. The v4 category view retains 77,922 rows, 66 columns and all
  19 unmatched household links. All non-null codes in the three reviewed housing fields across
  ten waves match a dictionary entry. This does not certify every housing variable or define an
  analysis population.
- Preserved the undocumented raw tenure code 0 as an explicit anomaly with unknown intended
  answer. The four published 2021 tenure NULLs remain three raw missing responses plus this
  anomaly. No imputation or row deletion was performed.
- Catalog totals are 1,746 variable mappings, 201 value mappings, nine releases/load runs,
  20 instruments, 171 questions and 296 question links. Existing 2014 and 2017 qualifications remain.

## Verification

The full test suite passed: **125 tests**. Ruff checks passed for the new publication/evidence
and orphan-audit code and tests. The independent current validator passed against `mda`, checking
the exact metadata change set, all original housing values, view definitions and read-only access,
coverage, tenure anomaly and fingerprints protecting 35 physical tables.

Graph v10 was exported twice with identical content: **4,838 nodes and 7,627 edges**. It preserves
the previous evidence/recovery edges and adds the two bilingual instrument evidence edges and
actual v4 view dependencies. Historical exports and validators remain frozen.

## Immutable artifacts

The following paths are DVC-owned; hashes are SHA-256.

| Path | SHA-256 |
| --- | --- |
| `data/releases/cses-housing-2021-resolution-v1/plan.json` | `471fb942991dd4619a271f8c6971064ebca06f2d93be3e6a8076dcd3c2735b75` |
| `data/releases/cses-housing-2021-resolution-v1/execution.json` | `6666409bf8bb52e6cd081a877a040dd1ab6cb386d7520d7c5dd9927bc36d4183` |
| `data/releases/cses-housing-2021-resolution-v1/import.json` | `2afa5fd95a70a1a406c5d361c992351243ce990d1a2e70980101d1de6881be3e` |
| `data/releases/cses-housing-2021-resolution-v1/validation.json` | `f5168f0d661f2518435ed46c27684238262895867b249a52c9f1c048d4ea6938` |
| `data/lineage/cses_lineage_graph_v10.json` | `78a871252df283d54d765458a77d61236fa94f4c4a5bae87853ac922f50d5779` |
| `data/lineage/cses_housing_interface_topology_v4.json` | `8ecec6e9ebe4cb8d7b44c4243e867f73d1423e15c8c82b455165874625d2bc88` |
| `data/processing/cses/final_HO_CSES.parquet` (unchanged) | `e0dae1a43267250b22fd8e18070b4a9243cd8f451fd40511ac4f7666e4b4826d` |
| `data/processing/cses/housing_orphan_audit_v1/report.json` | `db2dee56b57546bb58ad7d569769c558b58389d2208bd38eb5e0af94ff1da28b` |

The execution manifest pins publication code and source evidence by hash. Publication is not
retrospectively attributed to a Git commit created after the transaction.

## External recovery snapshots

Both snapshots were checked using their table of contents and full `pg_restore` decompression
before publication. They cover the affected metadata tables and analysis schema, not a new full
physical-data backup. Existing source/physical-data recovery provenance is unchanged.

| Path | SHA-256 |
| --- | --- |
| `/Volumes/MikesDataBackup/PG_DB/mda_cses_2021_metadata_wsmym5ov.dump` | `d9397b1549e83139d8e5da052cbc4c8fbe27cfd122c8cd919f945abb9f2e5528` |
| `/Volumes/MikesDataBackup/PG_DB/mda_cses_2021_analysis_schema_pw99dvl2.dump` | `f0854039eaf6deaab33afa0d5febd4407bf4b1c4424fab64d453ffc9b591bd9a` |

## Follow-up: existing 19 household linkage exceptions

The read-only audit examined identifiers across 174 original Stata members in the 2004, 2009
and 2014 archives and checked the exact exceptions in PostgreSQL. All 19 lack an original
member-roster match. The household builder uses that roster as its household base.

- 2004: 16 housing rows have all raw housing question fields empty; their household headers
  also lack household size.
- 2009: one answered housing row occurs only in the housing file among identifier-searchable
  source members; no member-roster, core or weight match was found.
- 2014: two answered housing rows have household headers and other-module evidence, but no
  member-roster match. One has three education records, corresponding to already known
  education-to-member exceptions rather than a newly created error.

This is an inherited source/base-population mismatch, not row loss in the current PostgreSQL
join. The upstream cause and intended corrections remain unknown. All rows and flags are
preserved; no household or member records were synthesized. See the
[detailed diagnosis](../cses-housing-orphan-diagnosis.md).

## Archival status

Database publication, independent validation and the read-only orphan audit are complete.
`dvc add data/` completed, and local `dvc status` reports data and pipelines up to date.
The new `data.dvc` directory MD5 is `649ebe11a1bd58ecf5bf79bd6f7519e8.dir`, covering
142 files and 518,597,103 bytes. `etc.dvc` is unchanged; data payloads remain excluded from Git.

The preceding `dvc push data.dvc -r storage` targeted `/Volumes/MikesDataBackup/dvc_remote`.
On 2026-09-06 its process had ended, and a fresh `dvc status -c data.dvc -r storage` confirmed
that the cache and remote are in sync. Local `dvc status` also remained up to date. The previous
transfer's terminal completion output was unavailable; this independent check establishes the
current remote completeness without asserting a transferred-object count.

The user approved the exact 41-path Git archive with message
`Record CSES housing evidence resolutions and orphan audit` on `main`, followed by a normal
push to `origin main`. It excludes all local `.codex/` files and DVC payloads. This note is prepared
for that archive; its containing commit records the source/pointer version. Git history and the
reported remote verification establish the commit and push outcome, without a self-referential
commit hash or a pre-emptive claim of successful push in this file.
