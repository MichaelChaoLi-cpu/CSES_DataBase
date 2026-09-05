# CSES Housing Value Mapping Review Preflight v0.9

- Date: 2026-09-05
- Review: `cses-value-mapping-review-v1`
- Status: local review built; forced read-only database checks passed; publication not approved
- Base Git revision: `6c63fb591f4ccb734a7dbdfef77a2e502b0f9bc2`
- Input DVC pointer: `md5:3c393945cb2a4af8c12d24833590d0e6.dir`
- Versioning status: new planner, spec, tests, docs, and generated outputs await Git/DVC synchronization

The corrected housing state is the input, not a new write target. All 30 profiles and 208 code rows
were retained from the pinned historical audit and rechecked against the ten raw datasets. The review
separates 70 candidate label interpretations, 70 manual-review rows, 52 unresolved rows, and 16
missing-evidence rows. Every row remains proposed and non-publishable.

The code-9 correction in 2004 lighting is marked resolved, with baseline count 1 and current numeric
count 0. Other years' code 9 is not reclassified as missing. The 2021 tenure code 0 remains unresolved
(one raw observation, zero published numeric occurrences); the six observations with untranslated
2021 lighting code 8 remain unassigned. Unobserved labeled/option codes and all questionnaire gaps
remain visible.

All current per-wave/field numeric frequencies plus SQL NULLs account for their full row totals.
These are unweighted records, not population estimates or pooled unique-household counts. SQL NULL
is not assigned a source missingness reason by aggregate matching.

Live validation used a new forced `REPEATABLE READ, READ ONLY` transaction. All 35 protected physical
tables and correction metadata matched the accepted post-correction state. The full housing table
matched the local artifact after the documented comparison-only archive-path normalization. The
database snapshot SHA-256 remains
`35799d1996e5d75351da2f53feff9565296fc8c09feadb88a370bd6f4731f8b5`.
Canonical value mappings remain empty; there was no database mutation or new alignment release.

All 49 tests passed, including ten new review regressions. Ruff and Git whitespace checks passed.
Two independently built review bundles were compared byte-for-byte across all three output files.

| DVC-owned local output | SHA-256 |
|---|---|
| `value_mapping_review_v1/review.json` | `aec4d1184e3675ec30b69e79291c41c5838edebc9be45d42f3b0e1bc68fdd81f` |
| `value_mapping_review_v1/review.md` | `4053f7083aa5a8d448ad4bb2a11b8ca172d3e5055cf8ea63704a28bb24f32cb0` |
| `value_mapping_review_v1/overview.mmd` | `f6ec36b70d147303b26e1228a578a9b155013e83381abda1661bbcdc276840c7` |

Paths above are relative to `data/processing/cses/`. Exact input hashes and implementation-file
hashes are in `review.json`. Its Git revision is explicitly the base checkout because this step has
not committed the new code. The input DVC pointer is not a claim that the new outputs have been
versioned or uploaded.

The authoritative database topology remains graph v5. The new Mermaid file is a local evidence-review
projection, not graph v6 or a second source of database truth. Historical audit, correction, and
lineage evidence remain untouched. See the [review runbook](../cses-value-mapping-review-runbook.md)
and [topology](../cses-topology.md) for the review and later publication boundaries.
