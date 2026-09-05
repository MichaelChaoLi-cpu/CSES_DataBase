# Recovered 2007/2013 housing evidence v1

Published and independently validated on 2026-09-05. The user approved completing the recovered
housing evidence. Scope, cell locators, interpretation and current commands are in the
[runbook](../cses-housing-recovered-evidence.md).

## Published scope

| Change | Count |
| --- | ---: |
| New alignment release / successful load run | 1 / 1 |
| New versioned source rules / value definitions | 6 / 39 |
| New 2007 code-lookup instruments / 2013 questionnaire instrument | 3 / 1 |
| New 2013 housing questions / reviewed source-question links | 3 / 3 |
| Total inserted metadata records / updated existing source-link records | 54 / 3 |
| New additive analysis views | 2 |

The v3 dictionary has 200 entries: all 161 v2 entries unchanged plus 39 recovered definitions.
The housing interface remains 77,922 rows and 66 columns, including all 50 original physical columns
and all 19 unmatched HH records. All 22,289 non-null tenure/cooking/lighting values in 2007/2013
match; all ten source NULLs remain. Every actual source code was checked against its own wave's
evidence and reconciled by source-row identity to the pinned local housing release.

The database now contains 1,745 variable mappings, 200 value mappings, eight releases, eight load
runs, 18 instruments, 167 questions and 294 source-question links. The 51 provisional 2014 links
remain unchanged. Instrument registration covers the full 24-sheet 2013 workbook, not a claim that
all its sections have been question-cataloged. No 2007 household questionnaire was fabricated; its
independent lookup evidence is explicitly distinguished from questionnaire or embedded Stata labels.

The raw archives, all physical respondent data, earlier release records, v1/v2 views and 2017
user-approved transfer were preserved. Two historical 2021 code interpretations remain unresolved:
lighting code 8 (six currently unmatched observations) and raw tenure code 0 (one raw observation,
absent as a non-null code in the inherited published field). This release does not alter either.

## Validation and preservation

- Ruff and `pytest rsc/tests -q`: **113 passed**.
- Predecessor v2 validation passed before preparation; prospective SQL EXPLAIN and exact target
  identity checks passed. All three target source-variable links were initially empty.
- Verified custom-format external backups cover the seven affected metadata tables and existing
  analysis-schema definitions. Both archives were fully decompressed for integrity checking.
- Transactional application locked all 35 physical CSES tables, rejected unexpected triggers,
  compared planned and actual new records, and verified `mda_readonly` access to both new views.
- Protection fingerprints retained every pre-existing table row and view definition, masking only
  `question_id`, `question_link_status`, and `question_link_role` on source-variable IDs
  1863, 1887 and 1900, whose exact approved new links were separately verified.
- An independent new read-only transaction verified all original housing cells against local
  Parquet, every category/status/evidence association, per-wave coverage, source registry/links,
  old-state preservation and new view OIDs/ACLs/security options/definitions.
- Graph v9 and its topology JSON were exported twice identically: **4,828 nodes, 7,600 edges**,
  with four recovered-evidence edges and the preserved 2017 user-decision edge.

## Immutable evidence

Files under `data/releases/cses-housing-recovered-evidence-v1/`:

| File | SHA-256 |
| --- | --- |
| `source_evidence.json` | `b10ed3169c9e24347780cceaf8e1615cdbf5ad14890dd24dce1089feed047c6f` |
| `plan.json` | `9ca72bdb85a3229bcd406dfd2d99d82a4571a54b04893c8e7a43c7fbf0e10995` |
| `execution.json` | `879eabe18ab7c20f67c0177f042dfdb90f5e9ac0c91db3751913374a992c7372` |
| `import.json` | `8bf4d12b5f581e40abd2d4cd87299bf69c17b00ff2435eec2f6691865ca2825e` |
| `validation.json` | `b5def57c76412ed337377d861c341e24bec4ef5179765a981412e608df86d52a` |

Additional artifacts:

| Path | SHA-256 |
| --- | --- |
| `data/lineage/cses_lineage_graph_v9.json` | `0c526fc958d1ca3fc5d32cbd359f78220b502b41aa315ca8d5cc0f2c8d37a025` |
| `data/lineage/cses_housing_interface_topology_v3.json` | `450837fb7aeed5f93bb1670e8a11cc433286b29f7b994d78da014bdf0170c547` |
| `data/processing/cses/final_HO_CSES.parquet` (unchanged) | `e0dae1a43267250b22fd8e18070b4a9243cd8f451fd40511ac4f7666e4b4826d` |

External backups, outside Git/DVC:

- `/Volumes/MikesDataBackup/PG_DB/mda_cses_recovered_metadata_uj0k59sg.dump`:
  `2fe664b97066297df2bc37cc8b192a6d077fc74a9e7d7cb83c0da6ce3a0774aa`.
- `/Volumes/MikesDataBackup/PG_DB/mda_cses_recovered_analysis_schema_kio28jsq.dump`:
  `9eeeea2bdbb6e497b617d6ac8b02d9c3cb5cc2017e963d54e791f7e91dad0181`.

The execution manifest pins exact implementation, specification, evidence and predecessor hashes.
The load run deliberately has NULL Git/DVC revision fields because this implementation is not yet
archived; it records exact hashes instead of attributing new code to an older commit. Neither Git
commit/push nor DVC add/push was performed in this delivery. Historical release artifacts and
validators remain unchanged; the new publisher is the current validation/export entry point.
