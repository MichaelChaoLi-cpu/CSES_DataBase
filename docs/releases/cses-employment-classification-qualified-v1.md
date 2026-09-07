# EC classification qualification and 2007 source-job release

Release: `cses-employment-classification-qualified-v1`. Scope was approved by the user's
“好的，修正” request. This is an additive release in the existing `cses_analysis` schema:
one source table and three security-barrier views, with no replacement of historical interfaces.
Published to `mda` on 2026-09-06 after a successful rollback rehearsal. Independent post-commit
read-only validation passed for all projected values, source rows, rule records and protected state.
The [interface contract](../cses-classification-corrected-interface.md) documents how to query
the new interpreted codes and the recovered source-job rows.

## Scope and boundaries

- `cses_ec_classification_v1`: 332,903 rows × 86 columns; all 74 prior columns preserved.
- `cses_ec_jobs_2007_source_v1`: 11,949 rows × 13 columns; original person/job-index evidence.
- `cses_ec_jobs_2007_v1`: 11,949 rows × 17 columns; source rows plus job-count exception flags.
- `cses_ec_classification_rule_v1`: 14 rows × 10 columns; explicit source-label rules.

Exactly 774 field-cells are interpreted as NULL in new fields, not overwritten in raw fields.
The 12 unlabelled code cells and substantive 2004 industry `00` remain unchanged. The 2007 source
contains 10,174 existing EC people, 65 index/count conflicts and 21 index-2-only rows, all retained.
The six 2007 main/secondary wide fields remain NULL because the job-index meaning is not verified.
This is source-layer recovery, not a certified main/secondary reconstruction.

The release increases the CSES physical-relation count from 36 to 37. All 36 existing physical
relations, their contents, prior column/view definitions, permissions, comments, constraints and
indexes are protected. Historical catalog, question links, variable mappings, the 22-entry storage
registry and load-run records remain unchanged. No eighth core table or new schema is introduced.
The source artifact is explicitly marked unregistered in the lineage extension.

## Verification protocol

1. Recheck frozen archive/review hashes and independently reproduce all 54 existing raw
   field-wave transformations, plus the supplemental 2007 key/grain and exception counts.
2. Force a repeatable-read/read-only preflight: compare every projected value of the 86-column
   EC query and the 17-column job query with local artifacts; compare all 14 rules.
3. Hash all 36 protected physical relations and snapshot old structures, ACLs, constraints and indexes.
4. Back up `cses_analysis` schema definitions with mode 0600 and verify full backup decompression.
5. Create and verify all four objects inside a transaction, roll it back, then independently
   verify target absence and unchanged protected state.
6. Repeat the transaction with the exact prepared execution hash and commit only after all checks.
7. Independently re-read committed rows, object definitions and all protected state; verify
   `mda_readonly` access. Export the graph from database-verified dependencies.

Whole-view comparison covers all 332,903 × 86 EC values, every 11,949 × 13 source-table value,
every 11,949 × 17 job-view value, and all 14 rule rows. Only the known historical raw-archive prefix
is normalized for comparisons; database paths are not rewritten. Earlier 2009 day recovery,
2004 age/status/hour qualifications, education and housing interfaces are protected, not rebuilt.

Older publisher validators have intentionally fixed physical-table counts and are not the validator
for this later 37-table state. Use `publish_cses_classification_correction.py validate` for this release.

## Frozen implementation and artifacts

| Artifact | SHA-256 |
| --- | --- |
| Classification review | `e26b6d86ba717cab287a2bddb4f2d9f2869281d04fd38ddf230902973b3bd4cd` |
| Publisher | `ae5d881a2a23d2a1aa218e49d74e3c175391f94f390bb4a7827483f1653e08e7` |
| Plan | `2c48902f23f08c5e2654c58d4c64d798a36792e005772e54f1029efa4b2908f2` |
| Execution manifest | `6c00852e26b63457517b572cc455caf70c52942c5108aff29c9a239da05c0e4c` |
| Committed import | `459d7bf08bab4de9ecda5a7c596ccad8eb188fd194eaa5f519667ec6550cbce7` |
| Independent validation | `b6ca93f262e9128e0f2babaae24870d9220a56c1100cc006a71b638f9d424bae` |
| Qualified EC Parquet | `43a032554a7265384297e5c11a968920932582cc4b56546d28d820641ff00e1e` |
| Source-job Parquet | `82886a21b04e0bac67187f456cd258dffd32954a469f5bc6431328c986f5f78e` |
| Job-view Parquet | `4ca1bfb9ffa6bd28d7dfed0b8c4a2a3d39a4038f6ed26f57c7d659cb78c6b02a` |
| Graph v14 | `0ad1cbb8b5651fbabf13c479ee6cbe24e85d794b6e45f519f258940a80b053da` |
| Classification topology v1 | `74a54a188f4a0fddbe83584812324e5061cf9ec19959c6577776e09cb52b95f9` |

Private schema-only backup:
`/Volumes/MikesDataBackup/PG_DB/mda_cses_classification_v78ehwub.dump`, SHA-256
`269b2932a482e1464bb4c6e9a175f7c1124ed8684d0b112619e52bd70f1a8c11`.
It contains no respondent data and is not a full-database backup; source-table contents are
reproducible from the hash-pinned raw archive and versioned Parquet.

Execution records live under
[`data/releases/cses-employment-classification-qualified-v1/`](../../data/releases/cses-employment-classification-qualified-v1/).
This includes the preflight manifest, rollback rehearsal, committed import and independent validation.
No Git commit, DVC pointer update or remote push is implied.

The full local regression suite passed 293 tests, including 12 new correction tests. Ruff and
the whitespace checks passed. Read-only SQL examples were executed against the committed database:
10,153 index-1 and 1,796 index-2 rows; 65 count conflicts; 21 index-2-only rows; 14 rules and 774
interpreted missing cells. Earlier age/education/employment execution-pinned files retained their hashes.

[Graph v14](../../data/lineage/cses_lineage_graph_v14.json) contains 4,853 nodes and 7,677 edges,
preserving every v13 node and edge. Its five new nodes are the source table, three views and an
explicitly unregistered archive-member artifact. Its 23 new edges include three database-verified
SQL dependencies, four schema links, 14 source-variable interpretation links, one logical rule link
and one source-artifact ingestion link. Rebuilding the graph twice from the verified dependencies
and prepared inputs produced byte-identical output.

## Reproduce and recover

The publisher provides `plan`, `prepare`, `apply`, `validate` and `export` modes. Publication requires
an absent exact target set, an unchanged execution hash, a verified backup and a successful matching
rollback rehearsal. Do not blindly retry a commit with an uncertain response: inspect the exact
four targets and execution record first. Never replace existing views in place.

After publication, use the independent `validate` mode and the
[read-only SQL examples](../../rsc/sql/cses_classification_examples.sql). The previous 74-column
interface remains directly accessible, so consumers can return to it without undoing or overwriting
data. Any removal of new objects requires an explicit request, dependency review and a separate
controlled migration; do not restore the schema backup wholesale into a live database.
