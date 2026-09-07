# Education current-level correction interface v1

Published to `mda` on 2026-09-06 after the user's instruction to correct the reviewed issue and
continue to the next module. Exactly two new security-barrier views, their comments and SELECT
grants were added in the existing `cses_analysis` schema. No physical data, existing interfaces,
historical metadata rows or baseline Parquet files were rewritten.

Use the [corrected interface](../cses-education-corrected-interface.md) for new ED analysis.
The original physical ED table, its `public` compatibility view and `cses_ed_age_v1` still retain
the old current-level groups. This release does not silently redirect those interfaces.

## Published scope

| Object | Rows | Columns | Role |
| --- | ---: | ---: | --- |
| `cses_analysis.cses_ed_aligned_v1` | 343,204 | 37 | Age-qualified ED plus correction and original-value/evidence fields |
| `cses_analysis.cses_ed_current_level_rule_v1` | 3 | 14 | Versioned, source-located correction rules |

Current source code 21 is printed as Postgraduate studies at `02 Education!AF7` in the inspected
2013, 2014 and 2016 forms. The correction changes the current-level harmonized group from 7=Other
to 6=Higher education for **30 records: 2013 six, 2014 eighteen, 2016 six**. The 2014 draft remains
explicitly qualified. The eight 2017 code-21 records remain unresolved and unchanged. Highest-completed
education code 21 belongs to a different question and is not changed. All three existing 2004 age-96+
qualifications remain present. No rows are deleted, imputed or added.

A [matching versioned Parquet](../../data/processing/cses/education_corrected_v1/final_ED_CSES.parquet)
is stored separately from the frozen baseline. Its archive paths use current repository-relative
names; the database retains historical names, normalized only during equality comparisons.

## Validation

- A schema-only backup was verified before writing; the full creation-and-validation transaction
  was rehearsed with rollback, then a fresh connection confirmed both names absent and protected
  state unchanged.
- The approved transaction created the two views. Independent forced read-only validation then
  compared all 343,204 rows and 37 projected columns with the locally reproduced correction.
- All 35 protected physical-table fingerprints and pre-existing structure, definitions, comments
  and permissions remain unchanged. The three rule rows exactly match the accepted source plan.
- The existing `mda_readonly` role can query both views with the expected counts.
- Read-only execution of the interface's SQL examples confirms the 6/18/6 correction counts and
  three source rules; a separate query confirms all eight unresolved 2017 values equal their originals.
- The full test suite passed: **232 tests**, including seven new correction tests and ten EC
  screening tests. Ruff and whitespace checks passed.

The accepted education review SHA-256 is
`84a0b5a99c9f7daa0b2a73baab4429d4e3b5f7477a8a66034a5683c6018a1916`.
Execution SHA-256:
`ebc4128cdd72d44820684857a41059a066f169547b110dc63063548ad0efb82e`.
Independent validation SHA-256:
`da1e54d05b3834591135da6c50e554eed020eb889abead518afbce9940c16ea8`.

## Backup and immutable evidence

The private-permission external backup is
`/Volumes/MikesDataBackup/PG_DB/mda_cses_ed_correction_5p3739n_.dump`, SHA-256
`529661a0817fcb86fb95b17116803a1f885b7ef5d7eb6de131fed1f58eaaf563`.
It contains **cses_analysis schema definitions only**, not respondent data or a whole-database
backup. Full decompression was verified. Restoring it or removing the new views requires a
separately scoped recovery decision; do not overwrite newer definitions with this historical dump.

- [Exact source plan and correction scope](../../data/processing/cses/education_corrected_v1/plan.json)
- [Execution hashes and protected baseline](../../data/releases/cses-education-current-postgraduate-v1/execution.json)
- [Rollback rehearsal](../../data/releases/cses-education-current-postgraduate-v1/rollback_test.json)
- [Committed publication](../../data/releases/cses-education-current-postgraduate-v1/import.json)
- [Independent validation](../../data/releases/cses-education-current-postgraduate-v1/validation.json)

This is an analysis-interface overlay, not a new physical canonical-data release. No extra alignment
release, source mapping or load-run row was inserted into the historical catalog. The three rule-view
rows and hash-bound execution record preserve the correction's provenance without misrepresenting
the unchanged physical data. No Git commit/push or DVC add/push was performed in this step.

## Topology and current validator

[Graph v12](../../data/lineage/cses_lineage_graph_v12.json) has **4,845 nodes and 7,644 edges**.
It preserves every v11 node and edge and adds two view nodes, two schema-exposure edges, one
database-verified dependency from `cses_ed_age_v1`, and one logical evidence-rule edge. The rule
edge describes the documented interpretation, not a SQL join. The constant rule view has no physical
table dependency. The [topology supplement](../../data/lineage/cses_education_correction_topology_v1.json)
records the verified dependency separately.
Both artifacts were exported twice byte identically; exact set comparisons also verified preservation
of every historical v11 node and edge, including their properties.

Graph SHA-256: `74d6dc71e1ea36f36a51ab3ddac369ef5a0ab3d84132c8c9f4feb3d0d5972641`.
The unchanged v11 SHA-256 is
`d5531f4fa4eaabfc06049d2ac449a0817fe8e7860b3333a878be5617fbdec677`.

```bash
.venv/bin/python rsc/cses_db/publish_cses_education_correction.py validate
.venv/bin/python rsc/cses_db/publish_cses_education_correction.py export
```

Use this release's validator for the expanded interface state. Earlier whole-catalog validators
may intentionally reject the additional names and must not be weakened or rewritten. Historical
education review documents remain unchanged evidence snapshots.

## Following module: EC screening

The [employment screening brief](../cses-employment-screening-alignment.md) and
[field-wave details](../cses-employment-screening-field-waves.md) review four of 39 employment fields:
28 question-wave correspondences in seven freshly re-extracted forms and 40 profiles across ten
waves. A read-only comparison checks the four fields plus keys, age and HL-link flag across all
332,903 EC records; it is not a new full-60-column validation. Source transformations were reproduced,
including the two-file 2004 merge. The two documents and machine-readable source/review evidence
were regenerated independently and compared byte for byte.

EC review SHA-256: `aedcd983cd2936f9eda895480150e09102677bb8cb3f157c88f7d7b1977fbf19`.
No EC values or question links were published. Different paid/unpaid-work meanings, search periods,
age universes and routing remain qualified rather than forced into a common labour-force definition.
The remaining 35 employment fields start with working hours and job status in the next batch.
