# 2004 age top-code interface publication v1

Published to `mda` after explicit user approval on 2026-09-06. The release creates exactly five
ordinary security-barrier views in the existing `cses_analysis` schema, their comments and SELECT
grants to the existing `mda_readonly` role. No physical rows, prior canonical definitions, questionnaire
links, releases/load-run records, schemas or existing views were changed.

The [interface contract](../cses-age-topcode.md) explains the nullable 2004-specific fields and
interpretation limits. Other waves remain outside the rule scope rather than being declared free of
topcoding. Code 96 remains in the source age column and receives a lower bound of 96; its exact-year
qualification is NULL. This is not a new missing-age recode or a change to the analytical sample.

## Published objects and checks

| View | Rows | Top-coded rows |
| --- | ---: | ---: |
| `cses_analysis.cses_hl_age_v1` | 358,920 | 3 |
| `cses_analysis.cses_ed_age_v1` | 343,204 | 3 |
| `cses_analysis.cses_ec_age_v1` | 332,903 | 3 |
| `cses_analysis.cses_hh_head_age_v1` | 77,904 | 0 |
| `cses_analysis.cses_age_2004_rule_v1` | 4 | Not a respondent table |

The affected HL/ED/EC keys identify the same three people. A read-only example query confirms all
three have lower bound 96. The 2004 member age-65+ count remains 3,081. Household-head age is unaffected.

Verification includes:

- 188 passing tests, including the age and publication guardrails; Ruff and Git whitespace checks.
- Fresh natural-key/age/qualification comparisons against the four frozen canonical Parquet files.
- Full-row multiset comparison of every original view column with the underlying physical relation.
- Exact source-rule wording, file/hash, sheet/cell and review identity checks for the four metadata rows.
- Content hashes and row counts for all 35 pre-existing CSES physical relations, and protected prior
  structure/comments/permissions including CSES public compatibility views.
- Complete creation/validation rollback rehearsal, followed by fresh proof that all five names were
  absent and the protected baseline unchanged.
- Transactional publication, followed by independent forced read-only validation of definitions,
  comments, permissions, all results and actual `mda_readonly` access/counts.
- Read-only execution of the [SQL examples](../../rsc/sql/cses_age_topcode_examples.sql).

## Provenance and backup

Approved plan SHA-256:
`cfcf46ba2e2f060782bf7e5c4a7f885fc310bf856e614049e1fdd7fdd1b6b48a`.

Execution SHA-256:
`210b8b6c508557c4a45e7bddd7d88bba07785218bbc6a844c113f739f30f6202`.

The external backup is
`/Volumes/MikesDataBackup/PG_DB/mda_cses_age_2004_analysis_3zb10s4r.dump`, SHA-256
`d7e74fb432885da11fe00da0dff95c9a677bb18ab76278564f6cdbcc86798955`.
It is a private-permission, custom-format **cses_analysis schema-only** backup, not a full database
or respondent-data backup. Complete decompression was verified before either write transaction.
The new views had no previous contents to back up. Restoring or removing objects is separately
authorized recovery work; do not restore this dump blindly over newer database definitions.

Immutable DVC-owned records:

- [Execution and protected baseline](../../data/releases/cses-age-2004-topcode-v1/execution.json)
- [Rollback rehearsal](../../data/releases/cses-age-2004-topcode-v1/rollback_test.json)
- [Committed publication](../../data/releases/cses-age-2004-topcode-v1/import.json)
- [Independent validation](../../data/releases/cses-age-2004-topcode-v1/validation.json)

The execution binds exact implementation and input hashes. Its Git base revision does not imply
that the new code has already been committed. No Git commit/push or DVC add/push was performed here.
No tenth mapping release/load run was fabricated for this additive interface-only publication.

## Lineage and current validator

Graph v11 has **4,843 nodes and 7,640 edges**. It preserves every v10 node and edge, adds five view
nodes, five schema-exposure edges, four database-verified physical-table dependencies, and four
explicit logical evidence-rule links. The latter describe source interpretation, not a SQL join.
The constant rule view has no physical-table dependency.

Both [graph v11](../../data/lineage/cses_lineage_graph_v11.json) and the
[age topology](../../data/lineage/cses_age_topcode_topology_v1.json) were exported twice byte identically.
Graph SHA-256: `d5531f4fa4eaabfc06049d2ac449a0817fe8e7860b3333a878be5617fbdec677`.
The unchanged prior graph v10 SHA-256 is
`78a871252df283d54d765458a77d61236fa94f4c4a5bae87853ac922f50d5779`.

```bash
.venv/bin/python rsc/cses_db/publish_cses_age_topcode.py validate
.venv/bin/python rsc/cses_db/publish_cses_age_topcode.py export
```

Use this current validator for the expanded interface state. Earlier publication validators remain
frozen and may reject the newly added structure; do not weaken their historical checks. The housing
v4 interface itself is unchanged. All other questionnaire candidates, gaps and future publication
decisions retain their previous review boundaries.
