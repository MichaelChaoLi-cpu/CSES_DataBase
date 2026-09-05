# CSES housing 2017 transfer from 2016, v1

## Outcome

Published on 2026-09-05 under the user's explicit instruction to use 2016 definitions when the
data structure matches. The 2016/2017 housing column order and names match after case normalization.
This release covers only tenure, cooking fuel and lighting; it does not claim recovered 2017
questionnaire evidence or approve all variables in other sections.

The additive transaction inserted **26 metadata records**: one alignment release, three source
rules, 21 values and one load run. It created **two v2 analysis views**, retaining all v1 records,
views and physical data. All 35 pre-existing CSES physical tables were protected. The historical
mapping IDs 1165, 1172 and 1174 remain intact as the recorded predecessor rules.

| 2017 field | Adopted dictionary entries | Observed codes | Matched records | NULL records | Unmapped non-NULL |
| --- | ---: | ---: | ---: | ---: | ---: |
| Tenure | 4 | 3 | 3,839 | 1 | 0 |
| Cooking fuel | 8 | 5 | 3,840 | 0 | 0 |
| Lighting | 9 | 8 | 3,840 | 0 | 0 |

The v2 dictionary contains 161 entries. Its category view contains 77,922 rows and 66 columns.
All original 50 columns match the local Parquet after the established comparison-only archive-root
normalization. All 19 unmatched HH records are retained. Source labels remain NULL where absent;
transferred definitions are marked `user_approved_cross_wave_transfer` in their evidence.

Independent read-only validation passed. The test suite passed **104 tests**, including nine new
transfer checks. Graph v8 was exported twice without differences: **4,817 nodes, 7,562 edges**.
No Git commit, DVC add/push, or remote synchronization was performed in this operation. Execution
provenance uses exact file hashes and does not claim an archived code/data revision.

## Immutable evidence

| Artifact | SHA-256 |
| --- | --- |
| `data/releases/cses-housing-2017-from-2016-v1/plan.json` | `78b87ad69914ede6f7422d2028ce989eef4a6f131e92f1f26b0afd801ef91d9e` |
| `data/releases/cses-housing-2017-from-2016-v1/execution.json` | `536cabd51a07b4aa16281a6f2dd96b7a7ba4ac1446603a1f595c0dacb8460bb4` |
| `data/releases/cses-housing-2017-from-2016-v1/import.json` | `e85aa6b7e892f44b71a7f74470dc482e5f869242652d9353b2bd5ada6fe59e22` |
| `data/releases/cses-housing-2017-from-2016-v1/validation.json` | `6d2b34ac78874afbf20e22d2994bf1a091b6782605f22e5885d64659b378254c` |
| `data/lineage/cses_lineage_graph_v8.json` | `260a35330bda98abda025037ea82019b3ce2bbbad297f248db759881668fc623` |
| `data/lineage/cses_housing_interface_topology_v2.json` | `cdb82195ef1146764ef5f323de91a174565afd85befd834427de0bf9682f6aaf` |

## External recovery artifacts

Both backups were fully decompressed and hashed before publication:

- Metadata: `/Volumes/MikesDataBackup/PG_DB/mda_cses_2017_metadata_frl2n8rk.dump`,
  SHA-256 `cff6a9df4602291b6dfebd7e313434c8470f75432b564530b165bab2a049019a`.
- Pre-existing analysis schema definitions:
  `/Volumes/MikesDataBackup/PG_DB/mda_cses_2017_analysis_schema_pmiye4yo.dump`,
  SHA-256 `a1787a9a4f58acb6322e10bb9c0fbb1a924c984564e6503a86df8390ae8d7b0c`.

These are scoped recovery artifacts, not full database backups. Do not restore over newer state
without a separate reviewed recovery plan.

## Current commands

```bash
.venv/bin/python rsc/cses_db/publish_cses_housing_2017.py validate --root .
.venv/bin/python rsc/cses_db/publish_cses_housing_2017.py export --root .
```

Use `cses_analysis.cses_housing_categories_v2` for the expanded interface. The immutable v1 view
still intentionally leaves 2017 unmatched. Historical validators reject newer catalog state; do not
weaken them. See the [current runbook](../cses-housing-2017-alignment.md).
