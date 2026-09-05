# CSES Housing Interface v1 Publication

The second step of the accepted readiness plan is complete. Two additive views are published in
`mda.cses_analysis` and independently validated. No existing table, metadata row or compatibility
view was replaced, and no new schema was created.

## Published interface

| View | Rows | Contract |
|---|---:|---|
| `cses_housing_value_dictionary_v1` | 140 | Exact approved code dictionary with rule identity and qualified review evidence |
| `cses_housing_categories_v1` | 77,922 | All original 50 housing columns plus 16 category/provenance columns |

The wide view retains the unique `survey_wave, household_id` key, all ten waves and the 19 unmatched
HH records. Matching requires release, source archive/member, wave, field and code. Three LEFT JOINs
preserve every housing record; the existing source path compatibility normalization is comparison-only.
The existing reader role `mda_readonly` has SELECT on both views and successfully queried their counts.

No seventh alignment release/load run was inserted: these views consume
`cses-housing-value-mapping-v1`. Interface provenance is bound in the view comments, execution/import
records and graph v7. View OIDs at publication are 650276 (dictionary) and 650281 (categories).

## Coverage and interpretation

| Field | Matched rows | Unmapped non-null rows | Published NULL rows | Total |
|---|---:|---:|---:|---:|
| Tenure | 66,565 | 11,269 | 88 | 77,922 |
| Cooking fuel | 66,629 | 11,268 | 25 | 77,922 |
| Lighting | 66,626 | 11,277 | 19 | 77,922 |

These counts are per field, not additive household populations. Match statuses are `matched`,
`unmapped_nonnull` and `source_null`. Neither unmatched codes nor NULLs are silently removed or
assigned new meanings. The three source fields retain their already published values, including the
earlier one-cell 2004 lighting correction.

The 2007/2013/2017 unresolved substantive values remain unmatched, as do six 2021 lighting observations.
The 52 unresolved and 16 missing-only review code entries remain excluded from the substantive
dictionary. The original 2014 draft, skip annotations, compound and residual qualifications are
available in the evidence JSON. This is not certification of a common analytical denominator,
cross-wave comparability, clean-fuel status or grid access.

## Verification

- All 86 repository tests passed, including the interface's 11 regression cases. Ruff passed.
- A forced read-only preflight checked both prospective queries, exact dictionary/evidence records,
  every housing category/status/label/rule identity, all original columns, key uniqueness and row count.
- The publication transaction locked the protected CSES tables and permitted only two new views,
  their comments and SELECT grants. It rejected existing target names and checked for DDL event triggers.
- All 35 pre-existing physical tables and the earlier dictionary release remained at their accepted
  state. The structural comparison excludes only the two explicitly authorized new views; no arbitrary
  new objects or prior changes are ignored. Full housing/local equality was retained.
- Independent validation repeated these checks in a new forced read-only transaction and checked the
  new view identities, owner/ACL, security-barrier options, comments and definitions against the import.
- Two graph exports were byte-identical. The extension's dependencies came from PostgreSQL, not inferred
  field-name similarity.

The prior raw-root regression whitelist was extended only for this interface's anchored comparison
normalization; dedicated tests ensure exact source matching and unmodified source-path output.
Builders still must not use the legacy raw-root path. Earlier publication implementations and their
immutable evidence were not rewritten.

## Recovery and evidence bindings

The external custom-format backup is
`/Volumes/MikesDataBackup/PG_DB/mda_cses_housing_interface_v1_bpslwxlm.dump`, SHA-256
`8c8c930466df08a3d49c8450c6d28482fec444fb7cd6e1b60fd9f90ad8616e46`.
It contains the prior `cses_analysis` schema definitions only, not respondent data or a full database
backup. Full decompression passed. Both target names were absent before publication. Any recovery or
view removal needs exact dependency review; do not restore this dump wholesale over newer state.

| Artifact | SHA-256 |
|---|---|
| Accepted readiness inventory | `d5290547cb0c352d4cbde9122744a7f910814a69c6321ccfe50108319ce2f1d0` |
| Interface `execution.json` | `1c30a3aacec68ec6d4d055292c0e5bcb7553a5f6e18eddccf98441773eee0411` |
| Interface `import.json` | `7e37f31697d5f694472ffb75bcf9db3c028af99f33a7b20f7605cd41b077f2cc` |
| Interface `validation.json` | `3761a5aaae12500a4c166eb9a8c908dd11feb986835a55b632e125b12fbfefb6` |
| Graph v7 | `4ad312935c6e615a32f664503541d32a4efdf6e670b8af43602c4f66af09a520` |
| Interface dependency JSON | `16e42367303ed3e27418dd3faffce11ceb382a0d2ddfdbee02a4c4ec7903df24` |

Interface execution, import and independent validation records are under
`data/releases/cses-housing-interface-v1/`. The validation record binds the import hash; the execution
record contains exact implementation/input hashes and prospective query fingerprints. Its base Git
revision is `fcd25ba`; the new code and evidence were not Git/DVC archived as part of this operation.
Subsequent archive commands should preserve these evidence files rather than regenerate their base IDs.

## Lineage and current operation

Graph v7 has 4,813 nodes and 7,540 edges. It preserves graph v6 and adds two view nodes, seven nodes for
existing metadata relations, and 18 schema/dependency edges. No category node or respondent node is
invented. The graph and detailed dependency list are under `data/lineage/`; the human-readable
[topology](../cses-topology.md) explains the same boundary.

```bash
uv run python rsc/cses_db/publish_cses_housing_interface.py validate --root .
```

This is the current validator after the new views exist. Dictionary-only and correction-only
validators are pinned historical contracts and must not be weakened to accept new view structure.
For queries, publication/recovery boundaries and graph replay commands, see the
[housing interface runbook](../cses-housing-interface-runbook.md).

The next work item is evidence review for the unresolved housing codes and missingness questions,
followed by household/member foundations. The interface keeps those gaps visible while the review
continues; it does not silently resolve them.
